#!/usr/bin/env python3
"""Ob eine Search-Console-Property die Shop-Domain abdeckt.

Lesbar heißt nicht passend. Am 07.10.2026 kam aus dem Cockpit für einen Shop
auf einer Subdomain die URL-Präfix-Property der Hauptdomain. Sie war lesbar,
`--check` meldete "erreichbar", und jede Zahl daraus gehörte zu einem anderen
Store derselben Brand.

Regel: Eine Property deckt den Shop ab, wenn sie

* eine URL-Präfix-Property mit `https://`, genau dem Host des Shops und ohne
  Pfad ist, oder
* eine Domain-Property (`sc-domain:`) für den Host oder eine übergeordnete
  Domain.

`www.` gilt bei URL-Präfix-Properties als derselbe Host wie die Domain ohne
`www.`: Domains stehen in Config und Cockpit oft ohne `www.`, während der Shop
darunter ausliefert. Eine Subdomain wie `eu.` ist dagegen ein anderer Host.
`http://` oder ein Pfad passen nicht: die Property sähe nur einen Teil des
Shops.

Dieselbe Regel prüft das Cockpit beim Speichern (`gscCoversDomain`) und führt
eine unpassende Property als `domain_mismatch`. Ändert sich die Regel, an
beiden Stellen.

Reine Funktionen ohne Netz, damit `config.validate()`, `audit.portal` und
`gsc_pull.py` dieselbe Entscheidung treffen.
"""
import re
from urllib.parse import urlsplit

DOMAIN_PREFIX = "sc-domain:"


def shop_host(domain) -> str | None:
    """Host aus der `domain` der Config, ohne Schema, Pfad, Port und Großschreibung."""
    if not isinstance(domain, str):
        return None
    host = re.sub(r"^[a-z][a-z0-9+.-]*://", "", domain.strip().lower())
    host = host.split("/")[0].split("?")[0].split(":")[0].rstrip(".")
    return host or None


def _strip_www(host: str) -> str:
    return host[4:] if host.startswith("www.") else host


def covers(gsc_site, domain) -> bool:
    """Ob die Property `gsc_site` die Shop-Domain `domain` abdeckt.

    Eine nicht lesbare Property oder Domain deckt nichts ab.
    """
    host = shop_host(domain)
    if not host or not isinstance(gsc_site, str):
        return False
    site = gsc_site.strip().lower()
    if site.startswith(DOMAIN_PREFIX):
        property_domain = site[len(DOMAIN_PREFIX):].strip().rstrip(".")
        return bool(property_domain) and (host == property_domain
                                          or host.endswith("." + property_domain))
    parts = urlsplit(site)
    if parts.scheme != "https" or not parts.hostname or parts.path not in ("", "/"):
        return False
    return _strip_www(parts.hostname.rstrip(".")) == _strip_www(host)


def mismatch(gsc_site, domain) -> str | None:
    """Ein Satz, warum die Property den Shop nicht abdeckt, oder `None`.

    `None` auch, wenn `domain` oder `gsc_site` fehlt oder leer ist: das meldet
    `config.validate()` schon als Pflichtfeld, eine zweite Meldung zum selben
    Feld hilft niemandem.
    """
    host = shop_host(domain)
    if not host or not isinstance(gsc_site, str) or not gsc_site.strip():
        return None
    if covers(gsc_site, domain):
        return None
    return (f"Die Search-Console-Property {gsc_site} deckt den Shop {host} nicht ab; "
            f"ihre Zahlen gehören zu einem anderen Host. Passend ist nur eine "
            f"URL-Präfix-Property für https://{host}/ oder eine Domain-Property "
            f"sc-domain:<{host} oder übergeordnete Domain>.")
