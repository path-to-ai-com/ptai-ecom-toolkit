"""Tests für den Fake-Shop-Check (scripts/fakeshops). Ohne Netz, mit erfundener Marke."""
import unittest

from unittest import mock

import stat
import tempfile
from pathlib import Path

from fakeshops import candidates, classify, probe, recheck, screens, state, takedown

OWN = ["beispielshop.de", "beispielshop.com"]


def row(domain, **kw):
    base = {"domain": domain, "keyword": "beispielshop", "first_cert": "2026-05-01", "last_cert": "2026-05-01",
            "http_status": 200, "final_url": f"https://{domain}/", "fetch_error": "", "dns": "NOERROR", "ip": "192.0.2.10",
            "asn": "AS64500", "network": "Testnetz", "nameservers": [], "title": "", "platform": "", "legal_notice": False,
            "brand_mentions": 0, "discount": None, "under_construction": False, "registrar_abuse": "", "host_abuse": ""}
    base.update(kw)
    return base


class Candidates(unittest.TestCase):
    def test_registrierte_domain_kennt_zweistufige_endungen(self):
        self.assertEqual(candidates.registered_domain("shop.beispielshop.co.uk"), "beispielshop.co.uk")
        self.assertEqual(candidates.registered_domain("*.img.beispielshoppro.shop"), "beispielshoppro.shop")

    def test_stichwoerter_aus_marke_und_domains_ohne_doppelte(self):
        self.assertEqual(candidates.keywords("Beispiel Büffel", ["beispiel-bueffel.de"]),
                         ["beispielbueffel", "beispiel-bueffel"])

    def test_eigene_domains_und_geteilte_hosts_fallen_weg(self):
        rows = [("2026-03-01", "2026-03-01", "www.beispielshop.de"),
                ("2026-03-02", "2026-03-02", "beispielshop.workers.dev"),
                ("2026-04-01", "2026-04-02", "*.beispielshoppro.shop"),
                ("2026-04-01", "2026-04-01", "img.beispielshoppro.shop"),
                ("2026-05-01", "2026-05-01", "beispielshop.fremd.shop")]
        got = candidates.collect(rows, "beispielshop", OWN, "2026-01-01")
        self.assertEqual(sorted(got), ["beispielshop.fremd.shop", "beispielshoppro.shop"])
        self.assertEqual(sorted(got["beispielshoppro.shop"]["hostnames"]), ["beispielshoppro.shop", "img.beispielshoppro.shop"])

    def test_kandidat_ohne_zertifikat_seit_stichtag_faellt_weg(self):
        rows = [("2024-01-01", "2025-06-01", "beispielshopalt.shop")]
        self.assertEqual(candidates.collect(rows, "beispielshop", OWN, "2026-01-01"), {})

    def test_bindestrich_im_stichwort_findet_domain_ohne_bindestrich(self):
        rows = [("2026-03-25", "2026-03-25", "beispielbueffelco.shop")]
        self.assertIn("beispielbueffelco.shop", candidates.collect(rows, "beispiel-bueffel", ["beispiel-bueffel.de"], "2026-01-01"))


class Features(unittest.TestCase):
    def test_typischer_rabatt_aus_preispaaren(self):
        html = "$277.04 $83.11 ... $270.41 $81.12 ... $11 ... $4.95"
        self.assertEqual(probe.typical_discount(html), (70, 2))

    def test_euro_mit_komma_wird_richtig_gelesen(self):
        self.assertEqual(probe.parse_amount("1.299,00"), 1299.0)
        self.assertEqual(probe.parse_amount("7,289.16"), 7289.16)

    def test_markenname_mit_umlaut_in_jeder_schreibweise(self):
        rx = probe.brand_pattern("Beispiel Büffel")
        for text in ["BEISPIEL BÜFFEL", "beispiel bueffel", "Beispiel&nbsp;B&uuml;ffel"]:
            self.assertTrue(rx.search(text), text)


