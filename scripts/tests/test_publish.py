"""Einen Lauf für die Kundenansicht bereitstellen: was mitgeht, was bleibt."""
import contextlib
import io
import json
import os
import tempfile
import unittest
import urllib.error
from datetime import date
from pathlib import Path
from unittest import mock

from audit import manifest, publish

MANIFEST_KEY = "brands/beispielkunde/manifest.json"


def make_workspace(root: Path, run_id: str) -> Path:
    """Ein Kunden-Workspace mit einem Lauf, der drei Dateien trägt."""
    ws = root / "workspace"
    run = ws / "reporting" / "runs" / run_id
    (run / "findings").mkdir(parents=True)
    (ws / "reporting" / "config.json").write_text(json.dumps({
        "account_slug": "beispielkunde", "brand": "Beispielshop",
        "domain": "https://beispielshop.test"}), encoding="utf-8")
    (run / "state.json").write_text(json.dumps({
        "run_id": run_id, "cadence": "audit", "period": None}),
        encoding="utf-8")
    (run / "audit.pdf").write_bytes(b"%PDF")
    (run / "audit-web.html").write_text("<html>", encoding="utf-8")
    (run / "findings" / "cro.json").write_text("{}", encoding="utf-8")
    return ws


class TestSlugify(unittest.TestCase):
    def test_a_shop_name_becomes_a_path_segment(self):
        self.assertEqual(publish.slugify("Beispielshop"), "beispielshop")

    def test_an_ampersand_disappears(self):
        self.assertEqual(publish.slugify("Nord & Stein"), "nord-stein")

    def test_umlauts_become_ascii(self):
        # Dateinamen und Pfade sind ASCII, auch wenn der Shop es nicht ist.
        self.assertEqual(publish.slugify("Grün & Söhne"), "gruen-soehne")


