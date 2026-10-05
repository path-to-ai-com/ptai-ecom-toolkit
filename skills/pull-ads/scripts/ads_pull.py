#!/usr/bin/env python3
"""SEA-Snapshot über die Google Ads API.

Aufruf:
  ads_pull.py --customer-id 123-456-7890 --creds <sa.json> --out <dir> \
      [--login-customer-id <mcc>] [--start YYYY-MM-DD --end YYYY-MM-DD] \
      [--max-history] [--api-version v25]
  ads_pull.py --customer-id ... --creds ... --check

Schreibt <out>/ads.json.

**Seit dem 02.10.2026 gegen ein echtes Konto geprüft**, die Verifikationsliste
in der SKILL.md ist abgearbeitet.

Beträge kommen als Micros und werden umgerechnet. Die Währung steht in
`customer.currency_code` und geht mit in den Snapshot: ein Euro-Betrag aus einem
Konto in Franken wäre eine falsche Zahl, die niemandem auffällt.
"""
import argparse
import json
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
import ads_client  # noqa: E402
from google_token import get_access_token  # noqa: E402

MAX_TERMS = 300
MAX_CAMPAIGNS = 200

#: Startdatum der Historienmessung. Weit vor jedem realistischen Konto; die
#: API liefert für Tage ohne Daten schlicht keine Zeile. Gemessen statt
#: angenommen, wie bei pull-gsc und pull-ga4.
HISTORY_PROBE_START = "2010-01-01"

#: Kampagnen, Anzeigengruppen und Suchbegriffe laufen bei --max-history über die
#: letzten zwölf vollständigen Monate, nicht über die ganze Historie. Die
#: Monatsreihe braucht die Historie, die Frage "wofür geht das Geld heute"
#: nicht: im ersten echten Lauf am 02.10.2026 lieferte ein Konto mit gut zehn
#: Jahren Historie fast eine Million Suchbegriff-Zeilen und mehr als hundert
#: Kampagnen, die meisten seit Jahren entfernt.
#: Volle Monate, damit die Summen genau auf Zeilen von `by_month` passen.
DETAIL_MONTHS = 12


def detail_period(today: date) -> tuple[str, str]:
    """Die letzten DETAIL_MONTHS vollständigen Monate vor `today`."""
    end = today.replace(day=1) - timedelta(days=1)
    year, month = end.year, end.month - DETAIL_MONTHS + 1
    while month < 1:
        year, month = year - 1, month + 12
    return date(year, month, 1).isoformat(), end.isoformat()


def query_campaigns(start: str, end: str) -> str:
    return (
        "SELECT campaign.id, campaign.name, campaign.status, "
        "campaign.advertising_channel_type, segments.date, "
        "metrics.impressions, metrics.clicks, metrics.cost_micros, "
        "metrics.conversions, metrics.conversions_value, "
        "metrics.search_impression_share, "
        "metrics.search_budget_lost_impression_share, "
        "metrics.search_rank_lost_impression_share "
        f"FROM campaign WHERE segments.date BETWEEN '{start}' AND '{end}'")


def query_ad_groups(start: str, end: str) -> str:
    return (
        "SELECT campaign.name, ad_group.id, ad_group.name, ad_group.status, "
        "metrics.impressions, metrics.clicks, metrics.cost_micros, "
        "metrics.conversions, metrics.conversions_value "
        f"FROM ad_group WHERE segments.date BETWEEN '{start}' AND '{end}'")


def query_search_terms(start: str, end: str) -> str:
    return (
        "SELECT search_term_view.search_term, campaign.name, "
        "metrics.impressions, metrics.clicks, metrics.cost_micros, "
        "metrics.conversions, metrics.conversions_value "
        f"FROM search_term_view WHERE segments.date BETWEEN '{start}' AND '{end}'")


def query_history() -> str:
    """Ein Tag je Zeile über die ganze Kontohistorie, nur zum Messen des Anfangs."""
    end = (date.today() - timedelta(days=1)).isoformat()
    return ("SELECT segments.date, metrics.impressions FROM customer "
            f"WHERE segments.date BETWEEN '{HISTORY_PROBE_START}' AND '{end}'")


