"""Belegbilder für den Report: Aufnahmen mit abgelehntem Cookie-Dialog.

shoot.sh nimmt eine Seite so auf, wie ein Erstbesucher sie sieht, also mit
Cookie-Dialog. Auf dem Handy verdeckt der bei deutschen Shops oft die ganze
Seite, und als Beleg für einen Befund taugt das Bild dann nicht. Belegt am
01.10.2026 in einem Lauf: auf allen sieben Handy-Aufnahmen lag der Dialog über
Header, Preis und Kaufbutton. Dieses Skript lehnt den Dialog auf der ersten
Seite ab, behält die Entscheidung im selben Browser-Kontext und nimmt danach
alle Seiten auf. "Ablehnen" ist die Wahl, die am wenigsten Daten freigibt.

Aufruf (braucht ein Python mit dem Paket playwright, siehe audit-light Stufe 4):

  python3 shoot_declined.py --target <ordner> --url start=https://shop.example/ \
      --url product=https://shop.example/products/x [--strip product=1700]

Je Seite entstehen <name>-mobil-ohne-cookie.png, <name>-desktop-ohne-cookie.png
und die Ganzseiten-Fassungen *-voll.png. --strip <name>=<höhe> schneidet die
Handy-Aufnahme dieser Seite auf die ersten <höhe> CSS-Pixel zu, als
<name>-mobil-strip.png: das ist die Vorlage für den Belegtyp "phone" im Report
und hält die PDF klein. Am Ende steht eine Zeile IMAGES_JSON: [...] wie bei
shoot.sh.
"""
import argparse
import datetime
import json
import sys
from pathlib import Path

from consent import DECLINED, DECLINE_SELECTORS, decline

def parse_pairs(values, cast=str):
    out = {}
    for value in values or []:
        name, sep, rest = value.partition("=")
        if not sep or not name or not rest:
            sys.exit(f"Erwartet name=wert, bekommen: {value}")
        out[name] = cast(rest)
    return out


def main():
    parser = argparse.ArgumentParser(description="Aufnahmen mit abgelehntem Cookie-Dialog")
    parser.add_argument("--target", required=True)
    parser.add_argument("--url", action="append", required=True, help="name=https://...")
    parser.add_argument("--strip", action="append", help="name=höhe in CSS-Pixeln")
    parser.add_argument("--wait", type=int, default=3500, help="Wartezeit je Seite in ms")
    args = parser.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("Das Paket playwright fehlt in diesem Python. Ein Python mit playwright nehmen, "
                 "oder: pip install playwright && playwright install chromium")

    pages = parse_pairs(args.url)
    strips = parse_pairs(args.strip, int)
    target = Path(args.target)
    target.mkdir(parents=True, exist_ok=True)
    images = []

    with sync_playwright() as p:
        browser = p.chromium.launch()
        devices = [
            # Pixeldichte 2 statt 3: scharf genug für den Report, ein Drittel kleiner.
            ("mobil", {**p.devices["iPhone 13"], "device_scale_factor": 2}),
            ("desktop", {"viewport": {"width": 1440, "height": 900}}),
        ]
        for device, options in devices:
            context = browser.new_context(**options, locale="de-DE")
            page = context.new_page()
            declined = None
            for index, (name, url) in enumerate(pages.items()):
                page.goto(url, wait_until="load", timeout=60000)
                if index == 0:
                    # Auch über die zweite Ebene des Dialogs (consent.py).
                    state, how = decline(page)
                    declined = how if state == DECLINED else None
                    if not declined:
                        print(f"Kein Ablehnen-Knopf gefunden auf {url} ({device}), Aufnahme mit Dialog.",
                              file=sys.stderr)
                page.wait_for_timeout(args.wait)
                # Newsletter- und Rabatt-Popups schließen sich mit Escape, ein offener bleibt
                # sonst über dem Kaufbereich liegen.
                page.keyboard.press("Escape")
                page.wait_for_timeout(400)
                # Taucht der Dialog auf einer Folgeseite wieder auf, wird er dort erneut abgelehnt.
                for selector in DECLINE_SELECTORS:
                    again = page.locator(f"{selector} >> visible=true")
                    if again.count():
                        again.first.click(timeout=5000)
                        page.wait_for_timeout(1200)
                        break
                shots = [("ohne-cookie", {"full_page": False}), ("ohne-cookie-voll", {"full_page": True})]
                if device == "mobil" and name in strips:
                    width = page.viewport_size["width"]
                    shots.append(("strip", {"full_page": True,
                                            "clip": {"x": 0, "y": 0, "width": width, "height": strips[name]}}))
                for suffix, shot in shots:
                    path = target / f"{name}-{device}-{suffix}.png"
                    page.screenshot(path=str(path), **shot)
                    images.append({
                        "page_type": name, "device": device, "variant": suffix,
                        "consent": "declined" if declined else "dialog",
                        "viewport_width": page.viewport_size["width"],
                        "source_url": url, "path": str(path),
                        "captured_at": datetime.datetime.now().isoformat(timespec="seconds"),
                    })
            context.close()
        browser.close()

    print("IMAGES_JSON: " + json.dumps(images, ensure_ascii=False))


if __name__ == "__main__":
    main()
