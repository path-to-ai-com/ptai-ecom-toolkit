"""Tests für das Ablegen der Session-Transkripte eines Migrationslaufs."""
import contextlib
import gzip
import io
import json
import os
import re
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from theme import run_state, sessions

# Erfundene Werte im Format echter Token, keiner davon war je gültig.
SHOPIFY = "shpat_" + "0123456789abcdef" * 2
GITHUB = "ghp_" + "A1b2C3d4E5" * 4


def line(**record) -> str:
    return json.dumps(record, ensure_ascii=False)


class SessionsTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        self.ws = base / "beispiel"
        self.ws.mkdir()
        run_state.new(self.ws, "2026-01-01-migration").save()
        self.projects = base / "projects"

    def session(self, folder: str, session_id: str, lines: list[str], agents: dict | None = None) -> None:
        directory = self.projects / folder
        directory.mkdir(parents=True, exist_ok=True)
        (directory / f"{session_id}.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
        for name, agent_lines in (agents or {}).items():
            path = directory / session_id / "subagents" / f"{name}.jsonl"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("\n".join(agent_lines) + "\n", encoding="utf-8")

    def archive(self) -> dict:
        return sessions.archive(self.ws, "2026-01-01-migration", self.projects, days=3650)

    def read(self, rel: str) -> str:
        path = self.ws / "reporting/runs/2026-01-01-migration/sessions" / rel
        return gzip.decompress(path.read_bytes()).decode("utf-8")

    def test_nur_sessions_dieses_workspaces_werden_abgelegt(self):
        self.session("a", "eigene", [line(type="user", cwd=str(self.ws.resolve()), timestamp="2026-01-01T10:00:00Z",
                                          message={"role": "user", "content": "los"})])
        self.session("b", "fremde", [line(type="user", cwd="/anderswo", message={"role": "user", "content": "x"})])
        result = self.archive()
        self.assertEqual(result["sessions"], 1)
        index = json.loads((self.ws / "reporting/runs/2026-01-01-migration/sessions/index.json").read_text())
        self.assertEqual(index[0]["session_id"], "eigene")
        self.assertEqual(index[0]["user_prompts"], 1)

    def test_eine_session_im_uebergeordneten_ordner_zaehlt_sobald_ihr_cwd_ins_repo_wechselt(self):
        self.session("eltern", "geklont", [
            line(type="user", cwd=str(self.ws.parent), message={"role": "user", "content": "klon das repo"}),
            line(type="assistant", cwd=str(self.ws.resolve()), message={"role": "assistant", "content": "ok"})])
        self.assertEqual(self.archive()["sessions"], 1)

    def test_token_werden_geschwaerzt_auch_in_subagents(self):
        cwd = str(self.ws.resolve())
        self.session("a", "s1", [line(type="user", cwd=cwd, message={"role": "user", "content": f"token {SHOPIFY}"})],
                     agents={"agent-1": [line(type="assistant", cwd=cwd, text=f"gh {GITHUB}")]})
        result = self.archive()
        self.assertEqual(result["subagents"], 1)
        self.assertEqual(result["redactions"], 2)
        self.assertNotIn(SHOPIFY, self.read("s1.jsonl.gz"))
        self.assertNotIn(GITHUB, self.read("s1/subagents/agent-1.jsonl.gz"))

    def test_felder_mit_geheimnis_werden_geschwaerzt(self):
        text, hits = sessions.redact('{"access_token": "abcdefghijklmnop1234"}')
        self.assertEqual((text, hits), ('{"access_token": "[REDACTED]"}', 1))

    def test_ein_zweiter_lauf_ueber_dieselbe_session_ist_byte_gleich(self):
        self.session("a", "s1", [line(type="user", cwd=str(self.ws.resolve()), message={"role": "user", "content": "x"})])
        self.archive()
        first = (self.ws / "reporting/runs/2026-01-01-migration/sessions/s1.jsonl.gz").read_bytes()
        self.archive()
        self.assertEqual(first, (self.ws / "reporting/runs/2026-01-01-migration/sessions/s1.jsonl.gz").read_bytes())

    def index(self) -> list[dict]:
        return json.loads((self.ws / "reporting/runs/2026-01-01-migration/sessions/index.json").read_text())

    def test_scratch_sitzung_mit_pfad_im_text_wird_nicht_zugeordnet(self):
        ws = str(self.ws.resolve())
        self.session("-tmp-scratch", "privat", [
            line(type="user", cwd="/tmp/scratch-2026-01-01", message={"role": "user", "content": f"schau in {ws}"}),
            line(type="assistant", cwd="/tmp/scratch-2026-01-01",
                 message={"role": "assistant", "content": json.dumps({"cwd": ws, "path": f"{ws}/state.json"})})])
        self.assertEqual(self.archive()["sessions"], 0)

    def test_sitzung_aus_fremdem_repo_mit_kurzem_wechsel_in_den_workspace_wird_nicht_zugeordnet(self):
        ws = self.ws.resolve()
        self.session("-werkzeug", "fremd", [line(type="user", cwd="/repos/werkzeug"),
                                            line(type="assistant", cwd=str(ws / "reporting")),
                                            line(type="assistant", cwd="/repos/werkzeug")])
        self.assertEqual(self.archive()["sessions"], 0)

    def test_unterordner_und_ziel_repo_zaehlen_ein_namensvetter_nicht(self):
        ws = self.ws.resolve()
        self.session("a", "unter", [line(type="user", cwd=str(ws / "migration" / "sub"))])
        self.session("b", "ziel", [line(type="user", cwd=str(ws.parent / f"{ws.name}-horizon"))])
        self.session("c", "vetter", [line(type="user", cwd=str(ws.parent / f"{ws.name}-alt"))])
        self.archive()
        self.assertEqual(sorted(e["session_id"] for e in self.index()), ["unter", "ziel"])

    def test_ohne_cwd_entscheidet_der_projektordner(self):
        folder = re.sub(r"[^A-Za-z0-9]", "-", str(self.ws.resolve()))
        self.session(folder, "alt", [line(type="user", message={"role": "user", "content": "x"})])
        self.session("-anderswo", "fremd", [line(type="user", message={"role": "user", "content": "x"})])
        self.archive()
        self.assertEqual([e["session_id"] for e in self.index()], ["alt"])

    def test_windows_pfad_json_escaped_im_cwd_wird_erkannt(self):
        self.session("C--Users-beispiel-Beispielshop", "win",
                     [line(type="user", cwd="C:\\Users\\beispiel\\Beispielshop\\migration")])
        raw = (self.projects / "C--Users-beispiel-Beispielshop" / "win.jsonl").read_text()
        self.assertIn("C:\\\\Users\\\\beispiel", raw)
        roots = sessions.path_forms("c:/USERS/Beispiel//beispielshop/")
        self.assertTrue(sessions.belongs_to(self.projects / "C--Users-beispiel-Beispielshop" / "win.jsonl", roots))

    def test_unc_und_laufwerk_sind_derselbe_workspace(self):
        def within(cwd: str, workspace: str) -> bool:
            roots = sessions.path_forms(workspace)
            return any(sessions.is_within(form, root) for form in sessions.path_forms(cwd) for root in roots)

        self.assertTrue(within("\\\\?\\C:\\Beispielshop\\sub", "C:\\Beispielshop"))
        self.assertTrue(within("\\\\?\\UNC\\server\\share\\Beispielshop", "\\\\server\\share\\beispielshop\\"))
        with mock.patch.object(sessions, "drive_target", lambda letter: "//server/share" if letter == "y" else None):
            self.assertTrue(within("\\\\server\\share\\Claude\\Beispielshop\\sub", "Y:\\Claude\\Beispielshop"))
            self.assertTrue(within("Y:\\Claude\\Beispielshop", "\\\\server\\share\\Claude\\Beispielshop"))
            self.assertFalse(within("Z:\\Claude\\Beispielshop", "\\\\server\\share\\Claude\\Beispielshop"))

    def test_leerer_lauf_ueberschreibt_den_index_nicht(self):
        self.session("a", "s1", [line(type="user", cwd=str(self.ws.resolve()), timestamp="2026-01-01T10:00:00Z")])
        self.archive()
        before = (self.ws / "reporting/runs/2026-01-01-migration/sessions/index.json").read_bytes()
        (self.projects / "a" / "s1.jsonl").unlink()
        result = self.archive()
        self.assertEqual((result["sessions"], result["indexed"], result["index_written"]), (0, 1, False))
        self.assertEqual(before, (self.ws / "reporting/runs/2026-01-01-migration/sessions/index.json").read_bytes())

    def test_zwei_laeufe_ergeben_keine_dubletten_und_fuehren_zusammen(self):
        cwd = str(self.ws.resolve())
        self.session("a", "s1", [line(type="user", cwd=cwd, timestamp="2026-01-01T10:00:00Z")])
        self.archive()
        self.archive()
        self.assertEqual([e["session_id"] for e in self.index()], ["s1"])
        (self.projects / "a" / "s1.jsonl").unlink()
        self.session("a", "s2", [line(type="user", cwd=cwd, timestamp="2026-01-02T10:00:00Z")])
        self.archive()
        self.assertEqual([e["session_id"] for e in self.index()], ["s1", "s2"])

    def test_dieselbe_session_in_zwei_projektordnern_ergibt_einen_eintrag(self):
        cwd = str(self.ws.resolve())
        self.session("laufwerk", "s1", [line(type="user", cwd=cwd, timestamp="2026-01-01T10:00:00Z")])
        self.session("unc", "s1", [line(type="user", cwd=cwd, timestamp="2026-01-01T10:00:00Z"),
                                   line(type="user", cwd=cwd, timestamp="2026-01-01T12:00:00Z")])
        now = time.time()
        os.utime(self.projects / "laufwerk" / "s1.jsonl", (now - 100, now - 100))
        os.utime(self.projects / "unc" / "s1.jsonl", (now, now))
        self.assertEqual(self.archive()["sessions"], 1)
        self.assertEqual([(e["project_dir"], e["ended"]) for e in self.index()], [("unc", "2026-01-01T12:00:00Z")])

    def test_dubletten_im_alten_index_werden_bereinigt(self):
        out = self.ws / "reporting/runs/2026-01-01-migration/sessions"
        out.mkdir(parents=True)
        old = [{"session_id": "s1", "ended": "2026-01-01T10:00:00Z", "bytes": 10},
               {"session_id": "s1", "ended": "2026-01-02T10:00:00Z", "bytes": 20}]
        (out / "index.json").write_text(json.dumps(old))
        self.session("a", "s2", [line(type="user", cwd=str(self.ws.resolve()), timestamp="2026-01-03T10:00:00Z")])
        self.archive()
        self.assertEqual([(e["session_id"], e.get("bytes")) for e in self.index()][0], ("s1", 20))
        self.assertEqual(len(self.index()), 2)

    def test_unlesbarer_index_bleibt_unangetastet(self):
        out = self.ws / "reporting/runs/2026-01-01-migration/sessions"
        out.mkdir(parents=True)
        (out / "index.json").write_text("{kaputt")
        self.session("a", "s1", [line(type="user", cwd=str(self.ws.resolve()))])
        with contextlib.redirect_stdout(io.StringIO()):
            code = sessions.main(["archive", "--workspace", str(self.ws), "--projects", str(self.projects),
                                  "--run-id", "2026-01-01-migration"])
        self.assertEqual(code, 2)
        self.assertEqual((out / "index.json").read_text(), "{kaputt")

    def test_cli_ohne_lauf_endet_mit_exit_2(self):
        empty = self.ws.parent / "leer"
        empty.mkdir()
        with contextlib.redirect_stdout(io.StringIO()):
            code = sessions.main(["archive", "--workspace", str(empty), "--projects", str(self.ws)])
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
