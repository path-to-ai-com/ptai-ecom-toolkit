"""Den Cookie-Dialog eines Shops ablehnen, für Aufnahmen ohne Dialog.

Gemeinsam für `shoot_declined.py` (Übersichtsaufnahmen) und `shoot_proof.py`
(Belegbilder zu Befunden). "Ablehnen" ist die Wahl, die am wenigsten Daten
freigibt.

**Drei Wege, in dieser Reihenfolge.** Zuerst die bekannten Knöpfe der
verbreiteten Consent-Tools, dann ein Knopf mit einem üblichen Ablehnen-Text auf
der ersten Ebene, zuletzt die zweite Ebene: erst "Nein, anpassen" oder
"Einstellungen", dann dort "Ablehnen". Den dritten Weg braucht etwa ein Dialog,
der auf der ersten Ebene nur "Alle akzeptieren" und "Nein, anpassen" anbietet;
belegt am 02.10.2026 an einem Shop, dessen Audit genau das als Befund hatte.

Die zweite Ebene wird nur versucht, wenn auf der Seite sichtbar ein
Zustimmen-Knopf steht. Sonst träfe "Einstellungen" leicht einen Link im Footer.
"""
from __future__ import annotations

# Ablehnen-Knöpfe der verbreiteten Consent-Tools, in dieser Reihenfolge versucht.
DECLINE_SELECTORS = [
    "#CybotCookiebotDialogBodyButtonDecline",          # Cookiebot
    "#onetrust-reject-all-handler",                     # OneTrust
    "button[data-testid='uc-deny-all-button']",         # Usercentrics
    ".cmplz-deny",                                      # Complianz
    "button.sp_choice_type_REJECT_ALL",                 # Sourcepoint
    "[data-cookiefirst-action='reject']",               # CookieFirst
    "#shopify-pc__banner__btn-decline",                 # Shopify Customer Privacy
    "[data-cky-tag='reject-button']",                   # CookieYes
    ".cky-btn-reject",                                  # CookieYes, ältere Fassung
]

#: Texte eines Ablehnen-Knopfs, auf der ersten wie auf der zweiten Ebene.
DECLINE_TEXTS = (
    "Alle ablehnen", "Ablehnen", "Nur notwendige Cookies", "Nur notwendige",
    "Nur erforderliche Cookies", "Nur essenzielle Cookies", "Reject all", "Decline",
)

#: Texte eines Zustimmen-Knopfs. Steht einer sichtbar da, ist ein Dialog offen.
ACCEPT_TEXTS = (
    "Alle akzeptieren", "Akzeptieren", "Alle zulassen", "Zustimmen", "Alle annehmen",
    "Accept all", "Accept",
)

#: Texte, die die zweite Ebene eines Dialogs öffnen.
SECOND_LEVEL_TEXTS = (
    "Nein, anpassen", "Anpassen", "Einstellungen", "Cookie-Einstellungen",
    "Individuelle Einstellungen", "Mehr Optionen", "Optionen verwalten", "Customize", "Settings",
)

#: Zustimmen-Knöpfe derselben Tools. Nur für einen Mitschnitt mit Einwilligung,
#: den das Team freigegeben hat (`scripts/browser/capture_network.py --consent
#: accepted`); jede Aufnahme ohne diese Freigabe lehnt ab.
ACCEPT_SELECTORS = [
    "#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll",  # Cookiebot
    "#onetrust-accept-btn-handler",                     # OneTrust
    "button[data-testid='uc-accept-all-button']",       # Usercentrics
    ".cmplz-accept",                                    # Complianz
    "[data-cookiefirst-action='accept']",               # CookieFirst
    "#shopify-pc__banner__btn-accept",                  # Shopify Customer Privacy
    "[data-cky-tag='accept-button']",                   # CookieYes
    ".cky-btn-accept",                                  # CookieYes, ältere Fassung
]

