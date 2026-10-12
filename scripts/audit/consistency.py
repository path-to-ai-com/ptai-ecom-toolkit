#!/usr/bin/env python3
"""Abweichung zum Referenz-Store als Befund (Disziplin `consistency`).

Spec `ptai-portal` 2026-10-08 "eine Marke, mehrere Stores", Abschnitt 10. Die
Stores einer Marke sollen gleich sein und sind es nicht: das Theme ist nicht
ganz konsistent, jeder Store sieht ein bisschen anders aus. Hat die Marke einen
Referenz-Store (`reference_shop` in der Config des Store-Workspace, etwa
`eu`), vergleicht das Audit jedes anderen Stores seine Snapshots mit den
neuesten des Referenz-Stores. Marken ohne `reference_shop` überspringen das,
etwa eine Marke, deren Stores eigene Marken mit eigenem Theme sind.

Verglichen wird, was ohne Sprache, Währung und Recht gleich sein sollte:

==================  ==========================================================
``theme_version``   Theme-Name und -Version aus der Theme-Sicherung
                    (`migration/snapshots/`, `config/settings_schema.json`)
``theme_settings``  Einstellungen des Themes und der Sections in den
                    JSON-Templates, nur sprachneutrale Werte (Schalter, Zahlen,
                    Auswahlwerte, Farben), dazu fehlende Sections
``apps``            eingebundene Fremddienste (`shop-tech.json`,
                    `storefront_script_hosts`), ohne die eigene Domain
``legal``           Pflichtseiten unter `/policies/` mit Status 200 im Crawl;
                    eine Abweichung kann das Recht des Landes erklären, deshalb
                    `review: "law"`
``structured_data`` Typen der Strukturdaten im Crawl
``seo_description`` Meta-Description je Produkt, gleiche SKU
``alt_text``        Alt-Texte je Produkt, gleiche SKU
``master_data``     Stammdaten der gemeinsamen Produkte (gleiche SKU): Status,
                    Hersteller, Zahl der Varianten und Bilder
==================  ==========================================================

Texte, Preise, Handles und URL-Segmente vergleicht das Modul nie: sie
unterscheiden sich durch Sprache und Währung, und eine solche Abweichung wäre
kein Befund. Was übrig bleibt und doch erklärt ist (eine Pflichtseite, die es
im Land nicht braucht), nimmt die Sitzung mit Grund heraus (`--drop`).

Zwei Schritte:

    python3 -m audit.consistency compare --workspace . --run-id <run-id>
    python3 -m audit.consistency findings --workspace . --run-id <run-id> [--drop legal="…"]

`compare` schreibt `reporting/data/<run-id>/consistency.json`, `findings` daraus
`reporting/runs/<run-id>/findings/consistency.json` im Befund-Schema, mit dem
Titel "Abweichung zu <REF>: …". Phase 3 macht daraus Maßnahmen wie aus jedem
anderen Befund.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from audit import brand as brand_mod

DISCIPLINE = "consistency"

#: Datei der Befunde im Lauf und der Rohvergleich unter `reporting/data/<run-id>/`.
FILE = "consistency.json"

#: Snapshots, die der Vergleich liest. Fehlt einer auf einer Seite, steht der
#: Bereich unter `not_compared`, nie als "keine Abweichung".
SNAPSHOTS = ("shop-tech.json", "crawl.json", "catalog.json")

#: Höchstens so viele Beispiele je Abweichung im Befund.
MAX_EXAMPLES = 10

#: Werte einer Theme-Einstellung, die ohne Sprache gleich sein sollten:
#: Farben und Auswahlwerte. Freitext fällt durch, auch ein einzelnes Wort mit
#: Großbuchstaben oder Leerzeichen.
_NEUTRAL_TEXT = re.compile(r"^(#[0-9a-fA-F]{3,8}|[a-z0-9_\-]{1,40})$")

#: Sprachpräfix vor einem Pfad: /de/, /en-gb/, /de-ch/.
_LOCALE_PREFIX = re.compile(r"^/[a-z]{2}(-[a-z]{2})?(?=/)")

#: Was ein Bereich heißt, im Titel des Befunds und im Bericht.
AREA_LABELS = {
    "theme_version": "Theme-Version",
    "theme_settings": "Theme-Einstellungen",
    "apps": "Eingebundene Dienste",
    "legal": "Pflichtseiten",
    "structured_data": "Strukturdaten",
    "seo_description": "Meta-Descriptions",
    "alt_text": "Alt-Texte",
    "master_data": "Stammdaten",
}

#: Die Stammdaten je Produkt, die ohne Sprache und Währung gleich sein sollten.
MASTER_FIELDS = ("status", "vendor", "variants", "images")


class ConsistencyError(ValueError):
    """Der Vergleich kann nicht laufen: Referenz-Store fehlt, Ordner der Marke fehlt."""


# ------------------------------------------------------------ Konfiguration

def reference_shop(config: dict) -> str | None:
    """Der Referenz-Store der Marke, oder `None`."""
    value = config.get("reference_shop")
    return value if isinstance(value, str) and value else None


def is_active(config: dict) -> bool:
    """Läuft der Vergleich in diesem Store? Nur mit Referenz-Store, und nicht in ihm selbst."""
    ref = reference_shop(config)
    return bool(ref) and ref != brand_mod.shop_slug(config)


def label(shop: str) -> str:
    """Wie ein Store im Titel heißt: "EU" für `eu`, "Nordshop" für `nordshop`."""
    return shop.upper() if len(shop) <= 3 else shop.replace("-", " ").title()


def reference_workspace(workspace, config: dict) -> Path:
    """Der Workspace des Referenz-Stores: `<brand_workspace>/<ref>` (Spec 3.1)."""
    reporting = brand_mod.brand_reporting_dir(workspace, config)
    if reporting is None:
        raise ConsistencyError(
            "reference_shop braucht den Ordner der Marke (brand_workspace): nur von "
            "dort aus liegt der Referenz-Store an bekannter Stelle.")
    ref_ws = reporting.parent / reference_shop(config)
    if not (ref_ws / "reporting").is_dir():
        raise ConsistencyError(f"Der Referenz-Store liegt nicht unter {ref_ws}. "
                               "Ohne seine Snapshots gibt es keinen Vergleich.")
    return ref_ws


# ------------------------------------------------------------ Snapshots lesen

def _read_json(path: Path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def newest_snapshot(store_workspace, name: str) -> Path | None:
    """Der neueste Snapshot `name` eines Stores über alle Läufe unter `reporting/data/`."""
    data = Path(store_workspace) / "reporting" / "data"
    if not data.is_dir():
        return None
    for run in sorted((d for d in data.iterdir() if d.is_dir()), key=lambda d: d.name, reverse=True):
        if (run / name).is_file():
            return run / name
    return None


def newest_theme_snapshot(store_workspace) -> Path | None:
    """Die neueste vollständige Sicherung des Live-Themes (`theme_role: MAIN`)."""
    base = Path(store_workspace) / "migration" / "snapshots"
    if not base.is_dir():
        return None
    best, best_at = None, ""
    for folder in base.iterdir():
        manifest = _read_json(folder / "manifest.json") if folder.is_dir() else None
        if not isinstance(manifest, dict) or manifest.get("theme_role") != "MAIN":
            continue
        if manifest.get("complete") is False:
            continue
        captured = str(manifest.get("captured_at") or folder.name)
        if captured > best_at:
            best, best_at = folder, captured
    return best


def theme_json(path: Path):
    """Eine JSON-Datei aus dem Theme. Shopify setzt vor JSON-Templates einen
    Kommentarblock (`/* … */`), den `json` nicht liest."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return None
    text = re.sub(r"^\s*/\*.*?\*/", "", text, count=1, flags=re.S)
    try:
        return json.loads(text)
    except ValueError:
        return None


