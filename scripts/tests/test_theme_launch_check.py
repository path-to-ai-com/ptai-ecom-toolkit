"""Launch-Check: je Punkt ein Status mit Beleg, nie ein Schreibzugriff auf den Shop."""
import contextlib
import io
import json
import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from tests import theme_fake_shop as fake  # noqa: E402
from theme import launch_check as lc  # noqa: E402

EMBED = "shopify://apps/beispiel-bewertungen/blocks/sterne/0000aaaa-0000-0000-0000-000000000000"


def settings_with(embeds: dict) -> bytes:
    blocks = {key: {"type": EMBED.replace("sterne", name), "disabled": disabled, "settings": {}}
              for key, (name, disabled) in embeds.items()}
    return json.dumps({"current": {"blocks": blocks}}).encode()


class LaunchShop(fake.FakeShop):
    """Der erfundene Shop plus die zwei Abfragen, die nur der Launch-Check stellt."""

    locales = [{"locale": "de", "primary": True, "published": True},
               {"locale": "en", "primary": False, "published": True}]
    accounts = "NEW_CUSTOMER_ACCOUNTS"

    def op_LaunchCheckLocales(self, variables):
        return {"shopLocales": self.locales}

    def op_LaunchCheckAccounts(self, variables):
        return {"shop": {"customerAccountsV2": {"customerAccountsVersion": self.accounts}}}


def network(base: str, theme: str, pages: dict, consent: str = "declined", html: dict | None = None,
            folder: Path | None = None) -> dict:
    runs = []
    for page_id, (path, urls) in pages.items():
        run = {"page_id": page_id, "path": path, "template": page_id, "device": "desktop", "run": 1,
               "consent": consent, "state": "ok", "status": 200,
               "requests": [{"url": u, "method": "GET"} for u in urls]}
        if html and page_id in html and folder:
            (folder / "html").mkdir(parents=True, exist_ok=True)
            (folder / "html" / f"{page_id}.html").write_text(html[page_id], encoding="utf-8")
            run["html_file"] = f"html/{page_id}.html"
        runs.append(run)
    return {"base_url": base, "theme_id": theme, "consent_mode": consent, "runs": runs}


def write_capture(ws: Path, side: str, theme: str, runs: list, consent: str = "declined") -> None:
    """Ein Mitschnitt unter capture/<side>-<consent>/ aus fertigen Durchläufen."""
    folder = ws / "reporting" / "runs" / "2026-10-06-launch-check" / "capture" / f"{side}-{consent}"
    folder.mkdir(parents=True, exist_ok=True)
    data = {"base_url": "https://beispielshop.example", "theme_id": theme, "consent_mode": consent, "runs": runs}
    (folder / "network.json").write_text(json.dumps(data))


def capture_run(page_id: str, path: str, urls: list, *, device: str = "desktop", run: int = 1,
                final_url: str | None = None) -> dict:
    return {"page_id": page_id, "path": path, "template": page_id, "device": device, "run": run,
            "consent": "declined", "state": "ok", "status": 200,
            "final_url": final_url or "https://beispielshop.example" + path,
            "requests": [{"url": u, "method": "GET"} for u in urls]}


GA4 = "https://region1.google-analytics.com/g/collect?v=2"


class Base(unittest.TestCase):
    def setUp(self):
        self.ws = fake.temp_workspace(self, draft_theme_id="111111111111")
        config = json.loads((self.ws / "reporting" / "config.json").read_text())
        config["domain"] = "https://beispielshop.example"
        (self.ws / "reporting" / "config.json").write_text(json.dumps(config))
        self.shop = LaunchShop()
        files = fake.fixture_files()
        self.shop.add_theme(fake.LIVE_ID, "MAIN", dict(files), name="Live")
        self.shop.add_theme(fake.DRAFT_ID, "UNPUBLISHED", dict(files), name="Entwurf")
        self.fetched = []

    def fetch(self, url):
        self.fetched.append(url)
        return 200, {}, "<html><head><link rel=\"canonical\" href=\"%s\"></head></html>" % url.split("?")[0]

    def run_check(self, *argv, transport="shop") -> tuple:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = lc.main(["--workspace", str(self.ws), "--run-id", "2026-10-06-launch-check", *argv],
                           transport=self.shop if transport == "shop" else transport,
                           fetch=self.fetch, sleep=lambda s: None)
        name = "launch-check-after.json" if "--after" in argv else "launch-check.json"
        path = self.ws / "reporting" / "runs" / "2026-10-06-launch-check" / name
        return code, json.loads(path.read_text()) if path.exists() else None

    @staticmethod
    def by_id(report) -> dict:
        return {c["id"]: c for c in report["checks"]}