class Classify(unittest.TestCase):
    def test_bekannter_hoster_und_muster_ohne_impressum_ist_live_fake(self):
        r = classify.classify(row("beispielshoppro.shop", asn="AS199242", title="Beispielshop | Offizieller Shop", brand_mentions=40, discount=70),
                              "Beispielshop", OWN)
        self.assertEqual(r["category"], "fake_live")

    def test_marke_ohne_starkes_signal_bleibt_unklar(self):
        r = classify.classify(row("beispielshop.fremd.de", title="Beispielshop Fanseite", brand_mentions=5), "Beispielshop", OWN)
        self.assertEqual(r["category"], "unclear")

    def test_nxdomain_mit_muster_gilt_als_abgeschaltet(self):
        r = classify.classify(row("beispielshopstore.shop", dns="NXDOMAIN", http_status=0), "Beispielshop", OWN)
        self.assertEqual(r["category"], "taken_down")

    def test_weiterleitung_auf_eigene_domain(self):
        r = classify.classify(row("beispielshop-outlet.de", final_url="https://www.beispielshop.de/", title="Beispielshop", brand_mentions=50),
                              "Beispielshop", OWN)
        self.assertEqual(r["category"], "redirect_own")

    def test_keine_antwort_beim_bekannten_hoster_ist_nicht_erreichbar_nicht_offline(self):
        r = classify.classify(row("beispielshopco.shop", http_status=0, asn="AS199242", fetch_error="timed out"), "Beispielshop", OWN)
        self.assertEqual(r["category"], "fake_unreachable")

    def test_namensvetter_ohne_markennennung(self):
        r = classify.classify(row("beispielshopper.com", title="Finanzberatung Beispielmann", legal_notice=True), "Beispielshop", OWN)
        self.assertEqual(r["category"], "unrelated")


class State(unittest.TestCase):
    def _run(self, st, *rows, today="2026-10-28"):
        return state.merge(st, [classify.classify(r, "Beispielshop", OWN) for r in rows], today)

    def test_neuer_fake_oeffnet_meldung_und_nxdomain_schliesst_sie(self):
        st = state.load(__import__("pathlib").Path("/nicht/vorhanden.json"), "Beispielshop", OWN)
        ch = self._run(st, row("beispielshoppro.shop", asn="AS199242", title="Beispielshop", brand_mentions=9))
        self.assertEqual(ch["new_fakes"], ["beispielshoppro.shop"])
        self.assertEqual(st["domains"]["beispielshoppro.shop"]["takedown"]["status"], "open")
        ch = self._run(st, row("beispielshoppro.shop", dns="NXDOMAIN", http_status=0), today="2026-11-04")
        self.assertEqual(ch["gone"], ["beispielshoppro.shop"])
        self.assertEqual(st["domains"]["beispielshoppro.shop"]["takedown"]["evidence"], "NXDOMAIN am 2026-11-04")

    def test_bestaetigter_fake_wird_nicht_zu_unklar_zurueckgestuft(self):
        st = {"brand": "Beispielshop", "own_domains": OWN, "domains": {}}
        self._run(st, row("beispielshop.fremd.de", title="Beispielshop", brand_mentions=5))
        state.confirm(st, "beispielshop.fremd.de", "fake_live", "Screenshot zeigt Kopie")
        self._run(st, row("beispielshop.fremd.de", title="Beispielshop", brand_mentions=5))
        self.assertEqual(st["domains"]["beispielshop.fremd.de"]["category"], "fake_live")


class StatePageFields(unittest.TestCase):
    def test_keine_antwort_loescht_nicht_den_letzten_beleg(self):
        st = {"brand": "Beispielshop", "own_domains": OWN, "domains": {}}
        live = row("beispielshoppro.shop", asn="AS199242", title="Beispielshop Offiziell", brand_mentions=9, discount=70,
                   registrar_abuse="abuse@registrar.test")
        state.merge(st, [classify.classify(live, "Beispielshop", OWN)], "2026-10-28")
        slow = row("beispielshoppro.shop", asn="AS199242", http_status=0, fetch_error="timed out")
        state.merge(st, [classify.classify(slow, "Beispielshop", OWN)], "2026-10-29")
        e = st["domains"]["beispielshoppro.shop"]
        self.assertEqual((e["title"], e["discount"], e["last_seen_live"]), ("Beispielshop Offiziell", 70, "2026-10-28"))
        self.assertEqual(e["registrar_abuse"], "abuse@registrar.test")
        self.assertEqual(e["category"], "fake_unreachable")


