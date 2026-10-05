"""Anpassungen an einem Theme: Kandidaten finden und das Verzeichnis der Eingriffe prüfen.

Aufruf:
    PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m theme.customizations diff \\
        --original <dir> --current <dir> --out <file>
    PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m theme.customizations check \\
        --target-repo <path> --prefix <p> --register migration/customizations.md \\
        [--against <git-ref>] [--out <file>]

`diff` vergleicht den Code-Teil eines Themes mit seinem Original und liefert
Kandidaten je Datei mit Art (`added`, `changed`, `removed`) und Umfang. Der
Inhalts-Teil zählt nicht mit (`templates/**/*.json`, `sections/*.json`,
`config/settings_data.json`, `locales/`): das sind Daten des Shops, keine
Anpassungen, und sie erzeugten sonst tausende Scheinbefunde. CSS wird vorher
normalisiert und regelweise verglichen, weil ein neu formatiertes Stylesheet
im rohen Diff tausende Zeilen meldet, von denen fast keine eine Anpassung ist.
Die Einordnung (Funktion, Gestaltung, App-Rest, Altlast) macht die Skill.

`check` hält ein Ziel-Theme updatefähig:

- Eigene Dateien tragen das Präfix im Namen (`<prefix>-*`, privat `_<prefix>-*`).
  Eine neue Datei ohne Präfix ist ein Befund.
- Jede veränderte oder gelöschte Datei des Ziel-Themes steht im Verzeichnis
  (Tabelle unter `## Verzeichnis`, erste Spalte der Pfad in Backticks, Muster
  mit `*` erlaubt), und jeder Eintrag zeigt auf eine veränderte Datei.
- Jede veränderte Datei, die Kommentare kennt (Liquid, JS, CSS), trägt einen
  Kommentar mit `<prefix>:`. JSON kennt keine Kommentare, dort gilt nur das
  Verzeichnis.
- Mit `--against <ref>` kommt die Vorschau auf ein Update dazu: welche
  verzeichneten Dateien die Zielversion ebenfalls ändert (nach dem Merge
  prüfen) und welche Namen des Ziel-Themes die eigenen Dateien nutzen, die es
  in der Zielversion nicht mehr gibt (Snippets, Blöcke, JS-Module, CSS-Klassen).

Verglichen wird gegen den Upstream-Stand im Kopf des Verzeichnisses
(`upstream_ref:`), und zwar der Arbeitsstand, also auch Uncommittetes.

Exit-Code 0 ohne Befund, 1 mit Befunden, 2 bei Fehlern.
"""
import argparse
import difflib
import fnmatch
import json
import re
import subprocess
import sys
from pathlib import Path

CODE_DIRECTORIES = ("assets", "blocks", "config", "layout", "sections", "snippets")
THEME_DIRECTORIES = ("assets", "blocks", "config", "layout", "locales", "sections", "snippets", "templates")
#: Daten des Shops, keine Anpassungen. `locales/` gehört für `diff` ebenfalls dazu
#: (liegt außerhalb von `CODE_DIRECTORIES`); für `check` zählt eine geänderte
#: Sprachdatei des Ziel-Themes dagegen als Eingriff, weil sie beim Update kollidiert.
CONTENT = ("templates/*.json", "sections/*.json", "config/settings_data.json")
OWN_DIRECTORIES = ("assets", "blocks", "sections", "snippets", "templates", "layout")
COMMENT_SUFFIXES = (".liquid", ".js", ".css", ".scss")
TEXT_SUFFIXES = (".liquid", ".js", ".css", ".scss", ".json", ".svg", ".txt", ".md", ".html")

RENDER = re.compile(r"""{%-?\s*render\s+['"]([\w-]+)['"]""")
CONTENT_FOR_TYPE = re.compile(r"""content_for\s+['"]block['"][^%]*?type:\s*['"]([\w-]+)['"]""")
JS_IMPORT = re.compile(r"""(?:from|import)\s*\(?\s*['"]([^'".][^'"]*)['"]""")
CSS_CLASS = re.compile(r"\.(-?[_a-zA-Z][\w-]*)")


