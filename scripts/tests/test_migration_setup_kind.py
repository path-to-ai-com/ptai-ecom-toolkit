"""Migration und Setup als Lauf-Arten, die nur ihre eine Datei hochladen und sofort sichtbar sind."""
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from audit import manifest, publish
from tests.test_publish import make_workspace

MIGRATION = "2026-10-12-migration"
SETUP = "2026-10-12-setup"


def write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")


def store(root: Path) -> Path:
    """Ein Store-Workspace mit Config, Maßnahmen und einem Migrationslauf voller Werkstatt-Dateien."""
    ws = root / "workspace"
    write(ws / "reporting" / "config.json", {"account_slug": "beispielkunde", "brand": "Beispielshop",
                                              "domain": "https://beispielshop.test"})
    write(ws / "reporting" / "measures.json", {"next_id": 1, "measures": []})
    run = ws / "reporting" / "runs" / MIGRATION
    write(run / "state.json", {"run_id": MIGRATION, "kind": "migration", "phases": {}, "gates": {}, "values": {}})
    write(run / "migration.json", {"schema": 1, "run_id": MIGRATION, "current_step": 3})
    write(run / "journal.jsonl", '{"kind": "phase"}\n')
    write(run / "session.lock", {"session_id": "sitzung-a"})
    write(run / "sessions" / "2026-10-12-sitzung.md", "Transkript")
    return ws


def setup_run(ws: Path, value: str) -> None:
    run = ws / "reporting" / "runs" / SETUP
    write(run / "state.json", {"run_id": SETUP, "cadence": "setup", "title": "Setup"})
    # Gültig nach `reference/setup-format.md`, sonst hält `publish` an; `source` trägt die Fassung.
    write(run / "setup.json", {
        "schema": 1, "shop": "beispielshop", "reference_shop": None, "collected_at": "2026-10-12T10:00:00+00:00",
        "source": value, "automatic": False, "views": {"live": {
            "theme": {"name": "Horizon", "version": None, "id": None},
            "groups": [{"key": "theme", "label": "Theme", "rows": [
                {"key": "theme", "label": "Theme", "value": "Horizon"}]}]}}})


class RunKind(unittest.TestCase):
    def test_ein_migrationsstand_ist_die_art_migration_ohne_kadenz(self):
        self.assertEqual(publish.run_kind(MIGRATION, {"run_id": MIGRATION, "kind": "migration"}),
                         ("migration", None))

    def test_die_kadenz_setup_ist_das_setup(self):
        self.assertEqual(publish.run_kind(SETUP, {"cadence": "setup"}), ("setup", "setup"))

    def test_week_bleibt_der_puls_und_unbekannte_kadenz_ein_bericht(self):
        self.assertEqual(publish.run_kind("2026-10-13-week", {"cadence": "week"}), ("pulse", "week"))
        self.assertEqual(publish.run_kind("2026-10-13-monat", {"cadence": "monat"}), ("report", "monat"))


class SingleFileKinds(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.ws = store(self.root)
        self.bucket = self.root / "bucket"

    def entry(self, run_id: str) -> dict:
        data = manifest.load(self.bucket / publish.manifest_key("beispielkunde"))
        return next(r for r in data["runs"] if r["run_id"] == run_id)

    def test_migration_lauf_ist_sofort_sichtbar_und_traegt_nur_migration_json(self):
        out = publish.prepare(self.ws, MIGRATION, self.bucket, today=date(2026, 10, 12))
        self.assertTrue(out["released"])
        entry = self.entry(MIGRATION)
        self.assertEqual(entry["kind"], "migration")
        self.assertIsNone(entry["cadence"])
        self.assertEqual(list(entry["files"]), ["migration.json"])
        uploaded = sorted(p.relative_to(out["path"]).as_posix()
                          for p in Path(out["path"]).rglob("*") if p.is_file())
        self.assertEqual(uploaded, ["migration.json"])

    def test_migration_bekommt_keinen_schnappschuss_der_massnahmen(self):
        out = publish.prepare(self.ws, MIGRATION, self.bucket, today=date(2026, 10, 12))
        self.assertFalse((Path(out["path"]) / "measures.json").exists())
        self.assertNotIn("measures.json", self.entry(MIGRATION)["files"])

    def test_migration_ohne_datei_bricht_ab(self):
        (self.ws / "reporting" / "runs" / MIGRATION / "migration.json").unlink()
        with self.assertRaises(SystemExit) as caught:
            publish.prepare(self.ws, MIGRATION, self.bucket, today=date(2026, 10, 12))
        self.assertIn("migration.json fehlt", str(caught.exception))
        self.assertIn("Nichts kopiert", str(caught.exception))
        self.assertFalse(self.bucket.exists())

    def test_setup_ohne_datei_bricht_ab(self):
        setup_run(self.ws, "a")
        (self.ws / "reporting" / "runs" / SETUP / "setup.json").unlink()
        with self.assertRaises(SystemExit) as caught:
            publish.prepare(self.ws, SETUP, self.bucket, today=date(2026, 10, 12))
        self.assertIn("setup.json fehlt", str(caught.exception))
        self.assertFalse(self.bucket.exists())

    def test_setup_lauf_ersetzt_die_fassung_statt_v02(self):
        setup_run(self.ws, "erste")
        first = publish.prepare(self.ws, SETUP, self.bucket, today=date(2026, 10, 12))
        setup_run(self.ws, "zweite")
        # Ohne --visible: das Setup ist immer sichtbar, eine neue Fassung auch.
        second = publish.prepare(self.ws, SETUP, self.bucket, today=date(2026, 10, 12))
        self.assertEqual((first["revision"], second["revision"]), (1, 1))
        self.assertEqual(first["path"], second["path"])
        self.assertNotIn("v02", second["path"])
        entry = self.entry(SETUP)
        self.assertEqual(len(entry["revisions"]), 1)
        self.assertEqual(entry["title"], "Setup")
        self.assertTrue(entry["released"])
        stored = json.loads((Path(second["path"]) / "setup.json").read_text(encoding="utf-8"))
        self.assertEqual(stored["source"], "zweite")

    def test_eine_neue_migration_braucht_kein_visible(self):
        publish.prepare(self.ws, MIGRATION, self.bucket, today=date(2026, 10, 12))
        out = publish.prepare(self.ws, MIGRATION, self.bucket, today=date(2026, 10, 13))
        self.assertTrue(out["released"])
        self.assertEqual(out["revision"], 1)


class SessionLock(unittest.TestCase):
    def test_session_lock_geht_nie_hoch(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = make_workspace(Path(tmp), "2026-09-08-audit")
            write(ws / "reporting" / "runs" / "2026-09-08-audit" / "session.lock", {"session_id": "a"})
            out = publish.prepare(ws, "2026-09-08-audit", Path(tmp) / "bucket")
            self.assertFalse((Path(out["path"]) / "session.lock").exists())
            self.assertIn("session.lock", manifest.EXCLUDED)


if __name__ == "__main__":
    unittest.main()