class TestKalender(unittest.TestCase):
    def test_ostern_und_black_friday(self):
        self.assertEqual(lc.easter(2026), date(2026, 4, 5))
        self.assertEqual(lc.easter(2027), date(2027, 3, 28))
        self.assertEqual(lc.black_friday(2026), date(2026, 11, 27))
        self.assertEqual(lc.black_friday(2025), date(2025, 11, 28))

    def test_saisonfenster_beginnt_vier_wochen_vor_black_friday(self):
        start, end = lc.season_window(2026)
        self.assertEqual(start, date(2026, 10, 30))
        self.assertEqual(end, date(2026, 12, 31))


class TestVorDemLaunch(Base):
    def test_freitag_und_tag_vor_feiertag_fehlen(self):
        _, report = self.run_check("--launch-date", "2026-10-09")
        self.assertEqual(self.by_id(report)["timing-weekday"]["status"], lc.MISSING)
        _, report = self.run_check("--launch-date", "2026-10-02")
        self.assertEqual(self.by_id(report)["timing-holiday"]["status"], lc.MISSING)
        self.assertIn("Tag der Deutschen Einheit", self.by_id(report)["timing-holiday"]["evidence"])
        _, report = self.run_check("--launch-date", "2026-10-07")
        checks = self.by_id(report)
        self.assertEqual((checks["timing-weekday"]["status"], checks["timing-holiday"]["status"],
                          checks["timing-season"]["status"]), (lc.OK, lc.OK, lc.OK))
        _, report = self.run_check("--launch-date", "2026-11-12")
        self.assertEqual(self.by_id(report)["timing-season"]["status"], lc.MISSING)

    def test_ohne_termin_eine_frage_statt_drei_pruefungen(self):
        _, report = self.run_check()
        checks = self.by_id(report)
        self.assertEqual(checks["timing-date"]["status"], lc.MANUAL)
        self.assertTrue(checks["timing-date"]["question"])
        self.assertNotIn("timing-weekday", checks)

    def test_schreibt_nie_in_den_shop(self):
        self.run_check("--launch-date", "2026-10-07")
        self.assertTrue(self.shop.calls)
        self.assertFalse([c for c in self.shop.calls if c[2]], "keine Mutation")
        self.assertFalse([c for c in self.shop.calls if "Upsert" in c[0] or "Register" in c[0]])

    def test_ohne_shopify_zugang_nicht_pruefbar_statt_absturz(self):
        class Broken:
            def execute(self, *a, **k):
                raise lc.ShopifyError("kein Grant")
        code, report = self.run_check(transport=Broken())
        checks = self.by_id(report)
        self.assertEqual(code, 1)
        for key in ("draft-theme", "app-embeds", "theme-translations", "live-sync"):
            self.assertEqual(checks[key]["status"], lc.BLOCKED, key)
            self.assertIn("kein Grant", checks[key]["evidence"])

    def test_embed_fehlt_im_entwurf_ausser_es_ist_gestrichen(self):
        self.shop.touch(fake.LIVE_ID, "config/settings_data.json",
                        settings_with({"a": ("sterne", False), "b": ("alt", True)}))
        self.shop.touch(fake.DRAFT_ID, "config/settings_data.json", settings_with({}))
        _, report = self.run_check()
        embeds = self.by_id(report)["app-embeds"]
        self.assertEqual(embeds["status"], lc.MISSING)
        self.assertIn("beispiel-bewertungen/sterne", embeds["evidence"])
        self.assertNotIn("beispiel-bewertungen/alt", embeds["evidence"], "ausgeschaltet live ist keine Lücke")
        inventory = self.ws / "migration" / "inventory"
        inventory.mkdir(parents=True)
        (inventory / "apps.json").write_text(json.dumps(
            {"integrations": [{"app_handle": "beispiel-bewertungen", "decision": "drop"}]}))
        _, report = self.run_check()
        self.assertEqual(self.by_id(report)["app-embeds"]["status"], lc.OK)

    def test_live_theme_geaendert_seit_der_sicherung(self):
        snap = self.ws / "migration" / "snapshots" / "2026-10-01-000000000000"
        snap.mkdir(parents=True)
        live = self.shop.themes[fake.LIVE_ID]
        (snap / "manifest.json").write_text(json.dumps({"theme_id": "000000000000", "captured_at": "2026-10-01T08:00:00Z",
                                                        "theme_updated_at": live["updatedAt"], "files": {}}))
        _, report = self.run_check()
        self.assertEqual(self.by_id(report)["live-sync"]["status"], lc.OK)
        self.shop.touch(fake.LIVE_ID, "snippets/icon.liquid", b"<svg></svg>")
        _, report = self.run_check()
        self.assertEqual(self.by_id(report)["live-sync"]["status"], lc.MISSING)
        self.assertIn("sync-live-theme", self.by_id(report)["live-sync"]["action"])

    def test_offene_punkte_der_testrunde(self):
        folder = self.ws / "reporting" / "runs" / "2026-09-24-test"
        folder.mkdir(parents=True)
        test = {"title": "Testrunde", "groups": [{"id": "g", "items": [
            {"id": "TP-01", "title": "Menü", "status": "done"},
            {"id": "TP-02", "title": "Suche", "status": "decision"},
            {"id": "TP-03", "title": "Filter"}]}]}
        (folder / "test.json").write_text(json.dumps(test))
        _, report = self.run_check()
        check = self.by_id(report)["acceptance-test-round"]
        self.assertEqual(check["status"], lc.MISSING)
        self.assertIn("TP-02 Suche (decision)", check["evidence"])
        self.assertEqual(check["owner"], lc.TEAM)
        test["groups"][0]["items"][1]["status"] = "done"
        (folder / "test.json").write_text(json.dumps(test))
        _, report = self.run_check()
        self.assertEqual(self.by_id(report)["acceptance-test-round"]["status"], lc.OK)

    def test_tracking_fehlt_je_seite_shopify_und_eigene_domain_zaehlen_nicht(self):
        capture = self.ws / "reporting" / "runs" / "2026-10-06-launch-check" / "capture"
        base = "https://beispielshop.example"
        common = ["https://beispielshop.example/cart.js", "https://cdn.shopify.com/s/files/x.js"]
        for side, theme, extra in (("old", "000000000000", ["https://www.googletagmanager.com/gtm.js?id=GTM-X"]),
                                   ("new", "111111111111", [])):
            folder = capture / f"{side}-declined"
            folder.mkdir(parents=True)
            data = network(base, theme, {"home": ("/", common + extra)})
            (folder / "network.json").write_text(json.dumps(data))
        _, report = self.run_check()
        check = self.by_id(report)["tracking-hosts"]
        self.assertEqual(check["status"], lc.MISSING)
        self.assertEqual([m["service"] for m in check["details"]["missing"]], ["google_tag_manager"])
        self.assertTrue(any("preview_theme_id=111111111111" in l["url"] for l in check["links"]))
        self.assertTrue(any("preview_theme_id=000000000000" in l["url"] for l in check["links"]))
        self.assertEqual(self.by_id(report)["tracking-consent"]["status"], lc.MANUAL)

    def test_noindex_im_entwurf_aus_dem_html_des_mitschnitts(self):
        capture = self.ws / "reporting" / "runs" / "2026-10-06-launch-check" / "capture"
        base = "https://beispielshop.example"
        head = '<link rel="canonical" href="https://beispielshop.example/">'
        for side, theme, robots in (("old", "000000000000", ""), ("new", "111111111111",
                                                                   '<meta name="robots" content="noindex">')):
            folder = capture / f"{side}-declined"
            data = network(base, theme, {"home": ("/", [])}, html={"home": f"<head>{head}{robots}</head>"},
                           folder=folder)
            (folder / "network.json").write_text(json.dumps(data))
        _, report = self.run_check()
        check = self.by_id(report)["seo-pages"]
        self.assertEqual(check["status"], lc.MISSING)
        self.assertIn("noindex", check["evidence"])

    def test_antwort_gilt_nur_fuer_manuelle_punkte_und_braucht_einen_namen(self):
        answers = self.ws / "reporting" / "launch-answers.json"
        answers.write_text(json.dumps({"answers": {
            "timing-campaigns": {"status": "ok", "by": "Beispiel Person", "at": "2026-10-06", "note": "kein Sale"},
            "timing-contacts": {"status": "ok"},
            "draft-theme": {"status": "ok", "by": "Beispiel Person"}}}))
        self.shop.themes[fake.DRAFT_ID]["role"] = "DEVELOPMENT"
        _, report = self.run_check()
        checks = self.by_id(report)
        self.assertEqual(checks["timing-campaigns"]["status"], lc.OK)
        self.assertIn("Beispiel Person", checks["timing-campaigns"]["evidence"])
        self.assertEqual(checks["timing-contacts"]["status"], lc.MANUAL, "ohne Namen keine Antwort")
        self.assertEqual(checks["draft-theme"]["status"], lc.MISSING, "eine Antwort überstimmt keinen Befund")

    def test_markdown_fehlendes_zuerst_und_empfehlung_oben(self):
        self.shop.themes[fake.DRAFT_ID]["role"] = "DEVELOPMENT"
        code, report = self.run_check()
        self.assertEqual((code, report["recommendation"]), (1, "no_go"))
        text = (self.ws / "reporting" / "runs" / "2026-10-06-launch-check" / "launch-check.md").read_text()
        self.assertIn("**Empfehlung: No-Go.**", text.split("\n## ")[0])
        headings = [line for line in text.splitlines() if line.startswith("## ")]
        self.assertTrue(headings[0].startswith("## Fehlt"))
        self.assertNotRegex(text, r"[\u2013\u2014]")

    def test_gestrichener_dienst_ist_erfuellt_mit_der_entscheidung_als_beleg(self):
        vwo = "https://dev.visualwebsiteoptimizer.com/j.php"
        write_capture(self.ws, "old", "000000000000", [capture_run("home", "/", [vwo])])
        write_capture(self.ws, "new", "111111111111", [capture_run("home", "/", [])])
        _, report = self.run_check()
        self.assertEqual(self.by_id(report)["tracking-hosts"]["status"], lc.MISSING)
        mapping = self.ws / "migration" / "mapping"
        mapping.mkdir(parents=True)
        entries = [{"id": "D-1", "subject": "VWO", "kind": "app", "decision": "drop",
                    "reason": "Test beendet", "decided_by": "Beispiel Person", "decided_at": "2026-10-01"}]
        (mapping / "decisions.json").write_text(json.dumps({"decisions": entries}))
        _, report = self.run_check()
        check = self.by_id(report)["tracking-hosts"]
        self.assertEqual(check["status"], lc.OK)
        self.assertIn("bewusst entfallen: VWO: drop laut decisions.json, Beispiel Person", check["evidence"])
        self.assertIn("Test beendet", check["evidence"])
        entries.append({"id": "D-2", "subject": "VWO", "kind": "app", "decision": "keep",
                        "decided_by": "Beispiel Person"})
        (mapping / "decisions.json").write_text(json.dumps({"decisions": entries}))
        _, report = self.run_check()
        self.assertEqual(self.by_id(report)["tracking-hosts"]["status"], lc.MISSING, "der jüngste Eintrag gilt")

    def test_embed_gestrichen_laut_decisions_json_ueber_den_dienstnamen(self):
        self.shop.touch(fake.LIVE_ID, "config/settings_data.json", settings_with({"a": ("sterne", False)}))
        self.shop.touch(fake.DRAFT_ID, "config/settings_data.json", settings_with({}))
        mapping = self.ws / "migration" / "mapping"
        mapping.mkdir(parents=True)
        (mapping / "decisions.json").write_text(json.dumps([
            {"subject": "beispiel-bewertungen", "kind": "app", "decision": "drop", "decided_by": "Beispiel Person"}]))
        _, report = self.run_check()
        check = self.by_id(report)["app-embeds"]
        self.assertEqual(check["status"], lc.OK)
        self.assertIn("bewusst entfallen", check["evidence"])

    def test_eigene_subdomain_eines_dienstes_ist_kein_eigener_host(self):
        endpoint = "https://t.beispielshop.example/collect"
        fallback = "https://api.segment.io/v1/t"
        write_capture(self.ws, "old", "000000000000", [capture_run("home", "/", [endpoint])])
        write_capture(self.ws, "new", "111111111111", [capture_run("home", "/", [fallback])])
        _, report = self.run_check()
        check = self.by_id(report)["tracking-hosts"]
        self.assertEqual(check["status"], lc.MISSING, "die Subdomain fehlt im neuen Theme, das ist sichtbar")
        self.assertIn("t.beispielshop.example", check["evidence"])
        inventory = self.ws / "migration" / "inventory"
        inventory.mkdir(parents=True)
        (inventory / "apps.json").write_text(json.dumps({"integrations": [
            {"service_id": "segment", "hosts": ["t.beispielshop.example"], "decision": "keep"}]}))
        _, report = self.run_check()
        check = self.by_id(report)["tracking-hosts"]
        self.assertEqual(check["status"], lc.OK, "Subdomain und Ausweich-Endpunkt sind derselbe Dienst")
        self.assertEqual(check["details"]["added"], [])

    def test_pagination_mit_vervielfachten_ereignissen_fehlt(self):
        own = "https://t.beispielshop.example/collect"
        write_capture(self.ws, "old", "000000000000", [
            capture_run("search", "/search?q=ring", [GA4] * 3 + [own] * 2, run=1),
            capture_run("search", "/search?q=ring", [GA4] * 4 + [own] * 2, run=2),
            capture_run("home", "/", [GA4] * 3)])
        write_capture(self.ws, "new", "111111111111", [
            capture_run("search", "/search?q=ring", [GA4] * 9 + [own] * 8, run=1,
                        final_url="https://beispielshop.example/search?q=ring&page=8"),
            capture_run("search", "/search?q=ring", [GA4] * 10 + [own] * 8, run=2,
                        final_url="https://beispielshop.example/search?q=ring&page=8"),
            capture_run("home", "/", [GA4] * 4)])
        _, report = self.run_check()
        check = self.by_id(report)["pagination"]
        self.assertEqual(check["status"], lc.MISSING)
        self.assertIn("search (desktop): lädt beim Scrollen nach bis page=8", check["evidence"])
        self.assertIn("Google Analytics 4 9 statt 4 Anfragen", check["evidence"], "Minimum neu gegen Maximum alt")
        self.assertIn("t.beispielshop.example 8 statt 2", check["evidence"])
        self.assertNotIn("home", check["evidence"].split("mehr Analyse-Ereignisse")[1])
        self.assertTrue(any("search?q=ring&preview_theme_id=111111111111" in l["url"] for l in check["links"]))

    def test_pagination_anders_ohne_mehr_ereignisse_ist_eine_frage(self):
        write_capture(self.ws, "old", "000000000000", [capture_run("collection", "/collections/ringe", [GA4] * 3)])
        write_capture(self.ws, "new", "111111111111", [capture_run(
            "collection", "/collections/ringe", [GA4] * 3, final_url="https://beispielshop.example/collections/ringe?page=3")])
        _, report = self.run_check()
        check = self.by_id(report)["pagination"]
        self.assertEqual(check["status"], lc.MANUAL)
        self.assertTrue(check["question"])

    def test_pagination_gleich_und_ohne_mitschnitt(self):
        _, report = self.run_check()
        self.assertEqual(self.by_id(report)["pagination"]["status"], lc.BLOCKED)
        write_capture(self.ws, "old", "000000000000", [capture_run("home", "/", [GA4] * 3)])
        write_capture(self.ws, "new", "111111111111", [capture_run("home", "/", [GA4] * 5)])
        _, report = self.run_check()
        self.assertEqual(self.by_id(report)["pagination"]["status"], lc.OK, "2 mehr liegt unter der Schwelle")

    def test_gestrichener_host_streicht_nicht_seine_ganze_domain(self):
        catalog = lc.apps.HostCatalog.load()
        keys = lc.subject_keys("ajax.googleapis.com", catalog)
        self.assertIn("google_hosted_libraries", keys)
        self.assertNotIn("googleapis.com", keys)
        self.assertIn("beispiel-cdn.example", lc.subject_keys("static.beispiel-cdn.example", catalog),
                      "ein unbekannter Host zählt über seine Domain, wie im Tracking")


