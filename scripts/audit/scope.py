#!/usr/bin/env python3
"""Enthalten GA4, Google Ads und Search Console genau diesen Shop?

Ein Audit gilt einem Shopify-Store. Jede Quelle kann davon abweichen, in zwei
Richtungen:

* **Mehr als der Store.** Eine GA4-Property, ein Werbekonto oder eine
  Domain-Property der Search Console bedient mehrere Stores einer Marke, etwa
  je Markt eine Subdomain. Ohne Eingrenzung hält der Audit den Umsatz eines
  Stores gegen die Zahlen aller.
* **Weniger als der Store.** Ein zweites Werbekonto bringt Traffic, steht
  aber nicht in der Config; ein Domainwechsel liegt in der Historie.

Das Merkmal ist die Domain, nie das Land. Ein Store verkauft oft in viele
Länder, und eine Kampagne für ein Land kann auf einem anderen Store landen.
Am 07.10.2026 an einem echten Konto gemessen: die Kampagnen für ein Land
landeten fast vollständig auf dem globalen Store, nicht auf dem des Landes.

Der Check misst nur und schreibt nichts. Am Ende steht ein Vorschlag für
`shop_hostnames` und `ga4_stream_ids`, den ein Mensch übernimmt.

Aufruf im Kunden-Workspace:

    PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m audit.scope [--json]
"""
import argparse
import json
import subprocess
import sys
import urllib.parse
from datetime import date, timedelta
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
for _path in ("skills/pull-ga4/scripts", "skills/pull-gsc/scripts"):
    sys.path.insert(0, str(PLUGIN_ROOT / _path))

import ads_client  # noqa: E402
from api_common import describe_error  # noqa: E402
from audit import config as run_config, env, gsc_scope, portal  # noqa: E402
from audit.shop_hosts import (NOT_SET, bare_host, classify_campaigns,  # noqa: E402
                              is_shop_host, with_www)
from google_token import get_access_token  # noqa: E402

#: Tage, über die der Check misst, bis gestern.
WINDOW_DAYS = 28

#: Ab welchem Anteil an Sitzungen, Käufen oder Klicks fremde Hosts einen
#: Filter nötig machen. Vorschau-Domains und Übersetzungsdienste liegen
#: darunter.
FOREIGN_WEIGHT = 0.02


SHOPIFY_QUERY = """query {
  shop { primaryDomain { host } currencyCode }
  markets(first: 50) { nodes { name enabled
    regions(first: 250) { nodes { ... on MarketRegionCountry { code } } }
    webPresences(first: 10) { nodes { domain { host } subfolderSuffix } } } }
}"""


def parse_shopify(data: dict) -> dict:
    """Domains, Länder und Währung des Stores aus der Antwort von SHOPIFY_QUERY.

    Die Domains sind die Hauptdomain und die Domains der Märkte. Unterordner
    wie `/de` liegen auf derselben Domain und ändern nichts am Filter.
    """
    shop = data.get("shop") or {}
    hosts, countries, subfolders = [], [], []
    primary = ((shop.get("primaryDomain") or {}).get("host") or "").lower()
    if primary:
        hosts.append(primary)
    for market in ((data.get("markets") or {}).get("nodes") or []):
        if not market.get("enabled"):
            continue
        for region in ((market.get("regions") or {}).get("nodes") or []):
            if region.get("code") and region["code"] not in countries:
                countries.append(region["code"])
        for presence in ((market.get("webPresences") or {}).get("nodes") or []):
            host = ((presence.get("domain") or {}).get("host") or "").lower()
            if host and host not in hosts:
                hosts.append(host)
            if presence.get("subfolderSuffix"):
                subfolders.append(presence["subfolderSuffix"])
    return {"primary_host": primary or None, "hosts": hosts, "countries": sorted(countries),
            "subfolders": sorted(set(subfolders)), "currency": shop.get("currencyCode")}


