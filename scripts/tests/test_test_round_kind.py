"""Eine Testrunde als Lauf-Art mit Stand je Punkt und Rueckmeldungen."""
import unittest

from audit import manifest, publish


class TestRoundKind(unittest.TestCase):
    def test_test_is_a_known_kind(self):
        manifest_data = manifest.add_run(
            manifest.empty("beispielbrand", "Beispielbrand"),
            shop="beispielshop",
            run_id="2026-09-24-test",
            kind="test",
            cadence="test",
            period=None,
            run_date="2026-09-24",
            files={"test.json": 1},
        )
        self.assertEqual(manifest_data["runs"][0]["kind"], "test")

    def test_the_cadence_names_the_kind(self):
        self.assertEqual(
            publish.run_kind("2026-09-24-test", {"cadence": "test"}),
            ("test", "test"),
        )


if __name__ == "__main__":
    unittest.main()
