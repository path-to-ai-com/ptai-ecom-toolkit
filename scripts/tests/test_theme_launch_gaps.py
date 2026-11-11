"""Drei Lücken aus der Vorbereitung des nächsten Launches, geschlossen in 0.3.31.

1. Das Untermenü am Rechner: Der Bildvergleich öffnete das Menü nur am Handy. Bei einem Shop, der auf
   Horizon umzog, war das Mega-Menü am Rechner nach dem Launch kaputt.
2. Ein Bildvergleich nach dem letzten Abgleich vor G5: Nach G4 verlangte kein Schritt mehr Bilder, und der
   Abgleich vor dem Launch ließ eine dunkle leere Leiste im Entwurf.
3. E-Mail-Tools vor der Einwilligung: Der Check zählte nur Werbung, Analyse und Sitzungsaufzeichnung; ein
   E-Mail-Tool lud auch nach „Ablehnen“.

Kein Test geht ins Netz.
"""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "browser"))

import compose  # noqa: E402
import shoot_pair  # noqa: E402
from tests import test_theme_launch_check as base  # noqa: E402
from tests import test_theme_launch_check_guards as guards  # noqa: E402
from tests import visual_compare_support as vcs  # noqa: E402
from theme import launch_check as lc  # noqa: E402
from theme import open_items, run_state  # noqa: E402
from theme import visual_compare as vc  # noqa: E402

SUBMENU = {"state": "ok", "file": "home/desktop-b-menu.png", "points": 240, "foreign": [], "opened_by": "hover",
           "toggle": "header nav [aria-haspopup]:not([aria-haspopup='dialog'])",
           "drawer": {"label": "div.mega-menu", "z_index": "auto"}}
BAR = {"label": "div#beispiel-leiste", "z_index": "1000", "points": 40, "share": 0.167, "text": "Nur heute"}


def desktop_pair(menu_a=SUBMENU, menu_b=SUBMENU) -> dict:
    a = vcs.shot(vcs.LIVE, "desktop", "main", **({"menu": menu_a} if menu_a is not None else {}))
    b = vcs.shot(vcs.DRAFT, "desktop", **({"menu": menu_b} if menu_b is not None else {}))
    return {"page_id": "home", "device": "desktop", "a": a, "b": b}


