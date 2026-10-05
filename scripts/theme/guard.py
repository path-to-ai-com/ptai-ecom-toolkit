"""Schutz vor jedem Schreiben ins Theme (Spec 7.7).

Drei Regeln, jede vor jedem einzelnen Schreibvorgang, nicht einmal pro Lauf:

1. Die Ziel-ID ist die `draft_theme_id` aus der Konfiguration. Eine andere ID
   wird verweigert, auch wenn sie unveröffentlicht ist.
2. Die Rolle des Ziels wird frisch gelesen und muss `UNPUBLISHED` sein. `MAIN`
   ist das Live-Theme, und jede andere Rolle (DEVELOPMENT, DEMO, LOCKED,
   ARCHIVED) ist nicht unser Entwurf.
3. Das Live-Theme wird vorher und nachher gelesen. Ändert sich sein
   `updatedAt` oder wechselt das Live-Theme, bricht der Lauf ab und meldet es:
   dann arbeitet jemand parallel am Shop, und der Abgleich ist hinfällig.

Veröffentlichen gibt es in diesem Paket nicht; `themePublish` wird nirgends
aufgerufen.
"""
from theme.files import get_theme, list_themes, live_theme
from theme.shopify import ShopifyError, numeric_id, theme_gid


class GuardError(RuntimeError):
    """Das Schreiben wurde verweigert oder ist abgebrochen."""


def check_write_target(transport, theme_id, expected_draft_id) -> dict:
    """Prüft das Ziel frisch; gibt seinen Zustand zurück oder wirft `GuardError`."""
    if not expected_draft_id:
        raise GuardError("theme_migration.draft_theme_id ist nicht gesetzt; ohne sie wird nicht geschrieben")
    try:
        if numeric_id(theme_id) != numeric_id(expected_draft_id):
            raise GuardError(f"Ziel {numeric_id(theme_id)} ist nicht der Entwurf {numeric_id(expected_draft_id)}")
    except ShopifyError as exc:
        raise GuardError(str(exc)) from exc
    theme = get_theme(transport, theme_id)
    if not theme:
        raise GuardError(f"Theme {numeric_id(theme_id)} gibt es im Store nicht")
    role = theme.get("role")
    if role == "MAIN":
        raise GuardError(f"Theme {numeric_id(theme_id)} ist das Live-Theme (MAIN); dorthin wird nie geschrieben")
    if role != "UNPUBLISHED":
        raise GuardError(f"Theme {numeric_id(theme_id)} hat die Rolle {role}, geschrieben wird nur in UNPUBLISHED")
    if theme.get("id") and theme_gid(theme["id"]) != theme_gid(theme_id):
        raise GuardError("Shopify hat ein anderes Theme geliefert als angefragt")
    return theme


def live_fingerprint(transport) -> dict:
    """ID, Name und `updatedAt` des Live-Themes, frisch gelesen."""
    try:
        main = live_theme(list_themes(transport))
    except ShopifyError as exc:
        raise GuardError(f"Live-Theme nicht lesbar: {exc}") from exc
    return {"id": main.get("id"), "name": main.get("name"), "updated_at": main.get("updatedAt")}


def assert_live_unchanged(before: dict, after: dict) -> None:
    """Bricht ab, wenn das Live-Theme gewechselt oder geändert wurde."""
    if before.get("id") != after.get("id"):
        raise GuardError(f"Das Live-Theme hat gewechselt: {before.get('id')} zu {after.get('id')}")
    if before.get("updated_at") != after.get("updated_at"):
        raise GuardError(f"Das Live-Theme wurde während des Laufs geändert "
                         f"({before.get('updated_at')} zu {after.get('updated_at')})")


def guarded(transport, theme_id, expected_draft_id, write_fn):
    """Führt `write_fn()` unter allen drei Regeln aus und gibt `(ergebnis, protokoll)` zurück."""
    before = live_fingerprint(transport)
    target = check_write_target(transport, theme_id, expected_draft_id)
    result = write_fn()
    after = live_fingerprint(transport)
    assert_live_unchanged(before, after)
    return result, {"live_before": before, "live_after": after, "target": target}