class Takedown(unittest.TestCase):
    def _state(self):
        st = {"brand": "Beispielshop", "own_domains": OWN, "domains": {}}
        for d, reg in [("beispielshoppro.shop", "abuse@registrar.test"), ("beispielshopco.shop", "")]:
            r = classify.classify(row(d, asn="AS199242", title="Beispielshop", brand_mentions=9, host_abuse="abuse@host.test",
                                      registrar_abuse=reg, nameservers=["ns1.cloudflare.com"]), "Beispielshop", OWN)
            state.merge(st, [r], "2026-10-28")
            state.confirm(st, d, "fake_live", "Screenshot zeigt Kopie")
        return st

    def test_cloudflare_formular_nur_wenn_der_shop_hinter_cloudflare_liegt(self):
        pkg = takedown.build(self._state(), {"name": "Test", "org": "Test", "email": "t@test", "on_behalf": False})
        self.assertNotIn("cloudflare", [f["channel"] for f in pkg["forms"]])
        st = self._state()
        st["domains"]["beispielshopco.shop"]["asn"] = "AS13335"
        pkg = takedown.build(st, {"name": "Test", "org": "Test", "email": "t@test", "on_behalf": False})
        cf = next(f for f in pkg["forms"] if f["channel"] == "cloudflare")
        self.assertEqual(cf["domains"], ["beispielshopco.shop"])
        host = next(m for m in pkg["mails"] if m["to"] == "abuse@host.test")
        self.assertEqual(host["domains"], ["beispielshoppro.shop"])

    def test_eine_mail_je_empfaenger_mit_allen_domains(self):
        pkg = takedown.build(self._state(), {"name": "Test", "org": "Test", "email": "t@test", "on_behalf": False})
        host = next(m for m in pkg["mails"] if m["to"] == "abuse@host.test")
        self.assertEqual(sorted(host["domains"]), ["beispielshopco.shop", "beispielshoppro.shop"])
        self.assertEqual(len(pkg["mails"]), 2)

    def test_dynadot_bekommt_formular_statt_mail(self):
        st = self._state()
        st["domains"]["beispielshoppro.shop"]["registrar_abuse"] = "abuse@dynadot.com"
        pkg = takedown.build(st, {"name": "Test", "org": "Test", "email": "t@test", "on_behalf": False})
        self.assertNotIn("abuse@dynadot.com", [m["to"] for m in pkg["mails"]])
        form = next(f for f in pkg["forms"] if f["channel"] == "registrar_form")
        self.assertEqual(form["domains"], ["beispielshoppro.shop"])

    def test_mail_hat_html_fassung_ohne_links(self):
        pkg = takedown.build(self._state(), {"name": "Test", "org": "Test", "email": "t@test", "on_behalf": False})
        html = pkg["mails"][0]["html_body"]
        self.assertIn("https://beispielshop", html)
        self.assertNotIn("<a ", html)

    def test_unbestaetigter_verdacht_wird_nicht_gemeldet(self):
        st = self._state()
        st["domains"]["beispielshopco.shop"]["reviewed"] = False
        pkg = takedown.build(st, {"name": "Test", "org": "Test", "email": "t@test", "on_behalf": False})
        self.assertEqual(pkg["open"], ["beispielshoppro.shop"])

    def test_ohne_auftrag_keine_aussage_im_namen_der_marke(self):
        pkg = takedown.build(self._state(), {"name": "Test", "org": "Test", "email": "t@test", "on_behalf": False})
        body = pkg["mails"][0]["body"]
        self.assertIn("To our knowledge", body)
        self.assertNotIn("On behalf of", body)


class Recheck(unittest.TestCase):
    def test_nxdomain_ist_abgeschaltet_ohne_abruf(self):
        with mock.patch.object(probe, "dns_status", return_value=("NXDOMAIN", "")), mock.patch.object(probe, "fetch") as f:
            self.assertEqual(recheck.check("beispielshoppro.shop", "Beispielshop")["verdict"], "gone")
            f.assert_not_called()

    def test_keine_antwort_bei_aktiver_domain_ist_nicht_abgeschaltet(self):
        with mock.patch.object(probe, "dns_status", return_value=("NOERROR", "192.0.2.1")), \
             mock.patch.object(probe, "fetch", return_value=(0, "", "", "timed out")):
            self.assertEqual(recheck.check("beispielshoppro.shop", "Beispielshop")["verdict"], "unreachable")

    def test_seite_mit_marke_ist_noch_live(self):
        html = "<title>Beispielshop Offiziell</title>"
        with mock.patch.object(probe, "dns_status", return_value=("NOERROR", "192.0.2.1")), \
             mock.patch.object(probe, "fetch", return_value=(200, "https://beispielshoppro.shop/", html, "")):
            self.assertEqual(recheck.check("beispielshoppro.shop", "Beispielshop")["verdict"], "live")


if __name__ == "__main__":
    unittest.main()


