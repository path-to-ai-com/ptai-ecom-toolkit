"""Das Lauf-Verzeichnis einer Brand: was es traegt und was nicht."""
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from audit import manifest


class TestPathFor(unittest.TestCase):
    def test_the_shop_sits_under_the_brand(self):
        self.assertEqual(manifest.path_for("beispielkunde", "beispielshop"),
                         "brands/beispielkunde/shops/beispielshop")

    def test_a_run_hangs_under_its_shop(self):
        self.assertEqual(manifest.path_for("beispielkunde", "beispielshop", "2026-09-08-audit"),
                         "brands/beispielkunde/shops/beispielshop/runs/2026-09-08-audit")


class TestRunEntries(unittest.TestCase):
    def setUp(self):
        self.manifest_data = manifest.empty("beispielkunde", "Beispielkunde GmbH")

    def _add(self, manifest_data, run_id="2026-09-08-audit", shop="beispielshop", **kw):
        return manifest.add_run(manifest_data, shop=shop, run_id=run_id, kind="audit",
                                cadence="audit", period=None,
                                run_date="2026-09-08", files={"audit.pdf": 1},
                                today=date(2026, 9, 9), **kw)

    def test_an_empty_manifest_carries_no_runs(self):
        self.assertEqual(self.manifest_data["runs"], [])
        self.assertEqual(self.manifest_data["brand"], "beispielkunde")

    def test_a_run_without_a_title_carries_none(self):
        self.assertIsNone(self._add(self.manifest_data)["runs"][0]["title"])

    def test_a_run_carries_its_own_title(self):
        manifest_data = self._add(self.manifest_data, title="  Abstimmung vor dem Theme-Wechsel ")
        self.assertEqual(manifest_data["runs"][0]["title"], "Abstimmung vor dem Theme-Wechsel")

    def test_a_run_appears_with_its_path(self):
        manifest_data = self._add(self.manifest_data)
        self.assertEqual(len(manifest_data["runs"]), 1)
        self.assertEqual(manifest_data["runs"][0]["path"],
                         "brands/beispielkunde/shops/beispielshop/runs/2026-09-08-audit")

    def test_publishing_never_releases(self):
        # Der ganze Sinn der Trennung: ein hochgeladener Lauf ist unsichtbar,
        # bis ein Mensch ihn gelesen hat.
        manifest_data = self._add(self.manifest_data)
        self.assertFalse(manifest_data["runs"][0]["released"])
        self.assertEqual(manifest.released(manifest_data), [])

    def test_a_second_publish_keeps_the_release(self):
        # Ein erneutes Hochladen derselben Lauf-ID ist eine Korrektur, keine
        # Ruecknahme der Freigabe.
        manifest_data = manifest.release(self._add(self.manifest_data),
                                         "beispielshop", "2026-09-08-audit")
        manifest_data = self._add(manifest_data)
        self.assertTrue(manifest_data["runs"][0]["released"])
        self.assertEqual(len(manifest_data["runs"]), 1,
                         "die Korrektur legt keinen zweiten an")

    def test_release_makes_it_visible(self):
        manifest_data = manifest.release(self._add(self.manifest_data),
                                         "beispielshop", "2026-09-08-audit")
        self.assertEqual(len(manifest.released(manifest_data)), 1)
        self.assertEqual(manifest_data["runs"][0]["released_at"],
                         date.today().isoformat())

    def test_releasing_an_unknown_run_raises(self):
        with self.assertRaises(KeyError):
            manifest.release(self.manifest_data, "beispielshop", "gibt-es-nicht")

    def test_two_shops_stay_apart(self):
        manifest_data = self._add(self._add(self.manifest_data), shop="zweitshop")
        self.assertEqual({r["shop"] for r in manifest_data["runs"]},
                         {"beispielshop", "zweitshop"})
        manifest_data = manifest.release(manifest_data, "beispielshop",
                                         "2026-09-08-audit")
        self.assertEqual([r["shop"] for r in manifest.released(manifest_data)],
                         ["beispielshop"])
        self.assertEqual(manifest.released(manifest_data, shop="zweitshop"), [])

    def test_an_unknown_kind_raises(self):
        with self.assertRaises(ValueError):
            manifest.add_run(self.manifest_data, shop="beispielshop", run_id="x",
                             kind="quatsch", cadence=None, period=None,
                             run_date="2026-09-08", files={})

    def test_a_run_without_a_shop_raises(self):
        with self.assertRaises(ValueError):
            manifest.add_run(self.manifest_data, shop="", run_id="x", kind="audit",
                             cadence=None, period=None, run_date="2026-09-08",
                             files={})

    #: Was ein Lauf-Eintrag tragen darf. Alles andere waere ein Schema.
    ALLOWED_KEYS = {"shop", "run_id", "kind", "cadence", "period", "title", "run_date",
                    "published_at", "released", "released_at", "path", "files",
                    "revision", "revisions"}

    def test_a_run_entry_carries_only_known_keys(self):
        """Sobald Kennzahlen darin stuenden, waere der Manifest ein
        normalisiertes Schema und damit die Datenbank durch die Hintertuer
        (Spec Abschnitt 9).

        Geprueft wird die Schluesselmenge, nicht der Text: `files` traegt
        legitim `findings/conversion.json`, und eine Substring-Suche nach
        "conversion" wuerde einen Dateinamen fuer eine Kennzahl halten.
        """
        manifest_data = self._add(self.manifest_data)
        self.assertEqual(set(manifest_data["runs"][0]), self.ALLOWED_KEYS)

    def test_files_carry_sizes_not_values(self):
        """`files` ist ein Verzeichnis: Pfad auf Groesse. Wer dort eine
        gerechnete Zahl ablegt, hat das Schema begonnen."""
        manifest_data = self._add(self.manifest_data)
        for path, size in manifest_data["runs"][0]["files"].items():
            self.assertIsInstance(size, int, f"{path} traegt keinen Dateigroessen-Wert")


