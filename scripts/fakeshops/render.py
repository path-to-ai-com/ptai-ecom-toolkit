#!/usr/bin/env python3
"""Bericht eines Laufs: Markdown für die Ablage, HTML mit Screenshots zum Ansehen.

Beides sind Ansichten auf `fakeshops.json`; sie halten keinen eigenen Stand.

CLI:
  python3 -m fakeshops.render --state <fakeshops.json> --run-dir <ordner des laufs> [--changes <changes.json>]
"""
import argparse
import html
import json
import sys
from pathlib import Path

from fakeshops.classify import CATEGORIES

ORDER = list(CATEGORIES)
STATUS = {"open": "Meldung offen", "done": "abgeschaltet", "deferred": "zurückgestellt", "none": ""}


def _rows(state: dict, cats: set) -> list:
    rows = [dict(v, domain=d) for d, v in state["domains"].items() if v.get("category") in cats]
    return sorted(rows, key=lambda r: (ORDER.index(r["category"]), r.get("first_cert", "")))


def markdown(state: dict, run_date: str, changes: dict) -> str:
    fakes = _rows(state, {"fake_live", "fake_pending", "fake_unreachable"})
    gone = _rows(state, {"taken_down"})
    unclear = _rows(state, {"unclear"})
    rest = _rows(state, {"redirect_own", "parked", "unrelated"})
    out = [f"# Fake-Shops {state['brand']}, Lauf {run_date}", "",
           f"Geprüft: {len(state['domains'])} Domains, deren Name mit der Marke beginnt (Zertifikatslogs). "
           f"Live oder im Aufbau: {len(fakes)}. Schon abgeschaltet: {len(gone)}. Unklar: {len(unclear)}.", ""]
    # Neu ist auch, was erst beim Ansehen in diesem Lauf zum Fake wurde; `changes` kennt nur das
    # Vorurteil der Regeln vor dem Ansehen.
    new_fakes = list(dict.fromkeys((changes or {}).get("new_fakes", [])
                                   + [r["domain"] for r in fakes if r.get("first_seen") == run_date]))
    if changes or new_fakes:
        if new_fakes:
            out.append("Neu seit dem letzten Lauf: " + ", ".join(new_fakes))
        if changes.get("gone"):
            out.append("Seit dem letzten Lauf abgeschaltet: " + ", ".join(changes["gone"]))
        out.append("")
    out += ["Links nur ansehen, nichts eingeben und nichts bestellen.", "",
            "## Fake-Shops", "", "| Domain | Stand | Zertifikat seit | Rabatt | Hoster | Meldung | Screenshot |", "|---|---|---|---|---|---|---|"]
    for r in fakes:
        shot = f"screenshots/{r['domain']}.png"
        out.append(f"| https://{r['domain']} | {r['category_label']} | {r.get('first_cert', '')} | "
                   f"{str(r['discount']) + ' %' if r.get('discount') else ''} | {r.get('asn', '')} {r.get('network', '')} | "
                   f"{STATUS[r['takedown']['status']]} | {shot} |")
    out += ["", "## Schon abgeschaltet", "", *[f"- {r['domain']} (Zertifikat seit {r.get('first_cert', '')})" for r in gone], ""]
    out += ["## Unklar, ansehen", "", "| Domain | Befund |", "|---|---|",
            *[f"| {r['domain']} | {'; '.join(r.get('reasons', []))} |" for r in unclear], ""]
    out += ["## Unkritisch", "", *[f"- {r['domain']}: {r['category_label']}, {html.unescape(r.get('title') or '')[:80]}" for r in rest], ""]
    return "\n".join(out)


def overview_html(state: dict, run_date: str) -> str:
    fakes = _rows(state, {"fake_live", "fake_pending", "fake_unreachable"})
    cards = []
    for r in fakes:
        img = f"screenshots/{r['domain']}.png"
        meta = " · ".join(x for x in [f"Zertifikat seit {r.get('first_cert', '')}",
                                       f"Rabatt {r['discount']} %" if r.get("discount") else "",
                                       r.get("network", ""), STATUS[r["takedown"]["status"]]] if x)
        cards.append(f'<article><a href="{img}"><img src="{img}" alt="Screenshot {r["domain"]}" loading="lazy"></a>'
                     f'<div class="meta"><p class="cat">{html.escape(r["category_label"])}</p><h2>{r["domain"]}</h2>'
                     f'<p>{html.escape(meta)}</p><p class="title">{html.escape(html.unescape(r.get("title") or ""))}</p></div></article>')
    gone = "".join(f"<li>{d}</li>" for d, v in sorted(state["domains"].items()) if v.get("category") == "taken_down")
    return f"""<!doctype html><html lang="de"><head><meta charset="utf-8"><title>Fake-Shops {html.escape(state['brand'])}</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;margin:0;background:#f6f6f4;color:#1b1b1b}}
header,section{{max-width:1280px;margin:auto;padding:40px 40px 16px}} h1{{font-size:26px;margin:0 0 8px}} header p{{color:#555;max-width:760px;line-height:1.5}}
main{{display:grid;grid-template-columns:repeat(auto-fill,minmax(360px,1fr));gap:24px;padding:16px 40px 48px;max-width:1280px;margin:auto}}
article{{background:#fff;border-radius:10px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.08)}}
article img{{width:100%;height:300px;object-fit:cover;object-position:top;display:block;border-bottom:1px solid #eee}}
.meta{{padding:16px 18px 20px}} .meta h2{{font-size:17px;margin:2px 0 8px;word-break:break-all}} .meta p{{margin:4px 0;font-size:13px;color:#555}}
.cat{{text-transform:uppercase;letter-spacing:.06em;font-size:11px!important;color:#888!important}} .title{{color:#1b1b1b!important}}
ul{{columns:3;font-size:14px}}
</style></head><body>
<header><h1>Fake-Shops {html.escape(state['brand'])}, {run_date}</h1>
<p>{len(fakes)} Fake-Shops live oder im Aufbau. Klick auf ein Bild öffnet den Screenshot. Die vollständige Liste steht in report.md im selben Ordner.</p></header>
<main>{''.join(cards)}</main>
<section><h2>Schon abgeschaltet</h2><ul>{gone}</ul></section>
</body></html>"""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Bericht eines Laufs")
    ap.add_argument("--state", required=True)
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--changes", default="")
    args = ap.parse_args(argv)
    state = json.loads(Path(args.state).read_text())
    run_dir = Path(args.run_dir)
    run_date = run_dir.name[:10]
    changes = json.loads(Path(args.changes).read_text()) if args.changes else {}
    (run_dir / "report.md").write_text(markdown(state, run_date, changes))
    (run_dir / "overview.html").write_text(overview_html(state, run_date))
    print(f"Bericht in {run_dir}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