class TestUntermenueAmRechner(unittest.TestCase):
    def test_oeffnet_es_sich_links_und_rechts_nicht_haelt_g4_an(self):
        problem, note = vc.menu_problem(desktop_pair(menu_b={"state": "no_drawer"}), "desktop")
        self.assertIn("Untermenü offen: nach Zeigen und Klick kein Untermenü sichtbar im Entwurf", problem)
        self.assertIn("--menu-toggle-desktop", problem)
        self.assertIsNone(note)

    def test_in_beiden_themes_keins_ist_ein_hinweis(self):
        problem, note = vc.menu_problem(desktop_pair(menu_a={"state": "no_toggle"}, menu_b={"state": "no_toggle"}),
                                        "desktop")
        self.assertIsNone(problem)
        self.assertIn("in beiden Themes kein Untermenü gefunden", note)

    def test_nicht_aufgenommen_zaehlt_nicht(self):
        problem, _ = vc.menu_problem(desktop_pair(menu_b=None), "desktop")
        self.assertIn("Untermenü offen nicht aufgenommen", problem)
        self.assertIn("0.3.31", problem)

    def test_fremdes_element_ueber_dem_untermenue(self):
        problem, _ = vc.menu_problem(desktop_pair(menu_b={**SUBMENU, "state": "overlap", "foreign": [BAR]}), "desktop")
        self.assertIn("fremde Elemente über dem Untermenü: div#beispiel-leiste (z-index 1000", problem)

    def test_abdeckung_zaehlt_das_untermenue_am_rechner(self):
        slots = {("home", "desktop"): desktop_pair(menu_b={"state": "no_drawer"}),
                 ("home", "mobile"): {"a": vcs.shot(vcs.LIVE, "mobile", "main", menu=vcs.MENU_OK),
                                      "b": vcs.shot(vcs.DRAFT, "mobile", menu=vcs.MENU_OK)}}
        cover = vc.coverage(["home"], slots, lambda _p: {"a": vcs.LIVE, "b": vcs.DRAFT})
        self.assertEqual([(m["device"], m["side"]) for m in cover["missing"]], [("desktop", "b")])
        self.assertTrue(cover["missing"][0]["reason"].startswith(vc.MENU_PREFIX["desktop"]))

    def test_aufnahme_am_rechner_sucht_menuepunkte_mit_untermenue(self):
        self.assertEqual(shoot_pair.menu_name("home", "b", "desktop"), "home/desktop-b-menu.png")
        self.assertEqual(shoot_pair.menu_name("home", "b"), "home/mobile-b-menu.png")
        self.assertIn("header nav details > summary", shoot_pair.DESKTOP_MENU_TRIGGERS)
        self.assertTrue(all("dialog" not in s or ":not([aria-haspopup='dialog'])" in s
                            for s in shoot_pair.DESKTOP_MENU_TRIGGERS))
        self.assertIn("safe_click", shoot_pair.MENU_PREPARE_JS)
        self.assertLess(shoot_pair.MENU_MIN_SHARE["desktop"], shoot_pair.MENU_MIN_SHARE["mobile"])

    def test_klick_nur_ohne_linkziel(self):
        page = FakePage(prepare={"selector": "header li:has(ul a) > a", "safe_click": False},
                        probes=[{"state": "no_drawer"}])
        with tempfile.TemporaryDirectory() as tmp:
            result = shoot_pair.shoot_menu(page, Path(tmp), "home", "b", shoot_pair.DESKTOP_MENU_TRIGGERS, 0, "desktop")
        self.assertEqual(page.actions, ["hover"])
        self.assertEqual(result["state"], "no_drawer")
        self.assertEqual(result["file"], "home/desktop-b-menu.png")

    def test_oeffnet_zeigen_nichts_wird_geklickt(self):
        page = FakePage(prepare={"selector": "header nav details > summary", "safe_click": True},
                        probes=[{"state": "no_drawer"}, {"state": "ok", "foreign": [], "points": 240}])
        with tempfile.TemporaryDirectory() as tmp:
            result = shoot_pair.shoot_menu(page, Path(tmp), "home", "a", shoot_pair.DESKTOP_MENU_TRIGGERS, 0, "desktop")
        self.assertEqual(page.actions, ["hover", "click"])
        self.assertEqual((result["state"], result["opened_by"]), ("ok", "click"))
        self.assertEqual(page.probe_args[0][:2], list(shoot_pair.DESKTOP_MENU_GRID))

    def test_vergleichsseite_zeigt_untermenue_offen(self):
        data = {"themes": {"a": vcs.LIVE, "b": vcs.DRAFT}, "pairs": [desktop_pair()]}
        out = compose.render(data, Path("."), Path("."))
        self.assertIn("Rechner, 1440 px (Chromium), Untermenü offen</h3>", out)
        self.assertIn("home/desktop-b-menu.png", out)


class FakeLocator:
    def __init__(self, page):
        self.page = page
        self.first = self

    def hover(self, timeout=None):
        self.page.actions.append("hover")

    def click(self, timeout=None):
        self.page.actions.append("click")


