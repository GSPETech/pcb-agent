# Diode Net-Naming Spike — Execution Report

Date: 2026-08-29
Branch: `feat/diode-adapter-registry`
PR: https://github.com/GSPETech/pcb-agent/pull/5
Status: `PARTIAL — execution completed, provenance bundle incomplete`

This report is **not** safe to treat as a complete audit trail. Several claims
below (prefix variation, net-order instability, negative fixture behavior, and
the real green PASS) are awaiting retained provenance: hash-bound source +
result artifacts in `tests/evidence/diode-0.4.40/`. Remediation tasks in
`REVIEW_REMEDIATION_PLAN_V4.md` track closing those gaps.

## Task

Execute the Diode net-naming spike documented in `docs/spike-diode-net-naming.md`
to completion: capture real Diode output, verify the net-mapping hypotheses, and
unblock automatic TestBench generation.

## Environment

- OS: WSL2 Ubuntu-24.04, Linux 6.6.114.1-microsoft-standard-WSL2, ext4 filesystem
- Toolchain: real Diode `pcbc 0.4.40` (`/home/rendra/.local/bin/pcb`)
- Repo synced from Windows workspace into WSL ext4 (`/home/rendra/pcbagent-full`)

## What was done

1. Verified WSL ext4 + real Diode toolchain (the former blocker).
2. Ran the locked `valid-blinky` TestBench through real `pcb test -f json`
   → PASS, captured output + SHA-256.
3. Built spike fixtures (`fixtures/spike-generics/`) exercising the remaining
   stdlib generics: capacitor, crystal (2-pin and 4-pin), inductor, ferrite
   bead, thermistor, zener, rectifier, tvs.
4. Probed live `module.components()` / `module.nets()` output and the property
   accessor API (`value_accessor`, `package_accessor`).
5. Confirmed the prefix hypothesis `{TestBenchName}__{case_key}.` by varying
   both values. **Pending:** a dedicated prefix-evidence artifact
   (`RenamedBench__alt_case`) is not yet retained in the evidence bundle.
6. Captured all evidence under `tests/evidence/diode-0.4.40/` with a
   `manifest.sha256`.
7. Built the production adapter registry (`captured_adapter_registry()`) from
   the captured evidence.
8. Ran `pcb-agent verify` end-to-end against the real toolchain:
   - Real green project → `CONNECTIVITY: PASS`, `SPECIFICATION: PASS`.
     **Pending:** the retained `green-real-report.json` references raw artifacts
     (`diode_build.json`, `zener_test.json`, generated testbenches, result
     JSONs) that are not yet committed under `tests/evidence/diode-0.4.40/`;
     the report contract hashes do not match `fixtures/valid-blinky`, and the
     green-real project fixture is not yet committed.
   - Negative fixtures fail closed (locked TestBench FAIL → dependent gates
     BLOCKED). **Pending:** no negative run/report artifacts are retained in the
     evidence bundle.

## Bugs found and fixed

- **Generator prefix bug** (`src/pcb_agent/generated_testbench.py`):
  `module.components()` keys carry **no** TestBench prefix (`R1.R`), while
  `module.nets()` members **do** (`PcbAgentConnectivity__contract.R1.R`). The
  generator previously used the prefixed ref for `components[...]` lookups,
  so real runs failed with `missing component`. Component existence,
  value, and package checks now use the unprefixed ref; net membership keeps
  the prefixed ref.
- **Net ordering**: the generator asserts membership + count and never list
  equality. Ordering stability across runs is not assumed; it is a defensive
  design choice, not an empirically verified claim. **Pending:** repeated
  captures showing changed ordering are not yet retained.

## Verified mapping table (real pcbc 0.4.40)

Only kinds listed below are present in the production adapter registry
(`captured_adapter_registry()` in `src/pcb_agent/generated_testbench.py`):
`resistor`, `led`, `capacitor`, `inductor`, `ferrite_bead`, `thermistor`,
`zener`, `rectifier`, `tvs`. Crystal is **not** in the production registry: the
current `ComponentAdapter.pins` model supports one emitted pin per contract pin,
but a 4-pin crystal's GND maps to both `GND_2` and `GND_4`. Crystal rows below
are captured observations, not production-supported mappings.

| kind | contract pin → diode pin | suffix | value_accessor | package_accessor |
|---|---|---|---|---|
| resistor | P1→"1", P2→"2" | R | resistance | properties['package'] |
| led | A→"A", K→"K" | LED | None (unsupported / not captured) | properties['package'] |
| capacitor | P1→"1", P2→"2" | C | capacitance | properties['package'] |
| inductor | P1→"1", P2→"2" | L | inductance | properties['package'] |
| ferrite_bead | P1→"1", P2→"2" | FB | impedance | properties['package'] |
| thermistor | P1→"1", P2→"2" | TH | resistance | properties['package'] |
| zener | A→"A", K→"K" | D | zener_voltage | properties['package'] |
| rectifier | A→"A", K→"K" | D | reverse_voltage | properties['package'] |
| tvs (unidirectional) | A→"A", K→"K" | D | reverse_standoff_voltage | properties['package'] |
| crystal 2-pin | XIN→"1", XOUT→"2" | Y | frequency | properties['package'] |
| crystal 4-pin | XIN→"XIN", XOUT→"XOUT", GND→"GND_2"/"GND_4" | Y | frequency | properties['package'] |

**Crystal note:** the two crystal rows are observed fixture behaviour in
`spike-generics.json` but are **not** production adapter support. The current
adapter model cannot represent the one-to-many GND mapping, so crystal remains
`BLOCKED / REQUIRES IMPLEMENTATION`.

## Evidence (SHA-256)

- `tests/evidence/diode-0.4.40/valid-blinky.json` → `02c6cb60bfaf371e640e34ed0ff7b707074cfad0789b38a25c014cfa66cfac11`
- `tests/evidence/diode-0.4.40/spike-generics.json` → `3320a8aa668f5f28dc19b4240f9f92e22333805ead12e36cb4c5a3c3b1636267`
- `tests/evidence/diode-0.4.40/green-real-report.json` → `54665c6f1140ec4fa31dad8c288429273ac5bbd1a7d09d91b11b013741bd6b91`

## Verification

- 185 passed, 14 skipped, 32 subtests passed
- pyright: 0 errors
- Real toolchain end-to-end: green project → all required gates PASS
