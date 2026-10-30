#!/usr/bin/env python3
"""Nachprüfung gemeldeter Fake-Shops: sind sie weg, nicht erreichbar oder noch live?

Braucht nur Python und Netz, kein psql, kein dig, keinen Browser. Gebaut für die
Prüfung einige Tage nach einer Meldung, auch im Container der Paperclip-Agents.
Weg heißt NXDOMAIN; eine Seite, die nicht antwortet, gilt nicht als weg (die
Fakes antworten oft erst nach 20 bis 60 s).

CLI:
  python3 -m fakeshops.recheck --state <fakeshops.json> [--write]
  python3 -m fakeshops.recheck --domain <d> [--domain ...] --brand "<Marke>"
"""
import argparse
import datetime as dt
import json
import sys
from pathlib import Path

from fakeshops import probe

VERDICT = {"gone": "abgeschaltet", "live": "noch live", "unreachable": "antwortet nicht, Domain aktiv"}


def check(domain: str, brand: str) -> dict:
    dns, ip = probe.dns_status(domain)
    if dns == "NXDOMAIN":
        return {"domain": domain, "dns": dns, "ip": "", "http_status": 0, "title": "", "verdict": "gone"}
    status, _, html, error = probe.fetch(domain)
    feats = probe.page_features(html, brand) if html else {"title": "", "brand_mentions": 0}
    live = status == 200 and (feats["brand_mentions"] > 0 or brand.lower() in feats["title"].lower())
    return {"domain": domain, "dns": dns, "ip": ip, "http_status": status, "title": feats["title"],
            "fetch_error": error, "verdict": "live" if live else "unreachable"}


def table(rows: list) -> str:
    out = ["| Domain | Ergebnis | DNS | HTTP | Seitentitel |", "|---|---|---|---|---|"]
    out += [f"| {r['domain']} | {VERDICT[r['verdict']]} | {r['dns']} | {r['http_status'] or '-'} | {r['title'][:60]} |" for r in rows]
    gone = sum(r["verdict"] == "gone" for r in rows)
    return "\n".join(out + ["", f"{gone} von {len(rows)} abgeschaltet."])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Gemeldete Fake-Shops nachprüfen")
    ap.add_argument("--state", default="")
    ap.add_argument("--domain", action="append", default=[])
    ap.add_argument("--brand", default="")
    ap.add_argument("--write", action="store_true", help="Ergebnis in die Liste übernehmen (abgeschaltet heißt done)")
    args = ap.parse_args(argv)
    state = json.loads(Path(args.state).read_text()) if args.state else None
    brand = args.brand or (state or {}).get("brand", "")
    domains = args.domain or [d for d, v in (state or {}).get("domains", {}).items() if v.get("takedown", {}).get("status") == "open"]
    if not domains or not brand:
        print("Domains und Marke angeben, oder --state mit offenen Meldungen", file=sys.stderr)
        return 1
    rows = [check(d, brand) for d in domains]
    print(table(rows))
    if state and args.write:
        today = dt.date.today().isoformat()
        for r in rows:
            e = state["domains"][r["domain"]]
            e.update({"dns": r["dns"], "last_checked": today})
            if r["verdict"] == "gone" and e["takedown"]["status"] == "open":
                e["category"] = "taken_down"
                e["takedown"].update({"status": "done", "evidence": f"NXDOMAIN am {today}"})
                e.setdefault("history", []).append({"at": today, "category": "taken_down"})
        Path(args.state).write_text(json.dumps(state, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
