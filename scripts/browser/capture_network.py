"""Netzwerk-Mitschnitt je Beispielseite: jede Anfrage samt iframes und Workern, Cookies, Speicher, neue Globals.

Aufruf:

  uv run --quiet --with playwright==1.58.0 python scripts/browser/capture_network.py \
    --pages migration/inventory/pages.json --out <ordner> \
    [--theme <theme-id>] [--consent declined|accepted] [--runs 2] [--devices desktop,mobile] \
    [--only home,product] [--wait 8000]

Schreibt `<ordner>/network.json` und je Seite und Gerät beim ersten Durchlauf das
HTML nach `<ordner>/html/<id>-<gerät>-1.html` (für `theme.apps scan --html`).
Auf stdout eine Zusammenfassung als JSON-Zeile. Exit 0 alles gültig, 1 mindestens
ein Aufruf mit falschem Theme, Fehler oder einem Dialog, der sich nicht bedienen
ließ, 2 Fehler vor dem ersten Aufruf.

**Von den Spuren aus, nicht nach Namen.** Erfasst wird, was der Browser wirklich
lädt und sendet, nicht was man zu finden erwartet:

- jede Anfrage des Kontexts mit Methode, Typ, Status, Rahmen und, bei POST, dem
  gekürzten Inhalt; dazu die Anfragen der Worker und Service Worker,
- jeder Rahmen mit Elternrahmen, die Worker,
- Cookies (Name, Domain, Ablauf, keine Werte), local- und sessionStorage je
  Rahmen (nur Schlüssel),
- neue `window`-Globals gegenüber einer leeren Seite derselben Herkunft,
- der Consent-Zustand (`Shopify.customerPrivacy`, `google_tag_data.ics`).

Jede Anfrage trägt `consent_phase`: `pre` bis zum Klick im Cookie-Dialog, danach
`post`. Abgelehnt wird standardmäßig; zugestimmt nur mit `--consent accepted`,
und das nur, wenn das Team den Mitschnitt mit Einwilligung freigegeben hat.

Je Seite und Gerät läuft ein frischer Kontext, bis zum Seitenende gescrollt, mit
Wartezeit, standardmäßig zweimal. Kasse und Dankeseite gehören nicht dazu; dort
sieht man Pixel nur mit einer Testbestellung.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import common  # noqa: E402

#: So viel vom Inhalt einer POST-Anfrage bleibt stehen; genug für Event-Namen.
MAX_POST = 4000
MAX_URL = 2000

SNAPSHOT_JS = r"""() => {
  const keys = store => { try { const out = []; for (let i = 0; i < store.length; i++) out.push(store.key(i)); return out; }
                          catch (e) { return null; } };
  return {url: location.href, local: keys(window.localStorage), session: keys(window.sessionStorage)};
}"""

STATE_JS = r"""() => {
  const out = {};
  try { out.customer_privacy = window.Shopify && Shopify.customerPrivacy && Shopify.customerPrivacy.currentVisitorConsent
          ? Shopify.customerPrivacy.currentVisitorConsent() : null; } catch (e) { out.customer_privacy = String(e); }
  try { out.google_consent = window.google_tag_data && google_tag_data.ics && google_tag_data.ics.entries
          ? JSON.parse(JSON.stringify(google_tag_data.ics.entries)) : null; } catch (e) { out.google_consent = null; }
  try { out.gtm_containers = window.google_tag_manager ? Object.keys(window.google_tag_manager) : []; } catch (e) {}
  out.globals = Object.getOwnPropertyNames(window);
  return out;
}"""


def request_record(request, phase: str, started: float) -> dict:
    """Eine Anfrage als Zeile; ein Worker hat keinen Rahmen, das ist kein Fehler."""
    try:
        frame_url = request.frame.url
    except Exception:
        frame_url = None
    record = {
        "t": round(time.time() - started, 2),
        "url": request.url[:MAX_URL],
        "method": request.method,
        "resource_type": request.resource_type,
        "frame_url": frame_url[:600] if frame_url else None,
        "consent_phase": phase,
        "status": None,
        "failure": None,
    }
    worker = getattr(request, "service_worker", None)
    if worker is not None:
        try:
            record["service_worker"] = worker.url[:600]
        except Exception:
            pass
    if request.method != "GET":
        try:
            body = request.post_data
        except Exception:
            body = None
        if body:
            record["post_data"] = body[:MAX_POST]
    return record


def capture_page(playwright, browsers: dict, job: dict) -> dict:
    device, page_info = job["device"], job["page"]
    browser = common.browser_for(playwright, browsers, device)
    options = common.context_options(playwright, device, job["locale"])
    baselines = job["baselines"]
    engine = common.ENGINE[device]
    if engine not in baselines:
        baselines[engine] = common.baseline_globals(browser, options, job["base_url"])

    url = common.page_url(job["base_url"], page_info["path"], job["theme"], hide_bar=bool(job["theme"]))
    context = browser.new_context(**options)
    started = time.time()
    phase = {"value": "pre"}
    requests: list[dict] = []
    by_request: dict = {}

    def on_request(request):
        record = request_record(request, phase["value"], started)
        requests.append(record)
        by_request[request] = record

    def on_response(response):
        record = by_request.get(response.request)
        if record is not None:
            record["status"] = response.status

    def on_failed(request):
        record = by_request.get(request)
        if record is not None:
            record["failure"] = (request.failure or "failed")[:200]

    context.on("request", on_request)
    context.on("response", on_response)
    context.on("requestfailed", on_failed)
    result = {"page_id": page_info["id"], "template": page_info.get("template"), "path": page_info["path"],
              "url": url, "device": device, "browser": engine, "run": job["run"], "consent": job["consent"],
              "state": "ok", "error": None}
    try:
        page = context.new_page()
        response = page.goto(url, wait_until="load", timeout=job["timeout"])
        result["status"] = response.status if response else None
        page.wait_for_timeout(1500)
        theme = common.check_theme(common.theme_in_page(page), job["theme"])
        result["theme_check"] = theme
        if theme["state"] != "ok":
            result["state"] = "wrong_theme"
        result["consent_result"] = common.handle_consent(
            page, job["consent"], before_click=lambda: phase.__setitem__("value", "post"))
        common.scroll_to_end(page)
        page.wait_for_timeout(job["wait"])
        result["final_url"] = page.url
        frames, local, session = [], {}, {}
        for frame in page.frames:
            entry = {"url": frame.url[:600], "parent_url": frame.parent_frame.url[:600] if frame.parent_frame else None}
            try:
                snap = frame.evaluate(SNAPSHOT_JS)
                origin = snap["url"].split("/", 3)[:3]
                origin = "/".join(origin) if snap["url"].startswith("http") else snap["url"][:60]
                if snap.get("local"):
                    local.setdefault(origin, set()).update(snap["local"])
                if snap.get("session"):
                    session.setdefault(origin, set()).update(snap["session"])
            except Exception as exc:
                entry["error"] = str(exc)[:160]
            frames.append(entry)
        result["frames"] = frames
        result["local_storage"] = {k: sorted(v) for k, v in local.items()}
        result["session_storage"] = {k: sorted(v) for k, v in session.items()}
        try:
            state = page.evaluate(STATE_JS)
            globals_ = set(state.pop("globals") or [])
            result["new_globals"] = sorted(globals_ - set(baselines.get(engine) or []))
            result["privacy"] = state
        except Exception as exc:
            result["privacy"] = {"error": str(exc)[:200]}
            result["new_globals"] = []
        result["workers"] = [worker.url[:600] for worker in page.workers]
        try:
            result["service_workers"] = [worker.url[:600] for worker in context.service_workers]
        except Exception:
            result["service_workers"] = []
        result["cookies"] = [{"name": c["name"], "domain": c["domain"], "expires": c.get("expires"),
                              "http_only": c.get("httpOnly"), "secure": c.get("secure"),
                              "same_site": c.get("sameSite")} for c in context.cookies()]
        if job["run"] == 1:
            html_path = job["html_dir"] / f"{page_info['id']}-{device}-1.html"
            html_path.write_text(page.content(), encoding="utf-8")
            result["html_file"] = f"html/{html_path.name}"
    except Exception as exc:
        result["state"] = "error"
        result["error"] = f"{type(exc).__name__}: {exc}"[:500]
    finally:
        result["requests"] = requests
        result["seconds"] = round(time.time() - started, 1)
        context.close()
    return result


def build_jobs(pages: dict, devices: list[str], runs: int, args, html_dir: Path, baselines: dict) -> list[dict]:
    jobs = []
    for page in pages["pages"]:
        for device in devices:
            for run in range(1, runs + 1):
                jobs.append({"page": page, "page_id": page["id"], "device": device, "run": run,
                             "base_url": pages["base_url"], "theme": args.theme, "consent": args.consent,
                             "wait": args.wait, "timeout": args.timeout, "locale": args.locale,
                             "html_dir": html_dir, "baselines": baselines})
    return jobs


def summarize(runs: list[dict]) -> dict:
    return {
        "runs": len(runs),
        "ok": sum(1 for r in runs if r.get("state") == "ok"),
        "wrong_theme": sum(1 for r in runs if r.get("state") == "wrong_theme"),
        "errors": sum(1 for r in runs if r.get("state") == "error"),
        "consent_stuck": sum(1 for r in runs if (r.get("consent_result") or {}).get("result") == "stuck"),
        "requests": sum(len(r.get("requests") or []) for r in runs),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Netzwerk-Mitschnitt je Beispielseite")
    parser.add_argument("--pages", required=True, help="pages.json")
    parser.add_argument("--out", required=True, help="Zielordner für network.json und html/")
    parser.add_argument("--theme", help="Theme-ID für preview_theme_id; ohne sie das Live-Theme")
    parser.add_argument("--consent", choices=("declined", "accepted"), default="declined",
                        help="accepted nur nach Freigabe des Teams")
    parser.add_argument("--runs", type=int, default=2, help="Durchläufe je Seite und Gerät")
    parser.add_argument("--devices", default="desktop,mobile", help="desktop, mobile oder beide")
    parser.add_argument("--only", help="nur diese Seiten-IDs, kommagetrennt")
    parser.add_argument("--wait", type=int, default=8000, help="Wartezeit nach dem Scrollen in ms")
    parser.add_argument("--timeout", type=int, default=60000, help="Zeitlimit für das Laden in ms")
    parser.add_argument("--locale", default="de-DE")
    parser.add_argument("--parallel", type=int, default=common.MAX_PARALLEL, help="höchstens 2")
    args = parser.parse_args(argv)

    try:
        pages = common.load_pages(args.pages, common.parse_list(args.only))
        devices = common.parse_list(args.devices, common.DEVICES) or list(common.DEVICES)
    except (common.PagesError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 2
    # Ohne diese Variable meldet Playwright die Anfragen der Service Worker nicht.
    os.environ.setdefault("PW_EXPERIMENTAL_SERVICE_WORKER_NETWORK_EVENTS", "1")
    try:
        import playwright  # noqa: F401
    except ImportError:
        print(json.dumps({"error": common.PLAYWRIGHT_MISSING}, ensure_ascii=False))
        return 2

    out = Path(args.out)
    html_dir = out / "html"
    html_dir.mkdir(parents=True, exist_ok=True)
    baselines: dict = {}
    jobs = build_jobs(pages, devices, max(1, args.runs), args, html_dir, baselines)
    started = common.now()
    results = common.run_jobs(jobs, capture_page, args.parallel)
    runs = []
    for job, result in zip(jobs, results):
        if result.get("job") is not None:
            # Fehler vor dem ersten Aufruf der Seite: trotzdem als Zeile, nie still weg.
            result = {"page_id": job["page_id"], "template": job["page"].get("template"), "path": job["page"]["path"],
                      "device": job["device"], "browser": common.ENGINE[job["device"]], "run": job["run"],
                      "consent": job["consent"], "state": "error", "error": result.get("error"), "requests": []}
        runs.append(result)
    data = {"tool": "capture_network", "base_url": pages["base_url"], "theme_id": args.theme,
            "consent_mode": args.consent, "captured_at": started, "devices": devices, "runs_per_page": args.runs,
            "baseline_globals": baselines, "runs": runs}
    common.write_json(out / "network.json", data)
    summary = summarize(runs)
    print(json.dumps({"out": str(out / "network.json"), **summary}, ensure_ascii=False))
    return 0 if summary["ok"] == summary["runs"] and not summary["consent_stuck"] else 1


if __name__ == "__main__":
    sys.exit(main())
