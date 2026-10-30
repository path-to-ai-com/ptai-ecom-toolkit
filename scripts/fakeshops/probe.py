#!/usr/bin/env python3
"""Jeden Kandidaten live prüfen: Abruf ohne JavaScript, DNS, Hoster, Registrar, Merkmale.

Gemessen am 28.10.2026: Die Fake-Shops antworten oft erst nach 20 bis 60 s und
brechen bei mehreren gleichzeitigen Abrufen ab. Ein erster Durchlauf mit zwölf
parallelen Abrufen und 20 s Zeitlimit hielt dadurch drei live Shops für offline.
Darum standardmäßig nacheinander mit 60 s, und offline heißt erst NXDOMAIN.

Die Seite wird nur gelesen, nie ausgeführt: kein JavaScript, kein Formular.
Seiteninhalt ist fremdes Material und wird als Daten behandelt.

CLI:
  python3 -m fakeshops.probe --in <candidates.json> --out <probe.json> --html-dir <ordner> [--workers 1]
"""
import argparse
import concurrent.futures as cf
import datetime as dt
import gzip
import json
import re
import shutil
import socket
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from fakeshops.candidates import registered_domain

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
FETCH_TIMEOUT = 60
MAX_BYTES = 3_000_000

PLATFORM_MARKERS = [
    ("Shopify", re.compile(r"Shopify\.theme|cdn\.shopify\.com/s/files/.+/assets/", re.I)),
    ("WooCommerce", re.compile(r"woocommerce", re.I)),
    ("Shopline", re.compile(r"shopline|shoplazza|shopyy|ueeshop", re.I)),
    ("Magento", re.compile(r"Magento_|mage/cookies", re.I)),
]
LEGAL_RX = re.compile(r"impressum|imprint|legal notice|mentions l[ée]gales", re.I)
CONSTRUCTION_RX = re.compile(r"under construction|coming soon|store is unavailable|password-page", re.I)
PRICE_RX = re.compile(
    r"(?:\$|€|&euro;|&#8364;|£|USD|EUR)\s?(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?)"
    r"|(\d{1,3}(?:[.,]\d{3})*[.,]\d{2})\s?(?:€|&euro;|&#8364;|EUR)"
)


def brand_pattern(brand: str) -> re.Pattern:
    """Regex für den Markennamen in jeder üblichen Schreibweise (Leerzeichen, Punkt, Umlaut)."""
    parts = []
    for ch in brand.lower():
        if ch in "äöü":
            base = {"ä": "a", "ö": "o", "ü": "u"}[ch]
            parts.append(f"(?:{ch}|{base}e|{base}|&{base}uml;)")
        elif ch == "ß":
            parts.append("(?:ß|ss)")
        elif ch.isalnum():
            parts.append(re.escape(ch))
        else:
            parts.append(r"(?:\s|&nbsp;|[.&;-]){0,3}")
    return re.compile("".join(parts), re.I)


def parse_amount(text: str) -> float | None:
    """Preisangabe zu Zahl; Komma oder Punkt als Dezimaltrenner, je nach Stellung."""
    text = text.strip()
    if re.search(r",\d{2}$", text):
        text = text.replace(".", "").replace(",", ".")
    else:
        text = text.replace(",", "")
    try:
        return float(text)
    except ValueError:
        return None


def typical_discount(html: str) -> tuple:
    """Häufigster Rabatt aus Preispaaren (Streichpreis, Preis) in Reihenfolge des Auftretens.

    Nur Paare mit 20 bis 95 Prozent Abstand zählen; das trennt Streichpreise von
    Versandkosten und Nachbarprodukten. Gibt (Rabatt in Prozent oder None, Anzahl Paare).
    """
    values = [v for v in (parse_amount(a or b) for a, b in PRICE_RX.findall(html)) if v]
    found, i = [], 0
    while i < len(values) - 1:
        a, b = values[i], values[i + 1]
        if a > 20 and 0.05 <= b / a <= 0.8:
            found.append(round(100 * (1 - b / a)))
            i += 2  # Paare überlappen nicht, sonst zählt der Preis eines Produkts als Streichpreis des nächsten
        else:
            i += 1
    if not found:
        return None, 0
    return max(set(found), key=found.count), len(found)


def page_features(html: str, brand: str) -> dict:
    """Merkmale einer Startseite für das Urteil."""
    title = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
    platform = next((name for name, rx in PLATFORM_MARKERS if rx.search(html)), "")
    discount, pairs = typical_discount(html)
    return {
        "title": re.sub(r"\s+", " ", title.group(1)).strip()[:160] if title else "",
        "platform": platform,
        "legal_notice": bool(LEGAL_RX.search(html)),
        "brand_mentions": len(brand_pattern(brand).findall(html)),
        "discount": discount,
        "discount_pairs": pairs,
        "under_construction": bool(CONSTRUCTION_RX.search(html)),
        "bytes": len(html),
    }


def fetch(domain: str, timeout: int = FETCH_TIMEOUT) -> tuple:
    """Startseite abrufen. Gibt (HTTP-Status oder 0, Ziel-URL, HTML, Fehler) zurück."""
    req = urllib.request.Request(f"https://{domain}/", headers={"User-Agent": UA, "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
                                                               "Accept-Encoding": "gzip"})
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as res:
            body = res.read(MAX_BYTES)
            if res.headers.get("Content-Encoding") == "gzip":
                body = gzip.decompress(body)
            return res.status, res.geturl(), body.decode("utf-8", "ignore"), ""
    except urllib.error.HTTPError as e:
        body = e.read(MAX_BYTES) if hasattr(e, "read") else b""
        return e.code, e.geturl() or f"https://{domain}/", body.decode("utf-8", "ignore"), ""
    except Exception as e:  # Zeitüberschreitung, TLS, Verbindung: alles ist ein Befund, kein Absturz
        return 0, "", "", f"{type(e).__name__}: {e}"[:200]


