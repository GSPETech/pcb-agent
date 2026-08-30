"""Sanitize raw Diode evidence for publication.

Rewrites ONLY path fields (keys named file_path / path / absolute paths in
stdout text). Statuses, counts, names, and hashes are preserved. Sanitized
files are diagnostic companions; raw files remain the verification truth.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

EV = Path(__file__).resolve().parent
RAW_ROOT = EV / "diode-0.4.40"

_PATH_PATTERNS = (
    re.compile(r"/home/rendra/pcbagent-full"),
    re.compile(r"/home/rendra/.local/bin"),
    re.compile(r"/tmp/pcb-agent-[a-z0-9]+"),
)


def _rewrite(value: str) -> str:
    out = value
    for pattern in _PATH_PATTERNS:
        out = pattern.sub("<sanitized>", out)
    return out


def _walk(node: object) -> object:
    if isinstance(node, dict):
        result = {}
        for key, value in node.items():
            if key in {"file_path", "path"} and isinstance(value, str):
                result[key] = _rewrite(value)
            elif key == "command" and isinstance(value, list):
                result[key] = [_rewrite(item) if isinstance(item, str) else item for item in value]
            elif key == "stdout" and isinstance(value, str):
                result[key] = _rewrite(value)
            elif key == "stderr" and isinstance(value, str):
                result[key] = _rewrite(value)
            else:
                result[key] = _walk(value)
        return result
    if isinstance(node, list):
        return [_walk(item) for item in node]
    return node


def sanitize(relative: str) -> None:
    raw = RAW_ROOT / relative
    data = json.loads(raw.read_text(encoding="utf-8"))
    sanitized = RAW_ROOT / raw.with_name(raw.name.replace(".json", ".sanitized.json"))
    sanitized.write_text(
        json.dumps(_walk(data), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"wrote {sanitized.relative_to(RAW_ROOT)}")


if __name__ == "__main__":
    for relative in (
        "valid-blinky/valid-blinky.json",
        "spike-generics/spike-generics.json",
        "green-real/green-real-report.json",
        "prefix/prefix-renamed-alt-case.json",
        "green-real/run/raw/connectivity-result.json",
        "green-real/run/raw/specification-result.json",
    ):
        sanitize(relative)
