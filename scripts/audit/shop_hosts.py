#!/usr/bin/env python3
"""Welche Hosts und Kampagnen zu einem Shop gehören.

Ein Audit gilt einem Shopify-Store, und das Merkmal dafür ist die Domain,
nie das Land: ein Store verkauft oft in viele Länder, und eine Kampagne für
ein Land kann auf einem anderen Store landen. `shop_hostnames` in der Config
nennt die Domains; `audit.scope` misst, ob eine Quelle mehr enthält, und
`ads_pull.py` zieht damit nur die Kampagnen dieses Shops.

Reine Funktionen ohne Netz.
"""
import urllib.parse

import ads_client

NOT_SET = "(not set)"

#: Ab welchem Anteil der Klicks auf den Shop-Domains eine Kampagne dem Shop
#: gehört, und bis zu welchem sie fremd ist. Dazwischen ist sie gemischt.
#: Einzelne Klicks auf fremde Domains sind normal (Weiterleitungen nach
#: Land, alte Links); am echten Konto lagen sie bei rund fünf Prozent.
OWN_SHARE = 0.9
FOREIGN_SHARE = 0.1


def bare_host(host) -> str:
    """Host ohne www und Großschreibung, zum Vergleichen. `www.` und die
    Domain ohne gelten als derselbe Shop, eine Subdomain wie `eu.` nicht."""
    host = (host or "").strip().lower().rstrip(".")
    return host[4:] if host.startswith("www.") else host


def is_shop_host(host, shop_hosts) -> bool:
    return bare_host(host) in {bare_host(h) for h in shop_hosts}


def with_www(hosts: list) -> list:
    """Jeder Host mit und ohne `www.`, für Filter, die exakt vergleichen."""
    out = []
    for host in hosts:
        for variant in (bare_host(host), "www." + bare_host(host)):
            if variant not in out:
                out.append(variant)
    return out


def classify_campaigns(rows: list, shop_hosts: list) -> list:
    """Kampagnen nach dem Anteil ihrer Klicks auf den Shop-Domains.

    `rows` sind Zeilen aus `landing_page_view` mit Kampagne, Ziel-URL und
    Kennzahlen. Je Kampagne: Klicks je Host, Kosten, Conversions und
    `assignment` (own, foreign, mixed). Eine Kampagne ohne Klicks zählt nach
    ihren Kosten je Host, sonst bliebe sie unzugeordnet.
    """
    campaigns: dict = {}
    for row in rows:
        campaign = row.get("campaign") or {}
        view = row.get("landingPageView") or {}
        metrics = row.get("metrics") or {}
        host = (urllib.parse.urlsplit(view.get("unexpandedFinalUrl") or "").hostname
                or NOT_SET).lower()
        entry = campaigns.setdefault(campaign.get("id"), {
            "campaign_id": campaign.get("id"), "name": campaign.get("name"),
            "clicks": 0, "cost": 0.0, "conversions": 0.0, "conversions_value": 0.0,
            "hosts": {}})
        clicks = int(metrics.get("clicks") or 0)
        cost = ads_client.from_micros(metrics.get("costMicros")) or 0.0
        entry["clicks"] += clicks
        entry["cost"] += cost
        entry["conversions"] += float(metrics.get("conversions") or 0)
        entry["conversions_value"] += float(metrics.get("conversionsValue") or 0)
        bucket = entry["hosts"].setdefault(host, {"clicks": 0, "cost": 0.0})
        bucket["clicks"] += clicks
        bucket["cost"] += cost
    out = []
    for entry in campaigns.values():
        weight = "clicks" if entry["clicks"] else "cost"
        total = sum(h[weight] for h in entry["hosts"].values())
        own = sum(h[weight] for host, h in entry["hosts"].items() if is_shop_host(host, shop_hosts))
        share = own / total if total else None
        entry["shop_share"] = round(share, 3) if share is not None else None
        entry["assignment"] = ("own" if share is not None and share >= OWN_SHARE
                               else "foreign" if share is None or share <= FOREIGN_SHARE
                               else "mixed")
        entry["cost"] = round(entry["cost"], 2)
        entry["conversions_value"] = round(entry["conversions_value"], 2)
        entry["hosts"] = {host: {"clicks": h["clicks"], "cost": round(h["cost"], 2)}
                          for host, h in sorted(entry["hosts"].items(),
                                                key=lambda kv: -kv[1][weight])}
        out.append(entry)
    return sorted(out, key=lambda c: -c["cost"])
