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
        # Vorbereitet wird auf dem Manifest im Ziel, nicht auf dem aus dem
        # Bucket. Seit dem 09.10.2026 (D12) holt publish das Manifest vor dem
        # Hochladen trotzdem noch einmal: passt es nicht zu dem, auf dem das
        # Ziel aufbaut, bricht es ab, statt die Läufe im Bucket zu ersetzen.
        publish.prepare(self.ws, self.run_id, self.target)
        bucket = FakeBucket({MANIFEST_KEY: self.remote})
        with self.assertRaises(SystemExit) as raised:
            self._publish(bucket)
        self.assertIn("geändert", str(raised.exception))
        self.assertEqual(bucket.calls, [("GET", MANIFEST_KEY)])
        self.assertEqual(bucket.uploads(), [])

    def test_the_uploaded_manifest_counts_up(self):
        bucket = FakeBucket({MANIFEST_KEY: self.remote})
        self._publish(bucket, extra=("--visible",))
        self.assertEqual(bucket.manifest()["revision"], 1)

    def test_a_manifest_changed_since_reading_stops_the_upload(self):
        # Zwei publish zweier Stores: zwischen Lesen und Hochladen schreibt
        # das andere. Ohne Prüfung verschwände dessen Lauf aus dem Verzeichnis.
        bucket = FakeBucket({MANIFEST_KEY: self.remote})
        other = json.loads(self.remote)
        other["revision"] = 7
        real_prepare = publish.prepare

        def prepare_while_another_publish_writes(*args, **kwargs):
            result = real_prepare(*args, **kwargs)
            bucket.objects[MANIFEST_KEY] = json.dumps(other).encode("utf-8")
            return result

        with mock.patch.object(publish, "prepare", prepare_while_another_publish_writes), \
                self.assertRaises(SystemExit) as raised:
            self._publish(bucket, extra=("--visible",))
        self.assertIn("Zähler 7", str(raised.exception))
        self.assertEqual(bucket.uploads(), [])


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


