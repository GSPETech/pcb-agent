# Diode net-naming spike

Status: `COMPLETE`. The net-naming experiment was executed against real Diode
`pcbc 0.4.40` on WSL2 ext4 on 2026-08-29. Every claim below is backed by
hash-bound retained source + result artifacts under
`tests/evidence/diode-0.4.40/` (see `manifest.sha256`), and the production
adapter registry in `src/pcb_agent/generated_testbench.py` is validated lazily
against that bundle on the first generated TestBench use via
`ensure_registry_provenance()`. A failed validation empties the adapter
registry, so generated gates fail closed; `doctor` and `build` never trigger
the check.

## Question

To move from contract-coverage (phase A) to full pin-level netlist comparison
(phase B), the harness needs a deterministic mapping from the pin labels
declared in `expected-connectivity.json` (e.g. `R1.P1`, `D1.A`) to the names
Diode actually emits in its TestBench `module.nets()` output (e.g.
`("BlinkyTest__default.R1.R", "1")`).

Both the instance-path suffix and the pin name change depending on the
underlying generic module.

## Captured evidence

All raw output was produced by the real `pcb` toolchain in WSL2 Ubuntu-24.04
on an ext4 filesystem. Exact tool version, environment, and source revision are
retained:

| Artifact | Purpose |
|---|---|
| `tests/evidence/diode-0.4.40/environment.txt` | pwd, git commit, uname, /etc/os-release, findmnt (ext4), command -v pcb |
| `tests/evidence/diode-0.4.40/pcb-version.txt` | exact `pcbc 0.4.40` output |
| `tests/evidence/diode-0.4.40/repo-revision.txt` | exact git commit of executed source |
| `tests/evidence/diode-0.4.40/commands.json` | every run's command + metadata location |

The full digest manifest (`manifest.sha256`, `sha256sum -c` clean) lists every
retained artifact exactly once with a matching hash.

### Run directories

| Directory | Content |
|---|---|
| `valid-blinky/` | locked TestBench source, module source, contracts, raw `pcb test` JSON, command/exit/stderr |
| `spike-generics/` | evidence TestBench source, module source, pcb.toml, raw result JSON |
| `prefix/` | `RenamedBench__alt_case` TestBench source + raw result |
| `green-real/` | full `pcb-agent verify` report, complete run directory (`run/`), source/contract copies |
| `production-expression/` | exact production-generated connectivity + specification testbenches and their raw results, plus source/contracts |
| `negative-invalid-syntax/` | verify report + run dir + raw artifacts |
| `negative-invalid-connectivity/` | verify report + run dir + raw artifacts |
| `negative-invalid-value/` | verify report + run dir + raw artifacts |

Raw JSON output contains machine-local paths (`/home/rendra/...`,
`/tmp/pcb-agent-...`). Raw files are kept byte-identical and authoritative.
`.sanitized.json` companions rewrite only path fields for publication and are
diagnostic only.

## Verified mapping table

Every row below was observed directly in captured raw output. Status legend:
`VERIFIED` = observed in captured JSON and supported by the production adapter
registry; `OBSERVED — unsupported` = observed in captured JSON but not
representable by the current adapter model; `REQUIRES TEST` = not yet observed.

**Crystal rows are `OBSERVED — unsupported`.** `captured_adapter_registry()`
does not register crystal. The current `ComponentAdapter.pins` model supports
one emitted pin per contract pin, but a 4-pin crystal's GND maps to both
`GND_2` and `GND_4`; a single adapter cannot represent this one-to-many
mapping. Crystal contracts therefore return `BLOCKED` until the adapter model
gains package/variant discrimination and one-to-many pin support.

