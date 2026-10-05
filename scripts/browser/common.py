"""Gemeinsame Teile der Browser-Skripte: Seitenliste, Vorschau-Adresse, Theme-Nachweis, Ablauf.

Ohne Playwright importierbar; erst `run_jobs` und die Seitenhilfen brauchen es.
Die Skripte laufen wie in `capture-screens`:

  uv run --quiet --with playwright==1.58.0 python scripts/browser/<skript>.py …

Regeln, die hier stehen, damit jedes Skript sie gleich einhält:

- **Je Seite ein frischer Browser-Kontext.** Kein Cookie, keine Einwilligung und
  keine Vorschau-Sitzung aus einer anderen Seite wirkt nach.
- **Vorschau nur im Browser mit `preview_theme_id`**, nie per Abruf ohne Browser:
  die Vorschau greift über Cookie und Weiterleitung, ein Abruf ohne beides liefert
  den Live-Shop. Jede Seite trägt einen Theme-Nachweis aus der Seite selbst
  (`Shopify.theme`); stimmt die ID nicht, ist der Aufruf `wrong_theme` und zählt
  nicht.
- **`pb=0`** blendet die Vorschauleiste für Messungen und Bilder aus.
- **Höchstens zwei Seiten gleichzeitig** auf einer Storefront, sonst drosselt
  Shopify.
- **Consent wird abgelehnt**, außer ein Mitschnitt mit Einwilligung ist
  ausdrücklich verlangt (`--consent accepted`, nur nach Freigabe des Teams).
- **Chromium am Rechner, WebKit als iPhone.** Die WebKit-Aufnahme ist Pflicht,
  weil iOS-Safari anders rendert und andere Cookies zulässt.
"""
from __future__ import annotations

import datetime
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlencode, urlparse, parse_qsl, urlunparse

ROOT = Path(__file__).resolve().parents[2]
CONSENT_DIR = ROOT / "skills" / "capture-screens" / "scripts"

#: Höchstens so viele Seiten gleichzeitig auf einer Storefront.
MAX_PARALLEL = 2
DESKTOP_VIEWPORT = {"width": 1440, "height": 900}
MOBILE_DEVICE = "iPhone 13"
DEVICES = ("desktop", "mobile")
ENGINE = {"desktop": "chromium", "mobile": "webkit"}

PLAYWRIGHT_MISSING = ("Das Paket playwright fehlt in diesem Python. Aufruf über "
                      "uv run --quiet --with playwright==1.58.0 python <skript>.py")


class PagesError(Exception):
    """`pages.json` fehlt oder hat nicht die erwartete Form."""


def now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


