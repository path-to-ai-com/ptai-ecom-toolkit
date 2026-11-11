"""Geführter Launch einer Theme-Migration: prüfen, fragen, veröffentlichen, danach prüfen.

Phase 9 der Theme-Migration in vier Schritten, ausgeführt in der Sitzung des Teams:

1. **Prüfen** (`launch check`): der Launch-Check läuft, und jeder Go-Punkt steht als Haken-Liste da,
   ✅ erledigt, ❌ fehlt, ⏸ blockiert mit Grund, ✋ manuell zu bestätigen, je mit einer Zeile Beleg, am
   Ende die Summe ("8 von 8 grün"). Was für diesen Launch nicht zutrifft, steht in einer Zeile darunter.
2. **Fragen:** nur wenn alles grün ist, folgt "Jetzt Launch durchführen?" mit neuem und altem Theme
   und dem Rückfall-Theme. Sonst gibt es keine Frage, sondern die Liste dessen, was fehlt, und wer es
   erledigt.
3. **Veröffentlichen** (`launch publish --approved-by <Name>`), nur nach dem ausdrücklichen Ja der
   Person der Marke: Schlussprüfung (`theme.sync.final_check`), Sicherung von `layout/theme.liquid` und
   `config/settings_data.json` des Entwurfs nach `<lauf>/published-draft/` (seit 11.11.2026, Referenz für
   `app-injections-after`), dann `shopify theme publish`, dann zurücklesen, dass das neue Theme die Rolle
   `MAIN` hat. Danach stehen Zeitpunkt, neues Live-Theme, Rückfall-Theme und der Name der Person im
   Migrationslauf und in `launch.json`.
4. **Prüfen danach** (`launch check --after`): dieselbe Haken-Liste für die Prüfungen nach dem
   Veröffentlichen, am Ende der festgehaltene Stand.

Dazu seit 10.11.2026 **Rückfall** (`launch rollback`): die Kriterien, nach denen zurückgeschaltet wird, wer
im Ernstfall entscheidet und was nur bei diesem Launch nach einem Rückfall bleibt, in
`migration/rollback.json`. Vorher standen sie nur im Gespräch oder auf einer eigens gebauten Seite neben
dem Cockpit (10.11.2026). Das Cockpit zeigt sie mit Go-Liste und Ablauf (Modul `launch_status`).

Bis 10.11.2026 galt "die Skills veröffentlichen nie, den Klick macht ein Mensch im Admin". Die
Migrationen davor liefen chaotisch, und der Ablauf stand verteilt auf drei Dokumente (Phase 9 von
`theme-migration`, `launch-check`, `launch-checklist.md`). Jetzt veröffentlicht dieses Modul selbst, als
einziges im Paket (Test `TestNieVeroeffentlichen`), und nur mit dem Namen der Person, die Ja gesagt hat.

**Flags** von `shopify theme publish` am 10.11.2026 gegen Shopify CLI 4.9.4 geprüft (`shopify theme
publish --help`, Skill `shopify-use-shopify-cli`): `--store`, `--theme <id>`, `--force` (ohne Rückfrage,
ohne Terminal nötig), `--no-input` (keine Rückfrage und keine Anmeldung im Browser), `--path` (der Befehl
läuft nur in einem Ordner mit Theme-Struktur, deshalb das Ziel-Repo aus `theme_migration.target_repo`).
Er hat keine JSON-Ausgabe; ob das Theme live ist, entscheidet das Zurücklesen über die Theme-Liste,
nicht der Exit-Code der CLI. Angemeldet wird wie beim Upload über `cli-theme`: ein Konto mit
Themes-Recht oder ein Passwort aus Theme Access in `SHOPIFY_CLI_THEME_TOKEN`, nie als Argument.

CLI:
    python3 -m theme.launch check [--after] [Argumente von theme.launch_check ...] [--json]
    python3 -m theme.launch publish --approved-by "<Name>" [--theme-dir <ziel-repo>] [--run-id <id>] [--json]
    python3 -m theme.launch rollback [--decider "<Name>" --criterion "<wann> | <Frist>" ...
        [--not-reverted "<was bleibt>" ...] [--agreed-with "<Name>"]] [--json]

Exit 0: alles grün (`check`) oder veröffentlicht und als `MAIN` zurückgelesen (`publish`).
Exit 1: nicht grün, angehalten oder nicht bestätigt. Exit 2: Fehler im Aufruf oder in der Config.
"""
import argparse
import json
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from shopify_cli import ShopifyError, run_cli
from theme import (EXIT_ERROR, EXIT_FINDINGS, EXIT_OK, ConfigError, emit, load_config, migration_config, now_utc,
                   write_json)
