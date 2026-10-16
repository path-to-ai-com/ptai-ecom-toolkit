#!/usr/bin/env python3
"""Backlinkprofil über die DataForSEO Backlinks API.

Aufruf:
  backlinks_pull.py --target beispielshop.example [--competitors "a,b,c"] \
      --out ... --run-id ... --run-date ... --account-slug ... --budget-cap ... \
      --location-code <code> --language-code <lang> [--sandbox]

Schreibt <out>/dfs-backlinks.json aus sechs Endpunkten.

**Die Liste, nicht nur die Zahl.** Seit 15.10.2026 holt der Pull auch die
Backlinks auf Seiten, die nicht mehr funktionieren, einzeln
(`backlinks/backlinks/live`, `is_broken`). Vorher stand im Audit "37 defekte
Backlinks", und die Marke wusste nicht, welche; die Liste lag nur in unserem
Werkzeug. Sie geht als `items/<befund>.csv` an die Maßnahme
(`audit.readiness items`).

**Der Benchmark gegen Semrush und Ahrefs hat hier eine Lücke benannt**
(Endpoint-Bewertung vom 12.08.2026): rohe Backlink-Zahlen sagen wenig, den
Ausschlag geben dort der **normalisierte Autoritäts-Score** und der
**Toxizitäts-Score**. Im Testfall lag der Autoritäts-Score der Brand hinter den
Wettbewerbern, aber aufholbar; der Toxizitäts-Score dagegen war der höchste im
Feld. Daraus folgt eine **andere Maßnahme** als aus "zu wenig Autorität": erst
das Profil bereinigen, dann aufbauen. Ohne die zweite Kennzahl hätte der Report
die falsche Empfehlung gegeben, und zwar mit Zahlen belegt.

Gegen echte Antworten geprüft (07.09.2026, Fixtures in
`scripts/tests/fixtures/dfs/`). Dabei kam heraus, dass es das Feld `dofollow`
gar nicht gibt, siehe `_follows()`.
"""
import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
import dfs_client  # noqa: E402
from audit import dfs_pull, ledger  # noqa: E402

ENDPOINT_SUMMARY = "backlinks/summary/live"
ENDPOINT_DOMAINS = "backlinks/referring_domains/live"
ENDPOINT_ANCHORS = "backlinks/anchors/live"

#: Die beiden Kennzahlen, die im Semrush/Ahrefs-Benchmark den Ausschlag geben:
#: normalisierter Autoritäts-Score (Skala bis 1.000) und Toxizitäts-Score
#: (0 bis 100). Beide nehmen bis zu fünf Ziele je Aufruf.
ENDPOINT_RANKS = "backlinks/bulk_ranks/live"
ENDPOINT_SPAM = "backlinks/bulk_spam_score/live"

#: Einzelne Backlinks, gefiltert auf die, deren Ziel nicht mehr funktioniert.
#: `mode: as_is` liefert jeden Link, nicht einen je Domain. Am 15.10.2026 für
#: einen Shop mit rund 50 defekten Backlinks rund 0,03 USD.
ENDPOINT_BROKEN = "backlinks/backlinks/live"

MAX_DOMAINS = 200
MAX_ANCHORS = 200
API_LIMIT = 1000


def _normalize(domain) -> str:
    text = str(domain or "").strip().lower()
    return text[4:] if text.startswith("www.") else text


def _items(rows: list) -> list:
    """Die Zeilen eines Ergebnisses aus `result[0].items`.

    Am 07.09.2026 an echten Antworten festgestellt: `referring_domains`,
    `anchors`, `bulk_ranks` und `bulk_spam_score` liefern alle vier
    verschachtelt unter `items`. Nur `summary` ist flach, und das liest
    `shape()` direkt, nicht über diese Funktion.

    Der erste Entwurf las beide Formen, weil keine aufgezeichnete Antwort
    vorlag. Jetzt liegt eine vor, also steht hier die tatsächliche Form: eine
    Funktion, die zwischen zwei Formen rät, verdeckt später eine dritte.
    """
    if not rows or not isinstance(rows[0], dict):
        return []
    return rows[0].get("items") or []


