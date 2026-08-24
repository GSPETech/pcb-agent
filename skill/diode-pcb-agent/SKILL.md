---
name: diode-pcb-agent
description: Use when creating, checking, repairing, or analyzing Diode/Zener PCB projects with pcb-agent, including schematic-as-code, connectivity, component values, layout, KiCad DRC, and bounded repair. Not for fabrication approval.
---

# Diode PCB Agent

Use `AGENT_PROTOCOL.md` as portable source of truth. This skill guides work; it
does not replace compiler, tests, connectivity checks, KiCad DRC, or engineer
review.

## Workflow

1. Confirm project has `pcb.toml` or `.zen` source. Otherwise stop
   `BLOCKED/UNSUPPORTED_PROJECT`.
2. Locate repository `pcb-agent` launcher first, then trusted PATH. If absent,
   stop `BLOCKED/HARNESS_MISSING`; do not install or invent validation.
3. Read protocol, `SPEC.json`, `ACCEPTANCE.json`, and
   `expected-connectivity.json`.
4. Run `pcb-agent doctor --format json`.
5. Edit only allowed Zener source. Preserve maintained layout unless layout
   scope is explicit.
6. Run `pcb-agent verify --format json` and inspect raw evidence.
7. Repair at most five times. Stop when result + diff fingerprint repeats.
8. Never edit acceptance, expected connectivity, tests, policy, schema,
   validator, or evidence to gain PASS.
9. Escalate `BLOCKED` and `HUMAN_REVIEW` without guessing.
10. Report `production_ready: false` and `fabrication_approved: false`.

## Progressive references

- Read `references/zener-workflow.md` before Zener source/build changes.
- Read `references/schematic-review.md` for topology, values, ratings, and
  datasheet review.
- Read `references/layout-review.md` only for layout/KiCad tasks.
- Read `references/failure-classification.md` when classifying status/exit.

Use `scripts/inspect-verification-report.py REPORT.json` to display a sanitized
summary. Script does not validate evidence or determine final PASS.
