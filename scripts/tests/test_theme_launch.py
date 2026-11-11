"""Geführter Launch: Haken-Liste, Frage nur bei allem grün, Veröffentlichen nach dem Ja, danach --after.

Kein Test geht ins Netz oder an die Shopify CLI: der Shop ist `FakeShop`, die CLI ein Runner, der den
Aufruf mitschreibt und die Rollen im Shop umstellt, und die Ergebnisse des Launch-Checks sind, wo es um die
Führung geht, gestellt.
"""
import contextlib
import io
import json
import subprocess
import sys
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from tests import test_theme_launch_check as base  # noqa: E402
from tests import theme_fake_shop as fake  # noqa: E402
from theme import launch  # noqa: E402
from theme import launch_check as lc  # noqa: E402
from theme import open_items  # noqa: E402
from theme import run_state  # noqa: E402
from theme import sync  # noqa: E402
from theme import templates as template_usage  # noqa: E402

NEW, OLD = "111111111111", "000000000000"
MIGRATION = "2026-11-01-migration"
TODAY_RUN = f"{date.today().isoformat()}-launch-check"
PERSON = "Pat Beispiel"


def iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def check(check_id, status, title, evidence="Beleg", question="", action="", owner=""):
    return {"id": check_id, "group": "Gruppe", "title": title, "status": status, "evidence": evidence,
            "action": action, "owner": owner, "question": question, "links": []}


GREEN = [check("timing-weekday", lc.OK, "Wochentag und Feiertag", "Dienstag, kein Feiertag"),
         check("live-sync", lc.OK, "Live-Theme seit dem letzten Abgleich", "unverändert seit 09.11."),
         check("draft-theme", lc.OK, "Entwurf", f"{NEW} Rolle UNPUBLISHED"),
         check("rollback-theme", lc.OK, "Rückfall-Theme", f"{OLD} Rolle MAIN"),
         check("seo-hreflang", lc.OK, "hreflang", "wie live"),
         check("go-decision", lc.OK, "Go/No-Go entschieden (G5)", f"Go von {PERSON}"),
         check("customer-accounts", lc.NA, "Kundenkonten", "keine alten Kundenkonten")]

RED = [check("timing-weekday", lc.OK, "Wochentag und Feiertag", "Dienstag, kein Feiertag"),
       check("sync-fresh", lc.MISSING, "Abgleich vor dem Launch", "letzter Abgleich vor 9 Tagen",
             action="sync-live-theme direkt vor dem Launch erneut laufen lassen", owner=lc.OPERATOR),
       check("baseline", lc.BLOCKED, "Vergleichswerte", "kein Zugang zu GA4", owner=lc.OPERATOR),
       check("go-decision", lc.MANUAL, "Go/No-Go entschieden (G5)", "G5 nicht eingetragen",
             question="Go für den Launch?", owner="Person der Marke mit Path to AI"),
       check("customer-accounts", lc.NA, "Kundenkonten", "keine alten Kundenkonten")]


def staged_report(checks, *, mode="before", checked_at=None) -> dict:
    statuses = {c["status"] for c in checks}
    recommendation = "no_go" if lc.MISSING in statuses else "open" if statuses & {lc.BLOCKED, lc.MANUAL} else "go"
    return {"kind": "launch-check", "mode": mode, "checked_at": checked_at or iso(datetime.now(timezone.utc)),
            "store": "beispiel.myshopify.com", "domain": "https://beispielshop.example", "old_theme_id": OLD,
            "new_theme_id": NEW, "launch_date": None, "migration_run": MIGRATION, "answers_file": "",
            "captures": {}, "recommendation": recommendation,
            "counts": {s: sum(1 for c in checks if c["status"] == s) for s in lc.STATUS_ORDER}, "checks": checks}


