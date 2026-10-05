"""Messziele (Mess- und Werbe-Kennungen) in Code, Konfiguration und Anfragen finden.

Gemeinsam für `theme.apps` (Theme-Code, Pixel-Konfiguration, Netzwerk-Mitschnitt)
und `theme.gtm` (aufgelöster Tag-Manager-Container). Eine Kennung ist hier immer
ein Paar aus Art und Wert, normiert auf eine Schreibweise, damit dieselbe Kennung
aus fünf Quellen eine Zeile in `tracking.json` ergibt:

- GA4 `G-…`, Google-Tag `GT-…`, Google Ads `AW-<zahl>` (Label getrennt),
  Universal Analytics `UA-…`, Floodlight `DC-<zahl>`
- Meta-Pixel `META:<zahl>`, TikTok `TIKTOK:<code>`, Pinterest `PINTEREST:<zahl>`,
  Microsoft UET `UET:<zahl>`, Clarity `CLARITY:<id>`, Snap `SNAP:<uuid>`,
  LinkedIn `LINKEDIN:<zahl>`, Klaviyo `KLAVIYO:<id>`

Ein Container `GTM-…` ist kein Messziel, sondern ein Verteiler; er kommt über
`container_ids()` getrennt heraus.

Nur Standardbibliothek.
"""
from __future__ import annotations

import json
import re
from urllib.parse import parse_qs, urlparse

#: Eine GA4- oder Google-Tag-Kennung enthält Ziffern; ohne die Bedingung träfe
#: das Muster Wörter wie "G-STRING" in einem Text.
_GA4 = re.compile(r"\bG-(?=[A-Z0-9]*\d)[A-Z0-9]{6,12}\b")
_GT = re.compile(r"\bGT-(?=[A-Z0-9]*\d)[A-Z0-9]{6,12}\b")
_AW = re.compile(r"\bAW-(\d{6,12})(?:/([\w-]{4,40}))?")
_UA = re.compile(r"\bUA-\d{4,10}-\d{1,4}\b")
_DC = re.compile(r"\bDC-(\d{5,12})\b")
_UET = re.compile(r"\bti\s*:\s*['\"](\d{4,12})['\"]")
_GTM = re.compile(r"\bGTM-(?=[A-Z0-9]*\d)[A-Z0-9]{4,10}\b")

_CODE_PATTERNS = [
    ("meta", re.compile(r"fbq\(\s*['\"]init['\"]\s*,\s*['\"]?(\d{8,20})")),
    ("tiktok", re.compile(r"ttq\.load\(\s*['\"]([A-Z0-9]{10,30})['\"]")),
    ("pinterest", re.compile(r"pintrk\(\s*['\"]load['\"]\s*,\s*['\"]?(\d{6,20})")),
    ("clarity", re.compile(r"clarity\.ms/tag/([a-z0-9]{6,16})")),
    ("snapchat", re.compile(r"snaptr\(\s*['\"]init['\"]\s*,\s*['\"]([0-9a-f-]{36})['\"]")),
    ("linkedin", re.compile(r"_linkedin_partner_id\s*=\s*['\"]?(\d{4,12})")),
    ("klaviyo", re.compile(r"klaviyo[\w./-]*[?&]company_id=([A-Za-z0-9]{6})\b")),
]

#: Schlüssel in einer Pixel- oder Embed-Konfiguration, deren Wert eine Kennung ist.
_CONFIG_KEYS = {
    "pixel_id": "meta", "pixelid": "meta", "facebook_pixel_id": "meta", "fb_pixel_id": "meta",
    "pixelcode": "tiktok", "pixel_code": "tiktok", "tiktok_pixel_id": "tiktok",
    "pinterest_tag_id": "pinterest", "tagid_pinterest": "pinterest",
    "uet_tag_id": "uet", "clarity_project_id": "clarity",
}

KIND_PREFIX = {
    "meta": "META", "tiktok": "TIKTOK", "pinterest": "PINTEREST", "uet": "UET",
    "clarity": "CLARITY", "snapchat": "SNAP", "linkedin": "LINKEDIN", "klaviyo": "KLAVIYO",
}

#: Messziel-Art zu Dienst in `reference/theme-migration/hosts.json`.
KIND_SERVICE = {
    "ga4": "google_analytics", "google_tag": "google_tag", "google_ads": "google_ads",
    "ua": "google_analytics", "floodlight": "google_marketing_platform", "meta": "meta",
    "tiktok": "tiktok", "pinterest": "pinterest", "uet": "microsoft_ads", "clarity": "microsoft_clarity",
    "snapchat": "snapchat", "linkedin": "linkedin", "klaviyo": "klaviyo",
}


