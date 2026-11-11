"""Kasse am Launch-Tag bis zur Zahlung durchgehen; die Bestellung setzt ein Mensch ab.

Nur nach ausdrücklicher Freigabe des Teams. Aufruf:

  uv run --quiet --with playwright==1.58.0 python scripts/browser/walk_checkout.py \
    --pages <pages.json> --out <lauf>/test-order --approved-by "<Name>" \
    [--product-path /products/<handle>] [--contact <kontakt.json>] \
    [--consent accepted|declined] [--timeout-minutes 20] [--headless]

Öffnet ein sichtbares Browserfenster und geht durch:

1. Produktseite des veröffentlichten Themes, Cookie-Dialog (Standard: zustimmen, damit
   Kauf-Pixel in Consent-Regionen überhaupt senden dürfen).
2. In den Warenkorb über den Knopf des Themes; findet sich keiner, über `/cart/add.js`.
3. Kennung in den Warenkorb: Attribut `_ptai_test_order` (wird zu `customAttributes` der
   Bestellung, so findet `launch_check` sie) und eine Notiz "Testbestellung, wird storniert"
   für das Lager.
4. Warenkorb: Artikel, Steuer- und Versandhinweis.
5. Kasse: Steuer, Versand und Zahlung. Mit `--contact` trägt das Skript die Testadresse des
   Teams ein, damit Versandarten erscheinen; ohne sie erledigt das der Mensch.
6. Übergabe: ein Mensch gibt die Zahlung ein und setzt die Bestellung ab. Das Skript gibt
   **nie** Zahlungsdaten ein und klickt nie auf "Jetzt kaufen".
7. Dankeseite: 15 Sekunden warten, damit die Kauf-Pixel senden, dann Bild und Text.

`--contact` ist eine JSON-Datei des Teams, nie im Repo:
`{"email", "first_name", "last_name", "address1", "postal_code", "city", "country_code"}`.

Schreibt `<out>/walk.json` (Stufen mit Beleg, Kennung, Dankeseite, jede Anfrage mit ihrer
Stufe) und je Stufe ein Bild `<out>/NN-<stufe>.png`. Auf stdout eine JSON-Zeile.
Exit 0 Dankeseite erreicht (mit `--headless`: alle Stufen bis zur Zahlung), 1 sonst,
2 Fehler vor dem ersten Aufruf.

`--headless` ist der Probelauf ohne Bestellung: bis zur Zahlung, dann Schluss.
"""
from __future__ import annotations

import argparse
import json
import re
import secrets
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import common  # noqa: E402
from capture_network import request_record  # noqa: E402

TOKEN_KEY = "_ptai_test_order"
#: Ein Steuerhinweis, wie ihn Warenkorb und Kasse in DE und EN zeigen.
TAX_NOTICE = re.compile(r"(inkl\.?|inklusive|zzgl\.?|zuzüglich|exkl\.?)[^.\n]{0,40}?(MwSt|Mehrwertsteuer|USt|"
                        r"Umsatzsteuer|Steuer)|\bSteuern\b|\bMwSt\b|\btaxes\b|\btax\b|\bVAT\b", re.I)
SHIPPING_NOTICE = re.compile(r"Versand|Lieferung|\bshipping\b", re.I)
PAYMENT_NOTICE = re.compile(r"\bZahlung\b|\bZahlungsart|\bPayment\b", re.I)
SHIPPING_METHOD = re.compile(r"Versandart|Versandmethode|Lieferart|Shipping method", re.I)
THANK_YOU = re.compile(r"thank[-_]you|/orders/[0-9a-f]+|/thank_you", re.I)
ORDER_TEXT = re.compile(r"(Bestellung|Bestellnummer|Bestätigung|Order|Confirmation)\s*(Nr\.?|#|number)?\s*#?\s*"
                        r"([A-Z0-9][A-Z0-9-]{3,})", re.I)