class FakePage:
    """Genug von Playwrights Seite für `shoot_menu`: Vorbereitung, Zeigen, Klick, Prüfung, Bild."""

    def __init__(self, prepare, probes):
        self.prepare, self.probes, self.actions, self.probe_args = prepare, list(probes), [], []

    def wait_for_timeout(self, ms):
        pass

    def evaluate(self, script, args):
        if script == shoot_pair.MENU_PREPARE_JS:
            return self.prepare
        self.probe_args.append(args)
        return self.probes.pop(0)

    def locator(self, selector):
        return FakeLocator(self)

    def screenshot(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_bytes(b"")


class TestBildvergleichNachDemAbgleich(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.ws = Path(tmp.name)
        vcs.write_pages(self.ws)
        self.config = {"theme_migration": {"live_theme_id": vcs.LIVE, "draft_theme_id": vcs.DRAFT}}

    def test_ohne_abgleich_haelt_g5_an(self):
        vcs.write_record(self.ws, vcs.record())
        problems = vc.gate_problems_after_sync(self.ws, self.config, {})
        self.assertIn("kein Abgleich mit dem Live-Theme festgehalten", problems[0])
        self.assertIn("shoot_pair.py --a 000000000004 --b 000000000002", problems[0])

    def test_vergleich_vor_dem_abgleich_zaehlt_nicht(self):
        vcs.write_record(self.ws, vcs.record(captured_at="2026-11-11T09:00:00+00:00"))
        vcs.write_sync(self.ws, captured_at="2026-11-11T09:30:00Z")
        problems = vc.gate_problems_after_sync(self.ws, self.config, {})
        self.assertIn("nach dem letzten Abgleich (2026-11-11T09:30:00Z, migration/sync/2026-11-11/delta.json)",
                      problems[0])
        self.assertIn("8 von 8 Aufnahmen fehlen", problems[0])
        # G4 sieht denselben Vergleich weiter als vollständig an.
        self.assertEqual(vc.gate_problems(self.ws, self.config, {}), [])

    def test_vergleich_nach_dem_abgleich_haelt_nicht_an(self):
        vcs.write_sync(self.ws, captured_at="2026-11-11T08:00:00Z")
        vcs.write_record(self.ws, vcs.record(captured_at="2026-11-11T09:00:00+01:00"))
        self.assertEqual(vc.gate_problems_after_sync(self.ws, self.config, {}), [])

    def test_last_sync_im_lauf_gilt_wenn_es_spaeter_ist(self):
        vcs.write_sync(self.ws, captured_at="2026-11-10T08:00:00Z", day="2026-11-10")
        vcs.write_record(self.ws, vcs.record(captured_at="2026-11-10T09:00:00+00:00"), day="2026-11-10")
        sync = vc.last_sync(self.ws, self.config, {"last_sync": "2026-11-11"})
        self.assertEqual((sync["label"], sync["source"]), ("2026-11-11", "last_sync im Lauf"))
        self.assertTrue(vc.gate_problems_after_sync(self.ws, self.config, {"last_sync": "2026-11-11"}))

    def test_abgleich_eines_anderen_live_themes_zaehlt_nicht(self):
        vcs.write_sync(self.ws, captured_at="2026-11-11T08:00:00Z", live="000000000009")
        self.assertIsNone(vc.last_sync(self.ws, self.config, {}))

    def test_check_after_sync_auf_der_kommandozeile(self):
        (self.ws / "reporting").mkdir()
        (self.ws / "reporting" / "config.json").write_text(json.dumps(self.config), encoding="utf-8")
        vcs.write_sync(self.ws, captured_at="2026-11-11T08:00:00Z")
        vcs.write_record(self.ws, vcs.record(captured_at="2026-11-11T07:00:00+00:00"))
        with contextlib.redirect_stdout(io.StringIO()) as out:
            code = vc.main(["check", "--after-sync", "--workspace", str(self.ws)])
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(out.getvalue())["last_sync"]["at"], "2026-11-11T08:00:00Z")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(vc.main(["check", "--workspace", str(self.ws)]), 0)


class TestG5MitBildvergleich(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.ws = Path(tmp.name)
        patcher = mock.patch.dict(os.environ, {}, clear=False)
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop("PTAI_OPERATOR", None)
        (self.ws / "reporting").mkdir()
        (self.ws / "checklist.md").write_text("- [x] **P01** erledigt\n", encoding="utf-8")
        config = {"theme_migration": {"live_theme_id": vcs.LIVE, "draft_theme_id": vcs.DRAFT,
                                      "acceptance_checklist": "checklist.md"}}
        (self.ws / "reporting" / "config.json").write_text(json.dumps(config), encoding="utf-8")
        vcs.write_pages(self.ws)
        open_items.init(self.ws)
        self.state = run_state.new(self.ws, "2026-01-01-migration")

    def test_open_items_gate_g5_nennt_den_bildvergleich(self):
        vcs.write_record(self.ws, vcs.record(captured_at="2026-11-11T07:00:00+00:00"))
        vcs.write_sync(self.ws, captured_at="2026-11-11T08:00:00Z")
        with contextlib.redirect_stdout(io.StringIO()) as out:
            code = open_items.main(["gate", "--gate", "G5-go-live", "--workspace", str(self.ws)])
        result = json.loads(out.getvalue())
        self.assertEqual(code, 1)
        self.assertFalse(result["visual_after_sync"]["ok"])
        self.assertIn("nach dem letzten Abgleich", result["visual_after_sync"]["problems"][0])

    def test_run_state_g5_haelt_an_bis_nach_dem_abgleich_verglichen_ist(self):
        vcs.write_sync(self.ws, captured_at="2026-11-11T08:00:00Z")
        with self.assertRaises(run_state.StateError) as ctx:
            self.state.decide_gate("G5-go-live", "Beispielperson")
        self.assertIn("Gate G5-go-live hält an", str(ctx.exception))
        vcs.write_record(self.ws, vcs.record(captured_at="2026-11-11T09:00:00+00:00"))
        self.state.decide_gate("G5-go-live", "Beispielperson")
        self.assertEqual(self.state.data["gates"]["G5-go-live"]["decided_by"], "Beispielperson")


KLAVIYO_JS = "https://static.klaviyo.com/onsite/js/klaviyo.js?company_id=BeispielID"
KLAVIYO_EVENT = "https://a.klaviyo.com/client/events/?company_id=BeispielID"


class TestEmailToolVorEinwilligung(base.Base):
    def test_e_mail_tool_laedt_neu_vor_der_einwilligung(self):
        guards.write_capture(self.ws, "old", [guards.run("home", [guards.request(guards.GA4_PAGE)])])
        guards.write_capture(self.ws, "new", [guards.run("home", [guards.request(guards.GA4_PAGE),
                                                                   guards.request(KLAVIYO_JS, kind="script")])])
        _, report = self.run_check()
        check = self.by_id(report)["tracking-pre-consent"]
        self.assertEqual(check["status"], lc.MISSING, check["evidence"])
        self.assertIn("E-Mail-Tool lädt neu vor der Einwilligung", check["evidence"])
        self.assertIn("static.klaviyo.com", check["evidence"])
        self.assertIn("Einwilligung in Marketing", check["action"])
        self.assertEqual(list(check["details"]["loads_counted"]), ["klaviyo"])

    def test_e_mail_tool_sendet_neu_vor_der_einwilligung(self):
        guards.write_capture(self.ws, "old", [guards.run("home", [])])
        event = {"url": KLAVIYO_EVENT, "method": "POST", "resource_type": "fetch", "consent_phase": "pre"}
        guards.write_capture(self.ws, "new", [guards.run("home", [event])])
        _, report = self.run_check()
        check = self.by_id(report)["tracking-pre-consent"]
        self.assertEqual(check["status"], lc.MISSING, check["evidence"])
        self.assertIn("sendet neu vor der Einwilligung", check["evidence"])

    def test_e_mail_tool_erst_nach_dem_klick_ist_in_ordnung(self):
        guards.write_capture(self.ws, "old", [guards.run("home", [])])
        guards.write_capture(self.ws, "new", [guards.run("home", [])])
        guards.write_capture(self.ws, "old", [guards.run("home", [], consent="accepted")], consent="accepted")
        guards.write_capture(self.ws, "new", [guards.run("home", [guards.request(KLAVIYO_JS, kind="script",
                                                                                 phase="post")],
                                                         consent="accepted")], consent="accepted")
        _, report = self.run_check()
        self.assertEqual(self.by_id(report)["tracking-pre-consent"]["status"], lc.OK)

    def test_werbeskript_ohne_messaufruf_bleibt_ein_hinweis(self):
        guards.write_capture(self.ws, "old", [guards.run("home", [])])
        guards.write_capture(self.ws, "new", [guards.run("home", [guards.request("https://bat.bing.com/bat.js",
                                                                                 kind="script")])])
        _, report = self.run_check()
        self.assertEqual(self.by_id(report)["tracking-pre-consent"]["status"], lc.OK)

    def test_kategorien(self):
        self.assertIn("email_sms", lc.PRE_CONSENT_CATEGORIES)
        self.assertEqual(lc.LOAD_COUNTS_CATEGORIES, ("email_sms",))


if __name__ == "__main__":
    unittest.main()