def shape(rows: list, meta: dict) -> dict:
    """Die Kennzahlen des Profils. Leeres Ergebnis heißt null Backlinks."""
    if not rows:
        return {
            "summary": {"backlinks": 0, "referring_domains": 0,
                         "referring_main_domains": 0, "rank": None,
                         "broken_backlinks": 0},
            "notes": ["Backlinks-Summary: keine Daten für dieses Ziel"],
        }
    row = rows[0]
    return {
        "summary": {
            "backlinks": row.get("backlinks"),
            "referring_domains": row.get("referring_domains"),
            "referring_main_domains": row.get("referring_main_domains"),
            "referring_ips": row.get("referring_ips"),
            "rank": row.get("rank"),
            "broken_backlinks": row.get("broken_backlinks"),
            "broken_pages": row.get("broken_pages"),
            "link_types": row.get("referring_links_types"),
            "referring_domains_nofollow": row.get("referring_domains_nofollow"),
        },
        "notes": [],
    }


def _follows(row: dict):
    """Folgt mindestens eine Seite dieser Domain? `None`, wenn unbekannt.

    **Ein Feld `dofollow` gibt es nicht.** Die Items führen `referring_pages`
    und `referring_pages_nofollow`; eine Domain trägt also mindestens einen
    folgenden Link, wenn nicht alle ihre Seiten nofollow sind. Der erste
    Entwurf las ein nicht vorhandenes `dofollow`, bekam immer `falsy` und
    schrieb eine Dofollow-Quote von 0,0 für ein Profil, dessen Links
    ausnahmslos folgen. Plausibel aussehend und zu hundert Prozent falsch.

    Fehlen beide Felder, ist es unbekannt: weder 1 noch 0, sondern `None`.
    """
    pages = row.get("referring_pages")
    nofollow = row.get("referring_pages_nofollow")
    if pages is None and nofollow is None:
        return None
    return int(pages or 0) > int(nofollow or 0)


def shape_domains(rows: list, meta: dict) -> dict:
    """Verweisende Domains, begrenzte Liste plus Quote über die volle Menge."""
    entries = _items(rows)
    known = [_follows(row) for row in entries]
    measurable = [value for value in known if value is not None]
    listed, truncated = dfs_pull.truncate(entries, MAX_DOMAINS)
    return {
        "summary_domains": {
            "referring_domains_returned": len(entries),
            # Ohne messbare Domains gibt es keine Quote. None statt 0, weil
            # eine 0 sich als "keine einzige folgt" liest.
            "dofollow_share": (round(sum(measurable) / len(measurable), 4)
                                if measurable else None),
            "domains_without_follow_data": len(known) - len(measurable),
        },
        "referring_domains_top": [
            {"domain": row.get("domain"), "backlinks": row.get("backlinks"),
             "rank": row.get("rank"), "follows": _follows(row),
             "referring_pages": row.get("referring_pages"),
             "referring_pages_nofollow": row.get("referring_pages_nofollow"),
             "spam_score": row.get("backlinks_spam_score"),
             "first_seen": row.get("first_seen")}
            for row in listed],
        "referring_domains_truncated": truncated,
    }


def shape_anchors(rows: list, meta: dict) -> dict:
    entries = _items(rows)
    listed, truncated = dfs_pull.truncate(entries, MAX_ANCHORS)
    return {
        "summary_anchors": {"anchors_returned": len(entries)},
        "anchors_top": [
            {"anchor": row.get("anchor"), "backlinks": row.get("backlinks"),
             "referring_domains": row.get("referring_domains")}
            for row in listed],
        "anchors_truncated": truncated,
    }


def shape_ranks(rows: list, meta: dict) -> dict:
    """Normalisierter Autoritäts-Score je Domain, Skala bis 1.000.

    Das Äquivalent zu Ahrefs DR und Semrush Authority Score. Er steht neben
    den Wettbewerbern und nie allein: ein Score ohne Vergleichswert ist keine
    Aussage. Die eigene Domain ist markiert, damit die Analyse sie findet.
    """
    own = _normalize(meta.get("target"))
    return {"authority": [
        {"domain": entry.get("target"), "rank": entry.get("rank"),
         "own": bool(own) and _normalize(entry.get("target")) == own}
        for entry in _items(rows)]}


