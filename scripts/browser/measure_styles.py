"""Gestaltung eines Themes am gerenderten Shop messen: Schrift je Textrolle, Farben, Radien, Breakpoints.

Aufruf:

  uv run --quiet --with playwright==1.58.0 python scripts/browser/measure_styles.py \
    --pages migration/inventory/pages.json --out migration/inventory/design.json \
    [--theme <theme-id>] [--devices desktop,mobile]

Gemessen wird, was eine Besucherin sieht, nicht was in den Einstellungen steht:
je Beispielseite und Gerät die berechneten Stile der sichtbaren Elemente je
Textrolle (`h1` bis `h6`, Fließtext, Preis, Button, Hauptbutton, Navigation,
Link) mit Schriftfamilie, Größe, Gewicht, Zeilenhöhe, Laufweite, Schreibweise und
Farbe; dazu Hintergründe von Seite, Kopf und Fuß, Akzentfarben, Radien von
Buttons, Feldern, Karten und Bildern und die Breakpoints aus den Media Queries
der lesbaren Stylesheets.

Je Rolle steht der häufigste Wert mit Anteil und die nächsten Varianten. Das ist
die Grundlage für die Zuordnung auf die Einstellungen des Ziel-Themes; was dort
nicht abbildbar ist, wird eigener Code oder eine bewusste Abweichung.

Vorschau mit `--theme` über `preview_theme_id` und `pb=0`, mit Theme-Nachweis je
Seite. Exit 0 alles gemessen, 1 mindestens eine Seite falsches Theme oder Fehler,
2 Fehler vor dem ersten Aufruf.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import common  # noqa: E402

ROLES = ("h1", "h2", "h3", "h4", "h5", "h6", "body", "price", "button", "primary_button", "navigation", "link")
MAX_SAMPLES = 40
STYLE_KEYS = ("font_family", "font_size", "font_weight", "line_height", "letter_spacing", "text_transform", "color")

MEASURE_JS = r"""(maxSamples) => {
  const visible = el => {
    const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none' && parseFloat(s.opacity || '1') > 0;
  };
  const text = el => (el.innerText || el.textContent || '').trim();
  const pick = sel => { try { return [...document.querySelectorAll(sel)]; } catch (e) { return []; } };
  const style = el => { const s = getComputedStyle(el); return {
    font_family: s.fontFamily, font_size: s.fontSize, font_weight: s.fontWeight, line_height: s.lineHeight,
    letter_spacing: s.letterSpacing, text_transform: s.textTransform, color: s.color,
    background_color: s.backgroundColor, border_radius: s.borderTopLeftRadius,
    border_color: s.borderTopColor, border_width: s.borderTopWidth, text: text(el).slice(0, 40) }; };
  const money = /(\d[\d.,\s]*\s?(€|EUR|\$|£|CHF|kr))|((€|\$|£)\s?\d)/;
  const selectors = {
    h1: 'h1', h2: 'h2', h3: 'h3', h4: 'h4', h5: 'h5', h6: 'h6',
    body: 'main p, [role=main] p, article p, .rte p',
    price: '[class*=price], [data-price], .money',
    button: 'button, .button, .btn, [type=submit], a[class*=button], a[class*=btn]',
    primary_button: 'form[action*="/cart/add"] [type=submit], [name=add], button[class*=add-to-cart]',
    navigation: 'header nav a, header [role=navigation] a, nav[aria-label] a',
    link: 'main a',
  };
  const roles = {};
  for (const [role, sel] of Object.entries(selectors)) {
    let els = pick(sel).filter(visible).filter(el => text(el).length > 0);
    if (role === 'price') els = els.filter(el => money.test(text(el)) && text(el).length < 40 && !el.querySelector('[class*=price]'));
    if (role === 'body') els = els.filter(el => text(el).length > 30);
    roles[role] = els.slice(0, maxSamples).map(style);
  }
  const first = sel => { const el = pick(sel).find(visible); return el ? getComputedStyle(el) : null; };
  const bg = sel => { const s = first(sel); return s ? s.backgroundColor : null; };
  const radius = sel => pick(sel).filter(visible).slice(0, maxSamples).map(el => getComputedStyle(el).borderTopLeftRadius);
  const media = []; let unreadable = 0;
  const walk = rules => { for (const rule of rules) {
    if (rule.media && rule.media.mediaText) media.push(rule.media.mediaText);
    if (rule.cssRules) { try { walk(rule.cssRules); } catch (e) {} }
  } };
  for (const sheet of document.styleSheets) {
    try { if (sheet.media && sheet.media.mediaText) media.push(sheet.media.mediaText); walk(sheet.cssRules); }
    catch (e) { unreadable += 1; }
  }
  return {
    roles,
    backgrounds: {page: getComputedStyle(document.body).backgroundColor,
                  header: bg('header, .header, [class*=header]'), footer: bg('footer, .footer, [class*=footer]')},
    radii: {button: radius('button, .button, .btn, [type=submit]'),
            input: radius('input[type=text], input[type=email], input[type=search], select, textarea'),
            card: radius('[class*=card]'), image: radius('main img')},
    media, unreadable_sheets: unreadable, sheets: document.styleSheets.length,
    viewport: {width: window.innerWidth, height: window.innerHeight},
  };
}"""


# ---------------------------------------------------------------------------
# Reine Hilfen, ohne Browser
# ---------------------------------------------------------------------------

def normalize_color(value: str | None) -> str | None:
    """`rgb(17, 17, 17)` zu `#111111`; durchsichtig zu `None`, Alpha unter 1 als `#rrggbbaa`."""
    if not value:
        return None
    value = value.strip().lower()
    if value in ("transparent", "none"):
        return None
    if value.startswith("#"):
        return value
    match = re.match(r"rgba?\(\s*([\d.]+)[\s,]+([\d.]+)[\s,]+([\d.]+)(?:\s*[,/]\s*([\d.]+%?))?\s*\)", value)
    if not match:
        return value
    red, green, blue = (max(0, min(255, round(float(match.group(i))))) for i in (1, 2, 3))
    alpha = match.group(4)
    if alpha is not None:
        alpha_value = float(alpha[:-1]) / 100 if alpha.endswith("%") else float(alpha)
        if alpha_value == 0:
            return None
        if alpha_value < 1:
            return f"#{red:02x}{green:02x}{blue:02x}{round(alpha_value * 255):02x}"
    return f"#{red:02x}{green:02x}{blue:02x}"


def is_neutral(color: str | None) -> bool:
    """Grau, Schwarz oder Weiß: die drei Kanäle liegen dicht beieinander."""
    if not color or not color.startswith("#") or len(color) < 7:
        return True
    channels = [int(color[i:i + 2], 16) for i in (1, 3, 5)]
    return max(channels) - min(channels) < 24


def px(value: str | None) -> float | None:
    match = re.match(r"^(-?[\d.]+)px$", (value or "").strip())
    return round(float(match.group(1)), 2) if match else None


def first_family(value: str | None) -> str | None:
    if not value:
        return None
    return value.split(",")[0].strip().strip("\"'") or None


def clean_style(sample: dict) -> dict:
    """Ein gemessener Stil in vergleichbarer Form: Zahlen in px, Farben als Hex, erste Schriftfamilie."""
    size = px(sample.get("font_size"))
    line = px(sample.get("line_height"))
    return {
        "font_family": first_family(sample.get("font_family")),
        "font_size": size,
        "font_weight": str(sample.get("font_weight") or "") or None,
        "line_height": line if line is not None else sample.get("line_height"),
        "line_height_ratio": round(line / size, 2) if line and size else None,
        "letter_spacing": px(sample.get("letter_spacing")) if sample.get("letter_spacing") != "normal" else 0.0,
        "text_transform": sample.get("text_transform") or "none",
        "color": normalize_color(sample.get("color")),
    }


def summarize_role(samples: list[dict]) -> dict:
    """Häufigster Stil einer Rolle mit Anteil und den nächsten Varianten."""
    if not samples:
        return {"samples": 0, "value": None, "share": None, "variants": []}
    cleaned = [clean_style(s) for s in samples]
    keys = [tuple((k, c.get(k)) for k in ("font_family", "font_size", "font_weight", "line_height",
                                          "letter_spacing", "text_transform", "color")) for c in cleaned]
    counts = Counter(keys)
    (top, top_count), *rest = counts.most_common(4)
    value = dict(top)
    value["line_height_ratio"] = next(c["line_height_ratio"] for c, k in zip(cleaned, keys) if k == top)
    out = {"samples": len(samples), "value": value, "share": round(top_count / len(samples), 2),
           "variants": [{**dict(key), "count": count} for key, count in rest]}
    backgrounds = Counter(normalize_color(s.get("background_color")) for s in samples)
    backgrounds.pop(None, None)
    radii = Counter(s.get("border_radius") for s in samples if s.get("border_radius"))
    if backgrounds:
        out["background_color"] = backgrounds.most_common(1)[0][0]
    if radii:
        out["border_radius"] = radii.most_common(1)[0][0]
    return out


def accent_colors(roles: dict, limit: int = 5) -> list[dict]:
    """Nicht neutrale Farben aus Buttons, Links und Preisen, nach Häufigkeit."""
    counts = Counter()
    for role in ("button", "primary_button", "link", "price", "navigation"):
        for sample in roles.get(role) or []:
            for key in ("background_color", "color", "border_color"):
                color = normalize_color(sample.get(key))
                if color and not is_neutral(color):
                    counts[color] += 1
    return [{"color": color, "count": count} for color, count in counts.most_common(limit)]


_MEDIA = re.compile(r"\((min|max)-width\s*:\s*([\d.]+)(px|em|rem)\s*\)")


def parse_breakpoints(media_texts: list[str]) -> list[dict]:
    """Breakpoints aus Media-Query-Texten, `em` und `rem` zu 16 px, nach Häufigkeit."""
    counts = Counter()
    for text in media_texts or []:
        for kind, number, unit in _MEDIA.findall(text):
            value = float(number) * (16 if unit in ("em", "rem") else 1)
            counts[(kind, round(value, 1))] += 1
    return [{"kind": kind, "px": value, "count": count}
            for (kind, value), count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0][1]))]


def mode_radius(values: list[str]) -> dict:
    counts = Counter(v for v in values or [] if v)
    if not counts:
        return {"value": None, "samples": 0}
    value, count = counts.most_common(1)[0]
    return {"value": value, "px": px(value), "share": round(count / sum(counts.values()), 2),
            "samples": sum(counts.values())}


def summarize_page(raw: dict) -> dict:
    roles = raw.get("roles") or {}
    return {
        "roles": {role: summarize_role(roles.get(role) or []) for role in ROLES},
        "colors": {
            "background_page": normalize_color((raw.get("backgrounds") or {}).get("page")),
            "background_header": normalize_color((raw.get("backgrounds") or {}).get("header")),
            "background_footer": normalize_color((raw.get("backgrounds") or {}).get("footer")),
            "accents": accent_colors(roles),
        },
        "radii": {key: mode_radius(values) for key, values in (raw.get("radii") or {}).items()},
        "viewport": raw.get("viewport"),
    }


def summarize_site(pages: list[dict]) -> dict:
    """Je Gerät und Rolle der häufigste Wert über alle gültigen Seiten."""
    out = {}
    for device in sorted({p["device"] for p in pages}):
        per_role = {}
        for role in ROLES:
            values = Counter()
            for page in pages:
                if page["device"] != device or page.get("state") != "ok":
                    continue
                value = ((page.get("roles") or {}).get(role) or {}).get("value")
                if value:
                    values[json.dumps(value, sort_keys=True)] += 1
            if values:
                top, count = values.most_common(1)[0]
                per_role[role] = {"value": json.loads(top), "pages": count, "of_pages": sum(values.values())}
        out[device] = per_role
    return out


# ---------------------------------------------------------------------------
# Browser
# ---------------------------------------------------------------------------

def measure_page(playwright, browsers: dict, job: dict) -> dict:
    device, page_info = job["device"], job["page"]
    browser = common.browser_for(playwright, browsers, device)
    url = common.page_url(job["base_url"], page_info["path"], job["theme"], hide_bar=True)
    context = browser.new_context(**common.context_options(playwright, device, job["locale"]))
    result = {"page_id": page_info["id"], "template": page_info.get("template"), "path": page_info["path"],
              "url": url, "device": device, "browser": common.ENGINE[device], "state": "ok"}
    try:
        page = context.new_page()
        response = page.goto(url, wait_until="load", timeout=job["timeout"])
        result["status"] = response.status if response else None
        page.wait_for_timeout(1500)
        theme = common.check_theme(common.theme_in_page(page), job["theme"])
        result["theme_check"] = theme
        result["consent"] = common.handle_consent(page, "declined")
        page.keyboard.press("Escape")
        common.scroll_to_end(page)
        page.evaluate("() => window.scrollTo(0, 0)")
        page.wait_for_timeout(job["wait"])
        raw = page.evaluate(MEASURE_JS, MAX_SAMPLES)
        result.update(summarize_page(raw))
        result["media"] = raw.get("media") or []
        result["stylesheets"] = {"total": raw.get("sheets"), "unreadable": raw.get("unreadable_sheets")}
        if theme["state"] != "ok":
            result["state"] = "wrong_theme"
    except Exception as exc:
        result["state"] = "error"
        result["error"] = f"{type(exc).__name__}: {exc}"[:500]
    finally:
        context.close()
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Gestaltung je Beispielseite messen")
    parser.add_argument("--pages", required=True, help="pages.json")
    parser.add_argument("--out", required=True, help="Ziel design.json")
    parser.add_argument("--theme", help="Theme-ID für preview_theme_id; ohne sie das Live-Theme")
    parser.add_argument("--devices", default="desktop,mobile")
    parser.add_argument("--only", help="nur diese Seiten-IDs, kommagetrennt")
    parser.add_argument("--wait", type=int, default=2500, help="Wartezeit vor dem Messen in ms")
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
    jobs = [{"page": page, "page_id": page["id"], "device": device, "base_url": pages["base_url"],
             "theme": args.theme, "wait": args.wait, "timeout": args.timeout, "locale": args.locale}
            for page in pages["pages"] for device in devices]
    started = common.now()
    results = common.run_jobs(jobs, measure_page, args.parallel)
    measured = []
    for job, result in zip(jobs, results):
        if result.get("job") is not None:
            result = {"page_id": job["page_id"], "device": job["device"], "state": "error", "error": result.get("error")}
        measured.append(result)
    media = [text for page in measured if page.get("state") == "ok" for text in page.pop("media", [])]
    for page in measured:
        page.pop("media", None)
    data = {"tool": "measure_styles", "base_url": pages["base_url"], "theme_id": args.theme, "measured_at": started,
            "summary": summarize_site(measured), "breakpoints": parse_breakpoints(media), "pages": measured}
    common.write_json(Path(args.out), data)
    bad = [p for p in measured if p.get("state") != "ok"]
    print(json.dumps({"out": args.out, "pages": len(measured), "ok": len(measured) - len(bad),
                      "wrong_theme": sum(1 for p in bad if p.get("state") == "wrong_theme"),
                      "errors": sum(1 for p in bad if p.get("state") == "error")}, ensure_ascii=False))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
