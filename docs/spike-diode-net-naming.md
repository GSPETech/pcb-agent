# Diode net-naming spike

Status: `BLOCKED`. Spike not yet executed; requires Diode toolchain on a
Linux ext4 filesystem. Windows-native Diode remains blocked by OS error 1314
(symlink privilege).

Consequence for the harness: the adapter registry in
`src/pcb_agent/generated_testbench.py` is intentionally **empty**. Every
component kind therefore raises `GeneratorError`, and both `CONNECTIVITY` and
`SPECIFICATION` return `BLOCKED`. This is the correct fail-closed behaviour
until the mappings below are verified against captured Diode output.

## Question

To move from contract-coverage (phase A) to full pin-level netlist comparison
(phase B), the harness needs a deterministic mapping from the pin labels
declared in `expected-connectivity.json` (e.g. `R1.P1`, `D1.A`) to the names
Diode actually emits in its TestBench `module.nets()` output (e.g.
`("BlinkyTest__default.R1.R", "1")`).

Both the instance-path suffix and the pin name change depending on the
underlying generic module.

## Candidate mapping (NOT VERIFIED)

The harness repository carries
`fixtures/valid-blinky/tests/blinky_test.zen` which contains assertions
believed to reflect Diode 0.4.34 output for this project's reference schematic.
No captured raw JSON with a recorded SHA-256 exists in the repository, so none
of these rows may be treated as evidence.

| Component kind | Pin in contract | Candidate path suffix | Candidate pin name | Status |
|---|---|---|---|---|
| `resistor` (`@stdlib/generics/Resistor.zen`) | `P1` | `R` | `"1"` | `REQUIRES TEST` |
| `resistor` | `P2` | `R` | `"2"` | `REQUIRES TEST` |
| `led` (`@stdlib/generics/Led.zen`) | `A` | `LED` | `"A"` | `REQUIRES TEST` |
| `led` | `K` | `LED` | `"K"` | `REQUIRES TEST` |
| `capacitor` | unknown | unknown | unknown | `REQUIRES TEST` |
| `crystal` | unknown | unknown | unknown | `REQUIRES TEST` |

The TestBench name prefix `BlinkyTest__default.` appears to be composed from the
TestBench `name` (`BlinkyTest`) and the test case key (`default`). This is also
`REQUIRES TEST` until confirmed by varying both values.

## Property access API (NOT VERIFIED)

Property accessors are no longer hardcoded in the renderer. They are declared
per adapter as `value_accessor`, `package_accessor`, and `mpn_accessor`. An
adapter with `None` for a given accessor makes any populated contract value for
that field `BLOCKED`.

Candidate accessor forms, all `REQUIRES TEST`:

```text
components[REF].resistance.matches(VALUE)
components[REF].properties['package'].value == VALUE
```

`mpn` has no candidate accessor at all and must remain unsupported until
captured output proves one.

## Pull-up pin pair (NOT VERIFIED)

`required_pullup` verification needs to know which two logical pins form the
electrical pair for a component kind. This is declared as
`pullup_pin_pair` on the adapter.

| Component kind | Candidate pull-up pin pair | Status |
|---|---|---|
| `resistor` | `("P1", "P2")` | `REQUIRES TEST` |

Dictionary iteration order over `pins` must never be used as electrical
meaning. An adapter without a verified `pullup_pin_pair` makes any contract
declaring `required_pullup` for that kind `BLOCKED`.

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

## Why this is blocked

Two blockers:

1. **No WSL ext4 environment on the development machine used for the prior
   tasks.** Windows-native Diode is blocked by `SeCreateSymbolicLinkPrivilege`
   (OS error 1314). The spike requires running Diode, so it cannot run on
   Windows alone.
2. **No additional stdlib generic fixtures.** The current `valid-blinky`
   fixture only exercises Resistor and Led. Pin mappings for Capacitor,
   Crystal, and any future generic are unknown.

## Current harness behaviour

Because no mapping is verified, the adapter registry is empty and every
generated check fails closed:

| Gate | Status while spike is blocked |
|---|---|
| `CONTRACT` | PASS when contracts are valid |
| `DIODE_BUILD` | PASS or FAIL from the compiler |
| `ZENER_TEST` | PASS or FAIL from the locked TestBench |
| `CONNECTIVITY` | `BLOCKED` — unsupported component kind |
| `SPECIFICATION` | `BLOCKED` — unsupported component kind |

`src/pcb_agent/connectivity.py` and `src/pcb_agent/specification_check.py`
still compute source-level coverage, but only as advisory diagnostics. They
never determine a required check status. Their function names carry the
`advisory_` prefix to make this explicit.

## Unblocking procedure

1. Run the experiment above on WSL ext4.
2. Capture the exact output of `pcb --version`. The probe in
   `diode.probe_pcbc_version` matches `pcbc <major>.<minor>.<patch>` and
   returns `BLOCKED` on anything else, so if the real banner differs the
   pattern must be corrected against captured output, never loosened to accept
   arbitrary text.
3. Store each raw JSON under `tests/evidence/diode-<version>/` with a SHA-256
   manifest.
4. Build the registry with `build_adapter_registry`, which keys entries by
   `kind`. Each `ComponentAdapter` needs:
   - `kind` matching the value used in `expected-connectivity.json`
   - `instance_suffix` observed in the captured component path
   - the exact `pcbc` version in `verified_pcbc_versions`
   - the evidence SHA-256 in `evidence_sha256`
   - `value_accessor` and `package_accessor` only if observed in captured output
   - `mpn_accessor` only if a real accessor exists; otherwise leave `None`.
     The generator currently blocks every `mpn` constraint regardless, so
     enabling it also requires emitting an assertion in
     `render_specification_testbench`.
   - `pullup_pin_pair` only if the electrical pair is observed, never inferred
     from `pins` iteration order
5. Install it with `set_adapter_registry`.
6. Verify `fixtures/valid-blinky` reaches `CONNECTIVITY: PASS` and
   `SPECIFICATION: PASS`.
7. Verify `fixtures/invalid-connectivity` and `fixtures/invalid-value` reach
   `FAIL` and not `BLOCKED`.
8. Replace every `REQUIRES TEST` row above with `VERIFIED`.

Registering an adapter without captured evidence is exactly the kind of "guess
the netlist schema" behaviour the agent protocol forbids. Leave the registry
empty rather than populating it from inference.

`tests/test_green_run.py` registers a stub adapter to exercise the PASS path.
That stub is test-only and must never be promoted into the production registry.
