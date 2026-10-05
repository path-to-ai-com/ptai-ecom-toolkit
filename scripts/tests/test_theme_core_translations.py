"""Theme-Übersetzungen: frische Digests vom Entwurf, genau ein Schlüssel je Eintrag, nur die Theme-Ressource."""
import contextlib
import io
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from tests import theme_fake_shop as fake  # noqa: E402
from theme import translations  # noqa: E402

CONFIG = {"shopify_store": "beispiel.myshopify.com",
          "theme_migration": {"draft_theme_id": "111111111111", "access": {"write": "admin-api"}}}

CONTENT = [
    {"key": "section.index.json.hero.title:a1", "value": "Willkommen", "digest": "d-hero", "locale": "de"},
    {"key": "section.index.json.hero.row__text_1.text:b2", "value": "Hallo", "digest": "d-text", "locale": "de"},
    {"key": "section.index.json.text_1.text:c3", "value": "Hallo", "digest": "d-falsch", "locale": "de"},
    {"key": "section.header-group.json.hero.title:e5", "value": "Kopf", "digest": "d-kopf", "locale": "de"},
    {"key": "beispiel_title:f6", "value": "Willkommen im Shop", "digest": "d-setting", "locale": "de"},
]

ENTRIES = [
    {"file": "templates/index.json", "pointer": "/sections/hero/settings/title", "source_value": "Willkommen",
     "value": "Welcome", "translatableContentDigest": "veraltet"},
    {"file": "templates/index.json", "pointer": "/sections/hero/blocks/row/blocks/text_1/settings/text",
     "source_value": "Hallo", "value": "Hello"},
    {"file": "config/settings_data.json", "pointer": "/current/beispiel_title", "source_value": "Willkommen im Shop",
     "value": "Welcome to the shop"},
]


def shop(content=None) -> fake.FakeShop:
    s = fake.shop_with_live()
    s.add_theme(fake.DRAFT_ID, "UNPUBLISHED", fake.fixture_files())
    s.translatable[fake.DRAFT_ID] = {"content": [dict(c) for c in (content or CONTENT)]}
    return s


def source(entries=None) -> dict:
    return {"locale": "en", "entries": entries if entries is not None else [dict(e) for e in ENTRIES]}


class TestZuordnung(unittest.TestCase):
    def test_digest_kommt_frisch_vom_entwurf_nie_aus_der_quelle(self):
        s = shop()
        report, code = translations.run(CONFIG, "111111111111", source(), transport=s)
        self.assertEqual(code, 0, report["findings"])
        sent = {t["key"]: t["translatableContentDigest"] for t in s.ops("RegisterThemeTranslations")[0][1]["translations"]}
        self.assertEqual(sent["section.index.json.hero.title:a1"], "d-hero")
        self.assertNotIn("veraltet", sent.values())

    def test_aendert_sich_ein_ausgangswert_wird_mit_dem_neuen_digest_registriert(self):
        s = shop()
        translations.run(CONFIG, "111111111111", source(), transport=s)
        s.translatable[fake.DRAFT_ID]["content"][0]["digest"] = "d-hero-neu"
        s.translatable[fake.DRAFT_ID]["translations"]["en"]["section.index.json.hero.title:a1"]["outdated"] = True
        report, code = translations.run(CONFIG, "111111111111", source(), transport=s)
        self.assertEqual(code, 0, report["findings"])
        last = s.ops("RegisterThemeTranslations")[-1][1]["translations"]
        self.assertEqual([(t["key"], t["translatableContentDigest"]) for t in last],
                         [("section.index.json.hero.title:a1", "d-hero-neu")])

    def test_verschachtelte_bloecke_brauchen_die_ganze_kette_nicht_nur_die_blatt_id(self):
        plan = translations.build_plan(source()["entries"], {"translatableContent": CONTENT}, "en")
        keys = {item["target"]: item["key"] for item in plan["matched"]}
        self.assertEqual(keys["templates/index.json#/sections/hero/blocks/row/blocks/text_1/settings/text"],
                         "section.index.json.hero.row__text_1.text:b2")

    def test_offener_eintrag_verhindert_jedes_registrieren(self):
        entries = [dict(e) for e in ENTRIES] + [{"file": "sections/header-group.json",
                                                 "pointer": "/sections/hero/settings/title",
                                                 "source_value": "Kopf", "value": "Header"}]
        s = shop()
        report, code = translations.run(CONFIG, "111111111111", source(entries), transport=s)
        self.assertEqual(code, 1)
        self.assertEqual(report["plan"]["status"], "needs_key_review")
        self.assertEqual(s.ops("RegisterThemeTranslations"), [])

    def test_ein_geprueefter_schluessel_loest_den_offenen_eintrag(self):
        entry = {"file": "sections/header-group.json", "pointer": "/sections/hero/settings/title",
                 "source_value": "Kopf", "value": "Header", "key": "section.header-group.json.hero.title"}
        plan = translations.build_plan([entry], {"translatableContent": CONTENT}, "en")
        self.assertEqual(plan["matched"][0]["key"], "section.header-group.json.hero.title:e5")

    def test_gleicher_text_allein_reicht_nicht(self):
        entry = {"file": "templates/index.json", "pointer": "/sections/hero/settings/title", "source_value": "Anders",
                 "value": "Other"}
        plan = translations.build_plan([entry], {"translatableContent": CONTENT}, "en")
        self.assertEqual(plan["unresolved"][0]["reason"], "no_unique_match")

    def test_aktuelle_uebersetzung_wird_uebersprungen(self):
        s = shop()
        translations.run(CONFIG, "111111111111", source(), transport=s)
        report, code = translations.run(CONFIG, "111111111111", source(), transport=s)
        self.assertEqual(code, 0)
        self.assertEqual(len(report["plan"]["already_registered"]), 3)
        self.assertEqual(len(s.ops("RegisterThemeTranslations")), 1)

    def test_ausgangswert_wird_gegen_den_theme_ordner_geprueft(self):
        entries = [dict(ENTRIES[0], source_value="Willkommen")]
        plan = translations.build_plan(entries, {"translatableContent": CONTENT}, "en", fake.FIXTURE)
        self.assertEqual(len(plan["matched"]), 1)
        stale = [dict(ENTRIES[1], source_value="Alter Text")]
        plan = translations.build_plan(stale, {"translatableContent": CONTENT}, "en", fake.FIXTURE)
        self.assertEqual(plan["unresolved"][0]["reason"], "source_value_differs_from_theme_dir")


