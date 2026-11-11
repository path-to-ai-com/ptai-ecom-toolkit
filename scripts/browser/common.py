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
- **Tempo begrenzt, Drosselung erkannt** (seit 11.11.2026). Zwischen zwei
  Seitenaufrufen liegen über alle Arbeitsfäden mindestens `PACE_SECONDS`
  (`Pacer`). Antwortet Shopify mit HTTP 429 oder der Warteseite "Nur einen
  Moment…", ist der Aufruf `throttled`, kein Fehler des Shops: alle Fäden
  pausieren `COOLDOWN_SECONDS`, der Abstand verdoppelt sich, und die Seite läuft
  einmal neu. Anlass: Beim Prüfen eines Live-Shops scheiterte Horizons
  Nachladen an 429, und das Bild sah aus wie ein Fehler im Theme.
- **Consent wird abgelehnt**, außer ein Mitschnitt mit Einwilligung ist
  ausdrücklich verlangt (`--consent accepted`, nur nach Freigabe des Teams).
- **Chromium am Rechner, WebKit als iPhone.** Die WebKit-Aufnahme ist Pflicht,
  weil iOS-Safari anders rendert und andere Cookies zulässt. Die Breiten sind fest:
  1440 und 390 CSS-Pixel (`theme.visual_compare.WIDTHS`), Gate G4 zählt nur sie.
- **Scrollen und Ganzseiten-Bilder kennen scrollende Container.** Horizon scrollt
  am Rechner nicht das Dokument, sondern `.page-wrapper`; das Dokument bleibt so
  hoch wie das Fenster. Bis 11.11.2026 scrollte `scroll_to_end` deshalb nur einen
  Schritt, nachgeladene Bilder blieben leer, und `full_page` lieferte nur die
  Erstansicht. Dazu bleibt der Footer mit `content-visibility: auto` leer, bis er
  einmal im Bild war. Ablauf seitdem: `scroll_to_end` (Mausrad in Schritten, sonst
  per Skript im Container), `force_visible`, `scroll_to_top`, dann
  `capture_full_page`.