class TestRobots(unittest.TestCase):
    def test_sperre_gilt_je_gruppe(self):
        shopify = ("# we use Shopify as our ecommerce platform\nUser-agent: *\nDisallow: /admin\nDisallow: /cart\n\n"
                   "User-agent: adsbot-google\nDisallow: /checkouts/\n\nUser-agent: Nutch\nDisallow: /\n")
        self.assertEqual(lc.blocked_agents(shopify), ([], ["nutch"]))
        self.assertEqual(lc.blocked_agents("User-agent: *\nDisallow: /\n"), (["*", "googlebot"], []))
        own_group = "User-agent: *\nDisallow: /\n\nUser-agent: Googlebot\nAllow: /\n"
        self.assertEqual(lc.blocked_agents(own_group), (["*"], []), "Googlebot folgt seiner eigenen Gruppe")
        self.assertEqual(lc.blocked_agents("User-agent: *\nDisallow: /\nAllow: /\n"), ([], []))
        self.assertEqual(lc.blocked_agents("Disallow: /\n"), ([], []), "Regel ohne Gruppe gilt für niemanden")

    def test_seitenzahl_aus_der_adresse(self):
        self.assertEqual(lc.page_number("https://x.example/search?q=a&page=14"), 14)
        self.assertEqual(lc.page_number("/search?q=a"), 1)
        self.assertEqual(lc.page_number(None), 1)