# ------------------------------------------------------------ Vergleiche

def _deviation(key: str, count: int, rows: list[dict], evidence: str, sentence: str,
               review: str | None = None) -> dict:
    return {"key": key, "label": AREA_LABELS[key], "count": count,
            "rows": rows[:MAX_EXAMPLES], "evidence": evidence,
            "evidence_text": sentence, "review": review}


def _set_rows(only_ref: set, only_own: set, ref: str, own: str) -> list[dict]:
    rows = [{"from": f"{ref}: {x}", "to": f"{own}: fehlt"} for x in sorted(only_ref)]
    rows += [{"from": f"{ref}: fehlt", "to": f"{own}: {x}"} for x in sorted(only_own)]
    return rows


def theme_info(snapshot: Path | None) -> dict | None:
    """Name und Version aus `config/settings_schema.json` einer Theme-Sicherung."""
    if snapshot is None:
        return None
    schema = theme_json(snapshot / "config" / "settings_schema.json")
    for entry in schema if isinstance(schema, list) else []:
        if isinstance(entry, dict) and entry.get("name") == "theme_info":
            return {"theme_name": entry.get("theme_name"), "theme_version": entry.get("theme_version")}
    return None


def compare_theme_version(ref_info: dict | None, own_info: dict | None, ref: str, own: str) -> dict | None:
    if not ref_info or not own_info or ref_info == own_info:
        return None
    rows = [{"from": f"{ref}: {ref_info.get('theme_name')} {ref_info.get('theme_version')}",
             "to": f"{own}: {own_info.get('theme_name')} {own_info.get('theme_version')}"}]
    return _deviation("theme_version", 1, rows,
                      "migration/snapshots/<MAIN>/config/settings_schema.json > theme_info, beide Stores",
                      f"{own} läuft auf {own_info.get('theme_name')} {own_info.get('theme_version')}, "
                      f"{ref} auf {ref_info.get('theme_name')} {ref_info.get('theme_version')}.")


