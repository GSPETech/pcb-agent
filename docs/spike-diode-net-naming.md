# Diode net-naming spike

Status: `DEFERRED`. Spike not yet executed; awaiting Diode toolchain on a
Linux ext4 filesystem.

## Question

To move from contract-coverage (phase A) to full pin-level netlist comparison
(phase B), the harness needs a deterministic mapping from the pin labels
declared in `expected-connectivity.json` (e.g. `R1.P1`, `D1.A`) to the names
Diode actually emits in its TestBench `module.nets()` output (e.g.
`("BlinkyTest__default.R1.R", "1")`).

Both the instance-path suffix and the pin name change depending on the
underlying generic module.

## Empirical observation (informal)

The harness repository carries
`fixtures/valid-blinky/tests/blinky_test.zen` which contains assertions against
the actual output of Diode 0.4.34 against this project's reference schematic.

Observed mapping (status `LIKELY BUT NOT VERIFIED` for the LED half):

| Component kind | Pin in contract | Path suffix Diode emits | Pin name Diode emits |
|---|---|---|---|
| `resistor` (`@stdlib/generics/Resistor.zen`) | `P1` | `R` | `"1"` |
| `resistor` | `P2` | `R` | `"2"` |
| `led` (`@stdlib/generics/Led.zen`) | `A` | `LED` | `"A"` |
| `led` | `K` | `LED` | `"K"` |

The TestBench name prefix `BlinkyTest__default.` is composed from the
TestBench `name` (`BlinkyTest`) and the test case key (`default`). Both are
declared in `tests/*.zen`, so the prefix is fully predictable from the
TestBench source.

## Required experiment

On WSL2 (Diode Windows-native remains blocked by OS error 1314):

1. Copy this repository to the WSL ext4 filesystem.
2. Run `pcb test tests/blinky_test.zen -f json` against
   `fixtures/valid-blinky`.
3. Capture the JSON output, store SHA-256.
4. Repeat with a board that instantiates each remaining stdlib generic
   (`Capacitor.zen`, `Crystal.zen`, and any others present in
   `fixtures/valid-blinky/.pcb/stdlib/generics/`).
5. Record the observed `(kind, pin_contract) -> (suffix, pin_diode)` table
   for every generic.
6. Confirm or refute the hypothesis that the prefix is always
   `{TestBenchName}__{case_key}.`.

## Required artifact

A document under `docs/` that includes:

- `pcb` and `pcbc` versions actually used.
- Date the spike ran.
- SHA-256 of each captured raw JSON.
- The mapping table with one of three statuses per row:
  - `VERIFIED` — observed directly in the captured output.
  - `LIKELY BUT NOT VERIFIED` — inferred from `.zen` source but not observed.
  - `REQUIRES TEST` — cannot be determined from current fixtures.
- A verdict on whether automatic TestBench generation from
  `expected-connectivity.json` is feasible, or whether the harness should
  keep phase A as the permanent strategy.

## Why this is deferred

Two blockers:

1. **No WSL ext4 environment on the development machine used for the prior
   tasks.** Windows-native Diode is blocked by `SeCreateSymbolicLinkPrivilege`
   (OS error 1314). The spike requires running Diode, so it cannot run on
   Windows alone.
2. **No additional stdlib generic fixtures.** The current `valid-blinky`
   fixture only exercises Resistor and Led. Pin mappings for Capacitor,
   Crystal, and any future generic are unknown.

## What phase A already covers

Until this spike resolves, the harness still enforces the contract-coverage
invariant: every net name and component reference declared in
`expected-connectivity.json` must appear as a literal in the locked TestBench
source. A test that changes the contract without updating the TestBench is
caught with status `FAIL`. This is implemented in
`src/pcb_agent/connectivity.py` and covered by
`tests/test_connectivity.py`.

Phase A deliberately stops short of generating a TestBench. Inventing the
pin mapping table is exactly the kind of "guess the netlist schema"
behavior the agent protocol forbids.