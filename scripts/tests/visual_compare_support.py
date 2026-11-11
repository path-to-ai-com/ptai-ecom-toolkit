"""Hilfen für Tests mit dem Bildvergleich vor Gate G4. Kein Test.

Ein Eintrag sieht aus wie das, was `shoot_pair.py` nach `migration/verify/<date>/pairs.json`
schreibt: je Seite und Breite ein Paar, links das veröffentlichte Theme (Rolle `main`), rechts der
Entwurf, jede Aufnahme mit Theme-Nachweis.
"""
import json
from pathlib import Path

from theme import visual_compare

LIVE = "000000000004"
DRAFT = "000000000002"


def write_pages(workspace: Path, ids=("home", "product")) -> Path:
    path = Path(workspace) / "migration" / "inventory" / "pages.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"base_url": "https://beispielshop.example",
                                "pages": [{"id": i, "path": "/" if i == "home" else f"/{i}"} for i in ids]}),
                    encoding="utf-8")
    return path


def shot(theme: str, device: str, role: str | None = "unpublished", state: str = "ok", **extra) -> dict:
    data = {"state": state, "theme_id": theme, "file": f"x/{device}.png", "fold_file": f"x/{device}-fold.png",
            "viewport": {"width": visual_compare.WIDTHS[device], "height": 900},
            "theme_check": {"expected": theme, "found": theme, "found_role": role, "ok": state == "ok",
                            "state": state}}
    data.update(extra)
    return data


def record(ids=("home", "product"), live: str = LIVE, draft: str = DRAFT,
           captured_at: str = "2026-11-11T09:00:00+00:00", live_role: str | None = "main",
           devices=visual_compare.DEVICES) -> dict:
    pairs = [{"page_id": i, "device": d, "a": shot(live, d, live_role), "b": shot(draft, d)}
             for i in ids for d in devices]
    return {"tool": "shoot_pair", "themes": {"a": live, "b": draft}, "captured_at": captured_at, "pairs": pairs}


def write_record(workspace: Path, data: dict, day: str = "2026-11-11") -> Path:
    path = visual_compare.record_path(workspace, day)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def complete_compare(workspace: Path, ids=("home", "product")) -> tuple:
    """Beispielseiten und ein vollständiger Vergleich; gibt `(live, draft)` zurück."""
    write_pages(workspace, ids)
    write_record(workspace, record(ids))
    return LIVE, DRAFT
