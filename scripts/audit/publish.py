#!/usr/bin/env python3
"""Einen Lauf für die Kundenansicht bereitstellen.

Schritt 1 der Bau-Reihenfolge aus der Portal-Spec: der Lauf-Ordner wandert
**1:1** in den Bucket, nichts wird umbenannt, zusammengefasst oder neu
gerechnet. Was hochgeht, entscheidet eine Ausschlussliste (`manifest.EXCLUDED`),
keine Auswahlliste: im Zweifel hoch, denn es sind die Daten des Kunden.

**Hochladen ist nicht Freigeben.** Diese Datei setzt nie einen Freigabestatus.
Ein hochgeladener Lauf liegt im Bucket und ist für den Kunden unsichtbar, bis
`release` ihn sichtbar macht. Das hält das menschliche Gate aus dem
Audit-Design intakt: kein Lauf erreicht den Kunden, bevor der Betreiber ihn
gelesen hat. Benannte Ausnahmen sind der Wochenpuls, der Stand einer
Theme-Migration (`migration`) und das Setup eines Stores (`setup`): sie tragen
keine Befunde und keine Maßnahmen und sind sofort sichtbar. Migration und Setup
laden nur ihre eine Datei hoch und schreiben immer in dieselbe Fassung
(entschieden am 12.10.2026).

**Zwei Ebenen, zwei Bedeutungen.** `account_slug` aus der Config ist der Kunde
und damit die Login-Ebene, `brand` ist der Shop und damit die Ablage-Ebene. Ein
Kunde kann mehrere Shops fuehren; ohne diese Trennung braeuchte dieselbe Person
je Shop einen eigenen Zugang, und der zweite Shop waere eine Migration statt
eines Ordners.

**Dateien der Marke** (Spec `ptai-portal` 2026-10-08, Abschnitt 5.1 und 11).
Steht `brand_workspace` in der Config, liegen `measures.json`, `measures.md`
und `feedback.json` einmal je Marke. Sie gehen nach `brands/<slug>/` und
stehen im Manifest unter `files` an der Wurzel; je Store gehen nur noch
Baseline und Läufe hoch. Seit 0.3.16 gehören die Vorgaben der Marke dazu
(Vertrag V15): `policies.json` und jede Datei unter `policy-modules/`, aus
dem Ordner der Marke oder einem Ordner direkt darin (`brand.policies_dir`).
Sie gehen bei jedem publish mit, nicht nur mit `--brand-only`, weil jedes
publish `files` im Manifest neu schreibt; sonst verschwänden sie dort mit dem
nächsten Lauf. Vor dem Kopieren prüft `publish` ihr Format und dass jeder
Baustein aus `modules` daneben liegt, dazu gegen das neueste Setup jedes Stores,
dass das Cockpit jede offene Vorgabe erklärt und ihre Stores zeigt (`sheet_check`,
seit 15.10.2026). Ein Setup, das hochgeht, prüft es gegen sein Format. Vor dem Kopieren prüft `publish` die Liste der Marke
(`shops` und `by_shop` passen zusammen, jeder `finding_id` steht in seinem
Lauf `finding_run`, wenn der Lauf hier liegt). Die Vorschau geht dann je Marke
in eine eigene Testmarke `portal-test-<marke>` (D11), sonst überschrieben sich
die Listen zweier Marken in `portal-test`.

**Keine Aufgabe an die Marke, die nicht umsetzbar ist** (seit 15.10.2026).
Vor jedem Lauf mit Befunden und vor `--brand-only` prüft `publish` jede
anstehende Maßnahme der Marke: Befund belegt, Liste der Einzelobjekte im Lauf,
Empfehlung ohne unsere Werkzeuge (`audit.readiness`). Was die Marke im
Cockpit später als in Arbeit, umgesetzt, verworfen oder überholt gemeldet hat,
liegt bei ihr und hält nicht an, und ein Punkt aus ihrer eigenen Anforderung
braucht keinen Befund (seit 16.10.2026); die Meldungen kommen über
`audit.portal`, und ist das Cockpit nicht erreichbar, bricht `publish` ab.
Wochenpuls, Migration und Setup ändern keine Maßnahme und laufen ohne diese
Prüfung.

**Nur die Vorgaben** (`--policies-only`, seit 16.10.2026): `policies.json` und
die Bausteine gehen ohne Maßnahmen und Anforderungen hoch, geprüft wie bei
jedem anderen Weg, aber ohne die Prüfung der Maßnahmen. Eine neue Fassung der
Vorgaben wartet so nicht darauf, dass jede Maßnahme der Marke umsetzbar ist.

**Das Manifest unter Sperre und mit Zähler** (D12). Lesen, Ändern und Schreiben
des Manifests laufen unter der Sperre der Marke, und das Manifest trägt an der
Wurzel `revision`. Vor dem Hochladen holt `publish` das Manifest noch einmal
aus dem Bucket: hat es sich seit dem Lesen geändert, bricht es ab, statt den
Lauf eines anderen Stores aus dem Verzeichnis zu werfen.

CLI:
    python3 -m audit.publish --workspace . --run-id 2026-09-08-audit \\
        --target ~/tmp/bucket        # lokal, solange kein Bucket steht
    python3 -m audit.publish --workspace . --brand-only --target <leer> --upload
    python3 -m audit.publish --workspace . --policies-only --target <leer> --upload
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from datetime import date
from pathlib import Path

from audit import brand as brand_mod
from audit import manifest
from audit import measures

#: Dateien auf Workspace-Ebene, die zum Shop gehoeren und nicht zu einem
#: einzelnen Lauf: der Massnahmen-Backlog bewegt sich ueber Laeufe hinweg, die
#: Baseline ist der eingefrorene Nullpunkt, das Feedback haelt fest, was von
#: aussen hereinkam und auf welche Massnahme es zeigt. Alle drei braucht die
#: App fuer die Ansichten Massnahmen und Kennzahlen, und alle drei liegen
#: deshalb neben den Laeufen statt in einem von ihnen.
SHOP_FILES = ("measures.json", "measures.md", "feedback.json")
SHOP_DIRS = ("baseline",)

#: Diese Staende wandern zusaetzlich in den Lauf. Die Dateien auf Shop-Ebene
#: sind der aktuelle Stand und werden bei jedem publish ueberschrieben; die
#: Kopie im Lauf ist der Stand zur Zeit dieses Laufs und bleibt. Erst sie macht
#: den Vergleich zweier Laeufe moeglich, ohne dass eine Datenbank noetig waere.
#: Das Feedback gehoert dazu, weil eine Zuordnung sich zwischen zwei Laeufen
#: bewegt: aus einer vermuteten wird eine bestaetigte.
SNAPSHOT_FILES = ("measures.json", "feedback.json")

#: Was die Marke einmal für alle Stores führt. Liegt im Bucket unter
#: `brands/<slug>/` und im Manifest unter `files` an der Wurzel.
BRAND_FILES = brand_mod.BRAND_FILES

#: Vorsilbe der Testmarke je echter Marke (D11).
PREVIEW_PREFIX = "portal-test-"

#: Lauf-Arten, die nur eine Datei tragen. Von ihnen geht genau diese Datei hoch:
#: kein Transkript aus `sessions/`, kein Journal, kein `state.json`. Das Cockpit
#: liest nur sie, und alles andere im Lauf ist Werkstatt des Teams.
SINGLE_FILE_KINDS = {"migration": "migration.json", "setup": "setup.json"}

#: Lauf-Arten, die mit dem Hochladen sichtbar sind (benannte Ausnahme von
#: "hochgeladen ist nicht sichtbar"): sie tragen weder Befunde noch Maßnahmen.
AUTO_RELEASED = ("pulse", *SINGLE_FILE_KINDS)


def slugify(name: str) -> str:
    """Ein Shop-Name als Pfadsegment."""
    return brand_mod.slugify(name)


def destination(config: dict, account_slug: str | None = None) -> tuple[str, str]:
    """Marke und Shop, unter denen ein Lauf im Bucket liegt.

    Kommt der Shop aus dem Cockpit (Block `portal` in der Config), gelten dessen
    Schlüssel; das Cockpit ordnet Läufe über `public.shops.slug` zu. Bis zum
    08.10.2026 leitete `publish` den Shop immer aus `brand` ab: aus "Early
    Rider EU" wurde `early-rider-eu`, im Cockpit hieß der Shop `eu`, und der
    Lauf wäre als fünfter Shop neben den vier verbundenen erschienen.
    `account_slug` (etwa die Testmarke) ersetzt nur die Marke.
    """
    portal = config.get("portal") or {}
    brand = account_slug or portal.get("brand") or config["account_slug"]
    shop = portal.get("shop") or slugify(config.get("brand") or brand)
    return brand, shop


def run_kind(run_id: str, state: dict) -> tuple[str, str | None]:
    """Lauf-Art und Kadenz. Die Lauf-ID traegt sie im Namen (`<datum>-<kadenz>`),
    der Zustand bestaetigt sie."""
    # Der Stand einer Theme-Migration hat keine Kadenz, er nennt seine Art
    # selbst (`run_state.new`).
    if state.get("kind") == "migration":
        return "migration", None
    cadence = state.get("cadence") or (run_id.rsplit("-", 1)[-1] if "-" in run_id else None)
    # Ein Lauf der Kadenz `week` ist der Wochenpuls (Spec Wächter und Wirkung
    # im Repo `ptai-portal`, Abschnitt 3.2).
    if cadence == "week":
        return "pulse", cadence
    kind = cadence if cadence in manifest.KINDS else "report"
    return kind, cadence


def load_config(workspace) -> dict:
    """Die Reporting-Config des Workspace. Ohne `account_slug` gibt es keinen
    Kunden und damit keinen Bucket-Pfad."""
    config = json.loads((Path(workspace) / "reporting" / "config.json")
                        .read_text(encoding="utf-8"))
    if not config.get("account_slug"):
        raise SystemExit("reporting/config.json ohne account_slug: ohne Kunde "
                         "kein Bucket-Pfad")
    return config


def proof_problems(run_dir: Path, files: dict) -> list[str]:
    """Was an den Belegbildern eines Laufs fehlt, bevor er hochgeht.

    Zwei Fälle, beide aus dem Vertrag `reference/finding-format.md`: ein Bild-
    oder Handy-Block mit einem Aufnahme-Auftrag (`capture`) ohne `src` ist noch
    nicht aufgenommen, und ein `src` oder `full_src`, das nicht im Lauf liegt,
    zeigt im Portal ein kaputtes Bild. Beides sieht der Kunde, deshalb hält es
    den Upload auf, statt erst im Portal aufzufallen.
    """
    problems = []
    for name in sorted(n for n in files if n.startswith("findings/") and n.endswith(".json")):
        try:
            data = json.loads((run_dir / name).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            problems.append(f"{name}: nicht lesbar ({exc})")
            continue
        findings = data.get("findings") if isinstance(data, dict) else None
        for finding in findings or []:
            columns = ((finding.get("proof") or {}).get("columns") or []) if isinstance(finding, dict) else []
            for column in columns:
                for block in (column or {}).get("blocks") or []:
                    if not isinstance(block, dict) or block.get("type") not in ("image", "phone"):
                        continue
                    where = f"{name} {finding.get('id') or '?'}"
                    if block.get("capture") and not block.get("src"):
                        problems.append(f"{where}: Aufnahme offen, erst shoot_proof.py laufen lassen")
                    for key in ("src", "full_src"):
                        src = block.get(key)
                        if src and src not in files:
                            problems.append(f"{where}: {src} fehlt im Lauf")
    return problems


def manifest_key(brand: str) -> str:
    """Wo das Manifest einer Brand liegt, im Ziel wie im Bucket.

    Eine Stelle für beides: landet das geholte Manifest an einem anderen Pfad
    als dem, an dem `prepare()` sucht, ist der Fehler wieder da, den
    `fetch_manifest()` schließt.
    """
    return f"brands/{brand}/manifest.json"


def preview_slug(brand: str) -> str:
    """Die Testmarke einer echten Marke: `portal-test-<marke>`."""
    return f"{PREVIEW_PREFIX}{brand}"


def check_preview_target(config: dict, account_slug: str | None,
                         brand_files: bool) -> None:
    """Mit Dateien der Marke geht eine Vorschau nur in deren eigene Testmarke.

    Die Liste der Marke liegt im Bucket unter `brands/<slug>/measures.json`.
    Zwei Marken in derselben Testmarke `portal-test` überschrieben sich dort
    gegenseitig, und die Vorschau zeigte die Maßnahmen der falschen Marke (D11).
    """
    real = brand_mod.brand_slug(config)
    if not brand_files or not account_slug or account_slug == real:
        return
    expected = preview_slug(real)
    if account_slug != expected:
        raise SystemExit(
            f"--account-slug {account_slug}: diese Marke führt ihre Maßnahmen in "
            "einer Datei der Marke, und die läge in der Testmarke neben der "
            f"Liste anderer Marken. Vorschau mit --account-slug {expected}. "
            "Nichts kopiert.")


def brand_problems(workspace, backlog: dict, brand_reporting: Path,
                   config: dict) -> list[str]:
    """Die Prüfung vor `publish` für die Liste einer Marke (Spec 5.1, Abschnitt 11).

    Regel 2 (`shops` und `by_shop` passen zusammen) und dass jeder Befund in
    seinem Lauf steht: `finding_id` in `finding_run`, sofern dieser Lauf auf
    diesem Rechner liegt. Ein Lauf eines anderen Stores, der hier nicht liegt,
    ist kein Fehler, nur nicht prüfbar.
    """
    problems = measures.consistency_problems(backlog)
    own_shop = brand_mod.shop_slug(config)
    cache: dict[Path, set] = {}
    for measure in backlog.get("measures") or []:
        for shop, entry in (measure.get("by_shop") or {}).items():
            if not isinstance(entry, dict):
                continue
            fid, frun = entry.get("finding_id"), entry.get("finding_run")
            if not fid:
                continue
            if not frun:
                problems.append(f"{measure.get('id')}: by_shop.{shop} nennt "
                                f"Befund {fid} ohne finding_run")
                continue
            runs = brand_mod.store_runs_dir(brand_reporting, shop, workspace, own_shop)
            run_dir = runs / frun
            if not run_dir.is_dir():
                continue
            if run_dir not in cache:
                cache[run_dir] = brand_mod.finding_ids(run_dir)
            if fid not in cache[run_dir]:
                problems.append(f"{measure.get('id')}: by_shop.{shop} zeigt auf "
                                f"{fid} im Lauf {frun}, dort gibt es ihn nicht")
    return problems


def policy_problems(folder: Path) -> list[str]:
    """Was an den Vorgaben der Marke nicht gilt, bevor sie hochgehen (Vertrag V15).

    Das Cockpit gibt `policies.json` mit `get_policies` an jeden Store der Marke
    weiter. Eine Datei, die das Format verletzt, oder ein Baustein, der nicht
    daneben liegt, hielte den Start jeder Migration der Marke an.
    """
    # Erst hier importiert: audit braucht theme nur für diese Prüfung, und das
    # Format von policies.json hat genau eine Prüfung.
    from theme import policies
    path = folder / brand_mod.POLICIES_NAME
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [f"{path} nicht lesbar ({exc})"]
    problems = policies.validate(data)
    if problems:
        return problems
    for rule in data["rules"]:
        for module in rule.get("modules") or []:
            if not (folder / module["path"]).is_file():
                problems.append(f"Baustein {module['path']} der Regel {rule['key']} "
                                f"fehlt unter {folder}")
    return problems


def store_setups(brand_dir: Path, workspace: Path, current: Path | None = None) -> dict:
    """Das neueste Setup je Store, als `shop` auf Inhalt.

    Gesucht wird in jedem Ordner direkt im Ordner der Marke und im Workspace dieses Stores, je unter
    `reporting/runs/<datum>-setup/setup.json`; es gilt der Lauf mit dem spätesten Namen. `current` ist das
    Setup des Laufs, der gerade hochgeht, und gilt immer für seinen Store.
    """
    newest: dict = {}
    folders = [child for child in sorted(brand_dir.iterdir())
               if child.is_dir() and not child.name.startswith(".")]
    for folder in [*folders, workspace]:
        for path in (folder / "reporting" / "runs").glob("*-setup/setup.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            shop = data.get("shop") if isinstance(data, dict) else None
            if shop and (shop not in newest or path.parent.name > newest[shop][0]):
                newest[shop] = (path.parent.name, data)
    if current is not None:
        data = json.loads(current.read_text(encoding="utf-8"))
        newest[data.get("shop")] = (current.parent.name, data)
    return {shop: data for shop, (_run, data) in newest.items()}


def sheet_check(folder: Path, brand_dir: Path, workspace: Path,
                current_setup: Path | None = None) -> tuple[list, list]:
    """Fehler und Hinweise zum Blatt jeder Vorgabe im Cockpit (`theme.policies.sheet_problems`), dazu jeder
    fehlende Text für die Marke (`theme.policies.explanation_problems`, seit 16.10.2026)."""
    from theme import policies
    data = json.loads((folder / brand_mod.POLICIES_NAME).read_text(encoding="utf-8"))
    setups = store_setups(brand_dir, workspace, current_setup)
    reference = data.get("reference_shop")
    problems, hints = policies.sheet_problems(data, setups.get(reference),
                                              [setup for shop, setup in setups.items() if shop != reference])
    return problems + policies.explanation_problems(data), hints


def _check_brand_files(workspace, config: dict, brand_reporting: Path,
                       current_setup: Path | None = None) -> None:
    """Bricht vor dem Kopieren ab, wenn die Liste oder die Vorgaben der Marke nicht passen.

    Zu den Vorgaben gehört, dass das Cockpit jede offene erklären kann (`sheet_check`). `current_setup` ist
    `setup.json` des Laufs, der gerade hochgeht, falls er ein Setup ist.
    """
    backlog = measures.peek(workspace)
    if not measures.is_v2(backlog):
        raise SystemExit(f"{brand_reporting / 'measures.json'} ist keine Liste im "
                         "Format v2. Nichts kopiert.")
    problems = brand_problems(workspace, backlog, brand_reporting, config)
    if problems:
        raise SystemExit("Die Liste der Marke passt nicht, nichts kopiert:\n  "
                         + "\n  ".join(problems))
    folder = brand_mod.policies_dir(brand_reporting.parent)
    if folder is not None:
        _check_policies(folder, brand_reporting.parent, workspace, current_setup)


def _check_policies(folder: Path, brand_dir: Path, workspace,
                    current_setup: Path | None = None) -> None:
    """Bricht vor dem Kopieren ab, wenn die Vorgaben der Marke so nicht gelten oder im Cockpit unverständlich wären.

    Format und Bausteine (`policy_problems`), dazu das Blatt jeder Vorgabe gegen das neueste Setup jedes Stores
    (`sheet_check`). Gilt für jeden Weg, auf dem Vorgaben hochgehen.
    """
    problems = policy_problems(folder)
    if problems:
        raise SystemExit("Die Vorgaben der Marke gelten so nicht, nichts kopiert:\n  "
                         + "\n  ".join(problems))
    problems, hints = sheet_check(folder, brand_dir, Path(workspace), current_setup)
    for hint in hints:
        print(f"Hinweis: {hint}", file=sys.stderr)
    if problems:
        raise SystemExit("Die Vorgaben der Marke wären im Cockpit nicht verständlich, nichts kopiert:\n  "
                         + "\n  ".join(problems))


def _check_readiness(workspace, config: dict) -> None:
    """Bricht vor dem Kopieren ab, wenn eine Maßnahme der Marke nicht umsetzbar ist.

    Belegt, vollständig, machbar (`audit.readiness`, seit 15.10.2026). Für
    die Liste eines Stores wie für die einer Marke; eine Liste, die älter als
    eine Woche ist, steht nur als Hinweis da. Was die Marke im Cockpit später
    als in Arbeit, umgesetzt, verworfen oder überholt gemeldet hat, hält nicht
    an, und ein Punkt aus ihrer eigenen Anforderung braucht keinen Befund (seit
    16.10.2026); ist das Cockpit dafür nicht erreichbar, bricht es ab.
    """
    from audit import portal, readiness
    try:
        found = readiness.check_workspace(workspace, config)
    except portal.PortalError as exc:
        raise SystemExit(f"Gemeldete Stände aus dem Cockpit nicht lesbar, nichts kopiert: {exc}") from exc
    except ValueError as exc:
        raise SystemExit(f"Anforderungen der Marke nicht lesbar, nichts kopiert: {exc}") from exc
    reasons, hints = readiness.lines(found)
    for hint in hints:
        print(f"Hinweis: {hint}", file=sys.stderr)
    if reasons:
        raise SystemExit("Maßnahmen der Marke sind noch nicht umsetzbar, nichts kopiert. "
                         "Einzeln prüfen mit python3 -m audit.readiness check:\n  "
                         + "\n  ".join(reasons))


def _load_manifest(target: Path, brand: str, config: dict) -> tuple[Path, dict, int | None]:
    """Manifest aus dem Ziel, dazu sein Zähler vor dieser Änderung.

    `None` als Zähler heißt: es gab noch kein Manifest. Ein Manifest aus der
    Zeit vor dem Zähler zählt als 0.
    """
    manifest_path = target / manifest_key(brand)
    if manifest_path.exists():
        data = manifest.load(manifest_path)
        return manifest_path, data, int(data.get("revision") or 0)
    return manifest_path, manifest.empty(brand, config.get("brand") or brand), None


def _copy_brand_files(brand_reporting: Path, target: Path, brand: str) -> dict:
    """Legt die Dateien der Marke unter `brands/<slug>/` ab und gibt ihre Größen.

    Dazu die Vorgaben der Marke mit ihren Bausteinen, wenn es sie gibt
    (`policies.json`, `policy-modules/...`), unter demselben Namen wie im
    Ordner der Marke.
    """
    sources = {name: brand_reporting / name for name in BRAND_FILES}
    folder = brand_mod.policies_dir(brand_reporting.parent)
    if folder is not None:
        sources.update(brand_mod.policy_files(folder))
    return _copy_to_brand(sources, target, brand)


def _copy_to_brand(sources: dict, target: Path, brand: str) -> dict:
    """Kopiert je Name die Quelle nach `brands/<slug>/<name>` im Ziel und gibt die Größen; fehlende bleiben weg."""
    files = {}
    for name, source in sources.items():
        if source.exists():
            dest = target / "brands" / brand / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, dest)
            files[name] = source.stat().st_size
    return files


def is_policy_file(name: str) -> bool:
    """Gehört der Name unter `files` im Manifest zu den Vorgaben der Marke (`policies.json`, `policy-modules/…`)?"""
    return name == brand_mod.POLICIES_NAME or name.startswith(f"{brand_mod.POLICY_MODULES_DIR}/")


def prepare(workspace, run_id: str, target, today: date | None = None,
            note: str | None = None, replace: bool = False,
            visible: bool = False, account_slug: str | None = None) -> dict:
    """Kopiert den Lauf ans Ziel und traegt ihn ins Manifest.

    `target` ist die Wurzel des Buckets, lokal oder gemountet. Der Upload in
    einen echten Bucket ersetzt spaeter genau diese Kopie; die Struktur
    darunter bleibt dieselbe, damit der Wechsel keine Migration ist.

    **Eine neue Fassung eines veroeffentlichten Laufs braucht `visible`.**
    `add_run` uebernimmt die Freigabe, die neue Fassung waere also sofort beim
    Kunden. Ohne `visible` bricht `prepare` deshalb vor dem Kopieren ab
    (Spec `ptai-portal` 2026-10-02, Abschnitt 17, Punkt 2). `account_slug`
    schickt den Lauf an eine andere Marke, etwa die Testmarke `portal-test`,
    damit wir ihn dort ansehen, bevor der Kunde ihn sieht.

    Mit Dateien der Marke (`brand_workspace`) gehen diese nach `brands/<slug>/`
    statt je Store, die Kopie im Lauf ist die Liste der Marke, und die Vorschau
    braucht `portal-test-<marke>`.

    Ein Lauf der Art `migration` oder `setup` lädt nur `migration.json` bzw.
    `setup.json` hoch, immer in dieselbe Fassung (`replace`), und ist danach
    sichtbar. Fehlt die Datei, bricht `prepare` ab, bevor etwas kopiert ist.
    """
    workspace, target = Path(workspace), Path(target)
    config = load_config(workspace)
    brand_reporting = brand_mod.brand_reporting_dir(workspace, config)
    check_preview_target(config, account_slug, brand_reporting is not None)
    brand, shop = destination(config, account_slug)

    run_dir = workspace / "reporting" / "runs" / run_id
    if not run_dir.is_dir():
        raise SystemExit(f"Kein Lauf {run_id} unter {run_dir}")
    state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    kind, cadence = run_kind(run_id, state)

    single = SINGLE_FILE_KINDS.get(kind)
    if single:
        if not (run_dir / single).is_file():
            raise SystemExit(f"Lauf {run_id} ist ein Lauf der Art {kind}, aber {single} fehlt "
                             f"unter {run_dir}. Nichts kopiert.")
        files = {single: (run_dir / single).stat().st_size}
        # Eine lebende Fassung: jede neue ersetzt die alte, statt v02, v03 zu öffnen.
        replace = True
        if kind == "setup":
            # Ein Setup entsteht auch von Hand; das Format gilt trotzdem, bevor es sofort sichtbar ist.
            from theme import setup as setup_mod
            try:
                problems = setup_mod.validate(json.loads((run_dir / single).read_text(encoding="utf-8")))
            except ValueError as exc:
                problems = [f"{single} ist kein JSON ({exc})"]
            if problems:
                raise SystemExit(f"{single} in {run_id} gilt so nicht, nichts kopiert:\n  "
                                 + "\n  ".join(problems))
    else:
        files = manifest.collect_files(run_dir)
    if not files:
        raise SystemExit(f"Lauf {run_id} hat keine Dateien zum Hochladen")
    problems = proof_problems(run_dir, files)
    if problems:
        raise SystemExit("Belegbilder unvollständig, nichts kopiert:\n  " + "\n  ".join(problems))

    # Lesen, Prüfen, Kopieren und das Manifest schreiben am Stück unter der
    # Sperre: ein Lauf eines anderen Stores schreibt sonst dazwischen die
    # Liste der Marke, und die Kopie im Lauf zeigte einen halben Stand (D4).
    with brand_mod.lock(workspace):
        if brand_reporting is not None:
            _check_brand_files(workspace, config, brand_reporting,
                               run_dir / "setup.json" if kind == "setup" else None)
        # Wochenpuls, Migration und Setup ändern keine Maßnahme.
        if kind not in AUTO_RELEASED:
            _check_readiness(workspace, config)
        backlog_dir = measures.file_path(workspace).parent

        # **Das Manifest wird vor dem Kopieren gelesen**, weil der Zielpfad an
        # der Fassungsnummer haengt und die nur das Manifest kennt.
        manifest_path, manifest_data, base_revision = _load_manifest(target, brand, config)
        existing = next((r for r in manifest_data.get("runs") or []
                         if r["shop"] == shop and r["run_id"] == run_id), None)
        # Wochenpuls, Migration und Setup sind immer sichtbar; eine neue
        # Version braucht deshalb kein --visible.
        if existing and existing.get("released") and not visible and kind not in AUTO_RELEASED:
            raise SystemExit(
                f"Lauf {run_id} ist für den Kunden sichtbar, eine neue Fassung wäre es "
                "sofort auch. Mit --visible hochladen, wenn sie das sein soll, oder "
                "vorher mit --account-slug an eine Testmarke. Nichts kopiert.")
        revision = manifest.next_revision(manifest_data, shop, run_id, replace=replace)

        run_target = target / manifest.path_for(brand, shop, run_id, revision)
        if run_target.exists():
            shutil.rmtree(run_target)
        for rel in files:
            source, dest = run_dir / rel, run_target / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, dest)

        # Liegt im Lauf schon eine eigene Fassung, gilt seine: der Schnappschuss
        # ergaenzt, er ueberschreibt nie. Bei einer Marke ist es die Liste der
        # Marke zur Zeit dieses Laufs (Spec 5.4, D12).
        # Wochenpuls, Migration und Setup bekommen keinen Schnappschuss der
        # Maßnahmen: sie sind keine Prüfung, und ein Lauf mit `measures.json`
        # gilt im Cockpit als letzte Prüfung.
        for name in (() if kind in AUTO_RELEASED else SNAPSHOT_FILES):
            snapshot_source = backlog_dir / name
            if name not in files and snapshot_source.exists():
                shutil.copy2(snapshot_source, run_target / name)
                files[name] = snapshot_source.stat().st_size

        # Der Backlog und die Baseline gehoeren dem Shop, nicht dem Lauf. Sie
        # wandern bei jedem publish mit, weil sie sich zwischen den Laeufen
        # bewegen: eine Massnahme wechselt ihren Status, ein Baseline-Block wird
        # nachgetragen. Bei einer Marke gehen Maßnahmen und Anforderungen an
        # die Wurzel der Marke, je Store bleibt nur die Baseline.
        shop_target = target / manifest.path_for(brand, shop)
        shop_files = {}
        brand_files = None
        if brand_reporting is not None:
            brand_files = _copy_brand_files(brand_reporting, target, brand)
        else:
            for name in SHOP_FILES:
                source = workspace / "reporting" / name
                if source.exists():
                    dest = shop_target / name
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, dest)
                    shop_files[name] = source.stat().st_size
        for name in SHOP_DIRS:
            source = workspace / "reporting" / name
            if not source.is_dir():
                continue
            for path in sorted(source.rglob("*")):
                if not path.is_file():
                    continue
                rel = path.relative_to(workspace / "reporting").as_posix()
                dest = shop_target / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, dest)
                shop_files[rel] = path.stat().st_size

        # Der Shop bekommt seinen Anzeigenamen, damit die App ihn nennen kann,
        # ohne den Slug zu verschoenern.
        manifest_data.setdefault("shops", {})[shop] = {
            "name": config.get("brand") or shop,
            "domain": config.get("domain"),
            "path": manifest.path_for(brand, shop),
            "files": shop_files,
        }
        if brand_files is not None:
            manifest_data["files"] = brand_files
        manifest_data = manifest.add_run(manifest_data, shop=shop, run_id=run_id,
                                         kind=kind, cadence=cadence,
                                         period=state.get("period"),
                                         run_date=run_id[:10], files=files,
                                         revision=revision, note=note,
                                         title=state.get("title"), today=today)
        # Wochenpuls, Migration und Setup sind die benannte Ausnahme von
        # "hochgeladen ist nicht sichtbar": sie enthalten keine Befunde und
        # keine Maßnahmen. Der Puls trägt im Cockpit "automatisch erstellt".
        if kind in AUTO_RELEASED:
            manifest_data = manifest.release(manifest_data, shop, run_id, today=today)
        manifest_data["revision"] = (base_revision or 0) + 1
        manifest.save(manifest_path, manifest_data)
    # Eine Freigabe bleibt über neue Fassungen erhalten (`manifest.add_run`).
    # Gemeldet wird deshalb der Stand aus dem Manifest, nicht ein fester Wert.
    entry = next(r for r in manifest_data["runs"]
                 if r["shop"] == shop and r["run_id"] == run_id)
    return {"brand": brand, "shop": shop, "run_id": run_id,
            "files": len(files), "shop_files": len(shop_files),
            "brand_files": len(brand_files or {}),
            "revision": revision,
            "manifest_revision": manifest_data["revision"],
            "manifest_base_revision": base_revision,
            "path": str(run_target), "manifest": str(manifest_path),
            "released": entry["released"]}


def prepare_brand_only(workspace, target, account_slug: str | None = None) -> dict:
    """Nur die Dateien der Marke und das Manifest, kein Lauf.

    Für den Umzug einer Marke (Spec Abschnitt 12, A3): nach `brand_migrate`
    liegt die Liste bei der Marke, und das Cockpit soll sie lesen, ohne dass
    ein Lauf neu hochgeht. Ebenso für neue Vorgaben der Marke (Vertrag V15):
    `policies.json` und `policy-modules/` gehen mit, wenn es sie gibt.
    """
    workspace, target = Path(workspace), Path(target)
    config = load_config(workspace)
    brand_reporting = brand_mod.brand_reporting_dir(workspace, config)
    if brand_reporting is None:
        raise SystemExit("--brand-only braucht brand_workspace in reporting/config.json: "
                         "ohne Ordner der Marke gibt es keine Dateien der Marke.")
    check_preview_target(config, account_slug, True)
    brand, _shop = destination(config, account_slug)
    with brand_mod.lock(workspace):
        _check_brand_files(workspace, config, brand_reporting)
        _check_readiness(workspace, config)
        manifest_path, manifest_data, base_revision = _load_manifest(target, brand, config)
        brand_files = _copy_brand_files(brand_reporting, target, brand)
        manifest_data["files"] = brand_files
        manifest_data["revision"] = (base_revision or 0) + 1
        manifest.save(manifest_path, manifest_data)
    return {"brand": brand, "brand_files": len(brand_files),
            "manifest": str(manifest_path),
            "manifest_revision": manifest_data["revision"],
            "manifest_base_revision": base_revision}


def prepare_policies_only(workspace, target, account_slug: str | None = None) -> dict:
    """Nur die Vorgaben der Marke mit ihren Bausteinen und das Manifest, ohne Maßnahmen und Anforderungen.

    Seit 16.10.2026. `--brand-only` lädt Vorgaben, Maßnahmen und Anforderungen zusammen und hält an, solange
    eine Maßnahme der Marke nicht umsetzbar ist (`audit.readiness`). Eine neue Fassung der Vorgaben wartete
    damit auf die Maßnahmen, obwohl sie keine ändert, und die Stores bauten ihre Migration so lange nach der
    alten. Geprüft werden deshalb nur die Vorgaben, wie bei jedem anderen Weg (`_check_policies`).

    Im Manifest ersetzt die Fassung jeden Eintrag der Vorgaben unter `files`, auch Bausteine, die es nicht
    mehr gibt; Maßnahmen, Anforderungen und Läufe bleiben, wie sie im Manifest stehen. Ins Ziel kommen nur
    das Manifest und die Dateien der Vorgaben, und `upload` lädt nur, was im Ziel liegt: `measures.json`
    und `feedback.json` im Bucket bleiben unberührt.
    """
    workspace, target = Path(workspace), Path(target)
    config = load_config(workspace)
    brand_reporting = brand_mod.brand_reporting_dir(workspace, config)
    if brand_reporting is None:
        raise SystemExit("--policies-only braucht brand_workspace in reporting/config.json: "
                         "ohne Ordner der Marke gibt es keine Vorgaben der Marke.")
    check_preview_target(config, account_slug, True)
    brand, _shop = destination(config, account_slug)
    with brand_mod.lock(workspace):
        folder = brand_mod.policies_dir(brand_reporting.parent)
        if folder is None:
            raise SystemExit(f"Im Ordner der Marke {brand_reporting.parent} liegt keine "
                             f"{brand_mod.POLICIES_NAME}. Nichts kopiert.")
        _check_policies(folder, brand_reporting.parent, workspace)
        manifest_path, manifest_data, base_revision = _load_manifest(target, brand, config)
        policy_files = _copy_to_brand(brand_mod.policy_files(folder), target, brand)
        kept = {name: size for name, size in (manifest_data.get("files") or {}).items()
                if not is_policy_file(name)}
        manifest_data["files"] = {**kept, **policy_files}
        manifest_data["revision"] = (base_revision or 0) + 1
        manifest.save(manifest_path, manifest_data)
    return {"brand": brand, "policy_files": len(policy_files),
            "kept_files": len(kept),
            "manifest": str(manifest_path),
            "manifest_revision": manifest_data["revision"],
            "manifest_base_revision": base_revision}


#: Wie eine Datei im Bucket ausgeliefert wird. Ohne den richtigen Typ laedt der
#: Browser die Web-Fassung herunter, statt sie anzuzeigen.
CONTENT_TYPES = {".html": "text/html", ".pdf": "application/pdf",
                 ".json": "application/json", ".md": "text/markdown",
                 ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                 ".webp": "image/webp", ".csv": "text/csv", ".txt": "text/plain"}


def upload(local_root, url: str, service_key: str, bucket: str = "runs") -> dict:
    """Laedt einen vorbereiteten Baum in den Bucket.

    Getrennt von `prepare()`, weil beides getrennt scheitern darf: eine
    fehlgeschlagene Uebertragung soll den vorbereiteten Ordner nicht wegwerfen,
    und ein zweiter Anlauf soll ihn nicht neu bauen muessen.

    `x-upsert` ueberschreibt bestehende Objekte. Das ist gewollt: dieselbe
    Lauf-ID zweimal zu veroeffentlichen ist eine Korrektur.
    """
    import urllib.error
    import urllib.request

    local_root = Path(local_root)
    uploaded, errors = 0, []
    for path in sorted(local_root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(local_root).as_posix()
        request = urllib.request.Request(
            f"{url.rstrip('/')}/storage/v1/object/{bucket}/{rel}",
            data=path.read_bytes(), method="POST",
            headers={"Authorization": f"Bearer {service_key}",
                     "apikey": service_key,
                     "x-upsert": "true",
                     "Content-Type": CONTENT_TYPES.get(
                         path.suffix.lower(), "application/octet-stream")})
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                if response.status == 200:
                    uploaded += 1
                else:
                    errors.append(f"{rel}: HTTP {response.status}")
        except urllib.error.HTTPError as exc:
            errors.append(f"{rel}: HTTP {exc.code}")
        except OSError as exc:
            errors.append(f"{rel}: {exc}")
    return {"uploaded": uploaded, "errors": errors}


def _download_manifest(brand: str, url: str, service_key: str,
                       bucket: str = "runs") -> bytes | None:
    """Das Manifest aus dem Bucket, `None`, wenn die Brand dort keines hat.

    Jeder andere Fehler bricht ab: ein Manifest, das sich nicht lesen ließ, ist
    kein leeres.
    """
    import urllib.error
    import urllib.request

    object_key = manifest_key(brand)
    request = urllib.request.Request(
        f"{url.rstrip('/')}/storage/v1/object/{bucket}/{object_key}",
        headers={"Authorization": f"Bearer {service_key}",
                 "apikey": service_key})
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        # Supabase Storage antwortet bei einem fehlenden Objekt nicht mit dem
        # äußeren HTTP-Status 404, sondern mit HTTP 400 und `NoSuchKey` im
        # JSON-Body. Nur dieser benannte 400-Fall bedeutet "neue Brand"; ein
        # anderer 400er bleibt ein Abbruch, damit kein bestehendes Manifest
        # versehentlich durch ein leeres ersetzt wird.
        error_body = exc.read()
        exc.close()
        missing = (exc.code == 404 or
                   (exc.code == 400 and b'"code":"NoSuchKey"' in error_body))
        if missing:
            return None
        raise SystemExit(f"Manifest {object_key} nicht aus dem Bucket lesbar: "
                         f"HTTP {exc.code}. Abgebrochen, nichts hochgeladen.")
    except OSError as exc:
        raise SystemExit(f"Manifest {object_key} nicht aus dem Bucket lesbar: "
                         f"{exc}. Abgebrochen, nichts hochgeladen.")


def fetch_manifest(target, brand: str, url: str, service_key: str,
                   bucket: str = "runs") -> str:
    """Holt das Manifest aus dem Bucket ins Ziel, bevor `prepare()` darauf aufbaut.

    Liegt im Ziel keines, baut `prepare()` auf einem leeren auf, und `upload()`
    ersetzt damit das Manifest im Bucket: jeder andere Lauf verschwindet aus dem
    Portal, und ein schon freigegebener Lauf verliert seine Freigabe, weil
    `add_run` keinen Eintrag findet, dessen Status es behalten könnte.

    Rückgabe ist die Herkunft: `local` (lag schon im Ziel und bleibt
    unangetastet), `remote` (aus dem Bucket geholt) oder `new` (HTTP 404, die
    Brand ist neu). Jeder andere Fehler bricht ab, bevor etwas hochgeht: ein
    Manifest, das sich nicht lesen ließ, ist kein leeres.
    """
    path = Path(target) / manifest_key(brand)
    if path.exists():
        return "local"
    body = _download_manifest(brand, url, service_key, bucket)
    if body is None:
        return "new"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return "remote"


def check_manifest_unchanged(brand: str, base_revision: int | None, url: str,
                             service_key: str, bucket: str = "runs") -> None:
    """Bricht ab, wenn sich das Manifest im Bucket seit dem Lesen geändert hat (D12).

    `base_revision` ist der Zähler des Manifests, auf dem `prepare()` aufgebaut
    hat, `None` für eine Brand ohne Manifest. Steht im Bucket inzwischen ein
    anderer Zähler, hat ein zweites `publish` dazwischen geschrieben; dessen
    Lauf verschwände mit dem Hochladen aus dem Verzeichnis.
    """
    body = _download_manifest(brand, url, service_key, bucket)
    remote = None
    if body is not None:
        try:
            remote = int(json.loads(body.decode("utf-8")).get("revision") or 0)
        except (ValueError, AttributeError) as exc:
            raise SystemExit(f"Manifest {manifest_key(brand)} im Bucket ist kein "
                             f"lesbares JSON ({exc}). Abgebrochen, nichts hochgeladen.")
    if remote != base_revision:
        seen = "keins" if base_revision is None else f"Zähler {base_revision}"
        now = "keins" if remote is None else f"Zähler {remote}"
        raise SystemExit(
            f"Das Manifest von {brand} hat sich im Bucket geändert (gelesen: {seen}, "
            f"jetzt: {now}). Ein anderes publish hat dazwischen geschrieben. "
            "Abgebrochen, nichts hochgeladen. Mit einem leeren --target neu starten.")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--workspace", default=".")
    p.add_argument("--run-id",
                   help="der Lauf; entfällt nur mit --brand-only")
    p.add_argument("--target", required=True,
                   help="Ordner, in dem der Lauf fuer den Upload vorbereitet wird")
    p.add_argument("--note",
                   help="ein Satz, was an dieser Fassung korrigiert wurde; er "
                        "steht im Verlauf beim Kunden")
    p.add_argument("--replace", action="store_true",
                   help="in die laufende Fassung schreiben statt eine neue zu "
                        "oeffnen; fuer die Korrektur, die noch niemand gesehen "
                        "hat. Sie erscheint nicht im Verlauf")
    p.add_argument("--visible", action="store_true",
                   help="eine neue Fassung eines schon veroeffentlichten Laufs "
                        "hochladen; sie ist danach sofort beim Kunden sichtbar")
    p.add_argument("--account-slug",
                   help="an diese Marke statt an die aus reporting/config.json, "
                        "etwa portal-test fuer eine Vorschau; mit Dateien der "
                        "Marke nur portal-test-<marke>")
    p.add_argument("--brand-only", action="store_true",
                   help="nur die Dateien der Marke (Maßnahmen, Anforderungen, "
                        "Vorgaben mit Bausteinen) und das Manifest, kein Lauf; "
                        "für den Umzug einer Marke und neue Vorgaben")
    p.add_argument("--policies-only", action="store_true",
                   help="nur die Vorgaben der Marke mit ihren Bausteinen und das "
                        "Manifest, keine Maßnahmen, keine Anforderungen, kein Lauf; "
                        "für eine neue Fassung der Vorgaben")
    p.add_argument("--upload", action="store_true",
                   help="danach in den Bucket laden, braucht SUPABASE_URL und "
                        "SUPABASE_SERVICE_ROLE_KEY in der Umgebung; liegt im "
                        "Ziel kein Manifest, kommt es vorher aus dem Bucket")
    a = p.parse_args(argv)
    if a.brand_only and a.policies_only:
        p.error("--brand-only und --policies-only schließen sich aus")
    if not (a.brand_only or a.policies_only) and not a.run_id:
        p.error("--run-id fehlt (nur mit --brand-only oder --policies-only verzichtbar)")
    if a.brand_only and a.run_id:
        p.error("--brand-only lädt keinen Lauf, --run-id weglassen")
    if a.policies_only and a.run_id:
        p.error("--policies-only lädt keinen Lauf, --run-id weglassen")

    url = key = None
    if a.upload:
        import os
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        # Ohne Schlüssel wird auch nichts vorbereitet. Ein Ziel, dessen
        # Manifest auf einem leeren aufbaut, lüde der nächste Anlauf mit
        # Schlüssel sonst genau so hoch.
        if not (url and key):
            print("SUPABASE_URL oder SUPABASE_SERVICE_ROLE_KEY fehlen in der "
                  "Umgebung. Nichts vorbereitet, nichts hochgeladen.",
                  file=sys.stderr)
            return 1

    # Holen, Vorbereiten, Prüfen und Hochladen unter einer Sperre: zwei
    # publish desselben Rechners laufen nacheinander, und gegen eines von
    # einem anderen Rechner hilft der Zähler im Manifest (D12).
    with brand_mod.lock(a.workspace):
        config = load_config(a.workspace)
        check_preview_target(config, a.account_slug,
                             brand_mod.has_brand_files(a.workspace, config))
        brand = destination(config, a.account_slug)[0]
        if a.upload:
            origin = fetch_manifest(a.target, brand, url, key)
            print({"local": "Manifest lag schon im Ziel und bleibt, wie es ist",
                   "remote": "Manifest aus dem Bucket übernommen",
                   "new": "Brand ist neu im Bucket, das Manifest beginnt leer"}[origin])

        if a.brand_only:
            result = prepare_brand_only(a.workspace, a.target,
                                        account_slug=a.account_slug)
            print(f"{result['brand_files']} Dateien der Marke nach "
                  f"{Path(a.target) / 'brands' / result['brand']}")
        elif a.policies_only:
            result = prepare_policies_only(a.workspace, a.target,
                                           account_slug=a.account_slug)
            print(f"{result['policy_files']} Dateien der Vorgaben nach "
                  f"{Path(a.target) / 'brands' / result['brand']}; "
                  f"{result['kept_files']} übrige Dateien der Marke bleiben im Bucket, wie sie sind")
        else:
            result = prepare(a.workspace, a.run_id, a.target,
                             note=a.note, replace=a.replace,
                             visible=a.visible, account_slug=a.account_slug)
            print(f"{result['files']} Dateien nach {result['path']}")
            if result["revision"] > 1:
                print(f"Fassung {result['revision']:02d}"
                      + (f": {a.note}" if a.note else ": Korrektur ohne Notiz"))
            if a.replace:
                print("--replace: in die laufende Fassung geschrieben, kein Eintrag "
                      "im Verlauf.")
            if result["brand_files"]:
                print(f"{result['brand_files']} Dateien der Marke (Maßnahmen, "
                      "Anforderungen und Vorgaben, sie gelten für alle Stores)")
            print(f"{result['shop_files']} Dateien auf Shop-Ebene "
                  "(Baseline, bei einem Store ohne Marke auch die Massnahmen)")
        print(f"Manifest: {result['manifest']} (Zähler {result['manifest_revision']})")
        if a.upload:
            check_manifest_unchanged(brand, result["manifest_base_revision"], url, key)
            upload_result = upload(a.target, url, key)
            print(f"{upload_result['uploaded']} Objekte im Bucket")
            for line in upload_result["errors"][:10]:
                print(f"  FEHLER {line}", file=sys.stderr)
            if upload_result["errors"]:
                return 1

    if a.brand_only or a.policies_only:
        return 0
    if result["released"]:
        print("Freigabe: ja, übernommen. Der Kunde sieht diese Fassung.")
    else:
        print("Freigabe: nein. Der Lauf ist für den Kunden unsichtbar, bis "
              "release ihn freigibt.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
