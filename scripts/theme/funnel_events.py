#!/usr/bin/env python3
"""Datenschicht je GA4-Property: kommen view_item, add_to_cart, begin_checkout und purchase an?

Am 11.11.2026 fehlte nach einem Launch auf Horizon `add_to_cart` in einer GA4-Property,
während die serverseitige Littledata-Property weiterzählte; damit fielen auch
Werbe-Zielgruppen und eine Neben-Conversion aus. Ursache: Die eigene Datenschicht
meldete das Hinzufügen erst nach einem zweiten Abruf von `/cart.js`. Mit "Warenkorb
als Seite" leitet Horizon sofort auf `/cart` weiter, und Safari verwarf den
laufenden Abruf. Im Entwurf am Rechner mit schneller Verbindung fiel das nicht auf.

Seitdem gilt zweierlei:

**Durchlauf im Browser, alt gegen neu.** `scripts/browser/walk_checkout.py --headless`
geht Produkt, In den Warenkorb, Warenkorb und Kasse durch, am Handy in WebKit
(`--device mobile`) und mit langsamer Verbindung (`--latency`), auf beiden Themes
(`--theme`). Die Durchläufe liegen unter `migration/verify/<date>/events/<name>/walk.json`
(oder im Ordner eines Launch-Checks unter `events/`). Je GA4-Property (Messkennung
`G-…` in `tid`) und Ereignis gilt: was das alte Theme unter denselben Bedingungen an
die Property sendete, muss das neue auch senden. Fehlt es, ist das ein Befund; ein
abgebrochener Abruf des Warenkorbs beim Seitenwechsel steht als Beleg daneben. Ohne
Durchlauf am Handy mit langsamer Verbindung ist die Prüfung nicht erfüllt. Das liest
Gate G4 (`gate_problems`) und der Launch-Check (`funnel-ga4-<g-id>`).

**Echtzeit je Property nach dem Launch** (`launch_check --after`, `realtime-ga4-<g-id>`).
Die GA4-Echtzeit (Data API `runRealtimeReport`, `eventName` und `eventCount`, letzte
29 Minuten) je Property gegen die Property, die der Shop serverseitig beliefert
(`via`, etwa Littledata), und `purchase` gegen die Bestellungen in Shopify im selben
Fenster. Weil eine Property im Browser nur mit Einwilligung zählt, wird über die
Seitenaufrufe normiert: erwartet ist `referenz_ereignis * eigene_seitenaufrufe /
referenz_seitenaufrufe`. Null bei genug Verkehr ist ein Befund, weniger als die
Hälfte der Erwartung eine Frage, zu wenig Verkehr nicht prüfbar.

Config, je Messkennung die Property-ID (die Messkennung allein kennt die Data API nicht):

    "theme_migration": {"ga4_properties": {
      "G-AAAA": {"property_id": "123456789", "via": "Littledata"},
      "G-BBBB": {"property_id": "987654321"}}}

Nur Standardbibliothek. Schreibt nichts in den Shop und nichts in GA4.
"""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlparse

from theme import migration_config

#: Ereignisse, die der Durchlauf ohne Bestellung belegen kann, in der Reihenfolge des Kaufs.
FUNNEL = ("view_item", "add_to_cart", "begin_checkout")
#: Dazu `purchase` in der Echtzeit, normiert über `page_view`.
REALTIME_EVENTS = FUNNEL + ("purchase", "page_view")
#: Stufen von `walk_checkout.py`, in denen ein Ereignis zählt: ab der Handlung bis vor die nächste.
#: `add_to_cart` darf auch erst auf der nächsten Seite ankommen (Meldung über sessionStorage).
STAGES = {"view_item": ("product", "consent", "add_to_cart"),
          "add_to_cart": ("add_to_cart", "mark", "cart", "checkout"),
          "begin_checkout": ("cart", "checkout", "contact", "shipping", "payment")}
EVENT_LABEL = {"view_item": "view_item", "add_to_cart": "add_to_cart", "begin_checkout": "begin_checkout",
               "purchase": "purchase", "page_view": "page_view"}
#: So alt darf ein Durchlauf sein.
WALK_MAX_AGE = timedelta(days=7)
#: Unter so vielen Ereignissen der Referenz (oder Bestellungen) sagt die Echtzeit nichts.
MIN_REALTIME_BASE = 5
#: Unter diesem Anteil der Erwartung ist eine Property eine Frage wert.
REALTIME_SHARE = 0.5
REALTIME_MINUTES = 29
DEVICE_LABEL = {"desktop": "Rechner", "mobile": "Handy"}
ENGINE_LABEL = {"chromium": "Chromium", "webkit": "Safari/WebKit"}


# ---------------------------------------------------------------------------
# Durchläufe
# ---------------------------------------------------------------------------

