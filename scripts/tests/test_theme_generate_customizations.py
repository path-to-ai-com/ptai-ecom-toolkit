"""Anpassungen finden (`diff`) und das Verzeichnis der Eingriffe prüfen (`check`).

`check` läuft gegen ein Git-Repo im Temp-Ordner: ein Commit als Upstream-Stand,
danach eigene Dateien und Eingriffe, für `--against` ein Branch mit dem Update.
"""
import contextlib
import io
import json
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.theme_generate_support import temp_dir  # noqa: E402
from theme import customizations  # noqa: E402


def write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class Diff(unittest.TestCase):
    def setUp(self):
        base = temp_dir(self)
        self.original, self.current = base / "original", base / "current"
        for root in (self.original, self.current):
            write(root, "sections/hero.liquid", "<div>{{ section.settings.title }}</div>\n")
            write(root, "assets/base.css", ".a { color: red; margin: 0 }\n")
            write(root, "assets/theme.css", ".b { color: blue; }\n")
            write(root, "snippets/alt.liquid", "alt\n")
            write(root, "templates/index.json", "{}\n")
        write(self.current, "sections/hero.liquid", "<div>{{ section.settings.title }}</div>\n<p>neu</p>\n")
        write(self.current, "assets/base.css", "/* Kommentar */\n.a {\n  margin: 0;\n  color: red;\n}\n")
        write(self.current, "assets/theme.css", ".b { color: blue; }\n.c { color: green; }\n")
        write(self.current, "snippets/neu.liquid", "neu\n")
        (self.current / "snippets/alt.liquid").unlink()
        write(self.current, "templates/index.json", "{\"sections\": {}}\n")
        (self.current / "assets/logo.png").write_bytes(b"\x89PNG\x00\xff")

    def candidates(self):
        return {c["file"]: c for c in customizations.diff_themes(self.original, self.current)["candidates"]}

    def test_kinds_and_scope(self):
        found = self.candidates()
        self.assertEqual(found["sections/hero.liquid"]["kind"], "changed")
        self.assertEqual(found["sections/hero.liquid"]["lines_added"], 1)
        self.assertEqual(found["snippets/neu.liquid"]["kind"], "added")
        self.assertEqual(found["snippets/alt.liquid"]["kind"], "removed")
        self.assertTrue(found["assets/logo.png"]["binary"])

    def test_css_is_compared_rule_by_rule_after_normalizing(self):
        found = self.candidates()
        self.assertEqual(found["assets/base.css"]["kind"], "formatting")
        self.assertEqual((found["assets/theme.css"]["rules_added"], found["assets/theme.css"]["rules_removed"]), (1, 0))

    def test_content_files_are_not_customizations(self):
        self.assertNotIn("templates/index.json", self.candidates())

    def test_cli_writes_the_candidates(self):
        out = temp_dir(self) / "candidates.json"
        with contextlib.redirect_stdout(io.StringIO()):
            code = customizations.main(["diff", "--original", str(self.original), "--current", str(self.current),
                                        "--out", str(out)])
        self.assertEqual(code, 1)
        self.assertEqual(len(json.loads(out.read_text(encoding="utf-8"))["candidates"]), 6)


