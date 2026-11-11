"""Bildpaare zweier Themes je Beispielseite: Chromium am Rechner und WebKit als iPhone, mit Theme-Nachweis.

Aufruf (aus dem Workspace):

  uv run --quiet --with playwright==1.58.0 python scripts/browser/shoot_pair.py \
    --pages migration/inventory/pages.json --a <live-theme-id> --b <draft-theme-id> --out <ordner> \
    [--devices desktop,mobile] [--only home,product] [--workspace .]

Links (`a`) steht immer das veröffentlichte Theme mit seiner ID, rechts (`b`) der
Entwurf. Je Seite, Gerät und Seite des Paars entsteht
`<ordner>/<id>/<gerät>-<a|b>.png` (ganze Seite in CSS-Pixeln, höchstens
`MAX_HEIGHT` hoch) und `…-fold.png` (die Erstansicht in voller Dichte), dazu
`<ordner>/pairs.json` als Index für `compose.py`. Breiten: Rechner 1440, Handy 390.

Beide Seiten eines Paars laufen unter denselben Bedingungen: frischer Kontext,
`preview_theme_id` und `pb=0`, Cookie-Dialog abgelehnt, einmal bis zum Ende
gescrollt, auch in einem scrollenden Container wie `.page-wrapper` in Horizon
(lädt nachgeladene Bilder), `content-visibility` erzwungen (Footer in Horizon),
zurück nach oben, Wartezeit. Ein Bild, dessen Seite ein anderes Theme zeigt,
bleibt stehen und ist als `wrong_theme` markiert: es sieht aus wie ein Ergebnis
und ist keins. Ebenso `incomplete`, wenn ein Ganzseiten-Bild nicht die ganze
Seite zeigt (`common.capture_full_page`, Verfahren `resized`).

**Referenz.** Die linke Seite muss das veröffentlichte Theme sein. Beleg ist die
Rolle `main` im Theme-Nachweis der Seiten; `--a` wird außerdem gegen
`live_theme_id` der Config geprüft. Steht links ein anderes Theme, ist der
Vergleich ungültig (Exit 1, `reference.problems`); eine abweichende Config bei
belegter Rolle ist eine Warnung (`reference.warnings`).

**Eintrag für Gate G4.** Liegt im Workspace `reporting/config.json`, schreibt das
Skript zusätzlich `migration/verify/<date>/pairs.json`: dieselben Paare mit
Referenz und Abdeckung, ohne Bilder. `theme.visual_compare` liest daraus, ob für
jede Beispielseite am Rechner und am Handy ein gültiges Paar vorliegt; ohne das
hält G4 an. Ein zweiter Lauf am selben Tag mit denselben Themes ergänzt den
Eintrag je Seite und Breite.

Die Bilder gehören in den Kundenordner, nie ins Repo. Jedes Paar wird angesehen;
eine Pixel-Differenz allein ist kein Befund. Exit 0 alle Bilder gültig und
Referenz belegt, 1 mindestens ein Bild mit falschem Theme oder Fehler oder die
Referenz ist nicht das veröffentlichte Theme, 2 Fehler vor dem ersten Aufruf.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import common  # noqa: E402
from theme import visual_compare  # noqa: E402  (common legt scripts/ in den Suchpfad)

#: Höher wird eine Ganzseiten-Aufnahme nicht; darunter liegt selten etwas, das ein Vergleich braucht.
MAX_HEIGHT = 16000


def image_names(page_id: str, device: str, side: str) -> tuple[str, str]:
    """Feste Dateinamen je Seite, Gerät und Seite des Paars, relativ zum Zielordner."""
    return f"{page_id}/{device}-{side}.png", f"{page_id}/{device}-{side}-fold.png"


def build_pairs(jobs: list[dict], results: list[dict], themes: dict) -> dict:
    """Ordnet die Aufnahmen zu Paaren je Seite und Gerät."""
    pairs: dict[tuple, dict] = {}
    for job, result in zip(jobs, results):
        key = (job["page"]["id"], job["device"])
        entry = pairs.setdefault(key, {"page_id": job["page"]["id"], "template": job["page"].get("template"),
                                       "path": job["page"]["path"], "device": job["device"],
                                       "width": visual_compare.WIDTHS.get(job["device"])})
        if result.get("job") is not None:
            result = {"state": "error", "error": result.get("error")}
        entry[job["side"]] = result
    ordered = sorted(pairs.values(), key=lambda p: ([j["page"]["id"] for j in jobs].index(p["page_id"]), p["device"]))
    return {"tool": "shoot_pair", "themes": themes, "pairs": ordered}


def read_config(workspace: Path) -> dict | None:
    """`reporting/config.json` des Workspace, None ohne Workspace."""
    try:
        data = json.loads((workspace / "reporting" / "config.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def finish(data: dict, page_ids: list, config: dict | None) -> dict:
    """Referenz und Abdeckung an den Index hängen, dazu die Abweichung der rechten Seite vom Entwurf."""
    live, draft = visual_compare.current_ids(config or {})
    summary = visual_compare.record_summary(page_ids, data["pairs"], data["themes"], live)
    if draft and not visual_compare.same_id(data["themes"].get("b"), draft):
        summary["reference"]["warnings"].append(f"rechts steht Theme {data['themes'].get('b')}, draft_theme_id "
                                                f"der Config ist {draft}; Gate G4 zählt nur den Entwurf")
    for pair in data["pairs"]:
        pair.setdefault("captured_at", data.get("captured_at"))
    return {**data, "pages": page_ids, "widths": dict(visual_compare.WIDTHS), **summary}


def write_record(workspace: Path, data: dict, images_dir: Path) -> Path:
    """`migration/verify/<date>/pairs.json` im Workspace schreiben oder am selben Tag ergänzen."""
    path = visual_compare.record_path(workspace)
    try:
        old = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        old = None
    record = visual_compare.merge_record(old, {**data, "images_dir": str(images_dir)})
    common.write_json(path, record)
    return path


def shoot(playwright, browsers: dict, job: dict) -> dict:
    device, page_info, side = job["device"], job["page"], job["side"]
    theme_id = job["themes"][side]
    browser = common.browser_for(playwright, browsers, device)
    url = common.page_url(job["base_url"], page_info["path"], theme_id, hide_bar=True)
    full_name, fold_name = image_names(page_info["id"], device, side)
    out = job["out"]
    (out / page_info["id"]).mkdir(parents=True, exist_ok=True)
    context = browser.new_context(**common.context_options(playwright, device, job["locale"]))
    result = {"url": url, "theme_id": theme_id, "state": "ok", "captured_at": common.now()}
    try:
        page = context.new_page()
        response = page.goto(url, wait_until="load", timeout=job["timeout"])
        result["status"] = response.status if response else None
        page.wait_for_timeout(1500)
        theme = common.check_theme(common.theme_in_page(page), theme_id)
        result["theme_check"] = theme
        result["consent"] = common.handle_consent(page, "declined")
        page.keyboard.press("Escape")
        result["scroll_steps"] = common.scroll_to_end(page)
        result["forced_visible"] = common.force_visible(page)
        common.scroll_to_top(page)
        page.wait_for_timeout(job["wait"])
        page.screenshot(path=str(out / fold_name))
        capture = common.capture_full_page(page, str(out / full_name), MAX_HEIGHT)
        result.update({"file": full_name, "fold_file": fold_name, "page_height": capture["page_height"],
                       "cut_at": capture["cut_at"], "viewport": capture["viewport"],
                       "capture": {k: capture[k] for k in ("method", "scroller", "pinned", "incomplete")}})
        if theme["state"] != "ok":
            result["state"] = "wrong_theme"
        elif capture["incomplete"]:
            # Ein Bild, in dem ein Teil der Seite fehlt, sieht vollständig aus und ist es nicht.
            result["state"] = "incomplete"
            result["error"] = "Ganzseiten-Bild unvollständig: der Container scrollt nach dem Vergrößern noch"
    except Exception as exc:
        result["state"] = "error"
        result["error"] = f"{type(exc).__name__}: {exc}"[:500]
    finally:
        context.close()
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Bildpaare zweier Themes je Beispielseite")
    parser.add_argument("--pages", required=True, help="pages.json")
    parser.add_argument("--a", required=True, help="Theme-ID der linken Seite: das veröffentlichte Theme")
    parser.add_argument("--b", required=True, help="Theme-ID der rechten Seite: der Entwurf")
    parser.add_argument("--out", required=True, help="Zielordner der Bilder, im Kundenordner")
    parser.add_argument("--workspace", default=".", help="Workspace für Config und Eintrag unter migration/verify/")
    parser.add_argument("--devices", default="desktop,mobile")
    parser.add_argument("--only", help="nur diese Seiten-IDs, kommagetrennt")
    parser.add_argument("--wait", type=int, default=2500, help="Wartezeit vor der Aufnahme in ms")
    parser.add_argument("--timeout", type=int, default=60000)
    parser.add_argument("--locale", default="de-DE")
    parser.add_argument("--parallel", type=int, default=common.MAX_PARALLEL, help="höchstens 2")
    args = parser.parse_args(argv)
    try:
        pages = common.load_pages(args.pages, common.parse_list(args.only))
        devices = common.parse_list(args.devices, common.DEVICES) or list(common.DEVICES)
    except (common.PagesError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 2
    try:
        import playwright  # noqa: F401
    except ImportError:
        print(json.dumps({"error": common.PLAYWRIGHT_MISSING}, ensure_ascii=False))
        return 2
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    workspace = Path(args.workspace)
    config = read_config(workspace)
    themes = {"a": args.a, "b": args.b}
    jobs = [{"page": page, "page_id": page["id"], "device": device, "side": side, "themes": themes,
             "base_url": pages["base_url"], "out": out, "wait": args.wait, "timeout": args.timeout,
             "locale": args.locale}
            for page in pages["pages"] for device in devices for side in ("a", "b")]
    results = common.run_jobs(jobs, shoot, args.parallel)
    data = {**build_pairs(jobs, results, themes), "base_url": pages["base_url"], "captured_at": common.now()}
    data = finish(data, [p["id"] for p in pages["pages"]], config)
    common.write_json(out / "pairs.json", data)
    record = write_record(workspace, data, out.resolve()) if config is not None else None
    shots = [p.get(side) or {} for p in data["pairs"] for side in ("a", "b")]
    bad = [s for s in shots if s.get("state") != "ok"]
    reference = data["reference"]
    for line in reference["problems"] + reference["warnings"]:
        print(f"Referenz: {line}", file=sys.stderr, flush=True)
    if record is None:
        print(f"Kein Workspace unter {workspace} (reporting/config.json fehlt): kein Eintrag für Gate G4",
              file=sys.stderr, flush=True)
    print(json.dumps({"out": str(out / "pairs.json"), "record": str(record) if record else None,
                      "pairs": len(data["pairs"]), "images": len(shots),
                      "wrong_theme": sum(1 for s in bad if s.get("state") == "wrong_theme"),
                      "errors": sum(1 for s in bad if s.get("state") == "error"),
                      "reference_ok": reference["ok"], "reference_published": reference["published"],
                      "reference_problems": reference["problems"], "reference_warnings": reference["warnings"],
                      "coverage": {k: data["coverage"][k] for k in ("expected", "valid", "complete")}},
                     ensure_ascii=False))
    return 1 if bad or not reference["ok"] else 0


if __name__ == "__main__":
    sys.exit(main())