def host_history(rows: list) -> list:
    """Sitzungen und Käufe je Host über die Historie, mit erstem und letztem
    Monat. `rows` aus GA4 mit den Dimensionen yearMonth und hostName.

    Ein Host, dessen letzter Monat vor dem aktuellen liegt, ist ein Kandidat
    für einen Domainwechsel: ein Filter nur auf die heutige Domain löschte
    seine Historie still aus der Baseline.
    """
    hosts: dict = {}
    for dims, metrics in rows:
        month, host = (list(dims) + ["", NOT_SET])[:2]
        month = f"{month[:4]}-{month[4:6]}" if len(month) == 6 else month
        entry = hosts.setdefault(host, {"host_name": host, "first_month": month,
                                        "last_month": month, "sessions": 0, "purchases": 0})
        entry["first_month"] = min(entry["first_month"], month)
        entry["last_month"] = max(entry["last_month"], month)
        entry["sessions"] += metrics.get("sessions", 0) or 0
        entry["purchases"] += metrics.get("ecommercePurchases", 0) or 0
    return sorted(hosts.values(), key=lambda h: -h["sessions"])


def foreign_share(items: list, key: str, shop_hosts: list) -> float:
    """Anteil von `key` auf Hosts, die nicht zum Shop gehören. "(not set)"
    zählt nicht als fremd: es ist kein anderer Shop, sondern ein Ereignis
    ohne Hostnamen."""
    total = sum(i.get(key) or 0 for i in items)
    foreign = sum(i.get(key) or 0 for i in items
                  if i["host_name"] != NOT_SET and not is_shop_host(i["host_name"], shop_hosts))
    return foreign / total if total else 0.0