def _time(value) -> datetime | None:
    if not value:
        return None
    try:
        stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return stamp if stamp.tzinfo else stamp.replace(tzinfo=timezone.utc)


def profile(walk: dict) -> dict:
    """Bedingungen und Gültigkeit eines Durchlaufs aus `walk.json`."""
    stages = {s.get("stage"): s.get("state") for s in walk.get("stages") or []}
    device = walk.get("device") or "desktop"
    latency = int(walk.get("latency_ms") or 0)
    return {"device": device, "engine": walk.get("engine") or ("webkit" if device == "mobile" else "chromium"),
            "latency_ms": latency, "slow": latency > 0,
            "theme_id": str(((walk.get("theme") or {}).get("id")) or walk.get("theme_requested") or ""),
            "consent": ((walk.get("consent_result") or {}).get("result")),
            "throttled": bool(walk.get("throttle")), "started_at": walk.get("started_at"),
            "add_ok": stages.get("add_to_cart") == "ok", "checkout_ok": stages.get("checkout") == "ok"}


def condition(prof: dict) -> tuple:
    return prof["device"], prof["slow"]


def condition_label(cond: tuple, latency: int | None = None) -> str:
    device, slow = cond
    engine = "Safari/WebKit" if device == "mobile" else "Chromium"
    speed = (f"langsam, {latency} ms" if latency else "langsam") if slow else "schnell"
    return f"{DEVICE_LABEL.get(device, device)} ({engine}, {speed})"


def walk_problem(prof: dict, expected_theme) -> str | None:
    """Warum ein Durchlauf nicht zählt, sonst None."""
    if expected_theme and prof["theme_id"] and str(prof["theme_id"]) != str(expected_theme):
        return f"zeigt Theme {prof['theme_id']} statt {expected_theme}"
    if prof["throttled"]:
        return "von Shopify gedrosselt (HTTP 429), kein Fehler des Shops; langsamer wiederholen"
    if prof["consent"] != "accepted":
        return f"Einwilligung nicht erteilt ({prof['consent'] or 'ohne Ergebnis'}); ohne sie senden Tags nicht"
    if not prof["add_ok"]:
        return "In den Warenkorb gescheitert"
    return None


def find_walks(workspace, extra_dirs=(), now: datetime | None = None) -> list:
    """Durchläufe der Datenschicht der letzten sieben Tage: `[(pfad, walk, profil)]`, jüngster zuerst.

    Gesucht unter `migration/verify/*/events/*/walk.json`, `reporting/runs/*/events/*/walk.json` und in
    `extra_dirs` (je ein Ordner mit `*/walk.json`).
    """
    workspace = Path(workspace)
    now = now or datetime.now(timezone.utc)
    paths = set(workspace.glob("migration/verify/*/events/*/walk.json"))
    paths |= set(workspace.glob("reporting/runs/*/events/*/walk.json"))
    for folder in extra_dirs:
        paths |= set(Path(folder).glob("*/walk.json"))
    out = []
    for path in paths:
        try:
            walk = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(walk, dict) or walk.get("tool") != "walk_checkout":
            continue
        prof = profile(walk)
        started = _time(prof["started_at"])
        if started and now - started > WALK_MAX_AGE:
            continue
        out.append((path, walk, prof))
    return sorted(out, key=lambda item: str(item[2]["started_at"] or ""), reverse=True)


def pick(walks: list, theme_id) -> dict:
    """Je Bedingung der jüngste Durchlauf dieses Themes: `{(gerät, langsam): (pfad, walk, profil)}`."""
    out = {}
    for item in walks:
        prof = item[2]
        if theme_id and str(prof["theme_id"]) != str(theme_id):
            continue
        out.setdefault(condition(prof), item)
    return out


# ---------------------------------------------------------------------------
# GA4-Aufrufe im Durchlauf
# ---------------------------------------------------------------------------

def _lines(body: str) -> list:
    return [dict(parse_qsl(line, keep_blank_values=True)) for line in (body or "").splitlines() if "=" in line]


def ga4_events(requests: list) -> list:
    """Jedes GA4-Ereignis in den Anfragen: `{"tid", "en", "stage", "delivered", "failure"}`.

    Erkannt an `/g/collect` mit einer Messkennung `G-…`, auch über eine eigene Subdomain (Server-Side-Tagging).
    GA4 bündelt mehrere Ereignisse in einem POST, je Zeile eines.
    """
    out = []
    for request in requests or []:
        url = request.get("url") or ""
        parsed = urlparse(url)
        if not parsed.path.endswith("/g/collect"):
            continue
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        status = request.get("status")
        delivered = not request.get("failure") and (status is None or 200 <= int(status) < 400)
        for event in [dict(query, **line) for line in _lines(request.get("post_data") or "")] or [query]:
            tid = str(event.get("tid") or "").upper()
            if not tid.startswith("G-") or not event.get("en"):
                continue
            out.append({"tid": tid, "en": event["en"], "stage": request.get("stage"), "delivered": delivered,
                        "failure": request.get("failure") or (status if not delivered else None)})
    return out


