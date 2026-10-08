#!/usr/bin/env python3
"""Einen hochgeladenen Lauf für den Kunden sichtbar machen.

Das Gegenstück zu `publish`: der lädt hoch und gibt nie frei, dieses Modul gibt
frei und lädt nichts außer dem Manifest. Bis zum 02.10.2026 gab es dafür keine
Kommandozeile, nur die Funktion `manifest.release()`, die jeder von Hand
zusammen mit `fetch_manifest`, `save` und `upload` aufrufen musste.

Die Freigabe gilt je Lauf, nicht je Fassung. Ist ein Lauf einmal freigegeben,
bricht `publish` eine neue Fassung ohne `--visible` ab, weil sie sofort beim
Kunden wäre.

CLI:
    python3 -m audit.release --workspace . --run-id 2026-09-08-audit
    python3 -m audit.release --workspace . --run-id 2026-09-08-audit --account-slug portal-test
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
from datetime import date
from pathlib import Path

from audit import manifest, publish


def release_local(target, brand: str, shop: str, run_id: str,
                  today: date | None = None) -> dict:
    """Setzt die Freigabe im Manifest unter `target` und gibt den Lauf zurück.

    `KeyError`, wenn der Lauf nicht im Manifest steht: freigegeben wird nur, was
    vorher hochgeladen wurde.
    """
    path = Path(target) / publish.manifest_key(brand)
    data = manifest.release(manifest.load(path), shop, run_id, today=today)
    manifest.save(path, data)
    return next(r for r in data["runs"] if r["shop"] == shop and r["run_id"] == run_id)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--workspace", default=".")
    p.add_argument("--run-id", required=True)
    p.add_argument("--account-slug",
                   help="die Marke statt der aus reporting/config.json, etwa portal-test")
    p.add_argument("--shop",
                   help="der Shop statt des aus dem Markennamen abgeleiteten")
    a = p.parse_args(argv)

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not (url and key):
        print("SUPABASE_URL oder SUPABASE_SERVICE_ROLE_KEY fehlen in der Umgebung. "
              "Nichts freigegeben.", file=sys.stderr)
        return 1

    config = publish.load_config(a.workspace)
    brand, shop = publish.destination(config, a.account_slug)
    shop = a.shop or shop

    with tempfile.TemporaryDirectory() as tmp:
        if publish.fetch_manifest(tmp, brand, url, key) != "remote":
            print(f"Für {brand} liegt kein Manifest im Bucket. Erst hochladen, "
                  "dann freigeben.", file=sys.stderr)
            return 1
        try:
            entry = release_local(tmp, brand, shop, a.run_id)
        except KeyError as exc:
            print(f"{exc}. Nichts freigegeben.", file=sys.stderr)
            return 1
        result = publish.upload(tmp, url, key)
        for line in result["errors"][:10]:
            print(f"  FEHLER {line}", file=sys.stderr)
        if result["errors"]:
            return 1

    print(f"Freigegeben: {shop} / {a.run_id}, Fassung {entry.get('revision', 1)}, "
          f"am {entry['released_at']}. Der Kunde sieht den Lauf jetzt.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