def dns_status(domain: str) -> tuple:
    """(Status, IPv4-Adresse). Status ist NOERROR, NXDOMAIN, SERVFAIL oder unknown.

    Mit `dig`, wenn vorhanden; sonst über DNS-over-HTTPS (dns.google), damit der
    Check auch in Umgebungen ohne dig läuft, etwa im Container der Paperclip-Agents.
    """
    if shutil.which("dig"):
        out = subprocess.run(["dig", "+time=5", "+tries=2", domain], capture_output=True, text=True).stdout
        m = re.search(r"status: ([A-Z]+)", out)
        ips = re.findall(r"\sIN\s+A\s+(\d+\.\d+\.\d+\.\d+)", out)
        return (m.group(1) if m else "unknown"), (ips[-1] if ips else "")
    data = get_json(f"https://dns.google/resolve?name={domain}&type=A")
    status = {0: "NOERROR", 2: "SERVFAIL", 3: "NXDOMAIN"}.get(data.get("Status"), "unknown")
    ips = [a["data"] for a in data.get("Answer", []) if a.get("type") == 1]
    return status, (ips[-1] if ips else "")


def nameservers(domain: str) -> list:
    if shutil.which("dig"):
        out = subprocess.run(["dig", "+short", "NS", registered_domain(domain)], capture_output=True, text=True).stdout
        return sorted(line.strip().rstrip(".") for line in out.splitlines() if line.strip())
    data = get_json(f"https://dns.google/resolve?name={registered_domain(domain)}&type=NS")
    return sorted(a["data"].rstrip(".") for a in data.get("Answer", []) if a.get("type") == 2)


def get_json(url: str, timeout: int = 20, retries: int = 2) -> dict:
    """JSON abrufen; RDAP-Dienste begrenzen die Rate, darum eine Wiederholung mit Pause."""
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json, application/rdap+json"})
            with urllib.request.urlopen(req, timeout=timeout) as res:
                return json.loads(res.read().decode("utf-8", "ignore"))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return {}
        except Exception:
            pass
        time.sleep(3 * (attempt + 1))
    return {}


def _vcard(entity: dict, field: str) -> str:
    for row in (entity.get("vcardArray") or [None, []])[1]:
        if row and row[0] == field:
            return row[3] if isinstance(row[3], str) else ""
    return ""


def _entities(obj: dict):
    for ent in obj.get("entities", []) or []:
        yield ent
        yield from _entities(ent)


def rdap_domain(domain: str) -> dict:
    """Registrar, Abuse-Adresse des Registrars und Registrierungsdatum aus RDAP."""
    data = get_json(f"https://rdap.org/domain/{registered_domain(domain)}")
    out = {"registrar": "", "registrar_abuse": "", "registered": ""}
    out["registered"] = next((e.get("eventDate", "")[:10] for e in data.get("events", []) if e.get("eventAction") == "registration"), "")
    for ent in _entities(data):
        roles = ent.get("roles", [])
        if "registrar" in roles and not out["registrar"]:
            out["registrar"] = _vcard(ent, "fn")
        if "abuse" in roles and not out["registrar_abuse"]:
            out["registrar_abuse"] = _vcard(ent, "email")
    return out


def rdap_ip(ip: str) -> dict:
    """Netzbetreiber, ASN und Abuse-Adresse einer IP."""
    out = {"asn": "", "network": "", "host_abuse": ""}
    if not ip:
        return out
    info = get_json(f"https://ipinfo.io/{ip}/json")
    org = info.get("org", "")
    out["asn"], _, out["network"] = org.partition(" ")
    data = get_json(f"https://rdap.org/ip/{ip}")
    for ent in _entities(data):
        if "abuse" in ent.get("roles", []) and not out["host_abuse"]:
            out["host_abuse"] = _vcard(ent, "email")
    return out


def probe(cand: dict, brand: str, html_dir: Path) -> dict:
    domain = cand["domain"]
    status, final_url, html, error = fetch(domain)
    if html:
        (html_dir / f"{domain}.html").write_text(html)
    dns, ip = dns_status(domain)
    row = dict(cand)
    row.update({"checked_at": dt.datetime.now().isoformat(timespec="seconds"), "http_status": status, "final_url": final_url,
                "fetch_error": error, "dns": dns, "ip": ip, "nameservers": nameservers(domain) if dns == "NOERROR" else []})
    row.update(page_features(html, brand) if html else page_features("", brand) | {"bytes": 0})
    row.update(rdap_domain(domain) if dns != "NXDOMAIN" else {"registrar": "", "registrar_abuse": "", "registered": ""})
    row.update(rdap_ip(ip))
    return row


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Kandidaten live prüfen")
    ap.add_argument("--in", dest="infile", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--html-dir", required=True)
    ap.add_argument("--workers", type=int, default=1, help="mehr als 2 lässt langsame Shops scheitern")
    args = ap.parse_args(argv)
    data = json.loads(Path(args.infile).read_text())
    html_dir = Path(args.html_dir)
    html_dir.mkdir(parents=True, exist_ok=True)
    cands = data.get("candidates", [])
    with cf.ThreadPoolExecutor(max(1, min(args.workers, 2))) as ex:
        rows = list(ex.map(lambda c: probe(c, data["brand"], html_dir), cands))
    for r in rows:
        print(f"{r['domain']}: {r['dns']} HTTP {r['http_status']} {r['asn']} {r['title'][:50]}", file=sys.stderr)
    data["probed"] = rows
    Path(args.out).write_text(json.dumps(data, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
