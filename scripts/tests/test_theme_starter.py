"""Starter `bin/theme`: findet Python auch ohne python3, setzt PYTHONPATH und PYTHONUTF8.

Jeder Test baut eine eigene Plugin-Wurzel mit einer Kopie des Starters und einem
Modul `theme.probe`, das seine Umgebung als JSON ausgibt. Der PATH enthält nur
die Platzhalter des Tests; die Interpreter des Rechners sieht der Starter nicht.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STARTER = ROOT / "bin" / "theme"
BASH = shutil.which("bash")

PROBE = """import json, os, sys
print(json.dumps({"argv": sys.argv[1:], "pythonpath": os.environ.get("PYTHONPATH"),
                  "utf8": os.environ.get("PYTHONUTF8"), "shim": os.environ.get("PTAI_TEST_SHIM")}))
"""


@unittest.skipIf(BASH is None or os.name == "nt", "braucht bash und POSIX-Platzhalter für den Interpreter")
class TestStarter(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name).resolve()
        self.plugin = self.tmp / "plugin"
        (self.plugin / "bin").mkdir(parents=True)
        shutil.copy2(STARTER, self.plugin / "bin" / "theme")
        package = self.plugin / "scripts" / "theme"
        package.mkdir(parents=True)
        (package / "__init__.py").write_text("", encoding="utf-8")
        (package / "probe.py").write_text(PROBE, encoding="utf-8")
        self.path_dir = self.tmp / "path"
        self.path_dir.mkdir()

    def shim(self, name: str) -> None:
        """Ein Interpreter namens `name` im PATH, der das Python dieses Testlaufs startet."""
        script = self.path_dir / name
        script.write_text(f'#!/bin/sh\nPTAI_TEST_SHIM={name}\nexport PTAI_TEST_SHIM\nexec "{sys.executable}" "$@"\n',
                          encoding="utf-8")
        script.chmod(0o755)

    def run_starter(self, *args: str) -> subprocess.CompletedProcess:
        env = {"PATH": str(self.path_dir), "HOME": str(self.tmp)}
        return subprocess.run([BASH, str(self.plugin / "bin" / "theme"), *args], capture_output=True, encoding="utf-8",
                              env=env, cwd=self.tmp, timeout=60)

    def test_der_starter_findet_python_ohne_python3_und_setzt_die_umgebung(self):
        self.shim("python")
        result = self.run_starter("probe", "show", "--value", "zwei Wörter")
        self.assertEqual(result.returncode, 0, result.stderr)
        seen = json.loads(result.stdout)
        self.assertEqual(seen["shim"], "python")
        self.assertEqual(seen["argv"], ["show", "--value", "zwei Wörter"])
        self.assertEqual(seen["pythonpath"], str(self.plugin / "scripts"))
        self.assertEqual(seen["utf8"], "1")

    def test_ohne_python_nennt_der_starter_den_installationsweg(self):
        result = self.run_starter("probe")
        self.assertEqual(result.returncode, 2)
        self.assertIn("kein Python ab 3.10", result.stderr)
        self.assertIn("winget install Python.Python.3.12", result.stderr)
        self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
