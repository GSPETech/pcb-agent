"""Advisory source coverage only. Must never determine CONNECTIVITY PASS."""

from __future__ import annotations

from typing import Any, Mapping


def advisory_coverage_findings(
    connectivity: Mapping[str, Any], testbench_source: str
) -> tuple[str, ...]:
    """Return sorted advisory messages; empty tuple means statically covered."""
    failures: list[str] = []
    components = connectivity.get("components", {})
    nets = connectivity.get("nets", {})
    rules = connectivity.get("rules", {})

    for reference in components:
        if reference not in testbench_source:
            failures.append(f"component reference not asserted in TestBench: {reference}")

    for net in nets:
        if net not in testbench_source:
            failures.append(f"net not asserted in TestBench: {net}")

    for power_net in rules.get("required_power_nets", []):
        if power_net not in nets:
            failures.append(
                f"required_power_nets references undeclared net: {power_net}"
            )

    return tuple(sorted(failures))