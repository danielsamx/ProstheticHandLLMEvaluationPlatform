#!/usr/bin/env python3
"""Static checks for the Angular sources that do not need node_modules.

Catches two classes of failure that only surface at build time:

1. **Template literals that close early.** A stray backtick inside a
   ``template:`` block terminates the string, so the rest of the markup becomes
   further arguments to ``@Component`` — Angular reports this as NG1002. Simply
   counting backticks for balance does not catch it: a *pair* of stray backticks
   keeps the total even while still breaking the decorator.

2. **Unresolvable internal imports**, including the path aliases.

Run: ``python scripts/check_frontend.py``
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
ROOT = PROJECT / "frontend" / "src"
ALIASES = {
    "@core/": "app/core/",
    "@features/": "app/features/",
    "@shared/": "app/shared/",
    "@env/": "environments/",
}


def _closes_early(text: str, opener: re.Match[str]) -> int | None:
    """Return the 1-based line where the literal ends, if it ends too soon."""
    index = opener.end()
    while index < len(text):
        if text[index] == "\\":
            index += 2
            continue
        if text[index] == "`":
            break
        index += 1

    tail = text[index + 1 : index + 40].lstrip()
    if tail.startswith((",", "}", "]")):
        return None
    return text[:index].count("\n") + 1


def check_decorator_literals() -> list[str]:
    problems: list[str] = []
    for path in sorted(ROOT.rglob("*.ts")):
        text = path.read_text()
        for pattern in (r"template:\s*`", r"styles:\s*\[\s*`"):
            for match in re.finditer(pattern, text):
                line = _closes_early(text, match)
                if line is not None:
                    kind = "template" if "template" in pattern else "styles"
                    problems.append(
                        f"{path.relative_to(ROOT)}:{line}: {kind} literal closes "
                        "early — a stray backtick inside the block ends the "
                        "string (Angular reports NG1002)"
                    )
    return problems


#: TypeScript request interfaces and the Pydantic models they must mirror.
#: A field added on one side and forgotten on the other is a build error at best
#: and a silently dropped parameter at worst.
CONTRACTS = {
    "RunExecutionPayload": "RunExecutionIn",
}


def check_request_contracts() -> list[str]:
    """Compare each TypeScript request type against its Pydantic counterpart."""
    import ast

    backend = PROJECT / "backend" / "app" / "schemas" / "api.py"
    client = ROOT / "app" / "core" / "api" / "api.service.ts"
    if not backend.exists() or not client.exists():
        # Returning quietly here is how this check spent its first run doing
        # nothing: the backend path was wrong and nobody noticed.
        return [f"contract check could not run: {backend} or {client} not found"]

    tree = ast.parse(backend.read_text())
    source = client.read_text()
    problems: list[str] = []

    for ts_name, py_name in CONTRACTS.items():
        node = next(
            (n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == py_name),
            None,
        )
        match = re.search(rf"export interface {ts_name} \{{(.*?)\n\}}", source, re.S)
        if node is None or match is None:
            problems.append(f"cannot compare {ts_name} with {py_name}")
            continue

        backend_fields = {
            item.target.id for item in node.body if isinstance(item, ast.AnnAssign)
        }
        client_fields = set(re.findall(r"^\s*(\w+)\??:", match.group(1), re.M))

        for field in sorted(backend_fields - client_fields):
            problems.append(f"{ts_name}: missing '{field}' (present on {py_name})")
        for field in sorted(client_fields - backend_fields):
            problems.append(f"{ts_name}: '{field}' is not accepted by {py_name}")

    return problems


def check_imports() -> list[str]:
    problems: list[str] = []
    for path in sorted(ROOT.rglob("*.ts")):
        text = path.read_text()

        for alias, target in ALIASES.items():
            for match in re.finditer(rf"from '{re.escape(alias)}([^']+)'", text):
                if not (ROOT / target / f"{match.group(1)}.ts").exists():
                    problems.append(
                        f"{path.relative_to(ROOT)}: unresolved {alias}{match.group(1)}"
                    )

        for match in re.finditer(r"from '(\.[^']+)'", text):
            spec = match.group(1)
            if not (path.parent / f"{spec}.ts").exists() and not (
                path.parent / spec / "index.ts"
            ).exists():
                problems.append(f"{path.relative_to(ROOT)}: unresolved {spec}")

    return problems


#: Tags that never carry a closing tag, so counting them would always mismatch.
_VOID_TAGS = frozenset({
    "input", "img", "br", "hr", "source", "track", "area", "base", "col",
    "embed", "link", "meta", "param", "wbr",
})

#: Elements worth balancing. Restricted on purpose: `<ng-template>` and Angular
#: control flow have their own syntax, and self-closing component tags
#: (`<ph-emg-panel />`) are legal, so a blanket check would be noise.
_BALANCED_TAGS = ("div", "span", "table", "thead", "tbody", "tr", "td", "th",
                  "button", "p", "dl", "pre", "label", "select", "textarea")


def check_template_balance() -> list[str]:
    """Unclosed elements inside a component template.

    Angular finds these, but only at build time and with a message that points at
    wherever the parser gave up rather than at the tag that was dropped. This
    names the tag and the count.

    Worth checking because the failure mode is editing, not writing: removing a
    region by index — as happened here, cutting a duplicated block and taking its
    parent's closing tag with it — leaves a template that reads correctly and
    parses as garbage.
    """
    problems: list[str] = []

    for path in sorted(ROOT.rglob("*.ts")):
        text = path.read_text(encoding="utf-8")
        opener = re.search(r"template:\s*`", text)
        if not opener:
            continue
        start = opener.end()
        end = text.find("`", start)
        while end != -1 and text[end - 1] == "\\":
            end = text.find("`", end + 1)
        if end == -1:
            continue
        template = text[start:end]

        for tag in _BALANCED_TAGS:
            if tag in _VOID_TAGS:
                continue
            # `<div` but not `<divider`; `/>` excluded so self-closing is ignored.
            opens = len(re.findall(rf"<{tag}(?=[\s>])(?![^>]*/>)", template))
            closes = len(re.findall(rf"</{tag}>", template))
            if opens != closes:
                line = text[:start].count("\n") + 1
                problems.append(
                    f"{path.relative_to(ROOT.parent)}:{line}: template has "
                    f"{opens} <{tag}> and {closes} </{tag}> — "
                    f"{abs(opens - closes)} unbalanced."
                )

    return problems


def check_stacked_overlays() -> list[str]:
    """Two absolutely positioned boxes pinned to the same edge.

    They overlap, and the later one in the DOM wins — silently. That is how the
    manual command field ended up invisible: it was placed at `absolute bottom-4
    left-4 right-4`, and the actuator read-out sixty lines below used the same
    coordinates and painted straight over it.

    Nothing errors, nothing warns, and the element is in the DOM with a non-zero
    size, so it survives every check that looks at the code rather than the
    layout. Counting the collisions is the cheapest way to notice.
    """
    problems: list[str] = []
    # An `absolute` box pinned on an edge with matching insets.
    anchored = re.compile(
        r'class="[^"]*\babsolute\b[^"]*\b(top|bottom)-(\d+)[^"]*\bleft-(\d+)[^"]*\bright-(\d+)',
    )

    for path in sorted(ROOT.rglob("*.ts")):
        text = path.read_text(encoding="utf-8")
        if "template:" not in text:
            continue

        seen: dict[tuple[str, ...], int] = {}
        for number, line in enumerate(text.splitlines(), start=1):
            match = anchored.search(line)
            if not match:
                continue
            key = match.groups()
            if key in seen:
                edge, offset, left, right = key
                problems.append(
                    f"{path.relative_to(ROOT.parent)}:{number}: absolute box at "
                    f"{edge}-{offset} left-{left} right-{right} overlaps the one at "
                    f"line {seen[key]}. The later one paints over the earlier one."
                )
            else:
                seen[key] = number

    return problems


def check_duplicate_members() -> list[str]:
    """Two class members with the same name.

    TypeScript reports this as TS2300 and TS2717, and the template picks up the
    *last* declaration — so injecting a service over an existing signal silently
    changed what five template expressions referred to, and the build failed on
    call signatures rather than on the collision that caused it.

    Worth a static check because the failure is at the bottom of a long class and
    the cause is at the top: `movement = inject(MovementStore)` added near the
    constructor, `movement = computed(...)` already present 70 lines below.
    """
    problems: list[str] = []
    member = re.compile(
        r"^\s{2}(?:protected |private |public |readonly |static )*"
        r"(?:readonly )?([A-Za-z_$][\w$]*)\s*(?:[:=]|\()",
    )

    for path in sorted(ROOT.rglob("*.ts")):
        text = path.read_text(encoding="utf-8")
        # Only look inside a class body, and only at two-space indentation, which
        # is where this codebase puts members. Anything deeper is a local.
        seen: dict[str, int] = {}
        in_class = False
        for number, line in enumerate(text.splitlines(), start=1):
            if re.match(r"^export (?:abstract )?class \b", line):
                in_class, seen = True, {}
                continue
            if not in_class:
                continue

            match = member.match(line)
            if not match:
                continue
            name = match.group(1)
            # Keywords that can look like a member at this indentation.
            if name in {"constructor", "if", "for", "return", "get", "set", "async"}:
                continue
            if name in seen:
                problems.append(
                    f"{path.relative_to(ROOT.parent)}:{number}: duplicate class member "
                    f"{name!r} — also declared at line {seen[name]}. "
                    "The template will bind to the last one (TS2300/TS2717)."
                )
            else:
                seen[name] = number

    return problems


def main() -> int:
    files = list(ROOT.rglob("*.ts"))
    problems = (
        check_decorator_literals()
        + check_imports()
        + check_request_contracts()
        + check_duplicate_members()
        + check_template_balance()
        + check_stacked_overlays()
    )

    if problems:
        print(f"✗ {len(problems)} problem(s) across {len(files)} TypeScript files:\n")
        for problem in problems:
            print(f"  {problem}")
        return 1

    print(
        f"✓ {len(files)} TypeScript files: decorator literals, imports, "
        "request contracts, member names, template balance and overlay "
        "positions are sound"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
