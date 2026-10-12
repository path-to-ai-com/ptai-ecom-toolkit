"""Eine Fassung beiseitelegen, bevor eine neue Analyse darüber schreibt."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from audit import revision


class TestArchive(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = Path(self.tmp.name)
        self.run_id = "2026-10-01-audit"
        self.run = self.ws / "reporting" / "runs" / self.run_id
        (self.run / "findings").mkdir(parents=True)
        (self.ws / "reporting" / "measures.json").write_text(
            json.dumps({"next_id": 2, "measures": []}), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def _fassung(self):
        (self.run / "findings").mkdir(exist_ok=True)
        (self.run / "findings" / "cro.json").write_text('{"findings": []}',
                                                        encoding="utf-8")
        (self.run / "audit.pdf").write_bytes(b"%PDF")
        (self.run / "report-text.json").write_text('{"cover": "x"}',
                                                   encoding="utf-8")

    def test_the_first_archive_is_number_one(self):
        self._fassung()
        ziel = revision.archive(self.ws, self.run_id)
        self.assertEqual(ziel.name, "01")

    def test_findings_and_report_move_away(self):
        self._fassung()
        revision.archive(self.ws, self.run_id)
        self.assertFalse((self.run / "findings").exists())
        self.assertFalse((self.run / "audit.pdf").exists())

    def test_the_archive_holds_them(self):
        self._fassung()
        ziel = revision.archive(self.ws, self.run_id)
        self.assertTrue((ziel / "findings" / "cro.json").exists())
        self.assertTrue((ziel / "audit.pdf").exists())

    def test_the_proof_images_go_with_their_findings(self):
        self._fassung()
        (self.run / "proof").mkdir()
        (self.run / "proof" / "cro-01-1-mobil.jpg").write_bytes(b"\xff\xd8")
        ziel = revision.archive(self.ws, self.run_id)
        self.assertTrue((ziel / "proof" / "cro-01-1-mobil.jpg").exists())
        self.assertFalse((self.run / "proof").exists())

    def test_the_written_text_stays_put(self):
        # Cover-Headline und Kernaussagen hat ein Mensch geschrieben. Sie
        # gelten dem Lauf, nicht der Fassung, und wer sie mitnimmt, lässt sie
        # ein zweites Mal schreiben.
        self._fassung()
        revision.archive(self.ws, self.run_id)
        self.assertTrue((self.run / "report-text.json").exists())

    def test_the_backlog_is_copied_not_moved(self):
        self._fassung()
        ziel = revision.archive(self.ws, self.run_id)
        self.assertTrue((ziel / "measures.json").exists())
        self.assertTrue((self.ws / "reporting" / "measures.json").exists())

    def test_kopie_laesst_die_fassung_im_lauf_stehen(self):
        # Der Nachlauf einer Disziplin ersetzt nur deren Befund-Datei. Die
        # übrigen Befunde müssen bleiben, sonst baut der Gesamtreport auf
        # einer einzigen Disziplin.
        self._fassung()
        ziel = revision.archive(self.ws, self.run_id, copy=True)
        self.assertTrue((self.run / "findings" / "cro.json").exists())
        self.assertTrue((self.run / "audit.pdf").exists())
        self.assertTrue((ziel / "findings" / "cro.json").exists())
        self.assertTrue((ziel / "audit.pdf").exists())

    def test_kopie_setzt_den_backlog_nie_zurueck(self):
        self._fassung()
        backlog = {"next_id": 2, "measures": [
            {"id": "M-001", "status": "open", "history": [{"status": "open"}]}]}
        (self.ws / "reporting" / "measures.json").write_text(
            json.dumps(backlog), encoding="utf-8")
        revision.main(["--workspace", str(self.ws), "--run-id", self.run_id, "--copy"])
        after = json.loads((self.ws / "reporting" / "measures.json").read_text())
        self.assertEqual([m["id"] for m in after["measures"]], ["M-001"])

    def test_a_second_archive_counts_up(self):
        self._fassung()
        revision.archive(self.ws, self.run_id)
        self._fassung()
        self.assertEqual(revision.archive(self.ws, self.run_id).name, "02")

    def test_nothing_to_archive_returns_none(self):
        self.assertIsNone(revision.archive(self.ws, self.run_id))

    def test_nothing_to_archive_creates_no_folder(self):
        revision.archive(self.ws, self.run_id)
        self.assertFalse(revision.revisions_dir(self.ws, self.run_id).exists())


class TestResetMeasures(unittest.TestCase):
    def _measure(self, ident, status="open", history=1):
        return {"id": ident, "status": status,
                "history": [{"status": "open"}] * history}

    def test_an_untouched_measure_is_removed(self):
        neu, entfernt, behalten = revision.reset_measures(
            {"next_id": 2, "measures": [self._measure("M-01")]})
        self.assertEqual((entfernt, behalten), (1, 0))
        self.assertEqual(neu["measures"], [])

    def test_a_measure_with_a_status_stays(self):
        neu, entfernt, behalten = revision.reset_measures(
            {"next_id": 2, "measures": [self._measure("M-01", "in_progress")]})
        self.assertEqual((entfernt, behalten), (0, 1))

    def test_a_measure_with_history_stays(self):
        neu, entfernt, behalten = revision.reset_measures(
            {"next_id": 2, "measures": [self._measure("M-01", history=2)]})
        self.assertEqual((entfernt, behalten), (0, 1))

    def test_next_id_never_decreases(self):
        # Spec 2026-10-08, Abschnitt 5.1, Regel 6: eine entfernte Kennung
        # bleibt verbraucht. Bis zum 09.10.2026 sank next_id hier auf 3.
        backlog = {"next_id": 4, "measures": [
            self._measure("M-01", "implemented"),
            self._measure("M-02"),
            self._measure("M-03", "rejected"),
        ]}
        neu, entfernt, behalten = revision.reset_measures(backlog)
        self.assertEqual((entfernt, behalten), (1, 2))
        self.assertEqual(neu["next_id"], 4)

    def test_an_empty_backlog_survives(self):
        neu, entfernt, behalten = revision.reset_measures({"measures": []})
        self.assertEqual(neu, {"next_id": 1, "measures": []})


class TestCli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = Path(self.tmp.name)
        self.run_id = "2026-10-01-audit"
        run = self.ws / "reporting" / "runs" / self.run_id
        (run / "findings").mkdir(parents=True)
        (run / "findings" / "cro.json").write_text("{}", encoding="utf-8")
        (self.ws / "reporting" / "measures.json").write_text(json.dumps(
            {"next_id": 3, "measures": [
                {"id": "M-01", "status": "open", "history": [{"status": "open"}]},
                {"id": "M-02", "status": "implemented",
                 "history": [{"status": "open"}, {"status": "implemented"}]},
            ]}), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def _backlog(self):
        return json.loads((self.ws / "reporting" / "measures.json")
                          .read_text(encoding="utf-8"))

    def test_the_cli_archives_and_resets(self):
        code = revision.main(["--workspace", str(self.ws), "--run-id", self.run_id])
        self.assertEqual(code, 0)
        self.assertEqual([m["id"] for m in self._backlog()["measures"]], ["M-02"])

    def test_keep_measures_leaves_the_backlog_alone(self):
        revision.main(["--workspace", str(self.ws), "--run-id", self.run_id,
                       "--keep-measures"])
        self.assertEqual(len(self._backlog()["measures"]), 2)


if __name__ == "__main__":
    unittest.main()


from tests import brand_support as bs  # noqa: E402


class TestReanalyzeInABrandList(unittest.TestCase):
    """D12: eine neue Analyse in UK setzt nur zurück, was UK in diesem Lauf schrieb."""

    RUN = "2026-11-12-audit"

    def setUp(self):
        self.doc = bs.fixture()

    def _ids(self, backlog):
        return [m["id"] for m in backlog["measures"]]

    def test_uk_keeps_the_eu_measures(self):
        new, removed, kept = revision.reset_measures(self.doc, shop="uk", run_id=self.RUN)
        eu_before = [m for m in self.doc["measures"] if "eu" in m["shops"]]
        eu_after = [m for m in new["measures"] if "eu" in m["shops"]]
        self.assertEqual([m["by_shop"]["eu"] for m in eu_after],
                         [m["by_shop"]["eu"] for m in eu_before])
        self.assertEqual(self._ids(new), ["M-001", "M-002", "M-003", "M-005"])

    def test_only_its_own_new_measures_go(self):
        new, removed, kept = revision.reset_measures(self.doc, shop="uk", run_id=self.RUN)
        # M-004 legte dieser Lauf an; UK an M-001 kam in diesem Lauf dazu.
        self.assertEqual((removed, kept), (1, 4))
        m001 = new["measures"][0]
        self.assertEqual(m001["shops"], ["eu"])
        self.assertNotIn("uk", m001["by_shop"])

    def test_next_id_stays(self):
        new, _, _ = revision.reset_measures(self.doc, shop="uk", run_id=self.RUN)
        self.assertEqual(new["next_id"], 6)

    def test_an_entry_of_an_earlier_run_survives(self):
        # EU-Lauf vom 15.10.: nur dessen Eintrag an M-002 geht, der Status
        # fällt auf den vorigen zurück.
        new, removed, _ = revision.reset_measures(self.doc, shop="eu",
                                                  run_id="2026-10-15-report")
        m002 = new["measures"][1]
        self.assertEqual(removed, 0)
        self.assertEqual(m002["by_shop"]["eu"]["status"], "open")
        self.assertEqual(len(m002["by_shop"]["eu"]["history"]), 1)

    def test_a_brand_list_needs_shop_and_run(self):
        with self.assertRaises(ValueError):
            revision.reset_measures(self.doc)

    def test_the_cli_resets_the_brand_file_of_its_store(self):
        brand_ws = bs.make_brand(self)
        uk = brand_ws / "uk"
        (uk / "reporting" / "runs" / self.RUN / "findings").mkdir(parents=True)
        bs.write_json(uk / "reporting" / "runs" / self.RUN / "findings" / "cro.json",
                      {"findings": []})
        with contextlib.redirect_stdout(io.StringIO()):
            code = revision.main(["--workspace", str(uk), "--run-id", self.RUN])
        self.assertEqual(code, 0)
        on_disk = bs.read(brand_ws / "reporting" / "measures.json")
        self.assertEqual(self._ids(on_disk), ["M-001", "M-002", "M-003", "M-005"])
        self.assertEqual(on_disk["next_id"], 6)
        archived = uk / "reporting" / "runs" / self.RUN / "revisions" / "01" / "measures.json"
        self.assertEqual(bs.read(archived), bs.fixture())