def _target(kind: str, value: str, label: str | None = None) -> dict:
    if kind in KIND_PREFIX:
        target_id = f"{KIND_PREFIX[kind]}:{value}"
    else:
        target_id = value
    out = {"target_id": target_id, "kind": kind}
    if label:
        out["label"] = label
    return out


def _dedupe(targets: list[dict]) -> list[dict]:
    seen, out = set(), []
    for item in targets:
        key = (item["target_id"], item.get("label"))
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out


def find_targets(text: str) -> list[dict]:
    """Alle Messziele in einem Text (Code, URL, Konfiguration als Text).

    Rückgabe in Fundreihenfolge, ohne Doppel: `[{"target_id": "AW-123456789",
    "kind": "google_ads", "label": "abc"}, ...]`.
    """
    if not text:
        return []
    found = []
    for match in _GA4.finditer(text):
        found.append((match.start(), _target("ga4", match.group(0))))
    for match in _GT.finditer(text):
        found.append((match.start(), _target("google_tag", match.group(0))))
    for match in _AW.finditer(text):
        found.append((match.start(), _target("google_ads", f"AW-{match.group(1)}", match.group(2))))
    for match in _UA.finditer(text):
        found.append((match.start(), _target("ua", match.group(0))))
    for match in _DC.finditer(text):
        found.append((match.start(), _target("floodlight", f"DC-{match.group(1)}")))
    for kind, pattern in _CODE_PATTERNS:
        for match in pattern.finditer(text):
            found.append((match.start(), _target(kind, match.group(1))))
    # `ti: "…"` ist nur im Umfeld von UET eine Kennung, sonst träfe es jedes
    # Objekt mit einem Schlüssel `ti`.
    if "uetq" in text or "bat.bing." in text:
        for match in _UET.finditer(text):
            found.append((match.start(), _target("uet", match.group(1))))
    found.sort(key=lambda pair: pair[0])
    return _dedupe([item for _, item in found])


def container_ids(text: str) -> list[str]:
    """Alle Tag-Manager-Container `GTM-…` in einem Text, sortiert und ohne Doppel."""
    return sorted(set(_GTM.findall(text or "")))


def config_targets(config) -> list[dict]:
    """Messziele aus einer geparsten Konfiguration (Pixel, App-Embed).

    Erst jeder Text darin über `find_targets`, dann bekannte Schlüssel wie
    `pixel_id`, deren Wert eine nackte Zahl ist und im Text kein Muster hätte.
    """
    found = []

    def walk(node, key=None):
        if isinstance(node, dict):
            for child_key, value in node.items():
                walk(value, str(child_key))
        elif isinstance(node, list):
            for value in node:
                walk(value, key)
        elif isinstance(node, (str, int)) and not isinstance(node, bool):
            text = str(node)
            found.extend(find_targets(text))
            kind = _CONFIG_KEYS.get((key or "").lower().replace("-", "_"))
            if kind and re.fullmatch(r"[A-Za-z0-9-]{4,40}", text):
                found.append(_target(kind, text))

    walk(config)
    return _dedupe(found)


def config_events(config) -> list[tuple[str, list[dict]]]:
    """Je Event die Messziele, an die eine Konfiguration es schickt.

    Gemeint ist die Form `{"gtag_events": [{"type": "purchase", "action_label":
    ["G-…", "AW-…/label"]}]}`: ein Objekt mit einem Event-Namen und Kennungen
    daneben. Welche Events ein Absender an ein Ziel schickt, steht genau dort und
    nicht in der Liste der Kennungen; ein Ziel kann ein Event bekommen und ein
    anderes nicht.
    """
    pairs = []

    def walk(node):
        if isinstance(node, dict):
            name = None
            for key in ("type", "event", "event_name", "eventName", "name"):
                if isinstance(node.get(key), str) and node.get(key):
                    name = node[key]
                    break
            if name is not None:
                rest = {k: v for k, v in node.items() if k not in ("type", "event", "event_name", "eventName", "name")}
                targets = config_targets(rest)
                if targets:
                    pairs.append((name, targets))
                    return
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(config)
    return pairs


#: Events, die ein Theme-Code direkt auslöst, je Art des Aufrufs.
_CODE_EVENTS = [
    re.compile(r"gtag\(\s*['\"]event['\"]\s*,\s*['\"]([\w.-]+)['\"]"),
    re.compile(r"fbq\(\s*['\"]track(?:Custom)?['\"]\s*,\s*['\"]([\w.-]+)['\"]"),
    re.compile(r"ttq\.track\(\s*['\"]([\w.-]+)['\"]"),
    re.compile(r"pintrk\(\s*['\"]track['\"]\s*,\s*['\"]([\w.-]+)['\"]"),
    re.compile(r"_learnq\.push\(\s*\[\s*['\"]track['\"]\s*,\s*['\"]([^'\"]{1,60})['\"]"),
    re.compile(r"dataLayer\.push\(\s*\{[^}]{0,200}?['\"]?event['\"]?\s*:\s*['\"]([\w.-]+)['\"]"),
]