class TestPrepare(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.run_id = "2026-09-08-audit"
        self.ws = make_workspace(Path(self.tmp.name), self.run_id)
        self.bucket = Path(self.tmp.name) / "bucket"

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self):
        return publish.prepare(self.ws, self.run_id, self.bucket)

    def test_the_run_lands_under_customer_and_shop(self):
        out = self._run()
        self.assertEqual((out["brand"], out["shop"]),
                         ("beispielkunde", "beispielshop"))
        run_target = self.bucket / "brands/beispielkunde/shops/beispielshop/runs" / self.run_id
        self.assertTrue((run_target / "audit.pdf").exists())
        self.assertTrue((run_target / "findings" / "cro.json").exists())

    def test_the_title_from_the_state_reaches_the_manifest(self):
        state_path = self.ws / "reporting" / "runs" / self.run_id / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state_path.write_text(json.dumps({**state, "title": "Abstimmung vor dem Theme-Wechsel"}),
                              encoding="utf-8")
        self._run()
        manifest_data = manifest.load(self.bucket / MANIFEST_KEY)
        self.assertEqual(manifest_data["runs"][0]["title"], "Abstimmung vor dem Theme-Wechsel")

    def test_publishing_never_releases(self):
        self._run()
        manifest_data = manifest.load(self.bucket / "brands/beispielkunde/manifest.json")
        self.assertFalse(manifest_data["runs"][0]["released"])
        self.assertEqual(manifest.released(manifest_data), [])

    def test_the_ledger_stays_behind(self):
        (self.ws / "reporting" / "runs" / self.run_id / "dfs-ledger.jsonl"
         ).write_text("{}", encoding="utf-8")
        self._run()
        run_target = self.bucket / "brands/beispielkunde/shops/beispielshop/runs" / self.run_id
        self.assertFalse((run_target / "dfs-ledger.jsonl").exists())

    def test_earlier_versions_stay_behind(self):
        revision_dir = self.ws / "reporting" / "runs" / self.run_id / "revisions" / "01"
        revision_dir.mkdir(parents=True)
        (revision_dir / "audit.pdf").write_bytes(b"%PDF")
        self._run()
        run_target = self.bucket / "brands/beispielkunde/shops/beispielshop/runs" / self.run_id
        self.assertFalse((run_target / "revisions").exists())

    def test_the_shop_carries_its_display_name(self):
        self._run()
        manifest_data = manifest.load(self.bucket / "brands/beispielkunde/manifest.json")
        self.assertEqual(manifest_data["shops"]["beispielshop"]["name"], "Beispielshop")

    def test_the_run_carries_a_snapshot_of_the_measures(self):
        """Der Stand auf Shop-Ebene wird bei jedem publish ueberschrieben. Ohne
        die Kopie im Lauf gaebe es keinen frueheren Stand, gegen den sich
        vergleichen liesse."""
        (self.ws / "reporting" / "measures.json").write_text(
            json.dumps({"next_id": 2, "measures": []}), encoding="utf-8")
        result = self._run()
        snapshot = (self.bucket
                    / manifest.path_for("beispielkunde", "beispielshop", self.run_id)
                    / "measures.json")
        self.assertTrue(snapshot.exists())
        manifest_data = manifest.load(self.bucket / MANIFEST_KEY)
        self.assertIn("measures.json", manifest_data["runs"][0]["files"])
        self.assertEqual(result["files"], len(manifest_data["runs"][0]["files"]))

    def test_the_run_carries_a_snapshot_of_the_feedback(self):
        """Wie beim Backlog: die Datei auf Shop-Ebene ist der aktuelle Stand,
        die Kopie im Lauf haelt fest, welche Zuordnungen damals galten."""
        (self.ws / "reporting" / "feedback.json").write_text(
            json.dumps({"entries": []}), encoding="utf-8")
        self._run()
        snapshot = (self.bucket
                    / manifest.path_for("beispielkunde", "beispielshop", self.run_id)
                    / "feedback.json")
        self.assertTrue(snapshot.exists())
        manifest_data = manifest.load(self.bucket / MANIFEST_KEY)
        self.assertIn("feedback.json", manifest_data["runs"][0]["files"])

    def test_the_shop_carries_the_feedback(self):
        """Ansicht 3 liest die Zuordnungen vom Shop, nicht aus einem Lauf."""
        (self.ws / "reporting" / "feedback.json").write_text(
            json.dumps({"entries": []}), encoding="utf-8")
        self._run()
        shop_target = self.bucket / manifest.path_for("beispielkunde", "beispielshop")
        self.assertTrue((shop_target / "feedback.json").exists())

    def test_a_run_without_feedback_stays_unchanged(self):
        """Ein Shop ohne Rueckmeldung von aussen ist der Normalfall. Es darf
        nichts Erfundenes im Bucket landen."""
        self._run()
        run_target = (self.bucket
                      / manifest.path_for("beispielkunde", "beispielshop", self.run_id))
        self.assertFalse((run_target / "feedback.json").exists())

    def test_a_run_without_measures_stays_unchanged(self):
        """Ein Kurz-Audit hat keinen Backlog. Er darf daran nicht scheitern,
        und es darf auch nichts Erfundenes im Bucket landen."""
        self._run()
        run_target = (self.bucket
                      / manifest.path_for("beispielkunde", "beispielshop", self.run_id))
        self.assertFalse((run_target / "measures.json").exists())

    def test_a_second_publish_leaves_the_first_version_alone(self):
        """Bis zum 17.09.2026 pruefte dieser Test, dass eine geloeschte Datei
        im Bucket nicht stehenbleibt, und schaute dafuer auf den flachen
        Lauf-Pfad. Seit den Fassungen ist die Bedeutung eine andere: die neue
        Fassung traegt, was der Workspace sagt, und die alte bleibt
        vollstaendig liegen, weil sie das Archiv ist."""
        self._run()
        run = self.ws / "reporting" / "runs" / self.run_id
        (run / "audit.pdf").unlink()
        (run / "neu.txt").write_text("x", encoding="utf-8")
        result = self._run()

        erste = self.bucket / "brands/beispielkunde/shops/beispielshop/runs" / self.run_id
        zweite = Path(result["path"])
        self.assertTrue((zweite / "neu.txt").exists())
        self.assertFalse((zweite / "audit.pdf").exists(),
                         "eine geloeschte Datei darf in der neuen Fassung "
                         "nicht stehenbleiben")
        self.assertTrue((erste / "audit.pdf").exists())
        self.assertFalse((erste / "neu.txt").exists())

    def test_a_second_publish_keeps_an_existing_release(self):
        self._run()
        manifest_path = self.bucket / "brands/beispielkunde/manifest.json"
        manifest.save(manifest_path, manifest.release(manifest.load(manifest_path),
                                                      "beispielshop", self.run_id))
        result = publish.prepare(self.ws, self.run_id, self.bucket, visible=True)
        self.assertTrue(manifest.load(manifest_path)["runs"][0]["released"])
        self.assertTrue(result["released"],
                        "die Meldung muss die übernommene Freigabe zeigen")

    def test_a_new_version_of_a_released_run_needs_visible(self):
        # Spec ptai-portal 2026-10-02, Abschnitt 17, Punkt 2: sonst wäre die
        # neue Fassung ohne Abnahme sofort beim Kunden.
        self._run()
        manifest_path = self.bucket / "brands/beispielkunde/manifest.json"
        manifest.save(manifest_path, manifest.release(manifest.load(manifest_path),
                                                      "beispielshop", self.run_id))
        before = manifest.load(manifest_path)
        with self.assertRaises(SystemExit):
            self._run()
        self.assertEqual(manifest.load(manifest_path), before, "das Manifest darf sich nicht ändern")
        self.assertFalse((self.bucket / manifest.path_for("beispielkunde", "beispielshop",
                                                          self.run_id, 2)).exists(),
                         "es darf nichts kopiert sein")

    def test_replace_on_a_released_run_needs_visible_too(self):
        self._run()
        manifest_path = self.bucket / "brands/beispielkunde/manifest.json"
        manifest.save(manifest_path, manifest.release(manifest.load(manifest_path),
                                                      "beispielshop", self.run_id))
        with self.assertRaises(SystemExit):
            publish.prepare(self.ws, self.run_id, self.bucket, replace=True)

    def test_an_unreleased_run_takes_a_new_version_without_visible(self):
        self._run()
        self.assertEqual(self._run()["revision"], 2)

    def test_another_account_slug_sends_the_run_to_another_brand(self):
        result = publish.prepare(self.ws, self.run_id, self.bucket, account_slug="portal-test")
        self.assertEqual(result["brand"], "portal-test")
        self.assertTrue((self.bucket / "brands/portal-test/manifest.json").exists())
        self.assertFalse((self.bucket / "brands/beispielkunde/manifest.json").exists(),
                         "die Marke aus der Config bleibt unberührt")
        self.assertFalse(result["released"])

    def test_release_local_releases_an_uploaded_run(self):
        from audit import release
        self._run()
        entry = release.release_local(self.bucket, "beispielkunde", "beispielshop", self.run_id,
                                      today=date(2026, 10, 2))
        self.assertTrue(entry["released"])
        self.assertEqual(entry["released_at"], "2026-10-02")
        self.assertTrue(manifest.load(self.bucket / MANIFEST_KEY)["runs"][0]["released"])

    def test_release_local_refuses_a_run_that_was_never_uploaded(self):
        from audit import release
        self._run()
        with self.assertRaises(KeyError):
            release.release_local(self.bucket, "beispielkunde", "beispielshop", "2026-01-01-audit")

    def _findings_with(self, block):
        (self.ws / "reporting" / "runs" / self.run_id / "findings" / "cro.json").write_text(json.dumps({
            "findings": [{"id": "CRO-01", "proof": {"columns": [{"blocks": [block]}]}}]}),
            encoding="utf-8")

    def test_an_open_capture_stops_the_publish(self):
        self._findings_with({"type": "phone", "capture": {"url": "https://beispielshop.test/p"}})
        with self.assertRaises(SystemExit) as raised:
            self._run()
        self.assertIn("CRO-01", str(raised.exception))
        self.assertFalse((self.bucket / MANIFEST_KEY).exists(), "es darf nichts eingetragen sein")

    def test_a_missing_proof_image_stops_the_publish(self):
        self._findings_with({"type": "image", "src": "proof/cro-01-1-desktop.jpg", "alt": "a", "title": "t"})
        with self.assertRaises(SystemExit) as raised:
            self._run()
        self.assertIn("proof/cro-01-1-desktop.jpg", str(raised.exception))

    def test_a_taken_proof_image_goes_up_with_the_run(self):
        run = self.ws / "reporting" / "runs" / self.run_id
        (run / "proof").mkdir()
        (run / "proof" / "cro-01-1-mobil.jpg").write_bytes(b"\xff\xd8")
        (run / "proof" / "cro-01-1-mobil-voll.jpg").write_bytes(b"\xff\xd8")
        self._findings_with({"type": "phone", "capture": {"url": "https://beispielshop.test/p"},
                             "src": "proof/cro-01-1-mobil.jpg", "full_src": "proof/cro-01-1-mobil-voll.jpg"})
        self._run()
        entry = manifest.load(self.bucket / MANIFEST_KEY)["runs"][0]
        self.assertIn("proof/cro-01-1-mobil.jpg", entry["files"])
        self.assertEqual(publish.CONTENT_TYPES[".jpg"], "image/jpeg")

    def test_a_first_publish_reports_no_release(self):
        self.assertFalse(self._run()["released"])

    def test_a_config_without_a_customer_stops(self):
        (self.ws / "reporting" / "config.json").write_text(
            json.dumps({"brand": "Beispielshop"}), encoding="utf-8")
        with self.assertRaises(SystemExit):
            self._run()

    def test_an_unknown_run_stops(self):
        with self.assertRaises(SystemExit):
            publish.prepare(self.ws, "2026-01-01-audit", self.bucket)

    def test_two_shops_of_one_customer_share_a_manifest(self):
        self._run()
        (self.ws / "reporting" / "config.json").write_text(json.dumps({
            "account_slug": "beispielkunde", "brand": "Zweitshop",
            "domain": "https://zweitshop.test"}), encoding="utf-8")
        self._run()
        manifest_data = manifest.load(self.bucket / "brands/beispielkunde/manifest.json")
        self.assertEqual(set(manifest_data["shops"]), {"beispielshop", "zweitshop"})
        self.assertEqual(len(manifest_data["runs"]), 2)