from theme import launch_check as lc
from theme import launch_status, questions, run_state, sync
from theme.files import list_themes
from theme.shopify import numeric_id, transport_from_config

SYMBOLS = {lc.OK: "✅", lc.MISSING: "❌", lc.BLOCKED: "⏸", lc.MANUAL: "✋"}
QUESTION = "Jetzt Launch durchführen?"
ANNOUNCE_AFTER = "Jetzt kommt der Launch-Check After."
#: Eine Zeile Beleg je Punkt; längere Belege stehen vollständig in launch-check.md.
EVIDENCE_WIDTH = 160
#: So alt darf der Launch-Check höchstens sein, auf den sich das Ja bezieht; das Cockpit rechnet mit demselben Wert.
REPORT_MAX_AGE = launch_status.REPORT_MAX_AGE
#: Wartezeiten vor dem erneuten Zurücklesen; Shopify setzt die Rolle nicht immer sofort um.
READBACK_WAITS = (5, 10, 20)
#: Wer laut Launch-Check etwas erledigt, in den Worten der Sitzung des Teams. "Betreiber" heißt dort, wer
#: den Prüflauf ausführt; seit 0.3.27 ist das die Sitzung des Teams selbst.
OWNER_LABEL = {lc.OPERATOR: "diese Sitzung", lc.BOTH: "Team mit dieser Sitzung", lc.TEAM: "Team"}
COMMANDS = ("check", "publish", "rollback")
#: Trennt in `--criterion` das Kriterium von der Frist ("Kauf nicht möglich | sofort").
CRITERION_SEPARATOR = "|"


class LaunchError(RuntimeError):
    """Der Aufruf trägt nicht, was der Launch braucht."""


# ---------------------------------------------------------------------------
# Haken-Liste
# ---------------------------------------------------------------------------

def one_line(text, width: int = EVIDENCE_WIDTH) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= width else text[:width - 1].rstrip() + "…"


def owner_label(owner: str) -> str:
    return OWNER_LABEL.get(owner or lc.OPERATOR, owner)


def is_green(report: dict) -> bool:
    """Grün heißt: jeder Punkt erfüllt oder für diesen Launch nicht zutreffend, also Empfehlung Go."""
    return report.get("recommendation") == "go"


def checklist(report: dict) -> list[str]:
    """Je Go-Punkt Symbol und Titel, darunter eine Zeile Beleg; am Ende die Summe."""
    lines, skipped = [], []
    for check in report["checks"]:
        if check["status"] == lc.NA:
            skipped.append(check["title"])
            continue
        detail = check["question"] if check["status"] == lc.MANUAL and check.get("question") else check["evidence"]
        lines += [f"{SYMBOLS[check['status']]} {check['title']}", f"   {one_line(detail)}"]
    total = len(report["checks"]) - len(skipped)
    green = sum(1 for c in report["checks"] if c["status"] == lc.OK)
    lines += ["", f"{green} von {total} grün"]
    if skipped:
        lines.append(f"Entfällt für diesen Launch: {', '.join(skipped)}")
    return lines


def pending(report: dict) -> list[str]:
    """Was fehlt und wer es erledigt, je Punkt eine Zeile."""
    out = []
    for check in report["checks"]:
        if check["status"] in (lc.OK, lc.NA):
            continue
        todo = check.get("question") or check.get("action") or check["evidence"]
        out += [f"{SYMBOLS[check['status']]} {check['title']}", f"   {one_line(todo)}",
                f"   Wer: {owner_label(check.get('owner'))}"]
    return out


def theme_label(themes: dict, theme_id) -> str:
    name = (themes.get(str(theme_id)) or {}).get("name")
    return f"{theme_id} \"{name}\"" if name else str(theme_id)


