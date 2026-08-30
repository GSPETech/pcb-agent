# Review Remediation Plan V3

Target branch: `fix/review-remediation`

PR: `https://github.com/GSPETech/pcb-agent/pull/1`

Scope plan ini hanya temuan review terbaru: tiga High, empat Medium, dan satu
Low. Critical findings sebelumnya sudah diperbaiki dan tidak boleh diregresi.

## Aturan Eksekusi

1. Kerjakan task berurutan.
2. Satu task satu commit Conventional Commits.
3. Jangan mengaktifkan adapter produksi tanpa captured Diode evidence.
4. Evidence malformed/inconsistent selalu `BLOCKED`.
5. Structured expected assertion mismatch adalah `FAIL` hanya bila seluruh
   payload structurally consistent.
6. Unsupported contract semantics selalu `BLOCKED`, bukan silent skip.
7. Jalankan setelah setiap task:

   ```powershell
   python -m pytest tests/ -q
   python -m pyright
   git diff --check
   ```

8. Jangan merge sebelum seluruh CI pass.

## Task Map

| Task | Severity | Fokus | Commit |
|---|---|---|---|
| 0 | Low | Trailing whitespace dan baseline | `style: remove remediation whitespace` |
| 1 | High/Medium | Reconcile seluruh record statuses dengan summary | `fix: reconcile generated result statuses` |
| 2 | High | Ownership value/package/MPN | `fix: block unverified component properties` |
| 3 | High | Required pullup topology | `fix: verify required pullup topology` |
| 4 | Medium | Relative evidence paths | `fix: report generated evidence with relative paths` |
| 5 | Medium | Revalidate retained evidence hashes | `fix: revalidate retained generated evidence` |
| 6 | Final | Full verification, docs, PR update | `docs: record generated evidence hardening` |

---

## Task 0 - Branch Hygiene dan Baseline

### Menyelesaikan

- Low: enam trailing-whitespace findings.

### File

- `src/pcb_agent/contracts.py:182`
- `src/pcb_agent/jsonschema.py:90,94,119`
- `tests/helpers.py:103,107`

### Langkah

1. Periksa status:

   ```powershell
   git status --short
   git branch --show-current
   ```

2. Hapus hanya trailing spaces/tabs. Jangan format seluruh file.
3. Paksa LF untuk file yang disentuh bila perlu.
4. Jalankan baseline:

   ```powershell
   python -m pytest tests/ -q
   python -m pyright
   git diff --check
   ```

### Acceptance

- `git diff --check` tanpa output.
- pytest tetap minimal `131 passed, 5 skipped` atau lebih.
- pyright `0 errors`.

### Commit

```text
style: remove remediation whitespace
```

---

## Task 1 - Reconcile Generated Result Statuses

### Menyelesaikan

- High: zero-exit PASS walau record lain `SKIPPED`, `BLOCKED`, unknown, atau
  kosong.
- Medium: malformed optional `failures`/`errors` dianggap absent.
- Medium: nonzero expected FAIL dapat diklasifikasi tanpa cocok dengan summary.

### Masalah Saat Ini

`_payload_has_failure()` hanya mengenali:

```text
FAIL
FAILED
ERROR
```

Record lain seperti `SKIPPED`, `BLOCKED`, `UNKNOWN`, dan empty status tidak
dianggap failure. Summary juga belum direconcile dengan actual record status
counts.

### Result Status Contract

Definisikan exact sets di `src/pcb_agent/diode.py`:

```python
_PASS_STATUSES = frozenset({"PASS", "PASSED", "OK"})
_FAIL_STATUSES = frozenset({"FAIL", "FAILED", "ERROR"})
```

Semantics:

| Record status | Meaning |
|---|---|
| PASS/PASSED/OK | Passing assertion |
| FAIL/FAILED/ERROR | Failing assertion |
| Missing/empty/unknown/SKIPPED/BLOCKED | Evidence incompatible -> BLOCKED |

Generated TestBench selalu required dan expected to run. `SKIPPED` dan
`BLOCKED` dari tool output bukan deterministic design outcomes.

### Perubahan

#### 1. Validate optional counters strictly

Di `_validate_test_payload()`:

