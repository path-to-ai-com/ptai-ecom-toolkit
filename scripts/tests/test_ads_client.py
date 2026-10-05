"""Der Google-Ads-Client: Header, Paging, Micros, Fehler.

Kein Test ruft die API: beim Bau dieser Tests gab es keinen API-Zugang. Die
Fixtures sind von Hand aus der REST-Referenz gebaut, siehe
fixtures/ads/HERKUNFT.md. Sie beweisen, dass der Code die dokumentierte
Struktur richtig liest, nicht dass die echte Antwort so aussieht.
"""
import io
import json
import unittest
import urllib.error
from pathlib import Path

import ads_client

FIX = Path(__file__).parent / "fixtures" / "ads"


def pages(*names):
    """Ein Transport, der die Fixtures der Reihe nach liefert."""
    queue = [(FIX / name).read_bytes() for name in names]
    seen = []

    def transport(url, headers, body, timeout):
        seen.append({"url": url, "headers": headers, "body": json.loads(body)})
        return queue.pop(0)

    return transport, seen


class TestHeaders(unittest.TestCase):
    def test_bearer_is_sent(self):
        transport, seen = pages("campaigns_page2.json")
        ads_client.Client("1234567890", access_token="ya29.x",
                           transport=transport).search("SELECT campaign.id FROM campaign")
        self.assertEqual(seen[0]["headers"]["Authorization"], "Bearer ya29.x")

    def test_no_developer_token_header(self):
        # Google hat das Entwicklertoken am 09.09.2026 abgeschafft. Der Header
        # wird ignoriert und soll in einer späteren Version abgelehnt werden.
        transport, seen = pages("campaigns_page2.json")
        ads_client.Client("123", access_token="a", transport=transport).search("q")
        self.assertNotIn("developer-token", seen[0]["headers"])

    def test_login_customer_id_is_omitted_when_not_given(self):
        transport, seen = pages("campaigns_page2.json")
        ads_client.Client("123", access_token="a", transport=transport).search("q")
        self.assertNotIn("login-customer-id", seen[0]["headers"])

    def test_login_customer_id_is_sent_when_given(self):
        transport, seen = pages("campaigns_page2.json")
        ads_client.Client("123", access_token="a", login_customer_id="999-888-7777",
                           transport=transport).search("q")
        self.assertEqual(seen[0]["headers"]["login-customer-id"], "9998887777")

    def test_customer_id_dashes_are_stripped(self):
        # Google Ads zeigt die Kundennummer mit Bindestrichen an, die API
        # nimmt sie nicht. Ein Copy-Paste aus der Oberfläche scheiterte sonst
        # mit einer nichtssagenden 400.
        transport, seen = pages("campaigns_page2.json")
        ads_client.Client("123-456-7890", access_token="a",
                           transport=transport).search("q")
        self.assertIn("/customers/1234567890/", seen[0]["url"])

    def test_url_carries_the_api_version(self):
        transport, seen = pages("campaigns_page2.json")
        ads_client.Client("123", access_token="a", version="v21",
                           transport=transport).search("q")
        self.assertIn("/v21/", seen[0]["url"])

    def test_default_version_is_a_constant_not_a_guess(self):
        # Google stellt Versionen nach rund einem Jahr ab. Der Wert steht als
        # Konstante und ist per Schalter uebersteuerbar.
        self.assertRegex(ads_client.DEFAULT_VERSION, r"^v\d+$")