class _Response(io.BytesIO):
    status = 200


class FakeBucket:
    """Der Bucket im Speicher, an der Stelle von `urllib.request.urlopen`.

    Kein Test öffnet einen Socket. GET liest aus `objects`, POST schreibt
    hinein, und jeder Aufruf landet in `calls`, damit ein Test sieht, ob etwas
    hochging.
    """
    URL = "https://bucket.test"
    PREFIX = f"{URL}/storage/v1/object/runs/"

    def __init__(self, objects=None, get_status=None, get_body=b""):
        self.objects = dict(objects or {})
        self.get_status = get_status
        self.get_body = get_body
        self.calls = []

    def urlopen(self, request, timeout=None):
        key = request.full_url.removeprefix(self.PREFIX)
        method = request.get_method()
        self.calls.append((method, key))
        if method == "POST":
            self.objects[key] = request.data
            return _Response(b"{}")
        if self.get_status is None and key in self.objects:
            return _Response(self.objects[key])
        raise urllib.error.HTTPError(request.full_url, self.get_status or 404,
                                     "", {}, io.BytesIO(self.get_body))

    def uploads(self):
        return [key for method, key in self.calls if method == "POST"]

    def manifest(self):
        return json.loads(self.objects[MANIFEST_KEY])


class TestRevisionOnPublish(unittest.TestCase):
    """Ein zweites publish derselben Lauf-ID ist eine Korrektur. Sie bekommt
    einen eigenen Pfad, damit der Upload die erste Fassung nicht mit
    `x-upsert` ueberschreibt."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.run_id = "2026-09-08-audit"
        self.ws = make_workspace(Path(self.tmp.name), self.run_id)
        self.bucket = Path(self.tmp.name) / "bucket"

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_second_publish_writes_a_second_version(self):
        publish.prepare(self.ws, self.run_id, self.bucket)
        first = (self.bucket
                 / manifest.path_for("beispielkunde", "beispielshop", self.run_id)
                 / "audit-web.html")
        first_text = first.read_text(encoding="utf-8")

        (self.ws / "reporting" / "runs" / self.run_id / "audit-web.html").write_text(
            "<html>korrigiert", encoding="utf-8")
        result = publish.prepare(self.ws, self.run_id, self.bucket,
                                 note="GA4-Doppelzaehlung nachgetragen")

        self.assertEqual(result["revision"], 2)
        # Die erste Fassung liegt unangetastet da, wo sie lag.
        self.assertEqual(first.read_text(encoding="utf-8"), first_text)
        second = Path(result["path"]) / "audit-web.html"
        self.assertTrue(second.as_posix().endswith("/v02/audit-web.html"))
        self.assertEqual(second.read_text(encoding="utf-8"), "<html>korrigiert")

        manifest_data = manifest.load(self.bucket / MANIFEST_KEY)
        run = manifest_data["runs"][0]
        self.assertEqual([r["no"] for r in run["revisions"]], [1, 2])
        self.assertEqual(run["revisions"][1]["note"], "GA4-Doppelzaehlung nachgetragen")

    def test_replace_keeps_the_running_version(self):
        publish.prepare(self.ws, self.run_id, self.bucket)
        result = publish.prepare(self.ws, self.run_id, self.bucket, replace=True)
        self.assertEqual(result["revision"], 1)
        manifest_data = manifest.load(self.bucket / MANIFEST_KEY)
        self.assertEqual(len(manifest_data["runs"][0]["revisions"]), 1)


class TestUpload(unittest.TestCase):
    """`publish --upload` in ein frisches Ziel, während der Bucket schon Läufe kennt.

    Ohne das Manifest aus dem Bucket baut `prepare()` auf einem leeren auf, und
    der Upload ersetzt damit das im Bucket: jeder andere Lauf verschwindet aus
    dem Portal, eine Freigabe geht verloren.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.run_id = "2026-09-08-audit"
        self.ws = make_workspace(Path(self.tmp.name), self.run_id)
        self.target = Path(self.tmp.name) / "fresh"
        manifest_data = manifest.empty("beispielkunde", "Beispielshop")
        for run_id, kind in ((self.run_id, "audit"), ("2026-08-01-report", "report")):
            manifest_data = manifest.add_run(manifest_data, shop="beispielshop",
                                             run_id=run_id, kind=kind, cadence=kind,
                                             period=None, run_date=run_id[:10],
                                             files={"audit.pdf": 4})
        manifest_data = manifest.release(manifest_data, "beispielshop", self.run_id,
                                         today=date(2026, 9, 9))
        self.remote = json.dumps(manifest_data).encode("utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def _publish(self, bucket, env=None, extra=()):
        if env is None:
            env = {"SUPABASE_URL": FakeBucket.URL,
                   "SUPABASE_SERVICE_ROLE_KEY": "service-key"}
        argv = ["--workspace", str(self.ws), "--run-id", self.run_id,
                "--target", str(self.target), "--upload", *extra]
        # `clear=True`, damit ein Schlüssel aus der Shell nie in einen Test gerät.
        with mock.patch.dict(os.environ, env, clear=True), \
                mock.patch("urllib.request.urlopen", bucket.urlopen), \
                contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(io.StringIO()):
            return publish.main(argv)

    def test_an_upload_into_an_empty_target_keeps_the_other_runs(self):
        bucket = FakeBucket({MANIFEST_KEY: self.remote})
        self.assertEqual(self._publish(bucket, extra=["--visible"]), 0)
        self.assertEqual({r["run_id"] for r in bucket.manifest()["runs"]},
                         {self.run_id, "2026-08-01-report"})

    def test_an_upload_into_an_empty_target_keeps_the_release(self):
        bucket = FakeBucket({MANIFEST_KEY: self.remote})
        self._publish(bucket, extra=["--visible"])
        entry = next(r for r in bucket.manifest()["runs"]
                     if r["run_id"] == self.run_id)
        self.assertTrue(entry["released"])
        self.assertEqual(entry["released_at"], "2026-09-09")

    def test_a_released_run_uploads_nothing_without_visible(self):
        bucket = FakeBucket({MANIFEST_KEY: self.remote})
        with self.assertRaises(SystemExit):
            self._publish(bucket)
        self.assertEqual(bucket.uploads(), [], "ohne --visible darf nichts hochgehen")

    def test_a_new_brand_starts_with_an_empty_manifest(self):
        bucket = FakeBucket()
        self.assertEqual(self._publish(bucket), 0)
        runs = bucket.manifest()["runs"]
        self.assertEqual([r["run_id"] for r in runs], [self.run_id])
        self.assertFalse(runs[0]["released"])

    def test_supabase_no_such_key_starts_with_an_empty_manifest(self):
        body = b'{"statusCode":"404","error":"not_found","message":"Object not found","code":"NoSuchKey"}'
        bucket = FakeBucket(get_status=400, get_body=body)
        self.assertEqual(self._publish(bucket), 0)
        self.assertEqual([r["run_id"] for r in bucket.manifest()["runs"]],
                         [self.run_id])

    def test_a_failed_download_stops_before_anything_goes_up(self):
        # Ein Manifest, das nicht gelesen werden konnte, ist kein leeres. Auch
        # im Ziel bleibt keines liegen, sonst lüde ein zweiter Anlauf es hoch.
        bucket = FakeBucket({MANIFEST_KEY: self.remote}, get_status=500)
        with self.assertRaises(SystemExit):
            self._publish(bucket)
        self.assertEqual(bucket.uploads(), [])
        self.assertFalse((self.target / MANIFEST_KEY).exists())

    def test_a_missing_key_prepares_nothing(self):
        # Ohne Schlüssel lässt sich das Manifest nicht holen. Ein trotzdem
        # vorbereitetes Ziel trüge eines, das auf einem leeren aufbaut, und der
        # nächste Anlauf mit Schlüssel lüde genau das hoch.
        bucket = FakeBucket({MANIFEST_KEY: self.remote})
        self.assertEqual(self._publish(bucket, env={}), 1)
        self.assertEqual(bucket.calls, [])
        self.assertFalse((self.target / MANIFEST_KEY).exists())

    def test_a_manifest_already_in_the_target_is_used_as_it_is(self):
        publish.prepare(self.ws, self.run_id, self.target)
        bucket = FakeBucket({MANIFEST_KEY: self.remote})
        self._publish(bucket)
        self.assertNotIn(("GET", MANIFEST_KEY), bucket.calls)


if __name__ == "__main__":
    unittest.main()


class TestDestinationFromCockpit(unittest.TestCase):
    """Ein Shop aus dem Cockpit liegt unter dessen Schlüsseln im Bucket."""

    def test_portal_block_sets_brand_and_shop(self):
        config = {"account_slug": "beispielkunde", "brand": "Beispielshop EU",
                  "portal": {"brand": "beispielmarke", "shop": "eu"}}
        self.assertEqual(publish.destination(config), ("beispielmarke", "eu"))

    def test_account_slug_replaces_only_the_brand(self):
        config = {"account_slug": "beispielkunde", "brand": "Beispielshop EU",
                  "portal": {"brand": "beispielmarke", "shop": "eu"}}
        self.assertEqual(publish.destination(config, "portal-test"), ("portal-test", "eu"))

    def test_without_portal_the_shop_comes_from_the_brand(self):
        config = {"account_slug": "beispielkunde", "brand": "Beispielshop"}
        self.assertEqual(publish.destination(config), ("beispielkunde", "beispielshop"))