```python
for key in ("failures", "errors"):
    if key not in summary:
        continue
    value = _int_or_none(summary[key])
    if value is None or value < 0:
        raise GeneratedEvidenceError(
            f"pcb test JSON summary {key} must be non-negative integer"
        )
```

Boolean, string, float, dan null ditolak bila key hadir.

#### 2. Normalize exact top-level record statuses

Buat helper:

```python
def _top_level_record_counts(
    payload: Mapping[str, Any],
) -> tuple[int, int] | None:
```

Algorithm:

1. Iterate hanya direct `payload["results"]` records.
2. Setiap record harus object.
3. `status` harus string non-empty.
4. Normalize uppercase.
5. Increment pass/fail untuk recognized statuses.
6. Unknown status return `None`.

#### 3. Reconcile summary

Tambahkan:

```python
def _summary_matches_records(payload: Mapping[str, Any]) -> bool:
```

Require:

```text
summary.total == len(results)
summary.passed == recognized_pass_count
summary.failed == recognized_fail_count
summary.passed + summary.failed == summary.total
```

Jika optional `failures` ada:

- Untuk PASS payload harus zero.
- Untuk FAIL payload boleh nonzero, tetapi tidak boleh bertentangan dengan
  `summary.failed == 0`.

Jika optional `errors` > 0:

- Payload tidak boleh dianggap deterministic assertion FAIL kecuali captured
  Diode contract membuktikan errors merepresentasikan expected assertion.
- Default fail closed: `BLOCKED`.

#### 4. Zero-exit classification

PASS hanya bila:

1. Structural validation PASS.
2. Summary matches all top-level record statuses.
3. Exactly one expected record.
4. Expected record recognized PASS.
5. Semua records recognized PASS.
6. `failed == failures == errors == 0`.

Jika expected record recognized FAIL pada zero exit:

- Bila summary matches dan `errors == 0`, return `FAIL`.
- Jangan return `BLOCKED` hanya karena process exit zero.

#### 5. Nonzero classification

Return `FAIL` hanya bila:

1. JSON structurally valid.
2. Summary matches top-level records.
3. Exactly one expected record.
4. Expected record recognized FAIL.
5. `summary.failed > 0`.
6. `errors == 0`.

Semua inconsistent/unknown evidence return `BLOCKED`.

### Test

Extend `tests/test_generated_result.py`:

#### Zero exit

1. All records PASS + summary matches -> PASS.
2. Expected PASS + unrelated SKIPPED -> BLOCKED.
3. Expected PASS + unrelated BLOCKED -> BLOCKED.
4. Expected PASS + unknown status -> BLOCKED.
5. Expected PASS + empty status -> BLOCKED.
6. Expected PASS + summary says passed=2 but only one PASS -> BLOCKED.
7. Expected PASS + `errors: true` -> BLOCKED.
8. Expected PASS + `errors: "1"` -> BLOCKED.
9. Expected PASS + `failures: null` -> BLOCKED.
10. Expected FAIL + consistent summary -> FAIL.

#### Nonzero exit

1. Expected FAIL + summary failed=1 -> FAIL.
2. Expected FAIL + summary passed=1/failed=0 -> BLOCKED.
3. Expected FAIL + errors=1 -> BLOCKED.
4. Expected FAIL + unknown unrelated record -> BLOCKED.
5. Expected record absent -> BLOCKED.

### Acceptance

- Zero-exit partial/unknown execution tidak dapat PASS.
- FAIL hanya berasal dari consistent structured expected assertion failure.
- Malformed optional counters selalu BLOCKED.

### Commit

```text
fix: reconcile generated result statuses
```

---

## Task 2 - Component Property Ownership

### Menyelesaikan

- High: `expected-connectivity.json` menerima `value`, `package`, `mpn`, tetapi
  populated fields dapat tidak diperiksa.

### Ownership Decision

Freeze ownership berikut:

| Field | Gate |
|---|---|
| `kind` | CONNECTIVITY/component existence adapter |
| `value` | SPECIFICATION |
| `package` | SPECIFICATION |
| `mpn` | SPECIFICATION, currently unsupported -> BLOCKED |
| pin members | CONNECTIVITY |

### Masalah

