#!/usr/bin/env python3
"""Site-Crawl für den PTAI-Audit: Abruf, Breitensuche und das Parsen dazu.

Zwei Hälften in einer Datei. Die reinen Funktionen (`parse_page()`,
`sitemap_children()`, `sitemap_urls()`, `normalize()`) berechnen aus
HTML- oder Sitemap-Bytes ein Ergebnis, ohne je ein Netzwerk anzufassen, und
sind vollständig durch Unit-Tests abgedeckt. Die Abruf-Hälfte baut darauf auf:
robots.txt lesen, den Sitemap-Baum auflösen, dann eine Breitensuche über
interne Links bis `--max-urls`, jede Seite über `parse_page()` auswerten.
Die Nahtstelle für Tests ist überall dieselbe injizierbare Funktion
`fetch(url) -> dict`, die den einzigen Punkt ersetzt, der wirklich das Netz
anfasst (`_real_fetch`); kein Test öffnet einen Socket.

Warum das hier so genau genommen wird: der erste Kunde ist ein Shopify-Shop,
dessen Theme Ende Oktober abgelöst wird. Der Crawl hält den Vorher-Zustand
fest, und der ist nicht wiederholbar. Eine Baseline, die eine Seite falsch
liest, kann später niemand mehr nachmessen.

Nur Standardbibliothek: `html.parser`, `urllib.parse`, `urllib.request`,
`urllib.error`, `xml.etree.ElementTree`, `gzip`, `argparse`, `json`, `time`.
Kein `requests`.
"""
import argparse
from collections import Counter
import functools
import gzip
import json
import re
import sys
import time
import urllib.error
import urllib.request
from collections import deque
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qsl, urljoin, urlparse, urlunparse
from xml.etree import ElementTree as ET

#: Robots-Direktiven, die eine Seite von der Indexierung ausschließen.
NOINDEX_DIRECTIVES = {"noindex"}

#: Schemata, die nie eine crawlbare Seite ergeben (Mail, Telefon, Skript-Links).
FOREIGN_SCHEMES = {"mailto", "tel", "javascript"}

#: Container- und Mess-IDs, die sich per Inline-Snippet einbauen und deshalb
#: nie in `script_sources` auftauchen. Genau die häufigsten Doppelcounts
#: (Tag Manager, GA4, Ads-Conversion, Universal Analytics) installieren sich so;
#: ohne diese Erkennung heisst "kein Hinweis auf doppelte Tags" in Wahrheit
#: "nicht messbar". Am 06.09.2026 im ersten echten Lauf aufgefallen.
INLINE_TAG_ID = re.compile(r"\b(?:GTM-[A-Z0-9]{4,10}|G-[A-Z0-9]{8,12}|AW-\d{9,12}|UA-\d{4,10}-\d{1,4})\b")


def _without_www(host: str) -> str:
    """Entfernt ein führendes `www.` für den Host-Vergleich."""
    return host[4:] if host.startswith("www.") else host


def _same_shop(target_host: str | None, reference_host: str | None) -> bool:
    """Prüft, ob zwei Hosts denselben Shop meinen.

    Hostnamen sind laut RFC nicht case-sensitiv; `urlparse().hostname`
    liefert sie deshalb schon kleingeschrieben, und der Vergleich läuft
    darüber. Zusätzlich gelten `example.com` und `www.example.com` als
    derselbe Shop, weil Shopify-Themes beide Schreibweisen mischen können.
    Die Ausnahme gilt eng, nur für ein führendes `www.`: `blog.example.com`
    und `cdn.example.com` bleiben fremd.
    """
    if target_host is None or reference_host is None:
        return False
    if target_host == reference_host:
        return True
    return _without_www(target_host) == _without_www(reference_host) and (
        target_host.startswith("www.") or reference_host.startswith("www.")
    )


def script_host(src: str, base: str) -> str | None:
    """Der Host, von dem eine Skript-Quelle geladen wird, oder `None`, wenn
    die Quelle zum Shop selbst gehört.

    Drei Schreibweisen stehen in echten Themes nebeneinander: absolut
    (`https://cdn.intelligems.io/x.js`), protokoll-relativ
    (`//cdn.judge.me/y.js`) und seiten-relativ (`/assets/theme.js`). Nur die
    ersten beiden können überhaupt fremd sein, die dritte lädt immer vom Shop.
    `urljoin` gegen `base` löst alle drei einheitlich auf, `_same_shop` wirft
    danach die eigenen Hosts heraus: ein Theme lädt Dutzende eigener Dateien,
    und die sind kein Befund.

    Ein `data:`-URI trägt keinen Host und fällt damit ebenfalls heraus. Ist
    `base` leer, gibt es keinen eigenen Host zum Vergleich, und jeder gefundene
    Host zählt als fremd. Das ist die sichere Richtung: lieber ein eigener Host
    zu viel in der Liste als ein Preistest-Werkzeug still unterschlagen.
    """
    absolute = urljoin(base, src.strip())
    host = urlparse(absolute).hostname
    if host is None:
        return None
    return None if _same_shop(host, urlparse(base).hostname) else host


#: Der einzige Query-Parameter, der eine eigene Seite ergibt: die Blätterseite
#: einer Liste (`/collections/<handle>?page=2`, ebenso Blog-Übersichten).
PAGE_PARAM = "page"


def _page_query(query: str) -> str:
    """Die Query, die von einer gefundenen URL stehen bleibt: `page=<n>` ab
    Seite 2, sonst nichts.

    Bis zum 02.10.2026 fiel jede Query weg, auch `?page=2`. Damit rief der
    Crawl nie eine Folgeseite einer Kategorie ab, und jedes Produkt, das erst
    ab Seite 2 verlinkt ist, galt als unverlinkt und stand zu tief. Belegt am
    02.10.2026 an einem echten Shopify-Shop, bei dem eine Kategorie live
    `?page=2` bis `?page=24` verlinkt.

    Alle übrigen Parameter fallen weiter weg (`variant`, `sort_by`, Filter,
    Tracking), weil sie dieselbe Seite anders zeigen und keine eigene Adresse
    ergeben. `page=1` ist die erste Seite selbst und fällt deshalb auch weg,
    ebenso ein Wert, der keine ganze Zahl ab 2 ist. Steht `page` mehrfach in
    der Query, gilt der letzte Wert. Führende Nullen fallen weg (`page=02`
    wird `page=2`), sonst stünde dieselbe Seite zweimal im Snapshot.
    """
    pages = [value for key, value in parse_qsl(query) if key == PAGE_PARAM]
    if not pages or not re.fullmatch(r"[0-9]+", pages[-1]):
        return ""
    number = int(pages[-1])
    return f"{PAGE_PARAM}={number}" if number >= 2 else ""


def normalize(url: str, base: str) -> str | None:
    """Normalisiert eine im HTML gefundene URL gegen die Basis-Domain.

    Anker und Query fallen weg, weil sie dieselbe Seite referenzieren und
    keine eigene URL ergeben (`?variant=1` ist dieselbe Seite). Die eine
    Ausnahme ist die Blätterseite einer Liste: `?page=2` ist eine eigene
    Seite mit eigenen Produktlinks und bleibt stehen, siehe `_page_query`.
    Fremde Schemata (`mailto:`, `tel:`, `javascript:`) und fremde Hosts
    liefern `None`, ein relativer Pfad wird gegen die Basis absolut
    aufgelöst.

    Der Host-Vergleich läuft über `_same_shop` (case-insensitiv, mit
    `www`-Ausnahme). Das Ergebnis trägt dabei immer die Schreibweise der
    gecrawlten Domain (`base`), nie die des gefundenen Links: mischt ein
    Theme Groß-/Kleinschreibung oder `www` und ohne `www`, soll trotzdem
    genau eine Adresse pro Seite in der Baseline stehen.

    Ein abschließender Slash wird entfernt, außer bei der Wurzel: sonst wäre
    `https://x.de/` nach dem Entfernen nicht mehr von einer leeren URL zu
    unterscheiden, und `https://x.de/a/` sowie `https://x.de/a` blieben zwei
    Adressen für dieselbe Seite, statt auf eine zusammenzufallen.
    """
    candidate = urlparse(url)
    if candidate.scheme and candidate.scheme.lower() in FOREIGN_SCHEMES:
        return None

    absolute_url = urljoin(base, url)
    target = urlparse(absolute_url)
    reference = urlparse(base)

    if not _same_shop(target.hostname, reference.hostname):
        return None

    path = target.path
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")

    return urlunparse((target.scheme, reference.netloc, path, "",
                       _page_query(target.query), ""))


