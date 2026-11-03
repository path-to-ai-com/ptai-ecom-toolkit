"""Pflichtangaben für neue Befunde, Vertrag reference/finding-format.md.

Altdateien bleiben unverändert gültig. Der Laufzustand verlangt v2 auch dann,
wenn ein Agent den Formatstand in seiner Befunddatei vergessen hat.
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path
from datetime import date

VERSION = 2
FIELDS = ("primary_metric", "visualization", "reasoning")


def problems(finding, version=None):
    """Alle Feldfehler sammeln, damit der Schreiber sie zusammen beheben kann."""
    out = []
    if not isinstance(finding, dict):
        return ["finding: muss ein Objekt sein"]
    active = version is not None or any(k in finding for k in FIELDS)
    if not active:
        return out
    if version is not None and (type(version) not in (int, float) or version != VERSION):
        out.append("finding_format: nur Version 2 wird unterstützt")

    def text(obj, key, path):
        if not isinstance(obj.get(key), str) or not obj[key].strip():
            out.append(f"{path}.{key}: nichtleerer Text erforderlich")

    def number(value, path, nonnegative=False):
        try:
            valid = type(value) in (int, float) and math.isfinite(value)
        except OverflowError:
            valid = False
        if not valid or (nonnegative and value < 0):
            out.append(f"{path}: endliche Zahl" + (" ab 0" if nonnegative else "") + " erforderlich")
        return valid

    metric = finding.get("primary_metric")
    if not isinstance(metric, dict):
        out.append("primary_metric: Objekt erforderlich")
    else:
        number(metric.get("value"), "primary_metric.value")
        for key in ("unit", "label", "basis", "period"):
            text(metric, key, "primary_metric")

    reasoning = finding.get("reasoning")
    if not isinstance(reasoning, dict):
        out.append("reasoning: Objekt mit cause, effect, recommendation erforderlich")
    else:
        for key in ("cause", "effect", "recommendation"):
            text(reasoning, key, "reasoning")
            value = reasoning.get(key)
            if isinstance(value, str) and value.strip():
                sentence = re.sub(r"\b(?:z\. B\.|u\. a\.|d\. h\.|bzw\.|ca\.|Dr\.|ggf\.|usw\.)", "ABBR", value)
                # Datums- und Ordinalpunkte sind keine Satzgrenzen. Eine nackte
                # Zahl vor einem neuen Satz bleibt dagegen eine Satzgrenze.
                sentence = re.sub(r"\b[0-9]{1,2}\.\s*[0-9]{1,2}\.\s*[0-9]{4}\b", "DATE", sentence)
                sentence = re.sub(r"\b[0-9]{1,2}\.(?=\s+(?:Januar|Februar|März|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember)\b)", "DAY", sentence)
                sentence = re.sub(r"\b((?:am|vom|im|zum|beim|der|die|das|dem|den|des)\s+[0-9]+)\.(?=\s+[A-Za-zÄÖÜäöüß])", r"\1", sentence, flags=re.IGNORECASE)
                if "\n" in value or len(re.findall(r"[.!?](?=\s|$)", sentence.strip())) != 1 or not re.search(r"[.!?]$", sentence.strip()):
                    out.append(f"reasoning.{key}: genau ein abgeschlossener Satz erforderlich")
        if set(reasoning) - {"cause", "effect", "recommendation"}:
            out.append("reasoning: nur cause, effect, recommendation erlaubt")

    def comparison(chart, path, threshold_required):
        for key in ("unit", "period"):
            text(chart, key, path)
        values = chart.get("values")
        if not isinstance(values, list) or len(values) < 2:
            out.append(f"{path}.values: mindestens zwei Werte erforderlich")
        else:
            for i, item in enumerate(values):
                p = f"{path}.values[{i}]"
                if not isinstance(item, dict):
                    out.append(f"{p}: Objekt erforderlich")
                    continue
                text(item, "label", p)
                number(item.get("value"), p + ".value", True)
                if item.get("role") not in ("focus", "reference"):
                    out.append(f"{p}.role: focus oder reference erforderlich")
            if not any(isinstance(v, dict) and v.get("role") == "focus" for v in values):
                out.append(f"{path}.values: focus fehlt")
            if not any(isinstance(v, dict) and v.get("role") == "reference" for v in values):
                out.append(f"{path}.values: reference fehlt")
        threshold = chart.get("threshold")
        if "threshold" in chart or threshold_required:
            if not isinstance(threshold, dict):
                out.append(f"{path}.threshold: Grenze aus dem Prüfkriterium erforderlich")
            else:
                number(threshold.get("value"), path + ".threshold.value", True)
                for key in ("label", "criterion"):
                    text(threshold, key, path + ".threshold")

    chart = finding.get("visualization")
    if not isinstance(chart, dict):
        out.append("visualization: Objekt erforderlich")
        return out
    kind = chart.get("type")
    if kind == "comparison":
        comparison(chart, "visualization", True)
    elif kind == "share":
        for key in ("unit", "period"):
            text(chart, key, "visualization")
        total = chart.get("total")
        valid_total = number(total, "visualization.total", True)
        if valid_total and total == 0:
            out.append("visualization.total: muss größer als 0 sein")
        parts = chart.get("parts")
        if not isinstance(parts, list) or len(parts) < 2:
            out.append("visualization.parts: mindestens zwei Teile erforderlich")
        else:
            values = []
            for i, item in enumerate(parts):
                path = f"visualization.parts[{i}]"
                if not isinstance(item, dict):
                    out.append(f"{path}: Objekt erforderlich")
                    continue
                text(item, "label", path)
                if number(item.get("value"), path + ".value", True):
                    values.append(item["value"])
                if item.get("role") not in ("focus", "reference"):
                    out.append(f"{path}.role: focus oder reference erforderlich")
            if valid_total and len(values) == len(parts) and not math.isclose(sum(values), total, rel_tol=1e-9, abs_tol=1e-9):
                out.append("visualization.parts: Summe muss total entsprechen")
    elif kind == "trend":
        for key in ("unit", "period"):
            text(chart, key, "visualization")
        points = chart.get("points")
        if not isinstance(points, list) or len(points) < 2:
            out.append("visualization.points: mindestens zwei Messpunkte erforderlich")
        else:
            previous = ""
            dates = []
            for i, point in enumerate(points):
                path = f"visualization.points[{i}]"
                if not isinstance(point, dict):
                    out.append(f"{path}: Objekt erforderlich")
                    continue
                day = point.get("date")
                try:
                    if not isinstance(day, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
                        raise ValueError()
                    date.fromisoformat(day)
                    if day <= previous:
                        raise ValueError()
                    previous = day
                    dates.append(day)
                except ValueError:
                    out.append(f"{path}.date: gültiges Datum, streng aufsteigend erforderlich")
                number(point.get("value"), path + ".value")
            marker = chart.get("marker")
            if "marker" in chart:
                if not isinstance(marker, dict) or marker.get("date") not in dates:
                    out.append("visualization.marker.date: muss einen Messpunkt nennen")
                if isinstance(marker, dict):
                    text(marker, "label", "visualization.marker")
    elif kind == "image":
        ref = chart.get("proof_ref")
        columns = finding.get("proof", {})
        columns = columns.get("columns", []) if isinstance(columns, dict) else columns
        try:
            if not isinstance(ref, dict) or any(type(ref.get(k)) is not int or ref[k] < 0 for k in ("column", "block")):
                raise ValueError()
            block = columns[ref["column"]]["blocks"][ref["block"]]
            if block.get("type") not in ("image", "phone"):
                raise ValueError()
        except (ValueError, KeyError, IndexError, TypeError, AttributeError):
            out.append("visualization.proof_ref: muss auf image oder phone in proof zeigen")
        if "comparison" in chart:
            if not isinstance(chart["comparison"], dict):
                out.append("visualization.comparison: Objekt erforderlich")
            else:
                comparison(chart["comparison"], "visualization.comparison", False)
    else:
        out.append("visualization.type: comparison, share, trend oder image erforderlich")
    return out


def document_problems(doc, run_version=None):
    if not isinstance(doc, dict):
        return ["Dokument muss ein Objekt sein"]
    version = doc.get("finding_format", run_version)
    out = []
    if "finding_format" in doc and doc["finding_format"] is None:
        out.append("finding_format: nur Version 2 wird unterstützt")
    if run_version is not None and doc.get("finding_format", run_version) != run_version:
        out.append("finding_format: widerspricht dem Laufzustand")
    if version is not None and (type(version) not in (int, float) or version != VERSION):
        out.append("finding_format: nur Version 2 wird unterstützt")
    findings = doc.get("findings")
    if findings is None and version is None:
        return out
    if not isinstance(findings, list):
        return out + ["findings: Liste erforderlich"]
    for i, finding in enumerate(findings):
        identifier = finding.get("id", i) if isinstance(finding, dict) else i
        out.extend(f"{identifier} {p}" for p in problems(finding, version))
    return out


def run_problems(run_dir: Path):
    """Vor jedem Kopieren und Upload prüfen, auch beschädigtes JSON melden."""
    out = []
    state_path = run_dir / "state.json"
    try:
        state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
        if not isinstance(state, dict):
            return ["state.json: Objekt erforderlich"]
    except (OSError, ValueError):
        return ["state.json: nicht lesbar oder kein gültiges JSON"]
    version = state.get("finding_format")
    if "finding_format" in state and version is None:
        out.append("state.json finding_format: nur Version 2 wird unterstützt")
    if version is not None and (type(version) not in (int, float) or version != VERSION):
        out.append("state.json finding_format: nur Version 2 wird unterstützt")
    paths = sorted((run_dir / "findings").glob("*.json"))
    if version == VERSION and state.get("cadence") in ("audit", "month", "report") and not paths:
        out.append("findings: mindestens eine Befunddatei erforderlich, auch bei leerer findings-Liste")
    for path in paths:
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
            out.extend(f"{path.name} {p}" for p in document_problems(doc, version))
        except (OSError, ValueError):
            out.append(f"{path.name}: nicht lesbar oder kein gültiges JSON")
    return out