def query_customer() -> str:
    return ("SELECT customer.id, customer.descriptive_name, customer.currency_code, "
            "customer.time_zone FROM customer")


def _metric(row, name, default=0.0):
    return (row.get("metrics") or {}).get(name, default)


def _number(value, default=0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def by_month(rows: list) -> list:
    """Tageszeilen zu Monaten. Impression Share über die möglichen Impressionen.

    Ein Impression Share ist ein Anteil an den möglichen Impressionen, nicht
    an den tatsächlichen. Der Monatswert ist deshalb Summe der Impressionen
    durch Summe der möglichen (`impressions / share` je Zeile), und die beiden
    Verlustanteile werden mit den möglichen Impressionen gewichtet. Bis zum
    02.10.2026 stand hier ein mit den tatsächlichen Impressionen gewichteter
    Mittelwert, geteilt durch alle Impressionen des Monats, auch die aus
    Zeilen ohne Share. Im ersten echten Lauf ergab das für einen Tag, an dem
    Google den Share noch nicht geliefert hatte, rund 2 Prozent.

    `search_impression_share_coverage` sagt, welcher Anteil der Impressionen
    des Monats aus Zeilen mit Share stammt. Der Share beschreibt nur diesen
    Teil, Display und Demand Gen führen keinen.

    Google liefert Werte unter 10 Prozent als 0,0999 und über 90 Prozent als
    0,9001. Ein Monat mit vielen solchen Zeilen ist entsprechend unscharf.
    """
    buckets = defaultdict(lambda: defaultdict(float))
    for row in rows:
        day = (row.get("segments") or {}).get("date")
        if not day or len(day) < 7:
            continue
        bucket = buckets[day[:7]]
        impressions = _number(_metric(row, "impressions", 0))
        bucket["impressions"] += impressions
        bucket["clicks"] += _number(_metric(row, "clicks", 0))
        bucket["cost_micros"] += _number(_metric(row, "costMicros", 0))
        bucket["conversions"] += _number(_metric(row, "conversions", 0))
        bucket["conversions_value"] += _number(_metric(row, "conversionsValue", 0))
        share = _number(_metric(row, "searchImpressionShare", None), None)
        if share and impressions > 0:
            eligible = impressions / share
            bucket["share_impressions"] += impressions
            bucket["eligible"] += eligible
            for key, field in (("budget_lost", "searchBudgetLostImpressionShare"),
                               ("rank_lost", "searchRankLostImpressionShare")):
                lost = _number(_metric(row, field, None), None)
                if lost is not None:
                    bucket[key] += lost * eligible
                    bucket[key + "_eligible"] += eligible

    months = []
    for month in sorted(buckets):
        bucket = buckets[month]
        cost = round(bucket["cost_micros"] / 1_000_000, 2)
        impressions = bucket["impressions"]
        eligible = bucket["eligible"]
        months.append({
            "month": month,
            "impressions": int(impressions),
            "clicks": int(bucket["clicks"]),
            "cost": cost,
            "conversions": round(bucket["conversions"], 2),
            "conversions_value": round(bucket["conversions_value"], 2),
            # Ein Monat ohne Ausgaben hat keinen ROAS. None statt 0, weil eine
            # 0 sich als "nichts eingebracht" liest.
            "roas": round(bucket["conversions_value"] / cost, 2) if cost else None,
            # Kein Share geliefert heißt kein Impression Share. Eine 0 stünde
            # im Report als "nie ausgeliefert", und das ist etwas anderes.
            "search_impression_share": (round(bucket["share_impressions"] / eligible, 4)
                                         if eligible else None),
            "search_budget_lost_impression_share": _weighted(bucket, "budget_lost"),
            "search_rank_lost_impression_share": _weighted(bucket, "rank_lost"),
            "search_impression_share_coverage": (
                round(bucket["share_impressions"] / impressions, 4) if impressions else None),
        })
    return months


def _weighted(bucket, key):
    """Verlustanteil, gewichtet mit den möglichen Impressionen."""
    base = bucket[key + "_eligible"]
    return round(bucket[key] / base, 4) if base else None


def shape_campaigns(rows: list) -> dict:
    """Kampagnen über den ganzen Zeitraum, teuerste zuerst."""
    buckets = {}
    for row in rows:
        campaign = row.get("campaign") or {}
        name = campaign.get("name")
        entry = buckets.setdefault(name, {
            "name": name, "status": campaign.get("status"),
            "channel_type": campaign.get("advertisingChannelType"),
            "impressions": 0, "clicks": 0, "cost_micros": 0.0,
            "conversions": 0.0, "conversions_value": 0.0})
        entry["impressions"] += int(_number(_metric(row, "impressions", 0)))
        entry["clicks"] += int(_number(_metric(row, "clicks", 0)))
        entry["cost_micros"] += _number(_metric(row, "costMicros", 0))
        entry["conversions"] += _number(_metric(row, "conversions", 0))
        entry["conversions_value"] += _number(_metric(row, "conversionsValue", 0))

    campaigns = []
    for entry in buckets.values():
        cost = round(entry.pop("cost_micros") / 1_000_000, 2)
        entry["cost"] = cost
        entry["conversions"] = round(entry["conversions"], 2)
        entry["conversions_value"] = round(entry["conversions_value"], 2)
        entry["roas"] = round(entry["conversions_value"] / cost, 2) if cost else None
        campaigns.append(entry)
    campaigns.sort(key=lambda c: -c["cost"])
    return {"campaigns": campaigns[:MAX_CAMPAIGNS],
            "campaigns_truncated": len(campaigns) > MAX_CAMPAIGNS,
            "summary_campaigns": {"campaigns_total": len(campaigns)}}


def shape_search_terms(rows: list) -> dict:
    """Suchbegriffe ohne Conversion, absteigend nach verbranntem Betrag.

    Die Summe geht über alle Zeilen, die Liste ist begrenzt. Eine Summe über
    die gekürzte Liste wäre eine andere Zahl mit demselben Namen.
    """
    wasted, total_cost, count, all_cost = [], 0.0, 0, 0.0
    for row in rows:
        cost = ads_client.from_micros(_metric(row, "costMicros", None)) or 0.0
        all_cost += cost
        # Google zählt Conversions als Bruchteile. 0,5 ist eine Conversion.
        if _number(_metric(row, "conversions", 0)) > 0:
            continue
        count += 1
        total_cost += cost
        wasted.append({
            "term": (row.get("searchTermView") or {}).get("searchTerm"),
            "campaign": (row.get("campaign") or {}).get("name"),
            "cost": cost,
            "clicks": int(_number(_metric(row, "clicks", 0))),
            "impressions": int(_number(_metric(row, "impressions", 0)))})
    wasted.sort(key=lambda entry: -entry["cost"])
    return {
        "summary_search_terms": {
            "search_terms_total": len(rows),
            "terms_without_conversion": count,
            "cost_without_conversion": round(total_cost, 2),
            # Die Bezugsgröße für den Anteil. Die Suchbegriff-Ansicht deckt
            # nur Suche und Shopping ab, nicht Performance Max; gegen die
            # Gesamtausgaben gerechnet sähe die Verschwendung kleiner aus,
            # als sie ist.
            "cost_total": round(all_cost, 2)},
        "search_terms_without_conversion": wasted[:MAX_TERMS],
        "search_terms_truncated": len(wasted) > MAX_TERMS}


def history_start(rows: list):
    """Der früheste Tag mit Daten, gemessen statt angenommen."""
    days = [(row.get("segments") or {}).get("date") for row in rows]
    days = [day for day in days if day]
    return min(days) if days else None


def _build_client(args):
    access = get_access_token(args.creds, "adwords")
    return ads_client.Client(args.customer_id, access_token=access,
                              login_customer_id=args.login_customer_id,
                              version=args.api_version)


def main() -> None:
    parser = argparse.ArgumentParser(description="SEA-Snapshot über die Google Ads API ziehen.")
    parser.add_argument("--customer-id", required=True,
                        help="Kundennummer des Werbekontos, mit oder ohne Bindestriche")
    parser.add_argument("--creds", required=True, help="Pfad zum Service-Account-JSON")
    parser.add_argument("--login-customer-id",
                        help="Verwaltungskonto, nur beim Zugriff über ein MCC nötig")
    parser.add_argument("--out", help="Zielverzeichnis für den Snapshot")
    parser.add_argument("--start", help="Start des Zeitraums, YYYY-MM-DD")
    parser.add_argument("--end", help="Ende des Zeitraums, YYYY-MM-DD")
    parser.add_argument("--max-history", action="store_true",
                        help="misst den Kontobeginn und zieht ab da")
    parser.add_argument("--api-version", default=ads_client.DEFAULT_VERSION,
                        help=f"Google-Ads-API-Version (Default {ads_client.DEFAULT_VERSION})")
    parser.add_argument("--check", action="store_true",
                        help="nur Zugang und Währung prüfen, Exit 0/1")
    args = parser.parse_args()

    if not args.check and not args.out:
        parser.error("ohne --check ist --out erforderlich")
    if not args.check and not args.max_history and not (args.start and args.end):
        parser.error("ohne --check entweder --max-history oder --start und --end")

    try:
        client = _build_client(args)
        customer = client.search(query_customer())
    except Exception as exc:
        sys.exit(f"Fehler: Google Ads nicht erreichbar: {exc}")

    info = (customer[0].get("customer") if customer else {}) or {}
    currency = info.get("currencyCode")
    if args.check:
        print(f"OK: Google-Ads-Konto {args.customer_id} erreichbar "
              f"({info.get('descriptiveName')}, Währung {currency})")
        return

    start, end = args.start, args.end
    history_from = None
    if args.max_history:
        history_from = history_start(client.search(query_history()))
        if not history_from:
            sys.exit("Fehler: keine Historie im Konto gefunden")
        start, end = history_from, (date.today() - timedelta(days=1)).isoformat()

    snapshot = {
        "source": "ads",
        "period": {"start": start, "end": end,
                    "granularity": "max_history" if args.max_history else "range"},
        "currency": currency,
        "account": {"id": info.get("id"), "name": info.get("descriptiveName"),
                     "time_zone": info.get("timeZone")},
        "api_version": args.api_version,
    }
    if history_from:
        snapshot["history_from"] = history_from

    # Nur die Kampagnen sind fatal: ohne sie gibt es keine SEA-Baseline. Die
    # übrigen Blöcke scheitern isoliert, wie sitemaps in gsc_pull.py.
    try:
        campaign_rows = client.search(query_campaigns(start, end))
    except ads_client.AdsError as exc:
        sys.exit(f"Fehler: Kampagnen nicht abrufbar: {exc}")
    snapshot["by_month"] = by_month(campaign_rows)

    # Struktur und Suchbegriffe über den Detailzeitraum, siehe DETAIL_MONTHS.
    detail_start, detail_end = (detail_period(date.today()) if args.max_history
                                else (start, end))
    snapshot["detail_period"] = {"start": detail_start, "end": detail_end}
    snapshot.update(shape_campaigns(
        [row for row in campaign_rows
         if detail_start <= (row.get("segments") or {}).get("date", "") <= detail_end]))

    for key, query in (("ad_groups", query_ad_groups(detail_start, detail_end)),
                        ("search_terms", query_search_terms(detail_start, detail_end))):
        try:
            rows = client.search(query)
        except ads_client.AdsError as exc:
            snapshot[key] = {"error": str(exc)}
            continue
        if key == "search_terms":
            snapshot.update(shape_search_terms(rows))
        else:
            snapshot[key] = rows[:MAX_CAMPAIGNS]

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    path = out / "ads.json"
    path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    spend = sum(m["cost"] for m in snapshot["by_month"])
    print(f"Geschrieben: {path} ({len(snapshot['by_month'])} Monate, "
          f"{round(spend, 2)} {currency} Ausgaben)")


if __name__ == "__main__":
    main()
