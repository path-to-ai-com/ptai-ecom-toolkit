"""Der Generator als Befehl: Dateien, Report, `sources.lock`, Zusammenfassung und Exit-Codes."""
import contextlib
import hashlib
import io
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.theme_generate_support import (  # noqa: E402
    FIXTURE, SOURCE, TARGET, fixture_mapping, temp_dir, write_json)
from theme import generate  # noqa: E402


def run(case, mapping_path, *extra):
    base = temp_dir(case)
    out, lock = base / "out", base / "build" / "sources.lock"
    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        code = generate.main(["--mapping", str(mapping_path), "--source", str(SOURCE),
                              "--target-schemas", str(TARGET), "--out", str(out), "--lock", str(lock), *extra])
    return code, out, lock, stdout.getvalue().strip().splitlines()


class Cli(unittest.TestCase):
    def test_a_run_with_findings_writes_files_report_and_lock(self):
        code, out, lock, lines = run(self, FIXTURE / "mapping.json")
        self.assertEqual(code, 1)
        for rel in ("templates/index.json", "templates/product.json", "sections/header-group.json",
                    "config/settings_data.json", "report.json"):
            self.assertTrue((out / rel).is_file(), rel)
        self.assertEqual(len(lines), 1)
        summary = json.loads(lines[0])
        self.assertEqual(summary["build"], 2)
        report = json.loads((out / "report.json").read_text(encoding="utf-8"))
        self.assertEqual(report["summary"], summary)
        self.assertEqual(report["diff"]["new"], ["templates/product.json"])

    def test_the_lock_names_every_input_with_its_sha256(self):
        _, _, lock, _ = run(self, FIXTURE / "mapping.json")
        data = json.loads(lock.read_text(encoding="utf-8"))
        self.assertEqual(data["mapping"]["sha256"], hashlib.sha256((FIXTURE / "mapping.json").read_bytes()).hexdigest())
        for rel in ("templates/index.json", "sections/banner.liquid", "config/settings_data.json"):
            self.assertEqual(data["source"]["files"][rel],
                             hashlib.sha256((SOURCE / rel).read_bytes()).hexdigest(), rel)
        self.assertIn("sections/hero.liquid", data["target"]["files"])
        self.assertIsNone(data["overrides"])

    def test_a_clean_mapping_ends_with_exit_0(self):
        mapping = fixture_mapping()
        mapping["sections"]["banner"]["settings"]["color_scheme"] = {"transform": "drop"}
        mapping["sections"]["promo-strip"] = {"action": "drop", "reason": "entfällt"}
        mapping["sections"]["slider"] = {"action": "drop", "reason": "entfällt"}
        path = temp_dir(self) / "mapping.json"
        write_json(path, mapping)
        code, _, _, lines = run(self, path)
        self.assertEqual(json.loads(lines[0])["findings"], 0)
        self.assertEqual(code, 0)

    def test_an_invalid_mapping_ends_with_exit_2_before_writing(self):
        mapping = fixture_mapping()
        mapping["sections"]["banner"]["settings"]["heading"]["transform"] = "guess"
        path = temp_dir(self) / "mapping.json"
        write_json(path, mapping)
        code, out, _, lines = run(self, path)
        self.assertEqual(code, 2)
        self.assertFalse(out.exists())
        self.assertIn("guess", lines[0])

    def test_out_inside_the_target_repo_ends_with_exit_2(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = generate.main(["--mapping", str(FIXTURE / "mapping.json"), "--source", str(SOURCE),
                                  "--target-schemas", str(TARGET), "--out", str(TARGET / "neu"),
                                  "--lock", str(temp_dir(self) / "sources.lock")])
        self.assertEqual(code, 2)
        self.assertFalse((TARGET / "neu").exists())

    def test_overrides_are_locked_too(self):
        path = temp_dir(self) / "overrides.json"
        write_json(path, {"instances": {"templates/product.json": {"main": {"action": "drop"}}}})
        _, out, lock, _ = run(self, FIXTURE / "mapping.json", "--overrides", str(path))
        self.assertEqual(json.loads(lock.read_text(encoding="utf-8"))["overrides"]["sha256"],
                         hashlib.sha256(path.read_bytes()).hexdigest())
        product = json.loads((out / "templates/product.json").read_text(encoding="utf-8"))
        self.assertEqual(product["sections"], {})


if __name__ == "__main__":
    unittest.main()