class TestEmpfehlung(unittest.TestCase):
    def test_fehlt_schlaegt_offen_schlaegt_go(self):
        make = lambda s: lc.make_check("x", "g", "t", s, "")  # noqa: E731
        self.assertEqual(lc.recommend([make(lc.OK), make(lc.NA)]), "go")
        self.assertEqual(lc.recommend([make(lc.OK), make(lc.MANUAL)]), "open")
        self.assertEqual(lc.recommend([make(lc.BLOCKED), make(lc.MISSING)]), "no_go")

    def test_head_tags(self):
        tags = lc.head_tags('<meta content="NOINDEX, follow" name="robots">'
                            "<link href='https://x.example/a/?p=1' rel='canonical'>")
        self.assertTrue(tags["noindex"])
        self.assertEqual(lc.canonical_path(tags["canonical"]), "/a")


class TestNachDemLaunch(Base):
    def setUp(self):
        super().setUp()
        self.shop.themes[fake.LIVE_ID]["role"] = "UNPUBLISHED"
        self.shop.themes[fake.DRAFT_ID]["role"] = "MAIN"

    def test_neues_theme_live_altes_als_rueckfall(self):
        _, report = self.run_check("--after", "--live-theme-id", "000000000000")
        checks = self.by_id(report)
        self.assertEqual(report["mode"], "after")
        self.assertEqual(checks["published-theme"]["status"], lc.OK)
        self.assertEqual(checks["rollback-theme"]["status"], lc.OK)
        self.assertEqual(checks["pages-after"]["status"], lc.OK)
        self.assertEqual(checks["test-order"]["status"], lc.MANUAL)
        self.assertFalse([c for c in self.shop.calls if c[2]], "keine Mutation")

    def test_noindex_im_html_live_ist_ein_befund_wenn_das_alte_theme_es_nicht_hatte(self):
        self.fetch = lambda url: (200, {}, '<meta name="robots" content="noindex">')
        _, report = self.run_check("--after", "--live-theme-id", "000000000000")
        check = self.by_id(report)["pages-after"]
        self.assertEqual(check["status"], lc.MISSING)
        self.assertIn("ohne Mitschnitt des alten Themes", check["evidence"])

    def test_noindex_wie_im_alten_theme_ist_kein_befund(self):
        folder = self.ws / "reporting" / "runs" / "2026-10-06-launch-check" / "capture" / "old-declined"
        data = network("https://beispielshop.example", "000000000000", {"home": ("/", [])},
                       html={"home": '<head><meta name="robots" content="noindex"></head>'}, folder=folder)
        (folder / "network.json").write_text(json.dumps(data))
        self.fetch = lambda url: (200, {}, '<meta name="robots" content="noindex">')
        _, report = self.run_check("--after", "--live-theme-id", "000000000000")
        check = self.by_id(report)["pages-after"]
        self.assertEqual(check["status"], lc.OK)
        self.assertIn("wie im alten Theme", check["evidence"])

    def test_noindex_als_header_kommt_von_shopify_und_ist_kein_befund(self):
        self.fetch = lambda url: (200, {"x-robots-tag": "noindex"}, "")
        _, report = self.run_check("--after", "--live-theme-id", "000000000000")
        check = self.by_id(report)["pages-after"]
        self.assertEqual(check["status"], lc.OK)
        self.assertIn("X-Robots-Tag von Shopify", check["evidence"])

    def test_robots_sperre_fuer_einen_einzelnen_crawler_ist_shopify_standard(self):
        robots = "User-agent: *\nDisallow: /cart\n\nUser-agent: Nutch\nDisallow: /\n"
        self.fetch = lambda url: (200, {}, robots if url.endswith("/robots.txt") else "")
        _, report = self.run_check("--after", "--live-theme-id", "000000000000")
        check = self.by_id(report)["robots-after"]
        self.assertEqual(check["status"], lc.MANUAL, "kein Stand von vorher, aber keine Sperre")
        self.assertIn("Disallow: / nur für nutch", check["evidence"])
        robots = "User-agent: Nutch\nUser-agent: *\nDisallow: /\n"
        _, report = self.run_check("--after", "--live-theme-id", "000000000000")
        check = self.by_id(report)["robots-after"]
        self.assertEqual(check["status"], lc.MISSING)
        self.assertIn("alle Crawler (*) und Googlebot", check["evidence"])

    def test_pagination_nach_dem_launch_gegen_den_mitschnitt_von_vorher(self):
        write_capture(self.ws, "old", "000000000000", [capture_run("search", "/search?q=ring", [GA4] * 3)])
        write_capture(self.ws, "after", "111111111111", [capture_run(
            "search", "/search?q=ring", [GA4] * 12, final_url="https://beispielshop.example/search?q=ring&page=6")])
        _, report = self.run_check("--after", "--live-theme-id", "000000000000")
        self.assertEqual(self.by_id(report)["pagination"]["status"], lc.MISSING)

    def test_alte_id_unbekannt_wenn_sie_schon_auf_das_neue_zeigt(self):
        _, report = self.run_check("--after", "--live-theme-id", "111111111111")
        self.assertEqual(self.by_id(report)["rollback-theme"]["status"], lc.BLOCKED)


if __name__ == "__main__":
    unittest.main()
