"""Hilfen für Tests mit einer Marke und mehreren Stores. Kein Test.

Baut im Temp-Ordner die Ablage aus Spec `ptai-portal` 2026-10-08, Abschnitt 3.1:

    <tmp>/beispielmarke/
      reporting/measures.json      Liste der Marke (Fixture measures_v2.json)
      eu/reporting/config.json     Store EU mit brand_workspace
      uk/reporting/config.json     Store UK mit brand_workspace

Die Fixture teilt sich das Plugin mit dem Cockpit (`lib/fixtures/` dort). Ihre
Form wird hier nie geändert, nur gelesen.
"""
import copy
import json
import tempfile
from pathlib import Path

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "measures_v2.json"

BRAND = "beispielmarke"


def fixture() -> dict:
    """Die geteilte Fixture als frisches Dokument."""
    return copy.deepcopy(json.loads(FIXTURE.read_text(encoding="utf-8")))


def write_json(path: Path, data) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def store_config(shop: str, brand_workspace: Path | None) -> dict:
    config = {"account_slug": BRAND, "brand": f"Beispielmarke {shop.upper()}",
              "domain": f"https://{shop}.beispielmarke.test",
              "portal": {"brand": BRAND, "shop": shop}}
    if brand_workspace is not None:
        config["brand_workspace"] = str(brand_workspace)
    return config


def make_brand(case, shops=("eu", "uk"), doc=None, linked=True) -> Path:
    """Legt Marke und Stores an und gibt den Ordner der Marke zurück.

    `doc` ist die Liste der Marke, Vorgabe die Fixture; `None` als Wert von
    `doc=False` legt keine an. `linked=False` lässt `brand_workspace` in den
    Configs weg.
    """
    tmp = tempfile.TemporaryDirectory()
    case.addCleanup(tmp.cleanup)
    brand_ws = Path(tmp.name).resolve() / BRAND
    if doc is not False:
        write_json(brand_ws / "reporting" / "measures.json",
                   fixture() if doc is None else doc)
    for shop in shops:
        write_json(brand_ws / shop / "reporting" / "config.json",
                   store_config(shop, brand_ws if linked else None))
    return brand_ws


def read(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))