class CheckError(Exception):
    """Fehler, der die Prüfung unmöglich macht (Exit 2)."""


# --- diff --------------------------------------------------------------------

def is_content(path: str) -> bool:
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in CONTENT)


def code_files(root: Path) -> dict[str, Path]:
    files = {}
    for directory in CODE_DIRECTORIES:
        base = root / directory
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            rel = path.relative_to(root).as_posix()
            if path.is_file() and not is_content(rel):
                files[rel] = path
    return files


def css_rules(text: str) -> list[str]:
    """CSS in vergleichbare Regeln zerlegen: Kommentare weg, Leerraum zusammengefasst, Deklarationen sortiert."""
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    rules = []
    for selector, body in re.findall(r"([^{}]+)\{([^{}]*)\}", text):
        selector = " ".join(selector.split())
        declarations = sorted(" ".join(part.split()) for part in body.split(";") if part.strip())
        rules.append(f"{selector} {{{'; '.join(declarations)}}}")
    return rules


def read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None


def scope(rel: str, old: Path | None, new: Path | None) -> dict:
    """Umfang einer Abweichung: Zeilen, bei CSS zusätzlich Regeln, Binärdateien nur als solche."""
    old_text = read_text(old) if old else ""
    new_text = read_text(new) if new else ""
    if old_text is None or new_text is None:
        return {"binary": True}
    added = removed = 0
    for line in difflib.unified_diff(old_text.splitlines(), new_text.splitlines(), lineterm="", n=0):
        if line.startswith("+") and not line.startswith("+++"):
            added += 1
        elif line.startswith("-") and not line.startswith("---"):
            removed += 1
    result = {"binary": False, "lines_added": added, "lines_removed": removed}
    if rel.endswith((".css", ".scss")) or rel.endswith(".css.liquid"):
        old_rules, new_rules = set(css_rules(old_text)), set(css_rules(new_text))
        result["rules_added"] = len(new_rules - old_rules)
        result["rules_removed"] = len(old_rules - new_rules)
    return result


def diff_themes(original, current) -> dict:
    """Kandidaten für Anpassungen: jede Code-Datei, die vom Original abweicht."""
    original, current = Path(original), Path(current)
    before, after = code_files(original), code_files(current)
    candidates = []
    for rel in sorted(set(before) | set(after)):
        old, new = before.get(rel), after.get(rel)
        if old and new:
            if old.read_bytes() == new.read_bytes():
                continue
            kind = "changed"
            details = scope(rel, old, new)
            if details.get("rules_added") == 0 and details.get("rules_removed") == 0:
                # Nur anders formatiert: nach der Normalisierung keine neue und keine fehlende Regel.
                kind = "formatting"
        else:
            kind = "added" if new else "removed"
            details = scope(rel, old, new)
        candidates.append({"file": rel, "kind": kind, **details})
    counts = {}
    for candidate in candidates:
        counts[candidate["kind"]] = counts.get(candidate["kind"], 0) + 1
    return {"original_files": len(before), "current_files": len(after), "counts": counts,
            "candidates": candidates}


# --- check -------------------------------------------------------------------

def read_register(path: Path) -> tuple[dict, list[str]]:
    """Kopf (`upstream_ref`, `theme_version` ...) und die Muster aus der Tabelle unter `## Verzeichnis`."""
    if not path.is_file():
        raise CheckError(f"Verzeichnis fehlt: {path}")
    text = path.read_text(encoding="utf-8")
    front = re.match(r"---\n(.*?)\n---\n", text, re.S)
    meta = dict(re.findall(r"^(\w+):\s*(.+?)\s*$", front.group(1), re.M)) if front else {}
    section = re.search(r"^## Verzeichnis\n(.*?)(?=^## |\Z)", text, re.S | re.M)
    rows = section.group(1).splitlines() if section else []
    patterns = [match.group(1) for row in rows if (match := re.match(r"\|\s*`([^`]+)`", row))]
    return meta, patterns


def own_file(path: str, prefix: str) -> bool:
    directory, _, name = path.partition("/")
    return directory in OWN_DIRECTORIES and (name.startswith(f"{prefix}-") or name.startswith(f"_{prefix}-"))