def neutral(value) -> bool:
    """Ein Einstellungswert, der ohne Sprache gleich sein sollte."""
    if value is None or isinstance(value, (bool, int, float)):
        return True
    return isinstance(value, str) and not value.startswith("shopify://") and bool(_NEUTRAL_TEXT.match(value))


def _settings_pairs(prefix: str, settings) -> dict:
    if not isinstance(settings, dict):
        return {}
    return {f"{prefix}{k}": v for k, v in settings.items() if neutral(v)}


def theme_settings(snapshot: Path | None) -> dict | None:
    """Alle sprachneutralen Einstellungen einer Theme-Sicherung als flache Tabelle.

    Schlüssel `settings_data > <name>` für das Theme, `templates/<datei> >
    <section> > <name>` für eine Section, dazu `… > type` und `… > disabled`.
    Eine Section ist über ihre ID im Template gemeint; fehlt sie in einem
    Store, steht ihr Typ unter `… > type` nur auf einer Seite.
    """
    if snapshot is None:
        return None
    out = {}
    data = theme_json(snapshot / "config" / "settings_data.json")
    current = data.get("current") if isinstance(data, dict) else None
    if isinstance(current, dict):
        out.update(_settings_pairs("settings_data > ",
                                   {k: v for k, v in current.items()
                                    if k not in ("sections", "blocks", "content_for_index")}))
    for template in sorted((snapshot / "templates").glob("*.json")):
        doc = theme_json(template)
        sections = doc.get("sections") if isinstance(doc, dict) else None
        for sid, section in (sections or {}).items():
            if not isinstance(section, dict):
                continue
            base = f"templates/{template.name} > {sid} > "
            out[f"{base}type"] = section.get("type")
            out[f"{base}disabled"] = bool(section.get("disabled"))
            out.update(_settings_pairs(base, section.get("settings")))
    return out


def compare_theme_settings(ref_settings: dict | None, own_settings: dict | None,
                           ref: str, own: str) -> dict | None:
    if ref_settings is None or own_settings is None:
        return None
    rows = []
    for key in sorted(set(ref_settings) | set(own_settings)):
        a, b = ref_settings.get(key, "fehlt"), own_settings.get(key, "fehlt")
        if a != b:
            rows.append({"from": f"{ref}: {key} = {a}", "to": f"{own}: {b}"})
    if not rows:
        return None
    return _deviation("theme_settings", len(rows), rows,
                      "migration/snapshots/<MAIN>/config/settings_data.json und templates/*.json, beide Stores",
                      f"{len(rows)} sprachneutrale Einstellungen des Themes in {own} weichen von {ref} ab.")


def _host(url_or_host: str | None) -> str:
    if not url_or_host:
        return ""
    parsed = urlparse(url_or_host if "//" in url_or_host else f"//{url_or_host}")
    return (parsed.hostname or "").lower()


def script_hosts(shop_tech: dict | None, own_domain: str | None) -> set | None:
    """Fremddienste aus `shop-tech.json`, ohne die Domain des Stores selbst."""
    if not isinstance(shop_tech, dict) or not isinstance(shop_tech.get("storefront_script_hosts"), dict):
        return None
    mine = _host(own_domain)
    return {h.lower() for h in shop_tech["storefront_script_hosts"] if h.lower() != mine}


