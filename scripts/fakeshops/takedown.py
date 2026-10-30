#!/usr/bin/env python3
"""Meldepaket für offene Fake-Shops: eine Mail je Empfänger, dazu die Formulare.

Was sich automatisieren lässt, geprüft am 28.10.2026:
- Registrar und Hoster: Abuse-Adresse aus RDAP, Meldung per Mail. Ein
  Empfänger bekommt alle seine Domains in einer Mail, denn die Masche liegt
  meist gebündelt bei einem Hoster.
- Cloudflare: Formular, die API braucht eine eigene Freischaltung (Enterprise
  oder auf Antrag). Cloudflare prüft nur URLs, die auf Cloudflare-IPs zeigen
  (eigene Abuse-Policy). Nutzt ein Fake Cloudflare nur für DNS, liegt er beim
  Hoster, und die Meldung gehört dorthin. Darum nur bei ASN AS13335. Bei solchen
  Shops fehlt der echte Hoster; Cloudflare nennt ihn nach einer vollständigen
  Meldung, danach eine Mail an ihn.
- Google Web Risk Submission API: schließt Fake-Shops ohne Phishing ausdrücklich
  aus. Das öffentliche Formular bleibt als Weg, ohne Zusage.

Diese Datei schreibt nur Texte. Verschickt wird in der Skill über das
Mail-Werkzeug der Session, damit Rückfragen der Abuse-Teams im Postfach des
Absenders landen und nicht bei einer No-Reply-Adresse.

CLI:
  python3 -m fakeshops.takedown --state <fakeshops.json> --out-dir <ordner>
      --sender-name "<Name>" --sender-org "<Firma>" --sender-email <adresse> [--on-behalf]
"""
import argparse
import datetime as dt
import json
import sys
from collections import defaultdict
from pathlib import Path

from fakeshops.candidates import registered_domain

CLOUDFLARE_ASN = "AS13335"

FORMS = {
    "cloudflare": ("Cloudflare Abuse", "https://abuse.cloudflare.com/"),
    "google": ("Google Safe Browsing", "https://safebrowsing.google.com/safebrowsing/report_phish/"),
}

# Registrare, die Meldungen per Mail nicht annehmen, sondern nur über ein Webformular.
# Belegt durch Auto-Replies; ergänzen, sobald ein weiterer so antwortet.
REGISTRAR_FORMS = {
    # Auto-Reply vom 28.10.2026: "we do not accept, nor monitor, abuse reports via email"
    "abuse@dynadot.com": ("Dynadot Abuse", "https://www.dynadot.com/report-abuse"),
}


def open_fakes(state: dict) -> list:
    """Offene Fakes, die im Skill angesehen und bestätigt wurden; Vorurteile der Regeln allein nie."""
    return [dict(v, domain=d) for d, v in sorted(state["domains"].items())
            if v.get("takedown", {}).get("status") == "open" and v.get("reviewed")
            and v.get("category") in ("fake_live", "fake_pending", "fake_unreachable")]


def already_reported(row: dict, channel: str, to: str = "") -> bool:
    """Ob diese Domain auf diesem Weg schon gemeldet ist, seit sie zuletzt wieder erreichbar wurde.

    Bis 29.10.2026 kam jede offene Domain in jedes neue Paket, auch wenn sie beim selben
    Empfänger schon lag; ein zweiter Lauf hätte die Abuse-Teams doppelt angeschrieben.
    Ist ein abgeschalteter Fake wieder online (`reopened_at`), zählen nur Meldungen danach.
    """
    td = row.get("takedown", {})
    since = td.get("reopened_at", "")
    return any(r.get("channel") == channel and r.get("at", "") >= since
               and (not to or r.get("to", "").lower() == to.lower())
               for r in td.get("reports", []))


