"""Der Wochenpuls als Daten: Meldungen und Kennzahlen einer Woche.

Rein, ohne Netz und ohne Dateien. Die Skill `pulse` holt die Zahlen, dieses
Modul entscheidet, was davon eine Meldung ist, und baut `pulse.json`, die das
Cockpit liest (Spec "Wächter und Wirkung" vom 11.10.2026 im Repo
`ptai-portal`, Abschnitt 3).

**Auffällig heißt außerhalb der üblichen Schwankung, nicht über 20 %.** Die
übliche Schwankung einer Kennzahl ist die Spanne ihrer Veränderungen von Woche
zu Woche in den letzten acht Wochen. Bei kleinen Shops schwankt eine Woche schon
durch Zufall um mehrere Prozent, ein fester Satz meldete dort jede zweite Woche.
Vor der achten Woche gibt es kein Band und deshalb keine Meldung zu Kennzahlen,
nur zu Verbindung und Messung.

Vier Arten einer Meldung (`kind`): `connection` (eine Quelle liefert nicht),
`coverage` (GA4 erfasst einen ungewöhnlichen Anteil des Shopify-Umsatzes),
`kpi` (eine Kennzahl liegt außerhalb ihrer Spanne) und `stock` (ausverkauft,
ab Phase 2). Jede Meldung trägt einen Satz der Einordnung; die Begriffe stehen
in der Begriffstabelle der `CLAUDE.md` des Cockpits.

Eine Meldung nennt eine Maßnahme nur als zeitlichen Bezug, nie als Ursache.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

BAND_WEEKS = 8
STALE_HOURS = 36
RELATED_DAYS = 28
KINDS = ("connection", "coverage", "kpi", "stock")
SOURCE_LABEL = {"shopify": "Shopify", "ga4": "Google Analytics", "gsc": "Search Console",
                "google_ads": "Google Ads", "klaviyo": "Klaviyo"}


def week_changes(values: list[float | None]) -> list[float]:
    """Relative Veränderung in Prozent von Woche zu Woche, älteste zuerst.

    Eine Woche ohne Wert oder mit Vorwoche 0 ergibt keine Veränderung; sie
    fällt heraus, statt als 0 % das Band zu verengen.
    """
    out = []
    for prev, cur in zip(values, values[1:]):
        if prev is None or cur is None or prev == 0:
            continue
        out.append((cur / prev - 1) * 100)
    return out


def band(history: list[float | None]) -> tuple[float, float] | None:
    """Übliche Schwankung aus den Wochenwerten vor der aktuellen Woche.

    `history` sind die Werte der Wochen vor der Vorwoche bis einschließlich
    Vorwoche, älteste zuerst. Gebraucht werden acht Veränderungen; weniger
    ergibt kein Band.
    """
    changes = week_changes(history)[-BAND_WEEKS:]
    if len(changes) < BAND_WEEKS:
        return None
    return (min(changes), max(changes))


def classify_kpi(key: str, current: float | None, previous: float | None,
                 history: list[float | None]) -> dict:
    """Eine Kennzahl der Woche: Wert, Vorwoche, Veränderung, Band, Einordnung.

    `history` endet mit der Vorwoche. `state` ist `in_range`, `outside`,
    `no_band` (vor der achten Woche) oder `not_computable` (Wert fehlt oder
    Vorwoche 0).
    """
    row = {"key": key, "value": current, "previous": previous,
           "change": None, "band": None, "state": "not_computable"}
    if current is None or previous in (None, 0):
        return row
    change = (current / previous - 1) * 100
    row["change"] = round(change, 1)
    spread = band(history)
    if spread is None:
        row["state"] = "no_band"
        return row
    row["band"] = [round(spread[0], 1), round(spread[1], 1)]
    row["state"] = "outside" if change < spread[0] or change > spread[1] else "in_range"
    return row


def connection_alerts(sources: dict, now: datetime) -> list[dict]:
    """Je Quelle, die nicht liefert oder älter als 36 Stunden ist, eine Meldung.

    `sources` ist `{quelle: {"ok": bool, "pulled_at": iso | None, "reason": str | None}}`.
    """
    alerts = []
    for source, s in sorted(sources.items()):
        label = SOURCE_LABEL.get(source, source)
        pulled = datetime.fromisoformat(s["pulled_at"]) if s.get("pulled_at") else None
        stale = pulled is not None and now - pulled > timedelta(hours=STALE_HOURS)
        if s.get("ok") and not stale:
            continue
        reason = s.get("reason") or (f"Letzter Stand vom {pulled:%d.%m.%Y}." if stale else None)
        alerts.append({
            "kind": "connection", "source": source,
            "title": f"{label}-Verbindung unterbrochen",
            "text": " ".join(x for x in (
                reason, f"Die Zahlen aus {label} fehlen in diesem Wochenpuls.") if x),
        })
    return alerts


def coverage_alert(ga4_revenue: float | None, shop_net_sales: float | None,
                   history: list[float | None]) -> dict | None:
    """Meldung, wenn GA4 einen ungewöhnlichen Anteil des Shopify-Umsatzes erfasst.

    `history` sind die Anteile (GA4-Kaufumsatz durch Nettoumsatz) der Wochen
    davor, älteste zuerst. Das Band ist ihre Spanne über acht Wochen. Ohne
    Band meldet nur ein Anteil unter 50 %, weil dann sicher Käufe fehlen.
    """
    if not ga4_revenue or not shop_net_sales:
        return None
    share = ga4_revenue / shop_net_sales * 100
    known = [h for h in history if h is not None][-BAND_WEEKS:]
    if len(known) >= BAND_WEEKS:
        lo, hi = min(known), max(known)
        if lo <= share <= hi:
            return None
        usual = f"Üblich sind {lo:.0f} bis {hi:.0f} %."
    elif share >= 50:
        return None
    else:
        usual = "Die übliche Spanne steht ab der 8. Woche fest."
    return {
        "kind": "coverage", "share": round(share, 1),
        "title": f"Google Analytics erfasst {share:.0f} % des Umsatzes",
        "text": (f"{usual} Ist der Anteil zu niedrig, sind Conversion Rate und Kanäle "
                 "aus Google Analytics bis zur Klärung zu niedrig."
                 if share < 100 else
                 f"{usual} Ein Anteil über 100 % deutet auf doppelt erfasste Käufe."),
    }


def related_measures(metric: str, measures: list[dict], week_end: date,
                     days: int = RELATED_DAYS) -> list[dict]:
    """Maßnahmen mit dieser Zielkennzahl, die in den Tagen davor umgesetzt wurden.

    Nur zeitlicher Bezug. Das Datum ist der erste Eintrag `implemented` im
    Verlauf (Format v1 oder je Store in v2, `by_shop`).
    """
    out = []
    for m in measures:
        if m.get("target_metric") != metric:
            continue
        histories = [m.get("history") or []]
        histories += [s.get("history") or [] for s in (m.get("by_shop") or {}).values()]
        dates = [h["date"] for hist in histories for h in hist
                 if h.get("status") == "implemented" and h.get("date")]
        if not dates:
            continue
        done = date.fromisoformat(min(dates))
        if week_end - timedelta(days=days) <= done <= week_end:
            out.append({"id": m["id"], "title": m["title"], "implemented": done.isoformat()})
    return out


def build(*, week_start: date, kpis: dict, sources: dict, measures: list[dict],
          now: datetime, coverage: dict | None = None, labels: dict | None = None) -> dict:
    """Baut `pulse.json`.

    `kpis` ist `{schlüssel: {"value", "previous", "history", "source"}}`;
    `coverage` ist `{"ga4_revenue", "shop_net_sales", "history"}` oder fehlt.
    `labels` übersetzt Schlüssel in die Namen im Cockpit (Vorgabe: Schlüssel).
    """
    week_start = week_start - timedelta(days=week_start.weekday())
    week_end = week_start + timedelta(days=6)
    labels = labels or {}
    rows, alerts = [], connection_alerts(sources, now)
    if coverage:
        alert = coverage_alert(coverage.get("ga4_revenue"), coverage.get("shop_net_sales"),
                               coverage.get("history") or [])
        if alert:
            alerts.append(alert)
    for key, k in kpis.items():
        row = classify_kpi(key, k.get("value"), k.get("previous"), k.get("history") or [])
        row["source"] = k.get("source")
        rows.append(row)
        if row["state"] != "outside":
            continue
        label = labels.get(key, key)
        lo, hi = row["band"]
        alert = {
            "kind": "kpi", "metric": key,
            "title": f"{label} {row['change']:+.0f} % zur Vorwoche".replace(".", ","),
            "text": f"Über der üblichen Schwankung von {lo:+.0f} bis {hi:+.0f} %."
                    if row["change"] > hi else
                    f"Unter der üblichen Schwankung von {lo:+.0f} bis {hi:+.0f} %.",
            "related": related_measures(key, measures, week_end),
        }
        alerts.append(alert)
    iso = week_start.isocalendar()
    return {
        "version": 1,
        "week": f"{iso[0]}-W{iso[1]:02d}",
        "period": {"start": week_start.isoformat(), "end": week_end.isoformat()},
        "created_at": now.isoformat(timespec="minutes"),
        "band_weeks": BAND_WEEKS,
        "alerts": alerts,
        "kpis": rows,
        "sources": sources,
    }


# --- Aus den Abrufen der Skill zum Lauf ------------------------------------

# Acht Veränderungen vor der aktuellen Woche brauchen neun Wochen davor,
# dazu die Puls-Woche selbst.
WEEKS = BAND_WEEKS + 2
LABELS = {"revenue": "Umsatz", "orders": "Bestellungen", "aov": "Bestellwert",
          "sessions": "Sitzungen", "conversion_rate": "Conversion Rate",
          "gsc_clicks": "Klicks aus Google", "gsc_impressions": "Impressionen"}


def week_key(day: date) -> str:
    year, week, _ = day.isocalendar()
    return f"{year}-W{week:02d}"


def week_starts(last_start: date, weeks: int = WEEKS) -> list[date]:
    """Die Montage der letzten `weeks` Wochen, älteste zuerst, `last_start` zuletzt."""
    return [last_start - timedelta(weeks=n) for n in range(weeks - 1, -1, -1)]


def weekly_sums(daily: list[dict], field: str, starts: list[date]) -> list[float | None]:
    """Summe eines Felds je ISO-Woche aus Tageszeilen (`date`, Feld).

    Eine Woche mit weniger als sieben Tagen in den Daten gilt als fehlend:
    eine halbe Woche sähe sonst wie ein Einbruch aus.
    """
    sums: dict[str, float] = {}
    days: dict[str, int] = {}
    for row in daily or []:
        value = row.get(field)
        if value is None or not row.get("date"):
            continue
        key = week_key(date.fromisoformat(row["date"][:10]))
        sums[key] = sums.get(key, 0) + float(value)
        days[key] = days.get(key, 0) + 1
    return [sums[k] if days.get(k) == 7 else None for k in (week_key(s) for s in starts)]


def weekly_field(series: list[dict], field: str, starts: list[date]) -> list[float | None]:
    """Ein Feld aus einer fertigen Wochenreihe (`week`: "2026-W41")."""
    by_week = {r.get("week"): r.get(field) for r in series or []}
    return [by_week.get(week_key(s)) for s in starts]


def ratio(num: list[float | None], den: list[float | None], factor: float = 1) -> list[float | None]:
    return [n / d * factor if n is not None and d else None for n, d in zip(num, den)]


def _kpi(values: list[float | None], source: str) -> dict:
    return {"value": values[-1], "previous": values[-2], "history": values[:-1], "source": source}


def assemble(*, week_start: date, shopify: dict | None, ga4: dict | None, gsc: dict | None,
             measures: list[dict], now: datetime) -> dict:
    """Baut `pulse.json` aus den Snapshots der Skill.

    `shopify` trägt `daily` mit `total_sales`, `net_sales`, `orders`,
    `sessions`; `ga4` trägt `by_week` (Abruf mit `--pulse`); `gsc` trägt
    `daily`. Ein Snapshot mit `error` oder ohne Datei gilt als Verbindung, die
    nicht liefert.
    """
    week_start = week_start - timedelta(days=week_start.weekday())
    starts = week_starts(week_start)
    kpis, sources = {}, {}

    def status(name: str, snap: dict | None) -> bool:
        ok = bool(snap) and not snap.get("error")
        sources[name] = {"ok": ok, "pulled_at": now.isoformat(timespec="minutes") if ok else None,
                         "reason": (snap or {}).get("error") if snap else "Kein Abruf."}
        return ok

    shop_sessions = None
    if status("shopify", shopify):
        daily = shopify.get("daily")
        revenue = weekly_sums(daily, "total_sales", starts)
        orders = weekly_sums(daily, "orders", starts)
        kpis["revenue"] = _kpi(revenue, "Shopify")
        kpis["orders"] = _kpi(orders, "Shopify")
        kpis["aov"] = _kpi(ratio(revenue, orders), "Shopify")
        shop_sessions = weekly_sums(daily, "sessions", starts)
        if any(v is not None for v in shop_sessions):
            kpis["sessions"] = _kpi(shop_sessions, "Shopify")
            kpis["conversion_rate"] = _kpi(ratio(orders, shop_sessions, 100), "Shopify")
    ga4_ok = status("ga4", ga4)
    if ga4_ok and "sessions" not in kpis:
        # Rückfall wie im Monatsreport: Sitzungen und Käufe aus GA4, gesagt
        # über die Quelle.
        sessions = weekly_field(ga4.get("by_week"), "sessions", starts)
        purchases = weekly_field(ga4.get("by_week"), "purchases", starts)
        kpis["sessions"] = _kpi(sessions, "Google Analytics")
        kpis["conversion_rate"] = _kpi(ratio(purchases, sessions, 100), "Google Analytics")
    if status("gsc", gsc):
        kpis["gsc_clicks"] = _kpi(weekly_sums(gsc.get("daily"), "clicks", starts), "Search Console")
        kpis["gsc_impressions"] = _kpi(weekly_sums(gsc.get("daily"), "impressions", starts),
                                       "Search Console")

    # Die Messabdeckung vergleicht GA4-Kaufumsatz mit Shopify-Nettoumsatz.
    # Rechnet die GA4-Property in einer anderen Währung als der Shop (Early
    # Rider EU: GA4 in GBP, Shop in EUR), ist der Anteil sinnlos und entfällt.
    same_currency = not (ga4 and shopify and ga4.get("currency") and shopify.get("currency")
                         and ga4["currency"] != shopify["currency"])
    coverage = None
    if ga4_ok and shopify and not shopify.get("error") and same_currency:
        shares = ratio(weekly_field(ga4.get("by_week"), "purchase_revenue", starts),
                       weekly_sums(shopify.get("daily"), "net_sales", starts), 100)
        coverage = {"ga4_revenue": shares[-1], "shop_net_sales": 100 if shares[-1] else None,
                    "history": shares[:-1]}
    data = build(week_start=week_start, kpis=kpis, sources=sources, measures=measures,
                 now=now, coverage=coverage, labels=LABELS)
    for row in data["kpis"]:
        row["label"] = LABELS.get(row["key"], row["key"])
    # Die Währung des Shops für Umsatz und Bestellwert; ohne Angabe liest das
    # Cockpit EUR.
    if shopify and isinstance(shopify.get("currency"), str):
        data["currency"] = shopify["currency"]
    return data


def run_id_for(now: datetime) -> str:
    """Lauf-ID nach der Konvention `<datum>-<kadenz>` (Spec v1, Abschnitt 9)."""
    return f"{now.date().isoformat()}-week"


def write_run(workspace, data: dict, now: datetime):
    """Legt `reporting/runs/<datum>-week/` mit `pulse.json` und `state.json` an."""
    import json
    from pathlib import Path
    run_id = run_id_for(now)
    run_dir = Path(workspace) / "reporting" / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "pulse.json").write_text(json.dumps(data, ensure_ascii=False, indent=2),
                                        encoding="utf-8")
    week = data["week"].split("-W")[1].lstrip("0")
    (run_dir / "state.json").write_text(json.dumps({
        "run_id": run_id, "cadence": "week", "period": data["period"],
        "title": f"Wochenpuls KW {week}"}, ensure_ascii=False, indent=2), encoding="utf-8")
    return run_dir


def main(argv=None) -> int:
    """Aufruf aus der Skill `pulse`, Schritt 6:

        python3 -m audit.pulse --workspace . --data reporting/data/<heute> \\
            --week-start 2026-10-06
    """
    import argparse
    import json
    from pathlib import Path
    from audit import measures as measures_mod

    parser = argparse.ArgumentParser(description="Wochenpuls aus den Snapshots bauen")
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--data", required=True, help="Ordner mit den -pulse.json")
    parser.add_argument("--week-start", required=True, help="Montag der Puls-Woche")
    args = parser.parse_args(argv)

    def load(name: str) -> dict | None:
        path = Path(args.data) / name
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

    backlog_path = measures_mod.file_path(Path(args.workspace))
    backlog = json.loads(backlog_path.read_text(encoding="utf-8")) if backlog_path.exists() else {}
    now = datetime.now().replace(second=0, microsecond=0)
    data = assemble(week_start=date.fromisoformat(args.week_start),
                    shopify=load("shopify-pulse.json"), ga4=load("ga4-pulse.json"),
                    gsc=load("gsc-pulse.json"), measures=backlog.get("measures") or [], now=now)
    run_dir = write_run(args.workspace, data, now)
    print(f"Wochenpuls {data['week']}: {len(data['alerts'])} Meldungen, Lauf {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