| Component kind | Pin in contract | Diode path suffix | Diode pin name | Status |
|---|---|---|---|---|
| `resistor` (`@stdlib/generics/Resistor.zen`) | `P1` | `R` | `"1"` | `VERIFIED` |
| `resistor` | `P2` | `R` | `"2"` | `VERIFIED` |
| `led` (`@stdlib/generics/Led.zen`) | `A` | `LED` | `"A"` | `VERIFIED` |
| `led` | `K` | `LED` | `"K"` | `VERIFIED` |
| `capacitor` (`@stdlib/generics/Capacitor.zen`) | `P1` | `C` | `"1"` | `VERIFIED` |
| `capacitor` | `P2` | `C` | `"2"` | `VERIFIED` |
| `crystal` (`@stdlib/generics/Crystal.zen`, 2-pin) | `XIN` | `Y` | `"1"` | `OBSERVED — unsupported` |
| `crystal` (2-pin) | `XOUT` | `Y` | `"2"` | `OBSERVED — unsupported` |
| `crystal` (4-pin) | `XIN` | `Y` | `"XIN"` | `OBSERVED — unsupported` |
| `crystal` (4-pin) | `XOUT` | `Y` | `"XOUT"` | `OBSERVED — unsupported` |
| `crystal` (4-pin) | `GND` | `Y` | `"GND_2"` / `"GND_4"` | `OBSERVED — unsupported` |
| `inductor` (`@stdlib/generics/Inductor.zen`) | `P1` | `L` | `"1"` | `VERIFIED` |
| `inductor` | `P2` | `L` | `"2"` | `VERIFIED` |
| `ferrite_bead` (`@stdlib/generics/FerriteBead.zen`) | `P1` | `FB` | `"1"` | `VERIFIED` |
| `ferrite_bead` | `P2` | `FB` | `"2"` | `VERIFIED` |
| `thermistor` (`@stdlib/generics/Thermistor.zen`) | `P1` | `TH` | `"1"` | `VERIFIED` |
| `thermistor` | `P2` | `TH` | `"2"` | `VERIFIED` |
| `zener` (`@stdlib/generics/Zener.zen`) | `A` | `D` | `"A"` | `VERIFIED` |
| `zener` | `K` | `D` | `"K"` | `VERIFIED` |
| `rectifier` (`@stdlib/generics/Rectifier.zen`) | `A` | `D` | `"A"` | `VERIFIED` |
| `rectifier` | `K` | `D` | `"K"` | `VERIFIED` |
| `tvs` (`@stdlib/generics/Tvs.zen`, unidirectional) | `A` | `D` | `"A"` | `VERIFIED` |
| `tvs` (unidirectional) | `K` | `D` | `"K"` | `VERIFIED` |
| `opamp` (`@stdlib/generics/OperationalAmplifier.zen`) | — | `U` | — | `REQUIRES TEST` (generic is deprecated; pins `+`, `-`, `V+`, `V-`, `5`) |
| `PinHeader`, `SolderJumper`, `TestPoint`, `NetTie`, `MountingHole`, `Fiducial`, `QR`, `Version` | — | — | — | `REQUIRES TEST` |

The TestBench name prefix is always `{TestBenchName}__{case_key}.`. This was
confirmed by varying both values with real pcbc 0.4.40 and is proven by the
retained `RenamedBench__alt_case` run:

- `valid-blinky/valid-blinky.json` → `BlinkyTest__default.`
- `spike-generics/spike-generics.json` → `SpikeAllGenerics__default.`
- `prefix/prefix-renamed-alt-case.json` → `RenamedBench__alt_case.`

## Property access API (VERIFIED)

Accessors are declared per adapter as `value_accessor`, `package_accessor`, and
`mpn_accessor`. An adapter with `None` for a given accessor makes any populated
contract value for that field `BLOCKED`.

Observed and verified accessor forms:

| kind | `value_accessor` | verified against | `package_accessor` |
|---|---|---|---|
| `resistor` | `resistance` | `"1kohm"` via `.matches` | `properties['package']` |
| `capacitor` | `capacitance` | `"100nF"` via `.matches` | `properties['package']` |
| `inductor` | `inductance` | `"10uH"` via `.matches` | `properties['package']` |
| `ferrite_bead` | `impedance` | `"220ohm"` via `.matches` | `properties['package']` |
| `thermistor` | `resistance` | `"10kohm"` via `.matches` | `properties['package']` |
| `crystal` | `frequency` | `"8MHz"` via `.matches` | `properties['package']` |
| `zener` | `zener_voltage` | `"3.3V"` via `.matches` | `properties['package']` |
| `rectifier` | `reverse_voltage` | `"40V"` via `.matches` | `properties['package']` |
| `tvs` | `reverse_standoff_voltage` | `"5V"` via `.matches` | `properties['package']` |
| `led` | `None` (unsupported / not captured) | — | `properties['package']` |

The exact production package expression
`components["<ref>"].properties['package'].value == "<expected>"` was executed
against real pcbc 0.4.40 for every registered kind and passed; the exact
generated sources and raw results are retained under
`production-expression/` and bound to the renderer by
`tests/test_captured_registry.py`.

`mpn` has no captured accessor in any observed output, so `mpn_accessor` stays
`None` for every adapter and `mpn` constraints remain `BLOCKED`.

## Pull-up pin pair (VERIFIED)