Specification generator hanya membaca `SPEC.json.requirements[].constraints`.
Jika connectivity contract berisi:

```json
{"R1": {"kind": "resistor", "value": "1kohm", "package": "0402"}}
```

tetapi SPEC tidak menduplikasi fields tersebut, tidak ada assertion.

### Perubahan

#### 1. Collect expected properties

Di `render_specification_testbench()`:

1. Iterate seluruh `connectivity.components`.
2. Untuk setiap populated property `value`, `package`, `mpn`, buat expected
   property obligation.
3. Merge dengan constraints dari SPEC.
4. Bila nilai connectivity dan SPEC berbeda, raise `GeneratorError`:

   ```text
   conflicting expected value for R1: connectivity='1kohm', spec='10kohm'
   ```

5. Jangan pilih salah satu diam-diam.

#### 2. Verified property adapter

Extend `ComponentAdapter`:

```python
@dataclass(frozen=True)
class ComponentAdapter:
    ...
    value_accessor: str | None
    package_accessor: str | None
    mpn_accessor: str | None
```

Atau gunakan callable renderer functions bila lebih aman. Accessor string tidak
boleh berasal dari contract; hanya registry constant.

#### 3. Fail closed

Untuk setiap populated field:

- Adapter accessor verified -> render assertion.
- Accessor `None` -> `GeneratorError`, CLI `BLOCKED`.

`mpn` harus `BLOCKED` sampai Task 12 Diode spike memberi verified API.

#### 4. Requirements without component property constraints

Specification generator tetap harus menghasilkan assertions dari connectivity
component fields, walau SPEC hanya punya connectivity requirement. Jangan
anggap tidak ada assertions.

### Test

1. Connectivity-only `value` menghasilkan value assertion.
2. Connectivity-only `package` menghasilkan package assertion.
3. Connectivity-only `mpn` dengan accessor None -> GeneratorError/BLOCKED.
4. Connectivity value dan SPEC value sama -> satu assertion, bukan duplicate.
5. Connectivity value dan SPEC value berbeda -> GeneratorError.
6. Package conflict -> GeneratorError.
7. Unknown populated component property cannot PASS.
8. Component without optional properties remains valid.

### Acceptance

- Setiap populated value/package/MPN diperiksa atau explicit BLOCKED.
- Tidak ada silent ownership gap.
- Conflicting contracts invalid/block deterministically.

### Commit

```text
fix: block unverified component properties
```

---

## Task 3 - Required Pullup Topology

### Menyelesaikan

- High: `required_pullup` hanya memeriksa nama component dan rail, bukan exact
  signal-to-rail topology.
- Bug keying: component ref dibandingkan dengan kind-keyed adapter registry.

### Contract Meaning

Untuk:

```json
"SDA": {
  "members": ["U1.SDA", "R1.P1"],
  "required_pullup": {"component": "R1", "rail": "3V3"}
}
```

Harness harus membuktikan:

1. R1 terdaftar di `components`.
2. R1 kind punya exactly two verified logical pins.
3. Salah satu mapped pin R1 ada pada SDA.
4. Pin R1 yang lain ada pada 3V3.
5. Rail 3V3 terdaftar di `nets`.
6. Tidak cukup hanya component/rail name existence.

### Perubahan

#### 1. Resolve kind correctly

Ganti logic seperti:

```python
component in _ADAPTERS
```

dengan:

```python
component_def = components.get(component)
kind = component_def.get("kind")
adapter = adapter_for(kind, pcbc_version)
```

#### 2. Require verified two-pin topology

Adapter harus menyediakan mapping logical pin -> Diode pin. Untuk pullup:

- Require exactly two logical pins atau explicit pullup pin pair metadata.
- Jangan mengandalkan dictionary iteration order sebagai electrical meaning.

Recommended adapter extension:

```python
pullup_pin_pair: tuple[str, str] | None
```

Example verified resistor:

```python
pullup_pin_pair=("P1", "P2")
```

#### 3. Determine expected contract members

Before rendering:

1. Signal net members containing `R1.<pin>` harus exactly one supported pullup
   pin.