ADD_BUTTONS = ("form[action*='/cart/add'] [type=submit]", "button[name='add']", "[data-testid='add-to-cart']")
CHECKOUT_BUTTONS = ("button[name='checkout']", "input[name='checkout']", "a[href^='/checkout']")
CONTACT_FIELDS = (("email", ("input[name='email']", "#email")),
                  ("first_name", ("input[name='firstName']",)), ("last_name", ("input[name='lastName']",)),
                  ("address1", ("input[name='address1']",)), ("postal_code", ("input[name='postalCode']",)),
                  ("city", ("input[name='city']",)))
#: So lange senden die Kauf-Pixel nach dem Laden der Dankeseite noch.
PIXEL_WAIT_MS = 15000

PRIVACY_JS = r"""() => {
  const out = {};
  try { out.customer_privacy = window.Shopify && Shopify.customerPrivacy && Shopify.customerPrivacy.currentVisitorConsent
          ? Shopify.customerPrivacy.currentVisitorConsent() : null; } catch (e) { out.customer_privacy = String(e); }
  try { out.google_consent = window.google_tag_data && google_tag_data.ics && google_tag_data.ics.entries
          ? JSON.parse(JSON.stringify(google_tag_data.ics.entries)) : null; } catch (e) { out.google_consent = null; }
  return out;
}"""

SECTION_JS = r"""(pattern) => {
  const re = new RegExp(pattern, 'i');
  const heads = [...document.querySelectorAll('h1,h2,h3,h4,legend,[role=heading]')].filter(h => re.test(h.innerText || ''));
  if (!heads.length) return null;
  const box = heads[0].closest('section, fieldset, div') || heads[0].parentElement;
  return (box && box.innerText || '').replace(/\s+/g, ' ').trim().slice(0, 400);
}"""


# ---------------------------------------------------------------------------
# Ohne Playwright
# ---------------------------------------------------------------------------

def make_token() -> str:
    return "lc-" + secrets.token_hex(6)


def find_notice(text: str, pattern: re.Pattern) -> str | None:
    """Die Fundstelle samt etwas Umgebung, None ohne Treffer."""
    match = pattern.search(text or "")
    if not match:
        return None
    start, end = max(0, match.start() - 30), min(len(text), match.end() + 30)
    return re.sub(r"\s+", " ", text[start:end]).strip()


def is_thank_you(url: str) -> bool:
    return bool(THANK_YOU.search(url or ""))


def order_text(text: str) -> str | None:
    match = ORDER_TEXT.search(text or "")
    return re.sub(r"\s+", " ", match.group(0)).strip() if match else None


def pick_product_path(pages: dict, override: str | None) -> str | None:
    """`--product-path`, sonst die erste Produktseite der Seitenliste."""
    if override:
        return override
    return next((p["path"] for p in pages.get("pages") or []
                 if str(p.get("template") or p.get("id") or "").startswith("product")), None)


def load_contact(path: str | None) -> dict | None:
    if not path:
        return None
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("--contact muss ein JSON-Objekt sein")
    return data


# ---------------------------------------------------------------------------
# Mit Playwright
# ---------------------------------------------------------------------------

class Walk:
    """Ein Durchlauf: Stufen, Anfragen und Bilder, Stufe für Stufe festgehalten."""

    def __init__(self, page, out: Path, started: float):
        self.page, self.out, self.started = page, out, started
        self.current = "product"
        self.stages: list[dict] = []
        self.requests: list[dict] = []

    def record(self, name: str, state: str, evidence: str, **extra) -> dict:
        shot = f"{len(self.stages) + 1:02d}-{name}.png"
        try:
            self.page.screenshot(path=str(self.out / shot), full_page=False)
        except Exception:
            shot = None
        entry = {"stage": name, "state": state, "evidence": evidence, "url": self._url(), "screenshot": shot,
                 "t": round(time.time() - self.started, 1), **extra}
        self.stages.append(entry)
        print(f"{name}: {state} ({evidence})", file=sys.stderr, flush=True)
        return entry

    def _url(self) -> str | None:
        try:
            return self.page.url[:600]
        except Exception:
            return None

    def text(self) -> str:
        try:
            return self.page.inner_text("body", timeout=10000)
        except Exception:
            return ""

    def cart_count(self) -> int | None:
        try:
            return int(self.page.evaluate("async () => (await (await fetch('/cart.js')).json()).item_count"))
        except Exception:
            return None