`required_pullup` verification needs to know which two logical pins form the
electrical pair for a component kind. This is declared as `pullup_pin_pair` on
the adapter.

| Component kind | Verified pull-up pin pair | Status |
|---|---|---|
| `resistor` | `("P1", "P2")` | `VERIFIED` |

Every other kind keeps `pullup_pin_pair = None`, so a contract declaring
`required_pullup` for any unverified kind is `BLOCKED`. Dictionary iteration
order over `pins` is never used as electrical meaning.

## Important observed behaviour

- `module.components()` keys carry **no** TestBench prefix (`R1.R`, `D1.LED`),
  while `module.nets()` members **do** carry it
  (`("PcbAgentConnectivity__contract.R1.R", "1")`). The generator uses the
  unprefixed ref for `components[...]` lookups and the prefixed ref for net
  membership, matching the locked `blinky_test.zen` assertions.
- Net member ordering inside a net is **not assumed stable**; the generator
  asserts each member by membership, and `forbid_unlisted_members` asserts
  count, not order. This is a defensive design choice; ordering instability is
  not claimed as an empirically verified result.
- `crystal` pin names depend on package: 2-pin crystals expose `"1"`/`"2"`,
  4-pin crystals expose `"XIN"`/`"XOUT"`/`"GND_2"`/`"GND_4"`. Adapters are
  keyed by `kind`, so a single adapter cannot represent both the two-pin and
  four-pin variants, and the four-pin GND one-to-many mapping in particular.
  Crystal is **not registered** in the production registry; crystal contracts
  fail closed with `BLOCKED`.

## Verdict

Automatic TestBench generation from `expected-connectivity.json` is **feasible
and now enabled for the registered kinds** (`resistor`, `led`, `capacitor`,
`inductor`, `ferrite_bead`, `thermistor`, `zener`, `rectifier`, `tvs`). With the
captured registry installed and pcbc 0.4.40 on PATH, `pcb-agent verify` on the
committed `fixtures/green-real` project produces a full `PASS`:

| Gate | Result (green-real, pcbc 0.4.40) |
|---|---|
| `CONTRACT` | PASS |
| `DIODE_BUILD` | PASS |
| `ZENER_TEST` | PASS |
| `CONNECTIVITY` | PASS |
| `SPECIFICATION` | PASS |

The complete report and run directory are retained under
`tests/evidence/diode-0.4.40/green-real/`, including every raw artifact the
report references (`diode_build.json`, `zener_test.json`, generated testbenches,
result JSONs), each with a matching manifest hash. `production_ready` and
`fabrication_approved` remain `false`; `human_review_required` is `true`.

### Negative behaviour (real pcbc 0.4.40)

| Fixture | DIODE_BUILD | ZENER_TEST | CONNECTIVITY | SPECIFICATION | Overall |
|---|---|---|---|---|---|
| `invalid-syntax` | FAIL | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| `invalid-connectivity` | PASS | FAIL | BLOCKED (prerequisite) | BLOCKED (prerequisite) | BLOCKED |
| `invalid-value` | PASS | FAIL | BLOCKED (prerequisite) | BLOCKED (prerequisite) | BLOCKED |

Reports and raw artifacts for all three are retained under
`tests/evidence/diode-0.4.40/negative-*/`. A generated gate is reported as
`FAIL` only when it actually ran and found a mismatch; when the locked TestBench
fails first, dependent generated gates are `BLOCKED` because no evidence was
collected.

## Registry provenance

Every production adapter binds an exact result evidence file, an exact
assertion source file, and exact digests; `validate_captured_registry()` fails
closed if any referenced artifact is missing, missing from the manifest, hashed
differently on disk, or version-mismatched. Tests
(`tests/test_captured_registry.py`, `tests/test_evidence_bundle.py`) cover the
exact kind set, per-adapter fields, crystal absence, manifest completeness,
report-artifact resolution, and safety-field invariants.

## Unregistered kinds and fail-closed behaviour

Kinds with `REQUIRES TEST` rows above have no adapter. Any contract that
declares one raises `GeneratorError` during generation, and both generated
gates return `BLOCKED`. This is the correct fail-closed behaviour; do not
populate an adapter from inference. `mpn` constraints are likewise `BLOCKED`
until a real accessor is captured.

`tests/test_green_run.py` registers a stub adapter to exercise the PASS path in
CI where the real toolchain is absent. That stub is test-only; the production
registry in `src/pcb_agent/generated_testbench.py` is built from the captured
evidence above via `captured_adapter_registry()`.
