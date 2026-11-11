"""Bildpaare zweier Themes je Beispielseite: Chromium am Rechner und WebKit als iPhone, mit Theme-Nachweis.

Aufruf (aus dem Workspace):

  uv run --quiet --with playwright==1.58.0 python scripts/browser/shoot_pair.py \
    --pages migration/inventory/pages.json --a <live-theme-id> --b <draft-theme-id> --out <ordner> \
    [--devices desktop,mobile] [--only home,product] [--workspace .] [--pace 3] [--menu-toggle <css>] \
    [--menu-toggle-desktop <css>]

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
Seite zeigt (`common.capture_full_page`, Verfahren `resized`), und `throttled`,
wenn Shopify gedrosselt hat (HTTP 429, Warteseite): das ist kein Fehler des Shops.

**Am Handy auch mit offenem Menü** (seit 11.11.2026, Nachtrag). Nach der ganzen
Seite lädt das Skript die Seite neu, öffnet das Menü über den Menüknopf im
Kopfbereich (oder `--menu-toggle`), nimmt `<id>/mobile-<a|b>-menu.png` auf und
prüft an einem Raster von Punkten über der Menü-Schublade, welches Element oben
liegt (`elementFromPoint`). Was nicht zur Schublade und nicht zum Kopfbereich des
Menüknopfs gehört, steht in `menu.foreign` mit Kennzeichen, z-index und Anteil
der Fläche. Anlass: Ein E-Mail-Teaser (z-index 90000) und eine Countdown-Leiste
lagen über Horizons Schublade (z-index 18); geschlossen sah die Seite richtig aus.
Elemente mit `pointer-events: none` sieht `elementFromPoint` nicht; dafür bleibt
das Bild.

**Am Rechner mit offenem Untermenü** (seit 0.3.31). Ebenso am Rechner: die Seite
neu laden, den ersten Menüpunkt mit Untermenü im Kopfbereich suchen (oder
`--menu-toggle-desktop`), mit der Maus darauf zeigen, öffnet sich nichts, klicken
(nie auf einen Link mit Ziel), `<id>/desktop-<a|b>-menu.png` aufnehmen und über
dem Untermenü dasselbe Raster prüfen. Anlass: Bei einem Shop, der auf Horizon
umzog, war das Mega-Menü am Rechner nach dem Launch kaputt; der Bildvergleich
öffnete das Menü nur am Handy, und der Testpunkt war ohne Bild geschlossen.

**Referenz.** Die linke Seite muss das veröffentlichte Theme sein, nach dem Launch
das alte Theme, das bis dahin veröffentlicht war (`rollback_theme_id` mit
`published_at` im Lauf). Vor dem Launch ist Beleg die Rolle `main` im
Theme-Nachweis der Seiten; `--a` wird außerdem gegen `live_theme_id` der Config
geprüft. Steht links ein anderes Theme, ist der Vergleich ungültig (Exit 1,
`reference.problems`); eine abweichende Config bei belegter Rolle ist eine
Warnung (`reference.warnings`). Die Referenz steht mit ID und Name im Ergebnis.

**Eintrag für Gate G4.** Liegt im Workspace `reporting/config.json`, schreibt das
Skript zusätzlich `migration/verify/<date>/pairs.json`: dieselben Paare mit
Referenz und Abdeckung, ohne Bilder. `theme.visual_compare` liest daraus, ob für
jede Beispielseite am Rechner und am Handy ein gültiges Paar vorliegt; ohne das
hält G4 an. Ein zweiter Lauf am selben Tag mit denselben Themes ergänzt den
Eintrag je Seite und Breite.

Die Bilder gehören in den Kundenordner, nie ins Repo. Jedes Paar wird angesehen;
eine Pixel-Differenz allein ist kein Befund. Exit 0 alle Bilder gültig und
Referenz belegt, 1 mindestens ein Bild mit falschem Theme, Fehler oder Drosselung,
die Referenz ist nicht das veröffentlichte Theme, oder rechts ließ sich das Menü
(Handy) oder Untermenü (Rechner) nicht prüfen oder ein fremdes Element liegt
darüber, 2 Fehler vor dem ersten Aufruf.
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


#: Menüknöpfe im Kopfbereich, in dieser Reihenfolge versucht: Horizon, Dawn-Familie, verbreitete Muster.
MENU_TOGGLES = (
    "header-drawer summary", "summary.header__icon--menu", "[aria-controls*='menu-drawer' i]",
    "[aria-controls*='MenuDrawer' i]", "button[aria-label*='Menü' i]", "button[aria-label*='Menu' i]",
    "summary[aria-label*='Menü' i]", "summary[aria-label*='Menu' i]", "[data-drawer-toggle]",
    ".header__icon--menu", ".menu-toggle", ".mobile-menu-toggle", ".hamburger",
)
#: Menüpunkte mit Untermenü am Rechner, in dieser Reihenfolge versucht: Dawn-Familie (details), Horizon
#: (Listenpunkt mit Aufklappknopf, öffnet beim Zeigen), Navigation mit aria-haspopup (Broadcast und andere),
#: Listenpunkte mit Unterliste oder Aufklappknopf, verbreitete Muster (seit 0.3.31). Ein
#: aria-haspopup="dialog" öffnet Suche oder Warenkorb, kein Menü.
DESKTOP_MENU_TRIGGERS = (
    "header nav details > summary", ".menu-list__list-item:has(.menu-list__disclosure) .menu-list__link",
    "header nav [aria-haspopup]:not([aria-haspopup='dialog'])",
    "header nav li:has(ul a) > a", "header nav li:has(ul a) > button",
    "header nav li:has([aria-controls][aria-expanded]) a",
    "header [aria-haspopup]:not([aria-haspopup='dialog'])", "header li:has(ul a) > a",
    "[data-hover-disclosure-toggle]", "[data-mega-menu-trigger]", ".has-dropdown > a", ".site-nav--has-dropdown > a",
)
#: Raster der Punkte über der Schublade; bei 390 x 664 Pixeln liegen sie etwa 39 x 27 Pixel auseinander.
MENU_GRID = (10, 24)
#: Raster über dem Untermenü am Rechner, das meist breit und flach ist.
DESKTOP_MENU_GRID = (24, 10)
#: Ab diesem Anteil am Bildschirm gilt ein neu sichtbares Element als Schublade (Handy) oder Untermenü (Rechner).
MENU_MIN_SHARE = {"mobile": 0.25, "desktop": 0.02}
#: Bis hierher (CSS-Pixel von oben) muss der Menüknopf liegen.
MENU_TOGGLE_MAX_TOP = 220
#: So lange öffnet sich die Schublade (Animation).
MENU_OPEN_MS = 900

#: Sucht den Menüknopf, markiert ihn und alle großen Elemente, die vor dem Klick schon sichtbar sind.
MENU_PREPARE_JS = r"""([selectors, maxTop, minShare]) => {
  const W = innerWidth, H = innerHeight;
  const shown = el => { const cs = getComputedStyle(el);
    return cs.display !== 'none' && cs.visibility !== 'hidden' && parseFloat(cs.opacity || '1') > 0.05; };
  const onScreen = el => { const r = el.getBoundingClientRect();
    return Math.max(0, Math.min(r.right, W) - Math.max(r.left, 0)) * Math.max(0, Math.min(r.bottom, H) - Math.max(r.top, 0)); };
  for (const el of document.querySelectorAll('[data-ptai-menu-toggle],[data-ptai-before]')) {
    el.removeAttribute('data-ptai-menu-toggle'); el.removeAttribute('data-ptai-before'); }
  let toggle = null;
  for (const sel of selectors) {
    let found;
    try { found = document.querySelectorAll(sel); } catch (e) { continue; }
    for (const el of found) {
      const r = el.getBoundingClientRect();
      if (r.width > 0 && r.height > 0 && r.top < maxTop && shown(el)) { toggle = {el, sel}; break; }
    }
    if (toggle) break;
  }
  if (!toggle) return null;
  toggle.el.setAttribute('data-ptai-menu-toggle', '1');
  for (const el of document.querySelectorAll('body *')) {
    if (onScreen(el) >= minShare * W * H && shown(el)) el.setAttribute('data-ptai-before', '1');
  }
  const href = toggle.el.tagName === 'A' ? (toggle.el.getAttribute('href') || '') : '';
  return {selector: toggle.sel, safe_click: !href || href.startsWith('#') || href.startsWith('javascript')};
}"""

#: Findet die Schublade (neu sichtbar, groß, mit Links) und prüft je Rasterpunkt, was oben liegt.
MENU_PROBE_JS = r"""([cols, rows, minShare]) => {
  const W = innerWidth, H = innerHeight;
  const shown = el => { const cs = getComputedStyle(el);
    return cs.display !== 'none' && cs.visibility !== 'hidden' && parseFloat(cs.opacity || '1') > 0.05; };
  const box = el => { const r = el.getBoundingClientRect();
    return {left: Math.max(r.left, 0), top: Math.max(r.top, 0), right: Math.min(r.right, W), bottom: Math.min(r.bottom, H)}; };
  const area = b => Math.max(0, b.right - b.left) * Math.max(0, b.bottom - b.top);
  const label = el => {
    let out = el.tagName.toLowerCase();
    if (el.id) out += '#' + el.id;
    const cls = typeof el.className === 'string' ? el.className.trim().split(/\s+/).filter(Boolean).slice(0, 2) : [];
    return out + cls.map(c => '.' + c).join('');
  };
  const zIndex = el => { for (let e = el; e && e !== document.documentElement; e = e.parentElement) {
      const cs = getComputedStyle(e); if (cs.position !== 'static' && cs.zIndex !== 'auto') return cs.zIndex; }
    return 'auto'; };
  const layerRoot = el => { let root = el;
    for (let e = el; e && e !== document.body; e = e.parentElement) {
      const pos = getComputedStyle(e).position; if (pos === 'fixed' || pos === 'sticky' || pos === 'absolute') root = e; }
    return root; };
  let drawer = null, best = 0;
  for (const el of document.querySelectorAll('body *')) {
    if (el.hasAttribute('data-ptai-before') || !shown(el)) continue;
    const a = area(box(el));
    if (a < minShare * W * H || el.querySelectorAll('a[href]').length < 3) continue;
    if (a > best) { best = a; drawer = el; }
  }
  if (!drawer) return {state: 'no_drawer'};
  const toggle = document.querySelector('[data-ptai-menu-toggle]');
  const header = toggle && toggle.closest('header, [role="banner"]');
  const b = box(drawer);
  const foreign = new Map();
  let points = 0;
  for (let i = 0; i < cols; i++) for (let j = 0; j < rows; j++) {
    const x = b.left + 4 + (b.right - b.left - 8) * (i + 0.5) / cols;
    const y = b.top + 4 + (b.bottom - b.top - 8) * (j + 0.5) / rows;
    const top = document.elementFromPoint(x, y);
    points++;
    if (!top || top === drawer || drawer.contains(top) || top.contains(drawer)) continue;
    if (header && header.contains(top)) continue;
    const root = layerRoot(top);
    const key = label(root);
    const entry = foreign.get(key) || {label: key, z_index: zIndex(root), points: 0,
      text: (root.innerText || '').replace(/\s+/g, ' ').trim().slice(0, 60)};
    entry.points++;
    foreign.set(key, entry);
  }
  const list = [...foreign.values()].map(f => ({...f, share: Math.round(f.points / points * 1000) / 1000}))
    .sort((a, b) => b.points - a.points);
  return {state: list.length ? 'overlap' : 'ok', points,
          drawer: {label: label(drawer), z_index: zIndex(drawer), rect: b}, foreign: list};
}"""


def image_names(page_id: str, device: str, side: str) -> tuple[str, str]:
    """Feste Dateinamen je Seite, Gerät und Seite des Paars, relativ zum Zielordner."""
    return f"{page_id}/{device}-{side}.png", f"{page_id}/{device}-{side}-fold.png"


def menu_name(page_id: str, side: str, device: str = "mobile") -> str:
    """Bild des Zustands "Menü offen" am Handy oder "Untermenü offen" am Rechner."""
    return f"{page_id}/{device}-{side}-menu.png"


def shoot_menu(page, out: Path, page_id: str, side: str, toggles: tuple, wait_ms: int,
               device: str = "mobile") -> dict:
    """Öffnet das Menü (Handy) oder ein Untermenü (Rechner), nimmt es auf und prüft, was darüber liegt.

    Ergebnis `{"state": ok|overlap|no_toggle|no_drawer|error, "file", "toggle", "drawer", "foreign", "points"}`,
    am Rechner dazu `opened_by` (`hover` oder `click`). Die Seite ist frisch geladen; Einblendungen wie Teaser
    oder Leisten erscheinen oft erst nach einer Wartezeit, deshalb wartet das Skript `wait_ms`. Am Rechner
    öffnen Mega-Menüs meist beim Zeigen, die Dawn-Familie beim Klick; geklickt wird nur, wenn der Menüpunkt
    kein Link mit Ziel ist, sonst wechselte die Seite.
    """
    share = MENU_MIN_SHARE[device]
    grid = list(DESKTOP_MENU_GRID if device == "desktop" else MENU_GRID)
    page.wait_for_timeout(wait_ms)
    found = page.evaluate(MENU_PREPARE_JS, [list(toggles), MENU_TOGGLE_MAX_TOP, share])
    if not found:
        return {"state": "no_toggle", "tried": list(toggles)}
    toggle = found["selector"]
    locator = page.locator("[data-ptai-menu-toggle]").first
    extra = {}
    try:
        if device == "desktop":
            locator.hover(timeout=8000)
            extra["opened_by"] = "hover"
        else:
            locator.click(timeout=8000)
    except Exception as exc:
        return {"state": "error", "toggle": toggle, "error": f"Klick auf {toggle}: {type(exc).__name__}"}
    page.wait_for_timeout(MENU_OPEN_MS)
    probe = page.evaluate(MENU_PROBE_JS, [*grid, share])
    if device == "desktop" and probe.get("state") == "no_drawer" and found.get("safe_click"):
        try:
            locator.click(timeout=8000)
        except Exception as exc:
            return {"state": "error", "toggle": toggle, "error": f"Klick auf {toggle}: {type(exc).__name__}"}
        extra["opened_by"] = "click"
        page.wait_for_timeout(MENU_OPEN_MS)
        probe = page.evaluate(MENU_PROBE_JS, [*grid, share])
    name = menu_name(page_id, side, device)
    page.screenshot(path=str(out / name))
    return {**probe, "toggle": toggle, "file": name, **extra}


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


def finish(data: dict, page_ids: list, config: dict | None, workspace: Path | None = None) -> dict:
    """Referenz und Abdeckung an den Index hängen, dazu die Abweichung der rechten Seite vom Entwurf.

    Nach dem Launch (Stand des Migrationslaufs mit `published_at`) ist die Referenz das Rückfall-Theme.
    """
    values = visual_compare.run_values(workspace) if workspace is not None else {}
    live, draft = visual_compare.current_ids(config or {}, values)
    summary = visual_compare.record_summary(page_ids, data["pairs"], data["themes"], live,
                                            visual_compare.rollback_id(values))
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
    watch = common.ThrottleWatch(job["base_url"]).attach(context)
    result = {"url": url, "theme_id": theme_id, "state": "ok", "captured_at": common.now()}
    page = None
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
        if job.get("menu", True):
            # Frisch geladen: die Ganzseiten-Aufnahme hat Höhen festgesetzt und Container freigegeben.
            toggles = (job.get("desktop_menu_toggles") or DESKTOP_MENU_TRIGGERS) if device == "desktop" \
                else (job.get("menu_toggles") or MENU_TOGGLES)
            try:
                page.goto(url, wait_until="load", timeout=job["timeout"])
                common.handle_consent(page, "declined")
                result["menu"] = shoot_menu(page, out, page_info["id"], side, toggles, job["wait"], device)
            except Exception as exc:
                result["menu"] = {"state": "error", "error": f"{type(exc).__name__}: {exc}"[:300]}
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
        # Gedrosselt ist kein Ergebnis: ein Bild mit gescheitertem Nachladen sähe aus wie ein Fehler im Theme.
        if page is not None:
            common.mark_throttled(result, watch.signal(page, result.get("status")))
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
    parser.add_argument("--pace", type=float, default=common.PACE_SECONDS,
                        help="Mindestabstand zwischen zwei Seitenaufrufen in Sekunden")
    parser.add_argument("--menu-toggle", help="CSS-Selektor des Menüknopfs am Handy, wenn die Suche ihn nicht findet")
    parser.add_argument("--menu-toggle-desktop",
                        help="CSS-Selektor eines Menüpunkts mit Untermenü am Rechner, wenn die Suche ihn nicht findet")
    parser.add_argument("--no-menu", action="store_true",
                        help="ohne Aufnahme 'Menü offen' und 'Untermenü offen' (zählt nicht für G4)")
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
             "locale": args.locale, "menu": not args.no_menu,
             "menu_toggles": (args.menu_toggle,) + MENU_TOGGLES if args.menu_toggle else MENU_TOGGLES,
             "desktop_menu_toggles": ((args.menu_toggle_desktop,) + DESKTOP_MENU_TRIGGERS if args.menu_toggle_desktop
                                      else DESKTOP_MENU_TRIGGERS)}
            for page in pages["pages"] for device in devices for side in ("a", "b")]
    results = common.run_jobs(jobs, shoot, args.parallel, pace=args.pace)
    data = {**build_pairs(jobs, results, themes), "base_url": pages["base_url"], "captured_at": common.now()}
    data = finish(data, [p["id"] for p in pages["pages"]], config, workspace)
    common.write_json(out / "pairs.json", data)
    record = write_record(workspace, data, out.resolve()) if config is not None else None
    shots = [p.get(side) or {} for p in data["pairs"] for side in ("a", "b")]
    bad = [s for s in shots if s.get("state") != "ok"]
    reference = data["reference"]
    print(f"Referenz: {visual_compare.theme_label(reference['theme_id'], reference.get('name'))}"
          + (" (Rückfall-Theme, bis zum Launch veröffentlicht)" if reference.get("kind") == "rollback"
             else " (veröffentlicht)" if reference.get("published") else ""), file=sys.stderr, flush=True)
    for line in reference["problems"] + reference["warnings"]:
        print(f"Referenz: {line}", file=sys.stderr, flush=True)
    menu_issues = [m for m in data["coverage"]["missing"]
                   if str(m.get("reason", "")).startswith(tuple(visual_compare.MENU_PREFIX.values()))]
    for item in menu_issues[:6]:
        device = visual_compare.DEVICE_LABEL.get(item.get("device"), item.get("device"))
        print(f"{item['page_id']} {device} B: {item['reason']}", file=sys.stderr, flush=True)
    note = common.throttled_summary(shots)
    if note:
        print(note, file=sys.stderr, flush=True)
    if record is None:
        print(f"Kein Workspace unter {workspace} (reporting/config.json fehlt): kein Eintrag für Gate G4",
              file=sys.stderr, flush=True)
    print(json.dumps({"out": str(out / "pairs.json"), "record": str(record) if record else None,
                      "pairs": len(data["pairs"]), "images": len(shots),
                      "wrong_theme": sum(1 for s in bad if s.get("state") == "wrong_theme"),
                      "throttled": sum(1 for s in bad if s.get("state") == common.THROTTLED),
                      "errors": sum(1 for s in bad if s.get("state") == "error"),
                      "reference": visual_compare.theme_label(reference["theme_id"], reference.get("name")),
                      "reference_ok": reference["ok"], "reference_published": reference["published"],
                      "menu_problems": len(menu_issues),
                      "reference_problems": reference["problems"], "reference_warnings": reference["warnings"],
                      "coverage": {k: data["coverage"][k] for k in ("expected", "valid", "complete")}},
                     ensure_ascii=False))
    return 1 if bad or not reference["ok"] or menu_issues else 0


if __name__ == "__main__":
    sys.exit(main())