def evidence_lines(row: dict, own_domains: list) -> list:
    """Belege je Domain, sachlich und nachprüfbar, auf Englisch für internationale Abuse-Teams."""
    lines = [f"- https://{row['domain']}/"]
    seen = f" (seen {row['last_seen_live']})" if row.get("last_seen_live") else ""
    if row.get("title"):
        lines.append(f"  Page title copies the brand{seen}: \"{row['title'][:120]}\"")
        if row.get("legal_notice") is False:
            lines.append("  No company details or legal notice (Impressum) on the site")
    else:
        lines.append("  The page did not load during our checks; same hosting network and naming pattern as the sites above")
    if row.get("discount"):
        lines.append(f"  Typical advertised discount: {row['discount']} %")
    if row.get("first_cert"):
        lines.append(f"  First TLS certificate: {row['first_cert']}")
    if row.get("ip"):
        lines.append(f"  Hosted at {row['ip']} ({row.get('asn', '')} {row.get('network', '')})".rstrip())
    return lines


def message(brand: str, own_domains: list, rows: list, sender: dict, role: str) -> tuple:
    """Betreff und Text einer Meldung an einen Registrar oder Hoster."""
    official = ", ".join(own_domains)
    who = f"On behalf of {brand}" if sender["on_behalf"] else f"To protect customers of {brand}"
    # Nur behaupten, was die Befunde aller gemeldeten Seiten tragen; ein falsches Gewinnspiel ohne
    # Preise ist kein Shop mit Rabatten (PAT-590, 29.10.2026).
    traits = []
    if all(r.get("discount") for r in rows):
        traits.append("present its products at implausible discounts")
    if all(r.get("legal_notice") is False for r in rows):
        traits.append("show no company details or legal notice")
    parts = ["imitate the brand", *traits]
    claim = ", ".join(parts[:-1]) + " and " + parts[-1] if len(parts) > 1 else parts[0]
    action = ("suspend these domains" if len(rows) > 1 else "suspend the domain") if role == "registrar" else "take these sites offline"
    subject = f"Suspected fake sites impersonating {brand}: {len(rows)} domain{'s' if len(rows) > 1 else ''}"
    relation = (f"{brand} does not operate these sites and has not authorised them to sell its products."
                if sender["on_behalf"] else f"To our knowledge, {brand} does not operate or authorise these sites.")
    body = [
        "Hello abuse team,",
        "",
        f"{who}, I am reporting the following websites. They use the brand name {brand} (official shop: {official}) "
        f"to {claim}. " + relation,
        "",
        *[line for r in rows for line in evidence_lines(r, own_domains)],
        "",
        f"Please {action} and preserve the account data for law enforcement. Screenshots and further evidence are "
        "available on request.",
        "",
        "Thank you,",
        sender["name"],
        sender["org"],
        sender["email"],
    ]
    return subject, "\n".join(body)


def html_body(body: str) -> str:
    """Derselbe Text als HTML, Adressen als Klartext.

    Gmail schreibt Links in reinen Textmails beim Versand zu google.com/url-Umleitungen
    um (gesehen am 28.10.2026 in allen neun Meldungen). Ein Abuse-Team, das statt der
    gemeldeten Domain eine Google-Adresse sieht, prüft womöglich die falsche Seite.
    """
    escaped = body.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return "<div>" + escaped.replace("\n", "<br>\n") + "</div>"


