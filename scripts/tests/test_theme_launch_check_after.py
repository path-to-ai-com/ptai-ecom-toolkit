"""Launch-Check nach dem Veröffentlichen: Testbestellung je Ziel und Tracking nach Einwilligung."""
import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from tests import test_theme_launch_check as base  # noqa: E402
from tests import theme_fake_shop as fake  # noqa: E402
from theme import launch_check as lc  # noqa: E402
from theme import test_order as to  # noqa: E402

RUN = "2026-10-06-launch-check"
TOKEN = "lc-0a1b2c3d4e5f"
GA4_HIT = ("https://region1.google-analytics.com/g/collect?v=2&tid=G-BEISPIEL1",
           "en=purchase&ep.transaction_id=%231001&epn.value=49.9&cu=EUR")
ADS_HIT = "https://www.googleadservices.com/pagead/conversion/123456789/?label=AbCdEf&value=49.9&oid=1001"
META_HIT = "https://www.facebook.com/tr/?id=1234&ev=Purchase&cd[value]=49.9&cd[currency]=EUR"
GA4_PAGE = "https://region1.google-analytics.com/g/collect?v=2"
ADS_PAGE = "https://googleads.g.doubleclick.net/pagead/viewthroughconversion/123456789/"


def iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def stages(cart_tax="inkl. 19 % MwSt.", contact=False) -> list:
    out = [{"stage": "product", "state": "ok", "evidence": "/products/beispielring antwortet 200"},
           {"stage": "consent", "state": "ok", "evidence": "accepted"},
           {"stage": "add_to_cart", "state": "ok", "evidence": "1 Artikel im Warenkorb über Knopf des Themes"},
           {"stage": "mark", "state": "ok", "evidence": "gesetzt"},
           {"stage": "cart", "state": "ok", "evidence": "1 Artikel auf /cart", "screenshot": "05-cart.png",
            "notices": {"tax": cart_tax, "shipping": "zzgl. Versand"}},
           {"stage": "checkout", "state": "ok", "evidence": "Kasse geöffnet", "screenshot": "06-checkout.png",
            "notices": {"tax": "Inklusive 7,97 € MwSt.", "shipping": "Versand", "payment": "Zahlung"}}]
    if contact:
        out.append({"stage": "shipping", "state": "ok", "evidence": "Versandarten: Standard 4,90 €"})
    else:
        out.append({"stage": "shipping", "state": "skipped", "evidence": "keine Testadresse (--contact)"})
    out.append({"stage": "payment", "state": "skipped", "evidence": "Zahlungsbereich noch nicht sichtbar"})
    return out


class AfterShop(base.LaunchShop):
    orders: list = []

    def op_LaunchCheckTestOrder(self, variables):
        return {"orders": {"nodes": self.orders}}


class FakeGA4:
    prop = "123456"

    def __init__(self, rows=None, realtime=0, error=None):
        self.rows, self.realtime, self.error, self.calls = rows or [], realtime, error, []

    def transactions(self, candidates, start, end="today"):
        self.calls.append(("transactions", list(candidates), start))
        if self.error:
            raise RuntimeError(self.error)
        return {"rows": self.rows, "currency": "EUR"}

    def realtime_purchases(self, minutes):
        self.calls.append(("realtime", minutes))
        return self.realtime


