"""Testbestellung am Launch-Tag: Kauf-Aufrufe je Ziel, Bestellung in Shopify, Bericht in GA4.

Liest, was `scripts/browser/walk_checkout.py` festgehalten hat (`<lauf>/test-order/walk.json`):
die Stufen der Kasse bis zur Zahlung, die Kennung im Warenkorb, die Dankeseite und jede
Anfrage des Browsers. Die Bestellung setzt ein Mensch ab; dieses Modul schreibt nie in den
Shop und nie in ein Werbekonto.

**Welche Lesewege es gibt**, recherchiert am 10.11.2026, damit kein Ziel ohne Beleg als
erfüllt gilt:

- **Shopify:** Admin GraphQL `orders`, Scope `read_orders`, gegen 2026-04 validiert. Die
  Bestellung wird über das Warenkorb-Attribut `_ptai_test_order` gefunden, das der
  Durchlauf vor der Kasse setzt; es geht als `customAttributes` in die Bestellung über.
- **GA4:** Data API `runReport` mit der Dimension `transactionId`, eindeutig je Bestellung,
  aber mit Verarbeitungsverzug (bis 48 Stunden). Die Echtzeit-API (`runRealtimeReport`)
  kennt nur `eventName`, `minutesAgo` und wenige andere Dimensionen, keine
  `transactionId`; ein Kauf in Echtzeit lässt sich also keiner Bestellung zuordnen und ist
  nur ein Hinweis.
- **Google Ads:** kein Leseweg. Das Konto zählt eine Conversion nur nach einer
  Anzeigeninteraktion; eine Testbestellung ohne Klick erscheint dort nie, und GAQL zeigt
  keine einzelne Bestellnummer. Beleg ist der Conversion-Aufruf von der Dankeseite.
- **Meta:** kein Leseweg. Testereignisse gibt es nur in der Oberfläche des Events Manager,
  ohne API. Beleg ist der Pixel-Aufruf `ev=Purchase`.
- **Microsoft Ads, Pinterest, TikTok:** dasselbe, Beleg ist der Aufruf im Browser.

Ein Absender auf dem Server (Littledata, Elevar, Conversions-API) ist im Browser
unsichtbar. Läuft ein Ziel so, steht es in der Config als `via` (oder wird für GA4 aus
der Bestandsaufnahme erkannt); dann entscheidet der Leseweg, und ohne ihn steht das Ziel
als `blocked` oder als Frage, nie als `ok`.
"""
import json
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlparse

#: Ziele, an die ein Kauf geht, mit ihrer Dienst-ID aus `hosts.json`.
PURCHASE_SERVICES = ("google_analytics", "google_ads", "meta", "microsoft_ads", "pinterest", "tiktok")
LABELS = {"shopify": "Shopify-Bestellung", "google_analytics": "GA4", "google_ads": "Google Ads", "meta": "Meta",
          "microsoft_ads": "Microsoft Ads", "pinterest": "Pinterest", "tiktok": "TikTok"}
#: Wo ein Mensch den Kauf sieht, wenn es keinen Leseweg gibt.
TOOLS = {"google_ads": "Google Ads (Ziele, Conversions, Diagnose der Conversion-Aktion)",
         "meta": "Meta Events Manager (Testereignisse oder Übersicht des Pixels)",
         "microsoft_ads": "Microsoft Advertising (UET-Tag, Conversion-Ziele)",
         "pinterest": "Pinterest Ads (Conversions, Event-Historie des Tags)",
         "tiktok": "TikTok Events Manager (Testereignisse)",
         "google_analytics": "GA4 (Berichte, Monetarisierung, Transaktions-ID)"}
#: Dienste, die einen Kauf auf dem Server an GA4 senden; im Browser unsichtbar.
SERVER_SENDERS = {"littledata": "Littledata", "elevar": "Elevar"}
#: Warenkorb-Attribut, über das die Bestellung gefunden wird. Mit Unterstrich, damit die Kasse es nicht zeigt.
TOKEN_KEY = "_ptai_test_order"
#: So lange darf GA4 für einen Kauf im Bericht brauchen; danach fehlt er.
GA4_REPORT_DELAY_HOURS = 48
#: Die Echtzeit-API reicht bei Standard-Properties 29 Minuten zurück.
GA4_REALTIME_MINUTES = 29
#: Stufen des Durchlaufs, in denen ein Kauf-Aufruf entstehen kann: ab der Übergabe an den Menschen.
PURCHASE_STAGES = ("handoff", "thank_you")
#: Ergebnisse des Cookie-Dialogs, nach denen die Einwilligung belegt ist.
CONSENT_GIVEN = ("accepted",)

