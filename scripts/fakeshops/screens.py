#!/usr/bin/env python3
"""Screenshot der Startseite je Fake-Shop, als Beleg für Ansicht und Meldung.

Gemessen am 28.10.2026: Die Fake-Shops brechen mit Chromium per HTTP/2 ab
(ERR_HTTP2_PROTOCOL_ERROR). Mit `--disable-http2` laden sie. Der Browser kommt
aus `scripts/lib/find_chrome.sh`, bevorzugt die Headless Shell von Playwright;
das installierte Google Chrome fragt headless den Schlüsselbund ab und hängt.

CLI:
  python3 -m fakeshops.screens --out-dir <ordner> <domain> [<domain> ...]
"""
import argparse
import subprocess
import sys
from pathlib import Path

from fakeshops.probe import UA

FIND_CHROME = Path(__file__).resolve().parent.parent / "lib" / "find_chrome.sh"


def find_browser() -> str:
    res = subprocess.run(["bash", "-c", f'. "{FIND_CHROME}"; find_chrome'], capture_output=True, text=True)
    return res.stdout.strip() if res.returncode == 0 else ""


def shoot(browser: str, domain: str, out: Path, timeout: int = 120, sandbox: bool = True) -> str:
    """Ein Screenshot 1280 x 1400. Gibt einen Fehlertext zurück, leer bei Erfolg.

    Im Container der Paperclip-Agents gibt es keine Chromium-Sandbox; der Browser bricht dann
    mit "No usable sandbox!" ab (belegt in PAT-590, 29.10.2026). Nur in diesem Fall startet
    derselbe Aufruf ein zweites Mal mit `--no-sandbox`, wie das Screenshot-Werkzeug des Containers.
    """
    cmd = [browser, "--headless", "--disable-gpu", "--hide-scrollbars", "--disable-http2", "--window-size=1280,1400",
           f"--user-agent={UA}", "--virtual-time-budget=10000", f"--screenshot={out}", f"https://{domain}/"]
    if not sandbox:
        cmd.insert(1, "--no-sandbox")
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=out.parent)
    except subprocess.TimeoutExpired:
        return f"Zeitüberschreitung nach {timeout} s"
    if sandbox and "No usable sandbox" in (res.stderr or ""):
        return shoot(browser, domain, out, timeout, sandbox=False)
    if not out.exists() or out.stat().st_size < 5000:
        fatal = next((l for l in (res.stderr or "").splitlines() if "FATAL" in l or "ERROR" in l), "")
        return "kein Bild oder leere Seite" + (f" ({fatal[-160:]})" if fatal else "")
    return ""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Screenshots der Fake-Shops")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("domains", nargs="+")
    args = ap.parse_args(argv)
    browser = find_browser()
    if not browser:
        print("kein headless Browser gefunden (scripts/lib/find_chrome.sh)", file=sys.stderr)
        return 2
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    failed = 0
    for d in args.domains:
        err = shoot(browser, d, out_dir / f"{d}.png")
        print(f"{'FEHLER' if err else 'ok'} {d} {err}".strip(), file=sys.stderr)
        failed += bool(err)
    return failed


if __name__ == "__main__":
    sys.exit(main())