def propose(report: dict) -> dict:
    """Vorschlag für die Config und die Gründe dafür, aus den Abschnitten des
    Checks. Ein Filter wird nur vorgeschlagen, wo eine Quelle messbar mehr
    als diesen Shop enthält: ein Filter ohne Not nimmt Ereignisse ohne
    Hostnamen heraus, und die kommen oft von einem serverseitigen
    Kauf-Connector."""
    shopify = report.get("shopify") or {}
    shop_hosts = shopify.get("hosts") or report.get("config_hosts") or []
    ga4 = report.get("ga4") or {}
    ads = report.get("ads") or {}
    gsc = report.get("gsc") or {}
    reasons, warnings = [], []

    rows = ga4.get("rows") or []
    per_host: dict = {}
    for row in rows:
        entry = per_host.setdefault(row["host_name"], {"host_name": row["host_name"],
                                                       "sessions": 0, "purchases": 0})
        entry["sessions"] = max(entry["sessions"], row["sessions"])
        entry["purchases"] += row["purchases"] or 0
    hosts = list(per_host.values())
    if (foreign_share(hosts, "sessions", shop_hosts) > FOREIGN_WEIGHT
            or foreign_share(hosts, "purchases", shop_hosts) > FOREIGN_WEIGHT):
        reasons.append("GA4: die Property enthält andere Shops ("
                       + ", ".join(h["host_name"] for h in hosts
                                   if h["purchases"] and h["host_name"] != NOT_SET
                                   and not is_shop_host(h["host_name"], shop_hosts))
                       + ")")
    campaigns = ads.get("campaigns") or []
    foreign_cost = sum(c["cost"] for c in campaigns if c["assignment"] != "own")
    total_cost = sum(c["cost"] for c in campaigns)
    if total_cost and foreign_cost / total_cost > FOREIGN_WEIGHT:
        reasons.append(f"Google Ads: {round(100 * foreign_cost / total_cost)} % der Kosten "
                       "landen nicht oder nicht nur auf diesem Shop")
    gsc_hosts = gsc.get("hosts") or []
    # Deckt die Property den Shop gar nicht ab, hilft kein Filter; das steht
    # unten als Warnung.
    if gsc.get("covered") and foreign_share(gsc_hosts, "clicks", shop_hosts) > FOREIGN_WEIGHT:
        reasons.append("Search Console: die Property enthält Seiten anderer Hosts")

    proposal = {"shop_hostnames": [], "ga4_stream_ids": []}
    if reasons:
        seen = {bare_host(h) for h in shop_hosts}
        observed = [r["host_name"] for r in rows] + [h["host_name"] for h in gsc_hosts]
        names = list(shop_hosts) + [h for h in observed
                                    if h != NOT_SET and bare_host(h) in seen]
        proposal["shop_hostnames"] = list(dict.fromkeys(h.lower() for h in names))

    tx = ga4.get("transactions") or {}
    streams = [s for s in tx.get("by_stream") or [] if s["transactions"]]
    if len(streams) > 1 and tx.get("in_multiple_streams"):
        best = max(streams, key=lambda s: s["transactions"])
        proposal["ga4_stream_ids"] = [best["stream_id"]]
        reasons.append(f"GA4: {tx['in_multiple_streams']} Transaktionen kommen in mehr als "
                       f"einem Stream an; Stream {best['stream_id']} hat die meisten")
    for stream in tx.get("by_stream") or []:
        if stream.get("multiple_id_formats"):
            warnings.append(f"GA4: Stream {stream['stream_id']} erhält Transaktions-IDs in "
                            "mehreren Formen ("
                            + ", ".join(f"{f['format']} {f['transactions']}"
                                        for f in stream["id_formats"][:3])
                            + "), also ein zweiter Absender. Kein Filter behebt das; "
                              "Befund für den Kunden.")

    for other in [ga4] + list(report.get("ga4_compare") or []):
        unhosted = sum(r["purchases"] or 0 for r in other.get("rows") or []
                       if r["host_name"] in (NOT_SET, ""))
        if unhosted:
            prop = other.get("property_id")
            warnings.append(f"GA4 {prop}: {unhosted} Käufe ohne Hostnamen. Ein Filter über "
                            "shop_hostnames nähme sie heraus; gehören sie zu diesem Shop, "
                            "kommt \"(not set)\" mit in die Liste.")
            if proposal["shop_hostnames"] and prop == ga4.get("property_id"):
                proposal["shop_hostnames"].append(NOT_SET)

    orders = shopify.get("orders")
    if orders and tx.get("in_scope"):
        warnings.append(f"Gegenprobe: Shopify {orders} Bestellungen, GA4 "
                        f"{tx['in_scope']['transactions']} Transaktionen und "
                        f"{tx['in_scope']['purchases']} Käufe auf den Shop-Domains")

    history = ga4.get("history") or []
    current = max((h["last_month"] for h in history), default=None)
    all_purchases = sum(h["purchases"] for h in history)
    for host in history:
        if (host["last_month"] != current
                and host["purchases"] > FOREIGN_WEIGHT * all_purchases
                and host["host_name"] != NOT_SET
                and not is_shop_host(host["host_name"], shop_hosts)):
            warnings.append(f"GA4: {host['host_name']} hatte bis {host['last_month']} "
                            f"{host['purchases']} Käufe und ist seitdem still. War das eine "
                            "frühere Domain dieses Shops, gehört sie in shop_hostnames. War "
                            "es ein anderer Shop, enthält eine Baseline über die volle "
                            "Historie seine Zahlen; dann shop_hostnames auf die Domains "
                            "dieses Shops setzen.")

    configured = str(report.get("config_ads_customer_id") or "").replace("-", "")
    for account in ga4.get("ads_accounts") or []:
        if configured and account["customer_id"] != configured and account["sessions"]:
            warnings.append(f"Google Ads: Konto {account['customer_id']} "
                            f"({account['account_name']}) bringt {account['sessions']} "
                            "Sitzungen auf den Shop und steht nicht in der Config.")
    if (gsc.get("site") and gsc.get("covered") is False):
        warnings.append(f"Search Console: {gsc['site']} deckt die Shop-Domains nicht ab.")

    currencies = {k: v for k, v in (("Shopify", shopify.get("currency")),
                                    ("GA4", ga4.get("currency")),
                                    ("Google Ads", ads.get("currency"))) if v}
    if len(set(currencies.values())) > 1:
        warnings.append("Währungen verschieden: " + ", ".join(f"{k} {v}"
                                                              for k, v in currencies.items())
                        + ". Umsatz nur in gleicher Währung vergleichen.")
    return {"needed": bool(reasons), "reasons": reasons, "warnings": warnings,
            "config": proposal}


def window() -> dict:
    end = date.today() - timedelta(days=1)
    return {"startDate": (end - timedelta(days=WINDOW_DAYS - 1)).isoformat(),
            "endDate": end.isoformat()}


