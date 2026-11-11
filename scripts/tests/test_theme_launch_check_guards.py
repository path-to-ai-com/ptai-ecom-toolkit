"""Launch-Check: App-Einträge, Aufrufe vor Einwilligung, Pixel-Liste, Sicherung der Custom Pixels, Kauf je Messziel.

Die fünf Prüfungen seit 11.11.2026. Kein Test geht ins Netz: der Shop ist `FakeShop`, Abrufe der
Storefront und GA4 sind gestellt, Mitschnitte und Sicherungen liegen als Dateien im Temp-Workspace.
"""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from tests import test_theme_launch as guided  # noqa: E402
from tests import test_theme_launch_check as base  # noqa: E402
from tests import test_theme_launch_check_after as after_base  # noqa: E402
from tests import theme_fake_shop as fake  # noqa: E402
from theme import apps, test_order, tracking_ids, web_pixels  # noqa: E402
from theme import launch_check as lc  # noqa: E402

RUN = "2026-10-06-launch-check"
LAYOUT = fake.fixture_files()["layout/theme.liquid"].decode("utf-8")
INJECTED = LAYOUT.replace("{{ content_for_header }}", "{{ content_for_header }}\n  {% render 'beispiel-consent-rules' %}")
CONSENT_APP = "beispiel-consent"

APP_PIXEL = {"id": "2", "type": "APP", "apiClientId": 1000002, "configuration": json.dumps({"gtag_events": [
    {"type": "purchase", "action_label": ["G-BEISPIEL01", "AW-000000000/beispielLabel"]},
    {"type": "page_view", "action_label": ["G-BEISPIEL01"]}]})}
META_PIXEL = {"id": "1", "type": "APP", "apiClientId": 1000001,
              "configuration": json.dumps({"pixel_id": "100000000000001"})}
CUSTOM_PIXEL = {"id": "3", "type": "CUSTOM", "name": "Kasse Tag Manager", "configuration": "{}"}
PIXEL_CODE = ("analytics.subscribe('checkout_completed', (event) => {\n"
              "  gtag('config', 'G-BEISPIEL2');\n"
              "  gtag('event', 'conversion', {send_to: 'AW-111111111/kaufLabel'});\n});\n")
PIXEL_NOTE = ("# Kasse Tag Manager\n\n- Pixel-ID: 3\n- Sendet: purchase mit Wert und Transaktions-ID\n"
              "- Wo: nur in der Kasse (checkout_completed)\n- An: GA4 G-BEISPIEL2, Google Ads AW-111111111/kaufLabel\n"
              "- Gesichert: 2026-10-05, gelesen von Beispiel Person\n")

UET_NET = "https://bat.bing.net/action/0?ti=000000000&evt=pageLoad"
UET_COM = "https://bat.bing.com/action/0?ti=000000000&evt=pageLoad"
GA4_PAGE = "https://region1.google-analytics.com/g/collect?v=2&tid=G-BEISPIEL01&en=page_view"


def pixel_html(pixels: list) -> str:
    """Eine Shopify-Seite mit `webPixelsConfigList` aus fertigen Einträgen."""
    return ('<html><head><script>Shopify.shop = "beispiel.myshopify.com";</script>'
            '<script id="web-pixels-manager-setup">(function e(e){})({webPixelsConfigList: '
            + json.dumps(pixels) + ', isMerchantRequest: false});</script></head><body></body></html>')


def settings(*embeds) -> bytes:
    """`settings_data.json` mit App-Embeds aus `(handle, block, disabled)`."""
    blocks = {f"b{i}": {"type": f"shopify://apps/{handle}/blocks/{block}/0000bbbb-0000-0000-0000-00000000000{i}",
                        "disabled": disabled, "settings": {}}
              for i, (handle, block, disabled) in enumerate(embeds)}
    return json.dumps({"current": {"blocks": blocks}}).encode()


def request(url: str, *, kind: str = "image", phase: str = "pre") -> dict:
    return {"url": url, "method": "GET", "resource_type": kind, "consent_phase": phase}


def run(page_id: str, requests: list, *, consent: str = "declined", html: str | None = None) -> dict:
    out = {"page_id": page_id, "path": "/" if page_id == "home" else f"/{page_id}", "template": page_id,
           "device": "desktop", "run": 1, "consent": consent, "state": "ok", "status": 200, "requests": requests}
    if html is not None:
        out["html_file"] = f"html/{page_id}.html"
        out["_html"] = html
    return out