def compare_apps(ref_tech, own_tech, ref_domain, own_domain, ref: str, own: str) -> dict | None:
    a, b = script_hosts(ref_tech, ref_domain), script_hosts(own_tech, own_domain)
    if a is None or b is None or a == b:
        return None
    rows = _set_rows(a - b, b - a, ref, own)
    return _deviation("apps", len(rows), rows,
                      "shop-tech.json > storefront_script_hosts, beide Stores",
                      f"{len(a - b)} Dienste aus {ref} fehlen in {own}, {len(b - a)} gibt es nur in {own}.")


def policy_pages(crawl: dict | None) -> set | None:
    """Die Pflichtseiten unter `/policies/` mit Status 200, ohne Sprachpräfix."""
    if not isinstance(crawl, dict) or not isinstance(crawl.get("pages"), list):
        return None
    out = set()
    for page in crawl["pages"]:
        if not isinstance(page, dict) or page.get("status") != 200:
            continue
        path = _LOCALE_PREFIX.sub("", urlparse(page.get("url") or "").path)
        match = re.match(r"^/policies/([a-z0-9\-]+)/?$", path)
        if match:
            out.add(match.group(1))
    return out


def compare_legal(ref_crawl, own_crawl, ref: str, own: str) -> dict | None:
    a, b = policy_pages(ref_crawl), policy_pages(own_crawl)
    if a is None or b is None or a == b:
        return None
    rows = _set_rows(a - b, b - a, ref, own)
    return _deviation("legal", len(rows), rows, "crawl.json > pages (/policies/, Status 200), beide Stores",
                      f"{len(a ^ b)} Pflichtseiten gibt es nur in einem der beiden Stores.",
                      review="law")


def schema_types(crawl: dict | None) -> set | None:
    index = (crawl or {}).get("findings_index") if isinstance(crawl, dict) else None
    types = (index or {}).get("schema_types")
    return set(types) if isinstance(types, dict) else None


def compare_structured_data(ref_crawl, own_crawl, ref: str, own: str) -> dict | None:
    a, b = schema_types(ref_crawl), schema_types(own_crawl)
    if a is None or b is None or a == b:
        return None
    rows = _set_rows(a - b, b - a, ref, own)
    return _deviation("structured_data", len(rows), rows,
                      "crawl.json > findings_index.schema_types, beide Stores",
                      f"{len(a - b)} Typen der Strukturdaten aus {ref} fehlen in {own}, "
                      f"{len(b - a)} gibt es nur in {own}.")


def products_by_sku(catalog: dict | None) -> dict | None:
    """SKU auf Produkt aus `catalog.json > products_index` (seit 11.10.2026)."""
    index = catalog.get("products_index") if isinstance(catalog, dict) else None
    if not isinstance(index, list):
        return None
    out = {}
    for product in index:
        for sku in (product.get("skus") or []) if isinstance(product, dict) else []:
            out.setdefault(sku, product)
    return out


def shared_products(ref_catalog, own_catalog) -> list[tuple[dict, dict]] | None:
    """Paare gleicher Produkte über eine gemeinsame SKU, je Produkt des Stores einmal."""
    a, b = products_by_sku(ref_catalog), products_by_sku(own_catalog)
    if a is None or b is None:
        return None
    pairs, seen = [], set()
    for sku in sorted(set(a) & set(b)):
        own_product = b[sku]
        key = own_product.get("handle") or sku
        if key in seen:
            continue
        seen.add(key)
        pairs.append((a[sku], own_product))
    return pairs


def compare_seo_description(pairs, ref: str, own: str) -> dict | None:
    if pairs is None:
        return None
    rows = [{"from": f"{ref}: {r.get('handle')} {'mit' if r.get('seo_description') else 'ohne'} Meta-Description",
             "to": f"{own}: {o.get('handle')} {'mit' if o.get('seo_description') else 'ohne'}"}
            for r, o in pairs if bool(r.get("seo_description")) != bool(o.get("seo_description"))]
    if not rows:
        return None
    return _deviation("seo_description", len(rows), rows,
                      "catalog.json > products_index[].seo_description, gleiche SKU, beide Stores",
                      f"Bei {len(rows)} von {len(pairs)} gemeinsamen Produkten hat nur einer der beiden "
                      "Stores eine Meta-Description.")


