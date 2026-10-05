"""Belegbilder zu Befunden aufnehmen, aus den Aufnahme-Aufträgen im Lauf.

Vertrag: `reference/finding-format.md`, Abschnitt "Aufnahme-Auftrag capture".
Im vollen Audit schreibt ein Agent in einen Beleg-Baustein (`image` oder
`phone`) nur, was zu sehen sein soll, samt `alt` und `title`. Dieses Skript
öffnet die Seite, lehnt den Cookie-Dialog ab (auch über die zweite Ebene,
`consent.py`), misst die Elemente im Browser, schneidet aus, rechnet
Markierungen in Prozent um und schreibt das Ergebnis neben den Auftrag. Bis zum
02.10.2026 entstanden Ausschnitte und Markierungen von Hand, mit Koordinaten als
Zahlen im JSON.

**Der Auftrag bleibt stehen.** Die Bilder liegen nur im Lauf und im Bucket,
nicht in Git; ohne den Auftrag ließe sich keins neu aufnehmen. `--refresh` nimmt
alle neu auf, sonst nur die offenen.

**Ein Bild entsteht nur, wenn es den beschriebenen Zustand zeigt.** Trifft ein
Ziel kein oder mehr als ein sichtbares Element, oder ist etwas aus `absent` zu
sehen, bleibt der Auftrag offen, und das Skript endet mit Fehlercode 1. Ein Lauf
mit offenem Auftrag wird nicht hochgeladen (`publish`).

Aufruf (playwright 1.58.0 passt zu den Browsern im Playwright-Cache):

  uv run --quiet --with playwright==1.58.0 python shoot_proof.py \
    --run <workspace>/reporting/runs/<run-id> [--refresh] [--only CRO-01]
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
import tempfile
from pathlib import Path

#: Rand um einen Ausschnitt und um eine Markierung, in CSS-Pixeln.
CROP_PADDING = 24
RING_PADDING = 6
#: Unter der tiefsten Marke zeigt der Handy-Ausschnitt noch so viel von der Seite.
BELOW_LAST_MARKER = 100
#: Breiter wird kein Belegbild (Spec ptai-portal 2026-10-02, Abschnitt 19).
MAX_IMAGE_WIDTH = 1600
#: Höher wird die ganze Seite für die große Ansicht nicht.
MAX_FULL_HEIGHT = 4000
DEVICE_SCALE = 2
JPEG_QUALITY = 82


# ---------------------------------------------------------------------------
# Reine Hilfen, ohne Browser
# ---------------------------------------------------------------------------

def proof_columns(proof) -> list:
    if isinstance(proof, list):
        return proof
    if isinstance(proof, dict):
        return proof.get("columns") or []
    return []


def capture_blocks(finding: dict) -> list[tuple[int, dict]]:
    """Die Bild-Bausteine eines Befunds mit Auftrag, nummeriert ab 1 in ihrer Reihenfolge."""
    blocks = []
    for column in proof_columns(finding.get("proof")):
        for block in column.get("blocks") or []:
            if block.get("type") in ("image", "phone") and isinstance(block.get("capture"), dict):
                blocks.append(block)
    return list(enumerate(blocks, start=1))


def is_open(block: dict, refresh: bool = False) -> bool:
    return refresh or not block.get("src")


def device_of(block: dict) -> str:
    if block.get("type") == "phone":
        return "mobil"
    return block["capture"].get("device") or "desktop"


def file_name(finding_id: str, number: int, device: str, full: bool = False) -> str:
    """Fester Name je Befund, Bild und Gerät, damit ein zweiter Lauf dieselbe Datei trifft."""
    return f"proof/{finding_id.lower()}-{number}-{device}{'-voll' if full else ''}.jpg"


def union(boxes: list[dict]) -> dict:
    left = min(b["x"] for b in boxes)
    top = min(b["y"] for b in boxes)
    right = max(b["x"] + b["width"] for b in boxes)
    bottom = max(b["y"] + b["height"] for b in boxes)
    return {"x": left, "y": top, "width": right - left, "height": bottom - top}


def pad_clip(box: dict, viewport: dict, padding: int = CROP_PADDING) -> dict:
    """Der Ausschnitt um `box` mit Rand, innerhalb des Bildschirms, in ganzen Pixeln."""
    left = max(0, int(box["x"] - padding))
    top = max(0, int(box["y"] - padding))
    right = min(viewport["width"], int(box["x"] + box["width"] + padding + 0.999))
    bottom = min(viewport["height"], int(box["y"] + box["height"] + padding + 0.999))
    return {"x": left, "y": top, "width": right - left, "height": bottom - top}


def ring_percent(box: dict, clip: dict, padding: int = RING_PADDING) -> dict:
    """Eine Markierung in Prozent des Ausschnitts, mit Rand und innerhalb von 0 bis 100."""
    left = max(0.0, (box["x"] - padding - clip["x"]) / clip["width"] * 100)
    top = max(0.0, (box["y"] - padding - clip["y"]) / clip["height"] * 100)
    right = min(100.0, (box["x"] + box["width"] + padding - clip["x"]) / clip["width"] * 100)
    bottom = min(100.0, (box["y"] + box["height"] + padding - clip["y"]) / clip["height"] * 100)
    return {"left": round(left, 1), "top": round(top, 1),
            "width": round(right - left, 1), "height": round(bottom - top, 1)}


def strip_height(fold: int, marker_bottoms: list[float], page_height: int,
                 below: int = BELOW_LAST_MARKER) -> int:
    """Wie weit der Handy-Ausschnitt reicht: bis knapp unter die tiefste Marke."""
    lowest = max([fold, *marker_bottoms])
    return int(min(page_height, lowest + below))


def scale_for(width_css: float) -> str:
    """`device` (doppelte Dichte), solange das Bild nicht breiter als `MAX_IMAGE_WIDTH` wird."""
    return "device" if width_css * DEVICE_SCALE <= MAX_IMAGE_WIDTH else "css"


def apply_result(block: dict, result: dict) -> dict:
    """Der Baustein mit Ergebnis; der Auftrag, `alt` und `title` bleiben, wie sie sind."""
    updated = {**block, **result}
    if block.get("type") == "image":
        updated.pop("fold", None)
        updated.pop("markers", None)
    return updated


def write_json_atomic(path: Path, data) -> None:
    """Schreibt erst eine Nachbardatei und tauscht sie dann aus: kein halbes JSON bei einem Abbruch."""
    handle, temp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    with os.fdopen(handle, "w", encoding="utf-8") as out:
        json.dump(data, out, ensure_ascii=False, indent=2)
        out.write("\n")
    os.replace(temp, path)


class CaptureError(Exception):
    """Ein Auftrag ließ sich nicht erfüllen; die Nachricht sagt, warum."""


# ---------------------------------------------------------------------------
# Browser
# ---------------------------------------------------------------------------

def target_of(page, target: dict, what: str, control: bool = False):
    """Das eine sichtbare Element zu einem Ziel `{text}` oder `{selector}`.

    `control` nimmt bei einem Text den umgebenden Knopf oder Link, wenn es einen
    gibt: eine Markierung soll den ganzen Knopf umfassen, nicht nur seine
    Beschriftung, und eine Marke auf seiner Oberkante sitzen.
    """
    if not isinstance(target, dict) or not (target.get("text") or target.get("selector")):
        raise CaptureError(f"{what}: Ziel braucht text oder selector")
    if target.get("selector"):
        candidates = [page.locator(target["selector"])]
        label = target["selector"]
    else:
        candidates = [page.get_by_text(target["text"], exact=True), page.get_by_text(target["text"])]
        label = f'"{target["text"]}"'
    for locator in candidates:
        visible = [locator.nth(i) for i in range(locator.count()) if locator.nth(i).is_visible()]
        if len(visible) == 1:
            element = visible[0]
            if control and not target.get("selector"):
                around = element.locator("xpath=ancestor-or-self::*[self::button or self::a or @role='button']")
                if around.count() and around.last.is_visible():
                    return around.last
            return element
        if len(visible) > 1:
            raise CaptureError(f"{what}: {label} trifft {len(visible)} sichtbare Elemente, genau eins nötig")
    raise CaptureError(f"{what}: {label} ist nicht zu sehen")


def visible_count(page, target: dict) -> int:
    if target.get("selector"):
        locator = page.locator(target["selector"])
    else:
        locator = page.get_by_text(target.get("text", ""), exact=True)
    return sum(1 for i in range(locator.count()) if locator.nth(i).is_visible())


def open_page(browser, playwright, device: str, url: str, consent: str, wait_ms: int):
    from consent import DECLINED, NO_DIALOG, decline

    if device == "mobil":
        options = {**playwright.devices["iPhone 13"], "device_scale_factor": DEVICE_SCALE}
    else:
        options = {"viewport": {"width": 1440, "height": 900}, "device_scale_factor": DEVICE_SCALE}
    context = browser.new_context(**options, locale="de-DE")
    page = context.new_page()
    page.goto(url, wait_until="load", timeout=60000)
    page.wait_for_timeout(wait_ms)
    if consent == "declined":
        state, _ = decline(page)
        if state not in (DECLINED, NO_DIALOG):
            context.close()
            raise CaptureError("der Cookie-Dialog ließ sich nicht ablehnen, auch nicht über die zweite Ebene")
        # Newsletter- und Rabatt-Popups schließen sich mit Escape.
        page.keyboard.press("Escape")
        page.wait_for_timeout(400)
    return context, page


def shoot_image(page, capture: dict, run_dir: Path, name: str) -> dict:
    viewport = page.viewport_size
    rings = [target_of(page, ring, "Markierung", control=True) for ring in capture.get("rings") or []]
    if capture.get("crop"):
        crop = target_of(page, capture["crop"], "Ausschnitt")
        crop.scroll_into_view_if_needed()
        page.wait_for_timeout(300)
        boxes = [crop.bounding_box(), *[ring.bounding_box() for ring in rings]]
        clip = pad_clip(union(boxes), viewport)
        if clip["height"] <= 0 or clip["width"] <= 0:
            raise CaptureError("Ausschnitt liegt außerhalb des Bildschirms")
        ring_boxes = boxes[1:]
    else:
        clip = {"x": 0, "y": 0, "width": viewport["width"], "height": viewport["height"]}
        ring_boxes = [ring.bounding_box() for ring in rings]
    scale = scale_for(clip["width"])
    page.screenshot(path=str(run_dir / name), type="jpeg", quality=JPEG_QUALITY, clip=clip, scale=scale)
    factor = DEVICE_SCALE if scale == "device" else 1
    return {
        "src": name,
        "width": int(clip["width"] * factor),
        "height": int(clip["height"] * factor),
        "rings": [ring_percent(box, clip) for box in ring_boxes],
    }


def shoot_phone(page, capture: dict, run_dir: Path, name: str, full_name: str) -> dict:
    page.evaluate("window.scrollTo(0, 0)")
    page.wait_for_timeout(300)
    viewport = page.viewport_size
    page_height = int(page.evaluate("document.documentElement.scrollHeight"))
    markers, bottoms = [], []
    for marker in capture.get("markers") or []:
        box = target_of(page, (marker or {}).get("target") or {}, "Marke", control=True).bounding_box()
        y = int(box["y"])
        markers.append({"y": y, "label": f"{y} px", "text": marker.get("text") or ""})
        bottoms.append(box["y"] + box["height"])
    fold = int(viewport["height"])
    height = strip_height(fold, bottoms, page_height)
    page.screenshot(path=str(run_dir / name), type="jpeg", quality=JPEG_QUALITY, full_page=True,
                    clip={"x": 0, "y": 0, "width": viewport["width"], "height": height}, scale="device")
    full_height = min(page_height, MAX_FULL_HEIGHT)
    page.screenshot(path=str(run_dir / full_name), type="jpeg", quality=JPEG_QUALITY, full_page=True,
                    clip={"x": 0, "y": 0, "width": viewport["width"], "height": full_height}, scale="css")
    return {
        "src": name,
        "full_src": full_name,
        "width": int(viewport["width"]),
        "height": height,
        "fold": fold,
        "markers": [{"y": fold, "label": f"{fold} px", "text": "Ende der Erstansicht"}, *markers],
    }


def capture_block(browser, playwright, block: dict, finding_id: str, number: int,
                  run_dir: Path, wait_ms: int) -> dict:
    capture = block["capture"]
    url = capture.get("url")
    if not isinstance(url, str) or not url.startswith("https://"):
        raise CaptureError("capture.url ist keine https-Adresse")
    if not block.get("alt") or not block.get("title"):
        raise CaptureError("alt und title gehören in den Auftrag, der Agent schreibt sie")
    device = device_of(block)
    consent = capture.get("consent") or "declined"
    context, page = open_page(browser, playwright, device, url, consent, wait_ms)
    try:
        for target in capture.get("absent") or []:
            if visible_count(page, target):
                what = target.get("text") or target.get("selector")
                raise CaptureError(f"Mangel scheint behoben: {what!r} ist zu sehen. Befund prüfen, kein Bild")
        name = file_name(finding_id, number, device)
        if block["type"] == "phone":
            result = shoot_phone(page, capture, run_dir, name, file_name(finding_id, number, device, full=True))
        else:
            result = shoot_image(page, capture, run_dir, name)
        result.update({
            "device": device,
            "captured_at": datetime.date.today().isoformat(),
            "page_url": page.url,
        })
        return apply_result(block, result)
    finally:
        context.close()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Belegbilder aus den Aufnahme-Aufträgen eines Laufs")
    parser.add_argument("--run", required=True, help="der Lauf-Ordner, reporting/runs/<run-id>")
    parser.add_argument("--refresh", action="store_true", help="auch erledigte Aufträge neu aufnehmen")
    parser.add_argument("--only", action="append", help="nur diese Befunde, Kennung, wiederholbar")
    parser.add_argument("--wait", type=int, default=3500, help="Wartezeit je Seite in ms")
    args = parser.parse_args(argv)

    run_dir = Path(args.run)
    findings_dir = run_dir / "findings"
    if not findings_dir.is_dir():
        print(f"{run_dir} hat keinen Ordner findings/", file=sys.stderr)
        return 2
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Das Paket playwright fehlt in diesem Python. Ein Python mit playwright nehmen, "
              "oder: pip install playwright && playwright install chromium", file=sys.stderr)
        return 2

    (run_dir / "proof").mkdir(exist_ok=True)
    only = {item.upper() for item in args.only or []}
    done, errors = 0, []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        for path in sorted(findings_dir.glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            changed = False
            for finding in data.get("findings") or []:
                finding_id = finding.get("id") or "ohne-kennung"
                if only and finding_id.upper() not in only:
                    continue
                for number, block in capture_blocks(finding):
                    if not is_open(block, args.refresh):
                        continue
                    try:
                        updated = capture_block(browser, playwright, block, finding_id, number, run_dir, args.wait)
                    except CaptureError as exc:
                        errors.append(f"{path.name} {finding_id} Bild {number}: {exc}")
                        continue
                    except Exception as exc:  # Netz, Zeitlimit, Browser
                        errors.append(f"{path.name} {finding_id} Bild {number}: {type(exc).__name__}: {exc}")
                        continue
                    block.clear()
                    block.update(updated)
                    changed = True
                    done += 1
                    print(f"aufgenommen: {updated['src']}")
            if changed:
                write_json_atomic(path, data)
        browser.close()

    for line in errors:
        print(f"offen: {line}", file=sys.stderr)
    print(f"{done} Bild(er) aufgenommen, {len(errors)} Auftrag/Aufträge offen.")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