class Repo:
    """Dünne Hülle um git im Ziel-Repo."""

    def __init__(self, root):
        self.root = Path(root)
        if not (self.root / ".git").exists():
            raise CheckError(f"kein Git-Repo: {self.root}")

    def run(self, *args, check=True) -> subprocess.CompletedProcess:
        result = subprocess.run(["git", "-C", str(self.root), *args], capture_output=True, text=True)
        if check and result.returncode != 0:
            raise CheckError(f"git {' '.join(args)} ist fehlgeschlagen: {result.stderr.strip()}")
        return result

    def changed(self, base: str, target: str | None = None, diff_filter: str = "MD") -> list[str]:
        args = ["diff", "--name-only", f"--diff-filter={diff_filter}", base] + ([target] if target else [])
        files = self.run(*args, "--", *THEME_DIRECTORIES).stdout.split("\n")
        return sorted(path for path in files if path)

    def untracked(self) -> list[str]:
        out = self.run("ls-files", "--others", "--exclude-standard", "--", *THEME_DIRECTORIES).stdout
        return sorted(path for path in out.split("\n") if path)

    def exists(self, ref: str, path: str) -> bool:
        return self.run("cat-file", "-e", f"{ref}:{path}", check=False).returncode == 0

    def contains(self, ref: str, text: str, exclude: list[str]) -> bool:
        return self.run("grep", "-q", "-F", text, ref, "--", *THEME_DIRECTORIES, *exclude,
                        check=False).returncode == 0


def used_names(root: Path, prefix: str) -> dict[tuple[str, str], str]:
    """Namen des Ziel-Themes, auf die sich die eigenen Dateien verlassen, mit Fundstelle."""
    names: dict[tuple[str, str], str] = {}
    for directory in ("blocks", "sections", "snippets", "layout"):
        for path in sorted((root / directory).glob("*.liquid")):
            rel = path.relative_to(root).as_posix()
            if not own_file(rel, prefix):
                continue
            text = path.read_text(encoding="utf-8")
            for snippet in RENDER.findall(text):
                if not own_file(f"snippets/{snippet}", prefix):
                    names.setdefault(("snippet", f"snippets/{snippet}.liquid"), rel)
            for block in CONTENT_FOR_TYPE.findall(text):
                if not own_file(f"blocks/{block}", prefix):
                    names.setdefault(("block", f"blocks/{block}.liquid"), rel)
    for path in sorted((root / "assets").glob(f"{prefix}-*")):
        rel = path.relative_to(root).as_posix()
        text = read_text(path)
        if text is None:
            continue
        if path.suffix == ".js":
            for module in JS_IMPORT.findall(text):
                names.setdefault(("module", module), rel)
        elif path.suffix == ".css":
            css = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
            selectors = " ".join(re.findall(r"([^{}]+)\{", css))
            for name in CSS_CLASS.findall(selectors):
                if not name.startswith(f"{prefix}-"):
                    names.setdefault(("class", name), rel)
    return names


