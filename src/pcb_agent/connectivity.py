"""Contract coverage checks against the locked TestBench source.

Phase A. Confirms every net and component reference declared in the expected
contract is actually asserted by the testbench that the harness treats as the
source of truth for schematic verification. Pin-level netlist comparison is
not yet implemented; see IMPLEMENTATION_PLAN.md task 14.
"""

from __future__ import annotations

from typing import Any, Mapping


def coverage_failures(
    connectivity: Mapping[str, Any], testbench_source: str
) -> tuple[str, ...]:
    """Return sorted failure messages; empty tuple means fully covered."""
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