def _alt_complete(product: dict) -> bool:
    return (product.get("images") or 0) == (product.get("images_with_alt") or 0)


def compare_alt_text(pairs, ref: str, own: str) -> dict | None:
    if pairs is None:
        return None
    rows = [{"from": f"{ref}: {r.get('handle')} {r.get('images_with_alt')} von {r.get('images')} Bildern mit Alt-Text",
             "to": f"{own}: {o.get('images_with_alt')} von {o.get('images')}"}
            for r, o in pairs if _alt_complete(r) != _alt_complete(o)]
    if not rows:
        return None
    return _deviation("alt_text", len(rows), rows,
                      "catalog.json > products_index[].images_with_alt, gleiche SKU, beide Stores",
                      f"Bei {len(rows)} von {len(pairs)} gemeinsamen Produkten sind die Alt-Texte nur in "
                      "einem der beiden Stores vollständig.")


def compare_master_data(pairs, ref: str, own: str) -> dict | None:
    if pairs is None:
        return None
    rows, products = [], 0
    for r, o in pairs:
        diffs = [f for f in MASTER_FIELDS if r.get(f) != o.get(f)]
        if diffs:
            products += 1
            rows.append({"from": f"{ref}: {r.get('handle')} " + ", ".join(f"{f} {r.get(f)}" for f in diffs),
                         "to": f"{own}: " + ", ".join(f"{f} {o.get(f)}" for f in diffs)})
    if not rows:
        return None
    return _deviation("master_data", products, rows,
                      "catalog.json > products_index[] (status, vendor, variants, images), gleiche SKU",
                      f"{products} von {len(pairs)} gemeinsamen Produkten haben in {own} andere Stammdaten "
                      f"als in {ref}.")


def compare(ref_side: dict, own_side: dict, ref: str, own: str) -> tuple[list[dict], list[dict]]:
    """Alle Vergleiche. Gibt `(deviations, not_compared)` zurück.

    `ref_side` und `own_side` je mit `shop-tech.json`, `crawl.json`,
    `catalog.json` (Dokumente oder `None`), `theme` (Ordner der Theme-Sicherung
    oder `None`) und `domain`. Ein Bereich, für den eine Seite keine Daten hat,
    steht in `not_compared` mit Grund; er ist nicht "gleich".
    """
    ref_label, own_label = label(ref), label(own)
    not_compared = []

    def missing(key: str, *what: tuple[str, object, object]) -> bool:
        for name, a, b in what:
            if a is None or b is None:
                side = ref_label if a is None else own_label
                not_compared.append({"key": key, "label": AREA_LABELS[key],
                                     "reason": f"{name} fehlt für {side}"})
                return True
        return False

    deviations = []
    ref_theme, own_theme = ref_side.get("theme"), own_side.get("theme")
    if not missing("theme_version", ("Theme-Sicherung", ref_theme, own_theme)):
        deviations.append(compare_theme_version(theme_info(ref_theme), theme_info(own_theme),
                                                ref_label, own_label))
        deviations.append(compare_theme_settings(theme_settings(ref_theme), theme_settings(own_theme),
                                                 ref_label, own_label))
    else:
        not_compared.append({"key": "theme_settings", "label": AREA_LABELS["theme_settings"],
                             "reason": not_compared[-1]["reason"]})
    rt, ot = ref_side.get("shop-tech.json"), own_side.get("shop-tech.json")
    if not missing("apps", ("shop-tech.json", script_hosts(rt, ref_side.get("domain")),
                            script_hosts(ot, own_side.get("domain")))):
        deviations.append(compare_apps(rt, ot, ref_side.get("domain"), own_side.get("domain"),
                                       ref_label, own_label))
    rc, oc = ref_side.get("crawl.json"), own_side.get("crawl.json")
    if not missing("legal", ("crawl.json", policy_pages(rc), policy_pages(oc))):
        deviations.append(compare_legal(rc, oc, ref_label, own_label))
    if not missing("structured_data", ("crawl.json", schema_types(rc), schema_types(oc))):
        deviations.append(compare_structured_data(rc, oc, ref_label, own_label))
    pairs = shared_products(ref_side.get("catalog.json"), own_side.get("catalog.json"))
    if pairs is None:
        for key in ("seo_description", "alt_text", "master_data"):
            missing(key, ("catalog.json mit products_index",
                          products_by_sku(ref_side.get("catalog.json")),
                          products_by_sku(own_side.get("catalog.json"))))
    else:
        deviations += [compare_seo_description(pairs, ref_label, own_label),
                       compare_alt_text(pairs, ref_label, own_label),
                       compare_master_data(pairs, ref_label, own_label)]
    return [d for d in deviations if d], not_compared


