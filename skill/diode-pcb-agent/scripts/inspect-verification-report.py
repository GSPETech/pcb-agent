#!/usr/bin/env python3
"""Print non-authoritative summary of a pcb-agent verification report."""

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--failures-only", action="store_true")
    args = parser.parse_args()

    try:
        report = json.loads(args.report.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        print(f"error: cannot read report: {error}", file=sys.stderr)
        return 2

    if not isinstance(report, dict) or not isinstance(report.get("checks"), list):
        print("error: report must be an object containing checks[]", file=sys.stderr)
        return 3

    checks = report["checks"]
    if args.failures_only:
        checks = [check for check in checks if isinstance(check, dict) and check.get("status") != "PASS"]

    summary = {
        "project": report.get("project"),
        "status": report.get("status"),
        "production_ready": report.get("production_ready", False),
        "fabrication_approved": report.get("fabrication_approved", False),
        "human_review": report.get("human_review"),
        "checks": [
            {
                "id": check.get("id"),
                "status": check.get("status"),
                "severity": check.get("severity"),
                "message": check.get("message"),
                "artifact": (check.get("evidence") or {}).get("artifact")
                if isinstance(check.get("evidence"), dict)
                else None,
            }
            for check in checks
            if isinstance(check, dict)
        ],
        "notice": "Summary only; raw evidence and deterministic harness decide status.",
    }
    json.dump(summary, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