class Base(unittest.TestCase):
    """Ein Workspace mit Migrationslauf, Sicherung des Live-Themes, Bestandsaufnahme der Zuweisungen,
    Ziel-Repo und einem Shop mit Live-Theme und Entwurf."""

    def setUp(self):
        self.ws = fake.temp_workspace(self, draft_theme_id=NEW, target_repo="beispiel-theme",
                                      access={"read": "cli-grant", "write": "cli-theme"})
        config = json.loads((self.ws / "reporting" / "config.json").read_text())
        config["domain"] = "https://beispielshop.example"
        (self.ws / "reporting" / "config.json").write_text(json.dumps(config))
        (self.ws / "beispiel-theme" / "layout").mkdir(parents=True)
        (self.ws / "beispiel-theme" / "layout" / "theme.liquid").write_text("{{ content_for_layout }}")
        self.shop = base.LaunchShop()
        files = fake.fixture_files()
        self.live = self.shop.add_theme(fake.LIVE_ID, "MAIN", dict(files), name="Live")
        self.draft = self.shop.add_theme(fake.DRAFT_ID, "UNPUBLISHED", dict(files), name="Horizon Entwurf")
        self.shop.suffixes = {"products": ["", "beispiel", "beispiel"]}
        snapshot = self.ws / "migration" / "snapshots" / f"2026-11-09-{OLD}"
        for name, data in files.items():
            if name.startswith("templates/"):
                (snapshot / name).parent.mkdir(parents=True, exist_ok=True)
                (snapshot / name).write_bytes(data)
        (snapshot / "manifest.json").write_text(json.dumps({
            "theme_id": OLD, "theme_updated_at": self.live["updatedAt"], "captured_at": "2026-11-09T08:00:00Z"}))
        inventory = template_usage.usage(self.shop, snapshot)
        (self.ws / "migration" / "inventory").mkdir(parents=True)
        (self.ws / "migration" / "inventory" / "templates.json").write_text(json.dumps(inventory))
        open_items.init(self.ws)
        state = run_state.new(self.ws, MIGRATION)
        state.data["values"].update(live_theme_id=OLD, draft_theme_id=NEW, last_sync=date.today().isoformat())
        state.data["gates"]["G5-go-live"] = {"decided_by": PERSON, "decided_at": "2026-11-10T08:00:00+00:00",
                                             "note": "abgestimmt mit Path to AI"}
        state.save()
        self.cli_calls = []

    # Hilfen

    def write_report(self, checks, **kwargs) -> dict:
        report = staged_report(checks, **kwargs)
        path = self.ws / "reporting" / "runs" / TODAY_RUN / "launch-check.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report))
        return report

    def runner(self, publishes=True, exit_code=0):
        """Die Shopify CLI: schreibt den Aufruf mit und stellt die Rollen um wie `shopify theme publish`."""
        def run(cmd, **kwargs):
            self.cli_calls.append(cmd)
            if publishes:
                self.shop.themes[fake.LIVE_ID]["role"] = "UNPUBLISHED"
                self.shop.themes[fake.DRAFT_ID]["role"] = "MAIN"
            return subprocess.CompletedProcess(cmd, exit_code, stdout="Theme published", stderr="")
        return run

    def staged_check(self, report):
        """Statt des Prüflaufs ein gestelltes Ergebnis; schreibt den Bericht wie der echte Lauf."""
        calls = []

        def run(args, **injected):
            calls.append(args)
            data = dict(report, mode="after" if args.after else "before")
            run_dir = self.ws / "reporting" / "runs" / TODAY_RUN
            run_dir.mkdir(parents=True, exist_ok=True)
            suffix = "-after" if args.after else ""
            (run_dir / f"launch-check{suffix}.json").write_text(json.dumps(data))
            ctx = {"workspace": self.ws, "run_dir": run_dir, "suffix": suffix, "cache": {},
                   "transport": self.shop, "transport_error": None}
            return data, 0, ctx
        run.calls = calls
        return run

    def launch(self, *argv, check=None, runner=None, sleeps=None) -> tuple:
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = launch.main([*argv, "--workspace", str(self.ws)], transport=self.shop, check=check,
                               runner=runner, sleep=(sleeps.append if sleeps is not None else lambda s: None),
                               fetch=lambda url: (200, {}, "<html></html>"))
        return code, out.getvalue()

    def state_values(self) -> dict:
        return run_state.load(self.ws, MIGRATION).data["values"]


