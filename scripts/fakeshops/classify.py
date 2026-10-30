#!/usr/bin/env python3
"""Vorurteil je Domain aus den Merkmalen. Das Urteil fällt danach im Skill.

Die Regeln sortieren vor und begründen jede Einordnung in `reasons`. Jede Domain
in `fake_live`, `fake_pending`, `fake_unreachable` und `unclear` sieht sich der
Skill danach selbst an (Screenshot, Seitentext), bevor sie als Fake gilt.

Herkunft der Signale, Stand 28.10.2026 (sieben Marken geprüft):
- 14 von 15 live Fakes lagen bei AS199242 und hießen `<marke><zusatz>.shop`,
  Zusätze wie pro, hq, co, club, world, store, official, beauty, style.
- Keiner hatte ein Impressum; Streichpreise meist 65 bis 86 Prozent.
- Echte Händler und Weiterleitungen haben ein Impressum oder landen auf der
  eigenen Domain; Namensvettern nennen die Marke kaum.

CLI:
  python3 -m fakeshops.classify --in <probe.json> --out <classified.json>
"""
import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

from fakeshops.candidates import normalize, registered_domain

# Hoster, bei denen schon Fake-Shops dieser Masche lagen. Ergänzen, wenn ein
# bestätigter Fake bei einem neuen Hoster liegt; nie ohne Beleg.
KNOWN_FAKE_ASNS = {"AS199242"}

RISKY_TLDS = {"shop", "store", "top", "online", "sbs", "xyz", "site", "buzz", "cfd", "icu", "click"}
NAME_SUFFIXES = {"pro", "hq", "co", "club", "world", "store", "official", "shop", "online", "outlet", "sale", "sales",
                 "direct", "active", "gear", "sports", "style", "beauty", "bikes", "deals", "eu", "de", "us", "vip"}
PARKING_RX = re.compile(r"domain (is )?for sale|domain kaufen|parked|sedo|dan\.com|parklogic|afternic|domenarium|"
                        r"this domain|redirecting\.\.\.|temporarily unavailable", re.I)

CATEGORIES = {
    "fake_live": "Fake-Shop live",
    "fake_pending": "Fake-Shop im Aufbau",
    "fake_unreachable": "Fake-Netz, nicht erreichbar",
    "taken_down": "Abgeschaltet",
    "redirect_own": "Weiterleitung auf eigene Domain",
    "parked": "Geparkt oder zu verkaufen",
    "unrelated": "Andere Firma oder Händler",
    "unclear": "Unklar, ansehen",
}


def suspicious_name(domain: str, keyword: str) -> bool:
    """Name nach dem Muster der Masche: riskante Endung oder Marke plus typischer Zusatz."""
    reg = registered_domain(domain)
    label, _, tld = reg.partition(".")
    if tld in RISKY_TLDS:
        return True
    rest = label.replace("-", "").replace(keyword.replace("-", ""), "", 1)
    return rest in NAME_SUFFIXES


def classify(row: dict, brand: str, own_domains: list) -> dict:
    """Kategorie und Begründungen für eine geprüfte Domain."""
    reasons = []
    key = row.get("keyword") or normalize(brand)
    known_asn = row.get("asn", "") in KNOWN_FAKE_ASNS
    pattern = suspicious_name(row["domain"], key)
    own = {registered_domain(d) for d in own_domains}
    final_host = urlparse(row.get("final_url") or "").hostname or ""
    title = row.get("title", "")
    brand_in_title = bool(re.search(re.escape(brand.split()[0]), title, re.I)) or normalize(brand) in normalize(title)
    brand_hits = row.get("brand_mentions", 0)
    if known_asn:
        reasons.append(f"Hoster {row['asn']} ist aus früheren Fakes bekannt")
    if pattern:
        reasons.append("Name folgt dem Muster Marke plus Zusatz oder riskante Endung")

    if row.get("dns") == "NXDOMAIN":
        cat = "taken_down" if pattern else "unrelated"
        reasons.append("Domain existiert nicht mehr (NXDOMAIN)")
    elif final_host and registered_domain(final_host) in own:
        cat = "redirect_own"
        reasons.append(f"leitet auf {final_host}")
    elif not row.get("http_status"):
        cat = "fake_unreachable" if known_asn else "unclear"
        reasons.append(f"keine Antwort: {row.get('fetch_error') or 'ohne Meldung'}")
    elif PARKING_RX.search(title) or PARKING_RX.search(row.get("final_url", "")):
        cat = "parked"
        reasons.append("Parkseite oder Domainverkauf")
    elif row.get("under_construction") and (brand_in_title or brand_hits):
        cat = "fake_pending"
        reasons.append("Seite im Aufbau mit Markennamen")
    elif (brand_in_title or brand_hits >= 3) and not row.get("legal_notice"):
        strong = known_asn or pattern or (row.get("discount") or 0) >= 40
        cat = "fake_live" if strong else "unclear"
        reasons.append("Marke im Titel oder mehrfach genannt, kein Impressum")
        if row.get("discount"):
            reasons.append(f"typischer Rabatt {row['discount']} %")
    elif brand_hits == 0 and not brand_in_title:
        cat = "unrelated"
        reasons.append("Seite nennt die Marke nicht")
    else:
        cat = "unclear"
        reasons.append("Marke genannt, Impressum vorhanden oder Signale schwach")
    out = dict(row)
    out.update({"category": cat, "category_label": CATEGORIES[cat], "reasons": reasons, "reviewed": False})
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Vorurteil je Domain")
    ap.add_argument("--in", dest="infile", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    data = json.loads(Path(args.infile).read_text())
    data["classified"] = [classify(r, data["brand"], data["own_domains"]) for r in data.get("probed", [])]
    order = list(CATEGORIES)
    data["classified"].sort(key=lambda r: (order.index(r["category"]), r["first_cert"]))
    Path(args.out).write_text(json.dumps(data, indent=1, ensure_ascii=False))
    counts = {c: sum(1 for r in data["classified"] if r["category"] == c) for c in order}
    print(json.dumps(counts, ensure_ascii=False), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
