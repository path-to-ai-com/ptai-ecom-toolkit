"""Hilfen für die Tests des Generators und der Anpassungsprüfung. Kein Test.

Die Fixtures unter `fixtures/theme/generate/` sind erfunden (siehe HERKUNFT.md).
Tests, die Quelle oder Ziel verändern, arbeiten auf einer Kopie im Temp-Ordner.
"""
import copy
import json
import shutil
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from theme import generate  # noqa: E402

FIXTURE = Path(__file__).parent / "fixtures" / "theme" / "generate"
SOURCE = FIXTURE / "source"
TARGET = FIXTURE / "target"


def fixture_mapping() -> dict:
    return json.loads((FIXTURE / "mapping.json").read_text(encoding="utf-8"))


def temp_dir(case) -> Path:
    tmp = tempfile.TemporaryDirectory()
    case.addCleanup(tmp.cleanup)
    return Path(tmp.name)


def copy_themes(case) -> tuple[Path, Path]:
    """Kopie von Quelle und Ziel, für Tests, die Dateien ändern."""
    base = temp_dir(case)
    source, target = base / "source", base / "target"
    shutil.copytree(SOURCE, source)
    shutil.copytree(TARGET, target)
    return source, target


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_generator(mapping=None, overrides=None, source=SOURCE, target=TARGET) -> "generate.Generator":
    """Generator ohne Schreiben: Dokumente in `.documents`, Befunde in `.report`."""
    generator = generate.Generator(copy.deepcopy(mapping if mapping is not None else fixture_mapping()),
                                   overrides, source, target)
    generator.run()
    return generator


def entries(report: dict, section: str, **match) -> list[dict]:
    """Einträge einer Report-Liste, gefiltert nach Feldern."""
    return [entry for entry in report[section] if all(entry.get(k) == v for k, v in match.items())]
