"""Browser-Skripte: was ohne Browser feststeht.

Mitschnitt, Stilmessung und Bildpaare brauchen Playwright und einen echten Shop.
Geprüft wird hier, was davor und danach passiert: die Seitenliste, die
Vorschau-Adresse, der Theme-Nachweis aus dem HTML, die Zeile je Anfrage, die
Auswertung der gemessenen Stile und die Zuordnung der Bilder zu Paaren. Keines
der Module lädt Playwright beim Import.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "browser"))

import capture_network  # noqa: E402
import common  # noqa: E402
import measure_styles  # noqa: E402
import shoot_pair  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "theme" / "apps"


def write_pages(folder: Path, data) -> Path:
    path = folder / "pages.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


class TestSeitenliste(unittest.TestCase):
    def test_gueltige_liste_und_auswahl(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_pages(Path(tmp), {"base_url": "https://beispielshop.example/", "pages": [
                {"id": "home", "template": "index", "path": "/", "locale": "de"},
                {"id": "product", "template": "product", "path": "/products/beispiel"}]})
            pages = common.load_pages(path)
            self.assertEqual(pages["base_url"], "https://beispielshop.example")
            self.assertEqual([p["id"] for p in common.load_pages(path, ["product"])["pages"]], ["product"])

    def test_fehlerhafte_listen_werden_abgelehnt(self):
        cases = [
            {"base_url": "http://beispielshop.example", "pages": [{"id": "a", "path": "/"}]},
            {"base_url": "https://beispielshop.example", "pages": [{"id": "a", "path": "ohne-schraegstrich"}]},
            {"base_url": "https://beispielshop.example", "pages": [{"id": "a", "path": "/"}, {"id": "a", "path": "/x"}]},
            {"base_url": "https://beispielshop.example", "pages": []},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            for case in cases:
                with self.subTest(case=case):
                    with self.assertRaises(common.PagesError):
                        common.load_pages(write_pages(Path(tmp), case))

    def test_geraete_nur_aus_der_erlaubten_liste(self):
        self.assertEqual(common.parse_list("desktop, mobile", common.DEVICES), ["desktop", "mobile"])
        with self.assertRaises(ValueError):
            common.parse_list("tablet", common.DEVICES)


class TestVorschau(unittest.TestCase):
    def test_vorschau_adresse_behaelt_parameter(self):
        url = common.page_url("https://beispielshop.example", "/search?q=ring", "000000000000", hide_bar=True)
        self.assertEqual(url, "https://beispielshop.example/search?q=ring&preview_theme_id=000000000000&pb=0")

    def test_ohne_theme_kein_vorschauparameter(self):
        self.assertEqual(common.page_url("https://beispielshop.example", "/", None, hide_bar=True),
                         "https://beispielshop.example/")

    def test_alter_vorschauparameter_wird_ersetzt(self):
        url = common.page_url("https://beispielshop.example", "/?preview_theme_id=1&pb=1", "000000000000")
        self.assertEqual(url, "https://beispielshop.example/?preview_theme_id=000000000000")

    def test_theme_nachweis_aus_dem_html_mit_fuehrenden_nullen(self):
        html = (FIXTURES / "html" / "home-desktop-1.html").read_text(encoding="utf-8")
        found = common.theme_from_html(html)
        self.assertEqual((found["id"], found["name"], found["role"]), ("000000000000", "Beispiel Theme", "main"))
        self.assertIsNone(common.theme_from_html("<html>ohne Theme</html>"))

    def test_falsches_oder_fehlendes_theme_ist_wrong_theme(self):
        self.assertEqual(common.check_theme({"id": "000000000000"}, "000000000000")["state"], "ok")
        wrong = common.check_theme({"id": "111111111111"}, "000000000000")
        self.assertEqual((wrong["state"], wrong["reason"]), ("wrong_theme", "Seite zeigt Theme 111111111111"))
        self.assertEqual(common.check_theme(None, "000000000000")["state"], "wrong_theme")
        self.assertEqual(common.check_theme(None, None)["state"], "ok")

    def test_theme_id_als_zahl_aus_dem_browser(self):
        # Shopify.theme.id ist im Browser eine Zahl; eine Ziffernfolge gilt als dieselbe ID.
        self.assertTrue(common.check_theme({"id": "2"}, "000000000002")["ok"])


class FakeFrame:
    url = "https://beispielshop.example/"


class FakeRequest:
    def __init__(self, method="GET", frame=True, body=None):
        self.url = "https://region1.google-analytics.com/g/collect?v=2"
        self.method = method
        self.resource_type = "fetch"
        self._frame = frame
        self._body = body

    @property
    def frame(self):
        if not self._frame:
            raise RuntimeError("Service Worker requests do not have an associated frame")
        return FakeFrame()

    @property
    def post_data(self):
        return self._body


class TestMitschnitt(unittest.TestCase):
    def test_zeile_je_anfrage_mit_phase_und_inhalt(self):
        record = capture_network.request_record(FakeRequest("POST", body="en=page_view" * 1000), "pre", 0.0)
        self.assertEqual(record["consent_phase"], "pre")
        self.assertEqual(record["frame_url"], "https://beispielshop.example/")
        self.assertEqual(len(record["post_data"]), capture_network.MAX_POST)

    def test_anfrage_ohne_rahmen_ist_kein_fehler(self):
        record = capture_network.request_record(FakeRequest(frame=False), "post", 0.0)
        self.assertIsNone(record["frame_url"])
        self.assertNotIn("post_data", record)

    def test_zusammenfassung_zaehlt_jeden_ausgang(self):
        runs = [{"state": "ok", "requests": [1, 2]}, {"state": "wrong_theme", "requests": []},
                {"state": "error"}, {"state": "ok", "consent_result": {"result": "stuck"}, "requests": [1]}]
        self.assertEqual(capture_network.summarize(runs), {"runs": 4, "ok": 2, "wrong_theme": 1, "errors": 1,
                                                           "consent_stuck": 1, "requests": 3})

    def test_fixture_hat_das_format_des_mitschnitts(self):
        data = json.loads((FIXTURES / "network.json").read_text(encoding="utf-8"))
        self.assertEqual(data["tool"], "capture_network")
        for run in data["runs"]:
            self.assertLessEqual({"page_id", "device", "browser", "run", "consent", "state", "requests"}, set(run))


class FakeLocator:
    def __init__(self, page, text):
        self.page, self.text = page, text

    def count(self):
        return 1 if self.text in self.page.visible else 0

    def nth(self, index):
        return self

    def is_visible(self):
        return self.text in self.page.visible

    def click(self, timeout=None):
        self.page.events.append(f"click:{self.text}")
        self.page.visible = set(self.page.after.get(self.text, self.page.visible))

    @property
    def first(self):
        return self


class FakePage:
    """Ein Cookie-Dialog ohne bekanntes Tool; die Knöpfe tragen nur Text."""

    def __init__(self, visible, after):
        self.visible, self.after, self.events = set(visible), after, []

    def wait_for_selector(self, selector, state=None, timeout=None):
        raise TimeoutError("kein bekanntes Consent-Tool")

    def locator(self, selector):
        return FakeLocator(self, f"selector:{selector.split(' >> ')[0]}")

    def get_by_text(self, text, exact=False):
        return FakeLocator(self, text)

    def wait_for_timeout(self, ms):
        pass


class TestConsent(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, str(common.CONSENT_DIR))
        import consent
        self.consent = consent

    def test_zustimmen_nur_auf_verlangen_und_ueber_den_text(self):
        page = FakePage({"Alle akzeptieren", "Ablehnen"}, {"Alle akzeptieren": set()})
        result = common.handle_consent(page, "accepted")
        self.assertEqual((result["result"], result["how"]), ("accepted", "Alle akzeptieren"))
        page = FakePage({"Alle akzeptieren", "Ablehnen"}, {"Ablehnen": set()})
        self.assertEqual(common.handle_consent(page, "declined")["result"], "declined")

    def test_zustimmen_ueber_den_knopf_des_tools(self):
        selector = "selector:#onetrust-accept-btn-handler"
        page = FakePage({selector}, {selector: set()})
        self.assertEqual(self.consent.accept(page, wait_ms=0), ("accepted", "#onetrust-accept-btn-handler"))

    def test_phase_wechselt_unmittelbar_vor_dem_klick(self):
        page = FakePage({"Alle akzeptieren", "Alle ablehnen"}, {"Alle ablehnen": set()})
        self.consent.decline(page, wait_ms=0, before_click=lambda: page.events.append("phase:post"))
        self.assertEqual(page.events, ["phase:post", "click:Alle ablehnen"])

    def test_ohne_dialog_kein_klick_und_kein_phasenwechsel(self):
        page = FakePage({"Impressum"}, {})
        self.assertEqual(self.consent.accept(page, wait_ms=0, before_click=lambda: page.events.append("x")),
                         ("no_dialog", None))
        self.assertEqual(page.events, [])


class TestStilmessung(unittest.TestCase):
    def test_farben_werden_vergleichbar(self):
        self.assertEqual(measure_styles.normalize_color("rgb(17, 17, 17)"), "#111111")
        self.assertEqual(measure_styles.normalize_color("rgba(0, 0, 0, 0)"), None)
        self.assertEqual(measure_styles.normalize_color("rgba(255, 0, 0, 0.5)"), "#ff000080")
        self.assertEqual(measure_styles.normalize_color("rgb(0 128 255 / 100%)"), "#0080ff")

    def test_neutral_und_akzent(self):
        self.assertTrue(measure_styles.is_neutral("#f5f5f5"))
        self.assertFalse(measure_styles.is_neutral("#c0392b"))

    def test_breakpoints_in_px_nach_haeufigkeit(self):
        found = measure_styles.parse_breakpoints(["screen and (min-width: 750px)", "(min-width: 750px)",
                                                  "(max-width: 61.9375em)", "print"])
        self.assertEqual(found[0], {"kind": "min", "px": 750.0, "count": 2})
        self.assertIn({"kind": "max", "px": 991.0, "count": 1}, found)

    def test_haeufigster_stil_einer_rolle(self):
        base = {"font_family": "\"Beispiel Sans\", sans-serif", "font_size": "32px", "font_weight": "700",
                "line_height": "40px", "letter_spacing": "normal", "text_transform": "none", "color": "rgb(17, 17, 17)"}
        other = {**base, "font_size": "24px", "line_height": "30px"}
        role = measure_styles.summarize_role([base, base, other])
        self.assertEqual(role["samples"], 3)
        self.assertEqual(role["share"], 0.67)
        self.assertEqual(role["value"]["font_family"], "Beispiel Sans")
        self.assertEqual(role["value"]["font_size"], 32.0)
        self.assertEqual(role["value"]["line_height_ratio"], 1.25)
        self.assertEqual(role["variants"][0]["font_size"], 24.0)
        self.assertEqual(measure_styles.summarize_role([])["value"], None)

    def test_seite_mit_akzentfarben_und_radien(self):
        raw = {"roles": {"button": [{"background_color": "rgb(192, 57, 43)", "color": "rgb(255, 255, 255)",
                                     "border_radius": "4px", "font_size": "16px", "line_height": "20px"}]},
               "backgrounds": {"page": "rgb(255, 255, 255)", "header": "rgba(0, 0, 0, 0)"},
               "radii": {"button": ["4px", "4px", "0px"]}}
        page = measure_styles.summarize_page(raw)
        self.assertEqual(page["colors"]["accents"], [{"color": "#c0392b", "count": 1}])
        self.assertEqual(page["colors"]["background_page"], "#ffffff")
        self.assertIsNone(page["colors"]["background_header"])
        self.assertEqual(page["radii"]["button"]["value"], "4px")
        self.assertEqual(page["roles"]["h1"]["samples"], 0)


class TestBildpaare(unittest.TestCase):
    def test_feste_dateinamen(self):
        self.assertEqual(shoot_pair.image_names("home", "mobile", "b"), ("home/mobile-b.png", "home/mobile-b-fold.png"))

    def test_paare_je_seite_und_geraet_auch_bei_fehler(self):
        page = {"id": "home", "template": "index", "path": "/"}
        jobs = [{"page": page, "device": d, "side": s} for d in ("desktop", "mobile") for s in ("a", "b")]
        results = [{"state": "ok", "file": "home/desktop-a.png"}, {"state": "wrong_theme"},
                   {"job": {}, "state": "error", "error": "Zeitlimit"}, {"state": "ok"}]
        data = shoot_pair.build_pairs(jobs, results, {"a": "000000000000", "b": "000000000002"})
        self.assertEqual([(p["page_id"], p["device"]) for p in data["pairs"]], [("home", "desktop"), ("home", "mobile")])
        self.assertEqual(data["pairs"][0]["b"]["state"], "wrong_theme")
        self.assertEqual(data["pairs"][1]["a"], {"state": "error", "error": "Zeitlimit"})


if __name__ == "__main__":
    unittest.main()