def question(report: dict, themes: dict) -> list[str]:
    new, old = report["new_theme_id"], report["old_theme_id"]
    return [QUESTION,
            f"   Neues Theme: {theme_label(themes, new)}, wird live",
            f"   Bisher live: {theme_label(themes, old)}",
            f"   Rückfall-Theme: {theme_label(themes, old)}, bleibt als Entwurf in der Theme-Bibliothek"]


def recorded_state(workspace: Path, run_dir: Path) -> dict:
    """Der festgehaltene Stand des Launches: aus dem Migrationslauf, sonst aus `launch.json`."""
    run_id = run_state.latest_run_id(workspace)
    if run_id:
        try:
            values = run_state.load(workspace, run_id).data.get("values") or {}
        except run_state.StateError:
            values = {}
        if values.get("published_at"):
            return {key: values.get(key) for key in ("published_at", "live_theme_id", "rollback_theme_id",
                                                     "launch_approved_by")}
    record = lc.read_json(run_dir / "launch.json") or {}
    if record.get("published"):
        return {"published_at": record.get("published_at"), "live_theme_id": record.get("new_theme_id"),
                "rollback_theme_id": record.get("rollback_theme_id"), "launch_approved_by": record.get("approved_by")}
    return {}


def state_lines(state: dict) -> list[str]:
    if not state:
        return ["Stand", "   nicht festgehalten: kein veröffentlichter Launch im Migrationslauf und kein launch.json"]
    who = f" nach Ja von {state['launch_approved_by']}" if state.get("launch_approved_by") else ""
    return ["Stand",
            f"   Veröffentlicht: {state.get('published_at') or 'fehlt'}{who}",
            f"   Live: {state.get('live_theme_id') or 'fehlt'}",
            f"   Rückfall-Theme: {state.get('rollback_theme_id') or 'fehlt'}"]


def theme_names(ctx: dict) -> dict:
    try:
        themes, _ = lc.themes_by_id(ctx)
    except Exception:  # Namen sind nur Beschriftung; ohne sie bleibt die ID
        themes = None
    return themes or {}


def render_check(report: dict, ctx: dict) -> list[str]:
    after = report["mode"] == "after"
    stamp = report.get("checked_at") or ""
    lines = [f"Launch-Check {'After' if after else 'vor dem Launch'}, geprüft {stamp}", ""]
    lines += checklist(report)
    lines.append("")
    if after:
        if not is_green(report):
            lines += ["Offen nach dem Launch:"] + pending(report) + [""]
        lines += state_lines(recorded_state(ctx["workspace"], ctx["run_dir"]))
    elif is_green(report):
        lines += question(report, theme_names(ctx))
    else:
        lines += ["Noch nicht alles grün, deshalb keine Frage nach dem Launch. Es fehlt:"] + pending(report)
    lines += ["", f"Bericht: {(ctx['run_dir'] / ('launch-check' + ctx['suffix'] + '.md')).as_posix()}"]
    return lines


def command_check(argv: list[str], *, check=None, **injected) -> int:
    parser = lc.build_parser()
    parser.prog = "theme.launch check"
    parser.add_argument("--json", action="store_true", help="Bericht als JSON statt der Haken-Liste")
    args = parser.parse_args(argv)
    try:
        report, _, ctx = (check or lc.execute)(args, **injected)
    except (ConfigError, OSError, ValueError) as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        emit({"ok": False, "error": str(exc)})
        return EXIT_ERROR
    green = is_green(report)
    if args.json:
        emit({"ok": True, "mode": report["mode"], "green": green, "recommendation": report["recommendation"],
              "counts": report["counts"], "ask": QUESTION if green and report["mode"] == "before" else None})
    else:
        print("\n".join(render_check(report, ctx)), flush=True)
    return EXIT_OK if green else EXIT_FINDINGS


# ---------------------------------------------------------------------------
# Veröffentlichen
# ---------------------------------------------------------------------------

def report_age(report: dict, now: datetime) -> timedelta | None:
    try:
        checked = datetime.fromisoformat(str(report.get("checked_at")).replace("Z", "+00:00"))
    except ValueError:
        return None
    return now - checked


