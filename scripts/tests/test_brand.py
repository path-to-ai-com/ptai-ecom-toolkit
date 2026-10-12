"""Wo die Liste einer Marke liegt, wer sie schreiben darf, und die Sperre (D4, D9, D11)."""
import json
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from audit import brand, config, measures

from tests import brand_support as bs

SCRIPTS = Path(__file__).resolve().parents[1]


class TestBrandPath(unittest.TestCase):
    def test_the_store_reads_and_writes_the_brand_file(self):
        brand_ws = bs.make_brand(self)
        self.assertEqual(measures.file_path(brand_ws / "eu"),
                         brand_ws / "reporting" / "measures.json")
        self.assertEqual(measures.load(brand_ws / "uk")["brand"], bs.BRAND)

    def test_a_relative_brand_workspace_aborts(self):
        brand_ws = bs.make_brand(self)
        bs.write_json(brand_ws / "eu" / "reporting" / "config.json",
                      {**bs.store_config("eu", None), "brand_workspace": ".."})
        with self.assertRaises(brand.BrandFileError) as raised:
            measures.load_or_empty(brand_ws / "eu")
        self.assertIn("absoluter Pfad", str(raised.exception))

    def test_a_missing_brand_file_aborts_instead_of_starting_empty(self):
        # Fehlerfall aus Spec 14: eine Worktree-Session findet die Datei der
        # Marke nicht. Abbruch, keine leere Liste mit eigener Zählung.
        brand_ws = bs.make_brand(self, doc=False)
        with self.assertRaises(brand.BrandFileError) as raised:
            measures.load_or_empty(brand_ws / "eu")
        self.assertIn("keine leere Liste", str(raised.exception))
        with self.assertRaises(brand.BrandFileError):
            measures.save(brand_ws / "eu", measures.empty(bs.BRAND))
        self.assertFalse((brand_ws / "reporting" / "measures.json").exists())
        self.assertFalse((brand_ws / "eu" / "reporting" / "measures.json").exists())

    def test_config_validate_names_a_relative_brand_workspace(self):
        errors = config.validate({"brand_workspace": "../marke"})
        self.assertTrue(any("brand_workspace" in e for e in errors))
        errors = config.validate({"brand_workspace": "/abs/marke"})
        self.assertFalse(any("brand_workspace" in e for e in errors))


class TestNoSecondCounter(unittest.TestCase):
    """D9: hat die Marke ihre Datei, legt kein Store mehr eine eigene an."""

    def test_a_store_without_brand_workspace_aborts(self):
        brand_ws = bs.make_brand(self, linked=False)
        store = brand_ws / "uk"
        with self.assertRaises(brand.BrandFileError) as raised:
            measures.load_or_empty(store)
        self.assertIn("brand_workspace", str(raised.exception))
        with self.assertRaises(brand.BrandFileError):
            measures.save(store, measures.empty())
        self.assertFalse((store / "reporting" / "measures.json").exists())

    def test_a_worktree_below_the_store_aborts_too(self):
        brand_ws = bs.make_brand(self, linked=False)
        worktree = brand_ws / "uk" / ".claude" / "worktrees" / "session"
        bs.write_json(worktree / "reporting" / "config.json", bs.store_config("uk", None))
        with self.assertRaises(brand.BrandFileError):
            measures.load_or_empty(worktree)

    def test_the_file_of_another_brand_does_not_count(self):
        brand_ws = bs.make_brand(self, linked=False)
        bs.write_json(brand_ws / "uk" / "reporting" / "config.json",
                      {**bs.store_config("uk", None), "account_slug": "andere-marke",
                       "portal": {"brand": "andere-marke", "shop": "uk"}})
        self.assertEqual(measures.load_or_empty(brand_ws / "uk"), measures.empty())

    def test_a_store_of_its_own_keeps_its_v1_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            bs.write_json(ws / "reporting" / "config.json", bs.store_config("eu", None))
            saved = measures.save(ws, measures.empty())
            self.assertEqual(saved, ws / "reporting" / "measures.json")


HOLD = """
import fcntl, os, sys, time
fd = os.open(sys.argv[1], os.O_RDWR | os.O_CREAT, 0o644)
fcntl.flock(fd, fcntl.LOCK_EX)
print("locked", flush=True)
time.sleep(float(sys.argv[2]))
"""


class TestLock(unittest.TestCase):
    """D4: ein zweiter Schreiber wartet begrenzt und bricht dann ab."""

    def setUp(self):
        self.brand_ws = bs.make_brand(self)
        self.store = self.brand_ws / "eu"
        self.lock_file = brand.lock_path(self.store)

    def _hold(self, seconds: float) -> subprocess.Popen:
        proc = subprocess.Popen([sys.executable, "-c", HOLD, str(self.lock_file), str(seconds)],
                                stdout=subprocess.PIPE, text=True)
        self.addCleanup(proc.wait)
        self.assertEqual(proc.stdout.readline().strip(), "locked")
        return proc

    def test_the_lock_lies_in_the_brand_folder(self):
        self.assertEqual(self.lock_file.parent, self.brand_ws / "reporting")

    def test_a_second_writer_waits_for_the_first(self):
        self._hold(0.6)
        started = time.monotonic()
        with brand.lock(self.store, timeout=10):
            waited = time.monotonic() - started
        self.assertGreater(waited, 0.3)

    def test_a_second_writer_gives_up_with_a_message(self):
        self._hold(2)
        backlog = measures.load(self.store)
        with self.assertRaises(brand.BrandFileError) as raised:
            with brand.lock(self.store, timeout=0.3):
                pass
        self.assertIn("gesperrt", str(raised.exception))
        # save() wartet ebenso und schreibt nichts.
        original = brand.LOCK_TIMEOUT_SECONDS
        brand.LOCK_TIMEOUT_SECONDS = 0.3
        self.addCleanup(setattr, brand, "LOCK_TIMEOUT_SECONDS", original)
        with self.assertRaises(brand.BrandFileError):
            measures.save(self.store, {**backlog, "next_id": 99})
        self.assertEqual(measures.peek(self.store)["next_id"], 6)

    def test_the_lock_is_reentrant_within_one_process(self):
        with measures.locked(self.store, timeout=0.5):
            backlog = measures.load(self.store)
            measures.save(self.store, {**backlog, "next_id": 7})
        self.assertEqual(measures.peek(self.store)["next_id"], 7)
        self.assertFalse(brand.holds_lock(self.store))


class TestFindingIds(unittest.TestCase):
    def test_raw_and_report_ids_and_revisions(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp)
            bs.write_json(run / "findings" / "data-quality.json",
                          {"findings": [{"id": "DQ-07"}, {"id": "MES-02"}]})
            bs.write_json(run / "revisions" / "01" / "findings" / "sea.json",
                          {"findings": [{"id": "SEA-09"}]})
            self.assertEqual(brand.finding_ids(run, include_revisions=False),
                             {"DQ-07", "MES-07", "MES-02"})
            self.assertIn("SEA-09", brand.finding_ids(run))


if __name__ == "__main__":
    unittest.main()
