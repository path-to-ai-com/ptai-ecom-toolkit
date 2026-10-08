"""SEO-Ausgabe im Vergleich: strukturierte Daten, hreflang, Open Graph und Kopfdaten, Live gegen Entwurf.

Am 07.10.2026 ging ein Theme-Wechsel auf Horizon live, obwohl ein Prüfbericht
die Lücken unter "Vor dem Launch" führte: hreflang fehlte auf jeder Seite, das
Rückfallbild für `og:image`, `og:type product.group` auf Kategorien, `WebSite`
mit `SearchAction` auf der Startseite und `aggregateRating` im Produkt-Markup.
Dazu eine Lücke, die vorher niemand kannte: Horizons `structured_data` gibt eine
`ProductGroup` aus, deren Varianten keine `description` tragen, und die Search
Console meldet danach jede Variante in den Händlereinträgen. Der Launch-Check
verglich bis dahin nur `robots.txt`, Statuscodes, `noindex` und Canonicals.

Dieses Modul vergleicht je Seite das HTML des Live-Themes mit dem des Entwurfs
(nach dem Launch: das des veröffentlichten Themes mit dem Mitschnitt von
vorher). Die Regel ist einfach und hart: **was live da ist und im Entwurf
fehlt, ist ein Befund**. Dazu eine Regel unabhängig vom Live-Stand: eine
`ProductGroup`, deren Varianten keine `description` tragen, ist immer ein
Befund.

Das HTML kommt aus dem Mitschnitt von `scripts/browser/capture_network.py`,
nicht aus einem eigenen Abruf. Zwei Gründe: die Vorschau eines Entwurfs ist nur
im Browser verlässlich (Cookie und Weiterleitung), und die Storefront verträgt
einen Prüfer zur Zeit mit drei bis fünf Sekunden zwischen zwei Seitenaufrufen.
Ein zweiter Abrufer neben dem Mitschnitt würde beides verletzen.

Geparst wird mit `html.parser` aus der Standardbibliothek, nicht mit
regulären Ausdrücken: Horizon schreibt Meta-Tags über mehrere Zeilen
(`<meta\\n  property="og:type"\\n  content="...">`), und JSON-LD steht in
Skript-Blöcken, die ein Muster leicht zu früh beendet.

CLI:
    python3 -m theme.seo_parity compare --old <network.json> --new <network.json> [--locales de,en]
    python3 -m theme.seo_parity pages --pages <pages.json> --locales de,en [--out <pages.json>]

`compare` gibt das Ergebnis je Thema als JSON aus, `pages` ergänzt eine
Seitenliste um je eine Fassung jeder weiteren Sprache (`/<sprache><pfad>`),
damit der Mitschnitt jede veröffentlichte Sprache abdeckt.
"""
import argparse
import json
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse

#: Themen des Vergleichs, je eine Zeile im Launch-Check.
TOPICS = ("structured_data", "hreflang", "open_graph", "head")
#: Typen, die als ein Produkt zählen. Broadcast und viele ältere Themes geben `Product` mit einem
#: Angebot je Variante aus, Horizon eine `ProductGroup`; beides ist dieselbe Auszeichnung.
PRODUCT_TYPES = ("Product", "ProductGroup")
#: Felder einer Produktauszeichnung, die der Entwurf behalten muss, wenn live sie hat.
PRODUCT_FIELDS = ("name", "description", "image", "identifier", "brand", "offers", "aggregateRating")
#: Kennungen eines Produkts; eine davon genügt.
IDENTIFIERS = ("sku", "gtin", "gtin8", "gtin12", "gtin13", "gtin14", "mpn")
#: Pflichtangaben eines Angebots.
OFFER_FIELDS = ("price", "priceCurrency", "availability")
#: Felder weiterer Typen, die der Entwurf behalten muss, wenn live sie hat.
TYPE_FIELDS = {
    "Organization": ("name", "url", "logo", "sameAs"),
    "WebSite": ("name", "url", "potentialAction"),
    "BreadcrumbList": ("itemListElement",),
}
#: Diese Parameter gehören zur Vorschau, nicht zur Adresse einer Seite.
PREVIEW_PARAMS = ("preview_theme_id", "pb", "_ab", "_fd", "_sc")
#: Seitentypen, ohne die ein Vergleich nicht vollständig ist (Template-Grundtyp).
REQUIRED_TEMPLATES = ("index", "collection", "product")