def code_events(text: str) -> list[str]:
    """Event-Namen, die ein Stück Theme-Code selbst auslöst, sortiert."""
    events = set()
    for pattern in _CODE_EVENTS:
        events.update(pattern.findall(text or ""))
    if re.search(r"gtag\(\s*['\"]config['\"]\s*,\s*['\"]G-", text or "") and "send_page_view" not in (text or ""):
        # gtag('config', 'G-…') schickt den page_view selbst, ohne eigenen Aufruf.
        events.add("page_view")
    return sorted(events)


# ---------------------------------------------------------------------------
# Anfragen aus dem Netzwerk-Mitschnitt
# ---------------------------------------------------------------------------

def _query(url: str) -> dict:
    return {k: v[-1] for k, v in parse_qs(urlparse(url).query, keep_blank_values=True).items()}


def _post_lines(post: str | None) -> list[dict]:
    """GA4 bündelt mehrere Events in einem POST, eine Zeile je Event."""
    if not post:
        return []
    out = []
    for line in post.splitlines():
        if "=" in line and "{" not in line[:2]:
            out.append({k: v[-1] for k, v in parse_qs(line, keep_blank_values=True).items()})
    return out


def _post_json(post: str | None):
    if not post or post.lstrip()[:1] not in ("{", "["):
        return None
    try:
        return json.loads(post)
    except ValueError:
        return None


def request_targets(url: str, post: str | None = None) -> list[dict]:
    """Messziele und Events einer einzelnen Anfrage.

    Rückgabe: `[{"target_id", "kind", "events": [...], "label"?}]`. Erkannt
    werden die Sammelstellen der verbreiteten Dienste (GA4 `…/g/collect`,
    Google-Ads-Conversion-Pfade, Meta `/tr`, UET `/action/`, TikTok, Pinterest,
    Clarity); jede andere Anfrage liefert nur die Kennungen aus ihrer URL, ohne
    Event.
    """
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    path = parsed.path
    query = _query(url)
    out = []

    if "google-analytics.com" in host or host == "analytics.google.com" or path.endswith("/g/collect"):
        events = [query["en"]] if query.get("en") else []
        events += [line["en"] for line in _post_lines(post) if line.get("en")]
        if query.get("tid"):
            out.append({**_target("ga4", query["tid"]), "events": sorted(set(events))})
    conversion = re.search(r"/pagead/(?:conversion|viewthroughconversion|1p-conversion|1p-user-list)/(\d{6,12})", path)
    if conversion:
        label = query.get("label")
        event = "conversion" if "conversion" in path and "viewthrough" not in path else "remarketing"
        out.append({**_target("google_ads", f"AW-{conversion.group(1)}", label), "events": [event]})
    if host.endswith("facebook.com") and path.rstrip("/").endswith("/tr") and query.get("id"):
        out.append({**_target("meta", query["id"]), "events": [query["ev"]] if query.get("ev") else []})
    if host.startswith("bat.bing.") and query.get("ti"):
        event = query.get("ea") or query.get("evt") or ""
        out.append({**_target("uet", query["ti"]), "events": [event] if event else []})
    if host.endswith("pinterest.com") and query.get("tid"):
        out.append({**_target("pinterest", query["tid"]), "events": [query["event"]] if query.get("event") else []})
    if "tiktok" in host:
        body = _post_json(post)
        code = query.get("sdkid")
        event = None
        if isinstance(body, dict):
            code = code or ((body.get("context") or {}).get("pixel") or {}).get("code")
            event = body.get("event")
        if code:
            out.append({**_target("tiktok", code), "events": [event] if event else []})
    clarity = re.search(r"clarity\.ms/tag/([a-z0-9]{6,16})", host + path)
    if clarity:
        out.append({**_target("clarity", clarity.group(1)), "events": []})

    known = {item["target_id"] for item in out}
    for item in find_targets(url):
        if item["target_id"] not in known:
            out.append({**item, "events": []})
            known.add(item["target_id"])
    return out


def sends_data(method: str, resource_type: str, url: str) -> bool:
    """Ob eine Anfrage Daten verschickt und nicht nur etwas lädt.

    POST, Beacon und Ping senden immer; ein Bild, `fetch` oder `xhr` mit
    Query-String gilt als Messaufruf. Ein Skript mit `?id=` lädt nur.
    """
    if (method or "").upper() == "POST":
        return True
    kind = (resource_type or "").lower()
    if kind in ("beacon", "ping"):
        return True
    if kind in ("image", "xhr", "fetch", "other") and urlparse(url).query:
        return True
    return False