class AfterBase(base.Base):
    def setUp(self):
        super().setUp()
        self.shop = AfterShop()
        files = fake.fixture_files()
        self.shop.add_theme(fake.LIVE_ID, "UNPUBLISHED", dict(files), name="Live")
        self.shop.add_theme(fake.DRAFT_ID, "MAIN", dict(files), name="Entwurf")
        self.shop.orders = []
        self.ga4 = None
        self.write_apps([{"service_id": "google_analytics", "service_name": "Google Analytics 4"},
                         {"service_id": "google_ads", "service_name": "Google Ads"},
                         {"service_id": "meta", "service_name": "Meta", "decision": "drop", "decided_by": "Beispiel"}])

    def write_apps(self, rows: list) -> None:
        path = self.ws / "migration" / "inventory" / "apps.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"integrations": rows}))

    def write_walk(self, *, requests=(), reached=True, placed=None, consent="accepted", walk_stages=None,
                   headless=False, folder=RUN) -> dict:
        placed = placed or datetime.now(timezone.utc) - timedelta(minutes=5)
        walk = {"tool": "walk_checkout", "version": 1, "token": TOKEN, "approved_by": "Beispiel Team",
                "approved_at": iso(placed - timedelta(minutes=10)), "base_url": "https://beispielshop.example",
                "product_path": "/products/beispielring", "consent_mode": "accepted", "headless": headless,
                "consent_result": {"mode": "accepted", "result": consent, "how": "[data-cookiefirst-action='accept']"},
                "started_at": iso(placed - timedelta(minutes=10)), "finished_at": iso(placed),
                "stages": walk_stages if walk_stages is not None else stages(),
                "thank_you": {"reached": reached, "url": "https://beispielshop.example/checkouts/cn/x/thank-you",
                              "at": iso(placed), "order_text": "Bestellung #1001"} if reached else {"reached": False},
                "requests": [{"url": u, "stage": "thank_you", "status": 204, "post_data": p, "method": "POST"}
                             for u, p in requests]}
        path = self.ws / "reporting" / "runs" / folder / "test-order" / "walk.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(walk))
        return walk

    def order(self, placed=None, cancelled=None, financial="PAID", amount="49.9") -> dict:
        placed = placed or datetime.now(timezone.utc) - timedelta(minutes=5)
        node = {"id": "gid://shopify/Order/5550001", "name": "#1001", "createdAt": iso(placed), "test": False,
                "cancelledAt": cancelled, "displayFinancialStatus": financial,
                "totalPriceSet": {"shopMoney": {"amount": amount, "currencyCode": "EUR"}},
                "customAttributes": [{"key": to.TOKEN_KEY, "value": TOKEN}]}
        self.shop.orders = [node]
        return node

    def after(self, *argv):
        import contextlib
        import io
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            lc.main(["--workspace", str(self.ws), "--run-id", RUN, "--after", "--live-theme-id", "000000000000",
                     *argv], transport=self.shop, fetch=self.fetch, sleep=lambda s: None, ga4=self.ga4)
        report = json.loads((self.ws / "reporting" / "runs" / RUN / "launch-check-after.json").read_text())
        return self.by_id(report), report


