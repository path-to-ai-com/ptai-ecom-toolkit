"""Vergleichsseite aus den Bildpaaren von `shoot_pair.py`: je Seite und Gerät links A, rechts B.

Aufruf:

  python3 scripts/browser/compose.py --pairs <ordner-mit-pairs.json> --out <compare.html> [--title <text>]

Nur Standardbibliothek. Die Seite verweist relativ auf die Bilder, sie liegt
deshalb am besten neben dem Bildordner im Kundenordner und wandert mit ihm.
Gezeigt wird je Paar die Erstansicht; ein Klick öffnet die ganze Seite. Ein Bild
mit falschem Theme oder Fehler trägt eine deutliche Markierung, damit niemand
einen Entwurf mit dem Live-Shop vergleicht, ohne es zu merken.

Exit 0 geschrieben, 1 geschrieben, aber mindestens ein Bild ungültig oder
fehlend, 2 Fehler (kein `pairs.json`).
"""
from __future__ import annotations

import argparse
import html
import json
import os
import sys
from pathlib import Path

DEVICE_LABEL = {"desktop": "Rechner (Chromium)", "mobile": "iPhone (WebKit)"}
STATE_LABEL = {"ok": None, "wrong_theme": "Falsches Theme", "error": "Fehler"}

STYLE = """
:root { --bg: #ffffff; --fg: #1d1d1f; --muted: #6e6e73; --line: #e5e5ea; --warn-bg: #fff4e5; --warn: #9a4b00;
        --card: #f7f7f8; }
@media (prefers-color-scheme: dark) {
  :root { --bg: #141416; --fg: #f2f2f4; --muted: #a1a1a8; --line: #2c2c31; --warn-bg: #3a2610; --warn: #ffb35c;
          --card: #1d1d21; }
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--fg); font: 15px/1.5 system-ui, -apple-system, sans-serif; }
main { max-width: 1280px; margin: 0 auto; padding: 24px 16px 64px; }
h1 { font-size: 24px; margin: 0 0 4px; }
.meta { color: var(--muted); margin: 0 0 24px; }
section { border-top: 1px solid var(--line); padding: 24px 0; }
h2 { font-size: 18px; margin: 0 0 4px; }
h3 { font-size: 14px; color: var(--muted); font-weight: 600; margin: 16px 0 8px; }
.pair { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.pair.mobile { grid-template-columns: repeat(2, minmax(0, 390px)); }
figure { margin: 0; background: var(--card); border-radius: 8px; padding: 8px; }
figcaption { font-size: 13px; color: var(--muted); margin-bottom: 6px; overflow-wrap: anywhere; }
figure img { width: 100%; height: auto; display: block; border-radius: 4px; }
.flag { display: inline-block; background: var(--warn-bg); color: var(--warn); font-weight: 600;
        border-radius: 4px; padding: 1px 6px; margin-left: 6px; }
.missing { padding: 32px 8px; text-align: center; color: var(--muted); }
a { color: inherit; }
@media (max-width: 640px) { .pair, .pair.mobile { grid-template-columns: 1fr; } }
"""


class PairsError(Exception):
    """Kein lesbares `pairs.json` im angegebenen Ordner."""


def load_pairs(pairs_dir: Path) -> dict:
    path = pairs_dir / "pairs.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PairsError(f"{path}: {exc}") from exc
    if not isinstance(data.get("pairs"), list):
        raise PairsError(f"{path}: kein Feld pairs")
    return data


def relative_src(file: str, pairs_dir: Path, out_dir: Path) -> str:
    """Pfad eines Bilds relativ zur Vergleichsseite, mit Schrägstrichen."""
    rel = os.path.relpath(pairs_dir / file, out_dir)
    return Path(rel).as_posix()