class TestHakenListe(unittest.TestCase):
    def test_jeder_punkt_mit_symbol_und_einer_zeile_beleg_und_die_summe(self):
        lines = launch.checklist(staged_report(RED))
        self.assertIn("✅ Wochentag und Feiertag", lines)
        self.assertIn("❌ Abgleich vor dem Launch", lines)
        self.assertIn("⏸ Vergleichswerte", lines)
        self.assertIn("✋ Go/No-Go entschieden (G5)", lines)
        self.assertEqual(lines[lines.index("⏸ Vergleichswerte") + 1], "   kein Zugang zu GA4")
        # Ein Punkt, der einen Menschen braucht, zeigt seine Frage.
        self.assertEqual(lines[lines.index("✋ Go/No-Go entschieden (G5)") + 1], "   Go für den Launch?")
        self.assertIn("1 von 4 grün", lines)
        self.assertIn("Entfällt für diesen Launch: Kundenkonten", lines)

    def test_alles_gruen(self):
        lines = launch.checklist(staged_report(GREEN))
        self.assertIn("6 von 6 grün", lines)
        self.assertFalse(any(line.startswith(("❌", "⏸", "✋")) for line in lines))

    def test_ein_langer_beleg_bleibt_eine_zeile(self):
        lines = launch.checklist(staged_report([check("x", lc.OK, "Punkt", "Wort " * 100)]))
        self.assertLessEqual(len(lines[1].strip()), launch.EVIDENCE_WIDTH)
        self.assertNotIn("\n", lines[1])


class TestFragen(Base):
    def test_nur_bei_allem_gruen_kommt_die_frage_mit_beiden_themes_und_dem_rueckfall(self):
        code, out = self.launch("check", check=self.staged_check(staged_report(GREEN)))
        self.assertEqual(code, 0)
        self.assertIn("6 von 6 grün", out)
        self.assertIn("Jetzt Launch durchführen?", out)
        self.assertIn(f"Neues Theme: {NEW} \"Horizon Entwurf\", wird live", out)
        self.assertIn(f"Bisher live: {OLD} \"Live\"", out)
        self.assertIn(f"Rückfall-Theme: {OLD} \"Live\"", out)

    def test_fehlt_etwas_wird_nicht_gefragt_sondern_gezeigt_was_fehlt_und_wer(self):
        code, out = self.launch("check", check=self.staged_check(staged_report(RED)))
        self.assertEqual(code, 1)
        self.assertNotIn("Jetzt Launch durchführen?", out)
        self.assertIn("Es fehlt:", out)
        missing = out.split("Es fehlt:")[1]
        self.assertIn("❌ Abgleich vor dem Launch\n   sync-live-theme direkt vor dem Launch erneut laufen lassen\n"
                      "   Wer: diese Sitzung", missing)
        self.assertIn("Wer: Person der Marke mit Path to AI", missing)
        self.assertNotIn("Wochentag", missing)

    def test_json_nennt_die_frage_nur_bei_gruen(self):
        code, out = self.launch("check", "--json", check=self.staged_check(staged_report(RED)))
        self.assertIsNone(json.loads(out)["ask"])
        code, out = self.launch("check", "--json", check=self.staged_check(staged_report(GREEN)))
        self.assertEqual(json.loads(out)["ask"], "Jetzt Launch durchführen?")


