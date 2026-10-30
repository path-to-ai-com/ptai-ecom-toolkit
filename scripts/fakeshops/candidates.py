#!/usr/bin/env python3
"""Kandidaten aus den Zertifikatslogs: Domains, deren Name mit der Marke beginnt.

Jeder Shop braucht ein TLS-Zertifikat, und jedes Zertifikat steht innerhalb von
Minuten in den öffentlichen Certificate-Transparency-Logs. crt.sh macht sie über
eine öffentliche Postgres-Datenbank durchsuchbar. Die Web-Suche mit `%marke%`
lieferte am 28.10.2026 leere Ergebnisse, die Datenbank mit Präfixsuche dagegen
alle Treffer. Deshalb `psql` und nicht HTTP.

Grenzen, bewusst hingenommen:
- Präfixsuche: gefunden wird `marke...` und `marke.fremd.tld`, nicht `shop-marke.tld`.
- crt.sh verträgt eine Abfrage zur Zeit; parallele Abfragen sperren kurz
  (Connection refused, max_client_conn). Darum nacheinander und mit Wartezeit.
- Höchstens 400 Namen je Stichwort, neueste zuerst. Bei allgemeinen Namen
  (ein Wort aus dem Wörterbuch) reicht das nicht weit zurück.

CLI:
  python3 -m fakeshops.candidates --brand "<Marke>" --domain <eigene-domain> [--domain ...]
      [--keyword <stichwort>] [--since JJJJ-MM-TT] --out <datei.json>

Exit-Code: 0 mit Ergebnis, 1 Aufruf falsch, 2 keine Abfrage erfolgreich.
"""
import argparse
import datetime as dt
import json
import re
import shutil
import subprocess
import sys
import time
import unicodedata

# Zweistufige Endungen, bei denen die registrierte Domain drei Labels hat.
SECOND_LEVEL = {"co", "com", "net", "org", "gov", "ac", "edu"}

# Dienste, deren Subdomains jeder anlegen kann; der Markenname dort sagt nichts
# über den Betreiber der Hauptdomain.
SHARED_HOSTS = {"cloudflaressl.com", "workers.dev", "pages.dev", "chatgpt.site", "myshopify.com"}

KEYWORD_RX = re.compile(r"^[a-z0-9-]{3,40}$")
ROW_LIMIT = 400


def normalize(text: str) -> str:
    """Markenname zu Stichwort: Kleinbuchstaben, Umlaute ausgeschrieben, nur a-z0-9."""
    text = text.lower().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", text)


def registered_domain(host: str) -> str:
    """Registrierte Domain eines Hostnamens, etwa `shop.beispiel.co.uk` zu `beispiel.co.uk`."""
    labels = host.lower().strip(".").lstrip("*.").split(".")
    if len(labels) > 2 and labels[-2] in SECOND_LEVEL:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def keywords(brand: str, own_domains: list, extra: list | None = None) -> list:
    """Stichwörter für die Suche: Markenname und erstes Label jeder eigenen Domain."""
    found = []
    for raw in [brand] + [registered_domain(d).split(".")[0] for d in own_domains] + list(extra or []):
        for key in (normalize(raw), raw.lower().strip() if re.fullmatch(r"[a-z0-9-]+", raw.lower().strip()) else ""):
            if key and KEYWORD_RX.match(key) and key not in found:
                found.append(key)
    return found


