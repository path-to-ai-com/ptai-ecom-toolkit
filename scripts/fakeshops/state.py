#!/usr/bin/env python3
"""Die eine Liste je Marke: welche Domains bekannt sind und wo jede Meldung steht.

Liegt im Kundenordner unter `fakeshops/fakeshops.json`. Jeder Lauf schreibt
hinein (`merge`), die Meldungen lesen daraus (`takedown`), der nächste Lauf
prüft gegen sie, ob ein gemeldeter Shop weg ist. Kein zweiter Stand in
Berichten: die sind Ansichten auf diese Datei (CLAUDE.md, Offene Punkte).

Meldestatus je Domain, drei Werte wie in `open_items`, dazu `none`:
- `none`: kein Fake, nichts zu melden
- `open`: Fake bestätigt oder vermutet, Meldung offen oder noch ohne Wirkung
- `done`: Domain gelöscht (NXDOMAIN), Beleg mit Datum
- `deferred`: bewusst zurückgestellt, mit Person, Datum und Grund

CLI:
  python3 -m fakeshops.state merge --state <fakeshops.json> --run <classified.json>
  python3 -m fakeshops.state confirm --state <datei> --domain <d> --category <kategorie> [--note <text>]
  python3 -m fakeshops.state reported --state <datei> --domain <d> --channel <kanal> --to <empfänger>
  python3 -m fakeshops.state defer --state <datei> --domain <d> --by <person> --until <JJJJ-MM-TT> --reason <text>
"""
import argparse
import datetime as dt
import json
import sys
from pathlib import Path

from fakeshops.classify import CATEGORIES

FAKE = {"fake_live", "fake_pending", "fake_unreachable"}
KEEP_FIELDS = ("first_cert", "last_cert", "http_status", "final_url", "dns", "ip", "asn", "network", "nameservers",
               "category", "category_label", "reasons", "keyword")
# Seitenmerkmale gelten nur, wenn die Seite geantwortet hat. Antwortet ein Fake nicht
# (am 29.10.2026 alle, weil sie langsam sind), bleibt der zuletzt gesehene Stand mit
# Datum stehen; sonst ginge der Beleg für die Meldung verloren.
PAGE_FIELDS = ("title", "platform", "legal_notice", "discount")
# RDAP drosselt; ein leerer Wert überschreibt nie einen bekannten.
CONTACT_FIELDS = ("registrar", "registrar_abuse", "host_abuse", "registered")


def load(path: Path, brand: str = "", own_domains: list | None = None) -> dict:
    if path.exists():
        return json.loads(path.read_text())
    return {"brand": brand, "own_domains": own_domains or [], "updated_at": "", "domains": {}}