# ------------------------------------------------------------ Befunde

#: Was eine Abweichung bewirkt und was zu tun ist, je Bereich. Ein Satz, kein
#: erfundener Effekt: die Folge ist, dass die Stores auseinanderlaufen.
EFFECT = {
    "theme_version": "Umsetzungen im Theme wirken nicht in beiden Stores gleich, jede Änderung braucht zwei Wege.",
    "theme_settings": "Kunden sehen in den Stores ein anderes Verhalten, und eine Optimierung im Referenz-Store kommt hier nicht an.",
    "apps": "Funktionen und Messung unterscheiden sich zwischen den Stores, Zahlen sind nicht vergleichbar.",
    "legal": "Eine Pflichtseite, die im Referenz-Store steht, fehlt hier oder umgekehrt.",
    "structured_data": "Suchmaschinen und AI-Systeme lesen die Stores unterschiedlich gut aus.",
    "seo_description": "Gleiche Produkte erscheinen in der Suche mit und ohne gepflegte Beschreibung.",
    "alt_text": "Gleiche Produktbilder sind in einem Store für Screenreader und Bildersuche beschrieben, im anderen nicht.",
    "master_data": "Gleiche Produkte haben in den Stores verschiedene Stammdaten, Auswertungen über beide Stores passen nicht zusammen.",
}

EFFORT = {"theme_version": "large", "theme_settings": "small", "apps": "medium", "legal": "small",
          "structured_data": "medium", "seo_description": "medium", "alt_text": "medium",
          "master_data": "medium"}


def build_findings(deviations: list[dict], ref: str, run_id: str,
                   drop: dict[str, str] | None = None) -> dict:
    """Das Befund-Dokument `findings/consistency.json` aus den Abweichungen.

    `drop` nimmt Bereiche heraus, die Sprache, Währung oder Recht erklären,
    je mit Grund. Ein Bereich mit `review: "law"` muss in `drop` stehen oder
    ausdrücklich bleiben; das prüft der Aufrufer (`findings`-CLI).
    """
    drop = drop or {}
    ref_label = label(ref)
    findings = []
    for dev in deviations:
        if dev["key"] in drop:
            continue
        number = len(findings) + 1
        statement = f"Abweichung zu {ref_label}: {dev['label']} ({dev['count']})"
        findings.append({
            "id": f"ABW-{number:02d}",
            "statement": statement,
            "metrics": [{"label": f"{dev['label']}, abweichend", "value": str(dev["count"]),
                         "context": f"Vergleich mit dem Referenz-Store {ref_label}, neueste Snapshots"}],
            "explanation": (f"Verglichen mit dem Referenz-Store {ref_label}, nur Werte, die ohne "
                            "Sprache, Währung und Recht des Landes gleich sein sollten."),
            "evidence": dev["evidence"],
            "evidence_text": dev["evidence_text"],
            "effect": EFFECT[dev["key"]],
            "fix": f"{dev['label']} an {ref_label} angleichen, oder {ref_label} angleichen, wo dieser Store richtig liegt.",
            "severity": "mittel",
            "confidence": "confirmed",
            "effort": EFFORT[dev["key"]],
            "facts": [{"kind": "effect", "text": EFFECT[dev["key"]]}],
            "proof": {"layout": "wide", "columns": [{"blocks": [
                {"type": "metric", "ref": 0},
                {"type": "pairs", "rows": dev["rows"]},
            ]}]},
        })
    return {"discipline": DISCIPLINE, "run_id": run_id,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "blocked_questions": [], "findings": findings}


# ------------------------------------------------------------ mit Dateien

def _side(store_workspace: Path, config: dict, run_id: str | None) -> tuple[dict, dict]:
    """Die Snapshots eines Stores: aus `run_id`, sonst die neuesten. Gibt
    Dokumente und Pfade zurück."""
    docs, paths = {"domain": config.get("domain")}, {}
    for name in SNAPSHOTS:
        path = (store_workspace / "reporting" / "data" / run_id / name) if run_id else newest_snapshot(store_workspace, name)
        if path is not None and path.is_file():
            docs[name], paths[name] = _read_json(path), str(path)
        else:
            docs[name] = None
    theme = newest_theme_snapshot(store_workspace)
    docs["theme"] = theme
    if theme:
        paths["theme"] = str(theme)
    return docs, paths