def query_ct(keyword: str, retries: int = 4, timeout: int = 300) -> tuple:
    """Namen aus crt.sh, deren Hostname mit `keyword` beginnt. Gibt (Zeilen, Fehler) zurück."""
    if not KEYWORD_RX.match(keyword):
        return [], f"Stichwort ungültig: {keyword!r}"
    if not shutil.which("psql"):
        return [], "psql fehlt (Postgres-Client, etwa brew install libpq)"
    sql = (
        "SELECT min(x509_notBefore(cai.certificate))::date, max(x509_notBefore(cai.certificate))::date, "
        "lower(cai.name_value) FROM certificate_and_identities cai "
        f"WHERE to_tsquery('certwatch', '''{keyword}'':*') @@ identities(cai.certificate) "
        f"GROUP BY lower(cai.name_value) ORDER BY 2 DESC LIMIT {ROW_LIMIT};"
    )
    cmd = ["psql", "-h", "crt.sh", "-p", "5432", "-U", "guest", "-d", "certwatch", "-A", "-t", "-F", " ", "-c", sql]
    error = ""
    for attempt in range(retries):
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            error = f"Zeitüberschreitung nach {timeout} s"
        else:
            rows = [line.split() for line in res.stdout.splitlines() if len(line.split()) == 3]
            if res.returncode == 0:
                return rows, ""
            lines = [l.strip() for l in res.stderr.splitlines() if l.strip()]
            error = next((l for l in lines if re.search(r"refused|max_client_conn|timeout|ERROR|FATAL|Fehler", l)), lines[-1] if lines else "psql ohne Meldung")[:200]
        time.sleep(15 * (attempt + 1))
    return [], error


def collect(rows: list, keyword: str, own_domains: list, since: str) -> dict:
    """Zertifikatszeilen zu Kandidaten je Domain zusammenfassen.

    Zeile: (erstes Datum, letztes Datum, Hostname). Kandidat ist die registrierte
    Domain, wenn sie das Stichwort enthält, sonst der Hostname ab dem Label mit
    dem Stichwort (Marke als Subdomain einer fremden Domain). Eigene Domains und
    ihre Subdomains fallen weg, ebenso Kandidaten ohne Zertifikat seit `since`.
    """
    own = {registered_domain(d) for d in own_domains} | {d.lower() for d in own_domains}
    key = keyword.replace("-", "")
    out = {}
    for first, last, host in rows:
        host = host.lstrip("*.")
        reg = registered_domain(host)
        if reg in own or host in own:
            continue
        if key in reg.replace("-", ""):
            name = reg
        else:
            labels = host.split(".")
            hits = [i for i, label in enumerate(labels[:-2]) if key in label.replace("-", "")]
            if not hits or reg in SHARED_HOSTS:
                continue
            name = ".".join(labels[hits[0]:])
        cand = out.setdefault(name, {"domain": name, "keyword": keyword, "first_cert": first, "last_cert": last, "hostnames": []})
        cand["first_cert"] = min(cand["first_cert"], first)
        cand["last_cert"] = max(cand["last_cert"], last)
        if host not in cand["hostnames"]:
            cand["hostnames"].append(host)
    return {k: v for k, v in out.items() if v["last_cert"] >= since}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Kandidaten aus den Zertifikatslogs")
    ap.add_argument("--brand", required=True)
    ap.add_argument("--domain", action="append", default=[], help="eigene Domain, mehrfach")
    ap.add_argument("--keyword", action="append", default=[], help="zusätzliches Stichwort, mehrfach")
    ap.add_argument("--since", default=(dt.date.today() - dt.timedelta(days=365)).isoformat())
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    if not args.domain:
        print("mindestens eine eigene Domain mit --domain angeben", file=sys.stderr)
        return 1
    result = {"brand": args.brand, "own_domains": args.domain, "since": args.since,
              "queried_at": dt.datetime.now().isoformat(timespec="seconds"), "queries": [], "candidates": []}
    merged = {}
    for key in keywords(args.brand, args.domain, args.keyword):
        rows, error = query_ct(key)
        result["queries"].append({"keyword": key, "rows": len(rows), "truncated": len(rows) >= ROW_LIMIT, "error": error})
        print(f"{key}: {len(rows)} Namen" + (f", Fehler: {error}" if error else ""), file=sys.stderr)
        for name, cand in collect(rows, key, args.domain, args.since).items():
            if name in merged:
                merged[name]["hostnames"] = sorted(set(merged[name]["hostnames"]) | set(cand["hostnames"]))
            else:
                merged[name] = cand
    result["candidates"] = sorted(merged.values(), key=lambda c: c["first_cert"], reverse=True)
    with open(args.out, "w") as f:
        json.dump(result, f, indent=1, ensure_ascii=False)
    print(f"{len(result['candidates'])} Kandidaten in {args.out}", file=sys.stderr)
    return 0 if any(not q["error"] for q in result["queries"]) else 2


if __name__ == "__main__":
    sys.exit(main())
