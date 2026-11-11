"""Der Launch im Cockpit: Go-Liste aus dem jüngsten Launch-Check, Ablauf in sechs Schritten, Rückfall.

Kein Test geht ins Netz. Die Launch-Checks sind gestellte Berichte im Format von `launch_check.build_report`.
"""
import contextlib
import io
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from theme import launch, launch_status, open_items, run_state, steps
from theme import launch_check as lc

RUN = "2026-11-01-migration"
PERSON = "Pat Beispiel"
NOW = datetime(2026, 11, 11, 10, 0, tzinfo=timezone.utc)
NEW, OLD = "111111111111", "000000000000"


def iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def check(check_id, status, title, evidence="Beleg", question="", action="", owner=""):
    return {"id": check_id, "group": "Gruppe", "title": title, "status": status, "evidence": evidence,
            "action": action, "owner": owner, "question": question, "links": []}


RED = [check("timing-weekday", lc.OK, "Wochentag und Feiertag", "Mittwoch, kein Feiertag"),
       check("sync-fresh", lc.MISSING, "Abgleich vor dem Launch", "letzter Abgleich vor 9 Tagen",
             action="sync-live-theme direkt vor dem Launch erneut laufen lassen", owner=lc.OPERATOR),
       check("baseline", lc.BLOCKED, "Vergleichswerte", "kein Zugang zu GA4", owner=lc.BOTH),
       check("go-decision", lc.MANUAL, "Go/No-Go entschieden (G5)", "G5 nicht eingetragen",
             question="Go für den Launch?", owner="Person der Marke mit Path to AI"),
       check("customer-accounts", lc.NA, "Kundenkonten", "keine alten Kundenkonten")]
GREEN = [check("timing-weekday", lc.OK, "Wochentag und Feiertag", "Mittwoch, kein Feiertag"),
         check("go-decision", lc.OK, "Go/No-Go entschieden (G5)", f"Go von {PERSON}"),
         check("customer-accounts", lc.NA, "Kundenkonten", "keine alten Kundenkonten")]


def report(checks, *, mode="before", checked_at=NOW - timedelta(hours=1), run=RUN) -> dict:
    statuses = {c["status"] for c in checks}
    recommendation = "no_go" if lc.MISSING in statuses else "open" if statuses & {lc.BLOCKED, lc.MANUAL} else "go"
    return {"kind": "launch-check", "mode": mode, "checked_at": iso(checked_at), "store": "beispiel.myshopify.com",
            "domain": "https://beispielshop.example", "old_theme_id": OLD, "new_theme_id": NEW,
            "launch_date": "2026-11-11", "migration_run": run, "answers_file": "", "captures": {},
            "recommendation": recommendation,
            "counts": {s: sum(1 for c in checks if c["status"] == s) for s in lc.STATUS_ORDER}, "checks": checks}