def check_repo(target_repo, prefix: str, register, against: str | None = None) -> dict:
    """Verzeichnis gegen den tatsächlichen Stand des Ziel-Repos halten."""
    repo = Repo(target_repo)
    meta, patterns = read_register(Path(register))
    base = meta.get("upstream_ref")
    if not base:
        raise CheckError(f"{register}: `upstream_ref` fehlt im Kopf der Datei")
    if repo.run("rev-parse", "--verify", "--quiet", f"{base}^{{commit}}", check=False).returncode != 0:
        raise CheckError(f"Upstream-Stand {base!r} gibt es im Ziel-Repo nicht")
    if repo.run("merge-base", "--is-ancestor", base, "HEAD", check=False).returncode != 0:
        raise CheckError(f"Upstream-Stand {base} ist kein Vorfahre von HEAD; nach einem Update den Kopf nachziehen")

    changed = [path for path in repo.changed(base) if not is_content(path) and not own_file(path, prefix)]
    added = repo.changed(base, diff_filter="A") + repo.untracked()
    unprefixed = sorted({path for path in added
                         if not is_content(path) and not own_file(path, prefix)
                         and not path.startswith("locales/")})
    missing = [path for path in changed if not any(fnmatch.fnmatchcase(path, p) for p in patterns)]
    stale = [p for p in patterns if not any(fnmatch.fnmatchcase(path, p) for path in changed)]
    marker = re.compile(rf"\b{re.escape(prefix)}:", re.I)
    unmarked = []
    for path in changed:
        file = repo.root / path
        if path.endswith(COMMENT_SUFFIXES) and file.is_file():
            text = read_text(file)
            if text is not None and not marker.search(text):
                unmarked.append(path)

    result = {"upstream_ref": base, "theme_version": meta.get("theme_version"), "prefix": prefix,
              "changed_core_files": changed, "register_entries": patterns,
              "missing_in_register": missing, "register_without_change": stale,
              "missing_marker": unmarked, "own_files_without_prefix": unprefixed}
    findings = len(missing) + len(stale) + len(unmarked) + len(unprefixed)

    if against:
        if repo.run("rev-parse", "--verify", "--quiet", f"{against}^{{commit}}", check=False).returncode != 0:
            raise CheckError(f"Ziel-Stand {against!r} gibt es im Ziel-Repo nicht")
        update_changes = set(repo.changed(base, against))
        touched = [path for path in changed if path in update_changes]
        exclude = [f":!{directory}/{prefix}-*" for directory in OWN_DIRECTORIES]
        lost = []
        for (kind, name), source in sorted(used_names(repo.root, prefix).items()):
            if kind in ("snippet", "block"):
                gone = repo.exists(base, name) and not repo.exists(against, name)
            else:
                gone = repo.contains(base, name, exclude) and not repo.contains(against, name, exclude)
            if gone:
                lost.append({"kind": kind, "name": name, "used_in": source})
        result["against"] = against
        result["check_after_update"] = touched
        result["names_lost_in_update"] = lost
        findings += len(lost)
    result["findings"] = findings
    return result


# --- CLI ---------------------------------------------------------------------

def write_json(path: str | None, data: dict) -> None:
    if not path:
        return
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Anpassungen finden und das Verzeichnis der Eingriffe prüfen")
    sub = parser.add_subparsers(dest="command", required=True)
    diff_parser = sub.add_parser("diff", help="Code-Teil eines Themes gegen sein Original")
    diff_parser.add_argument("--original", required=True)
    diff_parser.add_argument("--current", required=True)
    diff_parser.add_argument("--out", required=True)
    check_parser = sub.add_parser("check", help="Verzeichnis der Eingriffe gegen das Ziel-Repo")
    check_parser.add_argument("--target-repo", required=True)
    check_parser.add_argument("--prefix", required=True)
    check_parser.add_argument("--register", required=True)
    check_parser.add_argument("--against", help="Ziel-Stand für die Update-Vorschau, etwa upstream/main")
    check_parser.add_argument("--out")
    args = parser.parse_args(argv)

    if args.command == "diff":
        for flag, value in (("--original", args.original), ("--current", args.current)):
            if not Path(value).is_dir():
                print(json.dumps({"error": f"{flag}: Verzeichnis fehlt: {value}"}, ensure_ascii=False))
                return 2
        result = diff_themes(args.original, args.current)
        write_json(args.out, result)
        print(json.dumps({"out": args.out, "candidates": len(result["candidates"]), **result["counts"]},
                         ensure_ascii=False))
        return 1 if result["candidates"] else 0

    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", args.prefix):
        print(json.dumps({"error": "--prefix: Kleinbuchstaben, Ziffern und Bindestrich"}, ensure_ascii=False))
        return 2
    try:
        result = check_repo(args.target_repo, args.prefix, args.register, args.against)
    except CheckError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 2
    write_json(args.out, result)
    summary = {key: (len(value) if isinstance(value, list) else value) for key, value in result.items()
               if key not in ("register_entries", "theme_version")}
    print(json.dumps(summary, ensure_ascii=False))
    return 1 if result["findings"] else 0


if __name__ == "__main__":
    sys.exit(main())
