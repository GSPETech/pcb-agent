# Diode Net-Naming Spike — Execution Report

Date: 2026-08-29
Branch: `feat/diode-adapter-registry`
PR: https://github.com/GSPETech/pcb-agent/pull/5
Status: `COMPLETE`

All claims in this report are backed by hash-bound retained source + result
artifacts under `tests/evidence/diode-0.4.40/` (`manifest.sha256` passes
`sha256sum -c`), and the production adapter registry is validated lazily
against that bundle on the first generated TestBench use.

The evidence bundle was re-captured from a clean tracked commit (`ff1b472`) on
WSL2 ext4 against the real `pcbc 0.4.40` toolchain; the executed revision and
clean `git status` are recorded per run in `capture-provenance.json`,
`commands.json`, and each run directory's `run-provenance.json`. See
`docs/report-spike-remediation.md`.

## Task

Execute the Diode net-naming spike documented in `docs/spike-diode-net-naming.md`
to completion: capture real Diode output, verify the net-mapping hypotheses, and
unblock automatic TestBench generation.

## Environment

- OS: WSL2 Ubuntu-24.04, Linux 6.6.114.1-microsoft-standard-WSL2, ext4 filesystem
- Toolchain: real Diode `pcbc 0.4.40` (`/home/rendra/.local/bin/pcb`)
- Repo synced from Windows workspace into WSL ext4 (`/home/rendra/pcbagent-full`)
- Retained: `tests/evidence/diode-0.4.40/environment.txt`,
  `pcb-version.txt`, `repo-revision.txt`

## What was done

1. Verified WSL ext4 + real Diode toolchain (the former blocker).
2. Ran the locked `valid-blinky` TestBench through real `pcb test -f json`
   → PASS, captured source + result + SHA-256.
3. Built spike fixtures (`fixtures/spike-generics/`) exercising the remaining
   stdlib generics: capacitor, crystal (2-pin and 4-pin), inductor, ferrite
   bead, thermistor, zener, rectifier, tvs.
4. Probed live `module.components()` / `module.nets()` output and the property
   accessor API (`value_accessor`, `package_accessor`).
5. Confirmed the prefix hypothesis `{TestBenchName}__{case_key}.` by varying
   both values; retained as `prefix/prefix-renamed-alt-case.json`.
6. Captured all evidence under `tests/evidence/diode-0.4.40/` with a
   `manifest.sha256` (144 artifacts, all hashes verify on Windows and WSL).
7. Built the production adapter registry (`captured_adapter_registry()`) from
   the captured evidence, with exact result/source path + digest bindings.
8. Ran `pcb-agent verify` end-to-end against the real toolchain:
   - Committed `fixtures/green-real` → full PASS (CONNECTIVITY + SPECIFICATION).
   - Negative fixtures fail closed; reports + raw artifacts retained.
9. Executed the exact production-generated connectivity and specification
   testbenches (byte-identical to the current renderer) against real Diode for
   every registered kind; results pass and are retained.

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
  design choice, not an empirically verified claim.

## Verified mapping table (real pcbc 0.4.40)

Registered kinds in the production registry: `resistor`, `led`, `capacitor`,
`inductor`, `ferrite_bead`, `thermistor`, `zener`, `rectifier`, `tvs`.
Crystal is **not** registered (the `ComponentAdapter.pins` model cannot
represent its one-to-many four-pin GND mapping); its rows are captured
observations, not production-supported mappings.

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
`spike-generics/spike-generics.json` but are **not** production adapter support.
The current adapter model cannot represent the one-to-many GND mapping, so
crystal remains `BLOCKED / REQUIRES IMPLEMENTATION`.

## Evidence inventory

- Environment: `environment.txt`, `pcb-version.txt` (`pcbc 0.4.40`),
  `repo-revision.txt`
- Capture provenance: `capture-provenance.json`, `commands.json`, per-run
  `run-provenance.json`, retained `scripts/`
- `valid-blinky/`: source, TestBench, contracts, raw result, exit/stderr
- `spike-generics/`: evidence TestBench + module source, raw result
- `prefix/`: `RenamedBench__alt_case` TestBench + raw result
- `green-real/`: full verify report + complete run directory + source/contracts
- `production-expression/`: exact production-generated testbenches + raw results
- `negative-invalid-syntax/`, `negative-invalid-connectivity/`,
  `negative-invalid-value/`: verify reports + run dirs + raw artifacts
- `verification/`: retained Windows/WSL pytest, pyright, and manifest transcripts
- `.sanitized.json` companions for publication (path fields only rewritten)
- `manifest.sha256`: 144 artifacts, all hashes verified

## Verification

- Windows pytest: 249 passed, 14 skipped, 395 subtests passed
- WSL pytest: 263 passed, 404 subtests passed
- pyright: 0 errors
- `sha256sum -c manifest.sha256`: all OK
- Real toolchain (pcbc 0.4.40): `fixtures/green-real` → all required gates PASS;
  invalid-syntax/invalid-connectivity/invalid-value → BLOCKED fail-closed with
  retained reports