class TestVeroeffentlichen(Base):
    def test_nach_dem_ja_schlusspruefung_publish_zuruecklesen_stand(self):
        self.write_report(GREEN)
        code, out = self.launch("publish", "--approved-by", PERSON, runner=self.runner())
        self.assertEqual(code, 0, out)
        self.assertEqual(self.cli_calls, [["shopify", "theme", "publish", "--store", "beispiel.myshopify.com",
                                           "--theme", NEW, "--path", str(self.ws / "beispiel-theme"),
                                           "--force", "--no-input", "--no-color"]])
        self.assertIn(f"Veröffentlicht: {NEW} \"Horizon Entwurf\" ist live, Rolle MAIN", out)
        self.assertIn(f"Rückfall-Theme: {OLD} \"Live\", Rolle UNPUBLISHED", out)
        self.assertTrue(out.rstrip().endswith("Jetzt kommt der Launch-Check After."))
        values = self.state_values()
        self.assertEqual(values["live_theme_id"], NEW)
        self.assertEqual(values["rollback_theme_id"], OLD)
        self.assertEqual(values["launch_approved_by"], PERSON)
        self.assertTrue(values["published_at"])
        config = json.loads((self.ws / "reporting" / "config.json").read_text())
        self.assertEqual(config["theme_migration"]["live_theme_id"], NEW)
        record = json.loads((self.ws / "reporting" / "runs" / TODAY_RUN / "launch.json").read_text())
        self.assertEqual(record["status"], "published")
        self.assertTrue(record["final_check"]["ok"])
        self.assertTrue(record["final_check"]["assignments"]["unchanged"])
        self.assertEqual(record["readback"]["new_role"], "MAIN")
        migration = json.loads((self.ws / "reporting" / "runs" / MIGRATION / "migration.json").read_text())
        self.assertIn(f"nach Ja von {PERSON}", json.dumps(migration, ensure_ascii=False))

    def test_ohne_gruenen_launch_check_wird_nie_veroeffentlicht(self):
        self.write_report(RED)
        code, out = self.launch("publish", "--approved-by", PERSON, runner=self.runner())
        self.assertEqual(code, 1)
        self.assertEqual(self.cli_calls, [])
        self.assertIn("nicht grün", out)
        self.assertNotIn("published_at", self.state_values())

    def test_ohne_launch_check_von_heute_wird_nie_veroeffentlicht(self):
        code, out = self.launch("publish", "--approved-by", PERSON, runner=self.runner())
        self.assertEqual(code, 1)
        self.assertEqual(self.cli_calls, [])
        self.write_report(GREEN, checked_at=iso(datetime.now(timezone.utc) - timedelta(hours=13)))
        code, out = self.launch("publish", "--approved-by", PERSON, runner=self.runner())
        self.assertEqual(code, 1)
        self.assertIn("älter als 12 Stunden", out)
        self.assertEqual(self.cli_calls, [])

    def test_ohne_g5_im_migrationslauf_wird_nie_veroeffentlicht(self):
        state = run_state.load(self.ws, MIGRATION)
        state.data["gates"]["G5-go-live"] = None
        state.save()
        self.write_report(GREEN)
        code, out = self.launch("publish", "--approved-by", PERSON, runner=self.runner())
        self.assertEqual(code, 1)
        self.assertIn("G5", out)
        self.assertEqual(self.cli_calls, [])

    def test_ohne_namen_oder_mit_sammelnamen_kein_veroeffentlichen(self):
        self.write_report(GREEN)
        for name in ("  ", "Team"):
            code, _ = self.launch("publish", "--approved-by", name, runner=self.runner())
            self.assertEqual(code, 2)
        self.assertEqual(self.cli_calls, [])

    def test_schlusspruefung_haelt_an_wenn_das_live_theme_seit_dem_abgleich_geaendert_wurde(self):
        self.write_report(GREEN)
        self.shop.touch(fake.LIVE_ID, "snippets/icon.liquid", b"geaendert")
        code, out = self.launch("publish", "--approved-by", PERSON, runner=self.runner())
        self.assertEqual(code, 1)
        self.assertIn("die Schlussprüfung hält den Launch an", out)
        self.assertIn("Live-Theme geändert am", out)
        self.assertEqual(self.cli_calls, [])
        record = json.loads((self.ws / "reporting" / "runs" / TODAY_RUN / "launch.json").read_text())
        self.assertEqual(record["status"], "held")
        self.assertNotIn("published_at", self.state_values())

    def test_schlusspruefung_haelt_an_wenn_eine_template_zuweisung_dazukam(self):
        self.write_report(GREEN)
        self.shop.suffixes = {"products": ["", "beispiel", "beispiel", "beispiel"]}
        code, out = self.launch("publish", "--approved-by", PERSON, runner=self.runner())
        self.assertEqual(code, 1)
        self.assertIn("Template-Zuweisungen seit dem Abgleich vor dem Launch geändert: product.beispiel", out)
        self.assertEqual(self.cli_calls, [])

    def test_ohne_mutation_im_shop_das_veroeffentlichen_laeuft_nur_ueber_die_cli(self):
        self.write_report(GREEN)
        self.launch("publish", "--approved-by", PERSON, runner=self.runner())
        self.assertFalse([call for call in self.shop.calls if call[2]], "keine Mutation über die Admin-API")

    def test_nicht_bestaetigt_wenn_das_neue_theme_nicht_main_wird(self):
        self.write_report(GREEN)
        sleeps = []
        code, out = self.launch("publish", "--approved-by", PERSON, runner=self.runner(publishes=False),
                                sleeps=sleeps)
        self.assertEqual(code, 1)
        self.assertIn("Nicht bestätigt", out)
        self.assertEqual(sleeps, list(launch.READBACK_WAITS))
        self.assertNotIn("published_at", self.state_values())
        config = json.loads((self.ws / "reporting" / "config.json").read_text())
        self.assertEqual(config["theme_migration"]["live_theme_id"], OLD)

    def test_scheitert_die_cli_wird_einmal_zurueckgelesen_und_nichts_festgehalten(self):
        self.write_report(GREEN)
        sleeps = []
        code, out = self.launch("publish", "--approved-by", PERSON, runner=self.runner(publishes=False, exit_code=1),
                                sleeps=sleeps)
        self.assertEqual(code, 1)
        self.assertEqual(sleeps, [])
        self.assertIn("Exit 1", out)

    def test_der_entwurf_muss_ein_fertiger_entwurf_sein(self):
        self.write_report(GREEN)
        self.shop.themes[fake.DRAFT_ID]["processing"] = True
        code, out = self.launch("publish", "--approved-by", PERSON, runner=self.runner())
        self.assertEqual(code, 1)
        self.assertEqual(self.cli_calls, [])


