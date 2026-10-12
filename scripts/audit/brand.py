#!/usr/bin/env python3
"""Wo die Dateien einer Marke liegen, und wer sie gerade schreibt.

Spec `ptai-portal` 2026-10-08 "eine Marke, mehrere Stores",
Abschnitt 5.1 und 11. Eine Marke kann mehrere Stores führen. Läufe, Baseline
und `context.json` bleiben je Store, die Maßnahmen und die Anforderungen von
außen gibt es einmal je Marke:

    <marke>/
      reporting/          Ordner der Marke
        measures.json     eine Liste für alle Stores, Format v2
        feedback.json
      <store>/reporting/  Store-Workspace mit config.json, runs/, baseline/

**Der Pfad zur Marke steht absolut in der Config des Stores** (`brand_workspace`,
D11). Ein relativer Standard wie `..` zeigte aus einem Git-Worktree an die
falsche Stelle, und die Sitzung dort legte still eine zweite Liste an. Fehlt
die Datei der Marke dort, bricht der Lauf ab, statt eine leere anzulegen.

**Der Pfad darf je Rechner anders sein (seit 11.10.2026).** Die Repos der
Stores einer Marke teilt das Team des Kunden auf Windows-Rechnern; ein
absoluter Pfad in der getrackten `reporting/config.json` stimmt dort nie. Vor
`config.json` gelten deshalb, in dieser Reihenfolge:

1. Umgebungsvariable `PTAI_BRAND_WORKSPACE`, für einen einzelnen Aufruf oder
   eine Sitzung (etwa in einem Git-Worktree, in dem die lokale Datei fehlt)
2. `reporting/config.local.json` mit `brand_workspace`, nie committet:
   `set_local()` schreibt sie und trägt sie in `.git/info/exclude` ein, das
   je Klon gilt und kein getracktes File ändert
3. `brand_workspace` in `reporting/config.json`

Für alle drei gilt D11: absolut, und die Datei der Marke muss dort liegen und
dieselbe Marke nennen wie der Store (`portal.brand`, sonst `account_slug`).
Eine Umgebungsvariable gilt für jeden Workspace der Sitzung; ohne den
Abgleich der Marke schriebe ein Lauf der einen Marke still in die Liste
einer anderen.

**Kein zweiter Zähler (D9).** Hat eine Marke ihre Datei, legt kein Store
dieser Marke mehr eine eigene `measures.json` an. Ein Store-Workspace ohne
`brand_workspace`, über dem eine Datei der Marke liegt, bricht ab und sagt,
was in die Config gehört.

**Eine Sperre für jedes Lesen, Ändern und Schreiben (D4).** Zwei Läufe zweier
Stores schreiben dieselbe Datei. Ohne Sperre gewinnt der zweite und die
Maßnahmen des ersten sind weg. `lock()` hält eine `flock`-Sperre auf einer
Datei im Ordner der Marke; ein zweiter Schreiber wartet eine begrenzte Zeit
und bricht dann mit klarer Meldung ab.
"""
from __future__ import annotations

import contextlib
import errno
import fcntl
import json
import os
import re
import subprocess
import time
from pathlib import Path

#: Die Dateien, die einmal je Marke liegen, sobald es den Ordner der Marke gibt.
BRAND_FILES = ("measures.json", "measures.md", "feedback.json")

#: Die Datei, deren Dasein den Ordner der Marke ausweist. Fehlt sie dort, ist
#: der Pfad falsch oder der Umzug nicht gelaufen, und es wird nichts angelegt.
ANCHOR = "measures.json"

#: Name der Sperrdatei im Ordner der Marke (oder des Stores, solange es keine
#: Marke gibt). Sie bleibt liegen, ihr Inhalt ist leer; gesperrt wird über
#: `flock`, nicht über ihr Dasein. Eine liegengebliebene Datei sperrt also nie.
LOCK_NAME = ".measures.lock"

