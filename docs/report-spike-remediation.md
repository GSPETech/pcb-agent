# Spike Evidence Remediation — Execution Report

Date: 2026-08-29
Branch: `feat/diode-adapter-registry`
PR: https://github.com/GSPETech/pcb-agent/pull/5
Status: `COMPLETE`

This report documents the remediation of every evidence and provenance finding
from the final review of the Diode net-naming spike, as specified in
`REVIEW_REMEDIATION_PLAN_V4.md`.

## Summary

The prior spike evidence bundle was incomplete: it hashed only three result
JSONs, referenced missing artifacts, overclaimed crystal, and lacked
environment/version/source provenance. All findings are now remediated:

- The bundle is re-captured from a **clean tracked commit** (`ff1b472`) on WSL2
  ext4 against the real `pcbc 0.4.40` toolchain, and every run records its own
  executed revision and clean git status.
- `pcb-version.txt` is bound to the manifest and must be the exact single
  `pcbc <major>.<minor>.<patch>` record verified by every adapter.
- Registry provenance is enforced lazily before any generated TestBench use;
  a failed validation empties the adapter registry so generated gates fail
  closed, while `doctor` and `build` never trigger the check.
- Both generated renderers are byte-bound to retained production sources.
- The production-expression command metadata is a real retained executable,
  not a placeholder.
- Verification transcripts are retained for every exact count claimed.

## Source provenance

The evidence bundle was re-captured from a clean tree at commit
`ff1b4726b93d2e96cc73e229fba459ab0c76069b` (branch
`feat/diode-adapter-registry`) on WSL2 Ubuntu-24.04 ext4 with the real
`pcbc 0.4.40` (`/home/rendra/.local/bin/pcb`). The capture required an empty
`git status --short` and empty `git diff --binary` before executing any run:

- `repo-revision.txt` — the executed revision (`ff1b472`)
- `capture-provenance.json` — revision, empty `git_status`, empty binary diff,
  `ext4`, `pcbc 0.4.40`, capture timestamp, script digest
- `commands.json` — every run's exact argv, cwd, executable, exit code,
  timestamp, revision, and stdout/stderr artifacts
- per-run `run-provenance.json` — revision + clean-status + argv/exit/digests
  for each of the eight run directories
- `scripts/` — the executed capture scripts, hashed in the manifest

## Task-by-task remediation

| Task | Work done | Commit |
|---|---|---|
| 0 | Downgraded this report to `PARTIAL`; removed unsupported claims (clean-tree, "20f9a9c finalized", single-commit production captures, build-time validation, untranscribed counts) | `06e1e30` |
| 1 | Re-captured all real Diode evidence from the clean tracked revision `ff1b472`; per-run revision/status provenance; replaced placeholder command metadata; rebuilt manifest | `ff1b472`, `bb97b25` |
| 2 | Bound `pcb-version.txt` to the manifest (exact single `pcbc <major>.<minor>.<patch>` record, on-disk digest binding, version match against every adapter) | `552b2fe` |
| 3 | Enforced registry provenance lazily before generated use; fail-closed empty registry; `doctor`/`build` unaffected | `b0b4381` |
| 4 | Byte-bound both generated renderers to retained production-generated sources | `d93cd97` |
| 5 | Retained executable capture scripts; production command metadata is the exact executed script record | `a310c32`, `ff1b472` |
| 6 | Retained `RenamedBench__alt_case` prefix evidence | `68d96a3` |
| 7 | Retained negative real-toolchain runs (invalid-syntax/connectivity/value) | `68d96a3` |
| 8 | Built committed `fixtures/green-real`; full PASS with complete run directory retained | `68d96a3` |
| 9 | Added `src/pcb_agent/evidence.py` manifest loader + provenance validation; fails closed on missing file/manifest entry/digest/version mismatch/duplicate kind | `2b22fd2` |
| 10 | Narrowed the net-order claim to defensive design language (membership + count, ordering not assumed) | `ca11826` |
| 11 | Added `.sanitized.json` publication companions (path fields only); raw evidence kept byte-identical | `2b22fd2` |
| 12 | Rebuilt `manifest.sha256` deterministically; added `test_evidence_bundle.py` completeness + provenance-relation tests | `2b22fd2`, `486d518` |
| 13 | Finalized README, `docs/report-spike-execution.md`, and `docs/spike-diode-net-naming.md` only | `20f9a9c` |
| 14 | Retained verification transcripts for Windows/WSL pytest, pyright, and both manifest checks | `dbdc013` |
| 15 | Finalized this report and corrected its commit attribution | this commit |

