"""Hilfen für Tests mit dem Bildvergleich vor Gate G4. Kein Test.

Ein Eintrag sieht aus wie das, was `shoot_pair.py` nach `migration/verify/<date>/pairs.json`
schreibt: je Seite und Breite ein Paar, links das veröffentlichte Theme (Rolle `main`), rechts der
Entwurf, jede Aufnahme mit Theme-Nachweis.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

from theme import visual_compare

LIVE = "000000000004"
DRAFT = "000000000002"
GA4 = "G-BEISPIEL01"
#: Der Zustand "Menü offen" am Handy (und "Untermenü offen" am Rechner), ohne fremde Elemente darüber.
MENU_OK = {"state": "ok", "file": "x/mobile-menu.png", "points": 240, "foreign": [],
           "drawer": {"label": "dialog.menu-drawer", "z_index": "18"}}


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
           devices=visual_compare.DEVICES, menu: dict | None = MENU_OK) -> dict:
    """Ein Eintrag wie von `shoot_pair.py`; beide Seiten tragen `menu`, am Handy "Menü offen", am Rechner
    "Untermenü offen" (ohne Angabe: in Ordnung)."""
    def extra(device):
        return {"menu": dict(menu)} if menu is not None else {}
    pairs = [{"page_id": i, "device": d, "a": shot(live, d, live_role, **extra(d)), "b": shot(draft, d, **extra(d))}
             for i in ids for d in devices]
    return {"tool": "shoot_pair", "themes": {"a": live, "b": draft}, "captured_at": captured_at, "pairs": pairs}


def write_record(workspace: Path, data: dict, day: str = "2026-11-11") -> Path:
    path = visual_compare.record_path(workspace, day)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def walk(theme: str, *, device: str = "mobile", latency: int = 800, events=None, consent: str = "accepted",
         started_at: str | None = None, add_ok: bool = True, aborted: bool = False, throttle: dict | None = None) -> dict:
    """Ein Durchlauf von `walk_checkout.py --headless` mit GA4-Aufrufen je Stufe.

    `events` ist eine Liste `(messkennung, ereignis, stufe)`; ohne Angabe die drei Ereignisse des Kaufwegs an
    `GA4`. `aborted` legt einen beim Seitenwechsel abgebrochenen Abruf von `/cart.js` dazu.
    """
    if events is None:
        events = [(GA4, "view_item", "product"), (GA4, "add_to_cart", "add_to_cart"),
                  (GA4, "begin_checkout", "checkout")]
    requests = [{"url": f"https://region1.google-analytics.com/g/collect?v=2&tid={tid}&en={en}", "method": "POST",
                 "resource_type": "fetch", "status": 204, "failure": None, "stage": stage}
                for tid, en, stage in events]
    if aborted:
        requests.append({"url": "https://beispielshop.example/cart.js", "method": "GET", "resource_type": "fetch",
                         "status": None, "failure": "cancelled", "stage": "add_to_cart"})
    data = {"tool": "walk_checkout", "version": 2, "headless": True, "approved_by": "Beispiel Person",
            "started_at": started_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "device": device, "engine": "webkit" if device == "mobile" else "chromium", "latency_ms": latency,
            "theme": {"id": theme, "name": "Beispiel Theme", "role": "unpublished"},
            "consent_result": {"result": consent, "how": "Test"},
            "stages": [{"stage": "product", "state": "ok"}, {"stage": "consent", "state": "ok"},
                       {"stage": "add_to_cart", "state": "ok" if add_ok else "failed"},
                       {"stage": "cart", "state": "ok"}, {"stage": "checkout", "state": "ok"}],
            "requests": requests}
    if throttle:
        data["throttle"] = throttle
    return data


def write_walk(workspace: Path, name: str, data: dict, day: str = "2026-11-11") -> Path:
    path = Path(workspace) / "migration" / "verify" / day / "events" / name / "walk.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def complete_datalayer(workspace: Path, live: str = LIVE, draft: str = DRAFT) -> None:
    """Durchläufe am Handy mit langsamer Verbindung auf beiden Themes, gleiche Ereignisse."""
    write_walk(workspace, "old-mobile-slow", walk(live))
    write_walk(workspace, "new-mobile-slow", walk(draft))


def write_sync(workspace: Path, captured_at: str = "2026-11-11T08:00:00Z", live: str = LIVE,
               day: str = "2026-11-11") -> Path:
    """Ein Abgleich mit dem Live-Theme wie von `sync-live-theme` (`migration/sync/<datum>/delta.json`)."""
    path = Path(workspace) / "migration" / "sync" / day / "delta.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"captured_at": captured_at, "live_theme_id": live,
                                "theme_updated_at_after": captured_at}), encoding="utf-8")
    return path


def complete_compare(workspace: Path, ids=("home", "product")) -> tuple:
    """Alles, was G4 und G5 außer der Liste offener Punkte brauchen: Beispielseiten, ein Abgleich, danach ein
    vollständiger Bildvergleich, und die Durchläufe der Datenschicht. Gibt `(live, draft)` zurück."""
    write_pages(workspace, ids)
    write_sync(workspace)
    write_record(workspace, record(ids))
    complete_datalayer(workspace)
    return LIVE, DRAFT
