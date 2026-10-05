#!/usr/bin/env python3
"""Gerenderte Gegenprobe der strukturierten Daten für wenige Seiten.

Aufruf:
  render_check.py --crawl reporting/data/<run-id>/crawl.json --url <adresse> [--url ...]

Warum es das gibt: `crawl.py` liest statisches HTML. JSON-LD, das eine App
oder das Theme erst per JavaScript einfügt (typisch bei Bewertungs-Apps),
fehlt dort. Ohne Gegenprobe wird aus "im statischen HTML nicht gefunden"
ein Befund "fehlt", der im Browser nicht stimmt. Kriterium
`tec.rendered-check` im Agent `audit-seo-technical`.

Je Adresse ein Aufruf der Headless Shell aus `scripts/lib/find_chrome.sh`
mit `--dump-dom`, das gerenderte DOM läuft durch dasselbe `parse_page` wie
der Crawl. Ausgabe ist JSON auf stdout, je Adresse der statische und der
gerenderte Stand plus ein Urteil:

- `same`: gerendert steht dasselbe wie statisch
- `only_rendered`: Typen oder Produktfelder erscheinen erst nach JavaScript
- `only_static`: statisch da, gerendert weg (selten, meist ein Theme-Fehler)
- `render_failed`: kein brauchbares DOM, dann ist nichts gegengeprüft

Höchstens zehn Adressen je Aufruf: das ist eine Stichprobe je Seitentyp,
kein zweiter Crawl.

Nur Standardbibliothek.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import crawl  # noqa: E402

PLUGIN_ROOT = Path(__file__).resolve().parents[3]
MAX_URLS = 10
RENDER_TIMEOUT = 60


def find_browser() -> str | None:
    """Die Headless Shell über dieselbe Suche wie Screenshots und PDF."""
    script = PLUGIN_ROOT / "scripts" / "lib" / "find_chrome.sh"
    result = subprocess.run(["bash", "-c", f'. "{script}"; find_chrome'],
                            capture_output=True, text=True)
    path = result.stdout.strip()
    return path if result.returncode == 0 and path else None


def render(browser: str, url: str) -> str | None:
    """Das gerenderte DOM einer Adresse oder `None`.

    `--virtual-time-budget` lässt Skripte laufen, bevor das DOM geschrieben
    wird; ohne das käme oft der Stand vor den Apps zurück.
    """
    try:
        result = subprocess.run(
            [browser, "--headless", "--disable-gpu", "--virtual-time-budget=8000",
             "--dump-dom", url],
            capture_output=True, text=True, timeout=RENDER_TIMEOUT)
    except (subprocess.TimeoutExpired, OSError):
        return None
    dom = result.stdout
    # Chromes eigene Fehlerseite trägt diese Markierung (siehe shoot.sh).
    if result.returncode != 0 or not dom.strip() or "main-frame-error" in dom:
        return None
    return dom


def compare(url: str, static: dict | None, rendered_html: str | None) -> dict:
    """Statischer Crawl-Eintrag gegen das gerenderte DOM, als eine Zeile."""
    static = static or {}
    entry = {
        "url": url,
        "static_schema_types": static.get("schema_types"),
        "static_markup": static.get("markup"),
    }
    if rendered_html is None:
        return {**entry, "verdict": "render_failed"}
    parsed = crawl.parse_page(rendered_html, url)
    entry.update(rendered_schema_types=parsed["schema_types"], rendered_markup=parsed["markup"])

    before = set(static.get("schema_types") or [])
    after = set(parsed["schema_types"])
    flags_before = {k for k, _ in in_true((static.get("markup") or {}).get("product"))}
    flags_after = {k for k, _ in in_true(parsed["markup"].get("product"))}
    if after - before or flags_after - flags_before:
        verdict = "only_rendered"
    elif before - after or flags_before - flags_after:
        verdict = "only_static"
    else:
        verdict = "same"
    return {**entry, "verdict": verdict}


def in_true(product: dict | None):
    """Die Felder einer Produktzeile, die als vorhanden gelten."""
    for key, value in (product or {}).items():
        if key != "count" and value not in (None, False):
            yield key, value


def main() -> int:
    parser = argparse.ArgumentParser(description="Gerenderte Gegenprobe der strukturierten Daten.")
    parser.add_argument("--crawl", required=True, help="reporting/data/<run-id>/crawl.json")
    parser.add_argument("--url", action="append", required=True,
                        help=f"zu prüfende Adresse, höchstens {MAX_URLS}")
    args = parser.parse_args()
    if len(args.url) > MAX_URLS:
        print(f"Fehler: höchstens {MAX_URLS} Adressen je Aufruf, das ist eine Stichprobe.",
              file=sys.stderr)
        return 2

    pages = json.loads(Path(args.crawl).read_text(encoding="utf-8")).get("pages") or []
    by_url = {p.get("url"): p for p in pages}
    browser = find_browser()
    if browser is None:
        print("Fehler: kein headless Browser gefunden. Installieren: npx playwright install "
              "chromium-headless-shell", file=sys.stderr)
        return 1

    rows = [compare(url, by_url.get(url), render(browser, url)) for url in args.url]
    print(json.dumps({"checked": len(rows), "rows": rows}, ensure_ascii=False, indent=2))
    return sum(1 for row in rows if row["verdict"] == "render_failed")


if __name__ == "__main__":
    sys.exit(main())