def write_capture(ws: Path, side: str, runs: list, *, consent: str = "declined", captured_at: str | None = None) -> None:
    """Mitschnitt unter capture/<side>-<consent>/, mit HTML, wo ein Durchlauf `_html` trägt."""
    folder = ws / "reporting" / "runs" / RUN / "capture" / f"{side}-{consent}"
    (folder / "html").mkdir(parents=True, exist_ok=True)
    for item in runs:
        html = item.pop("_html", None)
        if html is not None:
            (folder / item["html_file"]).write_text(html, encoding="utf-8")
    data = {"base_url": "https://beispielshop.example", "consent_mode": consent, "runs": runs}
    if captured_at:
        data["captured_at"] = captured_at
    (folder / "network.json").write_text(json.dumps(data))


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def write_backup(ws: Path, stem: str = "kasse-tag-manager", code: str = PIXEL_CODE, note: str | None = PIXEL_NOTE):
    folder = ws / "migration" / "inventory" / "pixels"
    folder.mkdir(parents=True, exist_ok=True)
    if code is not None:
        (folder / f"{stem}.js").write_text(code, encoding="utf-8")
    if note is not None:
        (folder / f"{stem}.md").write_text(note, encoding="utf-8")


def write_before(ws: Path, pixels: list, captured_at: str = "2026-10-05T08:00:00Z", folder: str = "2026-10-05-launch-check"):
    parsed = apps.parse_web_pixels(pixel_html(pixels))
    web_pixels.save_before(ws / "reporting" / "runs" / folder / web_pixels.BEFORE_FILE, parsed, "Test", captured_at)


def write_decisions(ws: Path, *entries) -> None:
    write_json(ws / "migration" / "mapping" / "decisions.json", {"decisions": [
        {"subject": subject, "kind": "app", "decision": decision, "decided_by": "Beispiel Person",
         "decided_at": "2026-10-01", "reason": "Test"} for subject, decision in entries]})


# ---------------------------------------------------------------------------
# App-Einträge gegen den hochgeladenen Stand
# ---------------------------------------------------------------------------

class InjectionBase(base.Base):
    def set_target_repo(self, layout: str = LAYOUT, settings_data: bytes | None = None) -> None:
        config = json.loads((self.ws / "reporting" / "config.json").read_text())
        config["theme_migration"]["target_repo"] = "ziel-theme"
        (self.ws / "reporting" / "config.json").write_text(json.dumps(config))
        repo = self.ws / "ziel-theme"
        (repo / "layout").mkdir(parents=True, exist_ok=True)
        (repo / "layout" / "theme.liquid").write_text(layout, encoding="utf-8")
        if settings_data is not None:
            (repo / "config").mkdir(parents=True, exist_ok=True)
            (repo / "config" / "settings_data.json").write_bytes(settings_data)

    def write_launch(self, layout: str = LAYOUT, settings_data: bytes | None = None) -> None:
        """`launch.json` des geführten Launches samt Sicherung des Entwurfs vor dem Veröffentlichen."""
        folder = self.ws / "reporting" / "runs" / RUN
        (folder / "published-draft" / "layout").mkdir(parents=True, exist_ok=True)
        (folder / "published-draft" / "layout" / "theme.liquid").write_text(layout, encoding="utf-8")
        files = ["layout/theme.liquid"]
        if settings_data is not None:
            (folder / "published-draft" / "config").mkdir(parents=True, exist_ok=True)
            (folder / "published-draft" / "config" / "settings_data.json").write_bytes(settings_data)
            files.append("config/settings_data.json")
        write_json(folder / "launch.json", {"published": True, "new_theme_id": "111111111111",
                                            "published_at": "2026-10-06T09:00:00Z",
                                            "draft_backup": {"dir": "published-draft", "files": files}})

    def go_live(self) -> None:
        self.shop.themes[fake.LIVE_ID]["role"] = "UNPUBLISHED"
        self.shop.themes[fake.DRAFT_ID]["role"] = "MAIN"

    def after(self) -> dict:
        _, report = self.run_check("--after", "--live-theme-id", "000000000000")
        return self.by_id(report)


