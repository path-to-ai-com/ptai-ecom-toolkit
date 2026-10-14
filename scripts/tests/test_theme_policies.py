"""Tests für die Vorgaben aus dem Cockpit: `theme.policies import` (seit 0.3.15) und `sync` (seit 0.3.16)."""
import contextlib
import io
import json
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest import mock

from theme import policies

NOW = datetime(2026, 1, 13, 12, 0, tzinfo=timezone.utc)
OPTIONS = ["Abweichung erlauben", "An Beispielshop angleichen"]


def write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def source(**changes) -> dict:
    """Erfundene Vorgaben einer Marke wie im Beispiel von `policies-format.md`."""
    data = {
        "version": "2026-01-05.1", "reference_shop": "beispielshop", "decided_by": "Vorname Nachname",
        "decided_at": "2026-01-05",
        "rules": [
            {"key": "cookie_banner", "subject": "Cookie-Banner", "rule": "same_as_reference", "target": "Banner A",
             "keep": [["banner-a", "app:banner-a"]], "drop": ["app:banner-b"]},
            {"key": "translation", "subject": "Übersetzung", "rule": "open", "note": "erst im Referenz-Store klären"},
            {"key": "languages", "subject": "Sprachen", "rule": "may_differ"},
        ],
    }
    data.update(changes)
    return data


def answer(key="bundles", value="Abweichung erlauben", by="Erika Muster", at="2026-01-13T09:12:00+00:00",
           **extra) -> dict:
    entry = {"key": key, "value": value, "by": by, "at": at, "options": OPTIONS}
    entry.update(extra)
    return entry


