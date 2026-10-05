"""Bildpaare zweier Themes je Beispielseite: Chromium am Rechner und WebKit als iPhone, mit Theme-Nachweis.

Aufruf:

  uv run --quiet --with playwright==1.58.0 python scripts/browser/shoot_pair.py \
    --pages migration/inventory/pages.json --a <theme-id> --b <theme-id> --out <ordner> \
    [--devices desktop,mobile] [--only home,product]

Meist ist `a` das Live-Theme und `b` der Entwurf. Je Seite, Gerät und Seite des
Paars entsteht `<ordner>/<id>/<gerät>-<a|b>.png` (ganze Seite, höchstens
`MAX_HEIGHT` CSS-Pixel hoch) und `…-fold.png` (die Erstansicht), dazu
`<ordner>/pairs.json` als Index für `compose.py`.

Beide Seiten eines Paars laufen unter denselben Bedingungen: frischer Kontext,
`preview_theme_id` und `pb=0`, Cookie-Dialog abgelehnt, einmal bis zum Ende
gescrollt (lädt nachgeladene Bilder), zurück nach oben, Wartezeit. Ein Bild,
dessen Seite ein anderes Theme zeigt, bleibt stehen und ist als `wrong_theme`
markiert: es sieht aus wie ein Ergebnis und ist keins.

Die Bilder gehören in den Kundenordner, nie ins Repo. Jedes Paar wird angesehen;
eine Pixel-Differenz allein ist kein Befund. Exit 0 alle Bilder gültig, 1
mindestens eins mit falschem Theme oder Fehler, 2 Fehler vor dem ersten Aufruf.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import common  # noqa: E402

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
                                       "path": job["page"]["path"], "device": job["device"]})
        if result.get("job") is not None:
            result = {"state": "error", "error": result.get("error")}
        entry[job["side"]] = result
    ordered = sorted(pairs.values(), key=lambda p: ([j["page"]["id"] for j in jobs].index(p["page_id"]), p["device"]))
    return {"tool": "shoot_pair", "themes": themes, "pairs": ordered}


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
        common.scroll_to_end(page)
        page.evaluate("() => window.scrollTo(0, 0)")
        page.wait_for_timeout(job["wait"])
        page.screenshot(path=str(out / fold_name))
        viewport = page.viewport_size
        height = int(page.evaluate("() => document.documentElement.scrollHeight"))
        page.screenshot(path=str(out / full_name), full_page=True,
                        clip={"x": 0, "y": 0, "width": viewport["width"], "height": min(height, MAX_HEIGHT)})
        result.update({"file": full_name, "fold_file": fold_name, "page_height": height,
                       "cut_at": MAX_HEIGHT if height > MAX_HEIGHT else None, "viewport": viewport})
        if theme["state"] != "ok":
            result["state"] = "wrong_theme"
    except Exception as exc:
        result["state"] = "error"
        result["error"] = f"{type(exc).__name__}: {exc}"[:500]
    finally:
        context.close()
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Bildpaare zweier Themes je Beispielseite")
    parser.add_argument("--pages", required=True, help="pages.json")
    parser.add_argument("--a", required=True, help="Theme-ID der linken Seite, meist Live")
    parser.add_argument("--b", required=True, help="Theme-ID der rechten Seite, meist der Entwurf")
    parser.add_argument("--out", required=True, help="Zielordner, im Kundenordner")
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
    themes = {"a": args.a, "b": args.b}
    jobs = [{"page": page, "page_id": page["id"], "device": device, "side": side, "themes": themes,
             "base_url": pages["base_url"], "out": out, "wait": args.wait, "timeout": args.timeout,
             "locale": args.locale}
            for page in pages["pages"] for device in devices for side in ("a", "b")]
    results = common.run_jobs(jobs, shoot, args.parallel)
    data = {**build_pairs(jobs, results, themes), "base_url": pages["base_url"], "captured_at": common.now()}
    common.write_json(out / "pairs.json", data)
    shots = [p.get(side) or {} for p in data["pairs"] for side in ("a", "b")]
    bad = [s for s in shots if s.get("state") != "ok"]
    print(json.dumps({"out": str(out / "pairs.json"), "pairs": len(data["pairs"]), "images": len(shots),
                      "wrong_theme": sum(1 for s in bad if s.get("state") == "wrong_theme"),
                      "errors": sum(1 for s in bad if s.get("state") == "error")}, ensure_ascii=False))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