class TestAppEintraegeNachDemVeroeffentlichen(InjectionBase):
    def setUp(self):
        super().setUp()
        self.go_live()
        self.write_launch(settings_data=settings((CONSENT_APP, "banner", True)))
        self.shop.touch(fake.DRAFT_ID, "config/settings_data.json", settings((CONSENT_APP, "banner", True)))

    def test_gestrichene_app_traegt_sich_wieder_ein_ist_ein_befund(self):
        self.shop.touch(fake.DRAFT_ID, "layout/theme.liquid", INJECTED.encode())
        self.shop.touch(fake.DRAFT_ID, "config/settings_data.json", settings((CONSENT_APP, "banner", False)))
        write_json(self.ws / "migration" / "inventory" / "apps.json", {"integrations": [
            {"service_id": f"app:{CONSENT_APP}", "app_handle": CONSENT_APP, "decision": "replace",
             "decided_by": "Beispiel Person"}]})
        check = self.after()["app-injections-after"]
        self.assertEqual(check["status"], lc.MISSING, check["evidence"])
        self.assertIn("{% render 'beispiel-consent-rules' %}", check["evidence"])
        self.assertIn(f"App-Embed {CONSENT_APP}/banner (wieder eingeschaltet)", check["evidence"])
        self.assertIn("replace laut apps.json", check["evidence"])
        self.assertIn("published-draft", check["evidence"], "Referenz ist die Sicherung vom Veröffentlichen")
        self.assertIn("entfernt eine eingetragene Zeile nicht", check["action"])

    def test_unbekannter_eintrag_ist_eine_frage(self):
        self.shop.touch(fake.DRAFT_ID, "layout/theme.liquid", INJECTED.encode())
        check = self.after()["app-injections-after"]
        self.assertEqual(check["status"], lc.MANUAL)
        self.assertIn("beispiel-consent-rules", check["question"])
        self.assertEqual(check["owner"], lc.BOTH)

    def test_unveraendert_ist_erfuellt(self):
        check = self.after()["app-injections-after"]
        self.assertEqual(check["status"], lc.OK, check["evidence"])
        self.assertIn("keine neue Zeile", check["evidence"])

    def test_ohne_sicherung_und_ohne_ziel_repo_nicht_pruefbar(self):
        (self.ws / "reporting" / "runs" / RUN / "launch.json").unlink()
        check = self.after()["app-injections-after"]
        self.assertEqual(check["status"], lc.BLOCKED)
        self.assertIn("target_repo nicht gesetzt", check["evidence"])

    def test_ohne_sicherung_vergleicht_mit_dem_ziel_repo(self):
        (self.ws / "reporting" / "runs" / RUN / "launch.json").unlink()
        self.set_target_repo()
        self.shop.touch(fake.DRAFT_ID, "layout/theme.liquid", INJECTED.encode())
        check = self.after()["app-injections-after"]
        self.assertEqual(check["status"], lc.MANUAL)
        self.assertIn("Ziel-Repo (ziel-theme)", check["evidence"])


class TestAppEintraegeVorDemLaunch(InjectionBase):
    def test_skript_aus_shopify_files_und_eingeschaltetes_embed_im_entwurf(self):
        self.set_target_repo(settings_data=settings(("beispiel-tracker", "pixel", True)))
        script = "<script src=\"{{ 'beispiel-tracker-loader.js' | file_url }}\" defer></script>"
        self.shop.touch(fake.DRAFT_ID, "layout/theme.liquid", LAYOUT.replace("</head>", f"\n{script}\n</head>").encode())
        self.shop.touch(fake.DRAFT_ID, "config/settings_data.json", settings(("beispiel-tracker", "pixel", False)))
        _, report = self.run_check()
        check = self.by_id(report)["app-injections"]
        self.assertEqual(check["status"], lc.MANUAL, check["evidence"])
        self.assertIn("beispiel-tracker-loader.js", check["evidence"])
        self.assertIn("App-Embed beispiel-tracker/pixel (wieder eingeschaltet)", check["evidence"])
        write_decisions(self.ws, ("beispiel-tracker", "drop"))
        _, report = self.run_check()
        check = self.by_id(report)["app-injections"]
        self.assertEqual(check["status"], lc.MISSING)
        self.assertIn("drop laut decisions.json", check["evidence"])

    def test_ohne_migrationslauf_und_ohne_ziel_repo_trifft_nicht_zu(self):
        _, report = self.run_check()
        self.assertEqual(self.by_id(report)["app-injections"]["status"], lc.NA)

    def test_ein_wort_wie_cookie_ordnet_keine_app_zu(self):
        catalog = apps.HostCatalog.load()
        ctx = {"dropped": {"beispiel-consent": "beispiel-consent: drop", "google_analytics": "GA: drop"}}
        self.assertEqual(lc.injection_reason(ctx, {"beispiel-consent-rules"}, "{% render 'beispiel-consent-rules' %}"),
                         "beispiel-consent: drop")
        line = "{% render 'cookie-banner' %}"
        self.assertIsNone(lc.injection_reason(ctx, lc.line_keys(line, catalog, set()), line))
        line = '<script src="https://www.googletagmanager.com/gtag/js?id=G-BEISPIEL01"></script>'
        self.assertIsNone(lc.injection_reason(ctx, lc.line_keys(line, catalog, set()), line),
                          "google allein ist kein kennzeichnendes Wort")