class Workspace(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.ws = Path(tmp.name)
        write(self.ws / "reporting" / "config.json", {"theme_migration": {"people": [PERSON, "Kim Muster"]}})
        open_items.init(self.ws)
        env = mock.patch.dict(os.environ, {}, clear=False)
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("PTAI_OPERATOR", None)
        os.environ.pop("CLAUDE_CODE_SESSION_ID", None)
        self.state = run_state.new(self.ws, RUN)

    def place(self, data: dict, folder: str = "2026-11-11-launch-check") -> None:
        name = "launch-check-after.json" if data["mode"] == "after" else "launch-check.json"
        write(self.ws / "reporting" / "runs" / folder / name, data)

    def launch_block(self, *, sync_done=False, moment=NOW) -> dict:
        return launch_status.build(self.ws, self.state.data, sync_done=sync_done, people=[PERSON], now=moment)

    def flow(self, **kwargs) -> dict:
        return {s["key"]: s for s in self.launch_block(**kwargs)["flow"]}

    def publish(self, at: datetime = NOW - timedelta(hours=2)) -> None:
        values = self.state.data["values"]
        values.update(published_at=iso(at), live_theme_id=NEW, rollback_theme_id=OLD, launch_approved_by=PERSON)
        self.state.data["phases"]["9-launch"] = "running"


class SameValuesTest(unittest.TestCase):
    def test_statuswerte_und_zustaendige_wie_im_launch_check(self):
        self.assertEqual((launch_status.OK, launch_status.MISSING, launch_status.BLOCKED, launch_status.MANUAL,
                          launch_status.NA), (lc.OK, lc.MISSING, lc.BLOCKED, lc.MANUAL, lc.NA))
        self.assertEqual((launch_status.OPERATOR, launch_status.TEAM, launch_status.BOTH),
                         (lc.OPERATOR, lc.TEAM, lc.BOTH))

    def test_freigabe_und_cockpit_rechnen_mit_derselben_frist(self):
        self.assertEqual(launch.REPORT_MAX_AGE, launch_status.REPORT_MAX_AGE)


class GoListTest(Workspace):
    def test_go_liste_wie_die_haken_liste(self):
        self.place(report(RED))
        view = self.launch_block()["check"]
        self.assertEqual((view["green"], view["total"]), (1, 4))
        self.assertEqual(view["not_applicable"], ["Kundenkonten"])
        self.assertEqual([i["id"] for i in view["items"]], ["timing-weekday", "sync-fresh", "baseline", "go-decision"])
        self.assertEqual(view["recommendation"], "no_go")
        self.assertEqual((view["new_theme_id"], view["old_theme_id"]), (NEW, OLD))

    def test_jeder_punkt_mit_beleg_aufgabe_und_wer(self):
        self.place(report(RED))
        items = {i["id"]: i for i in self.launch_block()["check"]["items"]}
        self.assertEqual(set(items["sync-fresh"]), {"id", "group", "title", "status", "evidence", "todo", "owner"})
        self.assertEqual(items["sync-fresh"]["owner"], "claude")
        self.assertEqual(items["sync-fresh"]["todo"], "sync-live-theme direkt vor dem Launch erneut laufen lassen")
        self.assertEqual(items["baseline"]["owner"], "both")
        # Bei einer Frage steht die Frage als Aufgabe, nicht die Handlung.
        self.assertEqual(items["go-decision"]["todo"], "Go für den Launch?")
        self.assertEqual(items["go-decision"]["owner"], "team")
        self.assertIsNone(items["timing-weekday"]["owner"])
        self.assertIsNone(items["timing-weekday"]["todo"])

    def test_langer_beleg_wird_eine_zeile(self):
        long = check("seo-pages", lc.MISSING, "Seiten", "Zeile\n" + "x" * 500, owner=lc.OPERATOR)
        self.place(report([long]))
        evidence = self.launch_block()["check"]["items"][0]["evidence"]
        self.assertLessEqual(len(evidence), launch_status.EVIDENCE_WIDTH)
        self.assertNotIn("\n", evidence)
        self.assertTrue(evidence.endswith("…"))

    def test_juengster_bericht_gilt(self):
        self.place(report(RED, checked_at=NOW - timedelta(hours=20)), "2026-11-10-launch-check")
        self.place(report(GREEN, checked_at=NOW - timedelta(hours=1)), "2026-11-11-launch-check")
        self.assertEqual(self.launch_block()["check"]["recommendation"], "go")

    def test_bericht_eines_anderen_migrationslaufs_zaehlt_nicht(self):
        self.place(report(GREEN, run="2026-09-01-migration"))
        self.assertIsNone(self.launch_block()["check"])

    def test_ohne_launch_check_keine_liste(self):
        block = self.launch_block()
        self.assertIsNone(block["check"])
        self.assertIsNone(block["check_after"])

    def test_launch_check_danach_aus_einem_frueheren_versuch_zaehlt_nicht(self):
        self.publish(at=NOW - timedelta(hours=2))
        self.place(report(GREEN, mode="after", checked_at=NOW - timedelta(days=3)))
        self.assertIsNone(self.launch_block()["check_after"])


class FlowTest(Workspace):
    def test_sechs_schritte_in_fester_reihenfolge(self):
        flow = self.launch_block()["flow"]
        self.assertEqual([s["name"] for s in flow],
                         ["Vorbereiten", "Prüfen", "Go", "Veröffentlichen", "Prüfen danach", "Beobachten"])
        self.assertTrue(all(s["status"] == "open" for s in flow[1:]))

    def test_vorbereiten_nennt_was_fehlt(self):
        flow = self.flow(sync_done=True)
        self.assertEqual(flow["prepare"]["status"], "running")
        self.assertEqual(flow["prepare"]["note"], "Ausstehend: Rückfallkriterien")
        launch.set_rollback(self.ws, PERSON, ["Kauf nicht möglich | sofort"])
        self.assertEqual(self.flow(sync_done=True)["prepare"]["status"], "done")

    def test_pruefen_nicht_gruen_zeigt_die_summe(self):
        self.place(report(RED))
        flow = self.flow()
        self.assertEqual((flow["check"]["status"], flow["check"]["note"]), ("running", "1 von 4 grün"))
        self.assertEqual(flow["go"]["status"], "open")

    def test_gruen_und_frisch_heisst_go_wird_gefragt(self):
        self.place(report(GREEN))
        flow = self.flow()
        self.assertEqual((flow["check"]["status"], flow["check"]["note"]), ("done", "2 von 2 grün"))
        self.assertEqual(flow["go"]["status"], "running")
        self.assertEqual(flow["go"]["note"], "Bestätigung ausstehend")
        self.assertEqual(flow["go"]["person"], PERSON)

    def test_gruen_aber_aelter_als_zwoelf_stunden_wird_neu_geprueft(self):
        self.place(report(GREEN, checked_at=NOW - timedelta(hours=13)))
        flow = self.flow()
        self.assertEqual(flow["check"]["status"], "running")
        self.assertEqual(flow["check"]["note"], "2 von 2 grün, älter als 12 Stunden")
        self.assertEqual(flow["go"]["status"], "open")

    def test_g5_ohne_gruene_liste_nennt_die_person(self):
        self.state.data["gates"]["G5-go-live"] = {"decided_by": "Kim Muster", "decided_at": iso(NOW), "note": ""}
        self.place(report(RED))
        flow = self.flow()
        # Gefragt wird erst bei allem grün; bis dahin läuft nur Prüfen.
        self.assertEqual(flow["go"]["status"], "open")
        self.assertEqual(flow["go"]["person"], "Kim Muster")
        self.assertEqual(flow["go"]["note"], "G5 entschieden von Kim Muster")

    def test_nach_dem_veroeffentlichen_steht_der_check_danach_aus(self):
        self.place(report(GREEN))
        self.publish()
        flow = self.flow()
        self.assertEqual((flow["go"]["status"], flow["go"]["note"]), ("done", f"Ja von {PERSON}"))
        self.assertEqual(flow["live"]["status"], "done")
        self.assertEqual(flow["check_after"]["status"], "running")
        self.assertEqual(flow["check_after"]["note"], "Launch-Check ausstehend")
        self.assertEqual(flow["observe"]["status"], "running")
        self.assertEqual(flow["observe"]["note"], iso(NOW - timedelta(hours=2) + timedelta(hours=48)))

    def test_check_danach_gruen_und_48_stunden_vorbei(self):
        self.publish(at=NOW - timedelta(hours=50))
        self.place(report(GREEN, mode="after", checked_at=NOW - timedelta(hours=49)))
        block = self.launch_block()
        flow = {s["key"]: s for s in block["flow"]}
        self.assertEqual(flow["check_after"]["status"], "done")
        self.assertEqual(flow["observe"]["status"], "done")
        self.assertEqual(block["check_after"]["mode"], "after")
        self.assertEqual(block["new_theme_id"], NEW)

    def test_zustaendige_je_schritt(self):
        flow = self.flow()
        self.assertEqual(flow["prepare"]["owners"], ["team", "claude"])
        self.assertEqual(flow["live"]["owners"], ["claude"])
        self.assertIsNone(flow["live"]["person"])
        self.assertEqual(flow["observe"]["owners"], ["operator", "claude"])


class RollbackTest(Workspace):
    def test_kriterien_mit_frist_und_person(self):
        plan = launch.set_rollback(self.ws, PERSON, ["Kauf auf einem Gerät nicht möglich | sofort",
                                                     "Tracking fällt aus"],
                                   not_reverted=["App X ist deinstalliert"], agreed_with="Path to AI")
        self.assertEqual(plan["criteria"], [{"when": "Kauf auf einem Gerät nicht möglich", "deadline": "sofort"},
                                            {"when": "Tracking fällt aus", "deadline": None}])
        self.assertTrue(launch_status.rollback_path(self.ws).is_file())
        view = self.launch_block()["rollback"]
        self.assertEqual((view["decider"], view["agreed_with"]), (PERSON, "Path to AI"))
        self.assertEqual(view["criteria"], plan["criteria"])
        self.assertEqual(view["not_reverted"][0], {"text": "App X ist deinstalliert", "source": "team"})
        self.assertEqual([n["text"] for n in view["not_reverted"][1:]], list(launch_status.NOT_REVERTED))

    def test_sammelname_entscheidet_keinen_rueckfall(self):
        with self.assertRaises(launch.LaunchError):
            launch.set_rollback(self.ws, "Team", ["Kauf nicht möglich | sofort"])

    def test_ohne_kriterium_kein_rueckfall(self):
        with self.assertRaises(launch.LaunchError):
            launch.set_rollback(self.ws, PERSON, [])
        with self.assertRaises(launch.LaunchError):
            launch.set_rollback(self.ws, PERSON, [" | sofort"])

    def test_neuer_aufruf_ersetzt_die_kriterien(self):
        launch.set_rollback(self.ws, PERSON, ["A | sofort", "B"])
        launch.set_rollback(self.ws, PERSON, ["C"])
        self.assertEqual([c["when"] for c in self.launch_block()["rollback"]["criteria"]], ["C"])

    def test_rueckfall_theme_vor_und_nach_dem_launch(self):
        self.state.data["values"]["live_theme_id"] = "999"
        self.assertEqual(self.launch_block()["rollback"]["theme_id"], "999")
        self.place(report(RED))
        self.assertEqual(self.launch_block()["rollback"]["theme_id"], OLD)
        self.publish()
        self.state.data["values"]["rollback_theme_id"] = "123"
        self.assertEqual(self.launch_block()["rollback"]["theme_id"], "123")

    def test_ohne_kriterien_bleibt_die_liste_der_regel(self):
        view = self.launch_block()["rollback"]
        self.assertEqual(view["criteria"], [])
        self.assertIsNone(view["decider"])
        self.assertEqual(len(view["not_reverted"]), len(launch_status.NOT_REVERTED))

    def test_cli_legt_fest_und_zeigt(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = launch.main(["rollback", "--workspace", str(self.ws), "--decider", PERSON,
                                "--criterion", "Kauf nicht möglich | sofort", "--agreed-with", "Path to AI"])
        self.assertEqual(code, 0)
        self.assertIn("Entscheidet: Pat Beispiel, abgestimmt mit Path to AI", out.getvalue())
        self.assertIn("Kauf nicht möglich (sofort)", out.getvalue())
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(launch.main(["rollback", "--workspace", str(self.ws), "--json"]), 0)
        self.assertEqual(json.loads(out.getvalue())["decider"], PERSON)

    def test_cli_ohne_person_ist_ein_fehler(self):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            code = launch.main(["rollback", "--workspace", str(self.ws), "--criterion", "Kauf nicht möglich"])
        self.assertEqual(code, 2)
        self.assertFalse(launch_status.rollback_path(self.ws).exists())


class MigrationJsonTest(Workspace):
    def test_migration_json_traegt_den_launch(self):
        self.place(report(RED))
        launch.set_rollback(self.ws, PERSON, ["Kauf nicht möglich | sofort"])
        data = steps.export(self.ws, self.state.data, "0.0.0", git_status={"met": True, "note": None}, moment=NOW)
        self.assertEqual(data["schema"], 1)
        self.assertEqual(data["launch"]["check"]["total"], 4)
        self.assertEqual(len(data["launch"]["flow"]), 6)
        self.assertEqual(data["launch"]["rollback"]["criteria"][0]["deadline"], "sofort")
        # Die Handover-Zeile `now` bleibt, was sie war; der Zeitpunkt des Launches ist ein eigenes Argument.
        self.assertNotEqual(data["now"], NOW)

    def test_run_state_schreibt_den_block_nach_jedem_befehl(self):
        self.place(report(GREEN))
        self.state.save()
        run_state.export(self.ws, self.state)
        written = json.loads(run_state.migration_path(self.ws, RUN).read_text(encoding="utf-8"))
        self.assertEqual(written["launch"]["check"]["recommendation"], "go")


if __name__ == "__main__":
    unittest.main()