def load_pages(path: str | Path, only: list[str] | None = None) -> dict:
    """`pages.json` lesen und prüfen: `{"base_url", "pages": [{"id", "template", "path", "locale"}]}`."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PagesError(f"{path}: {exc}") from exc
    base = data.get("base_url")
    local = isinstance(base, str) and re.match(r"^http://(localhost|127\.0\.0\.1)(:\d+)?(/|$)", base)
    if not isinstance(base, str) or not (base.startswith("https://") or local):
        raise PagesError("base_url fehlt oder ist keine https-Adresse (http nur für localhost)")
    pages = []
    seen = set()
    for page in data.get("pages") or []:
        if not isinstance(page, dict) or not page.get("id") or not isinstance(page.get("path"), str):
            raise PagesError(f"Seite ohne id oder path: {page!r}")
        if not page["path"].startswith("/"):
            raise PagesError(f"path muss mit / beginnen: {page['path']}")
        if page["id"] in seen:
            raise PagesError(f"id doppelt: {page['id']}")
        seen.add(page["id"])
        if only and page["id"] not in only:
            continue
        pages.append({"id": str(page["id"]), "template": page.get("template"), "path": page["path"],
                      "locale": page.get("locale")})
    if not pages:
        raise PagesError("keine Seite in pages.json" + (" passt zu --only" if only else ""))
    return {"base_url": base.rstrip("/"), "pages": pages}


def page_url(base_url: str, path: str, theme_id: str | None = None, hide_bar: bool = False) -> str:
    """Die Adresse einer Seite, mit Vorschau-Theme und ausgeblendeter Leiste, wenn verlangt.

    Vorhandene Parameter bleiben erhalten (`/search?q=ring`).
    """
    parsed = urlparse(base_url.rstrip("/") + path)
    query = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True)
             if k not in ("preview_theme_id", "pb")]
    if theme_id:
        query.append(("preview_theme_id", str(theme_id)))
    if hide_bar and theme_id:
        query.append(("pb", "0"))
    return urlunparse(parsed._replace(query=urlencode(query)))


_THEME_OBJECT = re.compile(r"Shopify\.theme\s*=\s*(\{[^;]{0,2000}?\})\s*;")


def theme_from_html(html: str) -> dict | None:
    """Der Theme-Nachweis aus dem ausgelieferten HTML: `{"id", "name", "role"}` oder `None`.

    Shopify schreibt `Shopify.theme = {"name": …, "id": …, "role": …}` in den
    Seitenkopf. Das ist kein dokumentiertes Format; gelesen wird deshalb nur, was
    sich sicher erkennen lässt, und die ID als Ziffernfolge, nie als Zahl
    (sonst verlöre eine führende Null ihre Bedeutung).
    """
    match = _THEME_OBJECT.search(html or "")
    if not match:
        return None
    body = match.group(1)
    theme_id = re.search(r"[\"']?id[\"']?\s*:\s*[\"']?(\d+)", body)
    if not theme_id:
        return None
    name = re.search(r"[\"']?name[\"']?\s*:\s*\"((?:[^\"\\]|\\.)*)\"", body)
    role = re.search(r"[\"']?role[\"']?\s*:\s*\"(\w+)\"", body)
    return {"id": theme_id.group(1), "name": name.group(1) if name else None,
            "role": role.group(1) if role else None, "source": "html"}


def check_theme(found: dict | None, expected: str | None) -> dict:
    """Vergleicht den Theme-Nachweis mit dem verlangten Theme.

    Ohne verlangtes Theme gilt jeder Nachweis; ohne Nachweis ist ein verlangtes
    Theme nicht belegt und der Aufruf `wrong_theme`, statt still den Live-Shop zu
    messen.
    """
    found_id = str(found["id"]) if found and found.get("id") is not None else None
    if expected is None:
        return {"expected": None, "found": found_id, "found_name": (found or {}).get("name"),
                "ok": True, "state": "ok"}
    # Im Browser ist die ID eine Zahl; verglichen wird deshalb als Zahl, wenn beide Ziffern sind.
    if found_id is not None and found_id.isdigit() and str(expected).isdigit():
        ok = int(found_id) == int(expected)
    else:
        ok = found_id is not None and found_id == str(expected)
    return {"expected": str(expected), "found": found_id, "found_name": (found or {}).get("name"),
            "ok": ok, "state": "ok" if ok else "wrong_theme",
            "reason": None if ok else ("kein Theme-Nachweis auf der Seite" if found_id is None
                                       else f"Seite zeigt Theme {found_id}")}


def parse_list(value: str | None, allowed: tuple[str, ...] | None = None) -> list[str] | None:
    if not value:
        return None
    items = [item.strip() for item in value.split(",") if item.strip()]
    if allowed:
        bad = [item for item in items if item not in allowed]
        if bad:
            raise ValueError(f"unbekannt: {', '.join(bad)}; erlaubt: {', '.join(allowed)}")
    return items


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Mit Playwright
# ---------------------------------------------------------------------------

def context_options(playwright, device: str, locale: str = "de-DE") -> dict:
    if device == "mobile":
        options = dict(playwright.devices[MOBILE_DEVICE])
        options.pop("default_browser_type", None)
    else:
        options = {"viewport": dict(DESKTOP_VIEWPORT)}
    options.update({"locale": locale, "timezone_id": "Europe/Berlin"})
    return options


def browser_for(playwright, browsers: dict, device: str):
    engine = ENGINE[device]
    if engine not in browsers:
        browsers[engine] = getattr(playwright, engine).launch()
    return browsers[engine]


def run_jobs(jobs: list, handler, parallel: int = MAX_PARALLEL) -> list:
    """Führt `handler(playwright, browsers, job)` für jeden Auftrag aus, höchstens `parallel` gleichzeitig.

    Jeder Arbeitsfaden hat seine eigene Playwright-Instanz, weil die API nicht
    über Fäden hinweg geteilt werden darf. Ein Fehler in einem Auftrag wird zu
    `{"state": "error", "error": …}` und hält die anderen nicht an.
    """
    import queue
    import threading

    from playwright.sync_api import sync_playwright

    parallel = max(1, min(int(parallel), MAX_PARALLEL))
    pending: "queue.Queue" = queue.Queue()
    for index, job in enumerate(jobs):
        pending.put((index, job))
    results: list = [None] * len(jobs)

    def worker():
        with sync_playwright() as playwright:
            browsers: dict = {}
            try:
                while True:
                    try:
                        index, job = pending.get_nowait()
                    except queue.Empty:
                        return
                    try:
                        results[index] = handler(playwright, browsers, job)
                    except Exception as exc:  # Netz, Zeitlimit, Browser
                        results[index] = {"job": job, "state": "error", "error": f"{type(exc).__name__}: {exc}"[:500]}
                    print(f"{index + 1}/{len(jobs)} {job_label(job)}: {(results[index] or {}).get('state')}",
                          file=sys.stderr, flush=True)
            finally:
                for browser in browsers.values():
                    try:
                        browser.close()
                    except Exception:
                        pass

    threads = [threading.Thread(target=worker) for _ in range(min(parallel, len(jobs)) or 1)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return results


def job_label(job) -> str:
    if isinstance(job, dict):
        return " ".join(str(job.get(k)) for k in ("page_id", "device", "side", "run") if job.get(k) is not None)
    return str(job)


THEME_JS = """() => {
  try {
    if (window.Shopify && Shopify.theme && Shopify.theme.id !== undefined) {
      return {id: String(Shopify.theme.id), name: Shopify.theme.name || null, role: Shopify.theme.role || null,
              source: 'js'};
    }
  } catch (e) {}
  return null;
}"""


def theme_in_page(page) -> dict | None:
    """Theme-Nachweis aus der laufenden Seite, sonst aus ihrem HTML."""
    try:
        found = page.evaluate(THEME_JS)
    except Exception:
        found = None
    if found:
        return found
    try:
        return theme_from_html(page.content())
    except Exception:
        return None


def handle_consent(page, mode: str, before_click=None) -> dict:
    """Lehnt den Cookie-Dialog ab (Standard) oder stimmt zu (nur `accepted`)."""
    if str(CONSENT_DIR) not in sys.path:
        sys.path.insert(0, str(CONSENT_DIR))
    import consent  # noqa: E402

    if mode == "accepted":
        state, how = consent.accept(page, before_click=before_click)
    else:
        state, how = consent.decline(page, before_click=before_click)
    return {"mode": mode, "result": state, "how": how}


#: Unter diesem Pfad liefert der Browser selbst eine leere Seite aus, ohne den Shop zu fragen.
BASELINE_PATH = "/__ptai_baseline_blank__"


def baseline_globals(browser, options: dict, base_url: str) -> list[str]:
    """Die `window`-Eigenschaften einer leeren Seite auf derselben Herkunft wie der Shop.

    Nicht `about:blank`: das ist kein sicherer Kontext, und jede API, die es nur
    dort gibt (Bluetooth, GPU, Sensoren), stünde sonst als neues Global da. Die
    leere Seite erfüllt der Browser selbst über eine Route; beim Shop kommt keine
    Anfrage an.
    """
    context = browser.new_context(**options)
    try:
        context.route(f"**{BASELINE_PATH}",
                      lambda route: route.fulfill(status=200, content_type="text/html", body="<!doctype html><html></html>"))
        page = context.new_page()
        page.goto(base_url.rstrip("/") + BASELINE_PATH)
        return sorted(page.evaluate("() => Object.getOwnPropertyNames(window)"))
    finally:
        context.close()


def scroll_to_end(page, step: int = 800, pause_ms: int = 350, max_steps: int = 60) -> int:
    """Scrollt bis zum Seitenende, auch wenn die Seite beim Scrollen nachlädt."""
    last = -1
    steps = 0
    for steps in range(1, max_steps + 1):
        try:
            height = page.evaluate("() => document.documentElement.scrollHeight")
            bottom = page.evaluate("() => window.scrollY + window.innerHeight")
        except Exception:
            break
        if bottom >= height - 5 and height == last:
            break
        last = height
        try:
            page.mouse.wheel(0, step)
        except Exception:
            page.evaluate(f"() => window.scrollBy(0, {step})")
        page.wait_for_timeout(pause_ms)
    return steps