class TestRevisions(unittest.TestCase):
    """Eine Korrektur derselben Lauf-ID ist eine neue Fassung, kein Ersatz."""

    def setUp(self):
        self.empty = manifest.empty("beispielkunde", "Beispielshop")
        self.args = dict(shop="beispielshop", run_id="2026-09-08-audit",
                         kind="audit", cadence="audit", period=None,
                         run_date="2026-09-08")

    def _add(self, manifest_data, files, revision, **kw):
        return manifest.add_run(manifest_data, files=files, revision=revision,
                                **self.args, **kw)

    def test_the_first_version_stays_on_the_flat_path(self):
        """Die Laeufe, die heute im Bucket liegen, duerfen nicht umziehen."""
        manifest_data = self._add(self.empty, {"audit.pdf": 4}, 1,
                                  today=date(2026, 9, 8))
        run = manifest_data["runs"][0]
        self.assertEqual(
            run["path"],
            "brands/beispielkunde/shops/beispielshop/runs/2026-09-08-audit")
        self.assertEqual(run["revision"], 1)

    def test_the_second_version_gets_its_own_path(self):
        manifest_data = self._add(self.empty, {"audit.pdf": 4}, 1,
                                  today=date(2026, 9, 8))
        manifest_data = self._add(manifest_data, {"audit.pdf": 9}, 2,
                                  today=date(2026, 9, 13),
                                  note="GA4-Doppelzaehlung nachgetragen")
        run = manifest_data["runs"][0]
        self.assertTrue(run["path"].endswith("/2026-09-08-audit/v02"))
        self.assertEqual(run["revision"], 2)
        self.assertEqual([r["no"] for r in run["revisions"]], [1, 2])
        self.assertEqual(run["revisions"][1]["note"],
                         "GA4-Doppelzaehlung nachgetragen")
        # Die erste Fassung bleibt auffindbar, samt ihrer Dateien.
        self.assertTrue(run["revisions"][0]["path"].endswith("/2026-09-08-audit"))
        self.assertEqual(run["revisions"][0]["files"], {"audit.pdf": 4})

    def test_next_revision_counts_up_and_replace_holds(self):
        manifest_data = self._add(self.empty, {"audit.pdf": 4}, 1,
                                  today=date(2026, 9, 8))
        self.assertEqual(
            manifest.next_revision(manifest_data, "beispielshop", "2026-09-08-audit"), 2)
        self.assertEqual(
            manifest.next_revision(manifest_data, "beispielshop", "2026-09-08-audit",
                                   replace=True), 1)
        self.assertEqual(
            manifest.next_revision(manifest_data, "beispielshop", "2026-10-05-report"), 1)

    def test_replace_overwrites_the_running_revision(self):
        manifest_data = self._add(self.empty, {"audit.pdf": 4}, 1,
                                  today=date(2026, 9, 8))
        manifest_data = self._add(manifest_data, {"audit.pdf": 9}, 1,
                                  today=date(2026, 9, 8), note="Tippfehler")
        run = manifest_data["runs"][0]
        self.assertEqual(run["revision"], 1)
        self.assertEqual(len(run["revisions"]), 1)
        self.assertEqual(run["files"], {"audit.pdf": 9})

    def test_releasing_survives_a_correction(self):
        """Ein erneutes publish ist eine Korrektur, keine Ruecknahme der
        Freigabe."""
        manifest_data = self._add(self.empty, {"audit.pdf": 4}, 1,
                                  today=date(2026, 9, 8))
        manifest_data = manifest.release(manifest_data, "beispielshop",
                                         "2026-09-08-audit", today=date(2026, 9, 9))
        manifest_data = self._add(manifest_data, {"audit.pdf": 9}, 2,
                                  today=date(2026, 9, 13))
        self.assertTrue(manifest_data["runs"][0]["released"])
        self.assertEqual(manifest_data["runs"][0]["released_at"], "2026-09-09")