#: Wie lange ein zweiter Schreiber wartet, bevor er abbricht. Ein Schreibvorgang
#: dauert Millisekunden; wer länger wartet, wartet auf einen hängenden Lauf.
LOCK_TIMEOUT_SECONDS = 30.0

#: Die Datei je Rechner neben `config.json`, nie committet.
LOCAL_CONFIG_NAME = "config.local.json"

#: Umgebungsvariable mit dem Ordner der Marke, schlägt jede Datei.
ENV_BRAND_WORKSPACE = "PTAI_BRAND_WORKSPACE"

#: Was `config.local.json` übersteuern darf. Bewusst nur der Pfad: alles andere
#: in der Config gilt für jeden Rechner gleich, und eine zweite Quelle für
#: Domain oder Properties wäre eine zweite Wahrheit.
LOCAL_KEYS = ("brand_workspace",)

#: Aus "Beispielshop" wird "beispielshop", aus "Nord & Stein" wird "nord-stein".
_NON_SLUG_CHARS = re.compile(r"[^a-z0-9]+")


class BrandFileError(SystemExit):
    """Abbruch mit Ansage: falscher Pfad, fehlende Datei, belegte Sperre.

    Eine Unterklasse von `SystemExit`, damit ein CLI-Aufruf mit der Meldung
    endet statt mit einem Stacktrace, und ein Test sie gezielt fangen kann.
    """


def slugify(name: str) -> str:
    """Ein Shop-Name als Pfadsegment."""
    umlauts = {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss",
               "Ä": "ae", "Ö": "oe", "Ü": "ue"}
    for umlaut, replacement in umlauts.items():
        name = name.replace(umlaut, replacement)
    return _NON_SLUG_CHARS.sub("-", name.lower()).strip("-")


def read_config(workspace) -> dict:
    """Die Reporting-Config eines Store-Workspace, leer, wenn es keine gibt.

    Leer statt Fehler, weil auch Werkzeuge ohne Config (Tests, ein frischer
    Workspace) Maßnahmen lesen. Wer eine Config braucht, prüft selbst.
    """
    path = Path(workspace) / "reporting" / "config.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    return data if isinstance(data, dict) else {}


def brand_slug(config: dict) -> str | None:
    """Die Marke im Cockpit: `portal.brand`, sonst `account_slug`."""
    portal = config.get("portal") or {}
    return portal.get("brand") or config.get("account_slug") or None


def shop_slug(config: dict) -> str | None:
    """Der Store im Cockpit: `portal.shop`, sonst aus dem Namen gebildet.

    Dieselbe Regel wie `publish.destination()`, damit der Store in
    `measures.json` und im Bucket gleich heißt.
    """
    portal = config.get("portal") or {}
    if portal.get("shop"):
        return portal["shop"]
    name = config.get("brand") or brand_slug(config)
    return slugify(name) if name else None


def read_local_config(workspace) -> dict:
    """`reporting/config.local.json`, leer, wenn es sie nicht gibt.

    Nur die Schlüssel aus `LOCAL_KEYS` zählen; ein anderer bricht ab, damit
    niemand glaubt, er habe dort etwas übersteuert, das nie gelesen wird.
    """
    path = Path(workspace) / "reporting" / LOCAL_CONFIG_NAME
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except ValueError as exc:
        raise BrandFileError(f"{path} ist kein gültiges JSON: {exc}") from None
    if not isinstance(data, dict):
        raise BrandFileError(f"{path} muss ein Objekt sein")
    unknown = sorted(set(data) - set(LOCAL_KEYS))
    if unknown:
        raise BrandFileError(
            f"{path} übersteuert nur {', '.join(LOCAL_KEYS)}, nicht "
            f"{', '.join(unknown)}. Alles andere gehört in config.json.")
    return data