def readiness(report: dict | None, state, now: datetime) -> list[str]:
    """Gründe, nicht zu veröffentlichen. Leer heißt: das Ja bezieht sich auf einen grünen, frischen Lauf."""
    if not report:
        return ["kein Launch-Check von heute; zuerst launch check"]
    problems = []
    if report.get("mode") != "before":
        problems.append("der Bericht ist kein Launch-Check vor dem Launch")
    if not is_green(report):
        problems.append(f"der Launch-Check ist nicht grün (Empfehlung {report.get('recommendation')}); "
                        "gefragt wird erst, wenn alles grün ist")
    age = report_age(report, now)
    if age is None or age > REPORT_MAX_AGE:
        problems.append(f"der Launch-Check ist älter als {int(REPORT_MAX_AGE.total_seconds() // 3600)} Stunden "
                        f"({report.get('checked_at')}); neu prüfen und neu fragen")
    if not (report.get("new_theme_id") and report.get("old_theme_id")):
        problems.append("im Bericht fehlt die ID des neuen oder des bisherigen Themes")
    if state is not None and not (state.data.get("gates") or {}).get("G5-go-live"):
        problems.append("Gate G5 ist im Migrationslauf nicht entschieden")
    return problems


def resolve_theme_dir(workspace: Path, block: dict, theme_dir) -> Path:
    raw = theme_dir or block.get("target_repo")
    if not raw:
        raise LaunchError("theme_migration.target_repo fehlt; shopify theme publish läuft nur in einem Theme-Ordner "
                          "(--theme-dir)")
    path = Path(os.path.expanduser(str(raw)))
    path = path if path.is_absolute() else workspace / path
    if not (path / "layout" / "theme.liquid").is_file():
        raise LaunchError(f"{path} ist kein Theme-Ordner (layout/theme.liquid fehlt)")
    return path


def publish_command(binary: str, store: str, theme_id: str, theme_dir: Path) -> list[str]:
    return [binary, "theme", "publish", "--store", store, "--theme", str(theme_id), "--path", str(theme_dir),
            "--force", "--no-input", "--no-color"]


def themes_now(transport) -> dict:
    return {numeric_id(t["id"]): t for t in list_themes(transport)}


def read_back(transport, new_id: str, old_id: str, sleep, waits=READBACK_WAITS) -> dict:
    """Liest die Theme-Liste, bis das neue Theme `MAIN` ist oder die Wartezeiten aufgebraucht sind."""
    result = {}
    for attempt in range(len(waits) + 1):
        if attempt:
            sleep(waits[attempt - 1])
        try:
            themes = themes_now(transport)
        except ShopifyError as exc:
            result = {"error": str(exc), "checked_at": now_utc()}
            continue
        main = next((tid for tid, t in themes.items() if t.get("role") == "MAIN"), None)
        result = {"checked_at": now_utc(), "main_theme_id": main,
                  "new_role": (themes.get(new_id) or {}).get("role"), "old_role": (themes.get(old_id) or {}).get("role"),
                  "new_name": (themes.get(new_id) or {}).get("name"), "old_name": (themes.get(old_id) or {}).get("name")}
        if result["new_role"] == "MAIN":
            break
    result["confirmed"] = result.get("new_role") == "MAIN"
    return result


def update_config_live(workspace: Path, new_id: str) -> None:
    """`theme_migration.live_theme_id` auf das neue Theme; der Rest der Config bleibt, wie er ist."""
    path = workspace / "reporting" / "config.json"
    config = json.loads(path.read_text(encoding="utf-8"))
    block = config.setdefault("theme_migration", {})
    block["live_theme_id"] = str(new_id)
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def record_state(workspace: Path, state, record: dict) -> None:
    values = {"published_at": record["published_at"], "live_theme_id": record["new_theme_id"],
              "rollback_theme_id": record["rollback_theme_id"], "launch_approved_by": record["approved_by"]}
    for key, value in values.items():
        state.set_value(key, value)
    state.save()
    state.log("set", "; ".join(f"{k}={v}" for k, v in values.items()), phase="9-launch")
    run_state.export(workspace, state)


