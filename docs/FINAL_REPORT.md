# Final Report — Diode Net‑Naming Spike Provenance & Registry Remediation

**Date:** 2026-08-30
**Branch:** `feat/diode-adapter-registry`
**PR:** https://github.com/GSPETech/pcb-agent/pull/5
**Author:** `jrjuarendra <jrjuarendra@gmail.com>`
**Status:** ✅ COMPLETE — evidence recapture, verification transcripts, independent
attestation, CI, and documentation all finalized and verified.

---

## 1. Objective

Close all source‑provenance and registry‑enforcement gaps identified in the
audit of `docs/report-spike-remediation.md`, then finalize the evidence
lifecycle: recapture from an immutable source barrier, retain per‑platform
verification transcripts, build the non‑circular primary manifest + external
attestation, reach green CI, and document the verified end state.

---

## 2. Commit chain (final cycle)

| Step | Commit | Purpose |
|---|---|---|
| S1 | `3263d38db733897125b6b3f40a53310b527c6a6c` | `fix: align capture script call sites and evidence manifest model` — follow‑up source fixes after the first recapture attempt (manifest exclusion model, raw `is_symlink()` check) |
| **Capture barrier S2** | `1373b0d863f7339d19081dd97238376cb504cf09` | `fix: align pcb-test run provenance git status model` — per‑run provenance records the orchestrator‑verified clean status. **No source edit after this commit.** |
| **E1 (evidence)** | `0a7b0e28d50467cab575e13f2d698e95451fa3e1` | `test: recapture final spike evidence from revision 1373b0d` — 8 runs, 143‑entry primary manifest, no verification/attestation files |
| **A1 (attestations)** | `5001b1ea48d4ba21bdee79f10b1992340928202c` | `test: retain final post-evidence verification attestations` — 7 verification transcripts, 148‑entry primary manifest, external `manifest-attestation.json` |
| **D1 (docs)** | `fdb065381f35e67d93471dce76c491b14a62b8b8` | `docs: finalize verified spike remediation state` |
| **D2 (docs)** | `158c9077ed295584fe0e42fd88d150cf22f4e86c` | `docs: correct final spike audit wording` |
| **D3 (docs)** | `f322060c2e9b2ec91448b5a49495d74b6973e9a1` | `docs: reconcile final spike reports at D2` |

The capture was executed from WSL2 Ubuntu‑24.04 (ext4) with the real
`pcbc 0.4.40` at `/home/rendra/.local/bin/pcb`, from a fully clean tree at
revision `1373b0d`. At D3, local HEAD, remote branch HEAD, and PR head were
equal at `f322060c2e9b2ec91448b5a49495d74b6973e9a1` (verified via `git
rev-parse` and `gh pr view 5 --json headRefOid`).

The documentation tree may advance by the commit containing this statement;
verify the current immutable documentation head with `git rev-parse HEAD`;
D3 is the last explicitly named predecessor.

---

## 3. Evidence bundle

`tests/evidence/diode-0.4.40/`:

- **Primary manifest:** `manifest.sha256`, **148 entries**,
  SHA‑256 `5a22245ff49e72cb7a8ca72a67793f7cb367b463707ddab7e576883e2fa6728e`.
  Covers the 143 recaptured primary evidence files plus the five ordinary
  verification transcripts (`windows-pytest.txt`, `wsl-pytest.txt`,
  `pyright.txt`, `windows-pyright.txt`, `wsl-pyright.txt`).
- **External attestation (outside the primary manifest, 3 files):**
  - `manifest-attestation.json` — attests the primary manifest SHA‑256, the
    Windows manifest transcript SHA‑256, and the WSL manifest transcript
    SHA‑256. Its own SHA‑256 (reported externally here) is not contained in
    the file; it does not attest itself:
    `6eed2e3c893090cfc2c9952b4c7710e7b33fcc6c6412472ab2f707411dc98ac8`
  - `verification/windows-manifest.txt` —
    `021164ce9beeccde3d3005eb34a8b54129da96ac900428c29e7cc4b5388e082f`
  - `verification/wsl-manifest.txt` —
    `b333315a8f0f3a7fdf9cae0c5b4d29cbc84312c2d317fa8815f94c8146104351`
- **Stable raw hashes unchanged** across recaptures:
  - `valid-blinky/valid-blinky.json` —
    `02c6cb60bfaf371e640e34ed0ff7b707074cfad0789b38a25c014cfa66cfac11`
  - `spike-generics/spike-generics.json` —
    `3320a8aa668f5f28dc19b4240f9f92e22333805ead12e36cb4c5a3c3b1636267`
- Bundled script copies are recapture outputs and match the canonical
  `scripts/capture-spike-evidence.py` / `scripts/capture-production-expression.py`
  byte‑for‑byte (SHA‑256 pairs verified at E1).