def shape_spam(rows: list, meta: dict) -> dict:
    """Toxizitäts-Score je Domain, 0 bis 100.

    Die Kennzahl, die im Benchmark die Maßnahme umgedreht hat: ein hoher
    eigener Wert heißt "erst bereinigen, dann aufbauen", nicht "mehr Links".
    `None` heißt nicht gemessen, `0` heißt sauber.
    """
    own = _normalize(meta.get("target"))
    return {"spam_score": [
        {"domain": entry.get("target"), "spam_score": entry.get("spam_score"),
         "own": bool(own) and _normalize(entry.get("target")) == own}
        for entry in _items(rows)]}


#: Felder je defektem Backlink: woher, wohin, was das Ziel heute liefert.
BROKEN_FIELDS = ("url_from", "domain_from", "url_to", "url_to_status_code",
                 "url_to_redirect_target", "anchor", "dofollow", "first_seen", "last_seen",
                 "domain_from_rank")


def shape_broken(rows: list, meta: dict) -> dict:
    """Die Backlinks auf defekte Seiten, ungekürzt bis zur Grenze der API.

    Ungekürzt, weil die Marke jeden einzelnen umleiten muss: eine Liste, die
    nicht alles trägt, ist für sie dieselbe Frage wie gar keine. Liefert die
    API weniger, als `total_count` nennt, steht `broken_backlinks_truncated`
    auf true, und `audit.readiness items` verweigert die Liste.
    """
    block = rows[0] if rows and isinstance(rows[0], dict) else {}
    entries = block.get("items") or []
    total = block.get("total_count")
    return {
        "summary_broken": {"total_count": total, "returned": len(entries)},
        "broken_backlinks": [{field: row.get(field) for field in BROKEN_FIELDS}
                             for row in entries if isinstance(row, dict)],
        "broken_backlinks_truncated": bool(total is not None and total > len(entries)),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Backlinkprofil als Snapshot ziehen.")
    parser.add_argument("--target", required=True, help="Domain ohne Protokoll")
    parser.add_argument("--competitors", default="",
                        help="Wettbewerber-Domains für Autoritäts- und "
                             "Toxizitäts-Vergleich, kommagetrennt, höchstens vier")
    dfs_pull.add_common_args(parser)
    args = parser.parse_args()

    client = dfs_pull.build_client(args)
    common = dict(
        workspace=Path(args.workspace), out=Path(args.out), run_id=args.run_id,
        run_date=date.fromisoformat(args.run_date), account_slug=args.account_slug,
        cap=args.budget_cap, pull="backlinks")
    base_task = {"target": args.target, "backlinks_status_type": "live"}

    # Bis zu fünf Ziele je Aufruf: die eigene Domain plus vier Wettbewerber.
    # Ein Autoritäts-Score ohne Vergleichswerte ist eine Zahl ohne Maßstab.
    targets = ([args.target]
               + [d.strip() for d in args.competitors.split(",") if d.strip()])[:5]

    def with_target(shaper):
        return lambda rows, meta: shaper(rows, {**meta, "target": args.target})

    steps = (
        (ENDPOINT_SUMMARY, {**base_task, "internal_list_limit": 10}, shape, False, True),
        (ENDPOINT_DOMAINS, {**base_task, "limit": API_LIMIT}, shape_domains, True, False),
        (ENDPOINT_ANCHORS, {**base_task, "limit": API_LIMIT}, shape_anchors, True, False),
        (ENDPOINT_RANKS, {"targets": targets}, with_target(shape_ranks), True, False),
        (ENDPOINT_SPAM, {"targets": targets}, with_target(shape_spam), True, False),
        (ENDPOINT_BROKEN, {**base_task, "mode": "as_is", "limit": API_LIMIT,
                           "filters": ["is_broken", "=", True]}, shape_broken, True, False),
    )
    written = None
    for endpoint, task, shaper, merge, required in steps:
        try:
            written = dfs_pull.execute(client, endpoint=endpoint, task=task,
                                        shape=shaper, merge=merge, **common)
        except (ledger.BudgetExceeded, dfs_client.DfsError) as exc:
            if required:
                sys.exit(f"Fehler: Backlink-Pull nicht möglich: {exc}")
            print(f"Warnung: {endpoint} nicht gezogen ({exc}), "
                  "Snapshot ohne diesen Teil geschrieben")
    print(f"Geschrieben: {written}")


if __name__ == "__main__":
    main()
