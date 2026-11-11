"""Testbestellung: Kauf-Aufrufe je Ziel, Ziele des Shops, Bestellung und GA4-Bericht, Kassen-Durchlauf."""
import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "browser"))
sys.path.insert(0, str(ROOT / "skills" / "capture-screens" / "scripts"))

import consent  # noqa: E402
import walk_checkout  # noqa: E402
from theme import test_order as to  # noqa: E402

GA4_BATCH = ("en=page_view&dl=https%3A%2F%2Fbeispielshop.example%2Fthank-you\n"
             "en=purchase&ep.transaction_id=%231001&epn.value=49.9&cu=EUR")


def req(url, stage="thank_you", status=204, post=None, failure=None):
    return {"url": url, "stage": stage, "status": status, "post_data": post, "failure": failure, "method": "POST"}


class TestKaufAufrufe(unittest.TestCase):
    def test_ga4_purchase_aus_einem_gebuendelten_post(self):
        hits = to.parse_hits(req("https://region1.google-analytics.com/g/collect?v=2&tid=G-BEISPIEL1", post=GA4_BATCH))
        self.assertEqual(len(hits), 1, "page_view im selben POST zählt nicht")
        hit = hits[0]
        self.assertEqual((hit["service"], hit["id"], hit["transaction"], hit["value"], hit["currency"]),
                         ("google_analytics", "G-BEISPIEL1", "#1001", "49.9", "EUR"))
        self.assertTrue(hit["delivered"])

    def test_google_ads_conversion_braucht_ein_label(self):
        conversion = to.parse_hits(req("https://www.googleadservices.com/pagead/conversion/123456789/"
                                       "?label=AbCdEf&value=49.9&currency_code=EUR&oid=1001", status=200))
        self.assertEqual((conversion[0]["service"], conversion[0]["id"], conversion[0]["label"],
                          conversion[0]["transaction"]), ("google_ads", "123456789", "AbCdEf", "1001"))
        remarketing = to.parse_hits(req("https://www.googleadservices.com/pagead/conversion/123456789/?random=1"))
        self.assertEqual(remarketing, [], "ohne label ist es Remarketing")
        first_party = to.parse_hits(req("https://www.google.com/pagead/1p-conversion/123456789/?label=AbCdEf"))
        self.assertTrue(first_party[0]["first_party"])
        self.assertEqual(to.repeated(conversion + first_party), [], "die Erstanbieter-Kopie ist keine Doppelung")
        self.assertEqual(to.repeated(conversion + conversion)[0][1], 2)

    def test_meta_purchase_get_und_post(self):
        get = to.parse_hits(req("https://www.facebook.com/tr/?id=1234&ev=Purchase&cd[value]=49.9&cd[currency]=EUR"))
        self.assertEqual((get[0]["service"], get[0]["id"], get[0]["value"]), ("meta", "1234", "49.9"))
        self.assertEqual(to.parse_hits(req("https://www.facebook.com/tr/?id=1234&ev=PageView")), [])
        post = to.parse_hits(req("https://www.facebook.com/tr/", post="id=1234&ev=Purchase&eid=abc"))
        self.assertEqual(post[0]["event_id"], "abc")

    def test_tiktok_microsoft_pinterest(self):
        tiktok = to.parse_hits(req("https://analytics.tiktok.com/api/v2/pixel",
                                   post=json.dumps({"event": "CompletePayment", "pixel_code": "C0DE"})))
        self.assertEqual((tiktok[0]["service"], tiktok[0]["id"]), ("tiktok", "C0DE"))
        bing = to.parse_hits(req("https://bat.bing.com/action/0?ti=999&evt=custom&ea=purchase&gv=49.9&gc=EUR"))
        self.assertEqual((bing[0]["service"], bing[0]["value"]), ("microsoft_ads", "49.9"))
        self.assertEqual(to.parse_hits(req("https://bat.bing.com/action/0?ti=999&evt=pageLoad")), [])
        pin = to.parse_hits(req("https://ct.pinterest.com/v3/?event=checkout&tid=2612"))
        self.assertEqual(pin[0]["service"], "pinterest")

    def test_nur_ab_der_uebergabe_und_gescheiterte_aufrufe_erkennbar(self):
        requests = [req("https://www.facebook.com/tr/?id=1&ev=Purchase", stage="cart"),
                    req("https://www.facebook.com/tr/?id=1&ev=Purchase", stage="handoff", status=None, failure="net::ERR")]
        hits = to.purchase_hits(requests)
        self.assertEqual(len(hits), 1, "ein Aufruf im Warenkorb ist kein Kauf")
        self.assertFalse(hits[0]["delivered"])
        self.assertIn("gescheitert", to.describe_hit(hits[0]))