def brand_workspace_setting(workspace, config: dict | None = None) -> tuple[object, str]:
    """Der eingetragene Ordner der Marke und woher er kommt.

    Reihenfolge: `PTAI_BRAND_WORKSPACE`, `reporting/config.local.json`,
    `reporting/config.json`. Gibt `(None, "")` zurück, wenn nirgends einer steht.
    """
    from_env = os.environ.get(ENV_BRAND_WORKSPACE)
    if from_env:
        return from_env, f"Umgebungsvariable {ENV_BRAND_WORKSPACE}"
    local = read_local_config(workspace).get("brand_workspace")
    if local not in (None, ""):
        return local, str(Path(workspace) / "reporting" / LOCAL_CONFIG_NAME)
    config = read_config(workspace) if config is None else config
    raw = config.get("brand_workspace")
    if raw in (None, ""):
        return None, ""
    return raw, str(Path(workspace) / "reporting" / "config.json")


def configured_brand_dir(workspace, config: dict | None = None) -> Path | None:
    """Der Ordner der Marke laut Einstellung, oder `None`, wenn keiner eingetragen ist.

    Verlangt einen absoluten Pfad (eine Tilde wird aufgelöst). Ein relativer
    Pfad hinge davon ab, von wo aus der Lauf startet, und genau das soll das
    Feld ausschließen. Woher der Pfad kommt, steht in
    `brand_workspace_setting()`.
    """
    raw, origin = brand_workspace_setting(workspace, config)
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise BrandFileError(f"brand_workspace in {origin} ist kein Pfad: {raw!r}")
    path = Path(raw).expanduser()
    if not path.is_absolute():
        raise BrandFileError(
            f"brand_workspace muss ein absoluter Pfad sein, ist {raw!r} "
            f"({origin}). Ein relativer Pfad zeigt aus einem Git-Worktree an "
            "eine andere Stelle, und dort entstünde eine zweite Liste.")
    return path


def brand_reporting_dir(workspace, config: dict | None = None) -> Path | None:
    """`<brand_workspace>/reporting`, geprüft: die Datei der Marke muss dort liegen.

    Fehlt sie, bricht das ab. Eine leere Datei an dieser Stelle wäre eine
    zweite Liste mit eigener Zählung ab M-001, und genau die soll es nie geben.
    Nennt sie eine andere Marke als dieser Store, bricht das ebenfalls ab: der
    Pfad kann aus einer Umgebungsvariable kommen, die für jeden Workspace der
    Sitzung gilt.
    """
    config = read_config(workspace) if config is None else config
    base = configured_brand_dir(workspace, config)
    if base is None:
        return None
    _raw, origin = brand_workspace_setting(workspace, config)
    return _checked_reporting(base, config, origin)