def build(state: dict, sender: dict) -> dict:
    rows = open_fakes(state)
    brand, own = state["brand"], state["own_domains"]
    by_recipient = defaultdict(lambda: {"role": "", "rows": []})
    missing = []
    registrar_forms = defaultdict(list)
    reported = []
    for r in rows:
        reg, host = r.get("registrar_abuse", "").lower(), r.get("host_abuse", "").lower()
        if registered_domain(r["domain"]) != r["domain"]:
            # Unterseite auf einer Plattform (etwa name.code.blog bei WordPress.com): Die Domain
            # gehört der Plattform, der Registrar ist nicht zuständig, nur der Hoster.
            reg = ""
        if reg in REGISTRAR_FORMS:
            if not already_reported(r, "registrar_form"):
                registrar_forms[reg].append(r["domain"])
        elif reg and not already_reported(r, "email", reg):
            slot = by_recipient[reg]
            slot["role"] = slot["role"] or "registrar"
            slot["rows"].append(r)
        # Cloudflare ist bei AS13335 nur Proxy; die Meldung geht über das Formular, nicht per Mail.
        if host and r.get("asn") != CLOUDFLARE_ASN and not already_reported(r, "email", host):
            slot = by_recipient[host]
            slot["role"] = slot["role"] or "host"
            slot["rows"].append(r)
        if r.get("takedown", {}).get("reports"):
            reported.append(r["domain"])
        if not r.get("registrar_abuse") and not r.get("host_abuse"):
            missing.append(r["domain"])
    mails = []
    for to, slot in sorted(by_recipient.items()):
        if not slot["rows"]:
            continue
        uniq = list({r["domain"]: r for r in slot["rows"]}.values())
        subject, body = message(brand, own, uniq, sender, slot["role"])
        mails.append({"channel": "email", "role": slot["role"], "to": to, "subject": subject, "body": body,
                      "html_body": html_body(body), "domains": [r["domain"] for r in uniq]})
    forms = []
    for addr, domains in sorted(registrar_forms.items()):
        name, url = REGISTRAR_FORMS[addr]
        forms.append({"channel": "registrar_form", "name": name, "url": url, "domains": domains,
                      "note": "Registrar nimmt keine Mail an; Begründung aus dem Mailtext übernehmen, Captcha löst der Mensch"})
    cf_domains = [r["domain"] for r in rows if r.get("asn") == CLOUDFLARE_ASN and not already_reported(r, "cloudflare")]
    if cf_domains:
        forms.append({"channel": "cloudflare", "name": FORMS["cloudflare"][0], "url": FORMS["cloudflare"][1], "domains": cf_domains,
                      "note": "Typ Phishing; mehrere URLs je Meldung möglich; im Kommentar um den Namen des Hosters bitten"})
    google = [r["domain"] for r in rows if not already_reported(r, "google")]
    if google:
        forms.append({"channel": "google", "name": FORMS["google"][0], "url": FORMS["google"][1], "domains": google,
                      "note": "eine URL je Meldung, dazu ein Kommentar; das Häkchen gegen Roboter setzt ein Mensch. Wirkung ohne Zusage: Google warnt im Browser, nimmt aber nichts vom Netz"})
    return {"brand": brand, "built_at": dt.datetime.now().isoformat(timespec="seconds"), "sender": sender,
            "open": [r["domain"] for r in rows], "previously_reported": reported, "mails": mails, "forms": forms,
            "missing_contacts": missing}


def render_md(pkg: dict) -> str:
    out = [f"# Meldepaket Fake-Shops {pkg['brand']}, {pkg['built_at'][:10]}", "",
           f"Offene Fake-Shops: {len(pkg['open'])}. Mails: {len(pkg['mails'])}. Formulare: {len(pkg['forms'])}.", ""]
    if pkg.get("previously_reported"):
        out += ["Schon gemeldet, nur noch fehlende Wege im Paket: " + ", ".join(pkg["previously_reported"]), ""]
    if pkg["missing_contacts"]:
        out += ["Ohne Abuse-Adresse (nur Formulare): " + ", ".join(pkg["missing_contacts"]), ""]
    for m in pkg["mails"]:
        out += [f"## Mail an {m['to']} ({'Registrar' if m['role'] == 'registrar' else 'Hoster'})", "",
                f"Betreff: {m['subject']}", "", "```", m["body"], "```", ""]
    for f in pkg["forms"]:
        out += [f"## Formular {f['name']}", "", f"{f['url']}", "", f"Hinweis: {f['note']}", "",
                *[f"- https://{d}/" for d in f["domains"]], ""]
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Meldepaket für offene Fake-Shops")
    ap.add_argument("--state", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--sender-name", required=True)
    ap.add_argument("--sender-org", required=True)
    ap.add_argument("--sender-email", required=True)
    ap.add_argument("--on-behalf", action="store_true", help="nur mit Auftrag der Marke")
    args = ap.parse_args(argv)
    state = json.loads(Path(args.state).read_text())
    sender = {"name": args.sender_name, "org": args.sender_org, "email": args.sender_email, "on_behalf": args.on_behalf}
    pkg = build(state, sender)
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "takedown.json").write_text(json.dumps(pkg, indent=1, ensure_ascii=False))
    (out / "takedown.md").write_text(render_md(pkg))
    print(f"{len(pkg['open'])} offen, {len(pkg['mails'])} Mails, {len(pkg['forms'])} Formulare in {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