def save(state: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = dt.datetime.now().isoformat(timespec="seconds")
    path.write_text(json.dumps(state, indent=1, ensure_ascii=False))


def merge(state: dict, rows: list, today: str) -> dict:
    """Ergebnis eines Laufs übernehmen. Gibt die Änderungen gegenüber dem letzten Lauf zurück.

    Eine Domain, die im Lauf fehlt, bleibt mit ihrem letzten Stand stehen; crt.sh
    liefert höchstens 400 Namen, ein Fehlen heißt also nichts.
    """
    changes = {"new": [], "new_fakes": [], "gone": [], "back_online": [], "open": []}
    for row in rows:
        d = row["domain"]
        entry = state["domains"].get(d)
        if entry is None:
            entry = state["domains"][d] = {"first_seen": today, "history": [], "takedown": {"status": "none", "reports": []}}
            changes["new"].append(d)
        before, before_label = entry.get("category"), entry.get("category_label")
        entry.update({k: row.get(k) for k in KEEP_FIELDS})
        if row.get("http_status") == 200:
            entry.update({k: row.get(k) for k in PAGE_FIELDS})
            entry["last_seen_live"] = today
        entry.update({k: row[k] for k in CONTACT_FIELDS if row.get(k)})
        if entry.get("reviewed") and before in FAKE and row["category"] == "unclear":
            # Ein bestätigter Fake wird nicht durch ein schwächeres Vorurteil zurückgestuft.
            entry["category"], entry["category_label"] = before, before_label
        entry["last_checked"] = today
        if not entry["history"] or entry["history"][-1]["category"] != entry["category"]:
            entry["history"].append({"at": today, "category": entry["category"]})
        td = entry["takedown"]
        if entry["category"] in FAKE and td["status"] == "none":
            td["status"] = "open"
            changes["new_fakes"].append(d)
        elif entry["category"] == "taken_down" and td["status"] == "open":
            td.update({"status": "done", "evidence": f"NXDOMAIN am {today}"})
            changes["gone"].append(d)
        elif entry["category"] in FAKE and td["status"] == "done":
            td.update({"status": "open", "evidence": f"wieder erreichbar am {today}", "reopened_at": today})
            changes["back_online"].append(d)
        if td["status"] == "open":
            changes["open"].append(d)
    return changes


def confirm(state: dict, domain: str, category: str, note: str = "") -> dict:
    """Urteil nach Ansicht im Skill festhalten; überschreibt das Vorurteil der Regeln."""
    entry = state["domains"][domain]
    # Die Beschriftung gehört zur Kategorie; bis 29.10.2026 blieb sie beim Vorurteil stehen und
    # der Bericht führte einen bestätigten Fake weiter als "Unklar, ansehen" (PAT-590).
    entry.update({"category": category, "category_label": CATEGORIES[category], "reviewed": True,
                  "review_note": note})
    if category in FAKE and entry["takedown"]["status"] == "none":
        entry["takedown"]["status"] = "open"
    if category not in FAKE and entry["takedown"]["status"] == "open" and not entry["takedown"]["reports"]:
        entry["takedown"]["status"] = "none"
    return entry


def reported(state: dict, domain: str, channel: str, to: str, today: str) -> dict:
    td = state["domains"][domain]["takedown"]
    td["reports"].append({"at": today, "channel": channel, "to": to})
    return td


def defer(state: dict, domain: str, by: str, until: str, reason: str) -> dict:
    td = state["domains"][domain]["takedown"]
    td.update({"status": "deferred", "deferred_by": by, "deferred_until": until, "reason": reason})
    return td


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Liste der Fake-Shops je Marke")
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("merge"); m.add_argument("--state", required=True); m.add_argument("--run", required=True)
    c = sub.add_parser("confirm"); c.add_argument("--state", required=True); c.add_argument("--domain", required=True)
    c.add_argument("--category", required=True); c.add_argument("--note", default="")
    r = sub.add_parser("reported"); r.add_argument("--state", required=True); r.add_argument("--domain", required=True)
    r.add_argument("--channel", required=True); r.add_argument("--to", required=True)
    d = sub.add_parser("defer"); d.add_argument("--state", required=True); d.add_argument("--domain", required=True)
    d.add_argument("--by", required=True); d.add_argument("--until", required=True); d.add_argument("--reason", required=True)
    args = ap.parse_args(argv)
    path = Path(args.state)
    today = dt.date.today().isoformat()
    if args.cmd == "merge":
        run = json.loads(Path(args.run).read_text())
        state = load(path, run["brand"], run["own_domains"])
        out = merge(state, run.get("classified", []), today)
    else:
        state = load(path)
        if args.domain not in state["domains"]:
            print(f"{args.domain} steht nicht in {path}", file=sys.stderr)
            return 1
        if args.cmd == "confirm":
            out = confirm(state, args.domain, args.category, args.note)
        elif args.cmd == "reported":
            out = reported(state, args.domain, args.channel, args.to, today)
        else:
            out = defer(state, args.domain, args.by, args.until, args.reason)
    save(state, path)
    print(json.dumps(out, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