def _checked_reporting(base: Path, config: dict, origin: str) -> Path:
    """Die Prüfungen aus `brand_reporting_dir()` für einen gegebenen Ordner."""
    reporting = base / "reporting"
    anchor = reporting / ANCHOR
    if not anchor.is_file():
        raise BrandFileError(
            f"Die Datei der Marke fehlt: {anchor}. brand_workspace aus "
            f"{origin} zeigt dorthin. "
            "Pfad prüfen oder den Umzug laufen lassen (python3 -m "
            "audit.brand_migrate). Es wird keine leere Liste angelegt.")
    own = brand_slug(config)
    try:
        doc = json.loads(anchor.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        doc = None
    listed = doc.get("brand") if isinstance(doc, dict) and doc.get("version") == 2 else None
    if own and listed and listed != own:
        raise BrandFileError(
            f"{anchor} ist die Liste der Marke {listed!r}, dieser Store gehört "
            f"im Cockpit zu {own!r} (portal.brand, sonst account_slug). "
            f"brand_workspace aus {origin} zeigt auf die falsche Marke. "
            "Nichts gelesen, nichts geschrieben.")
    return reporting


def _brand_file_above(workspace, config: dict) -> Path | None:
    """Eine Datei der Marke in einem übergeordneten Ordner, falls es eine gibt.

    Sucht jede Ebene über dem Workspace ab, nicht nur die direkte: ein
    Git-Worktree liegt tiefer (`<store>/.claude/worktrees/<name>`), und auch
    von dort aus darf keine zweite Liste entstehen. Zählt nur, wenn die Datei
    im Format v2 vorliegt und dieselbe Marke nennt wie der Store im Cockpit:
    `portal.brand`, sonst `account_slug`. Stores, die früher eigene Marken
    waren, behalten ihren alten `account_slug`, veröffentlichen aber unter
    dem `portal.brand` der gemeinsamen Marke; maßgeblich ist die Marke im
    Cockpit.
    """
    own = brand_slug(config)
    if not own:
        return None
    for parent in Path(workspace).resolve().parents:
        candidate = parent / "reporting" / ANCHOR
        if not candidate.is_file():
            continue
        try:
            doc = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(doc, dict) and doc.get("version") == 2 and doc.get("brand") == own:
            return candidate
    return None


def guard_second_counter(workspace, config: dict | None = None) -> None:
    """Bricht ab, wenn dieser Store ohne `brand_workspace` neben einer Marke steht.

    D9: Sobald die Marke ihre Datei hat, führt kein Store mehr eine eigene.
    """
    config = read_config(workspace) if config is None else config
    if brand_workspace_setting(workspace, config)[0] is not None:
        return
    found = _brand_file_above(workspace, config)
    if found:
        raise BrandFileError(
            f"Die Marke {brand_slug(config)!r} führt ihre Maßnahmen in {found}. "
            "Dieser Store-Workspace hat kein brand_workspace und würde eine "
            "eigene Liste anlegen. Auf diesem Rechner eintragen: python3 -m "
            f"audit.brand set-local --workspace {Path(workspace)} "
            f"--brand-workspace {found.parent.parent} (oder für diese Sitzung "
            f"{ENV_BRAND_WORKSPACE}={found.parent.parent}).")


def reporting_dir(workspace, config: dict | None = None) -> Path:
    """Der Ordner, in dem `measures.json` und `feedback.json` dieses Workspace liegen.

    Mit `brand_workspace` der Ordner der Marke, sonst `reporting/` des Stores,
    nachdem `guard_second_counter()` ausgeschlossen hat, dass es eine Marke
    gibt, die diesen Store schon führt.
    """
    config = read_config(workspace) if config is None else config
    brand_dir = brand_reporting_dir(workspace, config)
    if brand_dir is not None:
        return brand_dir
    guard_second_counter(workspace, config)
    return Path(workspace) / "reporting"


def file_path(workspace, name: str, config: dict | None = None) -> Path:
    """Der volle Pfad einer Datei der Marke (`measures.json`, `feedback.json`, ...)."""
    if name not in BRAND_FILES:
        raise ValueError(f"{name!r} ist keine Datei der Marke, erlaubt: {BRAND_FILES}")
    return reporting_dir(workspace, config) / name


def has_brand_files(workspace, config: dict | None = None) -> bool:
    """Liegen die Maßnahmen dieses Store-Workspace im Ordner der Marke?"""
    return brand_reporting_dir(workspace, config) is not None


# ------------------------------------------------------------------- Sperre

#: Sperren, die dieser Prozess gerade hält: Pfad der Sperrdatei auf
#: (Dateideskriptor, Tiefe). Ein `flock` auf einen zweiten Deskriptor derselben
#: Datei im selben Prozess würde auf sich selbst warten; deshalb zählt ein
#: verschachteltes `lock()` nur hoch.
_HELD: dict[str, list] = {}


def lock_path(workspace, config: dict | None = None) -> Path:
    """Die Sperrdatei: im Ordner der Marke, sonst im `reporting/` des Stores."""
    return reporting_dir(workspace, config) / LOCK_NAME


@contextlib.contextmanager
def lock(workspace=None, *, path: Path | None = None,
         timeout: float | None = None, poll: float = 0.05):
    """Hält die Schreibsperre der Marke für die Dauer des `with`-Blocks.

    `timeout` in Sekunden, Vorgabe `LOCK_TIMEOUT_SECONDS`. Ist die Sperre dann
    noch belegt, bricht das mit `BrandFileError` ab. Verschachtelt im selben
    Prozess ist sie frei (`save()` innerhalb von `edit()`).
    """
    target = Path(path) if path is not None else lock_path(workspace)
    target.parent.mkdir(parents=True, exist_ok=True)
    key = _key(target)
    held = _HELD.get(key)
    if held is not None:
        held[1] += 1
        try:
            yield target
        finally:
            held[1] -= 1
        return

    fd = os.open(target, os.O_RDWR | os.O_CREAT, 0o644)
    limit = LOCK_TIMEOUT_SECONDS if timeout is None else timeout
    deadline = time.monotonic() + limit
    try:
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as exc:
                if exc.errno not in (errno.EAGAIN, errno.EACCES, errno.EWOULDBLOCK):
                    raise
                if time.monotonic() >= deadline:
                    raise BrandFileError(
                        f"{target.parent} ist seit {limit:g} Sekunden von einem "
                        "anderen Lauf gesperrt. Abgebrochen, nichts geschrieben. "
                        "Den anderen Lauf abwarten und dann erneut starten.") from None
                time.sleep(poll)
    except BaseException:
        os.close(fd)
        raise

    _HELD[key] = [fd, 1]
    try:
        yield target
    finally:
        del _HELD[key]
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def holds_lock(workspace=None, *, path: Path | None = None) -> bool:
    """Hält dieser Prozess die Sperre gerade? Für Prüfungen in `save()`."""
    target = Path(path) if path is not None else lock_path(workspace)
    return target.parent.is_dir() and _key(target) in _HELD


def _key(target: Path) -> str:
    """Ein Schlüssel je Sperrdatei, unabhängig davon, wie der Pfad geschrieben
    ist (`/tmp` und `/private/tmp` sind auf macOS derselbe Ordner)."""
    return str(target.parent.resolve() / target.name)


# ------------------------------------------------------------- Befunde je Lauf

def finding_ids(run_dir, include_revisions: bool = True) -> set[str]:
    """Alle Befund-Kennungen eines Lauf-Ordners.

    Je Befund zwei Schreibweisen: die Kennung, die der Agent vergeben hat, und
    die, unter der der Report ihn zeigt (`report_build.finding_id()`, das
    Kürzel der Disziplin plus Nummer). Eine Maßnahme kann auf beide zeigen.
    Mit `include_revisions` auch die Befunde früherer Fassungen dieses Laufs:
    eine durch einen Nachlauf geschlossene Maßnahme zeigt auf einen Befund,
    dessen Wortlaut nur noch in `revisions/` liegt.
    """
    from audit.report_build import finding_id  # spät, der Report zieht viel nach

    run_dir = Path(run_dir)
    folders = [run_dir / "findings"]
    if include_revisions:
        folders += sorted((run_dir / "revisions").glob("*/findings"))
    ids: set[str] = set()
    for folder in folders:
        for path in sorted(folder.glob("*.json")):
            if path.stem.startswith("_"):
                continue
            try:
                doc = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            items = doc.get("findings") if isinstance(doc, dict) else None
            for number, finding in enumerate(items or [], 1):
                if not isinstance(finding, dict):
                    continue
                raw = finding.get("id")
                if raw:
                    ids.add(str(raw))
                ids.add(finding_id(path.stem, raw, number))
    return ids


def store_runs_dir(brand_reporting: Path, shop: str, own_workspace=None,
                   own_shop: str | None = None) -> Path:
    """Der Ordner `runs/` eines Stores der Marke, so wie die Ablage ihn vorsieht.

    Für den eigenen Store der Workspace selbst, für jeden anderen
    `<marke>/<store>/reporting/runs` (Spec Abschnitt 3.1). Ob es ihn auf diesem
    Rechner gibt, prüft der Aufrufer.
    """
    if own_workspace is not None and shop == own_shop:
        return Path(own_workspace) / "reporting" / "runs"
    return Path(brand_reporting).parent / shop / "reporting" / "runs"


# ------------------------------------------------------- Pfad je Rechner

def _git(workspace, *args) -> str | None:
    """Ein git-Aufruf im Workspace; `None`, wenn es kein Repo ist oder git fehlt."""
    try:
        result = subprocess.run(["git", "-C", str(workspace), *args],
                                capture_output=True, text=True, check=False)
    except OSError:
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def ignore_local_config(workspace) -> Path | None:
    """Trägt `reporting/config.local.json` in `.git/info/exclude` ein.

    Die Ausschlussdatei gilt je Klon, also je Rechner, und für alle Worktrees
    dieses Klons. Sie ist selbst nicht getrackt: das Repo des Kunden ändert
    sich nicht, und auf den Rechnern seines Teams gibt es die lokale Datei
    gar nicht. Gibt die Ausschlussdatei zurück, oder `None` ohne Git-Repo.
    Bricht ab, wenn die lokale Datei schon getrackt ist; dann stünde der Pfad
    dieses Rechners im Repo des Kunden.
    """
    workspace = Path(workspace)
    relative = f"reporting/{LOCAL_CONFIG_NAME}"
    if _git(workspace, "rev-parse", "--is-inside-work-tree") != "true":
        return None
    if _git(workspace, "ls-files", "--error-unmatch", relative) is not None:
        raise BrandFileError(
            f"{workspace / relative} ist im Repo getrackt. Erst aus dem Index "
            f"nehmen (git rm --cached {relative}); sie hält einen Pfad dieses "
            "Rechners und gehört in kein Commit.")
    exclude = _git(workspace, "rev-parse", "--git-path", "info/exclude")
    if not exclude:
        return None
    path = Path(exclude)
    if not path.is_absolute():
        path = workspace / path
    pattern = f"/{relative}"
    lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    if pattern not in lines:
        path.parent.mkdir(parents=True, exist_ok=True)
        lines.append(pattern)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def set_local(workspace, brand_workspace) -> Path:
    """Schreibt `brand_workspace` für diesen Rechner nach `reporting/config.local.json`.

    Prüft vorher, was jeder Lauf prüft (absolut, Datei der Marke vorhanden,
    dieselbe Marke), und schreibt erst dann. Die Datei kommt in
    `.git/info/exclude`, bevor sie entsteht.
    """
    workspace = Path(workspace)
    path = Path(str(brand_workspace)).expanduser()
    if not path.is_absolute():
        raise BrandFileError(f"--brand-workspace muss ein absoluter Pfad sein, ist {brand_workspace!r}")
    config = read_config(workspace)
    if not config:
        raise BrandFileError(f"{workspace / 'reporting' / 'config.json'} fehlt; das ist kein Store-Workspace.")
    target = workspace / "reporting" / LOCAL_CONFIG_NAME
    _checked_reporting(path, config, str(target))
    ignore_local_config(workspace)
    target.write_text(json.dumps({"brand_workspace": str(path)}, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    return target


def main(argv=None) -> int:
    """CLI: den Ordner der Marke für diesen Rechner setzen oder anzeigen."""
    import argparse

    parser = argparse.ArgumentParser(prog="audit.brand", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    setter = sub.add_parser("set-local", help="brand_workspace nur für diesen Rechner setzen")
    setter.add_argument("--workspace", default=".")
    setter.add_argument("--brand-workspace", required=True)
    show = sub.add_parser("show", help="welcher Ordner der Marke gilt und woher")
    show.add_argument("--workspace", default=".")
    args = parser.parse_args(argv)

    if args.command == "set-local":
        target = set_local(args.workspace, args.brand_workspace)
        print(f"{target} geschrieben und in .git/info/exclude eingetragen.")
        return 0
    raw, origin = brand_workspace_setting(args.workspace)
    if raw is None:
        print("Kein brand_workspace: Maßnahmen liegen im Store.")
        return 0
    print(f"{brand_reporting_dir(args.workspace)} (aus {origin})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