class TestPaging(unittest.TestCase):
    def test_follows_the_next_page_token(self):
        transport, seen = pages("campaigns_page1.json", "campaigns_page2.json")
        rows = ads_client.Client("123", access_token="a",
                                  transport=transport).search("SELECT campaign.id FROM campaign")
        self.assertEqual(len(rows), 3)
        self.assertEqual(seen[1]["body"]["pageToken"], "PAGE2")

    def test_repeats_the_identical_query_on_the_next_page(self):
        # Die API verlangt dieselbe Query zum Token, sonst antwortet sie mit
        # einem Fehler statt mit der naechsten Seite.
        transport, seen = pages("campaigns_page1.json", "campaigns_page2.json")
        ads_client.Client("123", access_token="a", transport=transport).search("Q")
        self.assertEqual(seen[0]["body"]["query"], seen[1]["body"]["query"])

    def test_first_page_carries_no_token(self):
        transport, seen = pages("campaigns_page2.json")
        ads_client.Client("123", access_token="a", transport=transport).search("q")
        self.assertNotIn("pageToken", seen[0]["body"])

    def test_stops_without_a_token(self):
        transport, seen = pages("campaigns_page2.json")
        ads_client.Client("123", access_token="a", transport=transport).search("q")
        self.assertEqual(len(seen), 1)


class TestValues(unittest.TestCase):
    def test_micros_become_currency_units(self):
        self.assertAlmostEqual(ads_client.from_micros("450000000"), 450.0)

    def test_micros_none_stays_none(self):
        # 0 und "kein Wert" sind zwei Aussagen. Eine 0 stuende im Report als
        # "nichts ausgegeben".
        self.assertIsNone(ads_client.from_micros(None))

    def test_micros_are_rounded_to_cents(self):
        self.assertAlmostEqual(ads_client.from_micros("1234567"), 1.23)

    def test_micros_zero_is_zero_not_none(self):
        self.assertEqual(ads_client.from_micros("0"), 0.0)

    def test_unreadable_micros_are_none_not_zero(self):
        self.assertIsNone(ads_client.from_micros("keine Zahl"))


class TestErrors(unittest.TestCase):
    def test_transport_failure_is_wrapped(self):
        def failing(url, headers, body, timeout):
            raise OSError("connection reset")
        with self.assertRaises(ads_client.AdsError) as caught:
            ads_client.Client("123", access_token="a", transport=failing).search("q")
        self.assertIn("connection reset", str(caught.exception))

    def test_invalid_json_is_wrapped(self):
        def broken(url, headers, body, timeout):
            return b"not json"
        with self.assertRaises(ads_client.AdsError):
            ads_client.Client("123", access_token="a", transport=broken).search("q")

    def test_http_error_carries_the_code(self):
        def failing(url, headers, body, timeout):
            raise urllib.error.HTTPError("u", 401, "Unauthorized", {}, None)
        with self.assertRaises(ads_client.AdsError) as caught:
            ads_client.Client("123", access_token="a", transport=failing).search("q")
        self.assertIn("401", str(caught.exception))

    def test_http_error_names_googles_reason(self):
        # Die oberste Meldung einer 403 sagt nicht, wessen Seite fehlt. Der
        # Grund steht in details[].errors[] und muss bis in die Fehlerzeile.
        body = json.dumps({"error": {
            "code": 403, "message": "The caller does not have permission",
            "details": [{"errors": [{
                "errorCode": {"authorizationError": "CLOUD_PROJECT_NOT_APPROVED_FOR_PRODUCTION"},
                "message": "The Google Cloud project is only approved for use with test accounts."}]}],
        }}).encode()

        def failing(url, headers, body_, timeout):
            raise urllib.error.HTTPError("u", 403, "Forbidden", {}, io.BytesIO(body))
        with self.assertRaises(ads_client.AdsError) as caught:
            ads_client.Client("123", access_token="a", transport=failing).search("q")
        text = str(caught.exception)
        self.assertIn("403", text)
        self.assertIn("CLOUD_PROJECT_NOT_APPROVED_FOR_PRODUCTION", text)
        self.assertIn("test accounts", text)

    def test_http_error_without_details_keeps_the_top_message(self):
        body = json.dumps({"error": {"code": 404, "message": "Method not found."}}).encode()

        def failing(url, headers, body_, timeout):
            raise urllib.error.HTTPError("u", 404, "Not Found", {}, io.BytesIO(body))
        with self.assertRaises(ads_client.AdsError) as caught:
            ads_client.Client("123", access_token="a", transport=failing).search("q")
        self.assertIn("Method not found.", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
