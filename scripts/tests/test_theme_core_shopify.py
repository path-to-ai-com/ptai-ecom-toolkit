"""Zugang: CLI mit Drosselung und erlaubten Mutationen, Cockpit nur lesend, Wahl aus der Config."""
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from theme import shopify  # noqa: E402

QUERY = "query ThemeList { themes(first: 250) { nodes { id } } }"
MUTATION = "mutation UpsertThemeFiles($themeId: ID!) { themeFilesUpsert(themeId: $themeId, files: []) { job { id } } }"


class FakeRunner:
    """Spielt die CLI: je Aufruf ein vorbereitetes Ergebnis, merkt sich Befehl und Dateien."""

    def __init__(self, *results):
        self.results = list(results)
        self.calls = []

    def __call__(self, cmd, **kwargs):
        record = {"cmd": cmd}
        if "--query-file" in cmd:
            record["query"] = Path(cmd[cmd.index("--query-file") + 1]).read_text(encoding="utf-8")
        if "--variable-file" in cmd:
            record["variables"] = json.loads(Path(cmd[cmd.index("--variable-file") + 1]).read_text(encoding="utf-8"))
        self.calls.append(record)
        code, out, err = self.results.pop(0)
        return subprocess.CompletedProcess(cmd, code, out, err)


def ok(data):
    return 0, json.dumps(data), ""


class TestCliTransport(unittest.TestCase):
    def setUp(self):
        self.slept = []

    def transport(self, runner):
        return shopify.CliTransport("beispiel.myshopify.com", runner=runner, sleep=self.slept.append)

    def test_abfrage_geht_als_datei_mit_store_und_json_ohne_mutationsfreigabe(self):
        runner = FakeRunner(ok({"themes": {"nodes": []}}))
        data = self.transport(runner).execute(QUERY, {"after": None, "geheim": "x" * 10})
        self.assertEqual(data, {"themes": {"nodes": []}})
        cmd = runner.calls[0]["cmd"]
        self.assertEqual(cmd[:5], ["shopify", "store", "execute", "--store", "beispiel.myshopify.com"])
        self.assertIn("--json", cmd)
        self.assertNotIn("--allow-mutations", cmd)
        self.assertEqual(runner.calls[0]["query"], QUERY)
        self.assertEqual(runner.calls[0]["variables"]["geheim"], "x" * 10)
        self.assertFalse(any("geheim" in part for part in cmd), "Variablen nie als Argument")

    def test_mutation_braucht_die_ausdrueckliche_freigabe(self):
        runner = FakeRunner(ok({"themeFilesUpsert": {"job": None}}))
        with self.assertRaisesRegex(shopify.ShopifyError, "mutation=True"):
            self.transport(runner).execute(MUTATION, {"themeId": "x"})
        self.assertEqual(runner.calls, [])
        self.transport(runner).execute(MUTATION, {"themeId": "x"}, mutation=True)
        self.assertIn("--allow-mutations", runner.calls[0]["cmd"])

    def test_drosselung_wartet_und_wiederholt_statt_leer_zu_melden(self):
        runner = FakeRunner((1, "", "Throttled"), ok({"themes": {"nodes": [{"id": "a"}]}}))
        data = self.transport(runner).execute(QUERY)
        self.assertEqual(data["themes"]["nodes"], [{"id": "a"}])
        self.assertEqual(self.slept, [20])

    def test_leere_antwort_ist_nie_keine_daten(self):
        runner = FakeRunner((0, "", ""), (0, "  ", ""), (0, "", ""))
        with self.assertRaisesRegex(shopify.ShopifyError, "leere Antwort"):
            self.transport(runner).execute(QUERY)
        self.assertEqual(self.slept, [20, 40])

    def test_throttled_in_der_antwort_wird_ebenfalls_wiederholt(self):
        throttled = {"errors": [{"message": "Throttled", "extensions": {"code": "THROTTLED"}}]}
        runner = FakeRunner(ok(throttled), ok({"data": {"themes": {"nodes": []}}}))
        self.assertEqual(self.transport(runner).execute(QUERY), {"themes": {"nodes": []}})

    def test_eine_mutation_wird_nach_einem_anderen_fehler_nicht_wiederholt(self):
        runner = FakeRunner((1, "", "Network error"), ok({}))
        with self.assertRaisesRegex(shopify.ShopifyError, "nicht wiederholt"):
            self.transport(runner).execute(MUTATION, mutation=True)
        self.assertEqual(len(runner.calls), 1)

    def test_eine_gedrosselte_mutation_darf_wiederholt_werden(self):
        runner = FakeRunner((1, "", "Request was throttled"), ok({"themeFilesUpsert": {}}))
        self.transport(runner).execute(MUTATION, mutation=True)
        self.assertEqual(len(runner.calls), 2)

    def test_graphql_fehler_werden_zum_fehler(self):
        runner = FakeRunner(ok({"errors": [{"message": "Field 'x' doesn't exist"}]}))
        with self.assertRaisesRegex(shopify.ShopifyError, "doesn't exist"):
            self.transport(runner).execute(QUERY)

    def test_nur_eine_myshopify_domain_ist_ein_store(self):
        with self.assertRaises(shopify.ShopifyError):
            shopify.CliTransport("beispielshop.example")