class TestTestbestellung(AfterBase):
    def test_ohne_durchlauf_eine_frage_und_je_ziel_nicht_pruefbar(self):
        checks, _ = self.after()
        self.assertEqual(checks["test-order"]["status"], lc.MANUAL)
        self.assertIn("Ziele: GA4, Google Ads", checks["test-order"]["evidence"])
        self.assertIn("bewusst entfallen: Meta: drop laut apps.json", checks["test-order"]["evidence"])
        for cid in ("checkout-walk", "purchase-shopify", "purchase-google-analytics", "purchase-google-ads",
                    "test-order-refund"):
            self.assertEqual(checks[cid]["status"], lc.BLOCKED, cid)
        self.assertNotIn("purchase-meta", checks, "gestrichenes Ziel wird nicht geprüft")

    def test_abgelehnt_mit_namen_trifft_nicht_zu(self):
        (self.ws / "reporting" / "launch-answers.json").write_text(json.dumps({"answers": {
            "test-order": {"status": "n/a", "by": "Beispiel Team", "at": "2026-11-12"}}}))
        checks, _ = self.after()
        self.assertEqual(checks["test-order"]["status"], lc.NA)
        self.assertEqual(checks["purchase-google-ads"]["status"], lc.NA)
        self.assertIn("abgelehnt von Beispiel Team", checks["purchase-google-ads"]["evidence"])

    def test_kauf_kommt_ueberall_an(self):
        self.write_walk(requests=[GA4_HIT, (ADS_HIT, None)])
        self.order()
        self.ga4 = FakeGA4(rows=[{"transaction": "#1001", "purchases": 1, "revenue": 49.9}])
        checks, report = self.after()
        self.assertEqual(checks["test-order"]["status"], lc.OK)
        self.assertIn("freigegeben von Beispiel Team", checks["test-order"]["evidence"])
        self.assertEqual(checks["checkout-walk"]["status"], lc.OK, checks["checkout-walk"]["evidence"])
        self.assertIn("durch die abgesetzte Bestellung belegt", checks["checkout-walk"]["evidence"])
        self.assertEqual(checks["purchase-shopify"]["status"], lc.OK)
        self.assertIn("#1001", checks["purchase-shopify"]["evidence"])
        self.assertEqual(checks["purchase-shopify"]["links"][0]["url"],
                         "https://admin.shopify.com/store/beispiel/orders/5550001")
        self.assertEqual(checks["purchase-google-analytics"]["status"], lc.OK)
        self.assertIn("im GA4-Bericht: #1001: 1-mal", checks["purchase-google-analytics"]["evidence"])
        self.assertIn("#1001", self.ga4.calls[0][1])
        self.assertEqual(checks["purchase-google-ads"]["status"], lc.OK)
        self.assertIn("ohne Anzeigenklick nie", checks["purchase-google-ads"]["evidence"])
        self.assertEqual(checks["test-order-refund"]["status"], lc.MANUAL)
        self.assertIn("#1001", checks["test-order-refund"]["question"])
        self.assertFalse([c for c in self.shop.calls if c[2]], "keine Mutation, auch kein Storno")

    def test_storniert_und_erstattet_aus_der_bestellung(self):
        self.write_walk(requests=[GA4_HIT])
        self.order(cancelled="2026-11-12T11:00:00Z", financial="REFUNDED")
        checks, _ = self.after()
        self.assertEqual(checks["test-order-refund"]["status"], lc.OK)

    def test_doppelt_gezaehlt_ist_ein_befund(self):
        self.write_walk(requests=[GA4_HIT])
        self.order()
        self.ga4 = FakeGA4(rows=[{"transaction": "#1001", "purchases": 2, "revenue": 99.8}])
        checks, _ = self.after()
        self.assertEqual(checks["purchase-google-analytics"]["status"], lc.MISSING)
        self.assertIn("2-mal als Kauf gezählt", checks["purchase-google-analytics"]["evidence"])

    def test_ga4_noch_nicht_im_bericht_oder_nach_48_stunden_fehlend(self):
        self.write_walk(requests=[GA4_HIT])
        self.order()
        self.ga4 = FakeGA4(rows=[], realtime=1)
        checks, _ = self.after()
        check = checks["purchase-google-analytics"]
        self.assertEqual(check["status"], lc.BLOCKED)
        self.assertIn("Echtzeit: 1 purchase", check["evidence"])
        self.assertIn("erneut laufen lassen", check["action"])
        old = datetime.now(timezone.utc) - timedelta(hours=50)
        self.write_walk(requests=[GA4_HIT], placed=old)
        self.order(placed=old)
        checks, _ = self.after()
        self.assertEqual(checks["purchase-google-analytics"]["status"], lc.MISSING)

    def test_ga4_ueber_den_connector_ohne_zugang_nicht_pruefbar(self):
        self.write_apps([{"service_id": "google_analytics"}, {"service_id": "littledata", "service_name": "Littledata"}])
        self.write_walk(requests=[GA4_HIT])
        self.order()
        checks, _ = self.after()
        check = checks["purchase-google-analytics"]
        self.assertEqual(check["status"], lc.BLOCKED, "der Connector sendet auf dem Server, ohne Bericht kein ok")
        self.assertIn("serverseitig über Littledata", check["evidence"])
        self.assertIn("ga4_property_id", check["evidence"])

    def test_ga4_im_browser_ohne_zugang_ist_erfuellt_mit_hinweis(self):
        self.write_apps([{"service_id": "google_analytics"}])
        self.write_walk(requests=[GA4_HIT])
        self.order()
        checks, _ = self.after()
        check = checks["purchase-google-analytics"]
        self.assertEqual(check["status"], lc.OK)
        self.assertIn("Bericht nicht geprüft", check["evidence"])

    def test_pixel_fehlt_nach_einwilligung_aber_nicht_ohne_sie(self):
        self.write_apps([{"service_id": "google_ads"}])
        self.write_walk(requests=[])
        self.order()
        checks, _ = self.after()
        self.assertEqual(checks["purchase-google-ads"]["status"], lc.MISSING)
        self.write_walk(requests=[], consent="no_dialog")
        checks, _ = self.after()
        self.assertEqual(checks["purchase-google-ads"]["status"], lc.BLOCKED)
        self.assertIn("no_dialog", checks["purchase-google-ads"]["evidence"])

    def test_serverseitiges_ziel_ohne_leseweg_ist_eine_frage(self):
        config = json.loads((self.ws / "reporting" / "config.json").read_text())
        config.setdefault("theme_migration", {})["purchase_destinations"] = {"meta": {"via": "Conversions-API"}}
        (self.ws / "reporting" / "config.json").write_text(json.dumps(config))
        self.write_walk(requests=[])
        self.order()
        checks, _ = self.after()
        self.assertEqual(checks["purchase-meta"]["status"], lc.MANUAL)
        self.assertIn("Events Manager", checks["purchase-meta"]["question"])
        self.assertNotIn("purchase-google-ads", checks, "die Config gewinnt")

    def test_dankeseite_ohne_bestellung_ist_ein_befund(self):
        self.write_walk(requests=[GA4_HIT])
        checks, _ = self.after()
        self.assertEqual(checks["purchase-shopify"]["status"], lc.MISSING)
        self.assertIn(TOKEN, checks["purchase-shopify"]["evidence"])

    def test_nicht_abgeschlossen_oder_probelauf_nicht_pruefbar(self):
        self.write_walk(requests=[], reached=False)
        checks, _ = self.after()
        self.assertEqual(checks["purchase-shopify"]["status"], lc.BLOCKED)
        self.assertEqual(checks["purchase-google-ads"]["status"], lc.BLOCKED)
        self.assertEqual(checks["checkout-walk"]["status"], lc.BLOCKED, "Versand und Zahlung nicht belegt")
        self.assertIn("Versandarten nicht geprüft", checks["checkout-walk"]["evidence"])
        self.write_walk(requests=[], reached=False, headless=True)
        checks, _ = self.after()
        self.assertIn("Probelauf", checks["purchase-google-ads"]["evidence"])

    def test_warenkorb_ohne_steuerhinweis_fehlt(self):
        self.write_walk(requests=[GA4_HIT], walk_stages=stages(cart_tax=None))
        self.order()
        checks, _ = self.after()
        self.assertEqual(checks["checkout-walk"]["status"], lc.MISSING)
        self.assertIn("Warenkorb ohne Steuerhinweis", checks["checkout-walk"]["evidence"])

    def test_durchlauf_vom_launch_tag_wird_am_folgetag_gefunden(self):
        self.write_walk(requests=[GA4_HIT], folder="2026-10-05-launch-check")
        self.order()
        checks, _ = self.after()
        self.assertEqual(checks["test-order"]["status"], lc.OK)
        self.assertEqual(checks["purchase-shopify"]["status"], lc.OK)