def read_shopify(config: dict, workspace: Path, period: dict) -> dict:
    """Domains, Märkte und Bestellungen im Zeitraum, über das Cockpit oder
    die Shopify CLI, je nachdem, wie der Workspace eingerichtet ist."""
    orders_query = (f'query {{ ordersCount(query: "created_at:>={period["startDate"]} '
                    f'created_at:<={period["endDate"]}", limit: null) {{ count }} }}')

    def execute(query: str) -> dict:
        target = config.get("portal") or {}
        if target.get("brand") and target.get("shop"):
            return portal.shopify_execute(target["brand"], target["shop"], query, None,
                                          "audit.scope", workspace)
        result = subprocess.run(["shopify", "store", "execute", "--store",
                                 config.get("shopify_store") or "", "--json", "--query", query],
                                capture_output=True, text=True, timeout=120)
        if result.returncode:
            raise RuntimeError((result.stderr or "shopify store execute fehlgeschlagen")[-300:])
        return json.loads(result.stdout)

    try:
        section = parse_shopify(execute(SHOPIFY_QUERY))
        section["orders"] = (execute(orders_query).get("ordersCount") or {}).get("count")
        return section
    except Exception as exc:  # noqa: BLE001 - jede Quelle ist isoliert
        return {"note": f"Shopify nicht abrufbar: {describe_error(exc)}"}


def read_ga4(prop: str, creds: str, shop_hosts: list, period: dict) -> dict:
    """Streams und Hosts, Transaktionen, Hosts je Monat und die Ads-Konten,
    die Traffic auf die Shop-Domains bringen."""
    import ga4_pull

    section = {"property_id": prop}
    try:
        token = get_access_token(creds, "analytics")
        streams = ga4_pull.read_streams(prop, token)
        section["measurement_ids"] = streams.get("measurement_ids")
        scope = ga4_pull.read_scope(prop, token, period, None, with_www(shop_hosts), [],
                                    streams.get("streams"))
        section.update({"rows": scope["rows"], "transactions": scope["transactions"],
                        "note": scope["note"]})
        resp = ga4_pull.run_report(prop, token, {
            "dateRanges": [period], "dimensions": [{"name": "hostName"}],
            "metrics": [{"name": "sessions"}], "limit": 1})
        section["currency"] = ga4_pull.response_currency(resp)
        history = ga4_pull.run_report_all(prop, token, {
            "dateRanges": [{"startDate": ga4_pull.HISTORY_ANCHOR, "endDate": period["endDate"]}],
            "dimensions": [{"name": "yearMonth"}, {"name": "hostName"}],
            "metrics": [{"name": "sessions"}, {"name": ga4_pull.PURCHASE_METRIC}],
            "limit": 100000})
        section["history"] = [h for h in host_history(ga4_pull.parse_rows(history)["date_range_0"])
                              if h["sessions"] >= 100]
        shop_filter = ga4_pull.scope_filter(with_www(shop_hosts))
        accounts = ga4_pull.run_report(prop, token, {
            "dateRanges": [period],
            "dimensions": [{"name": "sessionGoogleAdsCustomerId"},
                           {"name": "sessionGoogleAdsAccountName"}],
            "metrics": [{"name": "sessions"}], "limit": 50,
            **({"dimensionFilter": shop_filter} if shop_filter else {})})
        section["ads_accounts"] = [
            {"customer_id": dims[0], "account_name": dims[1], "sessions": m.get("sessions", 0)}
            for dims, m in ga4_pull.parse_rows(accounts)["date_range_0"] if dims[0] != NOT_SET]
    except Exception as exc:  # noqa: BLE001
        section["note"] = f"GA4 nicht abrufbar: {describe_error(exc)}"
    return section


def read_ga4_compare(prop: str, creds: str, shop_hosts: list, period: dict) -> dict:
    """Streams, Hosts und Transaktionen einer Vergleichs-Property.

    Serverseitige Connectoren schreiben oft in eine eigene Property und
    senden Käufe ohne Hostnamen. Dort entscheidet sich, ob ein Hostnamen-
    Filter Käufe verlöre: Käufe unter "(not set)" fielen heraus.
    """
    import ga4_pull

    section = {"property_id": prop}
    try:
        token = get_access_token(creds, "analytics")
        scope = ga4_pull.read_scope(prop, token, period, None, with_www(shop_hosts), [], None)
        section.update({"rows": scope["rows"], "transactions": scope["transactions"],
                        "note": scope["note"]})
    except Exception as exc:  # noqa: BLE001
        section["note"] = f"GA4 {prop} nicht abrufbar: {describe_error(exc)}"
    return section


