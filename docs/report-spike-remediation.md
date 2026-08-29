# Spike Evidence Remediation — Execution Report

Date: 2026-08-29
Branch: `feat/diode-adapter-registry`
PR: https://github.com/GSPETech/pcb-agent/pull/5
Status: `PARTIAL` — artifact bundle complete, source provenance incomplete

This report documents the remediation of every evidence and provenance finding
from the final review of the Diode net-naming spike, as specified in
`REVIEW_REMEDIATION_PLAN_V4.md`.

## Summary

The prior spike evidence bundle was incomplete: it hashed only three result
JSONs, referenced missing artifacts, overclaimed crystal, and lacked
environment/version/source provenance. Most findings were remediated by
re-running the real Diode toolchain on WSL2 ext4 and retaining a complete
hash-bound bundle under `tests/evidence/diode-0.4.40/`.

One finding remains open: the retained `repo-revision.txt` records commit
`ca11826`, but the required evidence inputs first appear in the later commit
`68d96a3`. The executed source revision therefore cannot be pinned to the
committed inputs from a clean tree. The status stays `PARTIAL` until the
bundle is re-captured from a clean tracked revision or the report is
permanently downgraded.

## Task-by-task remediation

| Task | Work done | Commit |
|---|---|---|
| 0 | Downgraded docs to `PARTIAL`; marked crystal observed-unsupported; narrowed net-order/prefix claims to observed evidence | `ca11826` |
| 1 | Initial evidence layout and captures (environment, locked, spike, prefix, green-real, negatives, production-expression) | `68d96a3` |
| 2 | Implemented `_tool_versions()` in cli.py; reports now carry exact `pcb`/`pcbc` versions; added tests | `08cfa63` |
| 3 | Retained exact locked and spike inputs (source, TestBench, contracts) and bound results to sources | `68d96a3` |
| 4 | Renderer byte-binding work: bound the specification renderer output to the retained production-generated source by test | `81010b9` |
| 5 | Kept crystal absent from production registry; added fail-closed tests (`GeneratorError`) | `2b22fd2` |
| 6 | Captured `RenamedBench__alt_case` prefix-variation evidence under `prefix/` | `68d96a3` |
| 7 | Captured negative real-toolchain runs for invalid-syntax/connectivity/value with reports + run dirs | `68d96a3` |
| 8 | Built committed `fixtures/green-real`; full PASS with complete run directory retained | `68d96a3` |
| 9 | Added `src/pcb_agent/evidence.py` manifest loader + provenance validation; fails closed on missing file/manifest entry/digest/version mismatch/duplicate kind | `2b22fd2` |
| 10 | Narrowed net-order claim to defensive design language (membership + count, ordering not assumed) | `ca11826` |
| 11 | Added `.sanitized.json` publication companions (path fields only); raw evidence kept byte-identical | `2b22fd2` |
| 12 | Rebuilt `manifest.sha256` deterministically; added `test_evidence_bundle.py` completeness tests | `2b22fd2` |
| 13 | Finalized README, `docs/report-spike-execution.md`, and `docs/spike-diode-net-naming.md` only | `20f9a9c` |

Follow-up CI fixes:
- `31aaf79`: re-enabled tracking of `verify-report.json`/`.md` under `tests/evidence/` (global `.gitignore` had silently excluded them).
- `a850a4b`: `.gitattributes -text` for `tests/evidence/**` so Windows checkouts cannot alter evidence bytes and break manifest hashes.

The table above is attribution history. It is not a claim that any single commit
alone produced the production-expression captures; those are being re-run from a
clean tracked revision as part of the remaining remediation.

## Evidence inventory

All under `tests/evidence/diode-0.4.40/` (126 artifacts, `manifest.sha256`
`sha256sum -c` clean):

- `environment.txt` — pwd, git commit, uname, /etc/os-release, findmnt (ext4), `command -v pcb`
- `pcb-version.txt` — exact `pcbc 0.4.40`
- `repo-revision.txt` — git commit recorded at capture time
- `commands.json` — command + metadata locations for every run
- `valid-blinky/` — locked TestBench source, module source, contracts, raw result, command/exit/stderr
- `spike-generics/` — evidence TestBench source, module source, pcb.toml, raw result
- `prefix/` — `RenamedBench__alt_case` TestBench source + raw result
- `green-real/` — full `pcb-agent verify` report, complete run directory (`run/`), source/contract copies
- `production-expression/` — exact production-generated connectivity + specification testbenches and raw results
- `negative-invalid-syntax/`, `negative-invalid-connectivity/`, `negative-invalid-value/` — verify reports + run dirs + raw artifacts
- `.sanitized.json` companions — path fields rewritten for publication; raw files authoritative

`commands.json` and the per-run metadata files are being replaced with exact
executed argv/cwd/executable/exit/timestamp/revision records; the current
`production-expression` entry is a placeholder until the re-run completes.

## Registered vs blocked kinds

Registered (verified against pcbc 0.4.40): `resistor`, `led`, `capacitor`,
`inductor`, `ferrite_bead`, `thermistor`, `zener`, `rectifier`, `tvs`.

Blocked/unsupported: `crystal` (adapter model cannot represent the one-to-many
four-pin GND mapping), `opamp`, `PinHeader`, `SolderJumper`, `TestPoint`,
`NetTie`, `MountingHole`, `Fiducial`, `QR`, `Version`, and all `mpn`
constraints. Crystal pin mappings are captured observations only and are not
registered.

## Verification

- Local pytest: passed (operator-reported; exact counts not yet retained)
- pyright: 0 errors
- `sha256sum -c manifest.sha256`: 126/126 OK
- Real pcbc 0.4.40 (operator-reported):
  - `fixtures/green-real` → **PASS** (CONTRACT, DIODE_BUILD, ZENER_TEST, CONNECTIVITY, SPECIFICATION); report `versions` populated
  - `invalid-syntax` → DIODE_BUILD FAIL, dependent gates BLOCKED, overall BLOCKED
  - `invalid-connectivity` → ZENER_TEST FAIL, generated gates BLOCKED (prerequisite), overall BLOCKED
  - `invalid-value` → ZENER_TEST FAIL, generated gates BLOCKED (prerequisite), overall BLOCKED
- PR CI: all green (Ubuntu + Windows, Python 3.11 + 3.13, typecheck)
- `production_ready` and `fabrication_approved` remain `false` in every report

Exact pass/skip/subtest counts are not claimed here yet; they will be backed by
retained verification transcripts before the report is marked `COMPLETE`.

## Residual limitations

- The executed source revision is not yet pinned to a clean tracked commit;
  `repo-revision.txt` records `ca11826`, but the required inputs first appear
  in `68d96a3`. The bundle must be re-captured from a clean commit (or the
  report permanently downgraded).
- `validate_captured_registry()` is now enforced lazily on the first generated
  TestBench use (`ensure_registry_provenance()`); a failed validation empties
  the adapter registry so generated gates report `BLOCKED`. This is covered by
  tests but has not yet been exercised in a real re-run.
- Crystal pin mappings are captured observations only; production support
  requires a package/variant-discriminated adapter model with one-to-many
  emitted pins.
- `mpn` has no captured accessor and remains BLOCKED.
- Net member ordering stability is not claimed as empirically verified; the
  generator defensively asserts membership + count.
- Green-real uses six buildable kinds (resistor, led, capacitor, inductor,
  ferrite_bead, tvs); thermistor/zener/rectifier stdlib generics fail
  `pcb build` BOM part-info checks, so their exact package/value expressions
  are proven via the `production-expression` run instead.