def first_visible(page, selectors):
    for selector in selectors:
        locator = page.locator(f"{selector} >> visible=true").first
        try:
            if locator.count():
                return selector, locator
        except Exception:
            continue
    return None, None


def add_to_cart(walk: Walk, product_path: str) -> None:
    page = walk.page
    selector, button = first_visible(page, ADD_BUTTONS)
    how = None
    if button is not None:
        try:
            button.click(timeout=8000)
            page.wait_for_timeout(2500)
            how = f"Knopf des Themes ({selector})"
        except Exception as exc:
            how = None
            reason = f"Knopf {selector} nicht klickbar: {type(exc).__name__}"
    else:
        reason = "kein Knopf In den Warenkorb gefunden"
    count = walk.cart_count()
    if not count:
        script = """async (path) => {
          const product = await (await fetch(path.split('?')[0] + '.js')).json();
          const variant = product.variants.find(v => v.available) || product.variants[0];
          const r = await fetch('/cart/add.js', {method: 'POST', headers: {'Content-Type': 'application/json'},
                                                  body: JSON.stringify({items: [{id: variant.id, quantity: 1}]})});
          return r.status;
        }"""
        try:
            status = page.evaluate(script, product_path)
            how = f"/cart/add.js (Antwort {status}); {how or reason}"
        except Exception as exc:
            how = f"/cart/add.js gescheitert ({type(exc).__name__}); {how or reason}"
        count = walk.cart_count()
    walk.record("add_to_cart", "ok" if count else "failed", f"{count or 0} Artikel im Warenkorb über {how}",
                item_count=count)


def mark_cart(walk: Walk, token: str) -> None:
    script = """async ([key, token]) => {
      const body = {attributes: {[key]: token}, note: 'Testbestellung launch-check ' + token + ', wird storniert'};
      const r = await fetch('/cart/update.js', {method: 'POST', headers: {'Content-Type': 'application/json'},
                                                body: JSON.stringify(body)});
      const cart = await r.json();
      return (cart.attributes || {})[key] || null;
    }"""
    try:
        echoed = walk.page.evaluate(script, [TOKEN_KEY, token])
    except Exception as exc:
        echoed, error = None, f"{type(exc).__name__}: {exc}"[:200]
    else:
        error = None
    walk.record("mark", "ok" if echoed == token else "failed",
                f"Warenkorb-Attribut {TOKEN_KEY}={token} gesetzt" if echoed == token
                else f"Kennung nicht gesetzt ({error or 'nicht zurückgegeben'})")


def fill_contact(walk: Walk, contact: dict) -> None:
    page = walk.page
    filled = []
    country = contact.get("country_code")
    if country:
        try:
            page.locator("select[name='countryCode']").first.select_option(str(country), timeout=5000)
            filled.append("country_code")
            page.wait_for_timeout(800)
        except Exception:
            pass
    for key, selectors in CONTACT_FIELDS:
        if not contact.get(key):
            continue
        _, field = first_visible(page, selectors)
        if field is None:
            continue
        try:
            field.fill(str(contact[key]), timeout=5000)
            filled.append(key)
        except Exception:
            continue
    page.wait_for_timeout(5000)
    missing = [k for k, _ in CONTACT_FIELDS if contact.get(k) and k not in filled]
    walk.record("contact", "ok" if not missing else "failed",
                f"Testadresse eingetragen: {', '.join(filled) or 'nichts'}"
                + (f"; Feld nicht gefunden: {', '.join(missing)}" if missing else ""))


