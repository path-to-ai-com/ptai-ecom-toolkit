"""Horizon-Grundpaket: SEO-Snippets, die jede Migration auf Horizon beim Bau bekommt, nicht nach dem Launch.

Horizon gibt ohne Zutun weniger SEO-Ausgabe aus als die meisten älteren Themes.
Am 07.10.2026 ging eine Migration mit diesen Lücken live; gefunden hatte sie ein
Prüfbericht, geschlossen hatte sie niemand. Seitdem kommen die Snippets mit dem
Bau ins Ziel-Repo (`reference/theme-migration/horizon-base/`):

- `<prefix>-product-structured-data`: Produkt-JSON-LD statt `structured_data`,
  mit `description` an jeder Variante und `aggregateRating` aus den
  Standard-Metafeldern `reviews.rating` und `reviews.rating_count`
- `<prefix>-hreflang`: hreflang aus den veröffentlichten Sprachen, deckungsgleich
  mit der Canonical; nur einbinden, wenn Shopify keine automatischen Tags ausgibt
- `<prefix>-og-image-fallback`: `og:image` aus dem Shoplogo, wenn die Seite kein Bild hat
- `<prefix>-website-structured-data`: `WebSite` mit `SearchAction` auf der Startseite

Dazu drei kleine Eingriffe in Horizon-Dateien (Render-Aufrufe und `og:type
product.group` auf Kategorien). Die schreibt die Skill von Hand nach
`seo-parity.md`, mit Kommentar `<prefix>:` und Zeile im Verzeichnis der
Eingriffe; dieses Modul kopiert nur die Snippets und prüft danach, ob die
Eingriffe stehen.

CLI:
    python3 -m theme.horizon_base install --target-repo <pfad> --prefix <p>
    python3 -m theme.horizon_base check --target-repo <pfad> --prefix <p> [--without-hreflang]

`install` schreibt `snippets/<prefix>-*.liquid` und ersetzt dabei den
Platzhalter `beispiel-` durch das Präfix. Eine vorhandene, abweichende Datei
wird nur mit `--force` überschrieben, weil sie eine bewusste Anpassung sein kann.
`check` meldet fehlende Snippets und fehlende Eingriffe. Exit 0 ohne Befund,
1 mit Befunden, 2 bei Fehlern.
"""
import argparse
import json
import re
import sys
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[2] / "reference" / "theme-migration" / "horizon-base" / "snippets"
PLACEHOLDER = "beispiel"

#: Eingriffe in Horizon-Dateien: Datei, Bezeichnung, Muster mit `{prefix}`, ob hreflang betroffen ist.
HOOKS = (
    ("sections/product-information.liquid", "Produkt-JSON-LD statt structured_data",
     r"""render\s+['"]{prefix}-product-structured-data['"]""", False),
    ("snippets/meta-tags.liquid", "og:type product.group auf Kategorien",
     r"""['"]product\.group['"]""", False),
    ("snippets/meta-tags.liquid", "og:image aus dem Shoplogo ohne Seitenbild",
     r"""render\s+['"]{prefix}-og-image-fallback['"]""", False),
    ("layout/theme.liquid", "WebSite mit SearchAction auf der Startseite",
     r"""render\s+['"]{prefix}-website-structured-data['"]""", False),
    ("layout/theme.liquid", "hreflang aus den veröffentlichten Sprachen",
     r"""render\s+['"]{prefix}-hreflang['"]""", True),
)
#: So steht Horizons eigene Produktauszeichnung im Original; bleibt sie, gibt es zwei Produkt-JSON-LD.
LEFTOVER = re.compile(r"closest\.product\s*\|\s*structured_data")


def snippets() -> dict:
    """Die Snippets des Pakets als `{dateiname: text}` mit Platzhalter."""
    return {p.name: p.read_text(encoding="utf-8") for p in sorted(SOURCE.glob(f"{PLACEHOLDER}-*.liquid"))}


def with_prefix(name: str, text: str, prefix: str) -> tuple:
    """Dateiname und Inhalt mit dem Präfix des Projekts statt des Platzhalters."""
    pattern = re.compile(rf"\b{PLACEHOLDER}-")
    return pattern.sub(f"{prefix}-", name, count=1), pattern.sub(f"{prefix}-", text)


def install(target: Path, prefix: str, force: bool = False) -> dict:
    """Snippets ins Ziel-Repo; `{"written", "unchanged", "kept"}` mit Dateinamen."""
    result = {"written": [], "unchanged": [], "kept": []}
    folder = Path(target) / "snippets"
    folder.mkdir(parents=True, exist_ok=True)
    for name, text in snippets().items():
        name, text = with_prefix(name, text, prefix)
        path = folder / name
        if path.exists():
            current = path.read_text(encoding="utf-8")
            if current == text:
                result["unchanged"].append(name)
                continue
            if not force:
                result["kept"].append(name)
                continue
        path.write_text(text, encoding="utf-8")
        result["written"].append(name)
    return result


def check(target: Path, prefix: str, with_hreflang: bool = True) -> list:
    """Befunde: fehlendes Snippet, fehlender Eingriff, verbliebenes `structured_data` am Produkt."""
    findings = []
    target = Path(target)
    for name, _ in snippets().items():
        name, _ = with_prefix(name, "", prefix)
        if with_hreflang or "hreflang" not in name:
            if not (target / "snippets" / name).is_file():
                findings.append(f"snippets/{name} fehlt")
    for file, label, pattern, hreflang in HOOKS:
        if hreflang and not with_hreflang:
            continue
        path = target / file
        text = path.read_text(encoding="utf-8") if path.is_file() else ""
        if not re.search(pattern.format(prefix=re.escape(prefix)), text):
            findings.append(f"{file}: Eingriff fehlt ({label})")
    product = target / "sections" / "product-information.liquid"
    if product.is_file() and LEFTOVER.search(product.read_text(encoding="utf-8")):
        findings.append("sections/product-information.liquid: structured_data steht noch, Produkt-JSON-LD doppelt")
    return findings


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(prog="theme.horizon_base", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("install", "check"):
        cmd = sub.add_parser(command)
        cmd.add_argument("--target-repo", required=True)
        cmd.add_argument("--prefix", required=True)
        if command == "install":
            cmd.add_argument("--force", action="store_true", help="abweichende Dateien überschreiben")
        else:
            cmd.add_argument("--without-hreflang", action="store_true",
                             help="Shopify gibt hreflang automatisch aus, das Snippet entfällt")
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", args.prefix):
        print(json.dumps({"ok": False, "error": f"Präfix ungültig: {args.prefix!r}"}, ensure_ascii=False))
        return 2
    target = Path(args.target_repo)
    if not target.is_dir():
        print(json.dumps({"ok": False, "error": f"{target} ist kein Ordner"}, ensure_ascii=False))
        return 2
    if args.command == "install":
        result = install(target, args.prefix, args.force)
        print(json.dumps({"ok": True, **result}, ensure_ascii=False))
        return 1 if result["kept"] else 0
    findings = check(target, args.prefix, not args.without_hreflang)
    print(json.dumps({"ok": not findings, "findings": findings}, ensure_ascii=False))
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