class TestSicherungBeimVeroeffentlichen(guided.Base):
    def test_der_gefuehrte_launch_sichert_den_entwurf_und_after_vergleicht_damit(self):
        self.write_report(guided.GREEN)
        code, out = self.launch("publish", "--approved-by", guided.PERSON, runner=self.runner())
        self.assertEqual(code, 0, out)
        run_dir = self.ws / "reporting" / "runs" / guided.TODAY_RUN
        record = json.loads((run_dir / "launch.json").read_text())
        self.assertEqual(record["draft_backup"]["files"], ["config/settings_data.json", "layout/theme.liquid"])
        self.assertEqual((run_dir / "published-draft" / "layout" / "theme.liquid").read_bytes(),
                         fake.fixture_files()["layout/theme.liquid"])
        # Die App trägt sich beim Veröffentlichen ein.
        self.shop.touch(fake.DRAFT_ID, "layout/theme.liquid", INJECTED.encode())
        self.launch("check", "--after")
        report = json.loads((run_dir / "launch-check-after.json").read_text())
        check = {c["id"]: c for c in report["checks"]}["app-injections-after"]
        self.assertEqual(check["status"], lc.MANUAL, check["evidence"])
        self.assertIn("Sicherung des Entwurfs vor dem Veröffentlichen", check["evidence"])
        self.assertFalse([c for c in self.shop.calls if c[2]], "die Sicherung liest nur")

    def test_scheitert_die_sicherung_wird_trotzdem_veroeffentlicht(self):
        self.write_report(guided.GREEN)
        original = self.shop.op_ThemeFilesByName

        def broken(variables):
            if variables["id"] == fake.DRAFT_ID:
                raise lc.ShopifyError("kein Zugriff")
            return original(variables)
        self.shop.op_ThemeFilesByName = broken
        code, out = self.launch("publish", "--approved-by", guided.PERSON, runner=self.runner())
        self.assertEqual(code, 0, out)
        record = json.loads((self.ws / "reporting" / "runs" / guided.TODAY_RUN / "launch.json").read_text())
        self.assertIn("kein Zugriff", record["draft_backup"]["error"])


# ---------------------------------------------------------------------------
# Werbung und Analyse vor Einwilligung
# ---------------------------------------------------------------------------

class TestVorEinwilligung(base.Base):
    def test_microsoft_ueber_bat_bing_net_vor_der_einwilligung_ist_ein_befund(self):
        write_capture(self.ws, "old", [run("home", [request(GA4_PAGE)])])
        write_capture(self.ws, "new", [run("home", [request(GA4_PAGE), request(UET_NET)])])
        _, report = self.run_check()
        check = self.by_id(report)["tracking-pre-consent"]
        self.assertEqual(check["status"], lc.MISSING, check["evidence"])
        self.assertIn("Microsoft Advertising (UET) an bat.bing.net (home)", check["evidence"])
        self.assertIn("Google Analytics 4", check["evidence"].split("wie im alten Theme")[1])

    def test_bat_bing_com_vorher_und_bat_bing_net_nachher_ist_derselbe_dienst(self):
        write_capture(self.ws, "old", [run("home", [request(UET_COM)])])
        write_capture(self.ws, "new", [run("home", [request(UET_NET)])])
        _, report = self.run_check()
        check = self.by_id(report)["tracking-pre-consent"]
        self.assertEqual(check["status"], lc.OK, check["evidence"])
        self.assertIn("wie im alten Theme: Microsoft Advertising (UET)", check["evidence"])

    def test_im_durchlauf_mit_einwilligung_zaehlt_nur_was_vor_dem_klick_kam(self):
        write_capture(self.ws, "old", [run("home", [])])
        write_capture(self.ws, "new", [run("home", [])])
        write_capture(self.ws, "old", [run("home", [], consent="accepted")], consent="accepted")
        write_capture(self.ws, "new", [run("home", [request(UET_NET, phase="post")], consent="accepted")],
                      consent="accepted")
        _, report = self.run_check()
        self.assertEqual(self.by_id(report)["tracking-pre-consent"]["status"], lc.OK)
        write_capture(self.ws, "new", [run("home", [request(UET_NET, phase="pre")], consent="accepted")],
                      consent="accepted")
        _, report = self.run_check()
        self.assertEqual(self.by_id(report)["tracking-pre-consent"]["status"], lc.MISSING)

    def test_nur_geladen_ohne_zu_senden_ist_ein_hinweis(self):
        write_capture(self.ws, "old", [run("home", [])])
        write_capture(self.ws, "new", [run("home", [request("https://bat.bing.com/bat.js", kind="script")])])
        _, report = self.run_check()
        check = self.by_id(report)["tracking-pre-consent"]
        self.assertEqual(check["status"], lc.OK)
        self.assertIn("lädt neu vor der Einwilligung, ohne zu senden: Microsoft Advertising", check["evidence"])

    def test_nach_dem_launch_gegen_den_mitschnitt_von_vorher(self):
        self.shop.themes[fake.LIVE_ID]["role"] = "UNPUBLISHED"
        self.shop.themes[fake.DRAFT_ID]["role"] = "MAIN"
        write_capture(self.ws, "old", [run("home", [])])
        write_capture(self.ws, "after", [run("product", []), run("home", [request(UET_NET)])])
        _, report = self.run_check("--after", "--live-theme-id", "000000000000")
        self.assertEqual(self.by_id(report)["tracking-pre-consent-after"]["status"], lc.MISSING)

    def test_ohne_mitschnitt_nicht_pruefbar(self):
        _, report = self.run_check()
        self.assertEqual(self.by_id(report)["tracking-pre-consent"]["status"], lc.BLOCKED)