class TestPortalTransport(unittest.TestCase):
    def test_das_cockpit_bekommt_nie_eine_mutation(self):
        calls = []
        transport = shopify.PortalTransport("beispielmarke", "eu", execute_fn=lambda *a: calls.append(a))
        for kwargs in ({"mutation": True}, {}):
            with self.subTest(kwargs=kwargs), self.assertRaisesRegex(shopify.ShopifyError, "nur lesend"):
                transport.execute(MUTATION, **kwargs)
        self.assertEqual(calls, [])

    def test_drosselung_im_cockpit_wird_wiederholt(self):
        answers = [RuntimeError("Shopify: gedrosselt (THROTTLED), später erneut versuchen"), {"themes": {}}]

        def fake(brand, shop, query, variables):
            answer = answers.pop(0)
            if isinstance(answer, Exception):
                raise answer
            return answer

        slept = []
        transport = shopify.PortalTransport("beispielmarke", "eu", execute_fn=fake, sleep=slept.append)
        self.assertEqual(transport.execute(QUERY), {"themes": {}})
        self.assertEqual(slept, [20])


class TestAuswahl(unittest.TestCase):
    def test_lesen_ueber_cli_grant_als_standard(self):
        transport = shopify.transport_from_config({"shopify_store": "beispiel.myshopify.com"})
        self.assertIsInstance(transport, shopify.CliTransport)

    def test_mit_cockpit_block_wird_ueber_das_cockpit_gelesen(self):
        config = {"shopify_store": "beispiel.myshopify.com", "portal": {"brand": "beispielmarke", "shop": "eu"}}
        self.assertIsInstance(shopify.transport_from_config(config), shopify.PortalTransport)

    def test_schreiben_geht_nur_mit_admin_api_und_nie_uebers_cockpit(self):
        base = {"shopify_store": "beispiel.myshopify.com", "portal": {"brand": "beispielmarke", "shop": "eu"}}
        with self.assertRaisesRegex(shopify.ShopifyError, "admin-api"):
            shopify.transport_from_config(base, write=True)
        config = dict(base, theme_migration={"access": {"read": "portal", "write": "admin-api"}})
        self.assertIsInstance(shopify.transport_from_config(config, write=True), shopify.CliTransport)

    def test_theme_ids_werden_zur_gid(self):
        self.assertEqual(shopify.theme_gid("111111111111"), "gid://shopify/OnlineStoreTheme/111111111111")
        self.assertEqual(shopify.numeric_id("gid://shopify/OnlineStoreTheme/111111111111"), "111111111111")
        with self.assertRaises(shopify.ShopifyError):
            shopify.theme_gid("live")


if __name__ == "__main__":
    unittest.main()
