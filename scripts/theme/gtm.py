"""Einen Google-Tag-Manager-Container vollständig auflösen.

Aufruf:

  PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m theme.gtm resolve \
    --gtm <gtm.js> --out <gtm.json>

Die Datei `gtm.js?id=GTM-…` enthält ein Objekt `var data = {"resource": …}` mit
`tags`, `macros`, `predicates` und `rules`. Daraus wird je Tag: Funktion
(`__googtag`, `__gaawe`, `__awct`, `__html`, …), Parameter mit aufgelösten
Makros, Auslöser als lesbare Bedingungen, Events aus den Auslösern, Consent-
Einstellung und die Messziele, an die der Tag schickt.

**Nur nach Kennungen zu suchen reicht nicht.** Ein Container kann Dutzende Tags
tragen, darunter Werbe-Pixel in eigenem HTML und eine Google-Ads-Kennung als
nackte Zahl ohne `AW-`. Erst das Auflösen zeigt, welche Dienste der Container
lädt und welcher davon ein eigenes Ziel bedient. Wird der Tag Manager im neuen
Theme entfernt, braucht jeder dieser Tags einen eigenen Weg.

Das Format von `gtm.js` ist von Google nicht als Schnittstelle dokumentiert. Was
hier nicht erkannt wird, bleibt mit seinem Rohnamen stehen (`__xyz#12`), nie
geraten. Exit 0 fertig, 2 Fehler (kein Container in der Datei).

Nur Standardbibliothek.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from theme import tracking_ids  # noqa: E402

#: So tief werden verschachtelte Makros aufgelöst; tiefer steht "…".
MAX_DEPTH = 8
#: Eigenes JavaScript und HTML wird für die Ausgabe gekürzt, nicht für die Suche.
MAX_CODE = 400

#: Bekannte Tag-Funktionen: Dienst und Zweck. Unbekannte bleiben mit Rohnamen.
TAG_FUNCTIONS = {
    "__googtag": ("google_tag", "Google-Tag (Konfiguration)"),
    "__gaawe": ("google_analytics", "GA4-Event"),
    "__gaawc": ("google_analytics", "GA4-Konfiguration (alt)"),
    "__ua": ("google_analytics", "Universal Analytics"),
    "__awct": ("google_ads", "Google-Ads-Conversion"),
    "__sp": ("google_ads", "Google-Ads-Remarketing"),
    "__gclidw": ("google_ads", "Conversion-Linker"),
    "__awcc": ("google_ads", "Google-Ads-Nutzerdaten"),
    "__flc": ("google_marketing_platform", "Floodlight-Zähler"),
    "__fls": ("google_marketing_platform", "Floodlight-Verkauf"),
    "__baut": ("microsoft_ads", "Microsoft-Advertising-UET"),
    "__hjtc": ("hotjar", "Hotjar"),
    "__html": (None, "eigenes HTML"),
    "__img": (None, "eigenes Bild-Pixel"),
    "__paused": (None, "pausierter Tag"),
}

#: Eingebaute Auslöser-Events des Tag Managers und was sie bedeuten.
BUILTIN_EVENTS = {
    "gtm.js": "Seitenaufruf (Container geladen)",
    "gtm.dom": "DOM bereit",
    "gtm.load": "Fenster geladen",
    "gtm.init": "Initialisierung",
    "gtm.init_consent": "Consent-Initialisierung",
    "gtm.click": "Klick",
    "gtm.linkClick": "Link-Klick",
    "gtm.formSubmit": "Formular abgeschickt",
    "gtm.historyChange": "Verlaufswechsel",
    "gtm.historyChange-v2": "Verlaufswechsel",
    "gtm.scrollDepth": "Scrolltiefe",
    "gtm.timer": "Timer",
    "gtm.video": "Video",
    "gtm.elementVisibility": "Element sichtbar",
}


class ContainerError(Exception):
    """Die Datei enthält keinen lesbaren Container."""


def extract_balanced(text: str, start: int) -> str:
    """Das JSON-Objekt oder -Array, das bei `start` beginnt, bis zur passenden Klammer.

    Zeichenketten werden beachtet, damit eine Klammer in einem String nicht
    zählt. Wirft `ValueError`, wenn bei `start` keine Klammer steht oder sie nicht
    schließt.
    """
    if start >= len(text) or text[start] not in "{[":
        raise ValueError("keine öffnende Klammer")
    pairs = {"{": "}", "[": "]"}
    stack = []
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char in pairs:
            stack.append(pairs[char])
        elif char in "}]":
            if not stack or stack.pop() != char:
                raise ValueError("Klammern passen nicht")
            if not stack:
                return text[start:index + 1]
    raise ValueError("Klammer schließt nicht")


def parse_container(text: str) -> dict:
    """Das Objekt `data` aus `gtm.js`; wirft `ContainerError`, wenn keins da ist."""
    match = re.search(r"var\s+data\s*=\s*\{", text)
    if not match:
        raise ContainerError("kein 'var data = {' in der Datei, ist das eine gtm.js?")
    try:
        data = json.loads(extract_balanced(text, match.end() - 1))
    except ValueError as exc:
        raise ContainerError(f"Container nicht lesbar: {exc}") from exc
    if not isinstance(data.get("resource"), dict):
        raise ContainerError("Container ohne 'resource'")
    return data


class _Resolver:
    def __init__(self, resource: dict):
        self.macros = resource.get("macros") or []
        self.predicates = resource.get("predicates") or []

    def macro(self, index, depth: int):
        if not isinstance(index, int) or index >= len(self.macros):
            return f"macro#{index}"
        macro = self.macros[index] or {}
        function = macro.get("function", "")
        if function == "__c":
            return self.render(macro.get("vtp_value"), depth + 1)
        if function == "__v":
            return f"dl:{self.render(macro.get('vtp_name'), depth + 1)}"
        if function == "__j":
            return f"js:{self.render(macro.get('vtp_name'), depth + 1)}"
        if function == "__k":
            return f"cookie:{self.render(macro.get('vtp_name'), depth + 1)}"
        if function == "__e":
            return "event"
        if function == "__u":
            return f"url:{macro.get('vtp_component', '')}".rstrip(":")
        if function == "__f":
            return "referrer"
        if function == "__cid":
            return "container_id"
        if function == "__jsm":
            code = str(self.render(macro.get("vtp_javascript"), depth + 1))
            return f"custom_js#{index}:{code[:MAX_CODE]}"
        if function in ("__smm", "__remm"):
            return {
                "lookup": f"#{index}",
                "input": self.render(macro.get("vtp_input"), depth + 1),
                "map": self.render(macro.get("vtp_map"), depth + 1),
                "default": self.render(macro.get("vtp_defaultValue"), depth + 1),
            }
        return f"{function}#{index}"

    def render(self, value, depth: int = 0):
        """Ein Wert aus dem Container in lesbarer Form, Makros aufgelöst."""
        if depth > MAX_DEPTH:
            return "…"
        if isinstance(value, list) and value and isinstance(value[0], str):
            head = value[0]
            if head == "macro" and len(value) > 1:
                return self.macro(value[1], depth)
            if head == "list":
                return [self.render(item, depth + 1) for item in value[1:]]
            if head == "map":
                items = value[1:]
                return {str(self.render(items[n], depth + 1)): self.render(items[n + 1], depth + 1)
                        for n in range(0, len(items) - 1, 2)}
            if head in ("escape", "zb") and len(value) > 1:
                return self.render(value[1], depth + 1)
            if head == "template":
                return "".join(str(self.render(item, depth + 1)) for item in value[1:])
            if head == "tag" and len(value) > 1:
                return f"tag#{value[1]}"
        if isinstance(value, list):
            return [self.render(item, depth + 1) for item in value]
        return value

    def predicate(self, index) -> dict:
        if not isinstance(index, int) or index >= len(self.predicates):
            return {"text": f"predicate#{index}"}
        raw = self.predicates[index] or {}
        arg0 = self.render(raw.get("arg0"))
        arg1 = self.render(raw.get("arg1"))
        extra = {k: v for k, v in raw.items() if k not in ("function", "arg0", "arg1")}
        text = f"{arg0} {raw.get('function', '?')} {arg1}"
        if extra:
            text += " " + json.dumps(extra, ensure_ascii=False, sort_keys=True)
        out = {"text": text, "function": raw.get("function"), "arg0": arg0, "arg1": arg1}
        if extra:
            out["flags"] = extra
        return out


def _events_of(conditions: list[dict]) -> list[str]:
    """Event-Namen aus den Bedingungen eines Auslösers (`event _eq purchase`)."""
    events = []
    for condition in conditions:
        if condition.get("arg0") == "event" and condition.get("function") in ("_eq", "_re", "_sw", "_cn"):
            if isinstance(condition.get("arg1"), str) and not condition.get("flags"):
                events.append(condition["arg1"])
    return events


def _strings(value):
    if isinstance(value, dict):
        for child in value.values():
            yield from _strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from _strings(child)
    elif isinstance(value, (str, int)) and not isinstance(value, bool):
        yield str(value)


def _tag_targets(function: str, params: dict) -> list[dict]:
    """Messziele eines Tags: aus allen Parametern, dazu die nackten Kennungen.

    `__awct` und `__sp` tragen die Google-Ads-Kennung oft als blanke Zahl in
    `conversionId`, ohne `AW-`; `__baut` die UET-Kennung in `tagId`.
    """
    text = "\n".join(_strings(params))
    targets = tracking_ids.find_targets(text)
    known = {t["target_id"] for t in targets}
    if function in ("__awct", "__sp", "__awcc"):
        conversion_id = str(params.get("conversionId") or "").strip()
        if re.fullmatch(r"\d{6,12}", conversion_id):
            label = params.get("conversionLabel")
            item = {"target_id": f"AW-{conversion_id}", "kind": "google_ads"}
            if isinstance(label, str) and label:
                item["label"] = label
            if item["target_id"] not in known:
                targets.append(item)
                known.add(item["target_id"])
            else:
                for target in targets:
                    if target["target_id"] == item["target_id"] and "label" in item:
                        target.setdefault("label", item["label"])
    if function == "__baut":
        tag_id = str(params.get("tagId") or "").strip()
        if re.fullmatch(r"\d{4,12}", tag_id) and f"UET:{tag_id}" not in known:
            targets.append({"target_id": f"UET:{tag_id}", "kind": "uet"})
    return targets


def resolve(data: dict) -> dict:
    """Je Tag Funktion, Parameter, Auslöser, Events, Consent und Messziele."""
    resource = data["resource"]
    resolver = _Resolver(resource)
    tags = resource.get("tags") or []

    triggers: dict[int, list[dict]] = {}
    for rule in resource.get("rules") or []:
        conditions, adds, blocks = [], [], []
        for part in rule or []:
            if not part:
                continue
            head, rest = part[0], part[1:]
            if head == "if":
                conditions += [{**resolver.predicate(i), "negated": False} for i in rest]
            elif head == "unless":
                conditions += [{**resolver.predicate(i), "negated": True} for i in rest]
            elif head == "add":
                adds += rest
            elif head == "block":
                blocks += rest
        positive = [c for c in conditions if not c["negated"]]
        readable = [("NICHT " if c["negated"] else "") + c["text"] for c in conditions]
        for index in adds:
            triggers.setdefault(index, []).append(
                {"fires_when": readable, "events": _events_of(positive)})
        for index in blocks:
            triggers.setdefault(index, []).append(
                {"blocked_when": readable, "events": _events_of(positive)})

    out = []
    for index, tag in enumerate(tags):
        function = tag.get("function", "")
        params = {key[4:]: resolver.render(value) for key, value in tag.items() if key.startswith("vtp_")}
        for key in ("html", "javascript"):
            if isinstance(params.get(key), str) and len(params[key]) > MAX_CODE:
                params[f"{key}_length"] = len(params[key])
        service, purpose = TAG_FUNCTIONS.get(function, (None, None))
        if function.startswith("__cvt_"):
            purpose = "Community-Vorlage"
        own_triggers = triggers.get(index, [])
        events = sorted({e for t in own_triggers if "fires_when" in t for e in t["events"]})
        if function == "__gaawe" and isinstance(params.get("eventName"), str):
            events = sorted(set(events) | {params["eventName"]})
        if function == "__googtag" and "send_page_view" not in json.dumps(params) and events:
            # Der Google-Tag schickt beim Laden einen page_view, solange send_page_view
            # nicht abgeschaltet ist; das Event steht nirgends im Container.
            events = sorted(set(events) | {"page_view"})
        if function == "__html" and isinstance(params.get("html"), str):
            # Eigenes HTML löst seine Events selbst aus (`fbq('track', 'PageView')`).
            events = sorted(set(events) | set(tracking_ids.code_events(params["html"])))
        paused = function == "__paused" or bool(tag.get("paused"))
        record = {
            "index": index,
            "tag_id": tag.get("tag_id"),
            "function": function,
            "original_function": params.get("originalTagType") if function == "__paused" else None,
            "service_id": service,
            "purpose": purpose,
            "paused": paused,
            "fires": any("fires_when" in t for t in own_triggers),
            "consent": resolver.render(tag.get("consent")) if tag.get("consent") else None,
            "params": {k: (v[:MAX_CODE] + "…" if isinstance(v, str) and len(v) > MAX_CODE else v)
                       for k, v in params.items()},
            "triggers": own_triggers,
            "events": events,
            "targets": _tag_targets(function, params),
            "hosts": sorted(set(re.findall(r"(?:https?:)?//([a-z0-9][a-z0-9.-]*\.[a-z]{2,})",
                                           "\n".join(_strings(params)), re.I))),
        }
        out.append(record)
    containers = tracking_ids.container_ids(json.dumps(data.get("resource", {}).get("macros", [])))
    return {
        "version": resource.get("version"),
        "container_ids": containers,
        "tags": out,
        "summary": {
            "tags": len(out),
            "paused": sum(1 for t in out if t["paused"]),
            "without_trigger": sum(1 for t in out if not t["fires"]),
            "targets": sorted({t["target_id"] for tag in out for t in tag["targets"]}),
        },
    }


def resolve_file(path: str) -> dict:
    """Liest eine `gtm.js` oder ein bereits aufgelöstes JSON und gibt das Ergebnis zurück."""
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    stripped = text.lstrip()
    if stripped.startswith("{"):
        try:
            data = json.loads(stripped)
        except ValueError:
            data = None
        if isinstance(data, dict) and isinstance(data.get("tags"), list) and "summary" in data:
            return data
        if isinstance(data, dict) and isinstance(data.get("resource"), dict):
            return resolve(data)
    result = resolve(parse_container(text))
    if not result["container_ids"]:
        # Die eigene Kennung steht im Kopf von gtm.js, nicht immer in den Makros.
        result["container_ids"] = tracking_ids.container_ids(text[:5000])
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="GTM-Container auflösen")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("resolve", help="gtm.js auflösen")
    run.add_argument("--gtm", required=True, help="gespeicherte gtm.js")
    run.add_argument("--out", required=True, help="Ziel-JSON")
    args = parser.parse_args(argv)

    try:
        result = resolve_file(args.gtm)
    except (OSError, ContainerError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 2
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({"out": str(out), **result["summary"], "container_ids": result["container_ids"]},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