class TestBrandFiles(unittest.TestCase):
    """Spec 2026-10-08, Abschnitt 5.1, 11 und 13 (A1): Dateien der Marke."""

    RUN = "2026-09-01-audit"
    KEY = "brands/beispielmarke/manifest.json"

    def setUp(self):
        from tests import brand_support as bs
        self.bs = bs
        self.brand_ws = bs.make_brand(self)
        bs.write_json(self.brand_ws / "reporting" / "feedback.json",
                      {"version": 2, "entries": []})
        self.eu = self.brand_ws / "eu"
        run = self.eu / "reporting" / "runs" / self.RUN
        bs.write_json(run / "state.json", {"run_id": self.RUN, "cadence": "audit"})
        bs.write_json(run / "findings" / "conversion.json", {"findings": [
            {"id": "CRO-03"}, {"id": "CRO-05"}]})
        bs.write_json(run / "findings" / "content-brand.json", {"findings": [{"id": "CNT-04"}]})
        bs.write_json(run / "findings" / "data-quality.json", {"findings": [{"id": "MES-11"}]})
        bs.write_json(self.eu / "reporting" / "baseline" / "01" / "baseline.json", {})
        self.target = self.brand_ws.parent / "bucket"

    def _prepare(self, **kwargs):
        return publish.prepare(self.eu, self.RUN, self.target, **kwargs)

    def test_brand_files_sit_under_files_at_the_manifest_root(self):
        result = self._prepare()
        data = manifest.load(self.target / self.KEY)
        self.assertEqual(sorted(data["files"]), ["feedback.json", "measures.json"])
        self.assertTrue((self.target / "brands" / "beispielmarke" / "measures.json").exists())
        self.assertEqual(sorted(data["shops"]["eu"]["files"]), ["baseline/01/baseline.json"])
        self.assertFalse((self.target / manifest.path_for("beispielmarke", "eu")
                          / "measures.json").exists())
        self.assertEqual(result["brand_files"], 2)
        self.assertEqual(data["revision"], 1)

    def test_the_run_carries_a_copy_of_the_brand_list(self):
        self._prepare()
        copy = self.target / manifest.path_for("beispielmarke", "eu", self.RUN) / "measures.json"
        self.assertEqual(self.bs.read(copy), self.bs.fixture())
        data = manifest.load(self.target / self.KEY)
        self.assertIn("measures.json", data["runs"][0]["files"])

    def test_the_manifest_counts_each_publish(self):
        self._prepare()
        self._prepare()
        self.assertEqual(manifest.load(self.target / self.KEY)["revision"], 2)

    def test_portal_test_is_refused_with_brand_files(self):
        with self.assertRaises(SystemExit) as raised:
            self._prepare(account_slug="portal-test")
        self.assertIn("portal-test-beispielmarke", str(raised.exception))
        self.assertFalse(self.target.exists())

    def test_the_preview_goes_to_its_own_test_brand(self):
        result = self._prepare(account_slug="portal-test-beispielmarke")
        self.assertEqual(result["brand"], "portal-test-beispielmarke")
        self.assertTrue((self.target / "brands" / "portal-test-beispielmarke"
                         / "measures.json").exists())

    def test_shops_without_by_shop_stops_the_publish(self):
        doc = self.bs.fixture()
        doc["measures"][0]["shops"] = ["eu"]
        self.bs.write_json(self.brand_ws / "reporting" / "measures.json", doc)
        with self.assertRaises(SystemExit) as raised:
            self._prepare()
        self.assertIn("by_shop.uk", str(raised.exception))
        self.assertFalse(self.target.exists())

    def test_a_finding_missing_from_its_local_run_stops_the_publish(self):
        self.bs.write_json(self.eu / "reporting" / "runs" / self.RUN / "findings"
                           / "data-quality.json", {"findings": []})
        with self.assertRaises(SystemExit) as raised:
            self._prepare()
        self.assertIn("MES-11", str(raised.exception))

    def test_a_run_of_another_store_not_on_this_machine_is_no_error(self):
        # Die UK-Befunde liegen in uk/reporting/runs/2026-11-12-audit, das es
        # hier nicht gibt. Nicht prüfbar ist kein Fehler.
        self._prepare()

    def _main(self, *argv):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return publish.main(["--workspace", str(self.eu), "--target", str(self.target), *argv])

    def test_brand_only_uploads_brand_files_and_manifest(self):
        bucket = FakeBucket()
        env = {"SUPABASE_URL": FakeBucket.URL, "SUPABASE_SERVICE_ROLE_KEY": "k"}
        with mock.patch.dict(os.environ, env, clear=True), \
                mock.patch("urllib.request.urlopen", bucket.urlopen):
            code = self._main("--brand-only", "--upload")
        self.assertEqual(code, 0)
        self.assertEqual(sorted(bucket.uploads()), [
            "brands/beispielmarke/feedback.json", "brands/beispielmarke/manifest.json",
            "brands/beispielmarke/measures.json"])
        uploaded = json.loads(bucket.objects[self.KEY])
        self.assertEqual(uploaded["runs"], [])
        self.assertEqual(sorted(uploaded["files"]), ["feedback.json", "measures.json"])

    def test_brand_only_keeps_the_runs_in_the_bucket(self):
        remote = manifest.add_run(manifest.empty("beispielmarke", "Beispielmarke"),
                                  shop="eu", run_id=self.RUN, kind="audit",
                                  cadence="audit", period=None, run_date="2026-09-01",
                                  files={"audit.pdf": 4})
        remote["revision"] = 3
        bucket = FakeBucket({self.KEY: json.dumps(remote).encode("utf-8")})
        env = {"SUPABASE_URL": FakeBucket.URL, "SUPABASE_SERVICE_ROLE_KEY": "k"}
        with mock.patch.dict(os.environ, env, clear=True), \
                mock.patch("urllib.request.urlopen", bucket.urlopen):
            self._main("--brand-only", "--upload")
        uploaded = json.loads(bucket.objects[self.KEY])
        self.assertEqual([r["run_id"] for r in uploaded["runs"]], [self.RUN])
        self.assertEqual(uploaded["revision"], 4)

    def test_brand_only_needs_a_brand_folder(self):
        from tests import brand_support as bs
        bs.write_json(self.eu / "reporting" / "config.json", bs.store_config("eu", None))
        with self.assertRaises(SystemExit):
            publish.prepare_brand_only(self.eu, self.target)

    def test_brand_only_takes_no_run(self):
        with self.assertRaises(SystemExit):
            self._main("--brand-only", "--run-id", self.RUN)