- `manifest-attestation.json` is compact single‑line JSON (sorted keys,
  `sha256:`-prefixed transcript digests, revision = E1) and stores the primary
  manifest digest non‑circularly; the primary manifest excludes
  `manifest-attestation.json`, `windows-manifest.txt`, and
  `wsl-manifest.txt` by name.

---

## 4. Verification results

The exact counts below are backed by retained transcripts (headers record
command argv, cwd, timestamp, revision, exit code, platform) for the E1-time
runs. The A1/D1/D2/D3 green state is backed by CI. No exact local
A1/D1/D2/D3 counts are claimed without retained transcripts.

### pytest (full suite, `python -m pytest tests/ -v`)

| Run | Result |
|---|---|
| Windows, against E1 (retained `verification/windows-pytest.txt`, exit 1) | 269 passed, 3 failed, 18 skipped — the 3 failures are exactly the attestation bootstrap subtests asserting the `verification/*` files that A1 adds |
| WSL2 ext4, against E1 (retained `verification/wsl-pytest.txt`, exit 1) | 285 passed, 3 failed, 2 skipped — same bootstrap subtests |
| Windows/WSL, A1/D1/D2/D3 trees (local) | no retained local transcripts — no exact local counts claimed |
| **CI at A1/D1/D2/D3** (Ubuntu 3.11/3.13, Windows 3.11/3.13) | **all green** |

### Pyright (`python -m pyright`, Pyright 1.1.411)

| Platform | Result |
|---|---|
| Windows (Python 3.13.2) | 0 errors, 0 warnings, 0 informations (retained `verification/pyright.txt` = `verification/windows-pyright.txt`) |
| WSL2 ext4 (Python 3.12.3) | 0 errors, 0 warnings, 0 informations (retained `verification/wsl-pyright.txt`) |
| CI typecheck | green |

### Primary manifest check (`sha256sum -c manifest.sha256`, 148 entries)

| Platform | Result |
|---|---|
| Windows (retained `verification/windows-manifest.txt`) | 148/148 OK, exit 0 |
| WSL2 ext4 (retained `verification/wsl-manifest.txt`) | 148/148 OK, exit 0 |

A read‑only recomputation on a second platform
(`find . -type f ! -name manifest.sha256 ! -name manifest-attestation.json
! -name windows-manifest.txt ! -name wsl-manifest.txt -print0 | sort -z |
xargs -0 sha256sum`) reproduces the 148‑entry manifest byte‑for‑byte. This
recomputation is a verification step; no separate retained transcript for it
exists.

### Repo hygiene

- `git diff --check`: clean at every commit.
- `git status --short`: clean (only untracked `docs/FINAL_REPORT.md` before D1).
- At D3, local HEAD, remote branch HEAD, and PR #5 head were equal at
  `f322060c2e9b2ec91448b5a49495d74b6973e9a1`.

---

## 5. Residual limitations

- Raw evidence contains machine‑local paths (`/home/rendra/pcbagent-full/...`,
  `/tmp/pcb-agent-*`); `.sanitized.json` companions rewrite path fields only.
- **Crystal** remains `OBSERVED — unsupported`: the adapter model cannot
  represent the one‑to‑many four‑pin GND mapping; crystal contracts fail
  closed with `BLOCKED`.
- **`mpn`** has no captured accessor → `mpn` constraints remain `BLOCKED`.
- Net member **ordering stability** is not claimed as empirically verified;
  the generator asserts membership + count only.
- `production_ready` and `fabrication_approved` remain `false` in every
  report; `human_review_required` is `true`.
- The E1‑time pytest transcripts record the expected attestation bootstrap
  failures (exit 1); they are superseded by the green CI test matrix and are
  retained as the exact record of the E1 state. No exact local A1/D1/D2/D3
  pytest counts are claimed because no local transcripts were retained for
  those trees.
- Green‑real exercises six buildable kinds: resistor, led, capacitor,
  inductor, ferrite_bead, tvs. Thermistor, zener, and rectifier
  package/value behavior is proven through `production-expression` evidence
  because their stdlib generics fail the green‑real `pcb build` BOM
  part‑info checks.

---

## 6. How to reproduce

```bash
# Windows (source tree)
git checkout feat/diode-adapter-registry
python -m pytest tests/ -v
python -m pyright
git diff --check master...HEAD
git status --short

# WSL2 Ubuntu-24.04 (ext4)
cd /home/rendra/pcbagent-full
git checkout feat/diode-adapter-registry
python3 -m pytest tests/ -v
python3 -m pyright
cd tests/evidence/diode-0.4.40 && sha256sum -c manifest.sha256
```

---

## 7. PR

https://github.com/GSPETech/pcb-agent/pull/5 — **OPEN, do not merge** (human
approval required).

**End of report.**
