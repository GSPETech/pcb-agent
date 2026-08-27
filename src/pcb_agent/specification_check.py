"""Specification constraint coverage checks against the locked TestBench."""

from __future__ import annotations

from typing import Any, Mapping


def specification_failures(
    specification: Mapping[str, Any],
    acceptance: Mapping[str, Any],
    testbench_source: str,
) -> tuple[str, ...]:
    """Return sorted failure messages; empty tuple means fully covered."""
    failures: list[str] = []
    requirements = specification.get("requirements", [])
    checks = acceptance.get("checks", [])

    check_kinds_by_requirement: dict[str, list[str]] = {}
    check_tests_by_requirement: dict[str, list[str]] = {}
    for item in checks:
        requirement_id = item.get("requirement")
        if not isinstance(requirement_id, str):
            continue
        kind = item.get("kind")
        if isinstance(kind, str):
            check_kinds_by_requirement.setdefault(requirement_id, []).append(kind)
        test_name = item.get("test")
        if isinstance(test_name, str):
            check_tests_by_requirement.setdefault(requirement_id, []).append(test_name)

    for requirement in requirements:
        if not isinstance(requirement, dict):
            continue
        rid = requirement.get("id")
        if not isinstance(rid, str):
            continue

        constraints = requirement.get("constraints")
        if isinstance(constraints, Mapping) and constraints:
            kinds = check_kinds_by_requirement.get(rid, [])
            if "zener_test" not in kinds:
                failures.append(
                    f"requirement {rid} has constraints but only diode_build acceptance; "
                    f"needs zener_test verification"
                )
                continue

            for key, value in constraints.items():
                if not isinstance(value, str):
                    continue
                if value and value not in testbench_source:
                    failures.append(
                        f"requirement {rid} constraint {key}={value!r} "
                        f"not asserted in TestBench"
                    )

        subject = requirement.get("subject")
        if isinstance(subject, str) and subject:
            if subject not in testbench_source:
                failures.append(
                    f"requirement {rid} subject {subject!r} not asserted in TestBench"
                )

    for test_name in check_tests_by_requirement.values():
        for full in test_name:
            if "." not in full:
                continue
            short = full.split(".", 1)[1]
            if short and short not in testbench_source:
                failures.append(
                    f"acceptance test references function not found in TestBench: {full}"
                )

    return tuple(sorted(failures))