class TestTestlauf(Base):
    """Der ganze Ablauf mit gestellten Ergebnissen: erst rot, dann grün, Ja, Veröffentlichen, After."""

    def test_haken_liste_frage_nur_bei_gruen_publish_nach_dem_ja_dann_after(self):
        # 1. Prüfen: noch rot, keine Frage.
        red = self.staged_check(staged_report(RED))
        code, out = self.launch("check", "--launch-date", date.today().isoformat(), check=red)
        self.assertEqual(code, 1)
        self.assertIn("1 von 4 grün", out)
        self.assertNotIn("Jetzt Launch durchführen?", out)
        self.assertFalse(red.calls[0].after)
        # Ohne Frage gibt es kein Ja; ein Versuch veröffentlicht nicht.
        code, _ = self.launch("publish", "--approved-by", PERSON, runner=self.runner())
        self.assertEqual((code, self.cli_calls), (1, []))

        # 2. Fragen: alles grün.
        code, out = self.launch("check", check=self.staged_check(staged_report(GREEN)))
        self.assertEqual(code, 0)
        self.assertIn("Jetzt Launch durchführen?", out)

        # 3. Ja von der Person der Marke: Veröffentlichen über die CLI.
        code, out = self.launch("publish", "--approved-by", PERSON, runner=self.runner())
        self.assertEqual(code, 0, out)
        self.assertEqual(self.cli_calls[0][:3], ["shopify", "theme", "publish"])
        self.assertIn("Jetzt kommt der Launch-Check After.", out)

        # 4. Prüfen danach, mit dem echten Prüflauf: die IDs kommen aus dem Stand, nicht von Hand.
        code, out = self.launch("check", "--after")
        report = json.loads((self.ws / "reporting" / "runs" / TODAY_RUN / "launch-check-after.json").read_text())
        self.assertEqual((report["mode"], report["old_theme_id"], report["new_theme_id"]), ("after", OLD, NEW))
        by_id = {c["id"]: c for c in report["checks"]}
        self.assertEqual(by_id["published-theme"]["status"], lc.OK)
        self.assertEqual(by_id["rollback-theme"]["status"], lc.OK)
        self.assertEqual(by_id["record-after"]["status"], lc.OK)
        self.assertIn(f"nach Ja von {PERSON}", by_id["record-after"]["evidence"])
        self.assertTrue(out.startswith("Launch-Check After"))
        self.assertIn("✅ Erwartetes Theme ist live", out)
        self.assertRegex(out, r"\d+ von \d+ grün")
        self.assertIn(f"Veröffentlicht: {self.state_values()['published_at']} nach Ja von {PERSON}", out)
        self.assertIn(f"Rückfall-Theme: {OLD}", out)