def read_ads(customer_id: str, login_id, creds: str, shop_hosts: list, period: dict) -> dict:
    """Kampagnen mit Ziel-Domains, Kosten und Zuordnung zum Shop."""
    section = {"customer_id": customer_id}
    try:
        client = ads_client.Client(customer_id, access_token=get_access_token(creds, "adwords"),
                                   login_customer_id=login_id)
        info = client.search("SELECT customer.descriptive_name, customer.currency_code FROM customer")
        customer = (info[0].get("customer") if info else {}) or {}
        section["currency"] = customer.get("currencyCode")
        section["name"] = customer.get("descriptiveName")
        rows = client.search(
            "SELECT campaign.id, campaign.name, landing_page_view.unexpanded_final_url, "
            "metrics.clicks, metrics.cost_micros, metrics.conversions, metrics.conversions_value "
            "FROM landing_page_view WHERE segments.date BETWEEN "
            f"'{period['startDate']}' AND '{period['endDate']}' AND metrics.impressions > 0")
        section["campaigns"] = classify_campaigns(rows, shop_hosts)
    except Exception as exc:  # noqa: BLE001
        section["note"] = f"Google Ads nicht abrufbar: {describe_error(exc)}"
    return section


def read_gsc(site: str, creds: str, shop_hosts: list, period: dict) -> dict:
    """Klicks je Host der konfigurierten Property und ob sie den Shop abdeckt."""
    import gsc_pull

    section = {"site": site, "covered": any(gsc_scope.covers(site, h) for h in shop_hosts)}
    try:
        token = get_access_token(creds, "webmasters")
        site_enc = urllib.parse.quote(site, safe="")
        resp = gsc_pull.api_request(
            f"https://www.googleapis.com/webmasters/v3/sites/{site_enc}/searchAnalytics/query",
            token, {"startDate": period["startDate"], "endDate": period["endDate"],
                    "dimensions": ["page"], "rowLimit": 25000})
        hosts: dict = {}
        for row in resp.get("rows") or []:
            host = (urllib.parse.urlsplit(row["keys"][0]).hostname or NOT_SET).lower()
            entry = hosts.setdefault(host, {"host_name": host, "clicks": 0, "impressions": 0})
            entry["clicks"] += row.get("clicks", 0)
            entry["impressions"] += row.get("impressions", 0)
        section["hosts"] = sorted(hosts.values(), key=lambda h: -h["impressions"])
    except Exception as exc:  # noqa: BLE001
        section["note"] = f"Search Console nicht abrufbar: {describe_error(exc)}"
    return section


def run_check(workspace: Path) -> dict:
    config = json.loads((workspace / "reporting" / "config.json").read_text(encoding="utf-8"))
    period = window()
    creds = env.get("PTAI_GOOGLE_CREDENTIALS", workspace) or ""
    if creds and not creds.startswith(portal.PREFIX) and not Path(creds).is_absolute():
        creds = str(workspace / creds)
    report = {"period": {"start": period["startDate"], "end": period["endDate"]},
              "config_hosts": run_config.shop_hostnames(config)
              or [h for h in [gsc_scope.shop_host(config.get("domain"))] if h],
              "config_ads_customer_id": config.get("google_ads_customer_id")}
    report["shopify"] = read_shopify(config, workspace, period)
    shop_hosts = report["shopify"].get("hosts") or report["config_hosts"]
    if config.get("ga4_property_id"):
        report["ga4"] = read_ga4(str(config["ga4_property_id"]), creds, shop_hosts, period)
    report["ga4_compare"] = [read_ga4_compare(prop, creds, shop_hosts, period)
                             for prop in run_config.compare_properties(config)]
    if config.get("google_ads_customer_id"):
        report["ads"] = read_ads(str(config["google_ads_customer_id"]),
                                 config.get("google_ads_login_customer_id"), creds,
                                 shop_hosts, period)
    if config.get("gsc_site"):
        report["gsc"] = read_gsc(config["gsc_site"], creds, shop_hosts, period)
    report["proposal"] = propose(report)
    report["current"] = {"shop_hostnames": run_config.shop_hostnames(config),
                         "ga4_stream_ids": run_config.ga4_stream_ids(config)}
    return report