def publish(workspace, approved_by: str, *, transport=None, runner=None, sleep=time.sleep, run_id=None,
            theme_dir=None, binary: str = "shopify", now: datetime | None = None) -> tuple[dict, int]:
    """Schlussprüfung, Veröffentlichen, Zurücklesen, Stand festhalten. Gibt `(record, exit_code)` zurück."""
    workspace = Path(workspace)
    approved_by = (approved_by or "").strip()
    if not approved_by:
        raise LaunchError("--approved-by fehlt: veröffentlicht wird nur nach dem Ja einer Person, mit ihrem Namen")
    try:
        # Dieselbe Regel wie für jedes Gate: der Name einer Person, die entscheiden darf, kein Sammelname.
        approved_by = questions.check_person(workspace, approved_by)
    except questions.QuestionError as exc:
        raise LaunchError(str(exc)) from exc
    config = load_config(workspace)
    block = migration_config(config)
    store = config.get("shopify_store") or ""
    if not store:
        raise LaunchError("shopify_store fehlt in reporting/config.json")
    run_dir = workspace / "reporting" / "runs" / (run_id or f"{date.today().isoformat()}-launch-check")
    report = lc.read_json(run_dir / "launch-check.json")
    state, state_id = None, run_state.latest_run_id(workspace)
    if state_id:
        state = run_state.load(workspace, state_id)
    moment = now or datetime.now(timezone.utc)
    record = {"kind": "launch", "run_id": run_dir.name, "approved_by": approved_by, "approved_at": now_utc(),
              "migration_run": state_id, "published": False}
    problems = readiness(report, state, moment)
    if problems:
        return {**record, "status": "refused", "problems": problems}, EXIT_FINDINGS
    new_id, old_id = str(report["new_theme_id"]), str(report["old_theme_id"])
    record.update(new_theme_id=new_id, old_theme_id=old_id, rollback_theme_id=old_id)
    path = resolve_theme_dir(workspace, block, theme_dir)
    if state is not None:
        # Vor dem Veröffentlichen, nicht danach: hält eine andere Sitzung den Lauf, darf nichts live gehen,
        # dessen Stand dann niemand festhalten kann.
        run_state.claim(workspace, state_id)
    if transport is None:
        transport = transport_from_config(config, workspace=workspace)
    themes = themes_now(transport)
    draft = themes.get(new_id)
    if not draft or draft.get("role") != "UNPUBLISHED" or draft.get("processing") or draft.get("processingFailed"):
        found = f"Rolle {draft.get('role')}" if draft else "nicht im Store"
        record.update(status="refused", problems=[f"Theme {new_id}: {found}, erwartet ein fertig verarbeiteter "
                                                  "Entwurf (UNPUBLISHED)"])
        write_json(run_dir / "launch.json", record)
        return record, EXIT_FINDINGS
    record["draft_updated_at"] = draft.get("updatedAt")
    final = sync.final_check(transport, workspace, old_id)
    record["final_check"] = final
    if not final["ok"]:
        record.update(status="held", problems=final["problems"])
        write_json(run_dir / "launch.json", record)
        return record, EXIT_FINDINGS
    # Layout und Einstellungen des Entwurfs, genau wie sie veröffentlicht werden: die Referenz, gegen die
    # `launch check --after` prüft, ob sich eine App beim Veröffentlichen eingetragen hat. Scheitert der
    # Abruf, steht der Grund in launch.json, und die Prüfung danach vergleicht mit dem Ziel-Repo.
    record["draft_backup"] = lc.backup_draft(transport, new_id, run_dir)
    command = publish_command(binary, store, new_id, path)
    record["command"] = command
    env = dict(os.environ, SHOPIFY_CLI_NO_ANALYTICS="1", SHOPIFY_CLI_NO_UPDATE_NOTIFIER="1")
    try:
        proc = (runner or run_cli)(command, capture_output=True, encoding="utf-8", errors="replace", env=env)
        record["cli"] = {"exit": proc.returncode, "output": one_line((proc.stdout or "") + " " + (proc.stderr or ""), 600)}
    except (OSError, ShopifyError) as exc:
        record["cli"] = {"exit": None, "output": str(exc)}
    # Ohne Erfolg der CLI genügt ein Blick; mit Erfolg darf Shopify ein paar Sekunden brauchen.
    waits = READBACK_WAITS if record["cli"]["exit"] == 0 else ()
    record["readback"] = read_back(transport, new_id, old_id, sleep, waits)
    if not record["readback"]["confirmed"]:
        record["status"] = "not_confirmed"
        write_json(run_dir / "launch.json", record)
        return record, EXIT_FINDINGS
    record.update(status="published", published=True, published_at=record["readback"]["checked_at"])
    write_json(run_dir / "launch.json", record)
    update_config_live(workspace, new_id)
    if state is not None:
        record_state(workspace, state, record)
    return record, EXIT_OK


