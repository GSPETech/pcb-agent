# Spike Evidence Remediation — Execution Report

Date: 2026-08-29 (finalized 2026-08-30)
Branch: `feat/diode-adapter-registry`
PR: https://github.com/GSPETech/pcb-agent/pull/5
Status: `COMPLETE — artifact integrity and per-run provenance enforcement verified; evidence recaptured from the 1373b0d barrier, attestations retained, CI green`

This report documents the remediation of every evidence and provenance finding
from the final review of the Diode net-naming spike, as specified in
`REVIEW_REMEDIATION_PLAN_V4.md`.

## Summary

The prior spike evidence bundle was incomplete: it hashed only three result
JSONs, referenced missing artifacts, overclaimed crystal, and lacked
environment/version/source provenance. All findings are now remediated:

- The bundle is re-captured from a **clean tracked commit** (`1373b0d`, the
  final capture barrier) on WSL2 ext4 against the real `pcbc 0.4.40`
  toolchain. The capture orchestrator verified a clean tree before beginning
  the capture sequence **and re-measured source cleanliness before every
  individual run and immediately before external tool execution**; every
  run's `run-provenance.json` records its own measured clean status, diff
  digests, and exclusion pathspec.
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
`1373b0d863f7339d19081dd97238376cb504cf09` (the final capture barrier S2,
branch `feat/diode-adapter-registry`) on WSL2 Ubuntu-24.04 ext4 with the real
`pcbc 0.4.40` (`/home/rendra/.local/bin/pcb`). The capture required an empty
`git status --short` and empty `git diff --binary` before executing any run,
and re-measured the same cleanliness before every individual run:

- `repo-revision.txt` — the executed revision (`1373b0d`)
- `capture-provenance.json` — revision, empty `git_status`, empty binary diff,
  `ext4`, `pcbc 0.4.40`, capture timestamp, script digest
- `commands.json` — every run's exact argv, cwd, executable, exit code,
  timestamp, revision, and stdout/stderr artifacts
- per-run `run-provenance.json` — executed revision, that run's own measured
  clean status (empty filtered source status, empty staged/unstaged diff
  digests, recorded exclusion pathspec), argv/exit/digests for each of the
  eight run directories
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
| 15 | Finalized this report and corrected its commit attribution | `22878f4` (first tracked version) |

Tasks 0–15 are the 16 numbered tasks of the remediation plan; the follow-up CI
fixes below are separate commits, not part of that table.

Follow-up CI fixes:
- `31aaf79`: re-enabled tracking of `verify-report.json`/`.md` under `tests/evidence/` (global `.gitignore` had silently excluded them).
- `a850a4b`: `.gitattributes -text` for `tests/evidence/**` so Windows checkouts cannot alter evidence bytes and break manifest hashes.

Final recapture cycle (provenance completion, this report set to `COMPLETE`):
- `ca4ac93`: per-run source cleanliness measurement (task 1 of the follow-up plan).
- `cea6b99` / `605401d` / `4e41734` / `037f594` / `4744783`: version
  validation, registry cache, production command provenance, provenance
  relations, and the non-circular transcript-attestation model.
- `3263d38` (S1) / `1373b0d` (S2, capture barrier): final source alignment of
  the capture scripts; no source edit after S2.
- `0a7b0e2` (E1): evidence recaptured from the S2 barrier on WSL2 ext4
  (8 runs, 143-entry primary manifest).
- `5001b1e` (A1): Windows/WSL verification transcripts, 148-entry primary
  manifest, external `manifest-attestation.json`.
- D1 (`fdb065381f35e67d93471dce76c491b14a62b8b8`): docs finalized.
- D2 (`158c9077ed295584fe0e42fd88d150cf22f4e86c`): `docs: correct final
  spike audit wording`.
- D3 (`f322060c2e9b2ec91448b5a49495d74b6973e9a1`): `docs: reconcile final
  spike reports at D2`.

The documentation tree may advance by the commit containing this statement;
verify the current immutable documentation head with `git rev-parse HEAD`;
D3 is the last explicitly named predecessor.

## Evidence inventory

All under `tests/evidence/diode-0.4.40/` (primary manifest: **148 entries**,
`sha256sum -c` 148/148 OK on both Windows and WSL). The three
external-to-primary-manifest attestation artifacts are outside the primary
manifest: `manifest-attestation.json` attests the primary manifest digest
and both manifest transcript digests, does not attest itself, and its own
SHA-256 is reported externally in `docs/FINAL_REPORT.md` and the PR body.