class TestSchreiben(unittest.TestCase):
    def test_nur_die_ressource_des_entwurfs_wird_angefasst(self):
        s = shop()
        translations.run(CONFIG, "111111111111", source(), transport=s)
        ids = {c[1]["resourceId"] for c in s.calls if c[0] in ("ThemeTranslations", "RegisterThemeTranslations")}
        self.assertEqual(ids, {fake.DRAFT_ID})

    def test_auf_das_live_theme_wird_nie_registriert(self):
        s = shop()
        config = {"theme_migration": {"draft_theme_id": "000000000000"}}
        with self.assertRaises(translations.GuardError):
            translations.run(config, "000000000000", source(), transport=s)
        self.assertEqual(s.ops("RegisterThemeTranslations"), [])

    def test_pakete_zu_hundert_und_halt_bei_user_errors(self):
        content = [{"key": f"section.index.json.s{i}.title:h{i}", "value": f"Titel {i}", "digest": f"d{i}",
                    "locale": "de"} for i in range(250)]
        entries = [{"file": "templates/index.json", "pointer": f"/sections/s{i}/settings/title",
                    "source_value": f"Titel {i}", "value": f"Title {i}"} for i in range(250)]
        s = shop(content)
        s.register_errors = {1: [{"code": "INVALID", "field": ["translations"], "message": "kaputt"}]}
        report, code = translations.run(CONFIG, "111111111111", source(entries), transport=s)
        calls = s.ops("RegisterThemeTranslations")
        self.assertEqual([len(c[1]["translations"]) for c in calls], [100, 100])
        self.assertEqual(code, 1)
        self.assertIn("user_errors", [f["rule"] for f in report["findings"]])
        self.assertEqual(len(report["register"]["registered"]), 100)

    def test_zuruecklesen_findet_veraltete_werte(self):
        s = shop()

        def outdate(shop_, variables):
            for item in shop_.translatable[fake.DRAFT_ID].get("translations", {}).get("en", {}).values():
                item["outdated"] = True

        s.hooks["ThemeTranslations"] = lambda shop_, v: outdate(shop_, v) if shop_.ops("RegisterThemeTranslations") \
            else None
        report, code = translations.run(CONFIG, "111111111111", source(), transport=s)
        self.assertEqual(code, 1)
        self.assertEqual(len(report["readback"]["different"]), 3)
        self.assertEqual(report["readback"]["equal"], [])


class TestCli(unittest.TestCase):
    def test_trockenlauf_registriert_nichts(self):
        ws = fake.temp_workspace(self, draft_theme_id="111111111111")
        (ws / "quelle.json").write_text(json.dumps(source()))
        s = shop()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = translations.main(["register", "--theme", "111111111111", "--source", str(ws / "quelle.json"),
                                      "--dry-run", "--workspace", str(ws)], transport=s)
        self.assertEqual(code, 0)
        summary = json.loads(out.getvalue())
        self.assertEqual((summary["matched"], summary["registered"]), (3, 0))
        self.assertEqual(s.ops("RegisterThemeTranslations"), [])
        self.assertTrue(Path(summary["out"]).is_file())


if __name__ == "__main__":
    unittest.main()