def run_compare(workspace, run_id: str) -> Path | None:
    """`compare`: schreibt den Rohvergleich, oder `None`, wenn der Store keinen braucht."""
    workspace = Path(workspace)
    config = brand_mod.read_config(workspace)
    if not is_active(config):
        return None
    ref, own = reference_shop(config), brand_mod.shop_slug(config)
    ref_ws = reference_workspace(workspace, config)
    ref_side, ref_paths = _side(ref_ws, brand_mod.read_config(ref_ws), None)
    own_side, own_paths = _side(workspace, config, run_id)
    deviations, not_compared = compare(ref_side, own_side, ref, own)
    doc = {"reference_shop": ref, "shop": own, "run_id": run_id,
           "compared_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "reference_snapshots": ref_paths, "own_snapshots": own_paths,
           "deviations": deviations, "not_compared": not_compared, "dropped": {}}
    target = workspace / "reporting" / "data" / run_id / FILE
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def run_findings(workspace, run_id: str, drop: dict[str, str], keep_law: bool = False) -> Path:
    """`findings`: schreibt die Befunde aus dem Rohvergleich."""
    workspace = Path(workspace)
    data = workspace / "reporting" / "data" / run_id / FILE
    doc = _read_json(data)
    if not isinstance(doc, dict):
        raise ConsistencyError(f"{data} fehlt; erst compare laufen lassen")
    keys = {d["key"] for d in doc.get("deviations") or []}
    unknown = sorted(set(drop) - keys)
    if unknown:
        raise ConsistencyError(f"--drop für Bereiche ohne Abweichung: {', '.join(unknown)}")
    empty = sorted(k for k, reason in drop.items() if not reason.strip())
    if empty:
        raise ConsistencyError(f"--drop ohne Grund: {', '.join(empty)}")
    law = sorted(d["key"] for d in doc.get("deviations") or []
                 if d.get("review") == "law" and d["key"] not in drop)
    if law and not keep_law:
        raise ConsistencyError(
            f"{', '.join(law)} kann das Recht des Landes erklären. Prüfen und entweder mit "
            "--drop <bereich>=<grund> herausnehmen oder mit --keep-law ausdrücklich behalten.")
    findings = build_findings(doc.get("deviations") or [], doc["reference_shop"], run_id, drop)
    doc["dropped"] = drop
    data.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    target = workspace / "reporting" / "runs" / run_id / "findings" / FILE
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(findings, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def _drop_arg(value: str) -> tuple[str, str]:
    key, _, reason = value.partition("=")
    if key not in AREA_LABELS:
        raise argparse.ArgumentTypeError(f"unbekannter Bereich {key!r}, erlaubt: {', '.join(AREA_LABELS)}")
    return key, reason


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="audit.consistency", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("compare", "findings"):
        p = sub.add_parser(name)
        p.add_argument("--workspace", default=".")
        p.add_argument("--run-id", required=True)
        if name == "findings":
            p.add_argument("--drop", action="append", type=_drop_arg, default=[],
                           help="<bereich>=<grund>, erklärt durch Sprache, Währung oder Recht")
            p.add_argument("--keep-law", action="store_true",
                           help="Abweichungen bei Pflichtseiten ausdrücklich als Befund behalten")
    args = parser.parse_args(argv)
    try:
        if args.command == "compare":
            target = run_compare(args.workspace, args.run_id)
            if target is None:
                print("Kein Referenz-Store (reference_shop) oder dies ist er selbst: kein Vergleich.")
                return 0
            doc = _read_json(target)
            print(f"{target}: {len(doc['deviations'])} Bereiche weichen ab, "
                  f"{len(doc['not_compared'])} nicht verglichen.")
            for item in doc["not_compared"]:
                print(f"  nicht verglichen: {item['label']} ({item['reason']})")
        else:
            target = run_findings(args.workspace, args.run_id, dict(args.drop), args.keep_law)
            print(f"{target} geschrieben.")
    except (ConsistencyError, brand_mod.BrandFileError) as exc:
        print(f"Abbruch: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