- `environment.txt` — pwd, git commit, uname, /etc/os-release, findmnt (ext4), `command -v pcb`
- `pcb-version.txt` — exact `pcbc 0.4.40`
- `repo-revision.txt` — executed revision `1373b0d`
- `capture-provenance.json` — clean-tree capture record
- `commands.json` — exact argv/cwd/executable/exit/timestamp/revision for every run
- `scripts/` — retained capture scripts (hashed)
- `valid-blinky/` — locked TestBench source, module source, contracts, raw result, exit/stderr, run-provenance
- `spike-generics/` — evidence TestBench source, module source, pcb.toml, raw result
- `prefix/` — `RenamedBench__alt_case` TestBench source + raw result
- `green-real/` — full `pcb-agent verify` report, complete run directory (`run/`), source/contract copies
- `production-expression/` — exact production-generated connectivity + specification testbenches and raw results, `production-summary.json`, captured stdout/stderr
- `negative-invalid-syntax/`, `negative-invalid-connectivity/`, `negative-invalid-value/` — verify reports + run dirs + raw artifacts
- `verification/` — retained transcripts (windows-pytest, wsl-pytest, pyright, windows-pyright, wsl-pyright, windows-manifest, wsl-manifest)
- `manifest-attestation.json` — external attestation (outside the primary manifest)
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

The exact counts below are backed by retained transcripts under
`tests/evidence/diode-0.4.40/verification/` for the E1-time runs, and by the
CI test matrix for the A1/D1/D2/D3 green state. No exact local
A1/D1/D2/D3 counts are claimed without retained transcripts. The pytest
transcripts record the
exact run against the immutable evidence commit E1
(`0a7b0e2`); at that revision the only failures are the attestation bootstrap
subtests asserting the `verification/*` files that A1 adds. They are
superseded by the green CI test matrix. Exact local A1/D1-tree pytest counts
are not stated (no local transcripts were retained for those trees):

- Windows pytest at E1 (retained `verification/windows-pytest.txt`, exit 1):
  269 passed, 3 failed, 18 skipped
- WSL pytest at E1 (retained `verification/wsl-pytest.txt`, exit 1): 285
  passed, 3 failed, 2 skipped
- A1/D1/D2/D3 trees: green state backed by the CI test matrix below (no
  retained local transcripts, so no exact local A1/D1/D2/D3 counts are
  claimed)
- pyright (Pyright 1.1.411): 0 errors, 0 warnings, 0 informations on Windows
  (`verification/pyright.txt` = `verification/windows-pyright.txt`) and WSL
  (`verification/wsl-pyright.txt`)
- `sha256sum -c manifest.sha256`: 148/148 OK on Windows and WSL
  (`verification/windows-manifest.txt`, `verification/wsl-manifest.txt`);
  primary manifest SHA-256
  `5a22245ff49e72cb7a8ca72a67793f7cb367b463707ddab7e576883e2fa6728e`,
  reproduced byte-for-byte by a read-only recomputation on the second
  platform (a verification step, not a separately retained transcript)
- Real pcbc 0.4.40:
  - `fixtures/green-real` → **PASS** (CONTRACT, DIODE_BUILD, ZENER_TEST,
    CONNECTIVITY, SPECIFICATION); report `versions` populated
  - `invalid-syntax` → DIODE_BUILD FAIL, dependent gates BLOCKED, overall BLOCKED
  - `invalid-connectivity` → ZENER_TEST FAIL, generated gates BLOCKED (prerequisite), overall BLOCKED
  - `invalid-value` → ZENER_TEST FAIL, generated gates BLOCKED (prerequisite), overall BLOCKED
- PR CI: all green (Ubuntu + Windows, Python 3.11 + 3.13, typecheck)
- `git diff --check`: clean; `git status`: clean at D1
  (`fdb065381f35e67d93471dce76c491b14a62b8b8`)
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
- The retained E1-time pytest transcripts honestly record exit 1: at that
  revision the attestation bootstrap subtests assert the `verification/*`
  files that A1 adds. No exact local A1/D1/D2/D3 pytest counts are claimed
  (no local transcripts were retained for those trees); the A1/D1/D2/D3 CI
  test matrix is all green.