def figure(side: str, shot: dict | None, theme_id: str | None, pairs_dir: Path, out_dir: Path) -> str:
    label = f"{side.upper()} · Theme {html.escape(str(theme_id or '?'))}"
    if not shot:
        return f'<figure><figcaption>{label}</figcaption><div class="missing">keine Aufnahme</div></figure>'
    flag = STATE_LABEL.get(shot.get("state"), shot.get("state"))
    flag_html = f'<span class="flag">{html.escape(flag)}</span>' if flag else ""
    reason = (shot.get("theme_check") or {}).get("reason") or shot.get("error")
    reason_html = f"<br>{html.escape(str(reason))}" if reason and flag else ""
    link = f' · <a href="{html.escape(shot["url"])}">Seite öffnen</a>' if shot.get("url") else ""
    if not shot.get("fold_file") and not shot.get("file"):
        return (f'<figure><figcaption>{label}{flag_html}{link}{reason_html}</figcaption>'
                f'<div class="missing">kein Bild</div></figure>')
    fold = relative_src(shot.get("fold_file") or shot["file"], pairs_dir, out_dir)
    full = relative_src(shot.get("file") or shot["fold_file"], pairs_dir, out_dir)
    cut = " · bei der Höchsthöhe abgeschnitten" if shot.get("cut_at") else ""
    return (f'<figure><figcaption>{label}{flag_html}{link}{cut}{reason_html}</figcaption>'
            f'<a href="{html.escape(full)}" title="ganze Seite"><img src="{html.escape(fold)}" loading="lazy" '
            f'alt="{side.upper()}, Erstansicht"></a></figure>')


def render(data: dict, pairs_dir: Path, out_dir: Path, title: str | None = None) -> str:
    """Die Vergleichsseite als HTML-Text."""
    themes = data.get("themes") or {}
    title = title or "Theme-Vergleich"
    sections: dict[str, list[str]] = {}
    heads: dict[str, str] = {}
    for pair in data["pairs"]:
        page_id = str(pair.get("page_id"))
        heads.setdefault(page_id, (f'<h2>{html.escape(page_id)}</h2><p class="meta">'
                                   f'{html.escape(str(pair.get("template") or ""))} · '
                                   f'{html.escape(str(pair.get("path") or ""))}</p>'))
        device = pair.get("device") or "desktop"
        sections.setdefault(page_id, []).append(
            f'<h3>{html.escape(DEVICE_LABEL.get(device, device))}</h3>'
            f'<div class="pair {html.escape(device)}">'
            f'{figure("a", pair.get("a"), themes.get("a"), pairs_dir, out_dir)}'
            f'{figure("b", pair.get("b"), themes.get("b"), pairs_dir, out_dir)}</div>')
    body = "".join(f"<section>{heads[pid]}{''.join(parts)}</section>" for pid, parts in sections.items())
    meta = (f'A: Theme {html.escape(str(themes.get("a") or "?"))} · B: Theme {html.escape(str(themes.get("b") or "?"))}'
            f' · aufgenommen {html.escape(str(data.get("captured_at") or ""))}')
    return (f'<!doctype html>\n<html lang="de"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<title>{html.escape(title)}</title><style>{STYLE}</style></head>'
            f'<body><main><h1>{html.escape(title)}</h1><p class="meta">{meta}</p>{body}</main></body></html>\n')


def problems(data: dict) -> int:
    count = 0
    for pair in data["pairs"]:
        for side in ("a", "b"):
            shot = pair.get(side)
            if not shot or shot.get("state") != "ok" or not (shot.get("file") or shot.get("fold_file")):
                count += 1
    return count


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Vergleichsseite aus Bildpaaren")
    parser.add_argument("--pairs", required=True, help="Ordner mit pairs.json aus shoot_pair.py")
    parser.add_argument("--out", required=True, help="Ziel compare.html")
    parser.add_argument("--title", help="Überschrift der Seite")
    args = parser.parse_args(argv)
    pairs_dir = Path(args.pairs)
    try:
        data = load_pairs(pairs_dir)
    except PairsError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 2
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(data, pairs_dir.resolve(), out.parent.resolve(), args.title), encoding="utf-8")
    bad = problems(data)
    print(json.dumps({"out": str(out), "pairs": len(data["pairs"]), "invalid_images": bad}, ensure_ascii=False))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