class BrandFolder(unittest.TestCase):
    """Ein Ordner der Marke mit `shared/policies.json` und den Stores daneben."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.folder = self.root / "shared"
        write(self.folder / "policies.json", source())

    def run_import(self, *entries, workspace=None, now=NOW) -> dict:
        return policies.import_answers(self.folder, list(entries), workspace=workspace, now=now)

    def rules(self) -> dict:
        return {r["key"]: r for r in read(self.folder / "policies.json")["rules"]}


class ImportRules(BrandFolder):
    def test_erste_option_legt_eine_regel_may_differ_an(self):
        result = self.run_import(answer(subject="Beispielbundle"))
        rule = self.rules()["bundles"]
        self.assertEqual(rule["rule"], "may_differ")
        self.assertEqual(rule["subject"], "Beispielbundle")
        self.assertEqual((rule["decided_by"], rule["decided_at"]), ("Erika Muster", "2026-01-13T09:12:00+00:00"))
        self.assertNotIn("target", rule)
        self.assertEqual([i["key"] for i in result["imported"]], ["bundles"])
        self.assertIsNone(result["imported"][0]["previous"])

    def test_zweite_option_heisst_wie_im_referenz_store(self):
        self.run_import(answer(value="An Beispielshop angleichen"))
        rule = self.rules()["bundles"]
        self.assertEqual(rule["rule"], "same_as_reference")
        self.assertEqual(rule["target"], "wie im Referenz-Store")
        self.assertEqual(rule["subject"], "bundles")

    def test_eine_offene_regel_wird_entschieden_und_behaelt_ihre_notiz(self):
        result = self.run_import(answer(key="translation", value="An Beispielshop angleichen"))
        rule = self.rules()["translation"]
        self.assertEqual(rule["rule"], "same_as_reference")
        self.assertEqual(rule["note"], "erst im Referenz-Store klären")
        self.assertEqual(result["imported"][0]["previous"], "open")
        self.assertEqual(result["still_open"], [])

    def test_die_datei_bekommt_eine_neue_version_und_bleibt_gueltig(self):
        result = self.run_import(answer())
        data = read(self.folder / "policies.json")
        self.assertEqual((result["previous_version"], result["version"]), ("2026-01-05.1", "2026-01-13.1"))
        self.assertEqual(data["version"], "2026-01-13.1")
        self.assertEqual(policies.validate(data), [])
        # Wer die übrigen Vorgaben entschieden hat, bleibt an der Datei.
        self.assertEqual((data["decided_by"], data["decided_at"]), ("Vorname Nachname", "2026-01-05"))

    def test_mehrere_antworten_ergeben_eine_neue_version(self):
        result = self.run_import(answer(), answer(key="translation", value="Abweichung erlauben"))
        self.assertEqual(len(result["imported"]), 2)
        self.assertEqual(result["version"], "2026-01-13.1")

    def test_ohne_options_gelten_die_knoepfe_des_cockpits(self):
        plain = [answer(key="bundles"), answer(key="wishlist", value="An Beispielshop angleichen")]
        for entry in plain:
            del entry["options"]
        self.run_import(*plain)
        rules = self.rules()
        self.assertEqual((rules["bundles"]["rule"], rules["wishlist"]["rule"]), ("may_differ", "same_as_reference"))

    def test_eine_antwort_ausserhalb_der_options_wird_uebersprungen(self):
        result = self.run_import(answer(value="Vielleicht später"))
        self.assertEqual(result["imported"], [])
        self.assertIn("keine der Antworten", result["skipped"][0]["reason"])
        self.assertNotIn("bundles", self.rules())
        self.assertEqual(read(self.folder / "policies.json")["version"], "2026-01-05.1")

    def test_ohne_options_und_mit_fremdem_text_wird_uebersprungen(self):
        entry = answer(value="Lieber nicht")
        del entry["options"]
        self.assertIn("options aus get_setup", self.run_import(entry)["skipped"][0]["reason"])

    def test_options_muessen_zwei_verschiedene_sein(self):
        result = self.run_import(answer(options=["Abweichung erlauben", "Abweichung erlauben"]))
        self.assertIn("genau zwei verschiedene", result["skipped"][0]["reason"])

    def test_ohne_namen_wird_nichts_uebernommen(self):
        result = self.run_import(answer(by=" "))
        self.assertEqual(result["imported"], [])
        self.assertIn("ohne Namen", result["skipped"][0]["reason"])

    def test_jede_person_aus_dem_cockpit_wird_uebernommen(self):
        # Das Plugin kennt die Mitglieder der Marke nicht; antworten können im Cockpit nur Mitglieder.
        self.run_import(answer(by="Max Beispiel"))
        self.assertEqual(self.rules()["bundles"]["decided_by"], "Max Beispiel")

    def test_dieselbe_antwort_aendert_nichts(self):
        self.run_import(answer())
        before = (self.folder / "policies.json").read_text(encoding="utf-8")
        result = self.run_import(answer(at="2026-01-14T08:00:00+00:00"),
                                 now=datetime(2026, 1, 14, tzinfo=timezone.utc))
        self.assertEqual(result["imported"], [])
        self.assertEqual([u["key"] for u in result["unchanged"]], ["bundles"])
        self.assertEqual(result["skipped"], [])
        self.assertEqual((self.folder / "policies.json").read_text(encoding="utf-8"), before)

    def test_eine_neuere_antwort_im_cockpit_aendert_die_regel(self):
        self.run_import(answer())
        result = self.run_import(answer(value="An Beispielshop angleichen", by="Max Beispiel",
                                        at="2026-01-13T11:00:00+00:00"))
        rule = self.rules()["bundles"]
        self.assertEqual((rule["rule"], rule["decided_by"]), ("same_as_reference", "Max Beispiel"))
        self.assertEqual(result["imported"][0]["previous"], "may_differ")
        self.assertEqual(result["version"], "2026-01-13.2")

    def test_eine_aeltere_antwort_aendert_eine_spaeter_entschiedene_regel_nicht(self):
        self.run_import(answer(at="2026-01-13T11:00:00+00:00"))
        result = self.run_import(answer(value="An Beispielshop angleichen", at="2026-01-13T09:00:00+00:00"))
        self.assertEqual(self.rules()["bundles"]["rule"], "may_differ")
        self.assertIn("später entschieden", result["skipped"][0]["reason"])

    def test_eine_regel_der_datei_gilt_am_tag_ihrer_entscheidung(self):
        same_day = self.run_import(answer(key="languages", value="An Beispielshop angleichen",
                                          at="2026-01-05T16:00:00+00:00"))
        self.assertEqual(self.rules()["languages"]["rule"], "may_differ")
        self.assertTrue(same_day["skipped"])
        self.run_import(answer(key="languages", value="An Beispielshop angleichen"))
        self.assertEqual(self.rules()["languages"]["rule"], "same_as_reference")

    def test_abweichung_raeumt_ziel_keep_und_drop_weg(self):
        result = self.run_import(answer(key="cookie_banner"))
        rule = self.rules()["cookie_banner"]
        self.assertEqual(rule["rule"], "may_differ")
        for field in ("target", "keep", "drop"):
            self.assertNotIn(field, rule)
        self.assertEqual(result["imported"][0]["previous"], "same_as_reference")
        self.assertEqual(policies.validate(read(self.folder / "policies.json")), [])

    def test_angleichen_mit_app_behaelt_die_app_unter_beiden_schreibweisen(self):
        result = self.run_import(answer(value="An Beispielshop angleichen", app="app:beispielbundle"))
        rule = self.rules()["bundles"]
        self.assertEqual(rule["keep"], [["app:beispielbundle", "beispielbundle"]])
        self.assertEqual(result["imported"][0]["app"], "app:beispielbundle")
        self.assertEqual(policies.validate(read(self.folder / "policies.json")), [])

    def test_abweichung_mit_app_behaelt_nichts(self):
        self.run_import(answer(app="app:beispielbundle"))
        self.assertNotIn("keep", self.rules()["bundles"])

    def test_eine_schon_behaltene_app_steht_nicht_doppelt(self):
        data = source()
        data["rules"][1]["note"] = "offen"
        write(self.folder / "policies.json", data)
        self.run_import(answer(key="translation", value="An Beispielshop angleichen", app="app:beispielbundle"))
        self.run_import(answer(key="translation", value="Abweichung erlauben", at="2026-01-13T10:00:00+00:00"))
        self.run_import(answer(key="translation", value="An Beispielshop angleichen", app="app:beispielbundle",
                               at="2026-01-13T11:00:00+00:00"))
        self.assertEqual(self.rules()["translation"]["keep"], [["app:beispielbundle", "beispielbundle"]])

    def test_eine_app_ohne_app_doppelpunkt_wird_uebersprungen(self):
        result = self.run_import(answer(value="An Beispielshop angleichen", app="beispielbundle"))
        self.assertIn("app:<handle>", result["skipped"][0]["reason"])
        self.assertNotIn("bundles", self.rules())

    def test_ein_unlesbarer_zeitpunkt_wird_jetzt(self):
        self.run_import(answer(at="gestern"))
        self.assertEqual(self.rules()["bundles"]["decided_at"], "2026-01-13T12:00:00+00:00")

    def test_offene_vorgaben_stehen_in_der_ausgabe(self):
        result = self.run_import()
        self.assertEqual(result["still_open"], [{"key": "translation", "subject": "Übersetzung"}])

    def test_fehlende_datei_ist_ein_fehler(self):
        with self.assertRaises(policies.PolicyError):
            policies.import_answers(self.root / "anderswo", [answer()], now=NOW)

    def test_keine_liste_ist_ein_fehler(self):
        with self.assertRaises(policies.PolicyError):
            policies.import_answers(self.folder, {"key": "bundles"}, now=NOW)


class NextVersion(unittest.TestCase):
    def test_neuer_tag_beginnt_bei_eins(self):
        self.assertEqual(policies.next_version("2026-01-05.3", date(2026, 1, 13)), "2026-01-13.1")

    def test_derselbe_tag_zaehlt_weiter(self):
        self.assertEqual(policies.next_version("2026-01-13.1", date(2026, 1, 13)), "2026-01-13.2")

    def test_nie_kleiner_als_die_bestehende(self):
        self.assertEqual(policies.next_version("2026-01-14.2", date(2026, 1, 13)), "2026-01-14.3")

    def test_eine_version_nach_anderem_schema_wird_heute_eins(self):
        self.assertEqual(policies.next_version("v7", date(2026, 1, 13)), "2026-01-13.1")


class ApplyNeeded(BrandFolder):
    def store(self, name: str, version: str | None, reference="beispielshop", shop=None) -> Path:
        workspace = self.root / name
        (workspace / "migration").mkdir(parents=True, exist_ok=True)
        if version is not None:
            write(policies.copy_path(workspace), {**source(version=version, reference_shop=reference),
                                                  "applied_at": "2026-01-06T10:00:00+00:00"})
        if shop:
            write(workspace / "reporting" / "config.json", {"portal": {"brand": "beispielmarke", "shop": shop}})
        return workspace

    def test_stores_mit_alter_kopie_brauchen_apply(self):
        self.store("store-a", "2026-01-05.1", shop="nordshop")
        self.store("store-b", "2026-01-13.1")
        self.store("fremd", "2026-01-01.1", reference="andererstore")
        result = self.run_import(answer())
        self.assertEqual([(s["shop"], s["applied_version"]) for s in result["apply_needed"]],
                         [("nordshop", "2026-01-05.1")])

    def test_ohne_neue_version_zaehlt_die_bestehende(self):
        self.store("store-a", "2026-01-05.1")
        self.store("store-b", "2026-01-04.1")
        result = self.run_import()
        self.assertEqual(sorted(s["shop"] for s in result["apply_needed"]), ["store-b"])

    def test_der_eigene_store_ohne_kopie_braucht_apply(self):
        own = self.store("eigener", None, shop="eigenershop")
        result = self.run_import(answer(), workspace=own)
        self.assertEqual(result["apply_needed"], [{"shop": "eigenershop", "workspace": str(own.resolve()),
                                                   "applied_version": None, "own": True}])

    def test_ein_ordner_ohne_migration_ist_kein_store(self):
        result = self.run_import(answer(), workspace=self.folder)
        self.assertEqual(result["apply_needed"], [])

    def test_nach_apply_braucht_der_store_nichts_mehr(self):
        own = self.store("eigener", "2026-01-05.1")
        result = self.run_import(answer(), workspace=own)
        self.assertEqual([s["own"] for s in result["apply_needed"]], [True])
        policies.apply(own, policies.load_source(self.folder / "policies.json"), now=NOW)
        self.assertEqual(self.run_import(workspace=own)["apply_needed"], [])


class ApplyAfterImport(BrandFolder):
    def setUp(self):
        super().setUp()
        self.ws = self.root / "store"
        write(self.ws / "migration" / "inventory" / "apps.json", {"services": [{"service_id": "app:banner-b"}]})

    def test_eine_im_cockpit_entschiedene_regel_traegt_ihre_person_in_den_lauf(self):
        data = source(rules=[{"key": "cookie_banner", "rule": "same_as_reference", "drop": ["app:banner-b"],
                              "decided_by": "Erika Muster", "decided_at": "2026-01-13T09:12:00+00:00"}])
        policies.apply(self.ws, data, now=NOW)
        decision = read(policies.decisions_path(self.ws))["decisions"][0]
        self.assertEqual((decision["decided_by"], decision["decided_at"]),
                         ("Erika Muster", "2026-01-13T09:12:00+00:00"))

    def test_eine_angeglichene_app_fehlt_im_store_und_wird_ein_punkt_zum_einbauen(self):
        from theme import open_items
        open_items.init(self.ws)
        imported = self.run_import(answer(value="An Beispielshop angleichen", app="app:beispielbundle"))
        result = policies.apply(self.ws, policies.load_source(self.folder / "policies.json"), now=NOW)
        self.assertEqual(imported["version"], result["version"])
        added = [i for i in result["open_items_added"] if "beispielbundle" in i]
        self.assertEqual(added, ["POLICY-bundles-beispielbundle"])
        item = open_items.load(self.ws).get(added[0])
        self.assertEqual(item["severity"], "blocker")
        self.assertIn("app:beispielbundle", item["description"])

    def test_ein_store_mit_der_app_unter_ihrem_handle_braucht_keinen_punkt(self):
        write(self.ws / "migration" / "inventory" / "apps.json", {"services": [{"service_id": "beispielbundle"}]})
        self.run_import(answer(value="An Beispielshop angleichen", app="app:beispielbundle"))
        result = policies.apply(self.ws, policies.load_source(self.folder / "policies.json"), now=NOW)
        self.assertEqual([i for i in result["open_items_added"] if "beispielbundle" in i], [])
        apps = read(self.ws / "migration" / "inventory" / "apps.json")["services"]
        self.assertEqual(apps[0]["decision"], "keep")

    def test_ohne_person_an_der_regel_gilt_die_der_datei(self):
        policies.apply(self.ws, source(), now=NOW)
        decision = next(d for d in read(policies.decisions_path(self.ws))["decisions"]
                        if d["service_id"] == "app:banner-b")
        self.assertEqual(decision["decided_by"], "Vorname Nachname")

    def test_dieselbe_version_zweimal_laesst_applied_at_stehen(self):
        first = policies.apply(self.ws, source(), now=NOW)
        again = policies.apply(self.ws, source(), now=datetime(2026, 1, 20, tzinfo=timezone.utc))
        self.assertFalse(first["unchanged"])
        self.assertTrue(again["unchanged"])
        self.assertEqual(again["applied_at"], first["applied_at"])
        self.assertEqual(read(policies.copy_path(self.ws))["applied_at"], "2026-01-13T12:00:00+00:00")

    def test_eine_neue_version_setzt_applied_at_neu(self):
        policies.apply(self.ws, source(), now=NOW)
        later = datetime(2026, 1, 20, tzinfo=timezone.utc)
        result = policies.apply(self.ws, source(version="2026-01-20.1"), now=later)
        self.assertFalse(result["unchanged"])
        self.assertEqual(result["applied_at"], later.isoformat(timespec="seconds"))

    def test_eine_leere_person_an_der_regel_ist_ungueltig(self):
        broken = source(rules=[{"key": "x", "rule": "may_differ", "decided_by": " "}])
        self.assertTrue(any("decided_by" in e for e in policies.validate(broken)))


class Cli(BrandFolder):
    def run_cli(self, *args, stdin: str | None = None) -> tuple[int, dict]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out), mock.patch("sys.stdin", io.StringIO(stdin or "")):
            code = policies.main(list(args))
        return code, json.loads(out.getvalue().strip().splitlines()[-1])

    def test_import_von_stdin_mit_exit_null(self):
        code, result = self.run_cli("import", "--brand-workspace", str(self.folder), "--file", "-",
                                    "--workspace", str(self.root), stdin=json.dumps([answer()]))
        self.assertEqual(code, 0, result)
        self.assertEqual(result["imported"][0]["rule"], "may_differ")

    def test_import_aus_datei_mit_uebersprungener_antwort_hat_exit_eins(self):
        path = self.root / "answers.json"
        write(path, [answer(value="Vielleicht")])
        code, result = self.run_cli("import", "--brand-workspace", str(self.folder), "--file", str(path),
                                    "--workspace", str(self.root))
        self.assertEqual(code, 1)
        self.assertEqual(len(result["skipped"]), 1)

    def test_import_ohne_ordner_der_marke_hat_exit_zwei(self):
        code, result = self.run_cli("import", "--file", "-", stdin="[]")
        self.assertEqual(code, 2)
        self.assertIn("--brand-workspace", result["error"])

    def test_import_ohne_json_hat_exit_zwei(self):
        code, result = self.run_cli("import", "--brand-workspace", str(self.folder), "--file", "-",
                                    stdin="kein json")
        self.assertEqual(code, 2)
        self.assertIn("kein JSON", result["error"])



def cockpit(**changes) -> dict:
    """Erfundene Ausgabe von `get_policies`: Fassung der Marke mit Bausteinen samt Inhalt."""
    data = source(brand="beispielmarke", version="2026-01-13.1")
    data["rules"][0]["modules"] = [
        {"name": "Banner A", "path": "policy-modules/cookie_banner/README.md",
         "description": "Einbindung des Banners wie im Referenz-Store",
         "content": "# Banner A\n\nEinbauen als Snippet.\n"},
        {"name": "Banner A", "path": "policy-modules/cookie_banner/snippets/banner.liquid",
         "description": "Snippet", "content": "{% comment %} Banner A {% endcomment %}\n"},
    ]
    data.update(changes)
    return data


class Sync(unittest.TestCase):
    """`sync`: die Fassung aus `get_policies` ins Repo des Stores, danach `apply` wie bisher."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.ws = Path(tmp.name) / "store"
        write(self.ws / "reporting" / "config.json", {"portal": {"brand": "beispielmarke", "shop": "nordshop"}})
        write(self.ws / "migration" / "inventory" / "apps.json", {"services": [{"service_id": "app:banner-b"}]})

    def module(self, rel: str) -> Path:
        return self.ws / "migration" / rel

    def apply_copy(self, now=NOW) -> dict:
        return policies.apply(self.ws, policies.load_source(policies.copy_path(self.ws)), now=now)

    def test_schreibt_die_fassung_ohne_inhalt_und_die_bausteine_daneben(self):
        result = policies.sync(self.ws, cockpit())
        copy = read(policies.copy_path(self.ws))
        self.assertEqual(copy["version"], "2026-01-13.1")
        self.assertEqual(policies.validate(copy), [])
        modules = copy["rules"][0]["modules"]
        self.assertEqual([m["path"] for m in modules], ["policy-modules/cookie_banner/README.md",
                                                        "policy-modules/cookie_banner/snippets/banner.liquid"])
        self.assertFalse(any("content" in m for m in modules))
        self.assertNotIn("applied_at", copy)
        self.assertEqual(self.module("policy-modules/cookie_banner/README.md").read_text(encoding="utf-8"),
                         "# Banner A\n\nEinbauen als Snippet.\n")
        self.assertTrue(self.module("policy-modules/cookie_banner/snippets/banner.liquid").is_file())
        self.assertEqual((result["previous_version"], result["version"]), (None, "2026-01-13.1"))
        self.assertTrue(result["available"] and result["changed"] and result["apply_needed"])
        self.assertEqual([(c["key"], c["change"]) for c in result["rules_changed"]],
                         [("cookie_banner", "added"), ("translation", "added"), ("languages", "added")])
        self.assertEqual([m["path"] for m in result["modules_written"]],
                         ["migration/policy-modules/cookie_banner/README.md",
                          "migration/policy-modules/cookie_banner/snippets/banner.liquid"])
        self.assertEqual(result["still_open"], [{"key": "translation", "subject": "Übersetzung"}])

    def test_apply_danach_traegt_die_vorgaben_ein(self):
        policies.sync(self.ws, cockpit())
        result = self.apply_copy()
        self.assertFalse(result["unchanged"])
        decisions = {d["service_id"]: d for d in read(policies.decisions_path(self.ws))["decisions"]}
        self.assertEqual((decisions["app:banner-b"]["decision"], decisions["app:banner-b"]["source"]),
                         ("drop", "policy"))
        self.assertIn("POLICY-cookie_banner-banner-a", result["open_items_added"])
        copy = read(policies.copy_path(self.ws))
        self.assertEqual(copy["applied_at"], "2026-01-13T12:00:00+00:00")
        self.assertEqual(len(copy["rules"][0]["modules"]), 2)

    def test_dieselbe_fassung_zweimal_aendert_nichts_und_laesst_applied_at_stehen(self):
        policies.sync(self.ws, cockpit())
        self.apply_copy()
        before = policies.copy_path(self.ws).read_text(encoding="utf-8")
        result = policies.sync(self.ws, cockpit())
        self.assertFalse(result["changed"])
        self.assertFalse(result["apply_needed"])
        self.assertEqual((result["rules_changed"], result["modules_written"], result["modules_removed"]), ([], [], []))
        self.assertEqual(policies.copy_path(self.ws).read_text(encoding="utf-8"), before)
        again = self.apply_copy(now=datetime(2026, 1, 20, tzinfo=timezone.utc))
        self.assertTrue(again["unchanged"])
        self.assertEqual(again["applied_at"], "2026-01-13T12:00:00+00:00")

    def test_eine_neue_version_verlangt_apply(self):
        policies.sync(self.ws, cockpit())
        self.apply_copy()
        data = cockpit(version="2026-01-14.1")
        data["rules"][1].update({"rule": "may_differ", "decided_by": "Erika Muster",
                                 "decided_at": "2026-01-14T08:00:00+00:00"})
        result = policies.sync(self.ws, data)
        self.assertEqual((result["previous_version"], result["version"]), ("2026-01-13.1", "2026-01-14.1"))
        self.assertTrue(result["apply_needed"])
        self.assertEqual(result["rules_changed"], [{"key": "translation", "subject": "Übersetzung",
                                                    "change": "changed", "previous": "open", "rule": "may_differ",
                                                    "fields": ["rule"]}])
        self.assertNotIn("applied_at", read(policies.copy_path(self.ws)))
        later = datetime(2026, 1, 14, 9, 0, tzinfo=timezone.utc)
        self.assertEqual(self.apply_copy(now=later)["applied_at"], later.isoformat(timespec="seconds"))

    def test_nur_eine_neue_person_ist_keine_geaenderte_regel(self):
        policies.sync(self.ws, cockpit())
        self.apply_copy()
        data = cockpit()
        data["rules"][2].update({"decided_by": "Max Beispiel", "decided_at": "2026-01-13T10:00:00+00:00"})
        result = policies.sync(self.ws, data)
        self.assertEqual(result["rules_changed"], [])
        self.assertTrue(result["changed"])
        self.assertFalse(result["apply_needed"])

    def test_eine_entfallene_regel_steht_in_der_ausgabe(self):
        policies.sync(self.ws, cockpit())
        data = cockpit()
        del data["rules"][2]
        result = policies.sync(self.ws, data)
        self.assertEqual([(c["key"], c["change"], c["previous"]) for c in result["rules_changed"]],
                         [("languages", "removed", "may_differ")])

    def test_ein_geaenderter_baustein_bei_gleicher_version_verlangt_apply(self):
        policies.sync(self.ws, cockpit())
        self.apply_copy()
        data = cockpit()
        data["rules"][0]["modules"][1]["content"] = "{% comment %} Banner A, neu {% endcomment %}\n"
        result = policies.sync(self.ws, data)
        self.assertEqual([m["path"] for m in result["modules_written"]],
                         ["migration/policy-modules/cookie_banner/snippets/banner.liquid"])
        self.assertEqual(result["rules_changed"], [])
        self.assertTrue(result["apply_needed"])
        self.assertNotIn("applied_at", read(policies.copy_path(self.ws)))

    def test_ein_gestrichener_baustein_wird_geloescht(self):
        policies.sync(self.ws, cockpit())
        data = cockpit()
        data["rules"][0]["modules"] = data["rules"][0]["modules"][:1]
        result = policies.sync(self.ws, data)
        self.assertEqual(result["modules_removed"], ["migration/policy-modules/cookie_banner/snippets/banner.liquid"])
        self.assertFalse(self.module("policy-modules/cookie_banner/snippets").exists())
        self.assertTrue(self.module("policy-modules/cookie_banner/README.md").is_file())
        self.assertEqual(result["rules_changed"][0]["fields"], ["modules"])

    def test_ohne_bausteine_verschwindet_der_ordner(self):
        policies.sync(self.ws, cockpit())
        data = cockpit()
        del data["rules"][0]["modules"]
        policies.sync(self.ws, data)
        self.assertFalse(policies.modules_path(self.ws).exists())

    def test_ein_pfad_ausserhalb_der_regel_wird_abgelehnt(self):
        for path in ("policy-modules/cookie_banner/../../reporting/config.json", "policy-modules/languages/x.md",
                     "/tmp/x.md", "policy-modules/cookie_banner/", "policy-modules\\cookie_banner\\x.md"):
            data = cockpit()
            data["rules"][0]["modules"][0]["path"] = path
            with self.assertRaises(policies.PolicyError, msg=path):
                policies.sync(self.ws, data)
        self.assertFalse(policies.copy_path(self.ws).exists())
        self.assertFalse(policies.modules_path(self.ws).exists())

    def test_ein_baustein_ohne_inhalt_steht_unter_modules_missing(self):
        policies.sync(self.ws, cockpit())
        data = cockpit()
        data["rules"][0]["modules"][0]["content"] = None
        result = policies.sync(self.ws, data)
        self.assertEqual(result["modules_missing"], [{"key": "cookie_banner", "name": "Banner A",
                                                      "path": "migration/policy-modules/cookie_banner/README.md"}])
        self.assertEqual(result["modules_removed"], ["migration/policy-modules/cookie_banner/README.md"])
        self.assertTrue(result["apply_needed"])
        # Der Verweis bleibt in der Fassung, die übrigen Bausteine und Regeln sind geschrieben.
        self.assertEqual(len(read(policies.copy_path(self.ws))["rules"][0]["modules"]), 2)
        self.assertTrue(self.module("policy-modules/cookie_banner/snippets/banner.liquid").is_file())

    def test_cli_mit_fehlendem_baustein_hat_exit_eins(self):
        data = cockpit()
        data["rules"][0]["modules"][1]["content"] = None
        out = io.StringIO()
        with contextlib.redirect_stdout(out), mock.patch("sys.stdin", io.StringIO(json.dumps(data))):
            code = policies.main(["sync", "--file", "-", "--workspace", str(self.ws)])
        self.assertEqual(code, 1)
        self.assertEqual(len(json.loads(out.getvalue())["modules_missing"]), 1)

    def test_eine_fremde_marke_wird_abgelehnt(self):
        with self.assertRaises(policies.PolicyError) as raised:
            policies.sync(self.ws, cockpit(brand="anderemarke"))
        self.assertIn("anderemarke", str(raised.exception))
        self.assertFalse(policies.copy_path(self.ws).exists())

    def test_eine_ungueltige_fassung_schreibt_nichts(self):
        data = cockpit()
        data["rules"][0]["rule"] = "vielleicht"
        with self.assertRaises(policies.PolicyError):
            policies.sync(self.ws, data)
        self.assertFalse(policies.copy_path(self.ws).exists())
        self.assertFalse(policies.modules_path(self.ws).exists())

    def test_eine_marke_ohne_vorgaben_schreibt_nichts(self):
        result = policies.sync(self.ws, {"brand": "beispielmarke", "rules": []})
        self.assertFalse(result["available"])
        self.assertFalse(policies.copy_path(self.ws).exists())

    def test_eine_kopie_aus_dem_ordner_der_marke_mit_gleicher_fassung_bleibt_angewendet(self):
        # Vor 0.3.16 hat der Betreiber dieselbe Fassung mit apply --source <ordner der marke> eingetragen.
        policies.apply(self.ws, source(version="2026-01-13.1"), now=NOW)
        result = policies.sync(self.ws, source(brand="beispielmarke", version="2026-01-13.1"))
        self.assertFalse(result["apply_needed"])
        self.assertEqual(read(policies.copy_path(self.ws))["applied_at"], "2026-01-13T12:00:00+00:00")

    def test_cli_von_stdin_mit_exit_null(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), mock.patch("sys.stdin", io.StringIO(json.dumps(cockpit()))):
            code = policies.main(["sync", "--file", "-", "--workspace", str(self.ws)])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out.getvalue())["version"], "2026-01-13.1")

    def test_cli_mit_ungueltiger_fassung_hat_exit_zwei(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), mock.patch("sys.stdin", io.StringIO("[]")):
            code = policies.main(["sync", "--file", "-", "--workspace", str(self.ws)])
        self.assertEqual(code, 2)
        self.assertIn("get_policies", json.loads(out.getvalue())["error"])