# ---------------------------------------------------------------------------
# HTML lesen
# ---------------------------------------------------------------------------

class _HeadParser(HTMLParser):
    """Sammelt, was für SEO zählt; ein kaputtes Tag bricht nichts ab."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.lang = None
        self.titles = []
        self.meta = []
        self.links = []
        self.scripts = []
        self._in_title = False
        self._in_jsonld = False
        self._buffer = []

    def handle_starttag(self, tag, attrs):
        attrs = {k.lower(): (v or "") for k, v in attrs}
        if tag == "html" and self.lang is None:
            self.lang = attrs.get("lang") or None
        elif tag == "title":
            self._in_title, self._buffer = True, []
        elif tag == "meta":
            self.meta.append(attrs)
        elif tag == "link":
            self.links.append(attrs)
        elif tag == "script" and attrs.get("type", "").strip().lower() == "application/ld+json":
            self._in_jsonld, self._buffer = True, []

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if tag == "title" and self._in_title:
            self.titles.append(" ".join("".join(self._buffer).split()))
            self._in_title = False
        elif tag == "script" and self._in_jsonld:
            self.scripts.append("".join(self._buffer))
            self._in_jsonld = False

    def handle_data(self, data):
        if self._in_title or self._in_jsonld:
            self._buffer.append(data)


def _types(node: dict) -> list:
    value = node.get("@type")
    return [str(t) for t in (value if isinstance(value, list) else [value]) if t]


def jsonld_entities(scripts: list) -> tuple:
    """Oberste Einträge aller JSON-LD-Blöcke, `@graph` aufgelöst; dazu die Zahl unlesbarer Blöcke."""
    entities, errors = [], 0
    for text in scripts:
        try:
            data = json.loads(text)
        except ValueError:
            errors += 1
            continue
        stack = data if isinstance(data, list) else [data]
        for node in stack:
            if not isinstance(node, dict):
                continue
            if isinstance(node.get("@graph"), list):
                entities += [n for n in node["@graph"] if isinstance(n, dict)]
            else:
                entities.append(node)
    return entities, errors


def parse_page(html: str) -> dict:
    """Die SEO-Ausgabe einer Seite: Sprache, Titel, Description, Canonical, Open Graph, hreflang, JSON-LD."""
    parser = _HeadParser()
    try:
        parser.feed(html or "")
        parser.close()
    except Exception:  # noqa: BLE001  html.parser wirft selten, ein Teilergebnis ist besser als keins
        pass
    description, og = None, {}
    for attrs in parser.meta:
        name = attrs.get("name", "").strip().lower()
        prop = attrs.get("property", "").strip().lower()
        if name == "description" and description is None:
            description = attrs.get("content", "").strip()
        if prop.startswith("og:"):
            og.setdefault(prop, []).append(attrs.get("content", "").strip())
    canonical, hreflang = None, []
    for attrs in parser.links:
        rel = attrs.get("rel", "").lower().split()
        if "canonical" in rel and canonical is None:
            canonical = attrs.get("href") or None
        if "alternate" in rel and attrs.get("hreflang"):
            hreflang.append((attrs["hreflang"].strip().lower(), attrs.get("href", "").strip()))
    entities, errors = jsonld_entities(parser.scripts)
    return {"lang": (parser.lang or "").strip().lower() or None, "title": parser.titles[0] if parser.titles else None,
            "description": description, "canonical": canonical, "og": og, "hreflang": hreflang,
            "jsonld": entities, "jsonld_errors": errors}


# ---------------------------------------------------------------------------
# Strukturierte Daten
# ---------------------------------------------------------------------------

def _present(value) -> bool:
    if isinstance(value, (list, dict)):
        return bool(value) and any(_present(v) for v in (value if isinstance(value, list) else value.values()))
    return value is not None and str(value).strip() != ""


def _offers(node: dict) -> list:
    value = node.get("offers")
    offers = value if isinstance(value, list) else [value]
    return [o for o in offers if isinstance(o, dict)]


def _offer_complete(offer: dict) -> bool:
    return all(_present(offer.get(field)) for field in OFFER_FIELDS)


def product_summary(node: dict) -> dict:
    """Was eine Produktauszeichnung trägt, gleich ob `Product` oder `ProductGroup`.

    Bei einer `ProductGroup` stehen Kennung und Angebote an den Varianten
    (`hasVariant`); eine Kennung genügt an einer Variante, Angebote müssen an
    jeder Variante vollständig sein.
    """
    variants = [v for v in (node.get("hasVariant") or []) if isinstance(v, dict)] \
        if isinstance(node.get("hasVariant"), list) else []
    carriers = variants or [node]
    offers = [o for c in carriers for o in _offers(c)]
    offers_ok = bool(offers) and all(_offer_complete(o) for o in offers) \
        and all(_offers(c) for c in carriers)
    return {
        "name": _present(node.get("name")),
        "description": _present(node.get("description")),
        "image": _present(node.get("image")) or any(_present(v.get("image")) for v in variants),
        "identifier": any(_present(c.get(k)) for c in [node] + variants for k in IDENTIFIERS),
        "brand": _present(node.get("brand")),
        "offers": offers_ok,
        "aggregateRating": _present(node.get("aggregateRating")),
        "variants": len(variants),
        "variants_without_description": sum(1 for v in variants if not _present(v.get("description"))),
        "is_group": "ProductGroup" in _types(node),
    }


def type_set(entities: list) -> set:
    """Typen der obersten Einträge; `ProductGroup` zählt als `Product`."""
    out = set()
    for node in entities:
        for t in _types(node):
            out.add("Product" if t in PRODUCT_TYPES else t)
    return out


def products(entities: list) -> list:
    return [n for n in entities if set(_types(n)) & set(PRODUCT_TYPES)]


def compare_structured_data(old: dict | None, new: dict) -> tuple:
    """Befunde und Hinweise zu JSON-LD einer Seite; `old` None heißt ohne Live-Stand."""
    problems, notes = [], []
    new_entities = new["jsonld"]
    if new["jsonld_errors"] and not (old and old["jsonld_errors"] >= new["jsonld_errors"]):
        problems.append(f"{new['jsonld_errors']} JSON-LD-Block nicht lesbar")
    new_products = products(new_entities)
    # Absolut, unabhängig vom Live-Stand: Google meldet jede Variante ohne Beschreibung.
    for node in new_products:
        summary = product_summary(node)
        if summary["is_group"] and summary["variants_without_description"]:
            problems.append(f"ProductGroup: {summary['variants_without_description']} von {summary['variants']} "
                            "Varianten ohne description")
    if old is None:
        return problems, notes
    old_entities = old["jsonld"]
    old_types, new_types = type_set(old_entities), type_set(new_entities)
    for missing in sorted(old_types - new_types):
        problems.append(f"{missing} fehlt (live vorhanden)")
    old_products = products(old_entities)
    if len(new_products) > 1 and len(old_products) <= 1:
        problems.append(f"Produkt-JSON-LD {len(new_products)}-mal statt einmal")
    if old_products and new_products:
        before = product_summary(old_products[0])
        after_all = [product_summary(n) for n in new_products]
        for field in PRODUCT_FIELDS:
            if before[field] and not any(a[field] for a in after_all):
                problems.append(f"Produkt ohne {field} (live vorhanden)")
        if before["is_group"] != after_all[0]["is_group"]:
            notes.append("Produkt als " + ("ProductGroup" if after_all[0]["is_group"] else "Product")
                         + ", live als " + ("ProductGroup" if before["is_group"] else "Product"))
    for type_name, fields in TYPE_FIELDS.items():
        before = [n for n in old_entities if type_name in _types(n)]
        after = [n for n in new_entities if type_name in _types(n)]
        if not (before and after):
            continue
        for field in fields:
            if any(_present(n.get(field)) for n in before) and not any(_present(n.get(field)) for n in after):
                problems.append(f"{type_name} ohne {field} (live vorhanden)")
    return problems, notes


# ---------------------------------------------------------------------------
# hreflang
# ---------------------------------------------------------------------------

def url_key(url: str | None) -> str | None:
    """Pfad und Abfrage einer Adresse ohne Vorschau-Parameter, ohne Schrägstrich am Ende."""
    if not url:
        return None
    parsed = urlparse(url)
    query = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True) if k not in PREVIEW_PARAMS]
    path = parsed.path.rstrip("/") or "/"
    return path + ("?" + urlencode(sorted(query)) if query else "")


def primary_subtag(code: str) -> str:
    return (code or "").split("-")[0].lower()


def hreflang_state(page: dict, published: set | None) -> dict:
    """Werte, Dubletten, Widerspruch zum Canonical und unveröffentlichte Sprachen einer Seite."""
    counts = {}
    for value, _ in page["hreflang"]:
        counts[value] = counts.get(value, 0) + 1
    contradiction = None
    lang = page.get("lang")
    if page["hreflang"] and lang and page.get("canonical"):
        own = [href for value, href in page["hreflang"] if value == lang] \
            or [href for value, href in page["hreflang"] if primary_subtag(value) == primary_subtag(lang)]
        canonical = url_key(page["canonical"])
        # Jeder Verweis auf die eigene Sprache muss die Canonical sein, auch ein doppelter.
        other = [url_key(h) for h in own if url_key(h) != canonical]
        if other:
            contradiction = f"hreflang {lang} zeigt auf {other[0]}, Canonical {canonical}"
    unpublished = sorted({v for v in counts if v != "x-default" and published is not None
                          and primary_subtag(v) not in published})
    return {"values": set(counts), "duplicates": sorted(v for v, n in counts.items() if n > 1),
            "contradiction": contradiction, "unpublished": unpublished}


def compare_hreflang(old: dict | None, new: dict, published: set | None) -> tuple:
    problems, notes = [], []
    after = hreflang_state(new, published)
    before = hreflang_state(old, published) if old else None
    if before:
        missing = sorted(before["values"] - after["values"])
        if missing and not after["values"]:
            problems.append(f"hreflang fehlt ganz, live {len(before['values'])} Werte ({', '.join(sorted(before['values']))})")
        elif missing:
            problems.append("hreflang ohne " + ", ".join(missing) + " (live vorhanden)")
    for key, label in (("duplicates", "hreflang doppelt"), ("unpublished", "hreflang auf unveröffentlichte Sprache")):
        new_items = [v for v in after[key] if not before or v not in before[key]]
        old_items = [v for v in after[key] if before and v in before[key]]
        if new_items:
            problems.append(f"{label}: {', '.join(new_items)}")
        if old_items:
            notes.append(f"{label} wie live: {', '.join(old_items)}")
    if after["contradiction"]:
        (notes if before and before["contradiction"] else problems).append(
            after["contradiction"] + (" (wie live)" if before and before["contradiction"] else ""))
    if published is None and after["values"]:
        notes.append("veröffentlichte Sprachen unbekannt, Abgleich der hreflang-Sprachen nicht geprüft")
    return problems, notes


# ---------------------------------------------------------------------------
# Open Graph und Kopfdaten
# ---------------------------------------------------------------------------

def compare_open_graph(old: dict | None, new: dict) -> tuple:
    problems, notes = [], []
    if old is None:
        if not new["og"].get("og:image"):
            notes.append("og:image fehlt, ohne Live-Stand zum Vergleich")
        return problems, notes
    old_type = (old["og"].get("og:type") or [None])[0]
    new_type = (new["og"].get("og:type") or [None])[0]
    if old_type and old_type != new_type:
        problems.append(f"og:type {new_type or 'fehlt'}, live {old_type}")
    missing = sorted(p for p, values in old["og"].items()
                     if p != "og:type" and any(values) and not any(new["og"].get(p) or []))
    if missing:
        problems.append(", ".join(missing) + " fehlt (live vorhanden)")
    return problems, notes


def compare_head(old: dict | None, new: dict) -> tuple:
    problems = []
    if old is None:
        return problems, []
    for field, label in (("title", "title"), ("description", "meta description"), ("canonical", "Canonical")):
        if old.get(field) and not new.get(field):
            problems.append(f"{label} fehlt (live vorhanden)")
    return problems, []


def compare_page(old_html: str | None, new_html: str, published: set | None = None) -> dict:
    """Je Thema `{"problems": [...], "notes": [...]}` für ein Seitenpaar."""
    old = parse_page(old_html) if old_html is not None else None
    new = parse_page(new_html)
    out = {}
    for topic, (problems, notes) in (
            ("structured_data", compare_structured_data(old, new)),
            ("hreflang", compare_hreflang(old, new, published)),
            ("open_graph", compare_open_graph(old, new)),
            ("head", compare_head(old, new))):
        out[topic] = {"problems": problems, "notes": notes}
    return out


# ---------------------------------------------------------------------------
# Seitenpaare und Abdeckung
# ---------------------------------------------------------------------------

def page_locale(page: dict, locales: set) -> str | None:
    """Sprache einer Seite: Feld `locale`, sonst das erste Pfadsegment, wenn es eine bekannte Sprache ist."""
    if page.get("locale"):
        return primary_subtag(page["locale"])
    first = (page.get("path") or "/").strip("/").split("/")[0].split("?")[0].lower()
    return primary_subtag(first) if first and primary_subtag(first) in locales else None


def template_base(page: dict) -> str:
    return str(page.get("template") or page.get("id") or "").split(".")[0].split("/")[0]


def compare_pages(pairs: list, published: set | None = None, primary: str | None = None) -> dict:
    """Vergleich über alle Seitenpaare.

    `pairs`: `[{"id", "path", "template", "locale"?, "old_html", "new_html"}]`;
    `old_html` darf None sein (keine Live-Fassung im Mitschnitt), `new_html` nicht.
    `published`: Primär-Subtags der veröffentlichten Sprachen oder None, wenn unbekannt.
    Liefert je Thema die Befunde je Seite und eine Abdeckung nach Seitentyp und Sprache.
    """
    topics = {t: {"pages": 0, "problems": [], "notes": []} for t in TOPICS}
    templates, languages, without_live = set(), set(), []
    for pair in pairs:
        result = compare_page(pair.get("old_html"), pair["new_html"], published)
        templates.add(template_base(pair))
        lang = page_locale(pair, published or set()) or primary
        if lang:
            languages.add(lang)
        if pair.get("old_html") is None:
            without_live.append(pair.get("path") or pair.get("id"))
        for topic, found in result.items():
            topics[topic]["pages"] += 1
            topics[topic]["problems"] += [{"path": pair.get("path"), "page_id": pair.get("id"), "text": t}
                                          for t in found["problems"]]
            topics[topic]["notes"] += [{"path": pair.get("path"), "page_id": pair.get("id"), "text": t}
                                       for t in found["notes"]]
    missing_templates = sorted(t for t in REQUIRED_TEMPLATES if t not in templates)
    missing_languages = sorted((published or set()) - languages) if published is not None else []
    return {"topics": topics, "templates": sorted(templates), "languages": sorted(languages),
            "missing_templates": missing_templates, "missing_languages": missing_languages,
            "without_live": without_live}


def expand_pages(pages: dict, locales: list, primary: str | None = None) -> dict:
    """Seitenliste plus je weiterer Sprache eine Fassung unter `/<sprache><pfad>`.

    Seiten mit eigener Sprache bleiben, wie sie sind; vorhandene IDs werden nicht
    doppelt angelegt. Die Primärsprache (erste Angabe in `locales`, wenn nicht
    gesetzt) hat keinen Pfad-Präfix.
    """
    locales = [primary_subtag(l) for l in locales if l]
    primary = primary_subtag(primary) if primary else (locales[0] if locales else None)
    base = [p for p in pages.get("pages") or [] if isinstance(p, dict)]
    ids = {p.get("id") for p in base}
    out = [dict(p) for p in base]
    for page in base:
        # Nur Seiten der Primärsprache bekommen Fassungen; `locale: "de"` an der Primärsprache zählt mit.
        own = primary_subtag(page["locale"]) if page.get("locale") else page_locale(page, set(locales))
        if own and own != primary:
            continue
        for locale in locales:
            if locale == primary:
                continue
            new_id = f"{page['id']}-{locale}"
            if new_id in ids:
                continue
            path = page.get("path") or "/"
            out.append({**page, "id": new_id, "locale": locale,
                        "path": f"/{locale}" + ("" if path == "/" else path)})
            ids.add(new_id)
    return {**pages, "pages": out}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def pairs_from_captures(old_file: str, new_file: str) -> list:
    """Seitenpaare aus zwei `network.json`, erster gültiger Desktop-Durchlauf je Seite."""
    def html_by_page(path: str) -> dict:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        out = {}
        runs = sorted((r for r in data.get("runs") or [] if r.get("state") == "ok" and r.get("html_file")),
                      key=lambda r: (r.get("run") != 1, r.get("device") != "desktop"))
        for run in runs:
            if run.get("page_id") in out:
                continue
            try:
                html = (Path(path).parent / run["html_file"]).read_text(encoding="utf-8")
            except OSError:
                continue
            out[run["page_id"]] = {"id": run["page_id"], "path": run.get("path"), "template": run.get("template"),
                                   "html": html}
        return out
    old, new = html_by_page(old_file), html_by_page(new_file)
    return [{"id": k, "path": v["path"], "template": v["template"], "new_html": v["html"],
             "old_html": (old.get(k) or {}).get("html")} for k, v in sorted(new.items(), key=lambda kv: str(kv[0]))]


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(prog="theme.seo_parity", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    cmp_parser = sub.add_parser("compare", help="zwei Mitschnitte vergleichen")
    cmp_parser.add_argument("--old", required=True, help="network.json des Live-Themes (vor dem Launch)")
    cmp_parser.add_argument("--new", required=True, help="network.json des Entwurfs oder des neuen Themes")
    cmp_parser.add_argument("--locales", help="veröffentlichte Sprachen, kommagetrennt, Primärsprache zuerst")
    pages_parser = sub.add_parser("pages", help="Seitenliste um weitere Sprachen ergänzen")
    pages_parser.add_argument("--pages", required=True)
    pages_parser.add_argument("--locales", required=True, help="veröffentlichte Sprachen, Primärsprache zuerst")
    pages_parser.add_argument("--out", help="Ziel, Standard: die Eingabe überschreiben")
    args = parser.parse_args(argv)
    try:
        if args.command == "pages":
            data = json.loads(Path(args.pages).read_text(encoding="utf-8"))
            result = expand_pages(data, args.locales.split(","))
            Path(args.out or args.pages).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                                                    encoding="utf-8")
            print(json.dumps({"ok": True, "pages": len(result["pages"]), "out": args.out or args.pages}))
            return 0
        locales = [primary_subtag(l) for l in (args.locales or "").split(",") if l.strip()]
        result = compare_pages(pairs_from_captures(args.old, args.new), set(locales) if locales else None,
                               locales[0] if locales else None)
    except (OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if any(t["problems"] for t in result["topics"].values()) else 0


if __name__ == "__main__":
    sys.exit(main())