"""
from __future__ import annotations

import datetime
import json
import re
import sys
import threading
import time
from pathlib import Path
from urllib.parse import urlencode, urlparse, parse_qsl, urlunparse

ROOT = Path(__file__).resolve().parents[2]
CONSENT_DIR = ROOT / "skills" / "capture-screens" / "scripts"
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from theme.visual_compare import WIDTHS  # noqa: E402

#: Höchstens so viele Seiten gleichzeitig auf einer Storefront.
MAX_PARALLEL = 2
#: Mindestabstand in Sekunden zwischen zwei Seitenaufrufen, über alle Arbeitsfäden eines Laufs.
PACE_SECONDS = 3.0
#: So lange ruhen alle Fäden, nachdem Shopify gedrosselt hat; danach läuft die Seite einmal neu.
COOLDOWN_SECONDS = 60.0
#: Größer wird der Abstand auch nach mehreren Drosselungen nicht.
MAX_PACE_SECONDS = 20.0
#: Status eines Aufrufs, den Shopify gedrosselt hat. Kein Fehler des Shops und kein Ergebnis.
THROTTLED = "throttled"
#: Shopifys Warteseite bei Drosselung und Bot-Abfrage, im Seitentitel, deutsch und englisch.
THROTTLE_TEXT = re.compile(r"Nur einen Moment|Einen Moment bitte|Just a moment|Too many requests|Zu viele Anfragen",
                           re.I)
DESKTOP_VIEWPORT = {"width": WIDTHS["desktop"], "height": 900}
#: In Playwright 390 x 664 CSS-Pixel; die Breite wird in `context_options` trotzdem fest gesetzt.
MOBILE_DEVICE = "iPhone 13"
DEVICES = ("desktop", "mobile")
ENGINE = {"desktop": "chromium", "mobile": "webkit"}
#: Ab diesem Anteil am Fenster (Höhe und Breite) trägt ein scrollender Container die Seite.
SCROLLER_SHARE = 0.5
#: So viele CSS-Pixel Abstand zum Ende gelten noch als Ende.
END_TOLERANCE = 5

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
    # Die Rolle (`main` heißt veröffentlicht) belegt, ob die Referenz eines Vergleichs das Live-Theme ist.
    role = (found or {}).get("role")
    if expected is None:
        return {"expected": None, "found": found_id, "found_name": (found or {}).get("name"),
                "found_role": role, "ok": True, "state": "ok"}
    # Im Browser ist die ID eine Zahl; verglichen wird deshalb als Zahl, wenn beide Ziffern sind.
    if found_id is not None and found_id.isdigit() and str(expected).isdigit():
        ok = int(found_id) == int(expected)
    else:
        ok = found_id is not None and found_id == str(expected)
    return {"expected": str(expected), "found": found_id, "found_name": (found or {}).get("name"),
            "found_role": role, "ok": ok, "state": "ok" if ok else "wrong_theme",
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
# Drosselung: erkennen und das Tempo begrenzen, ohne Browser prüfbar
# ---------------------------------------------------------------------------

def shop_host(url: str | None, base_url: str | None) -> bool:
    """Geht die Adresse an den Shop selbst: Shop-Domain (mit und ohne www) oder `*.myshopify.com`."""
    host = (urlparse(url or "").hostname or "").lower()
    base = (urlparse(base_url or "").hostname or "").lower()
    if not host:
        return False
    bare = base[4:] if base.startswith("www.") else base
    return host in (base, bare, "www." + bare) or host.endswith(".myshopify.com")


def count_429(requests: list, base_url: str | None) -> int:
    """Anfragen an den Shop, die Shopify mit HTTP 429 beantwortet hat (Zeilen aus `request_record`)."""
    return sum(1 for r in requests or [] if r.get("status") == 429 and shop_host(r.get("url"), base_url))


def throttle_signal(document_status, title: str | None, shop_429: int = 0) -> dict | None:
    """Hat Shopify gedrosselt? `{"reason", "requests_429"}` oder None.

    Drei Zeichen, jedes für sich genügt: die Seite selbst antwortet 429, der Titel ist die Warteseite
    ("Nur einen Moment…"), oder eine Anfrage an den Shop bekam 429. Das Letzte ist der heimtückische
    Fall: die Seite lädt, aber Horizons Nachladen (Abschnitte, Warenkorb, Empfehlungen) scheitert, und
    das Bild sieht aus wie ein Fehler im Theme.
    """
    reasons = []
    if document_status == 429:
        reasons.append("Seite antwortet HTTP 429")
    if title and THROTTLE_TEXT.search(title):
        reasons.append(f"Warteseite „{' '.join(title.split())[:60]}“")
    if shop_429:
        reasons.append(f"{shop_429} {'Anfrage' if shop_429 == 1 else 'Anfragen'} an den Shop mit HTTP 429")
    if not reasons:
        return None
    return {"reason": "; ".join(reasons) + "; Drosselung durch Shopify, kein Fehler des Shops",
            "requests_429": int(shop_429)}


def mark_throttled(result: dict, signal: dict | None) -> dict:
    """Setzt `state: throttled`, wenn gedrosselt wurde; das geht vor `wrong_theme` und `error`.

    Die Warteseite trägt keinen Theme-Nachweis, und ein abgebrochenes Nachladen wirft Fehler. Beides ist
    dann Folge der Drosselung, nicht ihr Grund.
    """
    if signal:
        result["state"] = THROTTLED
        result["throttle"] = signal
    return result


class Pacer:
    """Abstand zwischen Seitenaufrufen über alle Arbeitsfäden; nach einer Drosselung Pause und mehr Abstand.

    Jeder Aufruf reserviert seinen Zeitpunkt unter einer Sperre und wartet danach ohne sie. Uhr und Warten
    sind austauschbar, damit sich das ohne echte Zeit prüfen lässt.
    """

    def __init__(self, pace: float = PACE_SECONDS, cooldown: float = COOLDOWN_SECONDS,
                 clock=time.monotonic, sleep=time.sleep):
        self.pace = max(0.0, float(pace))
        self.cooldown = max(0.0, float(cooldown))
        self.clock, self.sleep = clock, sleep
        self.lock = threading.Lock()
        self.next_at = 0.0
        self.throttle_events = 0

    def wait(self) -> float:
        """Wartet bis zum nächsten freien Zeitpunkt; gibt die Wartezeit in Sekunden zurück."""
        with self.lock:
            now = self.clock()
            start = max(now, self.next_at)
            self.next_at = start + self.pace
        delay = start - now
        if delay > 0:
            self.sleep(delay)
        return delay

    def throttled(self) -> None:
        """Shopify hat gedrosselt: alle pausieren, der Abstand verdoppelt sich bis `MAX_PACE_SECONDS`."""
        with self.lock:
            self.throttle_events += 1
            self.pace = min(max(self.pace * 2, PACE_SECONDS), MAX_PACE_SECONDS)
            self.next_at = max(self.next_at, self.clock() + self.cooldown)


def throttled_summary(results: list) -> str | None:
    """Eine Zeile für stderr, wenn Aufrufe gedrosselt blieben; None sonst."""
    hits = [r for r in results or [] if isinstance(r, dict) and r.get("state") == THROTTLED]
    if not hits:
        return None
    return (f"{len(hits)} Aufrufe von Shopify gedrosselt (HTTP 429), kein Fehler des Shops. Nicht als Befund "
            "werten; später mit --parallel 1 und größerem --pace nachholen (--only <ids>).")


# ---------------------------------------------------------------------------
# Seitenhöhe und Scrollstand, ohne Browser prüfbar
# ---------------------------------------------------------------------------

def main_scroller(metrics: dict) -> dict | None:
    """Der scrollende Container, der die Seite trägt, sonst None.

    `metrics` kommt aus `METRICS_JS`. Ein Container zählt, wenn er mindestens die Hälfte von Höhe und
    Breite des Fensters einnimmt und überläuft. Kleine scrollende Elemente (Dropdown, Warenkorb-Liste)
    tragen die Seite nicht. Von mehreren gilt der mit dem meisten Inhalt.
    """
    height = metrics.get("viewport_height") or 0
    width = metrics.get("viewport_width") or 0
    found = [s for s in metrics.get("scrollers") or []
             if (s.get("client_height") or 0) >= SCROLLER_SHARE * height
             and (s.get("client_width") or 0) >= SCROLLER_SHARE * width
             and (s.get("scroll_height") or 0) > (s.get("client_height") or 0) + 1]
    return max(found, key=lambda s: s["scroll_height"]) if found else None


def page_extent(metrics: dict) -> dict:
    """Höhe der ganzen Seite in CSS-Pixeln, Scrollstand und ob das Ende erreicht ist.

    Die Höhe ist das Maximum aus Dokument und scrollendem Container: das Dokument plus der Teil, den
    der Container verdeckt. In Horizon ist das Dokument so hoch wie das Fenster, und alles Weitere
    steckt in `.page-wrapper`; ohne Container ist es die Dokumenthöhe.
    """
    document = int(metrics.get("doc_height") or 0)
    window = int(metrics.get("viewport_height") or 0)
    scroll_y = int(metrics.get("scroll_y") or 0)
    scroller = main_scroller(metrics)
    hidden = scroller["scroll_height"] - scroller["client_height"] if scroller else 0
    height = max(document, window, document + hidden, scroller["scroll_height"] if scroller else 0)
    top = int(scroller.get("scroll_top") or 0) if scroller else 0
    document_end = scroll_y + window >= document - END_TOLERANCE
    scroller_end = scroller is None or top + scroller["client_height"] >= scroller["scroll_height"] - END_TOLERANCE
    return {"height": height, "document_height": document, "position": scroll_y + top,
            "at_end": document_end and scroller_end,
            "scroller": ({k: scroller.get(k) for k in ("index", "tag", "id", "class_name", "client_height",
                                                       "scroll_height")} if scroller else None)}


def scroll_done(extent: dict, last_height: int | None) -> bool:
    """Fertig gescrollt: am Ende, und die Seite ist seit dem letzten Schritt nicht gewachsen."""
    return bool(extent["at_end"]) and extent["height"] == last_height


def wheel_stuck(extent: dict, last_position: int | None) -> bool:
    """Das Mausrad hat nichts bewegt, obwohl das Ende nicht erreicht ist.

    So in WebKit mit iPhone-Profil (kein Mausrad) oder wenn unter der Maus ein fester Bereich liegt.
    Dann scrollt der Rest per Skript.
    """
    return last_position is not None and not extent["at_end"] and extent["position"] <= last_position


def capture_height(height: int, max_height: int) -> tuple[int, int | None]:
    """Höhe der Aufnahme und, falls gekürzt, die Höchsthöhe, an der abgeschnitten wurde."""
    height = max(1, int(height))
    return (max_height, max_height) if height > max_height else (height, None)


def scroller_label(scroller: dict | None) -> str | None:
    """`div.page-wrapper` statt Index, damit ein Mensch im Ergebnis sieht, was gescrollt hat."""
    if not scroller:
        return None
    name = scroller.get("tag") or "?"
    if scroller.get("id"):
        name += f"#{scroller['id']}"
    classes = str(scroller.get("class_name") or "").split()
    return name + "".join(f".{c}" for c in classes[:2])


# ---------------------------------------------------------------------------
# Mit Playwright
# ---------------------------------------------------------------------------

def context_options(playwright, device: str, locale: str = "de-DE") -> dict:
    if device == "mobile":
        options = dict(playwright.devices[MOBILE_DEVICE])
        options.pop("default_browser_type", None)
        # Fest 390 CSS-Pixel, auch wenn eine neuere Playwright-Fassung das Profil ändert.
        options["viewport"] = {**options.get("viewport", {"height": 664}), "width": WIDTHS["mobile"]}
    else:
        options = {"viewport": dict(DESKTOP_VIEWPORT)}
    options.update({"locale": locale, "timezone_id": "Europe/Berlin"})
    return options


def browser_for(playwright, browsers: dict, device: str):
    engine = ENGINE[device]
    if engine not in browsers:
        browsers[engine] = getattr(playwright, engine).launch()
    return browsers[engine]


def run_jobs(jobs: list, handler, parallel: int = MAX_PARALLEL, *, pace: float = PACE_SECONDS,
             cooldown: float = COOLDOWN_SECONDS, retries: int = 1, pacer: Pacer | None = None) -> list:
    """Führt `handler(playwright, browsers, job)` für jeden Auftrag aus, höchstens `parallel` gleichzeitig.

    Jeder Arbeitsfaden hat seine eigene Playwright-Instanz, weil die API nicht
    über Fäden hinweg geteilt werden darf. Ein Fehler in einem Auftrag wird zu
    `{"state": "error", "error": …}` und hält die anderen nicht an.

    Vor jedem Auftrag wartet der Faden auf den `Pacer` (Abstand `pace` über alle
    Fäden). Kommt ein Auftrag `throttled` zurück, pausieren alle `cooldown`
    Sekunden, und er läuft bis zu `retries`-mal neu; bleibt er gedrosselt, steht
    er so im Ergebnis.
    """
    import queue

    from playwright.sync_api import sync_playwright

    parallel = max(1, min(int(parallel), MAX_PARALLEL))
    pacer = pacer or Pacer(pace, cooldown)
    pending: "queue.Queue" = queue.Queue()
    for index, job in enumerate(jobs):
        pending.put((index, job))
    results: list = [None] * len(jobs)
    attempts = [0] * len(jobs)

    def worker():
        with sync_playwright() as playwright:
            browsers: dict = {}
            try:
                while True:
                    try:
                        index, job = pending.get_nowait()
                    except queue.Empty:
                        return
                    pacer.wait()
                    try:
                        results[index] = handler(playwright, browsers, job)
                    except Exception as exc:  # Netz, Zeitlimit, Browser
                        results[index] = {"job": job, "state": "error", "error": f"{type(exc).__name__}: {exc}"[:500]}
                    state = (results[index] or {}).get("state")
                    print(f"{index + 1}/{len(jobs)} {job_label(job)}: {state}", file=sys.stderr, flush=True)
                    if state == THROTTLED:
                        pacer.throttled()
                        if attempts[index] < retries:
                            attempts[index] += 1
                            print(f"  gedrosselt, Pause {int(pacer.cooldown)} s, Abstand jetzt {pacer.pace:g} s, "
                                  "dann erneut", file=sys.stderr, flush=True)
                            pending.put((index, job))
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


def page_title(page) -> str | None:
    try:
        return page.title()
    except Exception:
        return None


class ThrottleWatch:
    """Zählt in einem Browser-Kontext die Antworten des Shops mit HTTP 429; `signal` urteilt über die Seite."""

    def __init__(self, base_url: str):
        self.base_url = base_url
        self.count = 0

    def attach(self, context) -> "ThrottleWatch":
        context.on("response", self._on_response)
        return self

    def _on_response(self, response) -> None:
        try:
            if response.status == 429 and shop_host(response.url, self.base_url):
                self.count += 1
        except Exception:
            pass

    def signal(self, page, document_status=None) -> dict | None:
        return throttle_signal(document_status, page_title(page), self.count)


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


#: Höhe von Dokument und Fenster, Scrollstand und jedes überlaufende Element mit `overflow-y: auto|scroll`.
#: Die Elemente bekommen `data-ptai-scroller` mit ihrem Index, damit spätere Aufrufe sie wiederfinden.
METRICS_JS = """() => {
  const doc = document.documentElement, body = document.body;
  const scrollers = [];
  for (const el of document.querySelectorAll('[data-ptai-scroller]')) el.removeAttribute('data-ptai-scroller');
  for (const el of document.querySelectorAll('body, body *')) {
    if (!el.clientHeight || el.scrollHeight <= el.clientHeight + 1) continue;
    const overflow = getComputedStyle(el).overflowY;
    if (overflow !== 'auto' && overflow !== 'scroll' && overflow !== 'overlay') continue;
    el.setAttribute('data-ptai-scroller', String(scrollers.length));
    scrollers.push({index: scrollers.length, tag: el.tagName.toLowerCase(), id: el.id || null,
                    class_name: typeof el.className === 'string' ? el.className.slice(0, 120) : null,
                    client_height: el.clientHeight, client_width: el.clientWidth,
                    scroll_height: el.scrollHeight, scroll_top: Math.round(el.scrollTop)});
  }
  return {viewport_width: window.innerWidth, viewport_height: window.innerHeight,
          doc_height: Math.max(doc.scrollHeight, body ? body.scrollHeight : 0),
          scroll_y: Math.round(window.scrollY), scrollers};
}"""

#: Ein Schritt per Skript: Fenster und jeder große scrollende Container, ohne weiche Animation.
SCROLL_BY_JS = """(step) => {
  window.scrollBy({top: step, left: 0, behavior: 'instant'});
  for (const el of document.querySelectorAll('[data-ptai-scroller]')) {
    if (el.clientHeight >= window.innerHeight * 0.5) el.scrollBy({top: step, left: 0, behavior: 'instant'});
  }
}"""

SCROLL_TOP_JS = """() => {
  window.scrollTo({top: 0, left: 0, behavior: 'instant'});
  for (const el of document.querySelectorAll('[data-ptai-scroller]')) el.scrollTo({top: 0, behavior: 'instant'});
}"""

#: `content-visibility: auto` rendert einen Bereich erst, wenn er im Bild war (Horizon: Footer). Gesetzt wird
#: je Element im Inline-Stil, nicht über ein Style-Element: das erlaubt auch eine strenge CSP.
FORCE_VISIBLE_JS = """() => {
  let count = 0;
  for (const el of document.querySelectorAll('body *')) {
    const value = getComputedStyle(el).contentVisibility;
    if (value && value !== 'visible') { el.style.setProperty('content-visibility', 'visible', 'important'); count++; }
  }
  return count;
}"""

#: Gibt den scrollenden Container frei: er und alle Vorfahren wachsen mit dem Inhalt, das Dokument trägt die
#: ganze Höhe. Der alte Inline-Stil bleibt in `data-ptai-style`, damit `RESTORE_JS` ihn zurücksetzt.
RELEASE_JS = """(index) => {
  let el = document.querySelector(`[data-ptai-scroller="${index}"]`);
  if (!el) return false;
  for (; el; el = el.parentElement) {
    if (!el.hasAttribute('data-ptai-style')) el.setAttribute('data-ptai-style', el.getAttribute('style') || '');
    for (const [prop, value] of [['height', 'auto'], ['max-height', 'none'], ['overflow', 'visible']]) {
      el.style.setProperty(prop, value, 'important');
    }
  }
  return true;
}"""

#: Höhe jedes Elements außerhalb des scrollenden Containers und seiner Vorfahren, vor dem Vergrößern des Fensters.
RECORD_HEIGHTS_JS = """(index) => {
  const chain = new Set([document.documentElement, document.body]);
  for (let el = document.querySelector(`[data-ptai-scroller="${index}"]`); el; el = el.parentElement) chain.add(el);
  let count = 0;
  for (const el of document.querySelectorAll('body *')) {
    if (chain.has(el)) continue;
    el.setAttribute('data-ptai-height', String(el.getBoundingClientRect().height));
    count++;
  }
  return count;
}"""

#: Was mit dem Fenster gewachsen ist (Höhen in `vh`, `svh`, `dvh`), zurück auf die gemessene Höhe.
PIN_GROWN_JS = """() => {
  let count = 0;
  for (const el of document.querySelectorAll('[data-ptai-height]')) {
    const before = parseFloat(el.getAttribute('data-ptai-height'));
    if (el.getBoundingClientRect().height > before + 2) {
      for (const prop of ['height', 'min-height', 'max-height']) el.style.setProperty(prop, before + 'px', 'important');
      count++;
    }
  }
  return count;
}"""

RESTORE_JS = """() => {
  for (const el of document.querySelectorAll('[data-ptai-style]')) {
    const old = el.getAttribute('data-ptai-style');
    if (old) el.setAttribute('style', old); else el.removeAttribute('style');
    el.removeAttribute('data-ptai-style');
  }
}"""


def measure(page) -> dict:
    """`page_extent` der laufenden Seite."""
    return page_extent(page.evaluate(METRICS_JS))


def scroll_to_end(page, step: int | None = None, pause_ms: int = 350, max_steps: int = 80) -> int:
    """Scrollt bis zum Seitenende, auch wenn die Seite beim Scrollen nachlädt oder in einem Container scrollt.

    Erst mit dem Mausrad in der Fenstermitte: es scrollt, was unter der Maus scrollt, auch `.page-wrapper`,
    und löst dieselben Ereignisse aus wie ein Mensch. Bewegt es nichts (WebKit mit iPhone-Profil kennt kein
    Mausrad), scrollt der Rest per Skript Fenster und Container. Ein Schritt ist 80 % der Fensterhöhe,
    damit kein nachgeladenes Bild zwischen zwei Schritten liegt.
    """
    try:
        size = page.viewport_size or {}
        page.mouse.move(size.get("width", 800) / 2, size.get("height", 600) / 2)
    except Exception:
        pass
    use_wheel = True
    last_height = last_position = None
    steps = 0
    for steps in range(1, max_steps + 1):
        try:
            extent = page.evaluate(METRICS_JS)
        except Exception:
            break
        distance = step or max(200, int((extent.get("viewport_height") or 800) * 0.8))
        extent = page_extent(extent)
        if scroll_done(extent, last_height):
            break
        if use_wheel and wheel_stuck(extent, last_position):
            use_wheel = False
        last_height, last_position = extent["height"], extent["position"]
        if use_wheel:
            try:
                page.mouse.wheel(0, distance)
            except Exception:
                use_wheel = False
        if not use_wheel:
            page.evaluate(SCROLL_BY_JS, distance)
        page.wait_for_timeout(pause_ms)
    return steps


def force_visible(page) -> int:
    """Erzwingt `content-visibility: visible` auf jedem Element; gibt zurück, wie viele es betraf."""
    try:
        return int(page.evaluate(FORCE_VISIBLE_JS) or 0)
    except Exception:
        return 0


def scroll_to_top(page) -> None:
    """Fenster und jeder scrollende Container zurück nach oben, ohne weiche Animation."""
    try:
        page.evaluate(SCROLL_TOP_JS)
    except Exception:
        page.evaluate("() => window.scrollTo(0, 0)")


def capture_full_page(page, path: str, max_height: int, settle_ms: int = 800) -> dict:
    """Ganzseiten-Bild, auch wenn die Seite in einem Container scrollt. Gibt Höhe und Verfahren zurück.

    - `document`: das Dokument trägt die Höhe, `full_page` wie immer.
    - `released`: ein Container scrollt (Horizon: `.page-wrapper`). Er und seine Vorfahren werden
      freigegeben, bis das Dokument die ganze Höhe trägt, dann `full_page`. Das Fenster bleibt so hoch wie
      vorher, Bereiche in `vh` oder `svh` (Horizon: Abschnitte "Volle Bildschirmhöhe") behalten ihre Höhe.
    - `resized`: trägt das Dokument nach der Freigabe noch nicht die ganze Höhe (etwa ein Container mit
      `position: fixed`), wird das Fenster auf die gemessene Höhe gesetzt (gedeckelt) und aufgenommen. So
      lief es am 11.11.2026 von Hand. Dabei wächst jeder Bereich in `vh` oder `svh` mit dem Fenster, ein
      Abschnitt "Volle Bildschirmhöhe" wird so hoch wie die ganze Seite und schiebt den Rest aus dem Bild.
      Deshalb wird vorher die Höhe jedes Elements gemessen und, was danach gewachsen ist, auf sie
      festgesetzt (`pinned`). Läuft der Container danach noch über, ist das Bild `incomplete` und zählt
      für Gate G4 nicht.

    Bilder in CSS-Pixeln (`scale="css"`): ein iPhone-Bild mit dreifacher Dichte wäre bei 10 000 Pixeln
    Seitenhöhe 30 000 Pixel hoch. Die Erstansicht nimmt `shoot_pair` getrennt in voller Dichte auf.
    """
    size = dict(page.viewport_size or {"width": 0, "height": 0})
    extent = measure(page)
    scroller, height, method = extent["scroller"], extent["height"], "document"
    pinned, incomplete = 0, False
    if scroller:
        page.evaluate(RECORD_HEIGHTS_JS, scroller["index"])
        page.evaluate(RELEASE_JS, scroller["index"])
        page.wait_for_timeout(settle_ms)
        released = measure(page)
        method = release_method(extent, released)
        if method == "released":
            height = released["height"]
        else:
            page.evaluate(RESTORE_JS)
            height, pinned, incomplete = _resize_to_content(page, size["width"], height, max_height, settle_ms)
    target, cut_at = capture_height(height, max_height)
    if method == "resized":
        page.screenshot(path=path, scale="css")
    else:
        page.screenshot(path=path, full_page=True, scale="css",
                        clip={"x": 0, "y": 0, "width": size["width"], "height": target})
    return {"method": method, "page_height": height, "cut_at": cut_at, "scroller": scroller_label(scroller),
            "viewport": size, "pinned": pinned, "incomplete": incomplete}


def _resize_to_content(page, width: int, height: int, max_height: int, settle_ms: int) -> tuple[int, int, bool]:
    """Fenster so hoch wie der Inhalt, Gewachsenes festgesetzt: `(höhe, festgesetzt, unvollständig)`."""
    pinned = 0
    for _ in range(3):
        target, cut_at = capture_height(height, max_height)
        page.set_viewport_size({"width": width, "height": target})
        page.wait_for_timeout(settle_ms)
        pinned += int(page.evaluate(PIN_GROWN_JS) or 0)
        page.wait_for_timeout(200)
        after = measure(page)
        if not after["scroller"]:
            return after["height"], pinned, False
        if cut_at:
            return max(height, after["height"]), pinned, False
        height = after["height"]
    return height, pinned, True


def release_method(before: dict, after: dict) -> str:
    """`released`, wenn nach der Freigabe kein Container mehr scrollt und das Dokument die Höhe trägt.

    Zehn Prozent Spielraum, weil ein freigegebener Container ohne `min-height: 100dvh` etwas kürzer
    werden darf. Sonst `resized`: das Fenster wird so hoch wie die Seite.
    """
    return "released" if not after["scroller"] and after["height"] >= before["height"] * 0.9 else "resized"