class TestBeideMicrosoftHosts(unittest.TestCase):
    def test_katalog_mitschnitt_und_testbestellung_kennen_bat_bing_net(self):
        catalog = apps.HostCatalog.load()
        self.assertEqual(catalog.service_for("bat.bing.net"), "microsoft_ads")
        self.assertEqual(catalog.service_for("bat.bing.com"), "microsoft_ads")
        self.assertEqual(tracking_ids.request_targets(UET_NET)[0]["target_id"], "UET:000000000")
        hit = test_order.parse_hits({"url": "https://bat.bing.net/action/0?ti=000000000&evt=custom&ea=purchase&gv=1"})
        self.assertEqual(hit[0]["service"], "microsoft_ads")


# ---------------------------------------------------------------------------
# Pixel-Liste und Sicherung der Custom Pixels
# ---------------------------------------------------------------------------

class TestPixelListeVorDemLaunch(base.Base):
    def test_liste_aus_dem_mitschnitt_wird_festgehalten(self):
        write_capture(self.ws, "old", [run("home", [], html=pixel_html([META_PIXEL, APP_PIXEL, CUSTOM_PIXEL]))])
        _, report = self.run_check()
        check = self.by_id(report)["web-pixels"]
        self.assertEqual(check["status"], lc.OK, check["evidence"])
        self.assertIn("3 Pixel aus HTML des Mitschnitts", check["evidence"])
        self.assertIn("Custom Pixel „Kasse Tag Manager“ (3)", check["evidence"])
        saved = web_pixels.load_before(self.ws / "reporting" / "runs" / RUN / web_pixels.BEFORE_FILE)
        self.assertEqual([p["id"] for p in saved["pixels"]], ["1", "2", "3"])
        self.assertTrue(saved["captured_at"])

    def test_ohne_mitschnitt_aus_dem_abruf_der_startseite(self):
        self.fetch = lambda url: (200, {}, pixel_html([APP_PIXEL]))
        _, report = self.run_check()
        check = self.by_id(report)["web-pixels"]
        self.assertEqual(check["status"], lc.OK)
        self.assertIn("Abruf von https://beispielshop.example/", check["evidence"])

    def test_ohne_liste_nicht_pruefbar(self):
        _, report = self.run_check()
        check = self.by_id(report)["web-pixels"]
        self.assertEqual(check["status"], lc.BLOCKED)
        self.assertIn("webPixelsConfigList weder", check["evidence"])