Follow-up CI fixes:
- `31aaf79`: re-enabled tracking of `verify-report.json`/`.md` under `tests/evidence/` (global `.gitignore` had silently excluded them).
- `a850a4b`: `.gitattributes -text` for `tests/evidence/**` so Windows checkouts cannot alter evidence bytes and break manifest hashes.

## Evidence inventory

All under `tests/evidence/diode-0.4.40/` (144 artifacts, `manifest.sha256`
`sha256sum -c` clean on both Windows and WSL):

- `environment.txt` — pwd, git commit, uname, /etc/os-release, findmnt (ext4), `command -v pcb`
- `pcb-version.txt` — exact `pcbc 0.4.40`
- `repo-revision.txt` — executed revision `ff1b472`
- `capture-provenance.json` — clean-tree capture record
- `commands.json` — exact argv/cwd/executable/exit/timestamp/revision for every run
- `scripts/` — retained capture scripts (hashed)
- `valid-blinky/` — locked TestBench source, module source, contracts, raw result, exit/stderr, run-provenance
- `spike-generics/` — evidence TestBench source, module source, pcb.toml, raw result
- `prefix/` — `RenamedBench__alt_case` TestBench source + raw result
- `green-real/` — full `pcb-agent verify` report, complete run directory (`run/`), source/contract copies
- `production-expression/` — exact production-generated connectivity + specification testbenches and raw results, `production-summary.json`, captured stdout/stderr
- `negative-invalid-syntax/`, `negative-invalid-connectivity/`, `negative-invalid-value/` — verify reports + run dirs + raw artifacts
- `verification/` — retained transcripts (windows-pytest, wsl-pytest, pyright, windows-manifest, wsl-manifest)
- `.sanitized.json` companions — path fields rewritten for publication; raw files authoritative and byte-identical

## Registered vs blocked kinds

Registered (verified against pcbc 0.4.40): `resistor`, `led`, `capacitor`,
`inductor`, `ferrite_bead`, `thermistor`, `zener`, `rectifier`, `tvs`.

Blocked/unsupported: `crystal` (adapter model cannot represent the one-to-many
four-pin GND mapping), `opamp`, `PinHeader`, `SolderJumper`, `TestPoint`,
`NetTie`, `MountingHole`, `Fiducial`, `QR`, `Version`, and all `mpn`
constraints. Crystal pin mappings are captured observations only; they are
documented but not registered, and crystal contracts fail closed with
`BLOCKED`.

## Verification

Exact counts are backed by retained transcripts under
`tests/evidence/diode-0.4.40/verification/` (recorded at revision `dbdc013`):

- Windows pytest: 249 passed, 14 skipped, 395 subtests passed
  (`verification/windows-pytest.txt`)
- WSL pytest (Ubuntu-24.04, ext4): 263 passed, 404 subtests passed
  (`verification/wsl-pytest.txt`)
- pyright: 0 errors, 0 warnings, 0 informations (`verification/pyright.txt`)
- `sha256sum -c manifest.sha256`: 144/144 OK on Windows and WSL
  (`verification/windows-manifest.txt`, `verification/wsl-manifest.txt`)
- Real pcbc 0.4.40:
  - `fixtures/green-real` → **PASS** (CONTRACT, DIODE_BUILD, ZENER_TEST,
    CONNECTIVITY, SPECIFICATION); report `versions` populated
  - `invalid-syntax` → DIODE_BUILD FAIL, dependent gates BLOCKED, overall BLOCKED
  - `invalid-connectivity` → ZENER_TEST FAIL, generated gates BLOCKED (prerequisite), overall BLOCKED
  - `invalid-value` → ZENER_TEST FAIL, generated gates BLOCKED (prerequisite), overall BLOCKED
- PR CI: all green (Ubuntu + Windows, Python 3.11 + 3.13, typecheck)
- `git diff --check`: clean; `git status`: clean at this commit
- `production_ready` and `fabrication_approved` remain `false` in every report

## Residual limitations

- Raw evidence contains machine-local paths (`/home/rendra/pcbagent-full/...`)
  and temporary harness paths (`/tmp/pcb-agent-*`). Raw files are kept
  byte-identical and authoritative; `.sanitized.json` companions rewrite only
  path fields and are diagnostic only.
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