def accepted_run(page_id, path, urls, *, result="accepted", privacy=None, consent="accepted") -> dict:
    run = base.capture_run(page_id, path, urls)
    run["consent"] = consent
    run["consent_result"] = {"mode": consent, "result": result, "how": "[data-cookiefirst-action='accept']"}
    run["privacy"] = privacy if privacy is not None else {
        "customer_privacy": {"analytics": "yes", "marketing": "yes", "preferences": "yes", "sale_of_data": "yes"},
        "google_consent": {"ad_storage": {"default": True, "update": True},
                           "analytics_storage": {"default": True, "update": True}}}
    return run


class TestTrackingNachEinwilligung(AfterBase):
    def test_ohne_mitschnitt_mit_einwilligung_nicht_pruefbar(self):
        checks, _ = self.after()
        check = checks["tracking-consent-after"]
        self.assertEqual(check["status"], lc.BLOCKED)
        self.assertIn("after-accepted", check["evidence"])

    def test_dialog_nicht_erkannt_zaehlt_nie_als_einwilligung(self):
        base.write_capture(self.ws, "old", "000000000000",
                           [accepted_run("home", "/", [GA4_PAGE], result="no_dialog")], consent="accepted")
        base.write_capture(self.ws, "after", "111111111111",
                           [accepted_run("home", "/", [GA4_PAGE, ADS_PAGE])], consent="accepted")
        checks, _ = self.after()
        check = checks["tracking-consent-after"]
        self.assertEqual(check["status"], lc.BLOCKED)
        self.assertIn("no_dialog", check["evidence"])
        self.assertIn("nicht verglichen, weil die Einwilligung", checks["tracking-after"]["evidence"])

    def test_dienst_fehlt_nach_einwilligung(self):
        base.write_capture(self.ws, "old", "000000000000",
                           [accepted_run("product", "/products/a", [GA4_PAGE, ADS_PAGE])], consent="accepted")
        base.write_capture(self.ws, "after", "111111111111",
                           [accepted_run("product", "/products/a", [GA4_PAGE])], consent="accepted")
        checks, _ = self.after()
        check = checks["tracking-consent-after"]
        self.assertEqual(check["status"], lc.MISSING)
        self.assertIn("fehlt nach Einwilligung im neuen Theme: Google Ads (product)", check["evidence"])

    def test_einwilligung_erreicht_shopify_nicht(self):
        base.write_capture(self.ws, "old", "000000000000",
                           [accepted_run("home", "/", [GA4_PAGE])], consent="accepted")
        base.write_capture(self.ws, "after", "111111111111", [accepted_run(
            "home", "/", [GA4_PAGE], privacy={"customer_privacy": {"analytics": "yes", "marketing": ""}})],
            consent="accepted")
        checks, _ = self.after()
        check = checks["tracking-consent-after"]
        self.assertEqual(check["status"], lc.MISSING)
        self.assertIn("Shopify customerPrivacy marketing=''", check["evidence"])

    def test_gleich_wie_vorher_ist_erfuellt_und_zeigt_was_erst_danach_laedt(self):
        base.write_capture(self.ws, "old", "000000000000",
                           [accepted_run("home", "/", [GA4_PAGE, ADS_PAGE])], consent="accepted")
        base.write_capture(self.ws, "after", "111111111111",
                           [accepted_run("home", "/", [GA4_PAGE, ADS_PAGE])], consent="accepted")
        base.write_capture(self.ws, "after", "111111111111", [base.capture_run("home", "/", [])])
        checks, _ = self.after()
        check = checks["tracking-consent-after"]
        self.assertEqual(check["status"], lc.OK, check["evidence"])
        self.assertIn("lädt erst nach Einwilligung: Google Ads, Google Analytics 4", check["evidence"])
        self.assertIn("customerPrivacy und Consent Mode nach Zustimmung erteilt", check["evidence"])


class TestEinwilligungVorDemLaunch(base.Base):
    def test_ordner_mit_einwilligung_genuegt_nicht_ohne_zustimmung(self):
        base.write_capture(self.ws, "old", "000000000000", [accepted_run("home", "/", [GA4_PAGE])],
                           consent="accepted")
        base.write_capture(self.ws, "new", "111111111111", [accepted_run("home", "/", [GA4_PAGE], result="stuck")],
                           consent="accepted")
        _, report = self.run_check()
        check = self.by_id(report)["tracking-consent"]
        self.assertEqual(check["status"], lc.BLOCKED)
        self.assertIn("neu: home (stuck)", check["evidence"])
        base.write_capture(self.ws, "new", "111111111111", [accepted_run("home", "/", [GA4_PAGE])],
                           consent="accepted")
        _, report = self.run_check()
        self.assertEqual(self.by_id(report)["tracking-consent"]["status"], lc.OK)


if __name__ == "__main__":
    unittest.main()