class TestSicherungDerCustomPixels(base.Base):
    def setUp(self):
        super().setUp()
        self.fetch = lambda url: (200, {}, pixel_html([APP_PIXEL, CUSTOM_PIXEL]))
        write_json(self.ws / "migration" / "inventory" / "apps.json", {"integrations": [
            {"integration_id": "web_pixel:3", "service_id": "custom_pixel:3", "service_name": "Custom Pixel 3",
             "integration_type": "web_pixel_custom", "location": {"pixel_id": "3", "pixel_name": "Kasse Tag Manager"},
             "decision": "drop",
             "decided_by": "Beispiel Person"}]})

    def check(self) -> dict:
        _, report = self.run_check()
        return self.by_id(report)["custom-pixel-backup"]

    def test_entfernen_ohne_sicherung_blockiert_den_go(self):
        check = self.check()
        self.assertEqual(check["status"], lc.MISSING)
        self.assertIn("Custom Pixel „Kasse Tag Manager“ (3): Custom Pixel 3: drop laut apps.json", check["evidence"])
        self.assertIn("keine Sicherung unter migration/inventory/pixels/", check["evidence"])
        self.assertIn("migration/inventory/pixels/<name>.js", check["action"])

    def test_gesichert_aber_nicht_gelesen_ist_ein_befund(self):
        write_backup(self.ws, note="# Kasse Tag Manager\n\n- Pixel-ID: 3\n- Sendet: purchase\n")
        check = self.check()
        self.assertEqual(check["status"], lc.MISSING)
        self.assertIn("nicht gelesen", check["evidence"])
        self.assertIn("fehlt Wo, An", check["evidence"])
        write_backup(self.ws, note=None, code="")
        (self.ws / "migration" / "inventory" / "pixels" / "kasse-tag-manager.md").unlink()
        self.assertIn("leer", self.check()["evidence"])

    def test_gesichert_und_gelesen_ist_erfuellt(self):
        write_backup(self.ws)
        check = self.check()
        self.assertEqual(check["status"], lc.OK, check["evidence"])
        self.assertIn("gesichert in migration/inventory/pixels/kasse-tag-manager.js", check["evidence"])
        self.assertIn("wo nur in der Kasse", check["evidence"])

    def test_bleibendes_pixel_braucht_keine_sicherung_steht_aber_im_beleg(self):
        write_json(self.ws / "migration" / "inventory" / "apps.json", {"integrations": [
            {"integration_id": "web_pixel:3", "service_id": "custom_pixel:3", "integration_type": "web_pixel_custom",
             "location": {"pixel_id": "3"}, "decision": "keep"}]})
        check = self.check()
        self.assertEqual(check["status"], lc.OK)
        self.assertIn("bleiben, noch ohne Sicherung: Custom Pixel „Kasse Tag Manager“ (3)", check["evidence"])

    def test_ohne_custom_pixel_trifft_nicht_zu(self):
        self.fetch = lambda url: (200, {}, pixel_html([APP_PIXEL]))
        (self.ws / "migration" / "inventory" / "apps.json").unlink()
        self.assertEqual(self.check()["status"], lc.NA)