2. Rail net members containing `R1.<other_pin>` harus ada.
3. Same pin on both nets invalid.
4. Both pins on signal invalid.
5. Both pins on rail invalid.
6. Missing rail member invalid.

Pelanggaran contract reference invariant sebaiknya `ContractError` exit 3 di
`contracts.py`. Unsupported adapter remains `BLOCKED` at renderer.

#### 4. Generated assertions

Renderer menegaskan exact Diode tuples:

```python
check((DIODE_REF, SIGNAL_DIODE_PIN) in observed_signal, ...)
check((DIODE_REF, RAIL_DIODE_PIN) in observed_rail, ...)
```

Existing generic net member assertions dapat memenuhi hal ini; required_pullup
logic harus memastikan relationship opposite pins, bukan menambah bare ref
existence assertion.

#### 5. Remove current broken helper

Hapus `_check_required_pullup()` yang saat ini membandingkan bare reference
dengan hierarchical component keys dan hanya memeriksa rail name.

### Test

1. Valid R1.P1 signal + R1.P2 rail -> generated assertions PASS structurally.
2. R1.P1 signal + R1.P1 rail -> invalid.
3. Signal member missing R1 -> invalid.
4. Rail member missing R1 opposite pin -> invalid.
5. Unknown pullup component -> ContractError.
6. Unknown rail -> ContractError.
7. Adapter without `pullup_pin_pair` -> GeneratorError/BLOCKED.
8. Component kind lookup uses `components[ref]["kind"]`, not ref as registry key.
9. Extra third pin adapter -> BLOCKED unless explicit pullup pair verified.

### Acceptance

- Required pullup cannot PASS from name existence.
- Exact signal and opposite rail pin topology verified.
- Unsupported topology BLOCKED.

### Commit

```text
fix: verify required pullup topology
```

---

## Task 4 - Portable Relative Evidence Paths

### Menyelesaikan

- Medium: reports expose absolute paths dan tidak portable.

### Desired Evidence Shape

Paths harus relative POSIX paths dari run directory atau project root.
Pilih satu root dan gunakan konsisten. Recommended: project root, karena report
sendiri berada di project `reports/<run-id>/`.

Example:

```json
{
  "generated_testbench": {
    "path": "reports/<run-id>/raw/connectivity-testbench.zen",
    "sha256": "sha256:..."
  },
  "result": {
    "path": "reports/<run-id>/raw/connectivity-result.json",
    "sha256": "sha256:..."
  }
}
```

### Perubahan

#### 1. GeneratedTestResult path root

Tambahkan field:

```python
evidence_root: Path
```

atau pass `project.root` ke `generated_check()`.

#### 2. Containment helper

Buat:

```python
def _relative_evidence_path(path: Path, project_root: Path) -> str:
    resolved_path = path.resolve(strict=True)
    resolved_root = project_root.resolve(strict=True)
    try:
        relative = resolved_path.relative_to(resolved_root)
    except ValueError as error:
        raise GeneratedCompatibilityError(
            "generated evidence escapes project root"
        ) from error
    return relative.as_posix()
```

3. Reject symlink evidence file sebelum resolution.
4. Reject evidence path di luar raw run directory walau masih di project root.
5. Store only relative POSIX string in Check evidence.
6. Jangan store absolute stdout/stderr paths dalam command/evidence metadata.

### Test

1. Path bawah project root serialized relative.
2. Backslashes become POSIX `/`.
3. Path outside project root rejected.
4. Path inside project but outside run raw directory rejected.
5. Symlink evidence rejected.
6. Report JSON tidak memuat temporary/home prefix.
7. Relocated project can resolve evidence path and verify hash.

### Acceptance

- No absolute evidence paths in reports.
- Paths contained under expected raw directory.
- Reports portable after project relocation.

### Commit

```text
fix: report generated evidence with relative paths
```

---

## Task 5 - Revalidate Retained Evidence Hashes

### Menyelesaikan

- Medium: `generated_check()` trusts stale earlier hashes.

### Threat Model

Files can change between:

1. Generated source write.
2. Result write.
3. Check construction.
4. Report persistence.

Hash stored earlier no longer proves current retained file contents.

### Perubahan

#### 1. Verification helper

Di `diode.py`:

```python
def _verify_retained_artifact(
    path: Path,
    expected_sha256: str,
    evidence_root: Path,
) -> str:
```

Require:

- Path bukan symlink.
- Path regular file.
- Canonical path under evidence root.
- Expected digest starts `sha256:` dan 64 lowercase hex chars.
- Current bytes digest equals expected.
- Return relative POSIX path.

Mismatch raises `GeneratedCompatibilityError`.

#### 2. generated_check API

`generated_check()` harus re-read dan verify:

- generated source file
- raw result file

tepat sebelum membentuk `Check` evidence.

Jangan hanya verify di `execute_generated_test()`.

#### 3. Before report persistence

Ideal defense-in-depth: `_persist()` atau report writer melakukan manifest hash
verification lagi untuk file-based evidence. Bila scope terlalu besar, minimum
wajib generated_check immediate verification dan immutable run directory policy.

#### 4. Error classification

Artifact missing/mutated/symlink/escape -> `BLOCKED`, bukan crash dan bukan FAIL.

CLI harus catch `GeneratedCompatibilityError` dari `generated_check()`.

### Test

1. Unmodified source/result verify PASS.
2. Source mutated after `GeneratedTestResult` creation -> BLOCKED.
3. Result mutated -> BLOCKED.
4. Source deleted -> BLOCKED.
5. Result deleted -> BLOCKED.
6. Source replaced symlink -> BLOCKED.
7. Result path outside evidence root -> BLOCKED.
8. Invalid digest format -> BLOCKED.
9. Report evidence digest matches current retained bytes.

### Acceptance

- Stale hashes cannot enter report.
- Missing/mutated evidence fail closed.
- Both artifacts verified immediately before Check creation.

### Commit

```text
fix: revalidate retained generated evidence
```

---

## Task 6 - Final Verification dan Documentation

### Full Local Verification

```powershell
python -m pytest tests/ -v
python -m pyright
git diff --check master...HEAD
git status --short
```

Expected:

```text
pytest: >= 131 passed
pyright: 0 errors
git diff --check: no output
```

### CI

```powershell
gh pr checks 1
```

Semua Ubuntu/Windows matrix dan typecheck harus PASS.

### Documentation

Update `README.md` generated evidence section:

1. All top-level result records must be recognized and summary-consistent.
2. Unknown/SKIPPED/BLOCKED tool record status means harness `BLOCKED`.
3. Component values/package/MPN owner gate dan unsupported behaviour.
4. Required pullup exact pin topology rule.
5. Evidence paths relative and hashes revalidated before report.

Update `docs/spike-diode-net-naming.md`:

- Adapter pullup pin pair juga memerlukan empirical verification.
- MPN/value/package accessors harus punya captured evidence.

### Final Review Focus

Run strict review khusus:

- Zero/nonzero summary reconciliation.
- Unknown record statuses.
- Pullup topology.
- Populated properties ownership.
- Evidence relocation and mutation.

### Commit

```text
docs: record generated evidence hardening
```

---

## Traceability

| Finding | Task |
|---|---|
| Zero-exit unknown/SKIPPED/BLOCKED record false PASS | 1 |
| Malformed optional counters pass | 1 |
| Nonzero FAIL inconsistent summary | 1 |
| Connectivity value/package/MPN ignored | 2 |
| required_pullup checks names only | 3 |
| required_pullup uses ref as registry key | 3 |
| Absolute evidence paths | 4 |
| Stale evidence hashes | 5 |
| Trailing whitespace | 0 |

## Definition of Done

1. PASS requires all top-level records recognized passing and summary exact.
2. FAIL requires one exact expected failed record and consistent summary.
3. Unknown/SKIPPED/BLOCKED/missing record status produces BLOCKED.
4. Malformed optional counters produce BLOCKED.
5. Every populated value/package/MPN is asserted or explicit BLOCKED.
6. Required pullup verifies exact opposite-pin signal-to-rail topology.
7. Evidence paths are relative, POSIX, and contained.
8. Both retained artifacts are rehashed before Check/report.
9. pytest passes.
10. pyright zero errors.
11. `git diff --check` clean.
12. CI all pass.
13. Adapter registry remains empty until live Diode evidence exists.
