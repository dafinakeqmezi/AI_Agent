"""PreToolUse hook: block any Edit/Write/NotebookEdit inside submissions/ (frozen submissions are immutable).

Exit code 2 blocks the tool call and shows stderr to Claude.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROTECTED = (ROOT / "submissions").resolve()


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0
    tool_input = data.get("tool_input") or {}
    target = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not target:
        return 0
    path = Path(target)
    if not path.is_absolute():
        path = Path(data.get("cwd") or ROOT) / path
    try:
        path.resolve().relative_to(PROTECTED)
    except ValueError:
        return 0
    print(f"Blocked: {target} is inside submissions/. Frozen submissions are immutable "
          "(rule 12: never modify submitted work). Write outputs to reviews/ or evaluations/ instead.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