def walk_checkout(playwright, args, pages: dict, out: Path) -> dict:
    token = make_token()
    product_path = pick_product_path(pages, args.product_path)
    started = time.time()
    browser = playwright.chromium.launch(headless=args.headless)
    context = browser.new_context(**common.context_options(playwright, "desktop", args.locale))
    page = context.new_page()
    walk = Walk(page, out, started)
    by_request: dict = {}
    phase = {"value": "pre"}

    def on_request(request):
        record = request_record(request, phase["value"], started)
        record["stage"] = walk.current
        walk.requests.append(record)
        by_request[request] = record

    def on_response(response):
        record = by_request.get(response.request)
        if record is not None:
            record["status"] = response.status

    def on_failed(request):
        record = by_request.get(request)
        if record is not None:
            record["failure"] = (request.failure or "failed")[:200]

    context.on("request", on_request)
    context.on("response", on_response)
    context.on("requestfailed", on_failed)
    result = {"tool": "walk_checkout", "version": 1, "token": token, "approved_by": args.approved_by,
              "approved_at": common.now(), "base_url": pages["base_url"], "product_path": product_path,
              "consent_mode": args.consent, "headless": bool(args.headless), "started_at": common.now(),
              "thank_you": {"reached": False}}
    try:
        response = page.goto(pages["base_url"] + product_path, wait_until="load", timeout=args.timeout_ms)
        page.wait_for_timeout(1500)
        result["theme"] = common.theme_in_page(page)
        status = response.status if response else None
        walk.record("product", "ok" if status and status < 400 else "failed",
                    f"{product_path} antwortet {status}, Theme {(result['theme'] or {}).get('id')}")
        walk.current = "consent"
        result["consent_result"] = common.handle_consent(page, args.consent,
                                                          before_click=lambda: phase.__setitem__("value", "post"))
        page.wait_for_timeout(2000)
        try:
            result["privacy"] = page.evaluate(PRIVACY_JS)
        except Exception:
            result["privacy"] = None
        walk.record("consent", "ok" if result["consent_result"]["result"] in ("accepted", "declined") else "failed",
                    f"{result['consent_result']['result']} über {result['consent_result']['how']}")
        walk.current = "add_to_cart"
        add_to_cart(walk, product_path)
        walk.current = "mark"
        mark_cart(walk, token)
        walk.current = "cart"
        page.goto(pages["base_url"] + "/cart", wait_until="load", timeout=args.timeout_ms)
        page.wait_for_timeout(1500)
        text = walk.text()
        count = walk.cart_count()
        walk.record("cart", "ok" if count else "failed", f"{count or 0} Artikel auf /cart",
                    notices={"tax": find_notice(text, TAX_NOTICE), "shipping": find_notice(text, SHIPPING_NOTICE)})
        walk.current = "checkout"
        selector, button = first_visible(page, CHECKOUT_BUTTONS)
        how = f"Knopf des Themes ({selector})"
        try:
            if button is None:
                raise LookupError("kein Knopf zur Kasse")
            button.click(timeout=8000)
            page.wait_for_url(re.compile(r"/checkouts?/"), timeout=args.timeout_ms)
        except Exception as exc:
            how = f"direkt über /checkout ({type(exc).__name__} am Knopf)"
            page.goto(pages["base_url"] + "/checkout", wait_until="load", timeout=args.timeout_ms)
        page.wait_for_timeout(4000)
        text = walk.text()
        in_checkout = "/checkouts/" in page.url or "/checkout" in page.url
        walk.record("checkout", "ok" if in_checkout else "failed", f"Kasse geöffnet über {how}",
                    notices={"tax": find_notice(text, TAX_NOTICE), "shipping": find_notice(text, SHIPPING_NOTICE),
                             "payment": find_notice(text, PAYMENT_NOTICE)})
        if args.contact_data:
            walk.current = "contact"
            fill_contact(walk, args.contact_data)
            walk.current = "shipping"
            try:
                section = page.evaluate(SECTION_JS, SHIPPING_METHOD.pattern)
            except Exception:
                section = None
            walk.record("shipping", "ok" if section else "failed",
                        f"Versandarten: {section}" if section else "keine Versandarten nach der Adresse gefunden")
        else:
            walk.record("shipping", "skipped", "keine Testadresse (--contact); Versandarten erscheinen erst nach "
                                               "der Adresse, die der Mensch einträgt")
        walk.current = "payment"
        try:
            payment = page.evaluate(SECTION_JS, r"\bZahlung\b|\bPayment\b")
        except Exception:
            payment = None
        walk.record("payment", "ok" if payment else "skipped",
                    f"Zahlungsbereich sichtbar: {payment[:160]}" if payment
                    else "Zahlungsbereich noch nicht sichtbar (erscheint nach Adresse und Versand)")
        if not args.headless:
            walk.current = "handoff"
            print("\nÜBERGABE: Bitte im geöffneten Fenster Adresse, Versand und Zahlung eingeben und die "
                  "Bestellung absetzen. Das Skript wartet auf die Dankeseite.\n", file=sys.stderr, flush=True)
            deadline = time.time() + args.timeout_minutes * 60
            while time.time() < deadline and not is_thank_you(page.url):
                page.wait_for_timeout(2000)
            if is_thank_you(page.url):
                walk.current = "thank_you"
                page.wait_for_timeout(PIXEL_WAIT_MS)
                text = walk.text()
                result["thank_you"] = {"reached": True, "url": page.url[:600], "at": common.now(),
                                       "order_text": order_text(text)}
                walk.record("thank_you", "ok", f"Dankeseite erreicht: {order_text(text) or page.url[:120]}")
            else:
                walk.record("handoff", "failed", f"keine Dankeseite nach {args.timeout_minutes} Minuten")
    except Exception as exc:
        walk.record(walk.current, "failed", f"{type(exc).__name__}: {exc}"[:300])
    finally:
        result["finished_at"] = common.now()
        result["stages"] = walk.stages
        result["requests"] = walk.requests
        context.close()
        browser.close()
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Kasse bis zur Zahlung, Bestellung durch einen Menschen")
    parser.add_argument("--pages", required=True, help="pages.json mit base_url und einer Produktseite")
    parser.add_argument("--out", required=True, help="Zielordner, etwa <lauf>/test-order")
    parser.add_argument("--approved-by", required=True, help="wer im Team die Testbestellung freigegeben hat")
    parser.add_argument("--product-path", help="Produktseite; ohne sie die erste aus pages.json")
    parser.add_argument("--contact", help="JSON des Teams mit Testadresse, nie im Repo")
    parser.add_argument("--consent", choices=("accepted", "declined"), default="accepted")
    parser.add_argument("--timeout-minutes", type=int, default=20, help="Wartezeit auf die Dankeseite")
    parser.add_argument("--timeout", dest="timeout_ms", type=int, default=60000, help="Zeitlimit je Seite in ms")
    parser.add_argument("--locale", default="de-DE")
    parser.add_argument("--headless", action="store_true", help="Probelauf bis zur Zahlung, ohne Übergabe")
    args = parser.parse_args(argv)
    if not args.approved_by.strip():
        print(json.dumps({"error": "--approved-by braucht den Namen aus dem Team"}, ensure_ascii=False))
        return 2
    try:
        pages = common.load_pages(args.pages)
        args.contact_data = load_contact(args.contact)
    except (common.PagesError, OSError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 2
    if not pick_product_path(pages, args.product_path):
        print(json.dumps({"error": "keine Produktseite: --product-path setzen oder eine Seite mit template "
                                   "product in pages.json"}, ensure_ascii=False))
        return 2
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(json.dumps({"error": common.PLAYWRIGHT_MISSING}, ensure_ascii=False))
        return 2
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        result = walk_checkout(playwright, args, pages, out)
    common.write_json(out / "walk.json", result)
    failed = [s["stage"] for s in result["stages"] if s["state"] == "failed"]
    done = result["thank_you"]["reached"] or (args.headless and not failed)
    print(json.dumps({"out": str(out / "walk.json"), "token": result["token"], "thank_you": result["thank_you"],
                      "failed": failed, "requests": len(result["requests"])}, ensure_ascii=False))
    return 0 if done and not failed else 1


if __name__ == "__main__":
    sys.exit(main())
