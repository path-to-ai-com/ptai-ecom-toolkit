"""Tests für den Block theme_migration in reporting/config.json (Spec 2026-10-05, Abschnitt 6)."""
import unittest

from audit import config


class ThemeMigrationConfigTest(unittest.TestCase):
    def errors(self, block):
        return config.theme_migration_errors(block)

    def test_ein_gueltiger_block_hat_keine_fehler(self):
        block = {
            "live_theme_id": "000000000000",
            "source_theme": {"name": "", "version": "", "architecture": "os2"},
            "target_theme": {"name": "Horizon", "version": "", "upstream": "", "ref": ""},
            "target_repo": "../beispielshop-theme",
            "draft_theme_id": None,
            "file_prefix": "beispiel",
            "access": {"read": "cli-grant", "write": "cli-theme"},
            "page_sample": "auto",
            "freeze": {"from": None, "until": None},
        }
        self.assertEqual(self.errors(block), [])

    def test_eine_theme_id_als_zahl_wird_gemeldet(self):
        self.assertTrue(self.errors({"live_theme_id": 123}))

    def test_ein_vertippter_schluessel_wird_gemeldet(self):
        found = self.errors({"live_theme": "000000000000"})
        self.assertEqual(len(found), 1)
        self.assertIn("live_theme_id", found[0])

    def test_der_cockpit_zugang_schreibt_nicht(self):
        self.assertTrue(self.errors({"access": {"read": "portal", "write": "admin-api"}}))

    def test_ein_praefix_mit_grossbuchstaben_wird_gemeldet(self):
        self.assertTrue(self.errors({"file_prefix": "Beispiel"}))

    def test_berichtspfade_und_pruefliste(self):
        self.assertEqual(self.errors({"report_paths": ["{drive_path}/projects/beispiel"],
                                      "acceptance_checklist": "migration/inventory/seo-checklist.md"}), [])
        self.assertTrue(self.errors({"report_paths": "{drive_path}/projects/beispiel"}))
        self.assertTrue(self.errors({"report_paths": [""]}))
        self.assertTrue(self.errors({"acceptance_checklist": 7}))

    def test_eine_config_ohne_block_bleibt_unberuehrt(self):
        self.assertFalse(any("theme_migration" in e for e in config.validate({})))

    def test_ein_block_der_kein_objekt_ist_wird_gemeldet(self):
        found = config.validate({"theme_migration": []})
        self.assertTrue(any("theme_migration muss ein Objekt sein" in e for e in found))


if __name__ == "__main__":
    unittest.main()