def cockpit_pr36() -> dict:
    """Die Ausgabe von `get_policies` in genau der Form des Cockpits (ptai-portal, PR #36): Kopffelder der Datei,
    `brand`, `version`, `file_version`, `reference_shop`, `reference_shop_name`, `decided_by`, `decided_at`,
    `rules` im Format von `policies.json` (Felder der Datei unverändert, Antworten aus dem Cockpit eingesetzt),
    `open_rules` und `cockpit_questions`; je Baustein `name`, `path`, `description` und `content`."""
    return {
        "source": "Abstimmung im Team, erfunden",
        "brand": "beispielmarke",
        "version": "2026-01-13.2",
        "file_version": "2026-01-05.1",
        "reference_shop": "beispielshop",
        "reference_shop_name": "Beispielshop",
        "decided_by": "Vorname Nachname",
        "decided_at": "2026-01-05",
        "rules": [
            {"key": "tag_manager", "subject": "Tag Manager", "rule": "same_as_reference",
             "target": "Tag Manager als eigener Code", "keep": [["gtm", "app:gtm"]], "note": "wie im Referenz-Store",
             "owner_hint": "Feld, das das Format nicht kennt",
             "modules": [
                 {"name": "Tag Manager", "path": "policy-modules/tag_manager/README.md",
                  "description": "Einbindung des Tag Managers im Theme", "content": "# Tag Manager\n"},
                 {"name": "Tag Manager", "path": "policy-modules/tag_manager/snippets/tag-manager.liquid",
                  "description": None, "content": "{% comment %} Container-ID des Stores {% endcomment %}\n"}]},
            {"key": "bundles", "subject": "Beispielbundle", "rule": "same_as_reference",
             "target": "wie im Referenz-Store", "keep": [["app:beispielbundle", "beispielbundle"]],
             "decided_by": "Erika Muster", "decided_at": "2026-01-13T09:12:00+00:00"},
            {"key": "wishlist", "subject": "Merkliste", "rule": "open"},
        ],
        "open_rules": [{"key": "wishlist", "subject": "Merkliste", "text": "Merkliste: in allen Stores gleich?"}],
        "cockpit_questions": [{"key": "wishlist", "text": "Gilt das auch für den Outlet-Store?", "by": "Max Beispiel",
                               "at": "2026-01-13T10:00:00+00:00"}],
    }