class _PageParser(HTMLParser):
    """Sammelt Kopfdaten, Überschriften, Bilder, Links und Text einer Seite.

    Ein einziger Durchlauf durch den HTML-Stream statt mehrerer Regex-Läufe,
    damit Reihenfolge und Verschachtelung (etwa Text innerhalb von `script`)
    korrekt bleiben.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title: str | None = None
        self.description: str | None = None
        self.base_href: str | None = None
        self.canonical: str | None = None
        self.canonical_count = 0
        self.hreflang: dict[str, str] = {}
        self.h1: list[str] = []
        self.images = {"total": 0, "without_alt": 0, "empty_alt": 0}
        self.raw_links: list[str] = []
        self.schema_types: set[str] = set()
        # Welche Pflicht- und Empfehlungsfelder die Product- und
        # Organization-Auszeichnung trägt. Nur ja/nein plus Preis und
        # Verfügbarkeit, nie das ganze JSON-LD: die Seitenliste ist mit rund
        # 6,8 KB je Seite schon an der Grenze dessen, was ein Lauf tragen kann.
        self.markup: dict = {}
        self.indexable = True
        self.word_count = 0

        self._in_body = False
        # Zwei getrennte Tiefenzähler, keine Bools, weil beides verschachteln
        # kann. script/style: Inhalt zählt nirgendwo als Text, H1 oder Link.
        # template ist eigenständig, weil JSON-LD immer in einem script-Tag
        # steckt und trotzdem gelesen werden muss, wenn es nicht zusätzlich
        # in einem template liegt. Ein gemeinsamer Zähler würde entweder
        # die strukturierten Daten jeder Seite verschlucken oder die im
        # Template durchlassen.
        self._script_style_depth = 0
        self._script_sources: list[str] = []
        self._inline_tag_ids: set[str] = set()
        self._template_depth = 0
        self._in_title = False
        self._title_buffer = ""
        # SVG hat ein eigenes <title>-Element, und Shopify-Themes rendern die
        # Zahlungs-Icons im Footer als Inline-SVG. Auf einem Shop standen so
        # zehn <title> auf der Startseite, das letzte war "Visa". Wer einfach
        # ueberschreibt, traegt fuer jede Seite des Shops denselben falschen
        # Titel ein, und jeder Title-Befund darueber ist Unsinn.
        self._svg_depth = 0
        self._in_h1 = False
        self._h1_buffer = ""
        self._in_ldjson = False
        self._ldjson_buffer = ""

    @property
    def _hidden(self) -> bool:
        """Wahr, wenn der aktuelle Punkt im Stream in script/style oder in
        einem template steckt, also in keinem Browser sichtbar ist.

        Für H1, Wörter, Links und Bilder zählt jede der beiden
        Verstecktheiten gleich. Für den JSON-LD-Fund gilt das nicht: der
        liegt selbst immer in einem script-Tag, dafür wird dort gezielt nur
        `_template_depth` geprüft, siehe `handle_starttag`. Dieselbe gezielte
        Prüfung gegen `_template_depth` gilt für die Kopfdaten (title,
        Meta-Description, Canonical, hreflang, Robots-Meta, base href): sie
        können nicht in einem script- oder style-Tag stehen, weil `title`,
        `meta`, `link` und `base` dort ohnehin nicht als Start-Tag ankommen
        (script/style laufen im CDATA-Modus des Parsers), also braucht es dort
        keine `_hidden`-Prüfung, nur die gegen `template`.
        """
        return self._script_style_depth > 0 or self._template_depth > 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)

        if tag == "body":
            self._in_body = True
        elif tag == "template":
            self._template_depth += 1
        elif tag in ("script", "style"):
            self._script_style_depth += 1
            if tag == "script" and self._template_depth == 0 and attrs_dict.get("src"):
                # Die Quelle, nicht der Inhalt. Skript-Inhalte bleiben inert,
                # aber welche fremden Skripte eine Seite lädt, ist ein Befund:
                # daran hängen Preistest-Werkzeuge, Bewertungs-Apps,
                # Consent-Banner und doppelte Analytics-Einbindungen.
                self._script_sources.append(attrs_dict["src"])
            if (
                tag == "script"
                and self._template_depth == 0
                and (attrs_dict.get("type") or "").strip().lower() == "application/ld+json"
            ):
                # Nur ausserhalb eines template gilt das JSON-LD als
                # gefunden: Google sieht ein Template so wenig wie der
                # Browser, egal dass der Fund selbst in einem script-Tag
                # liegt.
                self._in_ldjson = True
                self._ldjson_buffer = ""
        elif tag == "svg":
            self._svg_depth += 1
        elif tag == "title":
            # Nur das erste <title> ausserhalb von SVG und <template>.
            if self._template_depth == 0 and self._svg_depth == 0 and self.title is None:
                self._in_title = True
                self._title_buffer = ""
        elif tag == "h1":
            if not self._hidden:
                self._in_h1 = True
                self._h1_buffer = ""
        elif tag == "base":
            # Nur das erste <base href> zählt, wie im Browser auch. Ein
            # <base> in einem Template wirkt in keinem Browser auf die
            # Seite, zählt also auch hier nicht.
            if self._template_depth == 0 and self.base_href is None:
                href = attrs_dict.get("href")
                if href:
                    self.base_href = href
        elif tag == "meta":
            # Ein Robots-Meta oder eine Description in einem Template wirken
            # auf keiner gerenderten Seite, zählen also auch hier nicht.
            if self._template_depth == 0:
                name = (attrs_dict.get("name") or "").strip().lower()
                content = attrs_dict.get("content") or ""
                if name == "description":
                    self.description = content
                elif name == "robots":
                    directives = {d.strip().lower() for d in content.split(",")}
                    if directives & NOINDEX_DIRECTIVES:
                        self.indexable = False
        elif tag == "link":
            # Ein Canonical oder hreflang in einem Template zeigt auf keiner
            # gerenderten Seite, zählt also auch hier nicht.
            if self._template_depth == 0:
                rel = (attrs_dict.get("rel") or "").strip().lower()
                href = attrs_dict.get("href")
                if href and rel == "canonical":
                    # Zwei Canonical auf einer Seite sind selbst ein Befund:
                    # Theme und App setzen gern je eins. canonical_count
                    # hält das fest, canonical bleibt das zuletzt gefundene.
                    self.canonical = href
                    self.canonical_count += 1
                elif href and rel == "alternate" and attrs_dict.get("hreflang"):
                    self.hreflang[attrs_dict["hreflang"]] = href
        elif tag == "img":
            if not self._hidden:
                self.images["total"] += 1
                alt = attrs_dict.get("alt")
                if alt is None:
                    # Fehlendes alt ist der Befund, leeres alt ist bei Deko korrekt.
                    self.images["without_alt"] += 1
                elif alt == "":
                    self.images["empty_alt"] += 1
                elif not alt.strip():
                    # Nur Leerzeichen ist weder brauchbarer Alt-Text noch die
                    # bewusste Deko-Markierung alt="". Für den Report ist das
                    # dieselbe Tatsache wie ein fehlendes alt.
                    self.images["without_alt"] += 1
        elif tag == "a":
            href = attrs_dict.get("href")
            if href and not self._hidden:
                self.raw_links.append(href)

    def handle_endtag(self, tag: str) -> None:
        if tag == "body":
            self._in_body = False
        elif tag == "template":
            if self._template_depth > 0:
                self._template_depth -= 1
        elif tag in ("script", "style"):
            if self._script_style_depth > 0:
                self._script_style_depth -= 1
            if tag == "script" and self._in_ldjson:
                self._in_ldjson = False
                _collect_schema_types(self._ldjson_buffer, self.schema_types)
                _collect_markup(self._ldjson_buffer, self.markup)
        elif tag == "svg":
            self._svg_depth = max(0, self._svg_depth - 1)
        elif tag == "title":
            if self._in_title:
                self._in_title = False
                self.title = self._title_buffer.strip()
        elif tag == "h1":
            if self._in_h1:
                self._in_h1 = False
                self.h1.append(self._h1_buffer.strip())

    def handle_data(self, data: str) -> None:
        if self._script_style_depth > 0 and self._template_depth == 0:
            # Nur die IDs, nie der Skript-Inhalt: der bleibt inert und wird
            # weder gespeichert noch ausgewertet.
            self._inline_tag_ids.update(INLINE_TAG_ID.findall(data))
        if self._in_ldjson:
            self._ldjson_buffer += data
        if self._in_title:
            self._title_buffer += data
        if self._in_h1:
            self._h1_buffer += data
        if self._in_body and not self._hidden:
            self.word_count += len(data.split())


def _collect_schema_types(raw_json: str, target: set[str]) -> None:
    """Trägt alle `@type`-Werte eines JSON-LD-Blocks in `target` ein.

    Ein kaputtes JSON-LD (Tippfehler im Theme, abgeschnittenes Snippet) darf
    das Parsen der übrigen Seite nicht zum Absturz bringen, deshalb wird ein
    Fehler hier verschluckt statt geworfen.
    """
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError:
        return
    _collect_schema_node(data, target)


def _collect_schema_node(node, target: set[str]) -> None:
    if isinstance(node, list):
        for entry in node:
            _collect_schema_node(entry, target)
        return
    if not isinstance(node, dict):
        return

    schema_type = node.get("@type")
    if isinstance(schema_type, str):
        target.add(schema_type)
    elif isinstance(schema_type, list):
        target.update(t for t in schema_type if isinstance(t, str))

    graph = node.get("@graph")
    if isinstance(graph, list):
        for entry in graph:
            _collect_schema_node(entry, target)


#: Typen, die als Produktauszeichnung zählen. ProductGroup trägt bei Themes
#: mit Varianten die gemeinsamen Felder, die Angebote hängen dann an den
#: Varianten in `hasVariant`.
PRODUCT_TYPES = {"Product", "ProductGroup"}

#: Typen, die als Auszeichnung des Händlers zählen.
ORGANIZATION_TYPES = {"Organization", "OnlineStore", "OnlineBusiness", "Corporation", "Store"}

#: Produktkennungen, von denen Google im Merchant Listing eine empfiehlt.
PRODUCT_IDENTIFIERS = ("gtin", "gtin8", "gtin12", "gtin13", "gtin14", "isbn", "mpn", "sku")


def _node_types(node: dict) -> set[str]:
    kind = node.get("@type")
    if isinstance(kind, str):
        return {kind}
    if isinstance(kind, list):
        return {k for k in kind if isinstance(k, str)}
    return set()


def _top_level_nodes(data) -> list[dict]:
    """Die Knoten auf oberster Ebene eines JSON-LD-Blocks, `@graph` aufgelöst.

    Bewusst dieselbe Tiefe wie `_collect_schema_node`: eine Kategorieseite
    listet ihre Produkte oft als `ItemList` mit verschachtelten
    `Product`-Knoten. Die sind keine Produktauszeichnung der Seite, sonst trüge
    jede Kategorieseite scheinbar ein Produkt-Schema.
    """
    nodes = []
    for node in data if isinstance(data, list) else [data]:
        if not isinstance(node, dict):
            continue
        graph = node.get("@graph")
        if isinstance(graph, list):
            nodes.extend(entry for entry in graph if isinstance(entry, dict))
        nodes.append(node)
    return nodes


def _first_dict(value) -> dict | None:
    if isinstance(value, list):
        value = next((entry for entry in value if isinstance(entry, dict)), None)
    return value if isinstance(value, dict) else None


def _present(value) -> bool:
    """Feld gepflegt? Leerstring, leere Liste und `null` zählen nicht."""
    if isinstance(value, str):
        return bool(value.strip())
    return value not in (None, [], {})


def _schema_value(value) -> str | None:
    """`https://schema.org/InStock` wird zu `InStock`, wie Google es liest."""
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip().rsplit("/", 1)[-1]


def _offer_price(offer: dict) -> tuple[str | None, str | None]:
    """Preis und Währung eines Angebots, auch aus `priceSpecification` und
    `AggregateOffer` (`lowPrice`)."""
    spec = _first_dict(offer.get("priceSpecification")) or {}
    price = next((offer.get(key) for key in ("price", "lowPrice")
                  if _present(offer.get(key))), None)
    if price is None and _present(spec.get("price")):
        price = spec.get("price")
    currency = offer.get("priceCurrency") or spec.get("priceCurrency")
    return (str(price) if price is not None else None,
            str(currency) if _present(currency) else None)


def _product_fields(node: dict) -> dict:
    variants = node.get("hasVariant")
    variants = [v for v in (variants if isinstance(variants, list) else [variants])
                if isinstance(v, dict)]
    offer = _first_dict(node.get("offers"))
    if offer is None:
        # ProductGroup: das Angebot steht an der ersten Variante, die eins hat.
        offer = next((o for o in (_first_dict(v.get("offers")) for v in variants) if o), None)
    price, currency = _offer_price(offer) if offer else (None, None)
    identified = any(_present(node.get(k)) for k in PRODUCT_IDENTIFIERS) or any(
        _present(v.get(k)) for v in variants for k in PRODUCT_IDENTIFIERS)
    return {
        "has_name": _present(node.get("name")),
        "has_image": _present(node.get("image")),
        "has_brand": _present(node.get("brand")),
        "has_identifier": identified,
        "has_offers": offer is not None,
        "price": price,
        "currency": currency,
        "availability": _schema_value(offer.get("availability")) if offer else None,
        "has_shipping_details": bool(offer) and _present(offer.get("shippingDetails")),
        "has_return_policy": bool(offer) and _present(offer.get("hasMerchantReturnPolicy")),
        "has_aggregate_rating": _present(node.get("aggregateRating")),
        "has_variants": bool(variants),
    }


def _merge_product(current: dict | None, new: dict) -> dict:
    """Mehrere Product-Knoten auf einer Seite (Theme plus App) zu einer Zeile.

    Ein Feld gilt als vorhanden, wenn es in irgendeinem Knoten steht: Google
    liest alle Blöcke der Seite. Werte (Preis, Währung, Verfügbarkeit) nimmt
    der erste Knoten, der einen trägt. `count` hält fest, wie viele Knoten es
    waren, denn doppelte Produktauszeichnung ist selbst ein Befund.
    """
    if current is None:
        return {**new, "count": 1}
    merged = {"count": current["count"] + 1}
    for key, value in new.items():
        old = current.get(key)
        merged[key] = (old or value) if isinstance(value, bool) else (old if old is not None else value)
    return merged


def _collect_markup(raw_json: str, target: dict) -> None:
    """Trägt die Felder der Product- und Organization-Auszeichnung ein.

    Ergebnis unter `target["product"]` und `target["organization"]`, nur wenn
    die Seite so einen Knoten trägt. Kaputtes JSON-LD wird wie bei
    `_collect_schema_types` verschluckt.

    Die Feldliste folgt Google Search Central, Merchant Listing (Pflicht:
    name, image, offers mit price und priceCurrency; empfohlen: availability,
    Kennung, shippingDetails, hasMerchantReturnPolicy). Versand und Rückgabe
    dürfen stattdessen global an der Organization stehen, als
    `hasShippingService` und `hasMerchantReturnPolicy`; deshalb werden beide
    Stellen erfasst.
    """
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError:
        return
    for node in _top_level_nodes(data):
        kinds = _node_types(node)
        if kinds & PRODUCT_TYPES:
            target["product"] = _merge_product(target.get("product"), _product_fields(node))
        if kinds & ORGANIZATION_TYPES and "organization" not in target:
            same_as = node.get("sameAs")
            target["organization"] = {
                "has_logo": _present(node.get("logo")),
                "same_as": (len(same_as) if isinstance(same_as, list)
                            else int(_present(same_as))),
                "has_shipping_service": _present(node.get("hasShippingService")),
                "has_return_policy": _present(node.get("hasMerchantReturnPolicy")),
            }


def parse_page(html: str, url: str) -> dict:
    """Parst eine Seite und liefert ein JSON-fähiges Ergebnis-Dict.

    `url` ist die absolute Adresse der Seite selbst. Sie dient als Basis für
    relative Referenzen und als Referenz-Host für `normalize`, damit
    interne von externen Links getrennt werden.

    Setzt die Seite ein `<base href>` im Head, gilt das statt `url` als
    Basis: manche Shopify-Themes tun das, und ohne Auswertung würde jeder
    relative Link der Seite auf den falschen Pfad zeigen, ohne dass irgendwo
    ein Fehler entsteht, nur der Linkgraph des Shops stimmt dann nicht mehr.

    `<template>` ist inert: kein Browser rendert seinen Inhalt, also zählt
    hier auch nichts davon, weder `h1` noch `word_count` noch `internal_links`
    noch `images` noch `schema_types`. Das gilt genauso für die Kopfdaten:
    `title`, Meta-Description, Canonical, hreflang, Robots-Meta und
    `<base href>` in einem Template wirken auf keiner gerenderten Seite und
    zählen deshalb auch hier nicht. Die Regel kennt keine Ausnahme, auch
    nicht bei den Kopfdaten: ein `noindex` in einem Template würde eine
    indexierte Seite sonst als nicht indexierbar ausweisen, ein
    Falschbefund, der niemandem hilft. Shopify-Themes verstecken darin
    Quick-View-Modals, "zuletzt angesehen" und Empfehlungs-Widgets, und eine
    einzige solche Seite würde sonst H1-Zählung, Wortzahl und Linkgraph
    verfälschen, dazu Alt-Text-Befunde über Bilder erzeugen, die auf der
    gerenderten Seite gar nicht existieren, und ein `Offer`- oder sonstiges
    Schema melden, das Google nie sieht. Der Template-Tiefenzähler ist dabei
    getrennt vom `script`/`style`-Zähler: JSON-LD steckt selbst immer in
    einem `script`-Tag und muss weiter gelesen werden, ein gemeinsamer
    Zähler würde entweder die strukturierten Daten jeder Seite verschlucken
    oder die im Template durchlassen.

    Vorbehalt zu `word_count`: gezählt wird der ganze sichtbare Body, also
    auch Navigation, Footer und Newsletter-Block, die auf jeder Seite gleich
    sind. Die Zahl taugt zum Vergleich zwischen Seiten desselben Shops, aber
    nicht als absoluter Wert für einen Befund "dünner Inhalt".
    """
    parser = _PageParser()
    parser.feed(html)

    base = urljoin(url, parser.base_href) if parser.base_href else url

    internal_links: list[str] = []
    for raw in parser.raw_links:
        target = normalize(raw, base)
        if target is not None and target not in internal_links:
            internal_links.append(target)

    return {
        "title": parser.title,
        "description": parser.description,
        "canonical": urljoin(base, parser.canonical) if parser.canonical else None,
        "canonical_count": parser.canonical_count,
        "hreflang": {code: urljoin(base, target) for code, target in parser.hreflang.items()},
        "h1": parser.h1,
        "images": parser.images,
        "schema_types": sorted(parser.schema_types),
        # Felder der Product- und Organization-Auszeichnung, nur wenn es sie
        # gibt. Aus statischem HTML: per JavaScript eingefügtes JSON-LD fehlt
        # hier, bevor ein Befund "fehlt" entsteht, prüft die Analyse
        # gerendert gegen (Kriterium tec.rendered-check).
        "markup": parser.markup,
        # Fremde Skripte, die die Seite lädt. Nicht ihr Inhalt: der bleibt
        # inert. Daran hängen Preistest-Werkzeuge, Bewertungs-Apps,
        # Consent-Banner und doppelte Analytics-Einbindungen, und genau die
        # muss die Datenqualitäts-Analyse sehen können.
        "script_sources": sorted(set(parser._script_sources)),
        "inline_tag_ids": sorted(parser._inline_tag_ids),
        "indexable": parser.indexable,
        "internal_links": internal_links,
        "word_count": parser.word_count,
    }


def sitemap_children(xml_bytes: bytes) -> list[str]:
    """Liest die Kind-Sitemaps aus einem Sitemap-Index.

    Sitemaps tragen fast immer den Namespace der sitemaps.org-Spec
    (`http://www.sitemaps.org/schemas/sitemap/0.9`); ein naiver Tag-Match auf
    "sitemap" oder "loc" liefe deshalb ins Leere. Das Wildcard `{*}` matcht
    das Element unabhängig vom konkreten Namespace-URI.
    """
    root = ET.fromstring(xml_bytes)
    return [
        loc.text.strip()
        for loc in root.findall("{*}sitemap/{*}loc")
        if loc.text and loc.text.strip()
    ]


def sitemap_urls(xml_bytes: bytes) -> list[str]:
    """Liest die URLs aus einem Sitemap-Urlset.

    Ein Anker in einer Sitemap-URL ergibt keine eigene Seite und fällt weg,
    eine doppelt gelistete URL wird nur einmal zurückgegeben. Die Reihenfolge
    des ersten Vorkommens bleibt erhalten.
    """
    root = ET.fromstring(xml_bytes)
    seen: list[str] = []
    for loc in root.findall("{*}url/{*}loc"):
        if not loc.text:
            continue
        url = loc.text.strip().split("#", 1)[0]
        if url and url not in seen:
            seen.append(url)
    return seen

# ---------------------------------------------------------------------------
# Abruf-Hälfte: robots.txt, Sitemap-Baum, Redirect-Ketten, Breitensuche, CLI.
# ---------------------------------------------------------------------------

#: Der Name, unter dem eine robots.txt diesen Crawler anspricht, im Sinn von
#: RFC 9309 das Produkt-Token. So schreibt ihn ein Shop in seine Gruppe:
#: `User-agent: ptai-audit`. Welche Gruppe gilt, entscheidet
#: `select_robots_group`.
ROBOTS_TOKEN = "ptai-audit"

#: Eigener User-Agent, damit der Kunde und Dritte den Audit-Bot erkennen.
#:
#: **Die `Mozilla/5.0 (compatible; ...)`-Form ist Absicht, keine Tarnung.** Sie
#: ist die uebliche Schreibweise eines angemeldeten Crawlers (Googlebot,
#: Bingbot und jeder serioese SEO-Crawler schreiben sich genauso), und
#: Bot-Management-Systeme werten ein nacktes Kuerzel wie "ptai-audit/1.0" als
#: unidentifiziertes Skript. Der Name und die Kontakt-URL stehen unveraendert
#: darin: wer wissen will, wer da crawlt, liest es im Log.
#:
#: Der Name kommt aus `ROBOTS_TOKEN`, damit eine robots.txt-Gruppe, die ein
#: Shop nach seinem Log schreibt, auch die ist, die der Crawl befolgt.
USER_AGENT = (f"Mozilla/5.0 (compatible; {ROBOTS_TOKEN}/1.0; "
              "+https://path-to-ai.com/crawler)")

#: Timeout je einzelnem Abruf, Sekunden.
TIMEOUT_SECONDS = 15

#: Statuscodes, die als Weiterleitung gelten (301/302/303/307/308).
REDIRECT_CODES = {301, 302, 303, 307, 308}

#: Harte Grenze gegen einen Redirect-Loop. Wird sie erreicht, ist das selbst
#: ein Befund (kaputte Weiterleitungskette), kein stiller Abbruch.
MAX_REDIRECTS = 10

#: Harte Grenze gegen einen zyklischen Sitemap-Verweis. Sitemap-Indizes sind
#: in der Praxis nie tiefer als zwei Ebenen, fünf ist eine großzügige Reserve.
MAX_SITEMAP_DEPTH = 5

#: Bekannte KI-Crawler-User-Agents, gegen robots.txt-Gruppen abgeglichen.
#: Diese Liste veraltet: neue Crawler kommen laufend dazu. Sie lebt bewusst
#: als Modul-Konstante, damit sie an einer Stelle nachgezogen werden kann,
#: ohne die Parsing-Logik anzufassen.
AI_CRAWLERS = (
    "GPTBot", "ChatGPT-User", "OAI-SearchBot",
    "ClaudeBot", "Claude-User", "Claude-SearchBot", "anthropic-ai",
    "PerplexityBot", "Perplexity-User",
    "Google-Extended", "CCBot", "Bytespider", "Amazonbot",
    "cohere-ai", "Applebot-Extended", "meta-externalagent", "Diffbot",
)


def error_reason(exc: Exception) -> str:
    """Eine Exception aus einem Abruf in eine knappe, deutsche Meldung wandeln.

    Bewusst eine eigene kleine Variante statt des geteilten
    `api_common.describe_error`: dessen Wortlaut ("API nicht erreichbar")
    passt zu den Google-API-Pulls, nicht zu einem Seitenabruf, und sein
    Versuch, den Fehlerkörper als JSON zu lesen, geht an einer
    Shopify-Storefront-Antwort ohnehin fast immer vorbei.
    """
    if isinstance(exc, urllib.error.URLError):
        return f"nicht erreichbar: {exc.reason}"
    return str(exc)


def _build_opener() -> urllib.request.OpenerDirector:
    """Baut einen Opener, der Weiterleitungen nie automatisch folgt.

    Automatisches Folgen (der Default von `urllib`) würde die Kette selbst
    verschlucken, und die Kette ist hier der Befund, nicht ihr Endpunkt.
    `redirect_request` gibt `None` zurück, damit die Weiterleitung als
    `HTTPError` mit dem `Location`-Header beim Aufrufer ankommt, statt dass
    `urllib` ihr selbst folgt.
    """
    class _NoAutoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    return urllib.request.build_opener(_NoAutoRedirect)


def _real_fetch(opener: urllib.request.OpenerDirector, url: str, timeout: float) -> dict:
    """Der einzige Punkt, der wirklich das Netz anfasst: ein GET ohne
    automatische Weiterleitung.

    Liefert immer ein Dict `{"status", "headers", "body", "location"}`,
    `location` ist der aufgelöste `Location`-Header bei einer Weiterleitung,
    sonst `None`. Ein echter Netzwerkfehler (DNS, Verbindung, Timeout) wird
    nicht abgefangen, sondern wirft weiter: das ist die einzige Stelle, an
    der eine einzelne URL den Lauf nicht beenden darf, und das entscheidet
    der Aufrufer (`process_page`, `fetch_robots`, `resolve_sitemap_tree`),
    nicht diese Funktion.

    Bewusst kein `Accept-Encoding: gzip`: eine HTML-Seite kommt damit
    unkomprimiert, was für den Fließtext- und Kopfdaten-Umfang einer Seite
    unerheblich ist und die Logik hier einfach hält. Ein `.gz`-komprimiertes
    Sitemap-Dokument ist ein eigener Fall, siehe `_is_gzip`.
    """
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with opener.open(req, timeout=timeout) as resp:
            body = resp.read()
            headers = {k.lower(): v for k, v in resp.headers.items()}
            return {"status": resp.status, "headers": headers, "body": body, "location": None}
    except urllib.error.HTTPError as exc:
        headers = {k.lower(): v for k, v in (exc.headers or {}).items()}
        location = headers.get("location") if exc.code in REDIRECT_CODES else None
        body = b"" if location else _safe_read(exc)
        return {"status": exc.code, "headers": headers, "body": body, "location": location}


def bot_challenge(status: int | None, headers: dict) -> str | None:
    """Erkennt, ob eine abweisende Antwort eine Bot-Challenge ist statt einer
    Drosselung. Liefert den Grund als Text, sonst `None`.

    **Der Unterschied entscheidet ueber Stunden.** Eine Drosselung sagt "zu
    schnell", und langsamer werden hilft. Eine Challenge sagt "du siehst aus
    wie ein Bot", und langsamer werden hilft nie: die Antwort kommt in
    Millisekunden zurueck, egal wie lange wir vorher gewartet haben. Am
    08.09.2026 lief ein Crawl drei Stunden gegen genau das an, weil beides als
    HTTP 429 ankommt und der Crawl nur den Statuscode ansah.

    Das verlaessliche Signal ist Cloudflares `Cf-Mitigated`-Header. Ein 429
    von Cloudflare ohne `Retry-After` ist der zweite Fall: eine echte
    Drosselung nennt fast immer, wann es wieder geht.

    Was hier **nicht** passiert: die Challenge loesen. Ein Crawler, der eine
    Bot-Erkennung umgeht, ist genau der Bot, gegen den sie gebaut ist. Der Weg
    heraus fuehrt ueber den Kunden, der den Crawler in seiner WAF freigibt.
    """
    if status not in (403, 429, 503):
        return None
    mitigated = (headers.get("cf-mitigated") or "").strip().lower()
    if mitigated:
        return f"Cloudflare-Bot-Management ({mitigated})"
    server = (headers.get("server") or "").strip().lower()
    if server == "cloudflare" and status == 429 and not headers.get("retry-after"):
        return "Cloudflare-Bot-Management (429 ohne Retry-After)"
    return None


def _safe_read(exc: urllib.error.HTTPError) -> bytes:
    """Liest den Fehlerkörper, ohne bei einem bereits geschlossenen Stream
    eine zweite Exception zu riskieren."""
    try:
        return exc.read()
    except Exception:
        return b""


def _is_gzip(body: bytes, headers: dict, url: str) -> bool:
    """Erkennt ein gzip-komprimiertes Sitemap-Dokument.

    Die Magic-Number ist das verlässliche Signal (funktioniert immer), der
    `Content-Encoding`-Header und die `.gz`-Endung der URL sind zusätzliche
    Hinweise für den Fall, dass die Bytes aus irgendeinem Grund schon anders
    ankommen.
    """
    if body[:2] == b"\x1f\x8b":
        return True
    if "gzip" in (headers.get("content-encoding") or "").lower():
        return True
    return url.endswith(".gz")


def fetch_page(url: str, fetch, max_redirects: int = MAX_REDIRECTS) -> dict:
    """Verfolgt Weiterleitungen manuell und liefert Statuscode, vollständige
    Kette, Endadresse, Body und Ladezeit.

    `fetch` ist die injizierbare Einzel-Abruf-Funktion `url -> dict`
    (Produktion: an `_real_fetch` gebunden; Tests: eine programmierte
    Antwortfolge), damit diese Funktion die Redirect-Kette ganz ohne
    Netzwerk durchspielen kann. Ein echter Netzwerkfehler aus `fetch` wird
    hier nicht abgefangen, sondern wirft weiter zum Aufrufer.

    Überschreitet die Kette `max_redirects`, ist das selbst ein Befund
    (Redirect-Loop): `status` wird `None`, `error` trägt die Meldung, die
    schon durchlaufene Kette bleibt erhalten statt zu verschwinden.
    """
    chain: list[dict] = []
    current_url = url
    start = time.monotonic()
    for _ in range(max_redirects):
        response = fetch(current_url)
        chain.append({"url": current_url, "status": response["status"]})
        if response["status"] in REDIRECT_CODES and response.get("location"):
            current_url = urljoin(current_url, response["location"])
            continue
        return {
            "status": response["status"],
            "chain": chain,
            "end_url": current_url,
            "body": response["body"],
            "headers": response["headers"],
            "load_time_sec": round(time.monotonic() - start, 3),
        }
    return {
        "status": None,
        "chain": chain,
        "end_url": current_url,
        "body": b"",
        "headers": {},
        "load_time_sec": round(time.monotonic() - start, 3),
        "error": f"mehr als {max_redirects} Weiterleitungen (Redirect-Loop)",
    }


def process_page(url: str, fetch) -> dict:
    """Ruft eine Seite ab und parst sie bei einer 2xx-HTML-Antwort.

    Ein echter Netzwerkfehler, eine zu lange Weiterleitungskette oder ein
    Nicht-HTML-Content-Type auf einer 2xx-Antwort landen als `error` im
    Ergebnis und werfen nie: das ist die Umsetzung von "ein Fehler bei einer
    URL beendet nie den Lauf" auf Seiten-Ebene. Ein regulärer 404 oder 500
    ist dagegen kein Fehler in diesem Sinn, sondern selbst der Befund: der
    Statuscode steht im Ergebnis, nur ohne SEO-Kopfdaten dazu, weil es dafür
    keinen auswertbaren Seiteninhalt gibt.
    """
    try:
        response = fetch_page(url, fetch)
    except Exception as exc:
        return {"url": url, "error": error_reason(exc)}

    entry = {
        "url": url,
        "status": response["status"],
        "redirects": response["chain"][:-1],
        "end_url": response["end_url"],
        "load_time_sec": response["load_time_sec"],
    }
    if response.get("error"):
        entry["error"] = response["error"]
        return entry
    if not (response["status"] and 200 <= response["status"] < 300):
        reason = bot_challenge(response["status"], response.get("headers") or {})
        if reason:
            entry["bot_challenge"] = reason
        return entry

    content_type = response["headers"].get("content-type") or ""
    if content_type and "html" not in content_type.lower():
        entry["error"] = f"kein HTML (Content-Type: {content_type})"
        return entry

    html = response["body"].decode("utf-8", errors="replace")
    entry.update(parse_page(html, response["end_url"]))
    return entry


def parse_robots(text: str) -> dict:
    """Liest robots.txt: Sitemaps, Disallow-Regeln je User-Agent-Gruppe,
    gefundene KI-Crawler-Regeln.

    Bewusst kein vollständiger robots.txt-Interpreter nach RFC 9309: keine
    Präzedenz-Auswertung (Googles "längste Übereinstimmung gewinnt"), nur die
    wörtlichen Gruppen und ihre `Disallow`-Zeilen. Für die Report-Anzeige
    unter `disallow_rules` reicht der wörtliche Text, das behauptet dieses
    Feld nicht mehr als "dieser Crawler ist genannt und das ist sein
    Regelsatz". Welche Gruppe den Crawl lenkt, entscheidet
    `select_robots_group`, die Wildcard-Auswertung ihrer Regeln sitzt
    getrennt davon in `robots_path_blocked`.

    Eine neue `User-agent`-Zeile beginnt eine neue Gruppe, sobald für die
    vorherige schon eine Regel (`Disallow`/`Allow`) gesehen wurde; mehrere
    `User-agent`-Zeilen direkt hintereinander teilen sich dieselbe Gruppe
    (Standardverhalten für "diese Agents bekommen dieselben Regeln").
    """
    sitemaps: list[str] = []
    groups: dict[str, list[str]] = {}
    current_agents: list[str] = []
    in_rule_block = False

    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip().lower()
        value = value.strip()

        if key == "sitemap":
            if value:
                sitemaps.append(value)
        elif key == "user-agent":
            if in_rule_block:
                current_agents = []
                in_rule_block = False
            if value:
                current_agents.append(value)
                groups.setdefault(value, [])
        elif key == "disallow":
            in_rule_block = True
            if value:
                for agent in current_agents:
                    groups[agent].append(value)
        elif key == "allow":
            in_rule_block = True

    groups_lower = {agent.lower(): agent for agent in groups}
    ai_rules = {}
    for known in AI_CRAWLERS:
        match = groups_lower.get(known.lower())
        if match is not None:
            ai_rules[known] = "disallow" if "/" in groups[match] else "allowed"

    return {"sitemaps": sitemaps, "disallow_rules": groups, "ai_crawler_rules": ai_rules}


#: Die Zeichen, aus denen ein Produkt-Token nach RFC 9309 bestehen darf.
_PRODUCT_TOKEN = re.compile(r"[A-Za-z_-]*")


def robots_product_token(value: str) -> str:
    """Der vergleichbare Teil einer `User-agent`-Zeile, kleingeschrieben.

    RFC 9309 erlaubt im Produkt-Token nur Buchstaben, Bindestrich und
    Unterstrich, und Googles Referenz-Parser liest eine Zeile genau bis zum
    ersten anderen Zeichen. So trifft `User-agent: ptai-audit/1.0` denselben
    Crawler wie `User-agent: ptai-audit`, `User-agent: ptai-audit-beta` aber
    nicht: das ist ein anderer Name, kein Präfix. Kleingeschrieben, weil der
    Vergleich laut RFC nicht auf Groß- und Kleinschreibung achtet.
    """
    return _PRODUCT_TOKEN.match(value.strip()).group(0).lower()


def select_robots_group(disallow_rules: dict[str, list[str]],
                        token: str = ROBOTS_TOKEN) -> tuple[str | None, list[str]]:
    """Welche robots.txt-Gruppe für diesen Crawler gilt, und ihre Disallow-Regeln.

    Die Reihenfolge schreibt RFC 9309 in Abschnitt 2.2.1 vor. Gibt es eine
    Gruppe für den eigenen Namen, gilt nur sie, und die Gruppe `*` ist für
    diesen Crawler bedeutungslos, auch wenn sie mehr sperrt. Erst ohne
    eigene Gruppe gilt `*`. Gibt es beides nicht, gilt keine Regel.

    Eine eigene Gruppe ist der übliche Weg, auf dem die IT eines Shops einen
    bestimmten Bot aussperrt: `User-agent: ptai-audit` mit `Disallow: /`.
    Bis zum 23.09.2026 las der Crawl nur die Gruppe `*` und ging über genau
    diese Absage hinweg.

    Die eigene Gruppe wird über `robots_product_token` gefunden, also
    unabhängig von Groß- und Kleinschreibung und einer Versionsangabe. Stehen
    mehrere solche Gruppen in der Datei, gelten ihre Regeln zusammen, wie es
    die RFC verlangt. Eine eigene Gruppe ohne Regel ist eine Freigabe: sie
    sperrt nichts, auch nicht das, was `*` sperrt.

    `Allow` bleibt wie überall in dieser Datei unausgewertet. Das irrt in die
    vorsichtige Richtung: der Crawl ruft dann eher zu wenig ab als zu viel.

    Rückgabe ist `(group, rules)`: `token` für die eigene Gruppe, `"*"` für
    die allgemeine, `None`, wenn keine gilt.
    """
    wanted = token.lower()
    own = [agent for agent in disallow_rules if robots_product_token(agent) == wanted]
    if own:
        rules: list[str] = []
        for agent in own:
            for rule in disallow_rules[agent]:
                if rule not in rules:
                    rules.append(rule)
        return token, rules
    if "*" in disallow_rules:
        return "*", list(disallow_rules["*"])
    return None, []


#: Erkennt eine Prozent-Kodierung (zwei Hex-Ziffern nach `%`).
_PERCENT_HEX = re.compile(r"%[0-9a-fA-F]{2}")


def _percent_uppercase(text: str) -> str:
    """Vereinheitlicht Prozent-kodierte Bytes auf Großbuchstaben-Hexziffern.

    RFC 3986 zählt die Hex-Ziffern einer Prozent-Kodierung als
    case-insensitiv: `%2b` und `%2B` meinen dasselbe Zeichen. Ellis robots.txt
    führt eine eigene Regel für `%2B` (Shopify-Tag-Filter mit Leerzeichen
    werden so kodiert); ohne diese Vereinheitlichung würde ein Theme, das
    `%2b` kleingeschrieben ausgibt, an der Regel vorbeirutschen, obwohl es
    dieselbe Filterkombination meint.
    """
    return _PERCENT_HEX.sub(lambda match: match.group(0).upper(), text)


@functools.lru_cache(maxsize=None)
def _disallow_pattern(rule: str):
    """Kompiliert eine Disallow-Regel zu einem Pfad-Präfix-Pattern.

    Nur zwei Zeichen bekommen eine Sonderbedeutung, mehr braucht echte
    robots.txt nicht: `*` steht für eine beliebige Zeichenfolge, auch leer,
    `$` verankert das Zeilenende, wenn es die Regel abschließt. Alles andere
    ist wörtlich. Ohne `$` gilt eine Regel als Präfix, wie in der Praxis und
    bei Google üblich: `Disallow: /admin` sperrt auch `/admin/login`.

    `@functools.lru_cache` spart das erneute Kompilieren derselben Regel über
    Tausende Frontier-URLs eines Laufs hinweg; die Regelmenge einer robots.txt
    ist klein und ändert sich innerhalb eines Laufs nie.
    """
    rule = _percent_uppercase(rule)
    anchored = rule.endswith("$")
    core = rule[:-1] if anchored else rule
    pattern = ".*".join(re.escape(part) for part in core.split("*"))
    if anchored:
        pattern += "$"
    return re.compile("^" + pattern)


def robots_path_blocked(path_and_query: str, disallow_rules: list[str]) -> bool:
    """Prüft einen URL-Pfad (mit Query, falls vorhanden, genau wie er in der
    URL steht) gegen die Disallow-Regeln einer robots.txt-Gruppe, üblicherweise
    die von `User-agent: *`.

    Geprüft an der echten robots.txt von beispielshop.example (05.09.2026, Shopify-
    Standard): sie besteht fast nur aus Wildcard-Regeln auf Filter- und
    Sortier-URLs (`/collections/*sort_by*`, `/collections/*+*`,
    `*/collections/*filter*&*filter*`). Shopify baut Tag-Filter als
    Pfadsegment, nicht als Query, `normalize` fängt das also nicht ab,
    das Disallow muss es.
    """
    target = _percent_uppercase(path_and_query)
    return any(_disallow_pattern(rule).match(target) for rule in disallow_rules)


def _robots_target(url: str) -> str:
    """Pfad samt Query einer Adresse, so wie `robots_path_blocked` ihn prüft.

    Seit `normalize` die Blätterseite behält (`?page=2`), kann eine Adresse
    eine Query tragen. Eine Regel wie `Disallow: /*?page=` greift nur, wenn
    die Query mitgeprüft wird; mit dem Pfad allein riefe der Crawl gesperrte
    Folgeseiten ab.
    """
    parts = urlparse(url)
    return f"{parts.path}?{parts.query}" if parts.query else parts.path


def is_home_blocked(home: str, group: str | None, rules: list[str]) -> bool:
    """Ob der Crawl gar nicht erst starten darf, weil die eigene Gruppe die
    Startseite sperrt.

    Nur die eigene Gruppe hat diese Wirkung. Ein `Disallow: /` unter `*`
    richtet sich an alle Suchmaschinen und ist selbst ein Befund, den der
    Audit zeigen muss: ein Shop, der sich aus Google aussperrt. Dort ruft der
    Crawl die Startseite weiter ab, wie es `crawl` beschreibt. Eine eigene
    Gruppe richtet sich an genau diesen Crawler, und dann heißt die Antwort
    nein.

    Geprüft wird der Pfad der Startseite gegen die Regeln, nicht das
    wörtliche `/`, denn auch `/*`, `*` und `/$` sperren sie. Sperrt die
    Gruppe die Startseite, läuft der Crawl auch dann nicht, wenn sie andere
    Pfade offen ließe. Ohne Startseite gibt es keine Klicktiefe, jede Seite
    aus der Sitemap stünde als verwaist im Snapshot, und das wäre ein
    Falschbefund.
    """
    if group is None or group == "*":
        return False
    return robots_path_blocked(urlparse(home).path or "/", rules)


def fetch_robots(base: str, fetch) -> dict:
    """Liest robots.txt über `fetch` und wertet sie aus.

    Fehlt sie oder ist sie nicht erreichbar, ist das kein Fehler des Laufs:
    viele Shops haben keine robots.txt, der Crawl fällt dann auf
    `{base}/sitemap.xml` zurück (siehe `determine_sitemap_roots`). Diese
    Funktion wirft deshalb nie, sie liefert immer ein vollständiges Dict,
    bei einem Fehlschlag mit `found: False` und `reason`.
    """
    empty_result = {"sitemaps": [], "disallow_rules": {}, "ai_crawler_rules": {}}
    url = base.rstrip("/") + "/robots.txt"
    try:
        response = fetch(url)
    except Exception as exc:
        return {"found": False, "reason": error_reason(exc), **empty_result}
    if response["status"] != 200:
        return {"found": False, "reason": f"HTTP {response['status']}", **empty_result}
    text = response["body"].decode("utf-8", errors="replace")
    return {"found": True, **parse_robots(text)}


def determine_sitemap_roots(base: str, robots: dict) -> list[str]:
    """Die Sitemap-Wurzeln: aus robots.txt, sonst Fallback `{base}/sitemap.xml`."""
    if robots.get("sitemaps"):
        return list(robots["sitemaps"])
    return [urljoin(base.rstrip("/") + "/", "sitemap.xml")]


def resolve_sitemap_tree(roots: list[str], fetch,
                          max_depth: int = MAX_SITEMAP_DEPTH) -> tuple[list[str], list[dict]]:
    """Löst den Sitemap-Baum ab den Wurzeln vollständig auf: Kind-Sitemaps
    rekursiv, URLs aus den Blättern.

    Läuft vor der Seitenschleife und braucht deshalb eigene Fehlerbehandlung
    (Übergabe Task 5 -> Task 6, Punkt 1): `sitemap_children`/`sitemap_urls`
    werfen bei kaputtem XML, aber ein einziges ungültiges Kind (etwa eine
    404-Seite mit XML-Content-Type) darf nur diesen Ast abbrechen, nie den
    ganzen Baum. Jeder Fehler landet als `{"sitemap", "reason"}` in der
    zweiten Rückgabe, die erste bleibt die vollständige URL-Liste der
    restlichen, funktionierenden Äste. Die Rückgabe ist über alle Sitemaps
    hinweg dedupliziert, Reihenfolge des ersten Vorkommens bleibt erhalten.
    """
    seen_sitemaps: set[str] = set()
    depth = {w: 0 for w in roots}
    queue: deque[str] = deque(roots)
    raw_urls: list[str] = []
    errors: list[dict] = []

    while queue:
        sm_url = queue.popleft()
        if sm_url in seen_sitemaps:
            continue
        seen_sitemaps.add(sm_url)
        current_depth = depth.get(sm_url, 0)
        try:
            response = fetch(sm_url)
            if response["status"] != 200:
                raise RuntimeError(f"HTTP {response['status']}")
            body = response["body"]
            if _is_gzip(body, response.get("headers", {}), sm_url):
                body = gzip.decompress(body)
            children = sitemap_children(body)
            if children:
                if current_depth >= max_depth:
                    errors.append({"sitemap": sm_url,
                                   "reason": f"maximale Verschachtelungstiefe ({max_depth}) erreicht"})
                    continue
                for child in children:
                    if child not in seen_sitemaps:
                        depth[child] = current_depth + 1
                        queue.append(child)
            else:
                raw_urls.extend(sitemap_urls(body))
        except Exception as exc:
            errors.append({"sitemap": sm_url, "reason": error_reason(exc)})
            continue

    unique: list[str] = []
    seen: set[str] = set()
    for u in raw_urls:
        if u not in seen:
            seen.add(u)
            unique.append(u)
    return unique, errors


def normalize_sitemap_seeds(raw_urls: list[str], base: str) -> list[str]:
    """Normalisiert Sitemap-URLs, bevor sie in die Startmenge der Breitensuche
    gehen (Übergabe Task 5 -> Task 6, Punkt 2).

    `sitemap_urls` liefert den rohen `<loc>`-Text, HTML-Links sind dagegen
    schon über `normalize` gelaufen. Wer beides ungefiltert zusammenwirft,
    zählt dieselbe Seite zweimal, und Klicktiefe wie interne Verlinkung
    stimmen nicht mehr. Eine fremde Domain in der Sitemap (kommt vor, wenn
    ein Shop eine Sitemap eines anderen Shops verlinkt) liefert `None` und
    fällt heraus, wie überall sonst bei `normalize`.
    """
    result: list[str] = []
    seen: set[str] = set()
    for raw in raw_urls:
        target = normalize(raw, base)
        if target is not None and target not in seen:
            seen.add(target)
            result.append(target)
    return result


def third_party_script_hosts(pages: list[dict], base: str) -> list[str]:
    """Alle fremden Hosts, von denen der Shop Skripte lädt, über den ganzen
    Lauf dedupliziert und sortiert.

    Die Rolle je Seite hat `script_sources`: dort steht die rohe `src`, und
    zwei verschiedene Analytics-Loader auf derselben Seite sind genau daran zu
    sehen. Diese Liste hier beantwortet die andere Frage, und zwar in einem
    Blick statt über Hunderte Seiteneinträge: welche Fremdanbieter laufen in
    diesem Shop überhaupt. Daran hängen Preistest-Werkzeuge (Intelligems,
    Kameleoon, Dynamic Yield, VWO, Optimizely), Bewertungs-Apps und
    Consent-Banner.

    Host statt voller URL, weil der Befund am Anbieter hängt, nicht an der
    Datei: ein Werkzeug lädt gern ein Dutzend URLs von demselben Host.
    """
    hosts: set[str] = set()
    for page in pages:
        for src in page.get("script_sources") or []:
            host = script_host(src, base)
            if host:
                hosts.add(host)
    return sorted(hosts)


FINDINGS_CAP = 25


def _path_prefix(url: str) -> str:
    """Erstes Pfadsegment als grober Seitentyp: `/products/`, `/collections/`,
    für die Startseite `/`."""
    path = urlparse(url).path
    segments = [seg for seg in path.split("/") if seg]
    return f"/{segments[0]}/" if segments else "/"


def _count_inline_tag_ids(pages: list[dict]) -> dict:
    """Je inline gefundener Container-ID die Zahl der Seiten, absteigend.

    Absichtlich eine reine Auszählung ohne URL-Liste: die Frage lautet, ob
    zwei Zähler derselben Art nebeneinander laufen, und dafür zählt die
    Verbreitung, nicht welche Seite genau betroffen ist.
    """
    counts: dict[str, int] = {}
    for page in pages:
        for tag_id in page.get("inline_tag_ids") or []:
            counts[tag_id] = counts.get(tag_id, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))


def _count_script_hosts(pages: list[dict]) -> dict:
    """Je Host eines eingebundenen Fremdskripts die Zahl der Seiten, absteigend.

    Gezählt werden Seiten, nicht Einbindungen: zwei Snippets desselben
    Anbieters auf einer Seite sind eine Seite. Die Frage lautet, wie weit ein
    Anbieter im Shop verbreitet ist, nicht wie oft er pro Seite auftaucht.

    Relative Pfade fallen raus, die gehören zum Theme und sagen nichts über
    Fremdtechnik. Interessant ist, wer von außen mitliest.

    Ohne diese Tabelle muss jeder Leser `pages[]` durchgehen, und das sind bei
    300 Seiten 2,7 MB.
    """
    counts: dict[str, int] = {}
    for page in pages:
        hosts = set()
        for source in page.get("script_sources") or []:
            host = urlparse(str(source or "")).netloc
            if host:
                hosts.add(host)
        for host in hosts:
            counts[host] = counts.get(host, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))


#: Ab dieser Länge schneidet Google einen Title in der Ergebnisliste meist ab.
#: Eine Faustregel in Zeichen, Google misst in Pixeln; deshalb steht der Wert
#: mit im Snapshot, und das Kriterium tec.title-length ordnet fest als
#: "gering" ein.
TITLE_MAX_CHARS = 60

#: Shopify-Produktadresse im Kontext einer Collection. Kanonisch ist die
#: Adresse ohne Collection-Präfix, Themes verlinken Produktkarten trotzdem oft
#: auf diese Form.
COLLECTION_PRODUCT_PATH = re.compile(r"/collections/[^/]+/products/")

#: Seitenmarker paginierter Listen: `?page=2` (Shopify) oder `/page/2`.
PAGINATION_MARK = re.compile(r"(?:[?&]page=\d+|/page/\d+)")

#: Felder der Produktauszeichnung, deren Fehlen der Index je Feld zählt.
PRODUCT_MARKUP_FLAGS = ("has_name", "has_image", "has_brand", "has_identifier",
                        "has_offers", "has_shipping_details", "has_return_policy")
PRODUCT_MARKUP_VALUES = ("price", "currency", "availability")


def _url_key(url: str | None) -> str | None:
    """Vergleichsform einer Adresse: Schema und Host klein, leerer Pfad als
    "/", ohne Fragment.

    Google behandelt die Startseite mit und ohne Schrägstrich gleich. Ohne
    diese Angleichung stünde jede Startseite, deren hreflang auf
    `https://shop.de` statt `https://shop.de/` zeigt, als "ohne
    Selbstreferenz" im Index, ein Falschbefund auf jeder Sprachversion.
    """
    if not url:
        return None
    parts = urlparse(url)
    return urlunparse((parts.scheme.lower(), parts.netloc.lower(),
                       parts.path or "/", "", parts.query, ""))


def _self_canonical(p: dict, target) -> bool:
    """Kein Canonical oder eines auf die Seite selbst (vor oder nach einer
    Weiterleitung), in der Vergleichsform von `_url_key`."""
    canonical = _url_key(p.get("canonical"))
    return canonical is None or canonical in {_url_key(p.get("url")), _url_key(target(p))}


def _depth_key(url: str) -> str:
    """Vergleichsform einer Adresse im Linkgraphen: `_url_key` plus
    Prozent-Kodierung in Großbuchstaben.

    Shopify schreibt das Canonical eines Handles mit Sonderzeichen klein
    kodiert (`%c2%ae` für ®), die Links im Theme groß (`%C2%AE`). Ohne die
    Angleichung fände ein Canonical seine Zielseite nicht, belegt am
    02.10.2026 an 15 von 516 Produktadressen im Collection-Kontext eines
    echten Shops.
    """
    return _percent_uppercase(_url_key(url))


def _canonical_elsewhere(p: dict) -> str | None:
    """Vergleichsform der Adresse, auf die die Seite kanonisiert, sofern das
    eine andere Adresse im Shop ist; sonst `None`.

    Andere Adresse heißt: weder die aufgerufene URL noch `end_url`. Ein
    Canonical auf die Endadresse einer Weiterleitung gilt als Selbstverweis,
    wie in `_self_canonical`. Ein fremder Host liefert `None`, weil keine
    erfasste Seite dessen Inhalt trägt.
    """
    base = p.get("end_url") or p.get("url")
    if not p.get("canonical") or not base:
        return None
    target = normalize(p["canonical"], base)
    if target is None:
        return None
    key = _depth_key(target)
    own = {_depth_key(url) for url in (p.get("url"), base) if url}
    return None if key in own else key


def _shortest_depths(pages: list[dict], home: str, via_canonical: bool) -> dict[str, int]:
    """Kürzeste Klickzahl je Adresse ab der Startseite, als `_depth_key`.

    Jeder interne Link kostet einen Klick. Mit `via_canonical` kommt je Seite
    eine Kante ohne Klick zu ihrem Canonical-Ziel dazu (`_canonical_elsewhere`):
    wer die Seite erreicht, hat dessen Inhalt vor sich. Das ist eine
    Breitensuche mit Kanten der Länge null und eins; eine Kante der Länge null
    stellt ihr Ziel vorn in die Warteschlange, damit die Reihenfolge nach
    Tiefe sortiert bleibt.

    Gezählt wird nur über erfasste Seiten. Steht dieselbe Adresse mehrfach in
    `pages` (in der Vergleichsform), tragen alle Einträge zusammen ihre Kanten
    bei: ein gedrosselter Eintrag ohne Links verdeckt so nicht den
    abgerufenen.
    """
    links: dict[str, list[str]] = {}
    canonical_of: dict[str, str] = {}
    for p in pages:
        key = _depth_key(p["url"])
        links.setdefault(key, []).extend(p.get("internal_links") or [])
        target = _canonical_elsewhere(p) if via_canonical else None
        if target is not None:
            canonical_of[key] = target

    start = _depth_key(home)
    if start not in links:
        return {}
    depths = {start: 0}
    queue: deque[str] = deque([start])
    done: set[str] = set()
    while queue:
        key = queue.popleft()
        if key in done:
            continue
        done.add(key)
        depth = depths[key]
        target = canonical_of.get(key)
        if target in links and depths.get(target, depth + 1) > depth:
            depths[target] = depth
            queue.appendleft(target)
        for link in links[key]:
            target = _depth_key(link)
            if target in links and target not in depths:
                depths[target] = depth + 1
                queue.append(target)
    return depths


def assign_click_depths(pages: list[dict], home: str) -> None:
    """Setzt je Seite `link_depth` und `click_depth`.

    `link_depth` ist die reine Linktiefe: die kürzeste Zahl interner Links ab
    der Startseite. `click_depth` ist die Tiefe des Inhalts: zusätzlich
    reicht eine Seite ihre Tiefe an die Adresse weiter, auf die sie
    kanonisiert. `click_depth` ist damit nie größer als `link_depth`. Keine
    Tiefe heißt `None`, auf keinem Weg von der Startseite erreicht.

    Der Anlass, belegt am 02.10.2026 an einem echten Shopify-Shop: die
    Produktkarten einer Kategorie verlinken `/collections/<c>/products/<h>`.
    Das ist schon die Produktseite, ihr Canonical ist `/products/<h>`. Die
    reine Linktiefe gab dieser kanonischen Adresse erst über den Link von
    dort eine Ebene mehr, und so stand der Inhalt einen Klick tiefer, als
    eine Kundin klicken muss: 262 von 512 Produkten auf Tiefe 4 oder tiefer,
    über das Canonical 75.

    Die Regel gilt für jedes Canonical, nicht nur für dieses Muster: eine
    Seite zeigt den Inhalt ihres Canonical-Ziels, egal wie die Adresse
    gebaut ist (Varianten, Kategoriepfade anderer Shopsysteme). Ein falsch
    gesetztes Canonical kann eine Tiefe dabei nur senken, nie heben; es
    steht ohnehin unter `canonical_mismatch`. Eine Weiterleitung zählt hier
    nicht mit. Eine nicht abgerufene Seite (429, Bot-Challenge) trägt kein
    Canonical und reicht deshalb nichts weiter.

    Beide Werte entstehen aus demselben erfassten Graphen (`internal_links`
    und `canonical` je Seite), nicht während der Breitensuche: so hängt keine
    Tiefe davon ab, in welcher Reihenfolge der Crawl die Seiten abgerufen hat.
    """
    links = _shortest_depths(pages, home, via_canonical=False)
    contents = _shortest_depths(pages, home, via_canonical=True)
    for p in pages:
        key = _depth_key(p["url"])
        p["link_depth"] = links.get(key)
        p["click_depth"] = contents.get(key)


def _content_depth_pages(pages: list[dict]) -> list[dict]:
    """Seiten mit Klicktiefe, deren Inhalt keine andere erfasste Adresse trägt.

    Eine Seite, deren Canonical-Ziel selbst im Crawl steht, fällt heraus:
    ihr Inhalt steht dort mit höchstens derselben Tiefe (siehe
    `assign_click_depths`). Zählte sie mit, stünde jedes Produkt in
    `deepest` zweimal, einmal als `/collections/<c>/products/<h>` und einmal
    als `/products/<h>`.
    """
    crawled = {_depth_key(p["url"]) for p in pages if p.get("url")}
    return [p for p in pages if p.get("click_depth") is not None
            and _canonical_elsewhere(p) not in crawled]


def _examples(pages: list[dict], cap: int) -> dict:
    return {"count": len(pages), "examples": [p["url"] for p in pages[:cap]]}


def _duplicate_groups(pages: list[dict], field: str, cap: int) -> dict:
    """Gruppen gleicher Texte in `field`, mit Gruppengröße und drei Beispielen.

    `pages` sind die Seiten, über die gezählt wird. Wer hier alle erfassten
    Seiten übergibt statt der kanonischen, zählt jede Produktadresse im
    Collection-Kontext als eigene Dublette: an einem echten Shopify-Shop
    ergab das mehr als zwölfmal so viele Seiten mit doppelter Meta-Description
    wie über die kanonischen Seiten.
    """
    by_text: dict[str, list[str]] = {}
    for p in pages:
        text = (p.get(field) or "").strip()
        if text:
            by_text.setdefault(text, []).append(p["url"])
    groups = [{"text": text[:120], "count": len(urls), "examples": urls[:3]}
              for text, urls in by_text.items() if len(urls) > 1]
    groups.sort(key=lambda g: (-g["count"], g["text"]))
    return {"count": len(groups), "pages": sum(g["count"] for g in groups),
            "groups": groups[:cap]}


def _hreflang_index(pages: list[dict], ok: list[dict], target, cap: int) -> dict:
    """Sprach- und Ländervarianten: Selbstreferenz, x-default, Erreichbarkeit
    der Ziele, Gegenseitigkeit.

    "Ziel nicht erreicht" heißt: die Adresse kam bis zur Crawl-Grenze weder
    über interne Links noch über die Sitemap vor. Ist der Crawl an
    `--max-urls` gestoßen, kann das auch an der Grenze liegen; das muss die
    Analyse gegen `summary.url_count` halten, bevor sie einen Befund daraus
    macht.
    """
    by_key: dict[str, dict] = {}
    for p in pages:
        for url in (p.get("url"), p.get("end_url")):
            key = _url_key(url)
            if key and key not in by_key:
                by_key[key] = p

    def own(p: dict) -> set:
        return {k for k in (_url_key(p.get("url")), _url_key(target(p)),
                            _url_key(p.get("canonical"))) if k}

    with_tags = [p for p in ok if p.get("hreflang")]
    languages = Counter(code for p in with_tags for code in p["hreflang"])
    missing_x_default = [p for p in with_tags
                         if "x-default" not in {c.lower() for c in p["hreflang"]}]
    missing_self = [p for p in with_tags
                    if not own(p) & {_url_key(t) for t in p["hreflang"].values()}]

    not_crawled: dict[str, str] = {}
    not_indexable: dict[str, dict] = {}
    not_reciprocal: dict[tuple, dict] = {}
    for p in with_tags:
        mine = own(p)
        for code, href in p["hreflang"].items():
            key = _url_key(href)
            if not key or key in mine:
                continue
            other = by_key.get(key)
            if other is None:
                not_crawled.setdefault(key, href)
                continue
            status = other.get("status")
            if (status is None or status >= 400 or not other.get("indexable")
                    or not _self_canonical(other, target)):
                not_indexable.setdefault(key, {"url": href, "status": status})
                continue
            back = {_url_key(t) for t in (other.get("hreflang") or {}).values()}
            if other.get("hreflang") and not mine & back:
                not_reciprocal.setdefault((_url_key(p["url"]), key),
                                          {"url": p["url"], "target": href})

    return {
        "pages_with_hreflang": len(with_tags),
        "languages": dict(sorted(languages.items())),
        "missing_x_default": _examples(missing_x_default, cap),
        "missing_self_reference": _examples(missing_self, cap),
        "targets_not_crawled": {"count": len(not_crawled),
                                "examples": list(not_crawled.values())[:cap]},
        "targets_not_indexable": {"count": len(not_indexable),
                                  "examples": list(not_indexable.values())[:cap]},
        "not_reciprocal": {"count": len(not_reciprocal),
                           "examples": list(not_reciprocal.values())[:cap]},
    }


def _product_markup_index(canonical: list[dict], cap: int) -> dict:
    """Vollständigkeit der Produktauszeichnung je Feld, über kanonische Seiten.

    Drei Beispiele je Feld reichen als Beleg; bei sieben Feldern plus drei
    Werten wäre der Index mit `cap` Beispielen je Feld sonst zur Hälfte eine
    URL-Liste.
    """
    with_product = [p for p in canonical if (p.get("markup") or {}).get("product")]
    missing = {}
    for flag in PRODUCT_MARKUP_FLAGS:
        lacking = [p for p in with_product if not p["markup"]["product"].get(flag)]
        missing[flag] = {"count": len(lacking), "examples": [p["url"] for p in lacking[:3]]}
    for value in PRODUCT_MARKUP_VALUES:
        lacking = [p for p in with_product if p["markup"]["product"].get(value) is None]
        missing[value] = {"count": len(lacking), "examples": [p["url"] for p in lacking[:3]]}
    multiple = [p for p in with_product if p["markup"]["product"].get("count", 1) > 1]
    availability = Counter(p["markup"]["product"].get("availability") or "none"
                           for p in with_product)
    return {
        "pages": len(with_product),
        "missing": missing,
        "multiple_nodes": _examples(multiple, cap),
        "availability": dict(sorted(availability.items())),
    }


def _organization_markup_index(ok: list[dict]) -> dict:
    with_org = [p for p in ok if (p.get("markup") or {}).get("organization")]
    home = next((p for p in ok if p.get("click_depth") == 0), None)
    return {
        "pages": len(with_org),
        "home_url": home["url"] if home else None,
        "home": (home.get("markup") or {}).get("organization") if home else None,
        "with_return_policy": sum(1 for p in with_org
                                  if p["markup"]["organization"].get("has_return_policy")),
        "with_shipping_service": sum(1 for p in with_org
                                     if p["markup"]["organization"].get("has_shipping_service")),
    }


def build_findings_index(pages: list[dict], cap: int = FINDINGS_CAP) -> dict:
    """Befundklassen als Anzahl plus begrenzte Beispielliste.

    `crawl.json > pages` ist bei einem größeren Shop nicht mehr lesbar: rund
    6,8 KB und 1750 Token je Seite, ein Shop mit 2000 Seiten ergibt 13 MB. Der
    Analyse-Agent kann die Liste damit nicht durchgehen und würde auf einem
    abgeschnittenen Ausschnitt arbeiten, ohne es zu merken. Dieser Index trägt
    deshalb je Klasse die **vollständige** Anzahl und höchstens `cap` Beispiele
    als Beleg. `cap` steht mit in der Datei, damit die Kürzung sichtbar ist.

    Für alles darüber hinaus fragt der Agent `crawl.json` gezielt mit `jq` ab,
    statt sie zu lesen.
    """
    # Nur Seiten, die parse_page durchlaufen haben, tragen Inhaltsfelder;
    # gleiche Abgrenzung wie in build_summary über das Feld `indexable`.
    ok = [p for p in pages if "indexable" in p]

    def target(p):
        """Die Adresse, gegen die ein Canonical zu halten ist: nach einer
        Weiterleitung ist das end_url, sonst die aufgerufene URL."""
        return p.get("end_url") or p.get("url")

    orphans = [p["url"] for p in ok if p.get("click_depth") is None]

    errors, by_status = [], {}
    for p in pages:
        status = p.get("status")
        if status is not None and status < 400:
            continue
        key = str(status) if status is not None else "error"
        by_status[key] = by_status.get(key, 0) + 1
        errors.append({"url": p.get("url"), "status": status})

    multiple = [{"url": p["url"], "canonical_count": p.get("canonical_count")}
                for p in ok if (p.get("canonical_count") or 0) > 1]
    mismatch = [{"url": p["url"], "canonical": p["canonical"]}
                for p in ok if p.get("canonical") and p["canonical"] != target(p)]

    by_title: dict[str, list] = {}
    for p in ok:
        title = (p.get("title") or "").strip()
        if title:
            by_title.setdefault(title, []).append(p["url"])
    # Drei Beispiele je Gruppe reichen als Beleg, die Gruppengröße steht
    # daneben. Bei 25 Gruppen mit je 25 URLs wäre der Index sonst zur
    # Hälfte eine URL-Liste.
    groups = [{"title": t, "count": len(urls), "examples": urls[:3]}
              for t, urls in by_title.items() if len(urls) > 1]
    groups.sort(key=lambda g: (-g["count"], g["title"]))

    # Tiefe des Inhalts: eine Adresse, deren Canonical-Ziel im Crawl steht,
    # zählt dort und nicht hier (`_content_depth_pages`).
    linked = _content_depth_pages(ok)
    linked.sort(key=lambda p: p["click_depth"], reverse=True)

    def is_paginated(p):
        """Folgeseite einer Liste (`?page=2`, `/page/2`)."""
        return bool(PAGINATION_MARK.search(p.get("url") or ""))

    # Folgeseiten tragen eine Query, sind aber keine Parameter-Variante: sie
    # kanonisieren richtigerweise auf sich selbst und stehen unter
    # `pagination`. Zählten sie hier mit, wäre jede korrekt ausgezeichnete
    # Folgeseite ein Befund "ohne konsolidierendes Canonical".
    parameters = [p for p in ok if "?" in (p.get("url") or "") and not is_paginated(p)]
    indexable_parameters = [p for p in parameters if p.get("indexable")]
    unconsolidated = [p for p in indexable_parameters
                      if not p.get("canonical") or p["canonical"] == target(p)]

    schema_types: dict[str, int] = {}
    for p in ok:
        for kind in p.get("schema_types") or []:
            schema_types[kind] = schema_types.get(kind, 0) + 1
    without_schema = [p["url"] for p in ok if not p.get("schema_types")]

    prefixes: dict[str, int] = {}
    for p in ok:
        key = _path_prefix(p["url"])
        prefixes[key] = prefixes.get(key, 0) + 1

    # Grundgesamtheit der Inhaltskriterien (H1, Title, Description,
    # Produktauszeichnung): indexierbare Seiten, die auf sich selbst
    # kanonisieren. Eine Produktadresse im Collection-Kontext teilt Title,
    # Description und H1 mit ihrer kanonischen Seite; zählte sie mit, stünde
    # derselbe Mangel mehrfach im Befund. Dasselbe gilt für die Folgeseiten
    # einer Liste: `?page=2` bis `?page=24` tragen dieselbe H1 und meist
    # dieselbe Description wie Seite 1, und eine fehlende Description der
    # Kategorie stünde sonst 24-mal im Befund. Folgeseiten bewertet
    # `pagination`.
    # Zwei erfasste Adressen, die in der Vergleichsform dieselbe sind (die
    # Startseite mit und ohne Schrägstrich), zählen einmal.
    canonical, seen = [], set()
    for p in ok:
        key = _url_key(target(p))
        if (p.get("indexable") and _self_canonical(p, target) and not is_paginated(p)
                and key not in seen):
            seen.add(key)
            canonical.append(p)

    linked_elsewhere = [p for p in ok if p.get("click_depth") is not None
                        and not _self_canonical(p, target)]
    collection_products = [p for p in linked_elsewhere
                           if COLLECTION_PRODUCT_PATH.search(p["url"])]

    paginated = [p for p in ok if is_paginated(p)]
    to_first_page = [p for p in paginated
                     if p.get("canonical") and not PAGINATION_MARK.search(p["canonical"])]

    criteria_blocks = {
        # Ab hier die Blöcke der Kriterienliste vom 27.09.2026 (Agents
        # audit-seo-technical und audit-geo). Jede Zählregel steht hier im
        # Code statt in einer jq-Abfrage des Agents: zwei Läufe desselben
        # Moduls auf demselben Snapshot sollen dieselbe Zahl liefern.
        "canonical_pages": len(canonical),
        "h1": {
            "multiple": _examples([p for p in canonical if len(p.get("h1") or []) > 1], cap),
            "missing": _examples([p for p in canonical if not p.get("h1")], cap),
        },
        "titles": {
            "missing": _examples([p for p in canonical if not (p.get("title") or "").strip()], cap),
            "too_long": {**_examples([p for p in canonical
                                      if len((p.get("title") or "").strip()) > TITLE_MAX_CHARS], cap),
                         "max_chars": TITLE_MAX_CHARS},
            "duplicate_groups": _duplicate_groups(canonical, "title", cap),
        },
        "descriptions": {
            "missing": _examples([p for p in canonical
                                  if not (p.get("description") or "").strip()], cap),
            "duplicate_groups": _duplicate_groups(canonical, "description", cap),
        },
        "non_canonical_linked": {
            **_examples(linked_elsewhere, cap),
            "share_of_crawl": round(len(linked_elsewhere) / len(ok), 4) if ok else None,
            "collection_product_urls": len(collection_products),
        },
        "pagination": {
            **_examples(paginated, cap),
            "indexable": sum(1 for p in paginated if p.get("indexable")),
            "canonical_to_first_page": _examples(to_first_page, cap),
        },
        "hreflang": _hreflang_index(pages, ok, target, cap),
        "product_markup": _product_markup_index(canonical, cap),
        "organization_markup": _organization_markup_index(ok),
    }

    return {
        "cap": cap,
        # Inline eingebaute Container- und Mess-IDs, je ID die Zahl der Seiten.
        # Zwei GA4-IDs auf denselben Seiten heissen doppelte Messung, und ohne
        # diese Zeile ist das aus dem Crawl grundsätzlich nicht sichtbar.
        "inline_tag_ids": _count_inline_tag_ids(ok),
        # Fremdtechnik als Host-Tabelle: welcher Anbieter auf wie vielen
        # Seiten eingebunden ist. pull-shopify-tech liest sie, und die
        # technische Analyse spart sich die eigene Auszählung.
        "script_hosts": _count_script_hosts(ok),
        "orphans": {"count": len(orphans), "examples": orphans[:cap]},
        "errors": {"count": len(errors), "by_status": by_status,
                   "examples": errors[:cap]},
        "multiple_canonicals": {"count": len(multiple), "examples": multiple[:cap]},
        "canonical_mismatch": {"count": len(mismatch), "examples": mismatch[:cap]},
        "duplicate_titles": {"count": len(groups), "groups": groups[:cap]},
        "deepest": [{"url": p["url"], "click_depth": p["click_depth"]}
                    for p in linked[:cap]],
        "parameter_urls": {
            "count": len(parameters),
            "indexable": len(indexable_parameters),
            "without_consolidating_canonical": len(unconsolidated),
            "examples": [p["url"] for p in unconsolidated[:cap]],
        },
        "schema_types": schema_types,
        "pages_without_schema": {"count": len(without_schema),
                                  "examples": without_schema[:cap]},
        "path_prefixes": prefixes,
        **criteria_blocks,
    }


def build_summary(pages: list[dict], blocked_links: int = 0, base: str = "",
                  robots_group: str | None = None,
                  home_blocked_by_robots: bool = False) -> dict:
    """Aggregiert die Kennzahlen aus der Seitenliste zu `summary`.

    `successful` sind die Seiten, die `parse_page` durchlaufen haben
    (erkennbar am Feld `indexable`, das nur dort gesetzt wird): nur für die
    ergeben Anteil ohne Description, H1-Zählung und Bilder-Befund einen Sinn.
    Ein 404 oder ein Netzwerkfehler zählt in der Statuscode-Verteilung mit,
    aber nicht in diesen Anteilen, sonst würde eine tote Seite fälschlich
    als "ohne Description" auftauchen, obwohl sie gar keine Seite ist.

    `blocked_links` kommt von außen (aus `crawl`), weil eine von Disallow
    gesperrte URL nie abgerufen wird und deshalb gar nicht erst in `pages`
    auftaucht: sie hier mitzuzählen wäre falsch, sie fehlt hier komplett zum
    Zählen. Wie oft der Shop dennoch in gesperrten Raum verlinkt, ist selbst
    ein Befund, kein stilles Wegfiltern.

    `robots_group` und `home_blocked_by_robots` kommen ebenfalls von außen
    (aus `build_snapshot`). Das erste sagt, welche robots.txt-Gruppe der
    Crawl befolgt hat. Das zweite erklärt einen leeren Snapshot: ohne das
    Feld sähe eine Absage des Shops an diesen Crawler aus wie ein kaputter
    Lauf oder ein Shop ohne Seiten.
    """
    status_code_distribution: dict[str, int] = {}
    for s in pages:
        code = s.get("status")
        key = str(code) if code is not None else "error"
        status_code_distribution[key] = status_code_distribution.get(key, 0) + 1

    successful = [s for s in pages if "indexable" in s]
    n = len(successful)
    not_indexable = sum(1 for s in successful if not s["indexable"])
    without_description = sum(1 for s in successful if not s.get("description"))
    pages_with_multiple_h1 = sum(1 for s in successful if len(s.get("h1") or []) > 1)
    images_without_alt = sum(s.get("images", {}).get("without_alt", 0) for s in successful)
    longest_redirect_chain = max(
        (len(s.get("redirects") or []) for s in pages), default=0
    )
    depths = [s["click_depth"] for s in _content_depth_pages(pages)]

    return {
        "url_count": len(pages),
        "status_code_distribution": status_code_distribution,
        "share_not_indexable": round(not_indexable / n, 4) if n else None,
        "share_without_description": round(without_description / n, 4) if n else None,
        "pages_with_multiple_h1": pages_with_multiple_h1,
        "images_without_alt": images_without_alt,
        "longest_redirect_chain": longest_redirect_chain,
        "max_click_depth": max(depths, default=None),
        "blocked_links": blocked_links,
        "robots_group": robots_group,
        "home_blocked_by_robots": home_blocked_by_robots,
        "third_party_script_hosts": third_party_script_hosts(pages, base),
        "throttled_pages": sum(1 for p in pages if p.get("throttled")),
        "bot_challenge_pages": sum(1 for p in pages if p.get("bot_challenge")),
        "self_check": self_check(pages),
    }


#: Werte, die als Seitentitel praktisch immer ein Parser-Fehler sind statt
#: eines echten Shop-Problems: Zahlungsarten-Icons, die Shopify-Themes als
#: Inline-SVG in den Fuss rendern. SVG hat ein eigenes <title>-Element.
VERDAECHTIGE_TITEL = {"visa", "mastercard", "paypal", "american express",
                      "maestro", "klarna", "apple pay", "google pay",
                      "shop pay", "sofort", "amazon", "discover", "jcb",
                      "union pay", "diners club", "eps", "ideal", "bancontact"}


def self_check(pages: list[dict]) -> list[str]:
    """Auffaelligkeiten, die eher auf uns zeigen als auf den Shop.

    Der Anlass ist real und teuer: am 07.09.2026 trug in einem Lauf jede der
    gut tausend abgerufenen Seiten den Titel "Visa". Das war kein Shop-Problem,
    sondern unser Parser, der bis zum letzten <title> im Dokument
    weiterschrieb und dabei die Zahlungs-Icons im Seitenfuss mitnahm. Der
    Fehler ist behoben, aber ein Snapshot aus der Zeit davor sieht genauso aus
    wie ein echter Befund, und er ist als Schlagzeile in einen Kundenreport
    gewandert.

    **Deshalb prueft der Crawler sein eigenes Ergebnis.** Was hier steht, ist
    keine Aussage ueber den Shop: es ist eine Bitte, hinzusehen, bevor daraus
    ein Befund wird.
    """
    hinweise = []
    title = [p.get("title") for p in pages if p.get("status") == 200
             and p.get("title")]
    if len(title) >= 20:
        haeufigster, count = Counter(title).most_common(1)[0]
        share = count / len(title)
        if share > 0.9:
            reason = ("Der Wert ist ein Zahlungsarten-Icon aus dem Seitenfuss, "
                     "also fast sicher ein Fehler beim Auslesen."
                     if haeufigster.strip().lower() in VERDAECHTIGE_TITEL else
                     "Vor jedem Befund daraus die Seite im Browser gegenpruefen.")
            hinweise.append(
                f"{count} von {len(title)} Seiten tragen denselben Titel "
                f"{haeufigster!r}. {reason}")
    return hinweise


#: Obergrenze der Drosselpause, in Sekunden, **unabhaengig von `--delay`**.
#:
#: Vorher hiess sie `max(delay * 16, 2.0)`, und das war ein stiller Multiplikator:
#: bei `--delay 0.6` ergab sie 9,6 Sekunden, und mit drei Wiederholungen je Seite
#: kostete eine gedrosselte Seite bis zu 29 Sekunden. Ein Lauf ueber 3.000 URLs
#: haette 24 Stunden gebraucht. Am 08.09.2026 lief genau der drei Stunden lang,
#: ohne eine einzige Zeile Ausgabe, und niemand konnte unterscheiden, ob er
#: arbeitet oder haengt.
PAUSE_MAX = 5.0

#: Wie oft eine mit 429 abgewiesene Seite **im Hauptdurchgang** erneut geholt
#: wird. Genau einmal: eine kurze Delle faengt das ab, und bei anhaltender
#: Drosselung darf der Hauptdurchgang nicht je Seite mehrfach warten. Was auch
#: dann nicht antwortet, geht in den Nachlauf.
RETRY_429 = 1

#: Wie oft der Nachlauf die geparkten URLs versucht, mit der hoechsten Pause.
NACHLAUF_RUNDEN = 2

#: Wie viele Sekunden hoechstens zwischen zwei Fortschrittszeilen liegen. Ein
#: Crawl ohne Lebenszeichen ist von einem haengenden nicht zu unterscheiden.
#:
#: **Die Sekunde ist das Mass, nicht die Seite.** Die erste Fassung dieser
#: Ausgabe schrieb alle 50 Seiten eine Zeile. Bei den gemessenen 1,5 Sekunden je
#: Seite auf einem echten Shop sind das 75 Sekunden Stille am Anfang, und genau
#: in diese Stille faellt jedes Zeitlimit, mit dem ein Aufrufer den Lauf
#: beobachtet: am 08.09.2026 wurde ein gesunder Testlauf zweimal fuer haengend
#: gehalten und abgebrochen, bevor die erste Zeile faellig war. Eine Seite
#: dauert je nach Shop zwischen 0,2 und 15 Sekunden, eine Sekunde dauert immer
#: gleich lang.
FORTSCHRITT_SEKUNDEN = 20.0


def crawl(home: str, normalized_sitemap_urls: list[str], fetch,
          max_urls: int, delay: float,
          disallow_rules: list[str] = (), blocked_target: set[str] | None = None) -> list[dict]:
    """Führt die Breitensuche aus: ab der Startseite über interne Links, dazu
    die komplette Sitemap-Menge als zusätzlich zu besuchende Seiten.

    Die Klicktiefe kommt ausschließlich aus der Verlinkung ab der Startseite,
    nie aus der Position in der Sitemap. Gesetzt wird sie erst nach dem
    Abruf, aus dem erfassten Graphen (`assign_click_depths`): `link_depth`
    über Links allein, `click_depth` zusätzlich über Canonicals. Eine Seite,
    die auf keinem Weg von der Startseite erreicht wird, bekommt
    `click_depth: None`, selbst ein Befund: eine verwaiste, aber indexierte
    Seite.

    Die Link-Warteschlange (`queue`) wird trotzdem vollständig geleert, bevor
    je eine reine Sitemap-URL (`sitemap_rest`) an die Reihe kommt: reicht
    `max_urls` nicht für alles, stehen so die verlinkten Seiten im Snapshot,
    nicht die nur aus der Sitemap bekannten.

    `max_urls` ist eine harte Obergrenze über alle besuchten URLs, `delay`
    die Pause zwischen zwei Abrufen (nicht vor dem allerersten).

    `disallow_rules` sind die Disallow-Zeilen der robots.txt-Gruppe, die für
    diesen Crawler gilt: die eigene `ptai-audit`, sonst `*` (siehe
    `select_robots_group`; leer per Default, dann ändert sich nichts an
    bestehenden Aufrufen). Eine neu entdeckte URL, deren Pfad darauf passt, wird nie in
    die Warteschlange aufgenommen und nie abgerufen, zählt aber als
    entdeckter Link: bei Beispielshop (siehe `robots_path_blocked`) sind die
    Filter- und Sortier-Permutationen praktisch unbegrenzt, ohne dieses
    Aussieben verbrennt der Lauf sein `max_urls`-Budget dort statt auf den
    echten Produktseiten. `blocked_target`, wenn übergeben, sammelt diese
    Adressen dedupliziert für die Zusammenfassung (`blocked_links`); die
    Startseite selbst ist der angeforderte Einstiegspunkt, keine entdeckte
    Verlinkung, und wird deshalb hier nie gegen `disallow_rules` geprüft.
    Ob die eigene Gruppe den ganzen Lauf untersagt, entscheidet vorher
    `build_snapshot` über `is_home_blocked`. Hier kommt die Startseite also
    nur an, wenn die eigene Gruppe sie erlaubt oder die Regeln aus `*`
    stammen.
    """
    visited: set[str] = set()
    planned: set[str] = {home}
    queue: deque[str] = deque([home])

    sitemap_rest: deque[str] = deque()
    for u in normalized_sitemap_urls:
        if u == home:
            continue
        if disallow_rules and robots_path_blocked(_robots_target(u), disallow_rules):
            planned.add(u)
            if blocked_target is not None:
                blocked_target.add(u)
            continue
        sitemap_rest.append(u)

    pages: list[dict] = []
    first_fetch = True

    # Drosselung: der Shop antwortet mit 429, wenn wir zu schnell sind. Am
    # 07.09.2026 kam bei --delay 0.2 rund ein Drittel der Antworten so zurück.
    # Der Crawl zählte sie nur mit und lief weiter, und der Snapshot sah aus
    # wie ein fertiger Crawl: jeder Anteil darin bezog sich in Wahrheit auf
    # zwei Drittel der Seiten, ohne dass das irgendwo stand. Wir schalten
    # deshalb zurück statt weiterzurasen, und die Zusammenfassung hält fest,
    # wie oft und wie weit.
    aktuelle_pause = delay
    gedrosselt = 0
    abgewiesen = 0
    pause_max = min(PAUSE_MAX, max(delay * 8, 1.0))
    geparkt: list[str] = []
    begonnen = time.monotonic()

    zuletzt_gemeldet = begonnen

    def fortschritt(nachlauf=False, immer=False):
        """Eine Zeile Lebenszeichen, hoechstens alle `FORTSCHRITT_SEKUNDEN`.

        Ohne sie ist ein langsamer Crawl von einem haengenden nicht zu
        unterscheiden, und genau das hat am 08.09.2026 drei Stunden gekostet.
        Die Funktion entscheidet selbst, ob die Zeile faellig ist; die
        Aufrufstellen rufen sie nach jeder Seite. `immer=True` erzwingt die
        Ausgabe, fuer die erste und die letzte Zeile eines Laufs.
        """
        nonlocal zuletzt_gemeldet
        jetzt = time.monotonic()
        if not immer and jetzt - zuletzt_gemeldet < FORTSCHRITT_SEKUNDEN:
            return
        zuletzt_gemeldet = jetzt
        dauer = max(1e-9, time.monotonic() - begonnen)
        tempo = len(pages) / dauer * 60
        offen = len(queue) + len(sitemap_rest)
        remainder = (f", noch {min(offen, max_urls - len(pages))} offen"
                if not nachlauf else "")
        eta = (f", fertig in rund {int(min(offen, max_urls - len(pages)) / tempo)} min"
               if tempo > 0 and offen and not nachlauf else "")
        challenge = f", {abgewiesen} als Bot abgewiesen" if abgewiesen else ""
        print(f"{'Nachlauf' if nachlauf else 'Crawl'}: {len(pages)} Seiten in "
              f"{int(dauer // 60)}:{int(dauer % 60):02d} ({tempo:.0f}/min), "
              f"Pause {aktuelle_pause:.1f}s, {gedrosselt} mal gedrosselt, "
              f"{len(geparkt)} geparkt{challenge}{remainder}{eta}",
              file=sys.stderr, flush=True)

    print(f"Crawl startet: {len(sitemap_rest) + 1} bekannte URLs, Budget "
          f"{max_urls} Seiten, Pause {delay:.1f}s. Meldung alle "
          f"{int(FORTSCHRITT_SEKUNDEN)}s.", file=sys.stderr, flush=True)

    while (queue or sitemap_rest) and len(visited) < max_urls:
        url = queue.popleft() if queue else sitemap_rest.popleft()
        if url in visited:
            continue
        visited.add(url)

        if not first_fetch:
            time.sleep(aktuelle_pause)
        first_fetch = False

        # **429 heisst "spaeter nochmal", nicht "gibt es nicht".** Bis zum
        # 08.09.2026 verbuchte der Crawl eine abgewiesene Antwort als
        # erledigte Seite und holte die URL nie wieder. Im ersten echten Lauf
        # fehlte dadurch rund ein Drittel aller Seiten im Snapshot.
        #
        # **Wiederholt wird hier trotzdem nur einmal.** Die erste Fassung
        # dieses Fixes versuchte es dreimal je Seite mit verdoppelter Pause,
        # und bei anhaltender Drosselung kostete das bis zu 29 Sekunden pro
        # Seite. Was auch beim zweiten Versuch nicht antwortet, wandert in den
        # Nachlauf: der Hauptdurchgang laeuft weiter, statt an einer Seite zu
        # haengen, die der Shop gerade nicht herausgibt.
        # **Eine Bot-Challenge wird nie wiederholt und bremst nie aus.**
        # Sie kommt in Millisekunden zurueck und haengt nicht am Tempo (siehe
        # `bot_challenge`). Wer darauf mit einer laengeren Pause antwortet,
        # wartet gegen eine Wand: genau das kostete am 08.09.2026 drei
        # Stunden. Die Seite wird als nicht abrufbar vermerkt, mit Grund, und
        # der Lauf geht sofort weiter.
        challenge = None
        for versuch in range(RETRY_429 + 1):
            entry = process_page(url, fetch)
            challenge = entry.get("bot_challenge")
            if challenge:
                abgewiesen += 1
                break
            if entry.get("status") != 429:
                if aktuelle_pause > delay:
                    aktuelle_pause = max(delay, aktuelle_pause * 0.8)
                break
            gedrosselt += 1
            aktuelle_pause = min(pause_max, max(aktuelle_pause * 2, 0.5))
            if versuch < RETRY_429:
                time.sleep(aktuelle_pause)
        else:
            geparkt.append(url)
            visited.discard(url)
            fortschritt()
            continue
        pages.append(entry)
        fortschritt()

        for link in entry.get("internal_links") or []:
            if link in visited or link in planned:
                continue
            if disallow_rules and robots_path_blocked(_robots_target(link), disallow_rules):
                planned.add(link)
                if blocked_target is not None:
                    blocked_target.add(link)
                continue
            planned.add(link)
            queue.append(link)

    # Nachlauf: die geparkten URLs, mit der hoechsten Pause und in Ruhe. Der
    # Hauptdurchgang ist durch, der Shop hatte also Zeit, sich zu erholen.
    for runde in range(NACHLAUF_RUNDEN):
        if not geparkt:
            break
        diesmal, geparkt = geparkt, []
        print(f"Nachlauf {runde + 1}: {len(diesmal)} gedrosselte Seiten, "
              f"Pause {pause_max:.1f}s", file=sys.stderr, flush=True)
        for url in diesmal:
            if len(pages) >= max_urls:
                geparkt.append(url)
                continue
            time.sleep(pause_max)
            entry = process_page(url, fetch)
            if entry.get("status") == 429:
                gedrosselt += 1
                geparkt.append(url)
                continue
            visited.add(url)
            pages.append(entry)
            fortschritt(nachlauf=True)

    for url in geparkt:
        pages.append({"url": url, "status": 429, "throttled": True})

    if abgewiesen:
        print(f"Warnung: {abgewiesen} Seiten wurden als Bot abgewiesen und "
              f"fehlen im Snapshot. Das ist keine Drosselung: ein höherer "
              f"--delay hilft nicht. Die IP-Adresse des Betreibers muss in "
              f"der WAF des Shops befristet freigegeben werden "
              f"(reference/access.md, Teil B, \"Eure Firewall\"), sonst bleibt "
              f"dieser Teil des Shops unmessbar.")
    if geparkt:
        print(f"Warnung: {len(geparkt)} Seiten blieben auch im Nachlauf "
              f"gedrosselt und fehlen im Snapshot. Jeder Anteil daraus bezieht "
              f"sich auf die übrigen Seiten. Für einen vollständigen Lauf "
              f"--delay höher setzen.")
    elif gedrosselt:
        print(f"Hinweis: {gedrosselt} Abrufe wurden mit HTTP 429 abgewiesen und "
              f"später erfolgreich nachgeholt.")
    fortschritt(immer=True)
    assign_click_depths(pages, home)
    return pages


def check(base: str, robots: dict, roots: list[str], fetch) -> int:
    """`--check`: nur robots.txt und die Sitemap-Wurzel(n) abrufen, melden,
    wie viele URLs zu erwarten sind. Exit-Code 0 bei Erfolg, 1 wenn keine
    einzige Sitemap-Wurzel erreichbar war, dann ist die Domain selbst
    vermutlich falsch oder nicht erreichbar.

    Exit-Code 1 auch dann, wenn die eigene robots.txt-Gruppe die Startseite
    sperrt (`is_home_blocked`). Die Sitemap wird dann nicht mehr abgerufen:
    eine Zahl erwarteter URLs wäre eine falsche Zusage, denn der Crawl ruft
    keine einzige davon ab. Genau dafür läuft `--check` vor Gate A.
    """
    group, rules = select_robots_group(robots.get("disallow_rules") or {})
    if is_home_blocked(_home_url(base), group, rules):
        print(f"Fehler: robots.txt sperrt den Crawler {ROBOTS_TOKEN} mit einer "
              f"eigenen Gruppe ab der Startseite. Ein Crawl ruft keine Seite ab.")
        return 1

    urls, errors = resolve_sitemap_tree(roots, fetch)
    source = "robots.txt" if robots.get("found") and robots.get("sitemaps") else "Fallback /sitemap.xml"

    if not urls and errors and len(errors) >= len(roots):
        reasons = "; ".join(f"{f['sitemap']}: {f['reason']}" for f in errors)
        print(f"Fehler: keine Sitemap erreichbar ({source}): {reasons}")
        return 1

    sitemap_list = ", ".join(roots)
    print(f"OK: {len(roots)} Sitemap(s) ({source}: {sitemap_list}), ca. {len(urls)} URLs erwartet")
    if errors:
        reasons = "; ".join(f"{f['sitemap']}: {f['reason']}" for f in errors)
        print(f"Warnung: {len(errors)} Sitemap(s) fehlgeschlagen: {reasons}")
    return 0


def _home_url(base: str) -> str:
    """Die Startseite als normalisierte Adresse.

    Explizit mit Schluss-Slash normalisiert: sonst können die Startseite (aus
    `base` ohne Pfad) und eine Sitemap- oder Link-Referenz auf "/" nach
    `normalize` zwei verschiedene Strings ergeben (dessen Wurzel-Regel
    behält den Slash), obwohl beide dieselbe Seite meinen.
    """
    return normalize(base + "/", base) or base


def build_snapshot(base: str, robots: dict, roots: list[str], fetch,
                   max_urls: int, delay: float) -> dict:
    """Der ganze Lauf nach robots.txt: Sitemap, Crawl, Zusammenfassung.

    Aus `main` herausgelöst, damit die Entscheidung, welche robots.txt-Gruppe
    gilt und ob der Crawl überhaupt starten darf, mit einem injizierten
    `fetch` testbar ist. Bis zum 23.09.2026 stand sie ungetestet in `main`
    und las dort nur die Gruppe `*`.

    Sperrt die eigene Gruppe die Startseite (`is_home_blocked`), ruft der
    Lauf nichts mehr ab, auch die Sitemap nicht: die Absage gilt für jeden
    Pfad des Shops, und robots.txt ist die einzige Datei, die ein Crawler
    immer lesen darf. Der Snapshot entsteht trotzdem und sagt in
    `summary.home_blocked_by_robots`, warum er leer ist.
    """
    home = _home_url(base)
    robots_group, disallow_rules = select_robots_group(robots.get("disallow_rules") or {})
    home_blocked = is_home_blocked(home, robots_group, disallow_rules)
    blocked_links: set[str] = set()

    if home_blocked:
        sitemap_errors: list[dict] = []
        pages: list[dict] = []
        print(f"Kein Crawl: robots.txt sperrt {ROBOTS_TOKEN} mit einer eigenen "
              f"Gruppe ab der Startseite. Abgerufen wurde nur robots.txt.",
              file=sys.stderr, flush=True)
    else:
        print(f"Sitemap: {len(roots)} Wurzel(n), wird aufgeloest ...",
              file=sys.stderr, flush=True)
        raw_urls, sitemap_errors = resolve_sitemap_tree(roots, fetch)
        sitemap_seeds = normalize_sitemap_seeds(raw_urls, base)
        print(f"Sitemap: {len(sitemap_seeds)} URLs, {len(sitemap_errors)} Fehler. "
              f"robots.txt-Gruppe: {robots_group or 'keine'}.",
              file=sys.stderr, flush=True)
        pages = crawl(home, sitemap_seeds, fetch, max_urls, delay,
                      disallow_rules=disallow_rules, blocked_target=blocked_links)

    summary = build_summary(pages, blocked_links=len(blocked_links), base=base,
                            robots_group=robots_group,
                            home_blocked_by_robots=home_blocked)
    # Ob der Lauf an seiner Obergrenze aufgehört hat. Ohne dieses Feld sieht
    # ein gekappter Crawl aus wie ein vollständiger: verwaiste Seiten und nie
    # erreichte hreflang-Ziele wären dann Befunde über den Shop, obwohl sie
    # nur hinter der Grenze lagen.
    summary["max_urls"] = max_urls
    summary["hit_url_limit"] = len(pages) >= max_urls
    return {
        "domain": base,
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "robots": {**robots, "sitemap_errors": sitemap_errors},
        "summary": summary,
        "findings_index": build_findings_index(pages),
        "pages": pages,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Site-Crawl (Statuscodes, Redirect-Ketten, SEO-Kopfdaten, "
                    "Klicktiefe) als JSON-Snapshot ziehen."
    )
    parser.add_argument("--domain", required=True, help="z. B. https://www.example.com")
    parser.add_argument("--out", help="Zielverzeichnis für crawl.json")
    parser.add_argument("--max-urls", type=int, default=5000,
                        help="Obergrenze an URLs über den ganzen Lauf (Default 5000)")
    parser.add_argument("--delay", type=float, default=0.2,
                        help="Sekunden Pause zwischen zwei Abrufen (Default 0.2)")
    parser.add_argument("--check", action="store_true",
                        help="Nur robots.txt und Sitemap-Wurzel prüfen, Exit 0/1")
    args = parser.parse_args()

    if not args.check and not args.out:
        parser.error("ohne --check ist --out erforderlich")

    base = args.domain.rstrip("/")
    opener = _build_opener()

    def fetch(url: str) -> dict:
        return _real_fetch(opener, url, TIMEOUT_SECONDS)

    robots = fetch_robots(base, fetch)
    roots = determine_sitemap_roots(base, robots)

    if args.check:
        sys.exit(check(base, robots, roots, fetch))

    snapshot = build_snapshot(base, robots, roots, fetch, args.max_urls, args.delay)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "crawl.json"
    out_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")

    summary = snapshot["summary"]
    if summary["home_blocked_by_robots"]:
        # Exit 1, damit ein Aufrufer den leeren Snapshot nicht als
        # erfolgreichen Crawl weiterreicht. Die Datei entsteht trotzdem,
        # sie belegt die Absage.
        print(f"Geschrieben: {out_path} ohne eine einzige Seite. robots.txt "
              f"sperrt den Crawler {ROBOTS_TOKEN} mit einer eigenen Gruppe ab "
              f"der Startseite. Das ist eine Absage des Shops, kein leerer Shop "
              f"und kein Fehler des Laufs.")
        sys.exit(1)
    print(f"Geschrieben: {out_path} ({summary['url_count']} URLs, "
          f"{summary['status_code_distribution'].get('200', 0)} mit Status 200)")


if __name__ == "__main__":
    main()
