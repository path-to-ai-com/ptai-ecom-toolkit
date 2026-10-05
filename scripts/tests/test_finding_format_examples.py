"""Vertrag und Beispiele zum Befund-Format passen zusammen.

Die Regeln selbst prüft das Kundenportal (`lib/finding-format.ts`) gegen
dieselben Beispieldateien. Hier steht nur, dass die Beispiele lesbar sind, jeder
Verstoß sagt, was er verletzt, und der Vertrag jede Art und jeden Baustein
nennt, den die Beispiele benutzen.
"""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "reference" / "finding-format.md"
EXAMPLES = ROOT / "reference" / "finding-format"

KINDS = ("effect", "cause", "present", "open", "next")
BLOCKS = ("metric", "note", "quote", "chips", "rows", "pairs", "grid", "dist", "image", "phone")


def _findings(data):
    """Die Befunde einer Beispieldatei: eine Befund-Datei oder ein einzelner Befund."""
    return data["findings"] if "findings" in data else [data]


def _blocks(finding):
    proof = finding.get("proof") or []
    columns = proof["columns"] if isinstance(proof, dict) else proof
    return [block for column in columns for block in column.get("blocks", [])]


class TestFindingFormatExamples(unittest.TestCase):
    def setUp(self):
        self.contract = CONTRACT.read_text(encoding="utf-8")
        self.valid = sorted((EXAMPLES / "valid").glob("*.json"))
        self.invalid = sorted((EXAMPLES / "invalid").glob("*.json"))

    def test_there_are_examples_on_both_sides(self):
        self.assertTrue(self.valid)
        self.assertGreaterEqual(len(self.invalid), 10)

    def test_every_example_is_json(self):
        for path in self.valid + self.invalid:
            with self.subTest(path=path.name):
                json.loads(path.read_text(encoding="utf-8"))

    def test_every_violation_names_its_case(self):
        for path in self.invalid:
            with self.subTest(path=path.name):
                case = json.loads(path.read_text(encoding="utf-8")).get("_case", "")
                self.assertTrue(case.strip(), "ohne _case weiß niemand, welche Regel verletzt ist")

    def test_the_contract_names_every_kind_and_block(self):
        for word in KINDS + BLOCKS:
            with self.subTest(word=word):
                self.assertIn(f"`{word}`", self.contract)

    def test_valid_examples_use_only_known_kinds_and_blocks(self):
        for path in self.valid:
            for finding in _findings(json.loads(path.read_text(encoding="utf-8"))):
                for fact in finding.get("facts", []):
                    if "kind" in fact:
                        with self.subTest(path=path.name, kind=fact["kind"]):
                            self.assertIn(fact["kind"], KINDS)
                for block in _blocks(finding):
                    with self.subTest(path=path.name, block=block.get("type")):
                        self.assertIn(block.get("type"), BLOCKS)

    def test_the_full_audit_example_writes_no_quick_win(self):
        # Spec 2026-10-02, Abschnitt 17: im vollen Audit ist die Maßnahme die Handlung.
        data = json.loads((EXAMPLES / "valid" / "full-audit.json").read_text(encoding="utf-8"))
        for finding in data["findings"]:
            for fact in finding.get("facts", []):
                with self.subTest(finding=finding["id"]):
                    self.assertNotIn("now", fact)
                    self.assertIn(fact.get("kind"), ("effect", "cause"))


if __name__ == "__main__":
    unittest.main()