class SyncCockpitFormat(unittest.TestCase):
    """`sync` liest die Ausgabe von `get_policies` so, wie das Cockpit sie liefert, und schreibt nur das Format."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.ws = Path(tmp.name) / "store"
        write(self.ws / "reporting" / "config.json", {"portal": {"brand": "beispielmarke", "shop": "nordshop"}})

    def test_die_form_des_cockpits_wird_gelesen_und_nur_das_format_geschrieben(self):
        result = policies.sync(self.ws, cockpit_pr36())
        copy = read(policies.copy_path(self.ws))
        self.assertEqual(sorted(copy), ["decided_at", "decided_by", "reference_shop", "rules", "version"])
        self.assertEqual(copy["version"], "2026-01-13.2")
        self.assertEqual(policies.validate(copy), [])
        tag_manager, bundles, wishlist = copy["rules"]
        self.assertNotIn("owner_hint", tag_manager)
        self.assertEqual(tag_manager["modules"], [
            {"name": "Tag Manager", "path": "policy-modules/tag_manager/README.md",
             "description": "Einbindung des Tag Managers im Theme"},
            {"name": "Tag Manager", "path": "policy-modules/tag_manager/snippets/tag-manager.liquid"}])
        self.assertEqual((bundles["decided_by"], bundles["decided_at"]),
                         ("Erika Muster", "2026-01-13T09:12:00+00:00"))
        self.assertEqual(wishlist, {"key": "wishlist", "subject": "Merkliste", "rule": "open"})
        self.assertEqual((self.ws / "migration/policy-modules/tag_manager/README.md").read_text(encoding="utf-8"),
                         "# Tag Manager\n")
        self.assertEqual(result["still_open"], [{"key": "wishlist", "subject": "Merkliste"}])
        self.assertEqual(result["modules_missing"], [])
        applied = policies.apply(self.ws, policies.load_source(policies.copy_path(self.ws)), now=NOW)
        self.assertEqual(sorted(applied["open_items_added"]),
                         ["POLICY-bundles-beispielbundle", "POLICY-tag_manager-gtm"])

    def test_neue_fragen_im_cockpit_aendern_die_fassung_im_repo_nicht(self):
        policies.sync(self.ws, cockpit_pr36())
        policies.apply(self.ws, policies.load_source(policies.copy_path(self.ws)), now=NOW)
        before = policies.copy_path(self.ws).read_text(encoding="utf-8")
        data = cockpit_pr36()
        data["cockpit_questions"].append({"key": "bundles", "text": "Und im Outlet?", "by": "Erika Muster",
                                          "at": "2026-01-13T11:00:00+00:00"})
        data["reference_shop_name"] = "Beispielshop DE"
        result = policies.sync(self.ws, data)
        self.assertFalse(result["changed"] or result["apply_needed"])
        self.assertEqual(policies.copy_path(self.ws).read_text(encoding="utf-8"), before)

    def test_ohne_datei_des_betreibers_traegt_jede_entschiedene_regel_ihre_person(self):
        data = cockpit_pr36()
        data.update({"decided_by": None, "decided_at": None, "file_version": None})
        del data["source"]
        data["rules"] = data["rules"][1:]
        policies.sync(self.ws, data)
        copy = read(policies.copy_path(self.ws))
        self.assertNotIn("decided_by", copy)
        self.assertEqual(policies.validate(copy), [])
        policies.apply(self.ws, policies.load_source(policies.copy_path(self.ws)), now=NOW)
        decision = read(policies.decisions_path(self.ws))["decisions"][0]
        self.assertEqual(decision["decided_by"], "Erika Muster")

    def test_ohne_person_an_datei_und_regel_wird_abgelehnt(self):
        data = cockpit_pr36()
        data.update({"decided_by": None, "decided_at": None})
        with self.assertRaises(policies.PolicyError) as raised:
            policies.sync(self.ws, data)
        self.assertIn("fehlen an der Regel und an der Datei", str(raised.exception))
        self.assertFalse(policies.copy_path(self.ws).exists())

class ValidateModules(unittest.TestCase):
    def errors(self, modules) -> list:
        data = source()
        data["rules"][0]["modules"] = modules
        return policies.validate(data)

    def test_gueltige_bausteine(self):
        self.assertEqual(self.errors([{"name": "Banner A", "path": "policy-modules/cookie_banner/README.md"}]), [])

    def test_ohne_namen(self):
        self.assertTrue(any("name fehlt" in e for e in self.errors([{"path": "policy-modules/cookie_banner/a.md"}])))

    def test_doppelter_pfad(self):
        module = {"name": "Banner A", "path": "policy-modules/cookie_banner/a.md"}
        self.assertTrue(any("doppelt" in e for e in self.errors([module, dict(module)])))

    def test_beschreibung_muss_text_sein(self):
        module = {"name": "Banner A", "path": "policy-modules/cookie_banner/a.md", "description": 3}
        self.assertTrue(any("description" in e for e in self.errors([module])))

    def test_keine_liste(self):
        self.assertTrue(self.errors({"name": "Banner A"}))

    def test_beschreibung_darf_fehlen(self):
        module = {"name": "Banner A", "path": "policy-modules/cookie_banner/a.md", "description": None}
        self.assertEqual(self.errors([module]), [])

if __name__ == "__main__":
    unittest.main()
