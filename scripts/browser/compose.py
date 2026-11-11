"""Vergleichsseite aus den Bildpaaren von `shoot_pair.py`: je Seite und Breite links A, rechts B.

Aufruf:

  python3 scripts/browser/compose.py --pairs <ordner-mit-pairs.json> --out <compare.html> [--title <text>]

Nur Standardbibliothek. Die Seite verweist relativ auf die Bilder, sie liegt
deshalb am besten neben dem Bildordner im Kundenordner und wandert mit ihm.

Gezeigt wird je Paar die ganze Seite, alt links, neu rechts, beide in derselben
Breite, damit Abschnitte auf gleicher Höhe beginnen; die Erstansicht ist verlinkt.
Bis 11.11.2026 zeigte die Seite nur die Erstansicht, und Fehler weiter unten
(Newsletter, Footer, schmale Inhaltsseiten) fielen niemandem auf. Oben stehen die
Referenz (links das veröffentlichte Theme?) und die Abdeckung. Ein Bild mit
falschem Theme oder Fehler trägt eine deutliche Markierung, damit niemand einen
Entwurf mit dem Live-Shop vergleicht, ohne es zu merken.

Exit 0 geschrieben, 1 geschrieben, aber mindestens ein Bild ungültig oder
fehlend oder die Referenz ist nicht das veröffentlichte Theme, 2 Fehler (kein
`pairs.json`).
"""
from __future__ import annotations

import argparse
import html
import json
import os
import sys
from pathlib import Path

DEVICE_LABEL = {"desktop": "Rechner, 1440 px (Chromium)", "mobile": "Handy, 390 px (WebKit, iPhone)"}
SIDE_LABEL = {"a": "veröffentlicht", "b": "Entwurf"}
STATE_LABEL = {"ok": None, "wrong_theme": "Falsches Theme", "error": "Fehler", "incomplete": "Bild unvollständig"}

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
.status { background: var(--card); border-radius: 8px; padding: 12px 16px; margin: 0 0 24px; }
.status p { margin: 0 0 4px; }
.status ul { margin: 4px 0 0; padding-left: 20px; }
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


def figure(side: str, shot: dict | None, theme_id: str | None, pairs_dir: Path, out_dir: Path,
           side_label: str | None = None) -> str:
    label = (f"{side.upper()} · {html.escape(side_label or SIDE_LABEL[side])} · "
             f"Theme {html.escape(str(theme_id or '?'))}")
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
    full = relative_src(shot.get("file") or shot["fold_file"], pairs_dir, out_dir)
    fold = relative_src(shot.get("fold_file") or shot["file"], pairs_dir, out_dir)
    both = shot.get("fold_file") and shot.get("file")
    fold_link = f' · <a href="{html.escape(fold)}">Erstansicht</a>' if both else ""
    cut = " · bei der Höchsthöhe abgeschnitten" if shot.get("cut_at") else ""
    if not shot.get("file"):
        cut += " · nur Erstansicht"
    return (f'<figure><figcaption>{label}{flag_html}{link}{fold_link}{cut}{reason_html}</figcaption>'
            f'<a href="{html.escape(full)}" title="Bild in voller Größe"><img src="{html.escape(full)}" '
            f'loading="lazy" alt="{side.upper()}, ganze Seite"></a></figure>')


def status_block(data: dict) -> str:
    """Referenz und Abdeckung über den Paaren; fehlen beide (älteres pairs.json), nichts."""
    reference, cover = data.get("reference"), data.get("coverage")
    if not reference and not cover:
        return ""
    lines = []
    if reference:
        if reference.get("ok") and reference.get("published"):
            lines.append(f"<p>Links das veröffentlichte Theme {html.escape(str(reference.get('theme_id')))}, "
                         "belegt durch den Theme-Nachweis jeder Seite.</p>")
        elif reference.get("ok"):
            lines.append(f"<p>Links Theme {html.escape(str(reference.get('theme_id')))}, gleich live_theme_id der "
                         "Config; die Seiten belegen keine Rolle.</p>")
        for text in reference.get("problems") or []:
            lines.append(f'<p><span class="flag">Referenz falsch</span> {html.escape(str(text))}</p>')
        for text in reference.get("warnings") or []:
            lines.append(f'<p><span class="flag">Hinweis</span> {html.escape(str(text))}</p>')
    if cover:
        lines.append(f"<p>{cover.get('valid')} von {cover.get('expected')} Aufnahmen gültig, "
                     f"{cover.get('pages')} Seiten, Rechner 1440 px und Handy 390 px.</p>")
        missing = cover.get("missing") or []
        if missing:
            items = "".join(f"<li>{html.escape(str(m.get('page_id')))}, "
                            f"{html.escape(DEVICE_LABEL.get(m.get('device'), str(m.get('device'))))}, "
                            f"{html.escape(str(m.get('side', '')).upper())}: {html.escape(str(m.get('reason')))}</li>"
                            for m in missing[:30])
            more = f"<li>und {len(missing) - 30} weitere</li>" if len(missing) > 30 else ""
            lines.append(f"<ul>{items}{more}</ul>")
    return f'<div class="status">{"".join(lines)}</div>'


def render(data: dict, pairs_dir: Path, out_dir: Path, title: str | None = None) -> str:
    """Die Vergleichsseite als HTML-Text."""
    themes = data.get("themes") or {}
    title = title or "Theme-Vergleich"
    reference = data.get("reference") or {}
    # "veröffentlicht" nur mit Beleg; ein pairs.json vor 11.11.2026 hat keinen.
    a_label = ("veröffentlicht" if reference.get("published") else "Referenz nicht belegt") if reference \
        else "Referenz"
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
            f'{figure("a", pair.get("a"), themes.get("a"), pairs_dir, out_dir, a_label)}'
            f'{figure("b", pair.get("b"), themes.get("b"), pairs_dir, out_dir)}</div>')
    body = "".join(f"<section>{heads[pid]}{''.join(parts)}</section>" for pid, parts in sections.items())
    meta = (f'A: Theme {html.escape(str(themes.get("a") or "?"))} · B: Theme {html.escape(str(themes.get("b") or "?"))}'
            f' · aufgenommen {html.escape(str(data.get("captured_at") or ""))}')
    return (f'<!doctype html>\n<html lang="de"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<title>{html.escape(title)}</title><style>{STYLE}</style></head>'
            f'<body><main><h1>{html.escape(title)}</h1><p class="meta">{meta}</p>{status_block(data)}{body}'
            f'</main></body></html>\n')


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
    reference_ok = (data.get("reference") or {}).get("ok", True)
    print(json.dumps({"out": str(out), "pairs": len(data["pairs"]), "invalid_images": bad,
                      "reference_ok": reference_ok}, ensure_ascii=False))
    return 1 if bad or not reference_ok else 0


if __name__ == "__main__":
    sys.exit(main())