class TestPixelListeNachDemLaunch(base.Base):
    def setUp(self):
        super().setUp()
        self.shop.themes[fake.LIVE_ID]["role"] = "UNPUBLISHED"
        self.shop.themes[fake.DRAFT_ID]["role"] = "MAIN"
        write_before(self.ws, [META_PIXEL, APP_PIXEL, CUSTOM_PIXEL])

    def check(self, live: list) -> dict:
        self.fetch = lambda url: (200, {}, pixel_html(live))
        _, report = self.run_check("--after", "--live-theme-id", "000000000000")
        return self.by_id(report)["web-pixels-after"]

    def test_entferntes_custom_pixel_ohne_entscheidung_ist_ein_befund(self):
        check = self.check([META_PIXEL, APP_PIXEL])
        self.assertEqual(check["status"], lc.MISSING, check["evidence"])
        self.assertIn("Custom Pixel „Kasse Tag Manager“ (3): ohne Entscheidung entfernt", check["evidence"])
        self.assertIn("web-pixels-before.json vom 2026-10-05", check["evidence"])

    def test_bewusst_entfernt_und_gesichert_ist_erfuellt(self):
        write_decisions(self.ws, ("Kasse Tag Manager", "drop"))
        write_backup(self.ws)
        check = self.check([META_PIXEL, APP_PIXEL])
        self.assertEqual(check["status"], lc.OK, check["evidence"])
        self.assertIn("bewusst entfernt: Custom Pixel „Kasse Tag Manager“ (3)", check["evidence"])

    def test_bewusst_entfernt_aber_nicht_gesichert_ist_ein_befund(self):
        write_decisions(self.ws, ("Kasse Tag Manager", "drop"))
        check = self.check([META_PIXEL, APP_PIXEL])
        self.assertEqual(check["status"], lc.MISSING)
        self.assertIn("aber nicht gesichert", check["evidence"])

    def test_entferntes_app_pixel_nennt_seine_ziele(self):
        check = self.check([META_PIXEL, CUSTOM_PIXEL])
        self.assertEqual(check["status"], lc.MISSING)
        self.assertIn("App-Pixel 2 (App 1000002), Ziele G-BEISPIEL01, AW-000000000/beispielLabel", check["evidence"])

    def test_pixel_ohne_ein_messziel_von_vorher_ist_eine_frage(self):
        reduced = dict(APP_PIXEL, configuration=json.dumps({"gtag_events": [
            {"type": "page_view", "action_label": ["G-BEISPIEL01"]}]}))
        check = self.check([META_PIXEL, reduced, CUSTOM_PIXEL])
        self.assertEqual(check["status"], lc.MANUAL, check["evidence"])
        self.assertIn("sendet nicht mehr an AW-000000000/beispielLabel", check["evidence"])

    def test_gleiche_liste_ist_erfuellt(self):
        self.assertEqual(self.check([CUSTOM_PIXEL, APP_PIXEL, META_PIXEL])["status"], lc.OK)

    def test_liste_von_nach_dem_launch_zaehlt_nicht_als_vorher(self):
        (self.ws / "reporting" / "runs" / "2026-10-05-launch-check" / web_pixels.BEFORE_FILE).unlink()
        write_before(self.ws, [META_PIXEL, APP_PIXEL], captured_at="2026-10-06T10:00:00Z", folder=RUN)
        write_json(self.ws / "reporting" / "runs" / RUN / "launch.json",
                   {"published": True, "new_theme_id": "111111111111", "published_at": "2026-10-06T09:00:00Z"})
        check = self.check([META_PIXEL, APP_PIXEL])
        self.assertEqual(check["status"], lc.BLOCKED, check["evidence"])
        # Der Mitschnitt des alten Themes von vorher trägt die Liste noch.
        write_capture(self.ws, "old", [run("home", [], html=pixel_html([META_PIXEL, APP_PIXEL, CUSTOM_PIXEL]))],
                      captured_at="2026-10-06T07:00:00Z")
        check = self.check([META_PIXEL, APP_PIXEL])
        self.assertEqual(check["status"], lc.MISSING, check["evidence"])
        self.assertIn("HTML des Mitschnitts des alten Themes", check["evidence"])


class TestSicherungLesen(unittest.TestCase):
    def test_notiz_und_zuordnung_ueber_pixel_id_oder_dateinamen(self):
        note = web_pixels.parse_note(PIXEL_NOTE)
        self.assertEqual((note["pixel_id"], note["where"]), ("3", "nur in der Kasse (checkout_completed)"))
        self.assertEqual(note["title"], "Kasse Tag Manager")
        self.assertEqual(web_pixels.slug("Kasse / Übersicht & GTM"), "kasse-uebersicht-gtm")
        backups = [{"stem": "anders", "pixel_id": "3"}, {"stem": "kasse-tag-manager", "pixel_id": None}]
        self.assertEqual(web_pixels.find_backup(backups, "3")["stem"], "anders")
        self.assertEqual(web_pixels.find_backup(backups, "9", "Kasse Tag Manager")["stem"], "kasse-tag-manager")
        self.assertIsNone(web_pixels.find_backup(backups, "9", "Anderes Pixel"))


# ---------------------------------------------------------------------------
# Kauf je GA4-Property und Google-Ads-Conversion
# ---------------------------------------------------------------------------

GA4_PURCHASE = ("https://region1.google-analytics.com/g/collect?v=2&tid=G-BEISPIEL01",
                "en=purchase&ep.transaction_id=%231001&epn.value=49.9&cu=EUR")
ADS_PURCHASE = ("https://www.googleadservices.com/pagead/conversion/000000000/?label=beispielLabel&value=49.9", None)


