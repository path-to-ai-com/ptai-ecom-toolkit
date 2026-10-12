"""Die Shopify CLI finden, starten und ihre JSON-Ausgabe lesen.

Gemeinsam für Audit und Theme-Migration, damit beide die CLI gleich aufrufen.

**Windows.** npm legt die CLI dort als `shopify.cmd` ab, und `subprocess` ohne
Shell findet sie unter dem bloßen Namen nicht; `find_cli` sucht deshalb über
`shutil.which` und nimmt unter Windows auch `shopify.cmd`. Die Aufrufer lesen
die Ausgabe als UTF-8 (`encoding="utf-8", errors="replace"`), nicht in der
Codepage der Konsole. Steht vor dem JSON eine Fortschritts- oder Warnzeile,
liest `parse_cli_json` das letzte vollständige Objekt oder Array.

Eine Abfrage geht als Datei an die CLI (`--query-file`), nie als Argument:
`shopify.cmd` läuft über `cmd.exe`, und dort beendet ein Zeilenumbruch das
Kommando, und `>` oder `<` außerhalb der Anführungszeichen leiten um.
"""
import json
import os
import re
import shutil
import subprocess

#: Unter Windows startet `subprocess` ohne Shell nur Dateien mit diesen Endungen.
IS_WINDOWS = os.name == "nt"
WINDOWS_RUNNABLE = (".exe", ".cmd", ".bat", ".com")


class ShopifyError(RuntimeError):
    """Eine Abfrage ist gescheitert, gedrosselt geblieben oder unzulässig, oder die CLI fehlt."""


def find_cli(name: str = "shopify") -> str:
    """Voller Pfad der Shopify CLI über `shutil.which`, unter Windows auch `shopify.cmd`.

    Ein Treffer ohne ausführbare Endung ist unter Windows das Shell-Skript, das
    npm neben `shopify.cmd` ablegt; das startet `subprocess` nicht, deshalb wird
    dann weitergesucht.
    """
    candidates = [name]
    if IS_WINDOWS and not name.lower().endswith(WINDOWS_RUNNABLE):
        candidates.append(name + ".cmd")
    for candidate in candidates:
        path = shutil.which(candidate)
        if path and (not IS_WINDOWS or path.lower().endswith(WINDOWS_RUNNABLE)):
            return path
    raise ShopifyError(f"Shopify CLI nicht gefunden ({' oder '.join(candidates)} nicht im PATH); "
                       "installieren mit npm install -g @shopify/cli")


def run_cli(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    """`subprocess.run` mit dem aufgelösten Pfad der CLI an erster Stelle."""
    return subprocess.run([find_cli(cmd[0]), *cmd[1:]], **kwargs)


#: Ein Kandidat beginnt am Anfang einer Zeile, ohne Einrückung. Eingerückte
#: Klammern gehören zum Inneren eines Objekts, und ein Teilobjekt einer
#: abgeschnittenen Antwort darf nie als ganze Antwort gelten.
_JSON_START = re.compile(r"(?:^|(?<=[\r\n]))[\[{]")


def parse_cli_json(text: str):
    """JSON aus der Ausgabe der CLI, auch mit Fortschritts- oder Warnzeilen davor.

    Erst die ganze Ausgabe; scheitert das, das letzte vollständige Objekt oder
    Array, das am Zeilenanfang beginnt. Beginnt danach noch ein Objekt, das
    nicht vollständig ist, ist die Antwort abgeschnitten, und das ist ein
    Fehler statt eines älteren Treffers. `ValueError`, wenn nichts passt.
    """
    try:
        return json.loads(text)
    except ValueError:
        pass
    decoder = json.JSONDecoder()
    found, pos = None, 0
    while (match := _JSON_START.search(text, pos)) is not None:
        start = match.start()
        try:
            value, end = decoder.raw_decode(text, start)
        except ValueError:
            if found is not None and text[start] == "{":
                raise ValueError("Antwort nach dem letzten vollständigen JSON abgeschnitten")
            pos = start + 1
            continue
        found, pos = (value,), end
    if found is None:
        raise ValueError("kein JSON-Objekt in der Ausgabe")
    return found[0]