class Check(unittest.TestCase):
    REGISTER_HEAD = "---\ntheme_version: 4.0.0\nupstream_ref: upstream\n---\n\n# Eingriffe\n\n## Verzeichnis\n\n" \
                    "| Datei | Änderung | Grund | Nach einem Update prüfen |\n|---|---|---|---|\n"

    def git(self, *args):
        result = subprocess.run(["git", "-C", str(self.repo), "-c", "user.name=Test", "-c", "user.email=test@example.com",
                                 *args], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def setUp(self):
        base = temp_dir(self)
        self.repo = base / "theme"
        self.repo.mkdir()
        self.git("init", "-q", "-b", "main")
        write(self.repo, "sections/header.liquid", "<header>{% render 'logo' %}</header>\n")
        write(self.repo, "snippets/logo.liquid", "<img>\n")
        write(self.repo, "snippets/icon.liquid", "<svg></svg>\n")
        write(self.repo, "assets/base.css", ".card { color: red; }\n")
        write(self.repo, "assets/cart.js", "export const cart = 1;\n")
        write(self.repo, "config/settings_schema.json", "[]\n")
        write(self.repo, "templates/index.json", "{}\n")
        self.git("add", ".")
        self.git("commit", "-q", "-m", "Upstream 4.0.0")
        self.git("branch", "upstream")
        # Eigene Arbeit: eine Datei mit Präfix, ein markierter Eingriff, Inhalte.
        write(self.repo, "snippets/beispiel-badge.liquid", "{% render 'icon' %}<span class=\"card\"></span>\n")
        write(self.repo, "assets/beispiel-brand.css", ".card { color: blue; }\n.beispiel-x { color: red; }\n")
        write(self.repo, "sections/header.liquid",
              "<header>{% render 'logo' %}{% comment %}beispiel: Abzeichen{% endcomment %}"
              "{% render 'beispiel-badge' %}</header>\n")
        write(self.repo, "templates/index.json", "{\"sections\": {}}\n")
        self.git("add", ".")
        self.git("commit", "-q", "-m", "Eigene Arbeit")
        self.register = base / "customizations.md"
        self.write_register(["sections/header.liquid"])

    def write_register(self, paths):
        rows = "".join(f"| `{p}` | geändert | Grund | Prüfung |\n" for p in paths)
        self.register.write_text(self.REGISTER_HEAD + rows, encoding="utf-8")

    def check(self, against=None):
        return customizations.check_repo(self.repo, "beispiel", self.register, against)

    def test_a_registered_and_marked_intervention_passes(self):
        result = self.check()
        self.assertEqual(result["changed_core_files"], ["sections/header.liquid"])
        self.assertEqual(result["findings"], 0)

    def test_an_unregistered_change_is_a_finding(self):
        write(self.repo, "assets/cart.js", "// beispiel: Weiterleitung\nexport const cart = 2;\n")
        result = self.check()
        self.assertEqual(result["missing_in_register"], ["assets/cart.js"])

    def test_an_entry_without_change_is_a_finding(self):
        self.write_register(["sections/header.liquid", "snippets/logo.liquid"])
        self.assertEqual(self.check()["register_without_change"], ["snippets/logo.liquid"])

    def test_a_change_without_marker_comment_is_a_finding(self):
        write(self.repo, "snippets/logo.liquid", "<img alt=\"\">\n")
        self.write_register(["sections/header.liquid", "snippets/logo.liquid"])
        self.assertEqual(self.check()["missing_marker"], ["snippets/logo.liquid"])

    def test_json_cannot_carry_a_comment_and_needs_only_the_register(self):
        write(self.repo, "config/settings_schema.json", "[{\"name\": \"x\"}]\n")
        self.write_register(["sections/header.liquid", "config/*.json"])
        self.assertEqual(self.check()["findings"], 0)

    def test_an_own_file_without_prefix_is_a_finding(self):
        write(self.repo, "snippets/badge.liquid", "x\n")
        self.assertEqual(self.check()["own_files_without_prefix"], ["snippets/badge.liquid"])

    def test_against_shows_registered_files_the_update_touches_and_lost_names(self):
        self.git("checkout", "-q", "-b", "update", "upstream")
        write(self.repo, "sections/header.liquid", "<header class=\"neu\">{% render 'logo' %}</header>\n")
        (self.repo / "snippets/icon.liquid").unlink()
        write(self.repo, "assets/base.css", ".tile { color: red; }\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "Upstream 4.1.0")
        self.git("checkout", "-q", "main")
        result = self.check("update")
        self.assertEqual(result["check_after_update"], ["sections/header.liquid"])
        lost = {(n["kind"], n["name"]) for n in result["names_lost_in_update"]}
        self.assertEqual(lost, {("snippet", "snippets/icon.liquid"), ("class", "card")})

    def test_cli_exit_codes(self):
        with contextlib.redirect_stdout(io.StringIO()):
            ok = customizations.main(["check", "--target-repo", str(self.repo), "--prefix", "beispiel",
                                      "--register", str(self.register)])
            self.register.write_text("# ohne Kopf\n", encoding="utf-8")
            broken = customizations.main(["check", "--target-repo", str(self.repo), "--prefix", "beispiel",
                                          "--register", str(self.register)])
        self.assertEqual((ok, broken), (0, 2))


if __name__ == "__main__":
    unittest.main()