class TestZiele(unittest.TestCase):
    def test_aus_bestandsaufnahme_ohne_gestrichenes_und_ga4_ueber_den_connector(self):
        used = {"google_analytics": "apps.json", "google_ads": "apps.json", "meta": "apps.json"}
        found = to.derive_destinations(None, used, {"meta": "Meta: drop"}, {"littledata": "Littledata"})
        self.assertEqual([d["id"] for d in found], ["google_analytics", "google_ads"])
        self.assertEqual(found[0]["via"], "Littledata")
        self.assertIsNone(found[1]["via"], "der Connector sendet nur GA4")

    def test_config_gewinnt(self):
        configured = to.configured_destinations({"meta": {"via": "Conversions-API"}, "unbekannt": {}})
        found = to.derive_destinations(configured, {"google_ads": "apps.json"}, {}, {})
        self.assertEqual([(d["id"], d["via"]) for d in found], [("meta", "Conversions-API")])
        self.assertEqual(to.configured_destinations(["google_ads"]), {"google_ads": {}})
        self.assertIsNone(to.configured_destinations(None))


class FakeTransport:
    def __init__(self, nodes):
        self.nodes, self.calls = nodes, []

    def execute(self, query, variables=None, *, mutation=False):
        self.calls.append((query, variables, mutation))
        return {"orders": {"nodes": self.nodes}}


class TestBestellungUndGa4(unittest.TestCase):
    def test_bestellung_ueber_das_warenkorb_attribut(self):
        nodes = [{"id": "gid://shopify/Order/1", "name": "#1000", "customAttributes": []},
                 {"id": "gid://shopify/Order/2", "name": "#1001",
                  "customAttributes": [{"key": to.TOKEN_KEY, "value": "lc-abc"}]}]
        transport = FakeTransport(nodes)
        since = datetime(2026, 11, 12, 9, 50, tzinfo=timezone.utc)
        order = to.find_order(transport, "lc-abc", since)
        self.assertEqual(order["name"], "#1001")
        self.assertEqual(transport.calls[0][1], {"query": "created_at:>='2026-11-12T09:50:00Z'"})
        self.assertFalse(transport.calls[0][2], "nur lesend")
        self.assertIsNone(to.find_order(transport, "lc-anders", since))
        self.assertEqual(to.order_candidates(order, [{"transaction": "1001"}, {"transaction": "X9"}]),
                         ["#1001", "1001", "2", "X9"])

    def test_ga4_bericht_und_echtzeit(self):
        calls = []

        def post(url, token, body):
            calls.append((url, token, body))
            if url.endswith(":runRealtimeReport"):
                return {"rows": [{"dimensionValues": [{"value": "purchase"}], "metricValues": [{"value": "3"}]}]}
            return {"rows": [{"dimensionValues": [{"value": "#1001"}],
                              "metricValues": [{"value": "2"}, {"value": "99.8"}]}],
                    "metadata": {"currencyCode": "EUR"}}

        reader = to.GA4Reader("123456", lambda: "token", post=post)
        data = reader.transactions(["#1001", "1001"], "2026-11-11")
        self.assertEqual(data, {"rows": [{"transaction": "#1001", "purchases": 2, "revenue": 99.8}], "currency": "EUR"})
        body = calls[0][2]
        self.assertEqual(body["dimensionFilter"]["filter"]["inListFilter"]["values"], ["#1001", "1001"])
        self.assertEqual(body["metrics"][0]["name"], "ecommercePurchases", "nie transactions, die zählt Erstattungen")
        self.assertEqual(reader.realtime_purchases(90), 3)
        self.assertEqual(calls[1][2]["minuteRanges"][0]["startMinutesAgo"], 29, "Echtzeit reicht 29 Minuten zurück")
        self.assertIn("properties/123456:runReport", calls[0][0])

    def test_ohne_property_kein_zugang_statt_absturz(self):
        reader, reason = to.ga4_from_config({}, ".")
        self.assertIsNone(reader)
        self.assertIn("ga4_property_id", reason)