class TestBrandPolicies(unittest.TestCase):
    """Vertrag V15: die Vorgaben der Marke mit ihren Bausteinen gehen als Dateien der Marke hoch."""

    RUN = "2026-09-01-audit"
    KEY = "brands/beispielmarke/manifest.json"
    POLICIES = {
        "version": "2026-01-13.1", "reference_shop": "eu", "decided_by": "Vorname Nachname",
        "decided_at": "2026-01-05",
        "rules": [{"key": "tag_manager", "subject": "Tag Manager", "rule": "same_as_reference",
                   "target": "Tag Manager als eigener Code",
                   "modules": [{"name": "Tag Manager", "path": "policy-modules/tag_manager/README.md",
                                "description": "Einbindung wie im Referenz-Store"},
                               {"name": "Tag Manager",
                                "path": "policy-modules/tag_manager/snippets/tag-manager.liquid",
                                "description": "Snippet mit Platzhalter"}]},
                  {"key": "languages", "subject": "Sprachen", "rule": "may_differ"}],
    }

    def setUp(self):
        from tests import brand_support as bs
        self.bs = bs
        self.brand_ws = bs.make_brand(self)
        self.eu = self.brand_ws / "eu"
        run = self.eu / "reporting" / "runs" / self.RUN
        bs.write_json(run / "state.json", {"run_id": self.RUN, "cadence": "audit"})
        bs.write_json(run / "findings" / "conversion.json", {"findings": [
            {"id": "CRO-03"}, {"id": "CRO-05"}]})
        bs.write_json(run / "findings" / "content-brand.json", {"findings": [{"id": "CNT-04"}]})
        bs.write_json(run / "findings" / "data-quality.json", {"findings": [{"id": "MES-11"}]})
        self.target = self.brand_ws.parent / "bucket"

    def write_policies(self, folder: Path, data: dict | None = None) -> Path:
        self.bs.write_json(folder / "policies.json", data or self.POLICIES)
        modules = folder / "policy-modules" / "tag_manager"
        (modules / "snippets").mkdir(parents=True, exist_ok=True)
        (modules / "README.md").write_text("# Tag Manager\n", encoding="utf-8")
        (modules / "snippets" / "tag-manager.liquid").write_text("{% comment %} GTM {% endcomment %}\n",
                                                                 encoding="utf-8")
        return folder

    def brand_files(self) -> list:
        return sorted(manifest.load(self.target / self.KEY)["files"])

    EXPECTED = ["measures.json", "policies.json", "policy-modules/tag_manager/README.md",
                "policy-modules/tag_manager/snippets/tag-manager.liquid"]

    def test_brand_only_laedt_vorgaben_und_bausteine_hoch(self):
        self.write_policies(self.brand_ws)
        result = publish.prepare_brand_only(self.eu, self.target)
        self.assertEqual(self.brand_files(), self.EXPECTED)
        self.assertEqual(result["brand_files"], 4)
        root = self.target / "brands" / "beispielmarke"
        self.assertEqual(self.bs.read(root / "policies.json"), self.POLICIES)
        self.assertEqual((root / "policy-modules/tag_manager/README.md").read_text(encoding="utf-8"),
                         "# Tag Manager\n")

    def test_vorgaben_in_einem_ordner_direkt_in_der_marke(self):
        self.write_policies(self.brand_ws / "shared")
        publish.prepare_brand_only(self.eu, self.target)
        self.assertEqual(self.brand_files(), self.EXPECTED)
        self.assertTrue((self.target / "brands/beispielmarke/policy-modules/tag_manager/README.md").is_file())

    def test_ein_lauf_behaelt_die_vorgaben_im_manifest(self):
        self.write_policies(self.brand_ws)
        publish.prepare_brand_only(self.eu, self.target)
        publish.prepare(self.eu, self.RUN, self.target)
        self.assertEqual(self.brand_files(), self.EXPECTED)

    def test_versteckte_dateien_bleiben_liegen(self):
        folder = self.write_policies(self.brand_ws)
        (folder / "policy-modules" / ".DS_Store").write_bytes(b"x")
        publish.prepare_brand_only(self.eu, self.target)
        self.assertNotIn("policy-modules/.DS_Store", self.brand_files())

    def test_ohne_vorgaben_bleibt_alles_wie_bisher(self):
        publish.prepare_brand_only(self.eu, self.target)
        self.assertEqual(self.brand_files(), ["measures.json"])

    def test_ein_fehlender_baustein_haelt_an(self):
        folder = self.write_policies(self.brand_ws)
        (folder / "policy-modules/tag_manager/README.md").unlink()
        with self.assertRaises(SystemExit) as raised:
            publish.prepare_brand_only(self.eu, self.target)
        self.assertIn("policy-modules/tag_manager/README.md", str(raised.exception))
        self.assertFalse((self.target / "brands").exists())

    def test_ungueltige_vorgaben_halten_an(self):
        broken = {**self.POLICIES, "rules": [{"key": "tag_manager", "rule": "vielleicht"}]}
        self.write_policies(self.brand_ws, broken)
        with self.assertRaises(SystemExit) as raised:
            publish.prepare_brand_only(self.eu, self.target)
        self.assertIn("Vorgaben der Marke", str(raised.exception))
        self.assertFalse((self.target / "brands").exists())

    def test_zwei_ordner_mit_vorgaben_halten_an(self):
        self.write_policies(self.brand_ws / "shared")
        self.write_policies(self.brand_ws / "uk")
        with self.assertRaises(SystemExit) as raised:
            publish.prepare_brand_only(self.eu, self.target)
        self.assertIn("mehrfach", str(raised.exception))

    def test_upload_legt_die_bausteine_unter_die_marke(self):
        self.write_policies(self.brand_ws)
        bucket = FakeBucket()
        env = {"SUPABASE_URL": FakeBucket.URL, "SUPABASE_SERVICE_ROLE_KEY": "k"}
        with mock.patch.dict(os.environ, env, clear=True), \
                mock.patch("urllib.request.urlopen", bucket.urlopen), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            code = publish.main(["--workspace", str(self.eu), "--target", str(self.target),
                                 "--brand-only", "--upload"])
        self.assertEqual(code, 0)
        self.assertEqual(sorted(bucket.uploads()), [
            "brands/beispielmarke/manifest.json", "brands/beispielmarke/measures.json",
            "brands/beispielmarke/policies.json", "brands/beispielmarke/policy-modules/tag_manager/README.md",
            "brands/beispielmarke/policy-modules/tag_manager/snippets/tag-manager.liquid"])
        self.assertEqual(sorted(json.loads(bucket.objects[self.KEY])["files"]), self.EXPECTED)
