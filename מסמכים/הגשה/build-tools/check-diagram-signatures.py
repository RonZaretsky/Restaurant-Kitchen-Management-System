"""Compares every method signature written in a diagram against the real code.

Diagrams drift silently: a class diagram gets corrected, the sequence diagram
that calls the same method does not, and nothing complains until a reader
notices. This walks `diagrams/*.md`, pulls out every method signature it finds
in a Mermaid class diagram or sequence diagram, and reports the ones that no
longer match the backend.

A class-diagram member is a declaration, so its parameter *names* are compared.
A sequence-diagram message is a call showing argument *values*, so only the
number of arguments is compared there - that is what catches a parameter added
to the code and never added to the diagram.

Usage:
    python check-diagram-signatures.py [--verbose]

Exit code is 1 when anything is reported, so it can gate a build.
"""

import re
import sys
from pathlib import Path

# Windows gives a redirected stdout the ANSI codepage, which cannot hold Hebrew.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[3]
DIAGRAMS = Path(__file__).resolve().parents[1] / "diagrams"
BACKEND = ROOT / "backend"

# A class-diagram member line: "+pick_up_item(db, actor, item_id) OrderItem"
# or "-_lock_ingredient(db, ingredient_id)". Leading +/- is the UML visibility.
CLASS_MEMBER = re.compile(r"^\s*([+\-#~])(\w+)\(([^)]*)\)")

# A sequence-diagram message carrying a call: "API->>AIS: generate_suggestion(db, actor)"
SEQ_CALL = re.compile(r"^\s*\w+\s*-{1,2}>>?\s*\w+\s*:\s*.*?(\w+)\(([^)]*)\)")

# Python's own definition, across a possible line wrap.
PY_DEF = re.compile(r"^\s*(?:async\s+)?def\s+(\w+)\s*\(", re.M)

# Names that appear in diagrams but are not backend methods: HTTP verbs, the
# frontend's own calls, and mermaid's own syntax.
IGNORE = {"alt", "else", "opt", "loop", "par", "end", "note", "activate", "deactivate"}


def python_signatures():
    """Returns {method name: [parameter name lists]} for the whole backend.

    A name can be defined in more than one module, so every definition is kept
    and a diagram matching any one of them counts as correct.
    """
    found = {}
    for path in BACKEND.rglob("*.py"):
        if ".venv" in path.parts or "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        for match in PY_DEF.finditer(text):
            name = match.group(1)
            # Read forward to the closing paren, so wrapped signatures work.
            depth, i = 0, match.end() - 1
            while i < len(text):
                if text[i] == "(":
                    depth += 1
                elif text[i] == ")":
                    depth -= 1
                    if depth == 0:
                        break
                i += 1
            raw = text[match.end():i]
            params = []
            for part in split_params(raw):
                part = part.split(":")[0].split("=")[0].strip()
                if part and part not in ("self", "cls", "*", "/"):
                    params.append(part.lstrip("*"))
            found.setdefault(name, []).append(params)
    return found


def split_params(raw):
    """Splits a parameter list on commas that are not inside brackets."""
    parts, depth, current = [], 0, ""
    for char in raw:
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
        if char == "," and depth == 0:
            parts.append(current)
            current = ""
        else:
            current += char
    parts.append(current)
    return parts


def diagram_signatures():
    """Returns [(file, line number, method name, parameter names)]."""
    found = []
    for path in sorted(DIAGRAMS.glob("*.md")):
        in_class = in_seq = False
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("classDiagram"):
                in_class, in_seq = True, False
            elif stripped.startswith("sequenceDiagram"):
                in_class, in_seq = False, True
            elif stripped.startswith("```") and not stripped.startswith("```mermaid"):
                in_class = in_seq = False

            match = None
            if in_class:
                match = CLASS_MEMBER.match(line)
                if match:
                    name, raw = match.group(2), match.group(3)
            if not match and in_seq:
                match = SEQ_CALL.match(line)
                if match:
                    name, raw = match.group(1), match.group(2)
            if not match:
                continue
            if name.lower() in IGNORE:
                continue
            params = [p.strip().split(" ")[-1] for p in split_params(raw) if p.strip()]
            kind = "declaration" if in_class else "call"
            found.append((path.name, number, name, params, kind))
    return found


def main(verbose=False):
    code = python_signatures()
    problems = []
    checked = 0

    for file, number, name, params, kind in diagram_signatures():
        # A name the backend has never heard of is a frontend call or a label,
        # not drift, so only names the backend does define are compared.
        if name not in code:
            if verbose:
                print("  דילוג: %s:%d %s, אינו מתודה בצד השרת" % (file, number, name))
            continue
        checked += 1
        if kind == "declaration":
            if any(params == real for real in code[name]):
                continue
        else:
            if any(len(params) == len(real) for real in code[name]):
                continue
        problems.append((file, number, name, params, code[name], kind))

    print("נבדקו %d חתימות המופיעות גם בדיאגרמה וגם בקוד." % checked)
    if not problems:
        print("כל החתימות תואמות.")
        return 0

    print()
    print("נמצאו %d פערים:" % len(problems))
    for file, number, name, params, real, kind in problems:
        label = "הצהרה" if kind == "declaration" else "קריאה"
        print()
        print("  %s:%d  %s  (%s)" % (file, number, name, label))
        print("    בדיאגרמה : (%s)" % ", ".join(params))
        for option in real:
            print("    בקוד     : (%s)" % ", ".join(option))
    return 1


if __name__ == "__main__":
    sys.exit(main("--verbose" in sys.argv))
