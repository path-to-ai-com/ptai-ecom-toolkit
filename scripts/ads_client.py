#!/usr/bin/env python3
"""REST-Client für die Google Ads API (GoogleAdsService.Search).

Dieselbe Bauweise wie dfs_client.py: eine injizierbare Transport-Funktion,
alles darüber rein und getestet. Hier aus einem anderen Grund als Geld: beim
Bau gab es keinen API-Zugang, also keine Möglichkeit, gegen die echte API zu
entwickeln. Die Fixtures sind aus der REST-Referenz gebaut, siehe
`scripts/tests/fixtures/ads/HERKUNFT.md`.

Zugriff läuft über dasselbe Dienstkonto wie GA4 und GSC, mit dem Scope
`https://www.googleapis.com/auth/adwords`. Dafür braucht es zwei Dinge, und
nur eines davon gibt der Kunde:

- Der **Betreiber** aktiviert die Google Ads API im Cloud-Projekt, dem das
  Dienstkonto gehört, und beantragt dort mindestens die Zugriffsstufe Explorer.
  Auf der Teststufe antwortet jedes echte Konto mit
  CLOUD_PROJECT_NOT_APPROVED_FOR_PRODUCTION.
- Der **Kunde** trägt die Dienstkonto-Mail als Nutzer mit "Nur Lesen" im
  Werbekonto ein. Eine Personenadresse reicht nicht, die API läuft über das
  Dienstkonto.

Ein Entwicklertoken gibt es nicht mehr. Google hat es am 09.09.2026
abgeschafft, die Zugriffsstufe hängt seitdem am Cloud-Projekt. Der Header
`developer-token` wird ignoriert und soll in einer späteren Version abgelehnt
werden, deshalb sendet dieser Client ihn nicht.

Beträge kommen als Micros (millionstel Währungseinheit) und werden hier
umgerechnet. Die Währung steht in `customer.currency_code` und wird vom Pull
mitgezogen: ein Betrag ohne Währung ist keine Zahl, sondern eine Behauptung.

Nur Standardbibliothek plus google-auth über den geteilten Token-Helfer.
"""
import json
import urllib.error
import urllib.request

BASE = "https://googleads.googleapis.com"

#: Die eingesetzte API-Version. Google stellt Versionen nach rund einem Jahr
#: ab, eine abgestellte antwortet mit einer nackten 404. Am 02.10.2026 lief v21
#: schon nicht mehr, v22 bis v25 antworteten, v26 gab es noch nicht.
#: `--api-version` übersteuert den Wert.
DEFAULT_VERSION = "v25"

DEFAULT_TIMEOUT = 120


class AdsError(RuntimeError):
    """Ein Aufruf gegen die Google Ads API ist gescheitert."""


def from_micros(value):
    """Micros in Währungseinheiten, auf Cent gerundet. `None` bleibt `None`.

    `None` und `0` sind zwei Aussagen: "kein Wert geliefert" gegen "null
    ausgegeben". Eine 0 an der Stelle stünde im Report als Tatsache. Ein Wert,
    der sich nicht lesen lässt, wird ebenfalls `None` und nicht 0.
    """
    if value is None:
        return None
    try:
        return round(int(value) / 1_000_000, 2)
    except (TypeError, ValueError):
        return None


def _strip(customer_id) -> str:
    """Google Ads zeigt die Kundennummer mit Bindestrichen, die API nimmt sie
    ohne. Ein Copy-Paste aus der Oberfläche scheitert sonst mit einer
    nichtssagenden 400."""
    return str(customer_id).replace("-", "").strip()


def _real_transport(url, headers, body, timeout):
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def _describe_http_error(exc: urllib.error.HTTPError) -> str:
    """Status plus Googles eigene Begründung aus dem Fehlerkörper.

    Die oberste Meldung einer 403 lautet bei Google Ads fast immer "The caller
    does not have permission" und sagt nicht, wessen Seite fehlt. Der Grund
    steckt in `details[].errors[]`: CLOUD_PROJECT_NOT_APPROVED_FOR_PRODUCTION
    heißt, der Betreiber muss eine Zugriffsstufe beantragen, USER_PERMISSION_DENIED
    heißt, der Kunde hat das Dienstkonto nicht eingetragen. Ohne diese Zeile
    stand am 02.10.2026 nur "HTTP 403" da, für zwei Ursachen auf zwei Seiten.
    """
    text = f"HTTP {exc.code}"
    try:
        body = json.loads(exc.read().decode("utf-8", errors="replace"))
    except Exception:
        return text
    error = body.get("error") or {}
    reasons = []
    for detail in error.get("details") or []:
        for item in detail.get("errors") or []:
            code = next(iter((item.get("errorCode") or {}).values()), None)
            message = item.get("message")
            reasons.append(": ".join(part for part in (code, message) if part))
    if not reasons and error.get("message"):
        reasons.append(error["message"])
    return f"{text}, {'; '.join(reasons)}" if reasons else text


class Client:
    def __init__(self, customer_id, *, access_token,
                 login_customer_id=None, version=DEFAULT_VERSION,
                 transport=None, timeout=DEFAULT_TIMEOUT):
        self.customer_id = _strip(customer_id)
        self.version = version
        self.timeout = timeout
        self._transport = transport or _real_transport
        self._headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        if login_customer_id:
            self._headers["login-customer-id"] = _strip(login_customer_id)

    @property
    def url(self) -> str:
        return f"{BASE}/{self.version}/customers/{self.customer_id}/googleAds:search"

    def search(self, query: str) -> list:
        """Alle Zeilen einer GAQL-Abfrage, über alle Seiten hinweg.

        Die Query geht auf jeder Folgeseite unverändert mit: die API verlangt
        das zum Seitentoken und antwortet sonst mit einem Fehler statt mit der
        nächsten Seite.
        """
        rows, page_token = [], None
        while True:
            payload = {"query": query}
            if page_token:
                payload["pageToken"] = page_token
            body = json.dumps(payload).encode("utf-8")
            try:
                raw = self._transport(self.url, dict(self._headers), body, self.timeout)
            except urllib.error.HTTPError as exc:
                raise AdsError(f"Google Ads: {_describe_http_error(exc)}") from exc
            except (urllib.error.URLError, OSError) as exc:
                raise AdsError(f"Google Ads nicht erreichbar: {exc}") from exc
            try:
                answer = json.loads(raw.decode("utf-8", errors="replace"))
            except (json.JSONDecodeError, ValueError) as exc:
                raise AdsError(f"Google Ads: ungültige JSON-Antwort ({exc})") from exc
            rows.extend(answer.get("results") or [])
            page_token = answer.get("nextPageToken")
            if not page_token:
                return rows