class TestGoPunktImLaunchCheck(base.Base):
    """G5 steht im Launch-Check als Go-Punkt, damit ohne G5 nie gefragt wird."""

    def migration(self, gate=None):
        state = run_state.new(self.ws, MIGRATION)
        state.data["gates"]["G5-go-live"] = gate
        state.save()

    def test_ohne_g5_braucht_der_punkt_einen_menschen(self):
        self.migration()
        _, report = self.run_check("--launch-date", "2026-10-13")
        item = self.by_id(report)["go-decision"]
        self.assertEqual(item["status"], lc.MANUAL)
        self.assertIn("13.10.2026", item["question"])

    def test_mit_g5_ist_der_punkt_erfuellt_mit_name(self):
        self.migration({"decided_by": PERSON, "decided_at": "2026-10-12T09:00:00+00:00", "note": "abgestimmt"})
        _, report = self.run_check("--launch-date", "2026-10-13")
        item = self.by_id(report)["go-decision"]
        self.assertEqual(item["status"], lc.OK)
        self.assertIn(PERSON, item["evidence"])

    def test_ohne_migrationslauf_kein_g5_punkt(self):
        _, report = self.run_check("--launch-date", "2026-10-13")
        self.assertNotIn("go-decision", self.by_id(report))

    def test_nach_dem_launch_kommt_das_rueckfall_theme_aus_dem_stand(self):
        state = run_state.new(self.ws, MIGRATION)
        state.data["values"].update(live_theme_id=NEW, draft_theme_id=NEW, rollback_theme_id=OLD,
                                    published_at="2026-10-13T09:00:00Z", launch_approved_by=PERSON)
        state.save()
        self.shop.themes[fake.LIVE_ID]["role"] = "UNPUBLISHED"
        self.shop.themes[fake.DRAFT_ID]["role"] = "MAIN"
        _, report = self.run_check("--after")
        self.assertEqual((report["old_theme_id"], report["new_theme_id"]), (OLD, NEW))
        self.assertEqual(self.by_id(report)["rollback-theme"]["status"], lc.OK)


class TestSchlusspruefungCli(Base):
    def test_sync_final_ohne_aenderung_exit_0_und_schreibt_nichts(self):
        before = sorted(p for p in self.ws.rglob("*") if p.is_file())
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = sync.main(["--final", "--workspace", str(self.ws)], transport=self.shop)
        self.assertEqual(code, 0, out.getvalue())
        self.assertTrue(json.loads(out.getvalue())["ok"])
        self.assertEqual(sorted(p for p in self.ws.rglob("*") if p.is_file()), before)

    def test_sync_final_mit_aenderung_exit_1(self):
        self.shop.touch(fake.LIVE_ID, "snippets/icon.liquid", b"geaendert")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = sync.main(["--final", "--workspace", str(self.ws)], transport=self.shop)
        self.assertEqual(code, 1)
        self.assertIn("Live-Theme geändert", json.loads(out.getvalue())["problems"][0])

    def test_ein_abgleich_mit_zuweisungen_ist_die_referenz(self):
        # Beim Abgleich vor dem Launch war schon ein Produkt mehr zugewiesen; das ist kein neuer Unterschied.
        self.shop.suffixes = {"products": ["", "beispiel", "beispiel", "beispiel"]}
        snapshot = next((self.ws / "migration" / "snapshots").iterdir())
        inventory = json.loads((self.ws / "migration" / "inventory" / "templates.json").read_text())
        delta = {"captured_at": "2026-11-10T07:00:00Z", "live_theme_id": OLD,
                 "theme_updated_at_after": self.live["updatedAt"], "snapshot": str(snapshot.relative_to(self.ws)),
                 "assignments": sync.compare_assignments(inventory, template_usage.usage(self.shop, snapshot))}
        (self.ws / "migration" / "sync" / "2026-11-10").mkdir(parents=True)
        (self.ws / "migration" / "sync" / "2026-11-10" / "delta.json").write_text(json.dumps(delta))
        result = sync.final_check(self.shop, self.ws, OLD)
        self.assertTrue(result["ok"], result["problems"])
        self.assertEqual(result["reference"]["kind"], "sync")


if __name__ == "__main__":
    unittest.main()
