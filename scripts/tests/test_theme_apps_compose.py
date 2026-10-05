"""Vergleichsseite aus Bildpaaren: relative Bildpfade, markierte Fehlaufnahmen.

Ein Bild mit falschem Theme sieht aus wie ein Ergebnis. Die Seite muss es so
markieren, dass niemand einen Entwurf mit dem Live-Shop vergleicht, ohne es zu
merken.
"""
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "browser"))

import compose  # noqa: E402

PAIRS = {
    "tool": "shoot_pair",
    "themes": {"a": "000000000000", "b": "000000000002"},
    "captured_at": "2026-01-01T09:00:00+00:00",
    "pairs": [
        {"page_id": "start", "template": "index", "path": "/", "device": "desktop",
         "a": {"state": "ok", "file": "start/desktop-a.png", "fold_file": "start/desktop-a-fold.png",
               "url": "https://beispielshop.example/?preview_theme_id=000000000000&pb=0"},
         "b": {"state": "wrong_theme", "file": "start/desktop-b.png", "fold_file": "start/desktop-b-fold.png",
               "theme_check": {"reason": "Seite zeigt Theme 000000000000"}}},
        {"page_id": "start", "template": "index", "path": "/", "device": "mobile",
         "a": {"state": "ok", "file": "start/mobile-a.png", "fold_file": "start/mobile-a-fold.png", "cut_at": 16000},
         "b": {"state": "error", "error": "Zeitlimit <60s>"}},
    ],
}


class TestVergleichsseite(unittest.TestCase):
    def render(self, pairs_dir: Path, out_dir: Path) -> str:
        return compose.render(PAIRS, pairs_dir, out_dir, "Vergleich Beispielshop")

    def test_relative_pfade_von_der_seite_zu_den_bildern(self):
        page = self.render(Path("/kunde/bilder/2026-01-01"), Path("/kunde"))
        self.assertIn('src="bilder/2026-01-01/start/desktop-a-fold.png"', page)
        self.assertIn('href="bilder/2026-01-01/start/desktop-a.png"', page)
        self.assertEqual(compose.relative_src("start/x.png", Path("/kunde/bilder"), Path("/kunde/bilder")), "start/x.png")

    def test_falsches_theme_und_fehler_sind_markiert_und_escaped(self):
        page = self.render(Path("/kunde/bilder"), Path("/kunde/bilder"))
        self.assertIn("Falsches Theme", page)
        self.assertIn("Seite zeigt Theme 000000000000", page)
        self.assertIn("Zeitlimit &lt;60s&gt;", page)
        self.assertIn("kein Bild", page)
        self.assertIn("abgeschnitten", page)
        self.assertIn("iPhone (WebKit)", page)
        self.assertEqual(page.count("<section>"), 1)

    def test_seite_ist_ein_vollstaendiges_dokument(self):
        page = self.render(Path("/kunde/bilder"), Path("/kunde/bilder"))
        self.assertTrue(page.startswith("<!doctype html>"))
        self.assertIn('<meta name="viewport"', page)
        self.assertIn("<title>Vergleich Beispielshop</title>", page)
        self.assertIn("prefers-color-scheme: dark", page)

    def test_cli_meldet_ungueltige_bilder(self):
        with tempfile.TemporaryDirectory() as tmp:
            pairs_dir = Path(tmp) / "bilder"
            pairs_dir.mkdir()
            (pairs_dir / "pairs.json").write_text(json.dumps(PAIRS), encoding="utf-8")
            out = Path(tmp) / "compare.html"
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                code = compose.main(["--pairs", str(pairs_dir), "--out", str(out)])
            self.assertEqual(code, 1)
            self.assertEqual(json.loads(buffer.getvalue())["invalid_images"], 2)
            self.assertIn('src="bilder/start/desktop-a-fold.png"', out.read_text(encoding="utf-8"))

    def test_ohne_pairs_json_ist_es_ein_fehler(self):
        with tempfile.TemporaryDirectory() as tmp, redirect_stdout(io.StringIO()):
            self.assertEqual(compose.main(["--pairs", tmp, "--out", str(Path(tmp) / "x.html")]), 2)


if __name__ == "__main__":
    unittest.main()