GA4_REPORT_URL = "https://analyticsdata.googleapis.com/v1beta/properties/{prop}:runReport"
GA4_REALTIME_URL = "https://analyticsdata.googleapis.com/v1beta/properties/{prop}:runRealtimeReport"

ORDER_QUERY = """query LaunchCheckTestOrder($query: String!) {
  orders(first: 20, query: $query, sortKey: CREATED_AT, reverse: true) {
    nodes {
      id
      name
      createdAt
      test
      cancelledAt
      displayFinancialStatus
      totalPriceSet { shopMoney { amount currencyCode } }
      customAttributes { key value }
    }
  }
}"""


# ---------------------------------------------------------------------------
# Durchlauf
# ---------------------------------------------------------------------------

def load_walk(path: Path):
    """`walk.json` als dict, None ohne Datei oder bei kaputtem Inhalt."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and data.get("tool") == "walk_checkout" else None


def parse_time(value) -> datetime | None:
    if not value:
        return None
    try:
        stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return stamp if stamp.tzinfo else stamp.replace(tzinfo=timezone.utc)


def consent_given(walk: dict) -> bool:
    return ((walk.get("consent_result") or {}).get("result")) in CONSENT_GIVEN


def stage(walk: dict, name: str) -> dict:
    return next((s for s in walk.get("stages") or [] if s.get("stage") == name), {})


# ---------------------------------------------------------------------------
# Kauf-Aufrufe im Browser
# ---------------------------------------------------------------------------

def _form_lines(body: str) -> list:
    """Ein Inhalt wie GA4 ihn bündelt: je Zeile ein Ereignis als Query-String."""
    return [dict(parse_qsl(line, keep_blank_values=True)) for line in (body or "").splitlines() if "=" in line]


def _delivered(request: dict) -> bool:
    status = request.get("status")
    return not request.get("failure") and (status is None or 200 <= int(status) < 400)


def parse_hits(request: dict) -> list:
    """Kauf-Aufrufe in einer Anfrage, je Ziel eine Zeile; leer, wenn es keiner ist.

    GA4 bündelt mehrere Ereignisse in einem POST, deshalb eine Liste. Eine
    Google-Ads-Anfrage ohne `label` ist Remarketing, keine Conversion.
    """
    url = request.get("url") or ""
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    path = parsed.path or "/"
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    body = request.get("post_data") or ""
    base = {"url": url[:300], "status": request.get("status"), "failure": request.get("failure"),
            "delivered": _delivered(request), "stage": request.get("stage")}
    hits = []
    if (host.endswith("google-analytics.com") or host.endswith("analytics.google.com")) and path.endswith("/g/collect"):
        events = [dict(query, **line) for line in _form_lines(body)] or [query]
        for event in events:
            if event.get("en") == "purchase":
                hits.append(dict(base, service="google_analytics", id=query.get("tid") or event.get("tid"),
                                 transaction=event.get("ep.transaction_id"),
                                 value=event.get("epn.value") or event.get("ep.value"),
                                 currency=event.get("cu") or query.get("cu")))
        return hits
    ads = re.match(r"^/pagead/(1p-)?conversion/(\d+)/?", path)
    if ads and query.get("label") and (host.endswith("googleadservices.com") or host.endswith("google.com")
                                       or host.endswith("doubleclick.net") or ".google." in f".{host}"):
        return [dict(base, service="google_ads", id=ads.group(2), label=query.get("label"),
                     first_party=bool(ads.group(1)), transaction=query.get("oid"), value=query.get("value"),
                     currency=query.get("currency_code"))]
    if host.endswith("facebook.com") and path.rstrip("/") == "/tr":
        params = dict(query, **(_form_lines(body)[0] if _form_lines(body) else {}))
        if params.get("ev") == "Purchase":
            return [dict(base, service="meta", id=params.get("id"), event_id=params.get("eid"),
                         value=params.get("cd[value]"), currency=params.get("cd[currency]"))]
        return []
    if host in ("bat.bing.com", "bat.bing.net") and path.startswith("/action"):
        if query.get("ea") == "purchase" or query.get("gv"):
            return [dict(base, service="microsoft_ads", id=query.get("ti"), value=query.get("gv"),
                         currency=query.get("gc"))]
        return []
    if host == "ct.pinterest.com" and query.get("event") == "checkout":
        return [dict(base, service="pinterest", id=query.get("tid"))]
    if host.endswith("tiktok.com") and "/api/v2/pixel" in path:
        event = re.search(r'"event"\s*:\s*"(CompletePayment|Purchase)"', body)
        if event:
            code = re.search(r'"pixel_code"\s*:\s*"([^"]+)"', body)
            return [dict(base, service="tiktok", id=code.group(1) if code else None, event=event.group(1))]
    return []


def purchase_hits(requests: list, stages=PURCHASE_STAGES) -> list:
    """Alle Kauf-Aufrufe ab der Übergabe an den Menschen."""
    return [hit for request in requests or [] if request.get("stage") in stages for hit in parse_hits(request)]


def describe_hit(hit: dict) -> str:
    parts = [str(hit.get("id") or "ohne Kennung")]
    if hit.get("label"):
        parts.append(f"Label {hit['label']}")
    if hit.get("transaction"):
        parts.append(f"Bestellung {hit['transaction']}")
    if hit.get("value"):
        parts.append(f"Wert {hit['value']}" + (f" {hit['currency']}" if hit.get("currency") else ""))
    parts.append(f"Antwort {hit.get('status') or 'ohne Status'}" if hit["delivered"]
                 else f"gescheitert ({hit.get('failure') or hit.get('status')})")
    return ", ".join(parts)


def repeated(hits: list) -> list:
    """Aufrufe, die für dieselbe Kennung mehrfach kamen; die Erstanbieter-Kopie von Google Ads zählt nicht."""
    seen = {}
    for hit in hits:
        if hit.get("first_party"):
            continue
        key = (hit.get("id"), hit.get("label"), hit.get("transaction"))
        seen[key] = seen.get(key, 0) + 1
    return [(key, count) for key, count in seen.items() if count > 1]


# ---------------------------------------------------------------------------
# Ziele
# ---------------------------------------------------------------------------

def configured_destinations(raw) -> dict | None:
    """`theme_migration.purchase_destinations` als `{dienst: {"via": ...}}`, None ohne Eintrag.

    Erlaubt sind eine Liste von Dienst-IDs oder ein Objekt mit `via` je Dienst
    (`{"google_analytics": {"via": "littledata"}, "google_ads": {}}`).
    """
    if isinstance(raw, list):
        return {str(s): {} for s in raw if str(s).strip()}
    if isinstance(raw, dict):
        return {str(k): (v if isinstance(v, dict) else {}) for k, v in raw.items()}
    return None


def derive_destinations(configured: dict | None, used: dict, dropped: dict, senders: dict) -> list:
    """Die Ziele dieses Shops, je Ziel Herkunft und Absender auf dem Server.

    `used`: `{dienst: herkunft}` aus Bestandsaufnahme und Mitschnitt, `dropped`:
    `{dienst: beleg}` bewusst entfallener Dienste, `senders`: `{dienst: name}`
    der Absender auf dem Server, die im Shop laufen. Die Config gewinnt.
    """
    if configured is not None:
        return [{"id": sid, "via": spec.get("via"), "source": "Config (theme_migration.purchase_destinations)"}
                for sid, spec in configured.items() if sid in PURCHASE_SERVICES]
    out = []
    for sid in PURCHASE_SERVICES:
        if sid not in used or sid in dropped:
            continue
        via = ", ".join(senders.values()) if sid == "google_analytics" and senders else None
        out.append({"id": sid, "via": via, "source": used[sid]})
    return out


# ---------------------------------------------------------------------------
# Shopify
# ---------------------------------------------------------------------------

def find_order(transport, token: str, since: datetime | None) -> dict | None:
    """Die Bestellung mit dem Warenkorb-Attribut aus dem Durchlauf, None, wenn es keine gibt."""
    filter_ = f"created_at:>='{since.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}'" if since else ""
    data = transport.execute(ORDER_QUERY, {"query": filter_})
    for node in ((data.get("orders") or {}).get("nodes")) or []:
        attributes = {a.get("key"): a.get("value") for a in node.get("customAttributes") or []}
        if attributes.get(TOKEN_KEY) == token:
            return node
    return None


def order_amount(order: dict) -> tuple:
    money = ((order.get("totalPriceSet") or {}).get("shopMoney")) or {}
    try:
        amount = float(money.get("amount"))
    except (TypeError, ValueError):
        amount = None
    return amount, money.get("currencyCode")


def order_candidates(order: dict | None, hits: list) -> list:
    """Werte, unter denen ein Ziel die Bestellung als Transaktions-ID führen kann.

    Connectoren nehmen mal den Namen (`#1234`), mal die Nummer ohne Raute, mal die ID.
    Dazu jede Bestellnummer, die ein Aufruf im Browser selbst mitgeschickt hat.
    """
    values = []
    if order:
        name = str(order.get("name") or "")
        values += [name, name.lstrip("#"), str(order.get("id") or "").rsplit("/", 1)[-1]]
    values += [str(h["transaction"]) for h in hits if h.get("transaction")]
    out = []
    for value in values:
        if value and value not in out:
            out.append(value)
    return out


def admin_order_url(store: str, order: dict) -> str | None:
    handle = (store or "").replace(".myshopify.com", "")
    order_id = str(order.get("id") or "").rsplit("/", 1)[-1]
    return f"https://admin.shopify.com/store/{handle}/orders/{order_id}" if handle and order_id else None


# ---------------------------------------------------------------------------
# GA4
# ---------------------------------------------------------------------------

def _post(url: str, token: str, body: dict) -> dict:
    request = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), method="POST",
                                     headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def _describe(exc: Exception) -> str:
    if isinstance(exc, urllib.error.HTTPError):
        try:
            return json.loads(exc.read().decode("utf-8", "replace")).get("error", {}).get("message") or f"HTTP {exc.code}"
        except Exception:  # noqa: BLE001  kaputter Fehlertext
            return f"HTTP {exc.code}"
    return f"{type(exc).__name__}: {exc}"[:300]


class GA4Reader:
    """Lesezugang zu einer GA4-Property: Käufe je Transaktions-ID und Käufe in Echtzeit."""

    def __init__(self, prop: str, token_fn, post=None):
        self.prop, self.token_fn, self.post = str(prop), token_fn, post or _post
        self._token = None

    def _call(self, url: str, body: dict) -> dict:
        if self._token is None:
            self._token = self.token_fn()
        return self.post(url.format(prop=self.prop), self._token, body)

    def transactions(self, candidates: list, start: str, end: str = "today") -> dict:
        """`{"rows": [{"transaction", "purchases", "revenue"}], "currency"}` für diese Transaktions-IDs.

        `ecommercePurchases` zählt nur purchase-Ereignisse, nie Erstattungen
        (Begründung in `pull-ga4/scripts/ga4_pull.py`, PURCHASE_METRIC).
        """
        body = {"dateRanges": [{"startDate": start, "endDate": end}],
                "dimensions": [{"name": "transactionId"}],
                "metrics": [{"name": "ecommercePurchases"}, {"name": "purchaseRevenue"}],
                "dimensionFilter": {"filter": {"fieldName": "transactionId",
                                               "inListFilter": {"values": list(candidates)}}}}
        data = self._call(GA4_REPORT_URL, body)
        rows = []
        for row in data.get("rows") or []:
            values = [v.get("value") for v in row.get("metricValues") or []]
            rows.append({"transaction": (row.get("dimensionValues") or [{}])[0].get("value"),
                         "purchases": int(float(values[0] or 0)) if values else 0,
                         "revenue": float(values[1] or 0) if len(values) > 1 else None})
        return {"rows": rows, "currency": (data.get("metadata") or {}).get("currencyCode")}

    def realtime_purchases(self, minutes: int) -> int:
        """Zahl der purchase-Ereignisse der letzten Minuten; ohne Bezug zu einer Bestellung."""
        body = {"dimensions": [{"name": "eventName"}], "metrics": [{"name": "eventCount"}],
                "dimensionFilter": {"filter": {"fieldName": "eventName", "stringFilter": {"value": "purchase"}}},
                "minuteRanges": [{"startMinutesAgo": max(0, min(int(minutes), GA4_REALTIME_MINUTES)),
                                  "endMinutesAgo": 0}]}
        data = self._call(GA4_REALTIME_URL, body)
        return sum(int(float((row.get("metricValues") or [{}])[0].get("value") or 0)) for row in data.get("rows") or [])


def ga4_from_config(config: dict, workspace) -> tuple:
    """`(GA4Reader, None)` oder `(None, grund)`; liest `ga4_property_id` und `PTAI_GOOGLE_CREDENTIALS`."""
    prop = str(config.get("ga4_property_id") or "").strip()
    if not prop:
        return None, "ga4_property_id fehlt in reporting/config.json"
    try:
        from audit import env  # erst hier: das Theme-Paket bleibt ohne Audit-Paket importierbar
        creds = env.get("PTAI_GOOGLE_CREDENTIALS", workspace)
    except Exception as exc:  # noqa: BLE001  Paket fehlt oder .env nicht lesbar
        return None, f"Zugang nicht lesbar: {exc}"[:200]
    if not creds:
        return None, "PTAI_GOOGLE_CREDENTIALS nicht gesetzt (Workspace-.env oder zentral)"

    def token():
        from google_token import get_access_token
        return get_access_token(creds, "analytics")

    return GA4Reader(prop, token), None


def safe_call(fn, *args):
    """`(ergebnis, None)` oder `(None, grund)` für einen Aufruf an eine API."""
    try:
        return fn(*args), None
    except Exception as exc:  # noqa: BLE001  Netz, Zugang, kaputte Antwort
        return None, _describe(exc)