class Screens(unittest.TestCase):
    """Ohne Browser: ein Skript, das sich wie Chromium im Container ohne Sandbox verhält."""

    def browser(self, d):
        b = Path(d) / "chrome"
        b.write_text("#!/bin/sh\n"
                     "case \"$*\" in *--no-sandbox*) ;; *) echo 'FATAL: No usable sandbox!' >&2; exit 1;; esac\n"
                     "for a in \"$@\"; do case \"$a\" in --screenshot=*) head -c 6000 /dev/zero > \"${a#--screenshot=}\";; esac; done\n")
        b.chmod(b.stat().st_mode | stat.S_IEXEC)
        return str(b)

    def test_ohne_sandbox_startet_der_browser_ein_zweites_mal(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "x.png"
            self.assertEqual(screens.shoot(self.browser(d), "beispielshop.shop", out), "")
            self.assertTrue(out.exists())

    def test_fehlermeldung_des_browsers_steht_im_ergebnis(self):
        with tempfile.TemporaryDirectory() as d:
            b = Path(d) / "chrome"
            b.write_text("#!/bin/sh\necho 'ERROR: kaputt' >&2\nexit 1\n")
            b.chmod(b.stat().st_mode | stat.S_IEXEC)
            self.assertIn("kaputt", screens.shoot(str(b), "beispielshop.shop", Path(d) / "x.png"))


class ConfirmAndReport(unittest.TestCase):
    def state_with_unclear(self):
        st = {"brand": "Beispielshop", "own_domains": OWN, "domains": {}}
        state.merge(st, [dict(row("beispielshop-gewinn.blog"), category="unclear",
                              category_label=classify.CATEGORIES["unclear"])], "2026-10-29")
        return st

    def test_bestaetigung_zieht_die_beschriftung_nach(self):
        st = self.state_with_unclear()
        entry = state.confirm(st, "beispielshop-gewinn.blog", "fake_live", "Gewinnspiel mit Markenlogo")
        self.assertEqual(entry["category_label"], classify.CATEGORIES["fake_live"])

    def test_erst_beim_ansehen_bestaetigter_fake_steht_als_neu_im_bericht(self):
        from fakeshops import render
        st = self.state_with_unclear()
        state.confirm(st, "beispielshop-gewinn.blog", "fake_live", "Gewinnspiel mit Markenlogo")
        md = render.markdown(st, "2026-10-29", {"new_fakes": [], "gone": []})
        self.assertIn("Neu seit dem letzten Lauf: beispielshop-gewinn.blog", md)


class TakedownRepeat(unittest.TestCase):
    SENDER = {"name": "Test", "org": "Test", "email": "t@test", "on_behalf": False}

    def _state(self, **kw):
        st = {"brand": "Beispielshop", "own_domains": OWN, "domains": {}}
        r = classify.classify(row("beispielshoppro.shop", title="Beispielshop", brand_mentions=9,
                                  host_abuse="abuse@host.test", registrar_abuse="abuse@registrar.test", **kw),
                              "Beispielshop", OWN)
        state.merge(st, [r], "2026-10-28")
        state.confirm(st, "beispielshoppro.shop", "fake_live", "Screenshot zeigt Kopie")
        return st

    def test_gemeldeter_empfaenger_bekommt_keine_zweite_mail(self):
        st = self._state()
        state.reported(st, "beispielshoppro.shop", "email", "abuse@host.test", "2026-10-28")
        pkg = takedown.build(st, self.SENDER)
        self.assertEqual([m["to"] for m in pkg["mails"]], ["abuse@registrar.test"])
        self.assertEqual(pkg["previously_reported"], ["beispielshoppro.shop"])

    def test_wieder_erreichbarer_fake_wird_erneut_gemeldet(self):
        st = self._state()
        state.reported(st, "beispielshoppro.shop", "email", "abuse@host.test", "2026-10-28")
        st["domains"]["beispielshoppro.shop"]["takedown"].update({"status": "open", "reopened_at": "2026-11-05"})
        pkg = takedown.build(st, self.SENDER)
        self.assertIn("abuse@host.test", [m["to"] for m in pkg["mails"]])

    def test_ohne_rabatt_behauptet_die_mail_keinen_rabatt(self):
        pkg = takedown.build(self._state(discount=None), self.SENDER)
        self.assertNotIn("discount", pkg["mails"][0]["body"])
        pkg = takedown.build(self._state(discount=70), self.SENDER)
        self.assertIn("implausible discounts", pkg["mails"][0]["body"])

    def test_unterseite_einer_plattform_geht_nur_an_den_hoster(self):
        st = {"brand": "Beispielshop", "own_domains": OWN, "domains": {}}
        d = "beispielshopofficial.code.blog"
        r = classify.classify(row(d, title="Beispielshop", brand_mentions=9, host_abuse="abuse@platform.test",
                                  registrar_abuse="admin@registry.test"), "Beispielshop", OWN)
        state.merge(st, [r], "2026-10-29")
        state.confirm(st, d, "fake_live", "Gewinnspiel mit Markenlogo")
        pkg = takedown.build(st, self.SENDER)
        self.assertEqual([m["to"] for m in pkg["mails"]], ["abuse@platform.test"])