def render(report: dict) -> str:
    """Der Bericht als Text für die Kommandozeile."""
    lines = [f"Scope-Check {report['period']['start']} bis {report['period']['end']}"]
    shopify = report.get("shopify") or {}
    lines.append("")
    lines.append("Shopify: " + (shopify.get("note") or (
        f"Domains {', '.join(shopify.get('hosts') or []) or 'keine'}; "
        f"{len(shopify.get('countries') or [])} Länder; Währung {shopify.get('currency')}; "
        f"{shopify.get('orders')} Bestellungen")))
    ga4 = report.get("ga4")
    if ga4:
        lines.append("")
        lines.append(f"GA4 {ga4.get('property_id')}, Währung {ga4.get('currency')}"
                     + (f" (Hinweis: {ga4['note']})" if ga4.get("note") else ""))
        for row in (ga4.get("rows") or [])[:10]:
            mark = "  Shop" if is_shop_host(row["host_name"], report["shopify"].get("hosts")
                                           or report["config_hosts"]) else ""
            lines.append(f"  {row['stream_id']} {row['measurement_id'] or ''} "
                         f"\"{row['stream_name']}\" {row['host_name']}: "
                         f"{row['sessions']} Sitzungen / {row['purchases']} Käufe{mark}")
        tx = ga4.get("transactions") or {}
        for stream in tx.get("by_stream") or []:
            lines.append(f"  Stream {stream['stream_id']} auf den Shop-Domains: "
                         f"{stream['purchases']} Käufe, {stream['transactions']} "
                         "Transaktions-IDs, Formen "
                         + ", ".join(f"{f['format']} {f['transactions']}"
                                     for f in stream["id_formats"][:3]))
        for account in ga4.get("ads_accounts") or []:
            lines.append(f"  Ads-Konto laut GA4: {account['customer_id']} "
                         f"({account['account_name']}), {account['sessions']} Sitzungen")
    for other in report.get("ga4_compare") or []:
        lines.append("")
        lines.append(f"GA4-Vergleichs-Property {other['property_id']}"
                     + (f" (Hinweis: {other['note']})" if other.get("note") else ""))
        for row in (other.get("rows") or [])[:6]:
            lines.append(f"  {row['stream_id']} \"{row['stream_name']}\" {row['host_name']}: "
                         f"{row['sessions']} Sitzungen / {row['purchases']} Käufe")
        scoped = ((other.get("transactions") or {}).get("in_scope") or {})
        if scoped:
            lines.append(f"  auf den Shop-Domains: {scoped['purchases']} Käufe, "
                         f"{scoped['transactions']} Transaktions-IDs")
    ads = report.get("ads")
    if ads:
        lines.append("")
        lines.append(f"Google Ads {ads.get('customer_id')}, Währung {ads.get('currency')}"
                     + (f" (Hinweis: {ads['note']})" if ads.get("note") else ""))
        for campaign in ads.get("campaigns") or []:
            hosts = ", ".join(f"{h} {v['clicks']}" for h, v in list(campaign["hosts"].items())[:3])
            lines.append(f"  {campaign['assignment']:7} {campaign['cost']:>9.0f} "
                         f"{campaign['name']}: {hosts}")
    gsc = report.get("gsc")
    if gsc:
        lines.append("")
        lines.append(f"Search Console {gsc.get('site')}, deckt den Shop "
                     f"{'ab' if gsc.get('covered') else 'nicht ab'}"
                     + (f" (Hinweis: {gsc['note']})" if gsc.get("note") else ""))
        for host in (gsc.get("hosts") or [])[:6]:
            lines.append(f"  {host['host_name']}: {host['clicks']} Klicks, "
                         f"{host['impressions']} Impressionen")
    proposal = report["proposal"]
    lines.append("")
    lines.append("Ergebnis: " + ("Filter nötig." if proposal["needed"]
                                 else "kein Filter nötig, jede Quelle enthält nur diesen Shop."))
    lines.extend(f"  - {r}" for r in proposal["reasons"])
    lines.extend(f"  ! {w}" for w in proposal["warnings"])
    lines.append("")
    lines.append("Vorschlag für reporting/config.json (aktuell: "
                 + json.dumps(report["current"], ensure_ascii=False) + "):")
    lines.append("  " + json.dumps(proposal["config"], ensure_ascii=False))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="audit.scope", description=__doc__.split("\n\n")[0])
    parser.add_argument("--workspace", default=".")
    parser.add_argument("--json", action="store_true", help="den ganzen Bericht als JSON")
    args = parser.parse_args(argv)
    try:
        report = run_check(Path(args.workspace))
    except (OSError, ValueError) as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2) if args.json else render(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