def render_publish(record: dict) -> list[str]:
    status = record.get("status")
    if status == "refused":
        return ["Nicht veröffentlicht, nicht gefragt:"] + [f"- {p}" for p in record["problems"]]
    if status == "held":
        return (["Nicht veröffentlicht: die Schlussprüfung hält den Launch an."]
                + [f"- {p}" for p in record["problems"]]
                + ["Zuerst sync-live-theme für die geänderten Teile, dann launch check und erneut fragen."])
    back = record.get("readback") or {}
    if status == "not_confirmed":
        live = back.get("main_theme_id") or "unbekannt"
        return [f"Nicht bestätigt: Theme {record['new_theme_id']} hat die Rolle {back.get('new_role') or 'unbekannt'}, "
                f"erwartet MAIN. Live ist {live}.",
                f"Shopify CLI (Exit {record['cli']['exit']}): {record['cli']['output'] or 'keine Ausgabe'}",
                "Nicht erneut veröffentlichen, bevor geklärt ist, was live ist (Theme-Bibliothek im Admin)."]
    lines = [f"Veröffentlicht: {record['new_theme_id']} \"{back.get('new_name')}\" ist live, Rolle MAIN, "
             f"zurückgelesen {back.get('checked_at')}.",
             f"Rückfall-Theme: {record['rollback_theme_id']} \"{back.get('old_name')}\", Rolle {back.get('old_role')}.",
             f"Ja von {record['approved_by']}."]
    if record.get("migration_run"):
        lines.append(f"Festgehalten im Migrationslauf {record['migration_run']}: published_at, live_theme_id, "
                     "rollback_theme_id, launch_approved_by.")
    return lines + ["", ANNOUNCE_AFTER]


def command_publish(argv: list[str], *, transport=None, runner=None, sleep=None) -> int:
    parser = argparse.ArgumentParser(prog="theme.launch publish",
                                     description="Veröffentlicht nach dem Ja der Person der Marke")
    parser.add_argument("--approved-by", required=True, help="Name der Person, die Ja gesagt hat")
    parser.add_argument("--theme-dir", help="Theme-Ordner für shopify theme publish; Standard target_repo")
    parser.add_argument("--run-id", help="Lauf des Launch-Checks, Standard <heute>-launch-check")
    parser.add_argument("--workspace", default=".")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        record, code = publish(args.workspace, args.approved_by, transport=transport, runner=runner,
                               sleep=sleep or time.sleep, run_id=args.run_id, theme_dir=args.theme_dir)
    except (LaunchError, ConfigError, ShopifyError, run_state.StateError, OSError, ValueError) as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        emit({"ok": False, "error": str(exc)})
        return EXIT_ERROR
    if args.json:
        emit({"ok": True, **record})
    else:
        print("\n".join(render_publish(record)), flush=True)
    return code


# ---------------------------------------------------------------------------
# Rückfall
# ---------------------------------------------------------------------------

def parse_criterion(text: str) -> dict:
    """`"<wann> | <Frist>"` als Kriterium; die Frist ist optional."""
    when, _, deadline = str(text or "").partition(CRITERION_SEPARATOR)
    when, deadline = " ".join(when.split()), " ".join(deadline.split())
    if not when:
        raise LaunchError(f"Kriterium ohne Text: {text!r}; Form \"<wann> | <Frist>\"")
    return {"when": when, "deadline": deadline or None}