class TestCollectFiles(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.run = Path(self.tmp.name)
        (self.run / "findings").mkdir()
        (self.run / "audit.pdf").write_bytes(b"%PDF")
        (self.run / "findings" / "cro.json").write_text("{}", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_files_come_back_relative(self):
        files = manifest.collect_files(self.run)
        self.assertIn("audit.pdf", files)
        self.assertIn("findings/cro.json", files)

    def test_the_ledger_never_goes_up(self):
        # Kosten je Abfrage sind die Marge des Betreibers.
        (self.run / "dfs-ledger.jsonl").write_text("{}", encoding="utf-8")
        self.assertNotIn("dfs-ledger.jsonl", manifest.collect_files(self.run))

    def test_earlier_versions_stay_out(self):
        # `revisions/` haelt Zwischenstaende, die nie jemand freigegeben hat.
        (self.run / "revisions" / "01").mkdir(parents=True)
        (self.run / "revisions" / "01" / "audit.pdf").write_bytes(b"%PDF")
        files = manifest.collect_files(self.run)
        self.assertNotIn("revisions/01/audit.pdf", files)
        self.assertIn("audit.pdf", files)

    def test_everything_else_goes_up(self):
        # Ausschlussliste, keine Auswahlliste: im Zweifel hochladen.
        (self.run / "irgendwas-neues.csv").write_text("a,b", encoding="utf-8")
        self.assertIn("irgendwas-neues.csv", manifest.collect_files(self.run))


class TestSave(unittest.TestCase):
    def test_a_manifest_survives_disk(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest_path = Path(tmp) / "brands" / "beispielkunde" / "manifest.json"
            manifest_data = manifest.empty("beispielkunde", "Beispielkunde GmbH")
            manifest.save(manifest_path, manifest_data)
            self.assertEqual(manifest.load(manifest_path)["brand"], "beispielkunde")


if __name__ == "__main__":
    unittest.main()
