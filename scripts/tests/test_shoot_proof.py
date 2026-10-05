"""Belegbilder aus Aufnahme-Aufträgen: was ohne Browser feststeht.

Die Aufnahme selbst braucht Playwright und einen echten Shop. Geprüft wird hier,
was daraus wird: Dateinamen, Ausschnitt, Markierungen in Prozent, die Höhe des
Handy-Ausschnitts, das Ergebnis neben dem Auftrag, und der Weg durch einen
Cookie-Dialog, der auf der ersten Ebene kein Ablehnen hat.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "skills" / "capture-screens" / "scripts"))

import consent  # noqa: E402
import shoot_proof  # noqa: E402


class TestFileNames(unittest.TestCase):
    def test_the_name_is_fixed_per_finding_image_and_device(self):
        self.assertEqual(shoot_proof.file_name("CRO-01", 1, "mobil"), "proof/cro-01-1-mobil.jpg")
        self.assertEqual(shoot_proof.file_name("CRO-01", 1, "mobil", full=True), "proof/cro-01-1-mobil-voll.jpg")


class TestCaptureBlocks(unittest.TestCase):
    finding = {
        "id": "TRS-02",
        "proof": {"columns": [
            {"blocks": [{"type": "image", "capture": {"url": "https://beispielshop.test/"}, "alt": "a", "title": "t"}]},
            {"blocks": [{"type": "metric", "ref": 0},
                        {"type": "phone", "capture": {"url": "https://beispielshop.test/p"}, "src": "proof/x.jpg"}]},
        ]},
    }

    def test_only_image_blocks_with_a_capture_count_and_are_numbered(self):
        numbers = [(n, b["type"]) for n, b in shoot_proof.capture_blocks(self.finding)]
        self.assertEqual(numbers, [(1, "image"), (2, "phone")])

    def test_a_block_with_a_result_is_done_unless_refreshed(self):
        image, phone = [b for _, b in shoot_proof.capture_blocks(self.finding)]
        self.assertTrue(shoot_proof.is_open(image))
        self.assertFalse(shoot_proof.is_open(phone))
        self.assertTrue(shoot_proof.is_open(phone, refresh=True))

    def test_a_phone_is_always_taken_on_the_phone(self):
        _, phone = shoot_proof.capture_blocks(self.finding)[1]
        self.assertEqual(shoot_proof.device_of(phone), "mobil")


class TestGeometry(unittest.TestCase):
    viewport = {"width": 1440, "height": 900}

    def test_the_crop_gets_a_margin_and_stays_on_screen(self):
        clip = shoot_proof.pad_clip({"x": 10, "y": 850, "width": 200, "height": 100}, self.viewport, padding=24)
        self.assertEqual(clip, {"x": 0, "y": 826, "width": 234, "height": 74})

    def test_a_ring_is_a_share_of_the_crop_with_margin(self):
        clip = {"x": 100, "y": 100, "width": 500, "height": 200}
        ring = shoot_proof.ring_percent({"x": 150, "y": 150, "width": 100, "height": 50}, clip, padding=0)
        self.assertEqual(ring, {"left": 10.0, "top": 25.0, "width": 20.0, "height": 25.0})

    def test_a_ring_never_leaves_the_image(self):
        clip = {"x": 0, "y": 0, "width": 100, "height": 100}
        ring = shoot_proof.ring_percent({"x": 90, "y": -5, "width": 30, "height": 20}, clip, padding=0)
        self.assertLessEqual(ring["left"] + ring["width"], 100)
        self.assertGreaterEqual(ring["top"], 0)

    def test_the_union_holds_every_box(self):
        box = shoot_proof.union([{"x": 10, "y": 10, "width": 10, "height": 10},
                                 {"x": 50, "y": 5, "width": 5, "height": 40}])
        self.assertEqual(box, {"x": 10, "y": 5, "width": 45, "height": 40})

    def test_the_phone_strip_ends_shortly_below_the_lowest_marker(self):
        self.assertEqual(shoot_proof.strip_height(664, [807.0], 5538), 907)
        self.assertEqual(shoot_proof.strip_height(664, [], 5538), 764)
        self.assertEqual(shoot_proof.strip_height(664, [900.0], 950), 950)

    def test_wide_crops_keep_the_maximum_width(self):
        self.assertEqual(shoot_proof.scale_for(560), "device")
        self.assertEqual(shoot_proof.scale_for(1440), "css")


class TestResult(unittest.TestCase):
    def test_the_result_sits_next_to_the_capture(self):
        block = {"type": "image", "capture": {"url": "https://beispielshop.test/"}, "alt": "a", "title": "t"}
        updated = shoot_proof.apply_result(block, {"src": "proof/x-1-desktop.jpg", "width": 1120, "height": 620,
                                                   "rings": [], "device": "desktop"})
        self.assertEqual(updated["capture"], block["capture"])
        self.assertEqual(updated["alt"], "a")
        self.assertEqual(updated["src"], "proof/x-1-desktop.jpg")
        self.assertNotIn("src", block, "der Auftrag selbst bleibt unverändert")

    def test_the_findings_file_is_written_whole_or_not_at_all(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cro.json"
            path.write_text("{}", encoding="utf-8")
            shoot_proof.write_json_atomic(path, {"findings": [{"id": "CRO-01", "text": "Ä"}]})
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["findings"][0]["text"], "Ä")
            self.assertEqual([p.name for p in Path(tmp).iterdir()], ["cro.json"], "keine Reste daneben")


class FakeLocator:
    def __init__(self, page, text):
        self.page, self.text = page, text

    def count(self):
        return 1 if self.text in self.page.visible else 0

    def nth(self, index):
        return self

    def is_visible(self):
        return self.text in self.page.visible

    def click(self, timeout=None):
        self.page.clicks.append(self.text)
        self.page.visible = set(self.page.after.get(self.text, self.page.visible))

    @property
    def first(self):
        return self


class FakePage:
    """Ein Cookie-Dialog wie der, an dem der Weg über die zweite Ebene entstand."""

    def __init__(self, visible, after):
        self.visible, self.after, self.clicks = set(visible), after, []

    def wait_for_selector(self, selector, state=None, timeout=None):
        raise TimeoutError("kein bekanntes Consent-Tool")

    def locator(self, selector):
        return FakeLocator(self, f"selector:{selector}")

    def get_by_text(self, text, exact=False):
        return FakeLocator(self, text)

    def wait_for_timeout(self, ms):
        pass


class TestConsent(unittest.TestCase):
    def test_a_dialog_without_decline_on_the_first_level_is_declined_on_the_second(self):
        page = FakePage(
            visible={"Alle akzeptieren", "Nein, anpassen"},
            after={"Nein, anpassen": {"Alle akzeptieren", "Einstellungen speichern", "Ablehnen"},
                   "Ablehnen": set()},
        )
        self.assertEqual(consent.decline(page, wait_ms=0), (consent.DECLINED, "Nein, anpassen > Ablehnen"))
        self.assertEqual(page.clicks, ["Nein, anpassen", "Ablehnen"])

    def test_a_decline_on_the_first_level_is_taken_directly(self):
        page = FakePage(visible={"Alle akzeptieren", "Alle ablehnen"}, after={"Alle ablehnen": set()})
        self.assertEqual(consent.decline(page, wait_ms=0), (consent.DECLINED, "Alle ablehnen"))

    def test_a_page_without_a_dialog_needs_nothing(self):
        page = FakePage(visible={"Einstellungen"}, after={})
        self.assertEqual(consent.decline(page, wait_ms=0), (consent.NO_DIALOG, None))
        self.assertEqual(page.clicks, [], "ohne Dialog wird nichts geklickt, auch kein Footer-Link")

    def test_a_dialog_that_does_not_go_away_is_stuck(self):
        page = FakePage(visible={"Alle akzeptieren"}, after={})
        self.assertEqual(consent.decline(page, wait_ms=0), (consent.STUCK, None))


if __name__ == "__main__":
    unittest.main()