class TestKaufJeMessziel(after_base.AfterBase):
    def setUp(self):
        super().setUp()
        write_before(self.ws, [APP_PIXEL, CUSTOM_PIXEL])
        write_backup(self.ws)

    def test_jede_property_und_jede_conversion_ist_ein_eigenes_ziel(self):
        self.write_walk(requests=[GA4_PURCHASE, ADS_PURCHASE])
        self.order()
        checks, _ = self.after()
        self.assertIn("GA4-Properties: G-BEISPIEL01, G-BEISPIEL2", checks["test-order"]["evidence"])
        self.assertEqual(checks["purchase-ga4-g-beispiel01"]["status"], lc.OK)
        missing = checks["purchase-ga4-g-beispiel2"]
        self.assertEqual(missing["status"], lc.MISSING, missing["evidence"])
        self.assertIn("kein Kauf-Aufruf an G-BEISPIEL2", missing["evidence"])
        self.assertIn("gesichertes Custom Pixel (migration/inventory/pixels/kasse-tag-manager.js)", missing["evidence"])
        self.assertEqual(checks["purchase-google-ads-000000000-beispiellabel"]["status"], lc.OK)
        self.assertEqual(checks["purchase-google-ads-111111111-kauflabel"]["status"], lc.MISSING)
        self.assertEqual(checks["purchase-google-analytics"]["status"], lc.OK, "ein Kauf an GA4 kam an")

    def test_ohne_durchlauf_je_messziel_nicht_pruefbar(self):
        checks, _ = self.after()
        for cid in ("purchase-ga4-g-beispiel01", "purchase-ga4-g-beispiel2", "purchase-google-ads-111111111-kauflabel"):
            self.assertEqual(checks[cid]["status"], lc.BLOCKED, cid)

    def test_serverseitig_ohne_browser_aufruf_eine_frage_je_property(self):
        self.write_apps([{"service_id": "google_analytics"}, {"service_id": "littledata", "service_name": "Littledata"}])
        self.write_walk(requests=[GA4_PURCHASE])
        self.order()
        checks, _ = self.after()
        check = checks["purchase-ga4-g-beispiel2"]
        self.assertEqual(check["status"], lc.MANUAL)
        self.assertIn("GA4-Property G-BEISPIEL2", check["question"])
        self.assertIn("Echtzeitbericht", check["question"])

    def test_gestrichene_property_ist_kein_ziel(self):
        write_decisions(self.ws, ("G-BEISPIEL2", "drop"))
        self.write_walk(requests=[GA4_PURCHASE])
        self.order()
        checks, _ = self.after()
        self.assertNotIn("purchase-ga4-g-beispiel2", checks)
        self.assertIn("purchase-ga4-g-beispiel01", checks)

    def test_conversion_nur_aus_der_kasse_macht_google_ads_zum_ziel(self):
        self.write_apps([{"service_id": "google_analytics"}])
        self.write_walk(requests=[GA4_PURCHASE])
        self.order()
        checks, _ = self.after()
        self.assertIn("purchase-google-ads", checks)
        self.assertIn("Messziele vor dem Launch", checks["purchase-google-ads"]["evidence"])
        self.assertEqual(checks["purchase-google-ads-111111111-kauflabel"]["status"], lc.MISSING)

    def test_config_mit_ids_legt_die_properties_fest(self):
        config = json.loads((self.ws / "reporting" / "config.json").read_text())
        config["theme_migration"]["purchase_destinations"] = {"google_analytics": {"ids": ["G-BEISPIEL01"]}}
        (self.ws / "reporting" / "config.json").write_text(json.dumps(config))
        self.write_walk(requests=[GA4_PURCHASE])
        self.order()
        checks, _ = self.after()
        self.assertEqual(checks["purchase-ga4-g-beispiel01"]["status"], lc.OK)
        self.assertNotIn("purchase-ga4-g-beispiel2", checks)
        self.assertNotIn("purchase-google-ads", checks, "die Config gewinnt")

    def test_property_nur_aus_totem_theme_code_ist_kein_ziel(self):
        self.write_apps([{"service_id": "google_analytics"}, {"service_id": "google_ads"},
                         {"integration_id": "theme_code:snippets/alt.liquid", "service_id": "google_analytics",
                          "state": "leftover"}])
        write_json(self.ws / "migration" / "inventory" / "tracking.json", {"targets": [
            {"target_id": "G-BEISPIEL3", "kind": "ga4", "senders": [{"integration_id": None, "basis": "network"}]},
            {"target_id": "G-BEISPIEL4", "kind": "ga4", "senders": [
                {"integration_id": "theme_code:snippets/alt.liquid", "basis": "config"}]}]})
        self.write_walk(requests=[GA4_PURCHASE])
        self.order()
        checks, _ = self.after()
        self.assertEqual(checks["purchase-ga4-g-beispiel3"]["status"], lc.MISSING)
        self.assertIn("Bestandsaufnahme (tracking.json)", checks["purchase-ga4-g-beispiel3"]["evidence"])
        self.assertNotIn("purchase-ga4-g-beispiel4", checks, "ein Rest ohne lebenden Absender bekommt keinen Kauf")


if __name__ == "__main__":
    unittest.main()
