"""Tests für den Stand aller Stores aus GitHub (theme.stores)."""
import unittest
from unittest import mock

from theme import stores

MIGRATION = {
    "current_step": 6,
    "steps": [{"step": i, "name": f"Schritt {i}", "status": "done"} for i in range(1, 6)]
    + [{"step": 6, "name": "Abnahme", "status": "running"}]
    + [{"step": i, "name": f"Schritt {i}", "status": "open"} for i in range(7, 10)],
    "now": "Abnahme: bereit zum Testen",
    "owner": "team",
    "questions": [{"id": "Q-001", "status": "open"}, {"id": "Q-002", "status": "answered"}],
    "operator_tasks": [],
    "ready_for_launch": {"met": False},
}


class StoresTest(unittest.TestCase):
    def test_der_juengste_migrationslauf_gilt(self):
        paths = ["reporting/runs/2026-10-07-migration/migration.json",
                 "reporting/runs/2026-11-02-migration/migration.json",
                 "reporting/runs/2026-11-02-setup/setup.json",
                 "migration/next.json"]
        self.assertEqual(stores.latest_run_path(paths), "reporting/runs/2026-11-02-migration/migration.json")
        self.assertIsNone(stores.latest_run_path(["migration/next.json"]))

    def test_die_zeile_nennt_schritt_zustaendigkeit_und_offene_fragen(self):
        row = stores.summarize("org/store", MIGRATION, "2026-11-03T10:00:00Z")
        self.assertEqual((row["step"], row["step_name"], row["owner"]), (6, "Abnahme", "team"))
        self.assertEqual(row["open_questions"], ["Q-001"])
        text = stores.line(row)
        self.assertIn("Schritt 6 von 9: Abnahme: bereit zum Testen", text)
        self.assertIn("Zuständig: Team", text)
        self.assertIn("1 Fragen offen (Q-001)", text)
        self.assertIn("letzter Push 2026-11-03", text)
        self.assertNotIn("Path to AI:", text)

    def test_aufgaben_fuer_path_to_ai_stehen_in_der_zeile(self):
        migration = {**MIGRATION, "owner": "operator", "operator_tasks": ["Abnahme ins Cockpit stellen"]}
        text = stores.line(stores.summarize("org/store", migration, None))
        self.assertIn("Zuständig: Path to AI", text)
        self.assertIn("Path to AI: Abnahme ins Cockpit stellen", text)

    def test_ein_nicht_lesbares_repo_haelt_die_anderen_nicht_an(self):
        with mock.patch.object(stores, "gh_json", side_effect=stores.StoresError("Not Found")):
            row = stores.read_store("org/fehlt")
        self.assertEqual(stores.line(row), "org/fehlt: nicht gelesen (Not Found)")


if __name__ == "__main__":
    unittest.main()