def counts(walk: dict) -> dict:
    """`{tid: {ereignis: {"delivered": n, "failed": n}}}` je Ereignis des Kaufwegs, nur in seinen Stufen."""
    out = {}
    for hit in ga4_events(walk.get("requests")):
        if hit["en"] not in STAGES or hit["stage"] not in STAGES[hit["en"]]:
            continue
        slot = out.setdefault(hit["tid"], {}).setdefault(hit["en"], {"delivered": 0, "failed": 0})
        slot["delivered" if hit["delivered"] else "failed"] += 1
    return out


def aborted_cart(walk: dict) -> list:
    """Abgebrochene Abrufe des Warenkorbs beim Hinzufügen: `GET /cart.js (cancelled)`.

    Genau das war die Spur am 11.11.2026: der zweite Abruf von `/cart.js` lief noch, als die Seite wechselte.
    """
    out = []
    for request in walk.get("requests") or []:
        path = urlparse(request.get("url") or "").path
        if request.get("stage") in STAGES["add_to_cart"] and request.get("failure") and path.startswith("/cart"):
            out.append(f"{request.get('method') or 'GET'} {path} ({str(request['failure'])[:40]})")
    return list(dict.fromkeys(out))


# ---------------------------------------------------------------------------
# Alt gegen neu
# ---------------------------------------------------------------------------

def compare(old_walks: dict, new_walks: dict, old_id=None, new_id=None) -> dict:
    """Vergleich je Bedingung, Property und Ereignis.

    Liefert `{"properties": {tid: [eintrag]}, "conditions": [...], "blocked": [grund], "mobile_slow": bool}`;
    ein Eintrag ist `{"condition", "event", "old", "new", "aborted"}` für jedes Ereignis, das alt ankam.
    """
    result = {"properties": {}, "conditions": [], "blocked": [], "mobile_slow": False}
    for cond, (path, walk, prof) in sorted(new_walks.items()):
        label = condition_label(cond, prof["latency_ms"])
        problem = walk_problem(prof, new_id)
        if problem:
            result["blocked"].append(f"{label}, neues Theme: {problem}")
            continue
        old = old_walks.get(cond)
        if not old:
            result["blocked"].append(f"{label}: kein Durchlauf des alten Themes unter denselben Bedingungen")
            continue
        old_problem = walk_problem(old[2], old_id)
        if old_problem:
            result["blocked"].append(f"{label}, altes Theme: {old_problem}")
            continue
        before, after = counts(old[1]), counts(walk)
        aborted = aborted_cart(walk)
        result["conditions"].append({"condition": cond, "label": label, "aborted": aborted,
                                     "old": str(old[0]), "new": str(path)})
        if cond == ("mobile", True):
            result["mobile_slow"] = True
        for tid in sorted(set(before) | set(after)):
            for event in FUNNEL:
                o = (before.get(tid) or {}).get(event, {}).get("delivered", 0)
                n = (after.get(tid) or {}).get(event, {}).get("delivered", 0)
                if o or n:
                    result["properties"].setdefault(tid, []).append(
                        {"condition": label, "event": event, "old": o, "new": n,
                         "failed": (after.get(tid) or {}).get(event, {}).get("failed", 0), "aborted": aborted})
    return result


def property_verdict(entries: list, mobile_slow: bool) -> tuple:
    """`(status, beleg)` einer Property: `missing`, `blocked` oder `ok`."""
    lost = [e for e in entries if e["old"] and not e["new"]]
    parts = []
    for e in entries:
        mark = "fehlt" if e["old"] and not e["new"] else "ok"
        detail = f"alt {e['old']}, neu {e['new']}" + (f", {e['failed']} gescheitert" if e.get("failed") else "")
        parts.append(f"{e['condition']}: {e['event']} {mark} ({detail})")
    evidence = "; ".join(parts)
    aborted = sorted({a for e in lost for a in e.get("aborted") or []})
    if aborted:
        evidence += "; beim Seitenwechsel abgebrochen: " + ", ".join(aborted[:3])
    if lost:
        return "missing", evidence
    if not mobile_slow:
        return "blocked", evidence + "; kein gültiger Durchlauf am Handy mit langsamer Verbindung"
    return "ok", evidence