DECLINED = "declined"
ACCEPTED = "accepted"
NO_DIALOG = "no_dialog"
STUCK = "stuck"


def visible_text(page, text: str):
    """Der erste sichtbare Treffer für genau diesen Text, oder `None`."""
    candidates = page.get_by_text(text, exact=True)
    for index in range(candidates.count()):
        candidate = candidates.nth(index)
        try:
            if candidate.is_visible():
                return candidate
        except Exception:
            continue
    return None


def click_first(page, texts, before_click=None) -> str | None:
    """Klickt den ersten sichtbaren Treffer aus `texts` und nennt den Text."""
    for text in texts:
        target = visible_text(page, text)
        if target is None:
            continue
        try:
            if before_click:
                before_click()
            target.click(timeout=5000)
        except Exception:
            continue
        page.wait_for_timeout(1200)
        return text
    return None


def dialog_open(page) -> bool:
    return any(visible_text(page, text) is not None for text in ACCEPT_TEXTS)


def decline(page, wait_ms: int = 6000, before_click=None) -> tuple[str, str | None]:
    """Lehnt den Cookie-Dialog ab.

    `before_click` wird unmittelbar vor jedem Klick aufgerufen; der Mitschnitt
    trennt damit Anfragen vor und nach der Entscheidung.

    Rückgabe ist der Zustand und, bei `declined`, der Weg dorthin:
    `("declined", "#onetrust-reject-all-handler")`, `("declined", "Nein,
    anpassen > Ablehnen")`, `("no_dialog", None)` oder `("stuck", None)`, wenn ein
    Dialog offen ist und sich nicht ablehnen ließ.
    """
    # Die Dialoge kommen per Skript, oft Sekunden nach dem load-Ereignis.
    try:
        page.wait_for_selector(", ".join(DECLINE_SELECTORS), state="visible", timeout=wait_ms)
    except Exception:
        pass
    for selector in DECLINE_SELECTORS:
        # Manche Tools rendern den Knopf doppelt (Banner und Einstellungen); geklickt wird der sichtbare.
        button = page.locator(f"{selector} >> visible=true").first
        try:
            if button.count():
                if before_click:
                    before_click()
                button.click(timeout=5000)
                page.wait_for_timeout(1200)
                return DECLINED, selector
        except Exception:
            continue

    if not dialog_open(page):
        return NO_DIALOG, None

    first = click_first(page, DECLINE_TEXTS, before_click)
    if first and not dialog_open(page):
        return DECLINED, first

    opener = click_first(page, SECOND_LEVEL_TEXTS, before_click)
    if opener:
        second = click_first(page, DECLINE_TEXTS, before_click)
        if second and not dialog_open(page):
            return DECLINED, f"{opener} > {second}"
    return STUCK, None


def accept(page, wait_ms: int = 6000, before_click=None) -> tuple[str, str | None]:
    """Stimmt dem Cookie-Dialog zu, das Gegenstück zu `decline`.

    Nur für einen Mitschnitt mit Einwilligung, den das Team freigegeben hat.
    Rückgabe wie bei `decline`: `("accepted", "<Selektor oder Text>")`,
    `("no_dialog", None)` oder `("stuck", None)`.
    """
    try:
        page.wait_for_selector(", ".join(ACCEPT_SELECTORS), state="visible", timeout=wait_ms)
    except Exception:
        pass
    for selector in ACCEPT_SELECTORS:
        button = page.locator(f"{selector} >> visible=true").first
        try:
            if button.count():
                if before_click:
                    before_click()
                button.click(timeout=5000)
                page.wait_for_timeout(1200)
                return ACCEPTED, selector
        except Exception:
            continue
    if not dialog_open(page):
        return NO_DIALOG, None
    clicked = click_first(page, ACCEPT_TEXTS, before_click)
    if clicked and not dialog_open(page):
        return ACCEPTED, clicked
    return STUCK, None