class TestDurchlauf(unittest.TestCase):
    def test_hinweise_dankeseite_und_produktseite(self):
        self.assertIn("MwSt", walk_checkout.find_notice("Gesamt 49,90 € inkl. 19 % MwSt. zzgl. Versand",
                                                        walk_checkout.TAX_NOTICE))
        self.assertIsNone(walk_checkout.find_notice("Gesamt 49,90 €", walk_checkout.TAX_NOTICE))
        self.assertIsNotNone(walk_checkout.find_notice("Versand wird an der Kasse berechnet",
                                                       walk_checkout.SHIPPING_NOTICE))
        self.assertTrue(walk_checkout.is_thank_you("https://beispielshop.example/checkouts/cn/abc/thank-you"))
        self.assertTrue(walk_checkout.is_thank_you("https://beispielshop.example/1/checkouts/abc/thank_you"))
        self.assertFalse(walk_checkout.is_thank_you("https://beispielshop.example/checkouts/cn/abc"))
        self.assertEqual(walk_checkout.order_text("Danke!\nBestellung #1001 bestätigt"), "Bestellung #1001")
        pages = {"pages": [{"id": "home", "path": "/"}, {"id": "product", "template": "product", "path": "/products/a"}]}
        self.assertEqual(walk_checkout.pick_product_path(pages, None), "/products/a")
        self.assertEqual(walk_checkout.pick_product_path(pages, "/products/b"), "/products/b")
        self.assertTrue(walk_checkout.make_token().startswith("lc-"))


class FakeLocator:
    def __init__(self, page, key):
        self.page, self.key = page, key

    def count(self):
        return 1 if self.key in self.page.visible else 0

    @property
    def first(self):
        return self

    def nth(self, index):
        return self

    def is_visible(self):
        return self.key in self.page.visible

    def click(self, timeout=None):
        self.page.clicks.append(self.key)
        self.page.visible = set()


class FakePage:
    def __init__(self, visible, cookiefirst=False):
        self.visible, self.cookiefirst, self.clicks, self.calls = set(visible), cookiefirst, [], []

    def wait_for_selector(self, selector, state=None, timeout=None):
        raise TimeoutError

    def locator(self, selector):
        return FakeLocator(self, selector.replace(" >> visible=true", ""))

    def get_by_text(self, text, exact=False):
        return FakeLocator(self, text)

    def wait_for_timeout(self, ms):
        pass

    def evaluate(self, script):
        self.calls.append(script)
        if "Boolean(" in script:
            return self.cookiefirst
        return None


class TestEinwilligung(unittest.TestCase):
    def test_pandectes_wird_ueber_seinen_knopf_angenommen(self):
        page = FakePage({".cc-btn.cc-allow", "Das ist O.K.", "Einstellungen"})
        self.assertEqual(consent.accept(page, wait_ms=0), (consent.ACCEPTED, ".cc-btn.cc-allow"))

    def test_cookiefirst_ueber_die_api_wenn_kein_knopf_sichtbar_ist(self):
        page = FakePage(set(), cookiefirst=True)
        marks = []
        self.assertEqual(consent.accept(page, wait_ms=0, before_click=lambda: marks.append(1)),
                         (consent.ACCEPTED, "CookieFirst.acceptAllCategories()"))
        self.assertIn("acceptAllCategories()", page.calls[-1])
        self.assertEqual(marks, [1], "der Mitschnitt trennt vorher und nachher auch beim API-Weg")

    def test_ohne_dialog_und_ohne_api_kein_zugestimmt(self):
        self.assertEqual(consent.accept(FakePage(set()), wait_ms=0), (consent.NO_DIALOG, None))


if __name__ == "__main__":
    unittest.main()
