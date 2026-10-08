"""Tests für das Ablegen der Session-Transkripte eines Migrationslaufs."""
import contextlib
import gzip
import io
import json
import tempfile
import unittest
from pathlib import Path

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

    def test_eine_session_im_uebergeordneten_ordner_zaehlt_wenn_sie_das_repo_nennt(self):
        self.session("eltern", "geklont", [line(type="user", cwd=str(self.ws.parent),
                                                message={"role": "user", "content": f"cd {self.ws.resolve()}"})])
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

    def test_cli_ohne_lauf_endet_mit_exit_2(self):
        empty = self.ws.parent / "leer"
        empty.mkdir()
        with contextlib.redirect_stdout(io.StringIO()):
            code = sessions.main(["archive", "--workspace", str(empty), "--projects", str(self.ws)])
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