def set_rollback(workspace, decider: str, criteria: list[str], *, not_reverted=(), agreed_with: str = "",
                 now: str | None = None) -> dict:
    """Schreibt die Rückfallkriterien nach `migration/rollback.json` und gibt sie zurück.

    `decider` ist die Person, die im Ernstfall entscheidet, mit derselben Regel wie für ein Gate: der Name
    einer Person aus `theme_migration.people`, kein Sammelname. Ein neuer Aufruf ersetzt die Datei ganz,
    damit kein verworfenes Kriterium stehen bleibt.
    """
    workspace = Path(workspace)
    try:
        decider = questions.check_person(workspace, decider)
    except questions.QuestionError as exc:
        raise LaunchError(str(exc)) from exc
    parsed = [parse_criterion(c) for c in criteria]
    if not parsed:
        raise LaunchError("Mindestens ein Kriterium (--criterion), nach dem zurückgeschaltet wird.")
    plan = {"decider": decider, "agreed_with": " ".join(str(agreed_with or "").split()) or None,
            "set_at": now or now_utc(), "criteria": parsed,
            "not_reverted": [" ".join(str(t).split()) for t in not_reverted if str(t).strip()]}
    write_json(launch_status.rollback_path(workspace), plan)
    return plan


def render_rollback(plan: dict) -> list[str]:
    if not plan.get("criteria"):
        return ["Rückfall: noch keine Kriterien festgelegt (launch rollback --decider ... --criterion ...)."]
    who = plan.get("decider") + (f", abgestimmt mit {plan['agreed_with']}" if plan.get("agreed_with") else "")
    lines = [f"Rückfall, festgelegt {plan.get('set_at')}. Entscheidet: {who}", "Zurück, wenn:"]
    lines += [f"   {c['when']}" + (f" ({c['deadline']})" if c.get("deadline") else "") for c in plan["criteria"]]
    lines += ["Bleibt auch nach einem Rückfall:"]
    lines += [f"   {t}" for t in list(plan.get("not_reverted") or []) + list(launch_status.NOT_REVERTED)]
    return lines


def command_rollback(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="theme.launch rollback",
                                     description="Rückfallkriterien festlegen oder zeigen")
    parser.add_argument("--decider", help="Person, die im Ernstfall über den Rückfall entscheidet")
    parser.add_argument("--criterion", action="append", default=[],
                        help='Wann zurückgeschaltet wird, mit Frist: "<wann> | <Frist>"; mehrfach')
    parser.add_argument("--not-reverted", action="append", default=[],
                        help="Was nur bei diesem Launch nach einem Rückfall bleibt; mehrfach")
    parser.add_argument("--agreed-with", default="", help="mit wem abgestimmt, etwa Path to AI")
    parser.add_argument("--workspace", default=".")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.decider or args.criterion:
            if not args.decider:
                raise LaunchError("--decider fehlt: Rückfallkriterien tragen die Person, die im Ernstfall entscheidet")
            plan = set_rollback(args.workspace, args.decider, args.criterion, not_reverted=args.not_reverted,
                                agreed_with=args.agreed_with)
        else:
            plan = launch_status.load_rollback(args.workspace)
    except (LaunchError, OSError, ValueError) as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        emit({"ok": False, "error": str(exc)})
        return EXIT_ERROR
    if args.json:
        emit({"ok": True, **plan})
    else:
        print("\n".join(render_rollback(plan)), flush=True)
    return EXIT_OK


def main(argv: list[str] | None = None, *, transport=None, fetch=None, sleep=None, ga4=None, runner=None,
         check=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] not in COMMANDS:
        print(f"Aufruf: python3 -m theme.launch {{{','.join(COMMANDS)}}} ...", file=sys.stderr)
        return EXIT_ERROR
    if argv[0] == "check":
        injected = {"transport": transport, "fetch": fetch, "sleep": sleep, "ga4": ga4}
        return command_check(argv[1:], check=check, **injected)
    if argv[0] == "rollback":
        return command_rollback(argv[1:])
    return command_publish(argv[1:], transport=transport, runner=runner, sleep=sleep)


if __name__ == "__main__":
    raise SystemExit(main())