def walk_commands(old_id, new_id, base: str = "migration/verify/<date>/events") -> str:
    """Die Aufrufe für die fehlenden Durchläufe, alt und neu am Handy mit langsamer Verbindung."""
    lines = []
    for side, theme in (("old", old_id or "<live-theme-id>"), ("new", new_id or "<draft-theme-id>")):
        lines.append(f"walk_checkout.py --headless --device mobile --latency 800 --theme {theme} "
                     f"--out {base}/{side}-mobile-slow --approved-by <Name>")
    return "; ".join(lines)


def gate_problems(workspace, config: dict, values: dict | None = None) -> list:
    """Sätze für Gate G4: Datenschicht des Entwurfs gegen das Live-Theme, am Handy mit langsamer Verbindung."""
    values = values or {}
    block = migration_config(config)
    live = block.get("live_theme_id") or values.get("live_theme_id")
    draft = block.get("draft_theme_id") or values.get("draft_theme_id")
    walks = find_walks(workspace)
    result = compare(pick(walks, live), pick(walks, draft), live, draft)
    problems = []
    lost = {tid: [e for e in entries if e["old"] and not e["new"]] for tid, entries in result["properties"].items()}
    lost = {tid: entries for tid, entries in lost.items() if entries}
    if lost:
        problems.append("Datenschicht: im Entwurf fehlen Ereignisse je GA4-Property: " + "; ".join(
            f"{tid} {', '.join(sorted({e['event'] for e in entries}))} ({entries[0]['condition']})"
            for tid, entries in sorted(lost.items())))
    if not result["mobile_slow"]:
        reason = "; ".join(result["blocked"][:3]) or "kein Durchlauf"
        problems.append(f"Datenschicht am Handy (Safari) mit langsamer Verbindung nicht belegt ({reason}); "
                        + walk_commands(live, draft))
    return problems


# ---------------------------------------------------------------------------
# Echtzeit je Property
# ---------------------------------------------------------------------------

def configured_properties(config: dict) -> dict:
    """`theme_migration.ga4_properties` als `{"G-…": {"property_id", "via"}}`, leer ohne Eintrag."""
    raw = migration_config(config).get("ga4_properties")
    if not isinstance(raw, dict):
        return {}
    out = {}
    for g_id, spec in raw.items():
        spec = spec if isinstance(spec, dict) else {"property_id": spec}
        prop = str(spec.get("property_id") or "").strip()
        if str(g_id).upper().startswith("G-") and prop:
            out[str(g_id).upper()] = {"property_id": prop, "via": spec.get("via") or None}
    return out


def realtime_verdict(own: dict, reference: dict | None, orders: int | None, *,
                     base_min: int = MIN_REALTIME_BASE, share: float = REALTIME_SHARE) -> tuple:
    """`(status, beleg, auffällig)` einer Property aus den Echtzeit-Zahlen.

    `own` und `reference` sind `{ereignis: anzahl}`; `orders` die Bestellungen im selben Fenster. Ohne
    Referenz (die Property ist selbst die Referenz) zählt nur `purchase` gegen die Bestellungen.
    """
    scale = None
    if reference and reference.get("page_view") and own.get("page_view"):
        scale = own["page_view"] / reference["page_view"]
    rows = []  # (ereignis, wert, basis, herkunft der basis, erwartung)
    for event in FUNNEL if reference is not None else ():
        base = int(reference.get(event, 0))
        rows.append((event, int(own.get(event, 0)), base, "Referenz", base * scale if scale is not None else base))
    if orders is not None:
        rows.append(("purchase", int(own.get("purchase", 0)), int(orders), "Bestellungen",
                     orders * scale if scale is not None else orders))
    elif reference is not None:
        base = int(reference.get("purchase", 0))
        rows.append(("purchase", int(own.get("purchase", 0)), base, "Referenz",
                     base * scale if scale is not None else base))
    if not rows:
        return "blocked", "keine Vergleichsgröße: weder Referenz-Property noch Bestellungen", []
    evidence = "; ".join(f"{e} {v} ({label} {b})" for e, v, b, label, _ in rows)
    if scale is not None:
        evidence += f"; normiert über page_view (Anteil {scale:.2f})"
    lost = [e for e, v, b, _, _ in rows if b >= base_min and v == 0]
    low = [f"{e} {v} statt etwa {round(x)}" for e, v, b, _, x in rows if b >= base_min and v and v < share * x]
    thin = [f"{e} ({label} {b})" for e, v, b, label, _ in rows if b < base_min]
    if lost:
        return "missing", f"in den letzten {REALTIME_MINUTES} Minuten keine {', '.join(lost)}; {evidence}", low
    if low:
        return "manual", evidence, low
    if len(thin) == len(rows):
        return "blocked", f"zu wenig Verkehr für einen Abgleich: {', '.join(thin)}; {evidence}", low
    return "ok", evidence + (f"; zu wenig Verkehr für {', '.join(thin)}" if thin else ""), low
