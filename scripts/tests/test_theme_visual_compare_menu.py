"""Bildvergleich vor G4: Handy mit offenem Menü und Referenz-Theme mit ID und Name.

Nachtrag vom 11.11.2026: Am Handy lagen ein Teaser und eine Countdown-Leiste über der Menü-Schublade, und
Schriften wurden gegen ein älteres Theme verglichen statt gegen das veröffentlichte. Ohne Browser: geprüft
wird die Auswertung dessen, was `shoot_pair.py` schreibt, und die Vergleichsseite.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "browser"))

import compose  # noqa: E402
import shoot_pair  # noqa: E402
from tests import visual_compare_support as vcs  # noqa: E402
from theme import run_state  # noqa: E402
from theme import visual_compare as vc  # noqa: E402

TEASER = {"label": "div#beispiel-teaser", "z_index": "90000", "points": 18, "share": 0.075,
          "text": "10 % Rabatt"}
OVERLAP = {"state": "overlap", "file": "home/mobile-b-menu.png", "points": 240, "foreign": [TEASER],
           "drawer": {"label": "dialog.menu-drawer", "z_index": "18"}}


def pair(menu_a=vcs.MENU_OK, menu_b=vcs.MENU_OK, draft=vcs.DRAFT) -> dict:
    a = vcs.shot(vcs.LIVE, "mobile", "main", **({"menu": menu_a} if menu_a is not None else {}))
    b = vcs.shot(draft, "mobile", **({"menu": menu_b} if menu_b is not None else {}))
    return {"page_id": "home", "device": "mobile", "a": a, "b": b}


class TestMenuOffen(unittest.TestCase):
    def test_fremdes_element_ueber_der_schublade_haelt_g4_an(self):
        problem, note = vc.menu_problem(pair(menu_b=OVERLAP))
        self.assertIn("fremde Elemente über der Menü-Schublade", problem)
        self.assertIn("div#beispiel-teaser (z-index 90000 über Schublade z-index 18, 8 % der Fläche", problem)
        self.assertIsNone(note)

    def test_liegt_es_im_veroeffentlichten_theme_genauso_ist_es_ein_hinweis(self):
        problem, note = vc.menu_problem(pair(menu_a=dict(OVERLAP), menu_b=OVERLAP))
        self.assertIsNone(problem)
        self.assertIn("div#beispiel-teaser", note)

    def test_nicht_aufgenommen_oder_nicht_geoeffnet_zaehlt_nicht(self):
        self.assertIn("nicht aufgenommen", vc.menu_problem(pair(menu_b=None))[0])
        problem, _ = vc.menu_problem(pair(menu_b={"state": "no_toggle"}))
        self.assertIn("kein Menüknopf", problem)
        self.assertIn("--menu-toggle", problem)

    def test_abdeckung_zaehlt_das_menue_als_grund_derselben_aufnahme(self):
        slots = {("home", "desktop"): {"a": vcs.shot(vcs.LIVE, "desktop", "main"), "b": vcs.shot(vcs.DRAFT, "desktop")},
                 ("home", "mobile"): pair(menu_b=OVERLAP)}
        cover = vc.coverage(["home"], slots, lambda _p: {"a": vcs.LIVE, "b": vcs.DRAFT})
        self.assertEqual(cover["valid"], 3)
        self.assertEqual([(m["device"], m["side"]) for m in cover["missing"]], [("mobile", "b")])
        self.assertTrue(cover["missing"][0]["reason"].startswith("Menü offen"))

    def test_g4_haelt_mit_ueberdeckung_an(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            vcs.write_pages(ws, ["home"])
            data = vcs.record(["home"])
            data["pairs"][1]["b"]["menu"] = OVERLAP
            vcs.write_record(ws, data)
            config = {"theme_migration": {"live_theme_id": vcs.LIVE, "draft_theme_id": vcs.DRAFT}}
            result = vc.evaluate(ws, config, {})
            self.assertFalse(result["ok"])
            self.assertIn("Menü offen: fremde Elemente", result["problems"][0])
            self.assertIn("mit Menü offen", vc.gate_problems(ws, config, {})[0])

    def test_vergleichsseite_zeigt_das_offene_menue_und_was_darueber_liegt(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            data = {"themes": {"a": vcs.LIVE, "b": vcs.DRAFT}, "pairs": [pair(menu_b=OVERLAP)]}
            page = compose.render(data, folder, folder)
            self.assertIn("Menü offen", page)
            self.assertIn("Fremdes Element über dem Menü", page)
            self.assertIn("div#beispiel-teaser: z-index 90000 über Schublade z-index 18", page)
            self.assertIn("mobile-b-menu.png", page)

    def test_bildname_und_menueknoepfe(self):
        self.assertEqual(shoot_pair.menu_name("home", "b"), "home/mobile-b-menu.png")
        self.assertIn("header-drawer summary", shoot_pair.MENU_TOGGLES)
        self.assertIn("elementFromPoint", shoot_pair.MENU_PROBE_JS)


class TestReferenz(unittest.TestCase):
    def shots(self, theme, role, name="Beispiel Theme"):
        out = []
        for device in vc.DEVICES:
            s = vcs.shot(theme, device, role)
            s["theme_check"]["found_name"] = name
            out.append(s)
        return out

    def test_referenz_steht_mit_id_und_name(self):
        status = vc.reference_status(vcs.LIVE, self.shots(vcs.LIVE, "main", "Live Theme"), vcs.LIVE)
        self.assertTrue(status["ok"])
        self.assertEqual((status["name"], status["kind"]), ("Live Theme", "published"))

    def test_falsches_theme_nennt_id_und_name(self):
        status = vc.reference_status("000000000009", self.shots("000000000009", "unpublished", "altes Theme"),
                                     vcs.LIVE)
        self.assertFalse(status["ok"])
        self.assertIn("Theme 000000000009 „altes Theme“ mit Rolle unpublished", status["problems"][0])

    def test_nach_dem_launch_ist_das_rueckfall_theme_die_referenz(self):
        ok = vc.reference_status(vcs.LIVE, self.shots(vcs.LIVE, "unpublished"), vcs.DRAFT, rollback=vcs.LIVE)
        self.assertTrue(ok["ok"])
        self.assertEqual(ok["kind"], "rollback")
        other = vc.reference_status("000000000009", self.shots("000000000009", "unpublished", "drittes Theme"),
                                    vcs.DRAFT, rollback=vcs.LIVE)
        self.assertFalse(other["ok"])
        self.assertIn("nach dem Launch ist die Referenz das alte Theme 000000000004", other["problems"][0])
        self.assertIn("„drittes Theme“", other["problems"][0])

    def test_rueckfall_gilt_erst_nach_dem_veroeffentlichen(self):
        self.assertIsNone(vc.rollback_id({"rollback_theme_id": vcs.LIVE}))
        self.assertEqual(vc.rollback_id({"rollback_theme_id": vcs.LIVE, "published_at": "2026-11-11T11:47:00Z"}),
                         vcs.LIVE)


class TestReferenzAufloesen(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.ws = Path(tmp.name)
        self.config = {"domain": "beispielshop.example", "theme_migration": {"live_theme_id": vcs.LIVE}}
        self.themes = [{"id": f"gid://shopify/OnlineStoreTheme/{vcs.LIVE}", "name": "Live Theme", "role": "MAIN"},
                       {"id": "gid://shopify/OnlineStoreTheme/000000000009", "name": "altes Theme",
                        "role": "UNPUBLISHED"}]

    def test_vor_dem_launch_das_veroeffentlichte_theme_aus_der_theme_liste(self):
        ref = vc.resolve_reference(self.ws, self.config, {}, self.themes)
        self.assertTrue(ref["ok"])
        self.assertEqual(ref["line"], f"Referenz: Theme {vcs.LIVE} „Live Theme“, veröffentlicht")
        self.assertEqual(ref["preview_url"], f"https://beispielshop.example/?preview_theme_id={vcs.LIVE}")

    def test_veraltete_config_nennt_das_veroeffentlichte(self):
        config = {"theme_migration": {"live_theme_id": "000000000009"}}
        ref = vc.resolve_reference(self.ws, config, {}, self.themes)
        self.assertEqual(ref["theme_id"], vcs.LIVE)
        self.assertIn("live_theme_id 000000000009 der Config ist nicht das veröffentlichte Theme", ref["warnings"][0])

    def test_nach_dem_launch_das_rueckfall_theme(self):
        themes = [dict(self.themes[0], role="UNPUBLISHED"),
                  {"id": "gid://shopify/OnlineStoreTheme/000000000002", "name": "Neu", "role": "MAIN"}]
        values = {"rollback_theme_id": vcs.LIVE, "published_at": "2026-11-11T11:47:00Z", "live_theme_id": vcs.DRAFT}
        ref = vc.resolve_reference(self.ws, self.config, values, themes)
        self.assertEqual(ref["kind"], "rollback")
        self.assertEqual(ref["line"], f"Referenz: Theme {vcs.LIVE} „Live Theme“, bis zum Launch am 11.11.2026 "
                                      "veröffentlicht, jetzt Rückfall-Theme")

    def test_von_hand_veroeffentlicht_ist_das_bisherige_live_theme_die_referenz(self):
        themes = [dict(self.themes[0], role="UNPUBLISHED"),
                  {"id": f"gid://shopify/OnlineStoreTheme/{vcs.DRAFT}", "name": "Neu", "role": "MAIN"}]
        config = {"theme_migration": {"live_theme_id": vcs.LIVE, "draft_theme_id": vcs.DRAFT}}
        ref = vc.resolve_reference(self.ws, config, {}, themes)
        self.assertEqual((ref["theme_id"], ref["kind"]), (vcs.LIVE, "rollback"))
        self.assertIn("im Lauf fehlen published_at und rollback_theme_id", ref["warnings"][0])

    def test_ohne_shopify_name_aus_frueheren_vergleichen(self):
        data = vcs.record(["home"])
        for p in data["pairs"]:
            p["a"]["theme_check"]["found_name"] = "Live Theme"
        vcs.write_record(self.ws, data)
        ref = vc.resolve_reference(self.ws, self.config, {}, None, "kein Zugang")
        self.assertEqual(ref["name"], "Live Theme")
        self.assertIn("Theme-Liste nicht lesbar (kein Zugang)", ref["warnings"][0])

    def test_cli_reference(self):
        (self.ws / "reporting").mkdir()
        (self.ws / "reporting" / "config.json").write_text(json.dumps(self.config))

        class Transport:
            def execute(self, query, variables=None):
                return {"themes": {"nodes": themes}}
        themes = self.themes
        import contextlib
        import io
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = vc.main(["reference", "--workspace", str(self.ws)], transport=Transport())
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out.getvalue())["name"], "Live Theme")


class TestBildpaareNachDemLaunch(unittest.TestCase):
    def test_von_hand_veroeffentlicht_erkennt_das_rueckfall_theme_am_nachweis(self):
        data = vcs.record(["home"], live_role="unpublished")
        for pair in data["pairs"]:
            pair["b"]["theme_check"]["found_role"] = "main"
        summary = vc.record_summary(["home"], data["pairs"], data["themes"], vcs.LIVE)
        self.assertTrue(summary["reference"]["ok"], summary["reference"]["problems"])
        self.assertEqual(summary["reference"]["kind"], "rollback")
        self.assertIn("im Lauf fehlen published_at", summary["reference"]["warnings"][0])
        other = vcs.record(["home"], live="000000000009", live_role="unpublished")
        for pair in other["pairs"]:
            pair["b"]["theme_check"]["found_role"] = "main"
        self.assertFalse(vc.record_summary(["home"], other["pairs"], other["themes"], vcs.LIVE)["reference"]["ok"])

    def test_finish_nimmt_das_rueckfall_theme_aus_dem_lauf(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            state = run_state.new(ws, "2026-11-01-migration")
            for key, value in (("rollback_theme_id", vcs.LIVE), ("published_at", "2026-11-11T11:47:00Z"),
                               ("live_theme_id", vcs.DRAFT)):
                state.set_value(key, value)
            state.save()
            data = vcs.record(["home"], live_role="unpublished")
            config = {"theme_migration": {"live_theme_id": vcs.DRAFT}}
            done = shoot_pair.finish(data, ["home"], config, ws)
            self.assertTrue(done["reference"]["ok"], done["reference"]["problems"])
            self.assertEqual(done["reference"]["kind"], "rollback")


if __name__ == "__main__":
    unittest.main()
