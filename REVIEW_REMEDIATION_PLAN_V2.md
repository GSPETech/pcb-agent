# Review Remediation Plan V2

Target branch: `fix/review-remediation`

Base branch: `master`

PR: `https://github.com/GSPETech/pcb-agent/pull/1`

Plan ini memperbaiki seluruh temuan review kedua. Urutan wajib dijaga karena
task generated TestBench bergantung pada contract validation, evidence parser,
dan hasil spike Diode yang sudah terbukti.

## Aturan Eksekusi

1. Kerjakan task berurutan.
2. Satu task menghasilkan satu commit Conventional Commits.
3. Jangan mengubah acceptance, expected connectivity, schema, validator, atau
   test supaya desain invalid lolos.
4. Unsupported mapping atau evidence selalu `BLOCKED`, bukan tebakan dan bukan
   `PASS`.
5. Jalankan setelah setiap task:

   ```powershell
   python -m pytest tests/ -q
   git diff --check
   ```

6. Jalankan `python -m pyright` mulai Task 11 sampai nol error.
7. Jangan merge PR sebelum real Diode integration test generated TestBench
   berhasil pada WSL ext4.
8. `production_ready` dan `fabrication_approved` harus selalu `false`.

## Task Map

| Task | Severity | Temuan | Commit |
|---|---|---|---|
| 0 | Hygiene | Untracked plan, trailing whitespace, baseline | `chore: clean remediation branch baseline` |
| 1 | Critical | Module path generated TestBench salah | `fix: resolve generated module paths from test directory` |
| 2 | Critical | Empty JSON results menghasilkan false PASS | `fix: validate generated Diode test results strictly` |
| 3 | Critical | LED mapping belum verified | `fix: block unverified component adapters` |
| 4 | High | Identifier/source injection dari contract values | `fix: generate injection-safe Zener source` |
| 5 | High | Connectivity semantics diam-diam diabaikan | `fix: fail closed on unsupported connectivity semantics` |
| 6 | High/Medium | Contract reference dan test path invariant | `fix: enforce canonical contract references` |
| 7 | Medium | Filename/provenance generated evidence | `fix: preserve generated verification provenance` |
| 8 | Medium | FAIL versus BLOCKED salah | `fix: classify generated verification failures` |
| 9 | Medium | JSON Schema integer dan schema-tree semantics | `fix: validate schema trees and numeric semantics` |
| 10 | High/Medium | Fake pcb dan generated tests tidak realistis | `test: exercise generated verification result contracts` |
| 11 | High | Pyright CI gagal | `fix: satisfy strict project type checks` |
| 12 | Critical/High | Spike dan real Diode integration | `test: verify generated TestBenches with Diode` |
| 13 | Low | Contract traversal test structure | `test: separate canonical path regression cases` |
| 14 | Final | Full verification, docs, PR | `docs: record generated verification evidence` |

---

## Task 0 - Branch Hygiene dan Baseline

### Tujuan

Membersihkan branch supaya hasil test, diff, dan commit berikutnya dapat
dipercaya.

### Langkah

1. Periksa branch dan worktree:

   ```powershell
   git branch --show-current
   git status --short
   git log --oneline --decorate -15
   ```

2. Pastikan branch aktif `fix/review-remediation`.
3. `IMPLEMENTATION_PLAN.md` masih untracked. Pilih satu:
   - Commit jika masih menjadi dokumen proyek yang diperlukan.
   - Hapus jika hanya scratch plan lama.
   Jangan biarkan file ikut commit lain secara tidak sengaja.
4. Hapus trailing whitespace yang dilaporkan `git diff --check` dari:
   - `README.md`
   - `src/pcb_agent/cli.py`
   - `src/pcb_agent/contracts.py`
   - `src/pcb_agent/diode.py`
   - `src/pcb_agent/generated_testbench.py`
   - `tests/test_policy_config.py`
5. Jangan format seluruh repo. Ubah hanya trailing whitespace supaya diff kecil.
6. Jalankan baseline:

   ```powershell
   python -m pytest tests/ -v
   python -m pyright
   git diff --check master...HEAD
   ```

7. Simpan hasil aktual dalam commit body atau catatan PR:
   - Pytest baseline: `98 passed, 3 skipped`.
   - Pyright baseline: gagal; jumlah error aktual dicatat.
   - Real Diode Windows: blocked OS error 1314.

### Test

```powershell
git diff --check
python -m pytest tests/ -q
```

### Acceptance

- Tidak ada trailing whitespace.
- Tidak ada untracked file yang tidak disengaja.
- Test runtime tetap lolos.

### Commit

```text
chore: clean remediation branch baseline
```

---

## Task 1 - Perbaiki Module Path Generated TestBench

### Menyelesaikan

- Critical: generated TestBench memakai `Module("src/...")` dari bawah
  directory `tests/`.

### Masalah

Generated file berada di:

```text
tests/.pcb-agent-connectivity.generated.zen
tests/.pcb-agent-specification.generated.zen
```

Diode menyelesaikan import relatif terhadap file TestBench. Karena itu source
`src/blinky.zen` harus dirender sebagai `../src/blinky.zen`.

### Perubahan

#### `src/pcb_agent/generated_testbench.py`

1. Tambahkan helper stdlib:

   ```python
   import posixpath
   from pathlib import PurePosixPath

   GENERATED_TEST_DIRECTORY = PurePosixPath("tests")

   def _module_path_from_generated_test(source: str) -> str:
       source_path = PurePosixPath(source)
       if source_path.is_absolute() or ".." in source_path.parts:
           raise GeneratorError("source path must be workspace-relative")
       relative = posixpath.relpath(
           source_path.as_posix(),
           GENERATED_TEST_DIRECTORY.as_posix(),
       )
       return relative
   ```

2. Kedua renderer wajib memakai:

   ```python
   module_path = _module_path_from_generated_test(project.source)
   f"M = Module({_zener_string(module_path)})"
   ```

3. Jangan hardcode `../src`. Source dapat berada di directory lain yang masih
   valid dalam workspace.

### Test

Tambahkan ke `tests/test_generated_testbench.py`:

1. `src/blinky.zen` menjadi `../src/blinky.zen`.
2. `boards/main.zen` menjadi `../boards/main.zen`.
3. Absolute source ditolak.
4. Source dengan `..` ditolak.
5. Connectivity dan specification renderer memakai path yang sama.

### Integration Test Minimum

Pada Task 12, generated file harus benar-benar dikompilasi oleh Diode. Task ini
belum boleh dianggap membuktikan syntax hanya dari substring test.

### Acceptance

- Tidak ada generated `Module("src/...`)`.
- Unit test path relatif lolos.
- Unknown/unsafe source path menghasilkan `GeneratorError` dan CLI `BLOCKED`.

### Commit

```text
fix: resolve generated module paths from test directory
```

---

## Task 2 - Strict Generated Result Validation

### Menyelesaikan

- Critical: `{"results": []}` + exit zero menghasilkan `PASS`.
- Medium: malformed/missing generated evidence tidak dibedakan.

### Desain

Jangan biarkan `result_check()` menentukan PASS hanya dari process exit.
Generated TestBench mempunyai parser khusus yang memastikan expected check
benar-benar dijalankan dan lolos.

### Perubahan

#### `src/pcb_agent/diode.py`

1. Buat helper pure function:

   ```python
   def validate_test_json(
       stdout: str,
       expected_bench: str,
       expected_check: str,
   ) -> Mapping[str, Any]:
   ```

2. Parser harus memastikan:
   - Output tidak truncated.
   - Root adalah object.
   - `results` adalah list non-empty.
   - `summary` adalah object.
   - `summary.total`, `summary.passed`, `summary.failed` adalah integer
     non-negative, bukan bool.
   - `summary.total == len(results)`.
   - `passed + failed == total`.
   - `failed == 0`.
   - Optional `failures` dan `errors`, bila integer, harus nol.
   - Expected record ditemukan berdasarkan structured fields:
     `test_bench_name`/`check_name` atau verified equivalent dari Diode 0.4.34.
   - Expected record status salah satu `PASS`, `PASSED`, `OK`.
   - Tidak ada record expected dengan status gagal.

3. Empty results selalu `ValueError`, walaupun summary nol.
4. Jangan mencari expected check dengan substring recursive yang dapat cocok
   object diagnostic tidak terkait. Gunakan exact structured fields.
5. `execute_generated_test()` menerima parameter terpisah:

   ```python
   bench_name: str
   check_name: str
   generated_filename: str
   ```

6. Setelah process exit zero, panggil `validate_test_json`. Validation error
   diteruskan ke CLI untuk diklasifikasi `BLOCKED`, bukan `PASS`.

### Test

Buat/extend `tests/test_generated_result.py`:

1. Valid result + consistent summary diterima.
2. `results: []` ditolak.
3. Expected bench tidak ditemukan ditolak.
4. Expected check tidak ditemukan ditolak.
5. Failed status ditolak sebagai assertion failure marker.
6. Summary total mismatch ditolak.
7. Summary passed+failed mismatch ditolak.
8. `errors > 0` ditolak.
9. Malformed JSON ditolak.
10. Truncated output ditolak sebelum parse.
11. Unrelated passing record tidak memenuhi expected record.

### Acceptance

- Exit zero saja tidak pernah cukup untuk generated `PASS`.
- Empty/malformed/inconsistent evidence menghasilkan `BLOCKED`.
- Expected generated check harus ditemukan secara exact.

### Commit

```text
fix: validate generated Diode test results strictly
```

---

## Task 3 - Block Unverified Component Adapters

### Menyelesaikan

- Critical: LED mapping masih `LIKELY BUT NOT VERIFIED` tetapi aktif.

### Perubahan

#### `src/pcb_agent/generated_testbench.py`

1. Ubah adapter menjadi versioned evidence object:

   ```python
   @dataclass(frozen=True)
   class ComponentAdapter:
       instance_suffix: str
       pins: Mapping[str, str]
       verified_pcbc_versions: frozenset[str]
       evidence_sha256: str
   ```

2. Hapus LED dari `_ADAPTERS` sampai Task 12 memberi captured evidence.
3. Jangan menyebut resistor verified bila belum ada raw evidence hash yang dapat
   ditemukan di repo. Jika evidence resistor juga hanya dokumen informal, block
   resistor juga sampai Task 12.
4. Renderer menerima exact `pcbc_version` dari capability/lock metadata. Adapter
   hanya aktif bila installed version tercantum dalam verified versions.
5. Unknown kind atau unverified version menghasilkan:

   ```python
   raise GeneratorError(
       f"unverified adapter for {kind} on pcbc {version}"
   )
   ```

6. CLI memetakan ke `BLOCKED`.

### Test

1. LED sebelum evidence menghasilkan `GeneratorError`.
2. Resistor pada unknown `pcbc` version menghasilkan `GeneratorError`.
3. Verified kind+version baru aktif setelah registry diberi evidence fixture.
4. Empty evidence hash ditolak ketika registry dibangun.

### Acceptance

- Tidak ada adapter aktif dengan status dokumentasi `LIKELY BUT NOT VERIFIED`.
- Unsupported/unverified mapping tidak pernah menghasilkan PASS.

### Commit

```text
fix: block unverified component adapters
```

---

## Task 4 - Injection-Safe Zener Generation

### Menyelesaikan

- High: net names masuk identifier Zener.
- High: diagnostic string tidak escaped.

### Perubahan

#### `src/pcb_agent/generated_testbench.py`

1. Jangan gunakan contract value untuk Python/Zener identifier.
2. Ganti:

   ```python
   observed_{net_name}
   ```

   dengan index:

   ```python
   observed_net_0
   observed_net_1
   ```

3. Buat helper untuk semua literal:

   ```python
   def _zener_string(value: str) -> str:
       if not isinstance(value, str):
           raise GeneratorError("Zener literal must be string")
       return json.dumps(value, ensure_ascii=True)
   ```

4. Semua message `check(..., MESSAGE)` harus memakai `_zener_string(message)`.
   Jangan menulis `'missing {contract_value}'` manual.
5. Semua dictionary key, module path, component path, pin, net, expected value,
   package, dan check message harus melewati `_zener_string`.
6. `bench_name` dan `case_name` bukan contract values, tetapi tetap validasi
   dengan regex identifier aman:

   ```text
   ^[A-Za-z][A-Za-z0-9_]{0,63}$
   ```

7. Jangan menyisipkan raw tuple text ke diagnostic message. Buat message data
   terpisah lalu serialize.

### Test

Gunakan contract values:

```text
3V3-A
LED ANODE
O'CLOCK
X\ncheck(True, "injected")
R1\"evil
```

Pastikan:

1. Generated identifiers tetap `observed_net_N`.
2. Generated code hanya memiliki expected number of `check(` calls.
3. Newline/quote tampil escaped dalam literal.
4. Contract value tidak muncul sebagai executable source di luar quoted literal.
5. Invalid bench/case name ditolak.

### Acceptance

- Contract-controlled values tidak pernah menjadi identifier.
- Semua contract-controlled strings escaped lewat satu helper.
- Injection test tidak dapat menambah check/expression.

### Commit

```text
fix: generate injection-safe Zener source
```

---

## Task 5 - Fail Closed pada Connectivity Semantics

### Menyelesaikan

- High: value/package/MPN/required_pullup/unreferenced component diabaikan.

### Keputusan Ownership

Pisahkan gate:

- `CONNECTIVITY` memeriksa component existence dan pin-to-net topology.
- `SPECIFICATION` memeriksa value/package/MPN bila ada verified property API.

Field tidak boleh diperiksa dua kali, tetapi tidak boleh diabaikan.

### Perubahan Contract Coverage Matrix

Buat di `generated_testbench.py` atau module baru:

```python
SUPPORTED_CONNECTIVITY_FIELDS = {
    "component": {"kind"},
    "net": {"members"},
    "rules": {"forbid_unlisted_members", "required_power_nets"},
}
```

Semantics:

1. Setiap component declaration harus dibuktikan ada, walau tidak masuk net.
2. `kind` harus dibuktikan bila verified component type API tersedia; jika tidak,
   `BLOCKED`.
3. `value`, `package`, `mpn` harus ditandai sebagai responsibility
   `SPECIFICATION`. Specification generator harus benar-benar memeriksanya atau
   block.
4. `required_pullup`:
   - Implementasikan hanya setelah pin mapping dua sisi verified.
   - Signal net harus memuat pin pullup component.
   - Rail net harus memuat pin lain dari component sama.
   - Bila tidak dapat ditentukan exact, `GeneratorError` -> `BLOCKED`.
5. Unknown key pada schema sudah ditolak lewat `additionalProperties: false`.

### Test

1. Component tanpa net tetap menghasilkan existence assertion.
2. Component missing menghasilkan FAIL pada real/fake structured result.
3. `required_pullup` tanpa verified adapter menghasilkan BLOCKED.
4. Required pullup wrong rail menghasilkan FAIL ketika adapter verified.
5. Connectivity component dengan `mpn` tetapi specification evidence unsupported
   menghasilkan SPECIFICATION BLOCKED, bukan overall PASS.
6. Strict net mode menolak extra net dan member.
7. Non-strict mode menerima extra, tetapi tetap mensyaratkan expected member.

### Acceptance

- Tidak ada schema-supported field yang diam-diam diabaikan.
- Setiap field punya owner gate atau explicit BLOCKED.

### Commit

```text
fix: fail closed on unsupported connectivity semantics
```

---

## Task 6 - Canonical Contract References

### Menyelesaikan

- High: `tests/../src/board.zen` lolos test path policy.
- Medium: cross-contract references invalid baru ditemukan saat runtime.

### Perubahan

#### `src/pcb_agent/contracts.py`

1. Tambahkan lexical path validator:

   ```python
   def _reject_unsafe_relative_path(value: str, field: str) -> PurePosixPath:
       normalized = value.replace("\\", "/")
       path = PurePosixPath(normalized)
       if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
           raise ContractError(f"{field} must be a canonical workspace-relative path")
       return path
   ```

2. Untuk `project.test`:
   - Lexical first segment harus exact `tests`.
   - Suffix exact `.zen`.
   - Resolve canonical path.
   - Resolved parent harus berada di canonical `<root>/tests`.
   - File/salah satu parent symlink ditolak.
3. Untuk `project.source`:
   - Workspace-relative canonical path.
   - Tidak ada `.`/`..`.
   - Resolved path strictly dalam root.
4. Cross-contract validation:
   - Setiap `REF.PIN` di `nets.*.members`: `REF` ada di `components`.
   - Setiap `required_power_nets` item ada di `nets`.
   - `required_pullup.component` ada di `components`.
   - `required_pullup.rail` ada di `nets`.
   - `required_pullup.component` punya expected member pada signal net dan rail
     net bila schema mensyaratkan topology lengkap; bila belum cukup informasi,
     reject contract dengan pesan jelas atau biarkan generator BLOCKED sesuai
     frozen contract decision. Pilih satu dan dokumentasikan.

### Exit Semantics

Semua pelanggaran ini adalah invalid config:

```text
exit 3
```

Bukan runtime BLOCKED.

### Test

Pisahkan test functions:

1. Source `../outside.zen` ditolak.
2. Test `tests/../src/board.zen` ditolak.
3. Absolute source ditolak.
4. Absolute test ditolak.
5. Backslash traversal ditolak.
6. Symlink test keluar root ditolak.
7. Net member dengan component unknown ditolak.
8. Required power net unknown ditolak.
9. Pullup component unknown ditolak.
10. Pullup rail unknown ditolak.
11. CLI doctor untuk semua kasus exit `3`.

### Commit

```text
fix: enforce canonical contract references
```

---

## Task 7 - Generated Filename dan Evidence Provenance

### Menyelesaikan

- Medium: specification memakai filename connectivity.
- Medium: generated source artifact orphaned dari report.

### Perubahan

#### `src/pcb_agent/diode.py`

1. Jangan hardcode connectivity filename.
2. Definisikan allowlist:

   ```python
   GENERATED_TESTS = {
       "CONNECTIVITY": (
           "tests/.pcb-agent-connectivity.generated.zen",
           "connectivity-testbench.zen",
       ),
       "SPECIFICATION": (
           "tests/.pcb-agent-specification.generated.zen",
           "specification-testbench.zen",
       ),
   }
   ```

3. Unknown `check_id` ditolak sebelum file write.
4. `execute_generated_test` return object baru:

   ```python
   @dataclass(frozen=True)
   class GeneratedTestResult:
       process: ProcessResult
       generated_path: Path
       generated_sha256: str
       result_path: Path
       result_sha256: str
   ```

5. Tulis generated source dan raw result secara atomic ke `run.raw_directory`.
6. Hash retained file setelah write; jangan hanya hash source string sebelum
   retained write.
7. Verify retained file hash sebelum report persistence.

#### `src/pcb_agent/cli.py`

Evidence shape:

```json
{
  "generated_testbench": {
    "path": "...",
    "sha256": "sha256:..."
  },
  "result": {
    "path": "...",
    "sha256": "sha256:..."
  }
}
```

8. Paths harus report-relative, bukan absolute home path.

### Test

1. Connectivity dan specification memakai filename berbeda.
2. Unknown check ID ditolak.
3. Evidence memuat dua path dan dua digest.
4. Digest cocok dengan retained files.
5. Mutasi retained generated source sebelum report menyebabkan integrity error.
6. Report tidak membocorkan absolute home path.

### Commit

```text
fix: preserve generated verification provenance
```

---

## Task 8 - Klasifikasi FAIL versus BLOCKED

### Menyelesaikan

- Medium: semua nonzero generated command dianggap design FAIL.

### Desain Result Taxonomy

| Kondisi | Status |
|---|---|
| Generated renderer unsupported | BLOCKED |
| Generated source syntax/compile/import error | BLOCKED |
| Tool missing/timeout/privilege | BLOCKED |
| JSON malformed/truncated/inconsistent | BLOCKED |
| Expected check tidak dieksekusi | BLOCKED |
| Structured expected assertion executed dan failed | FAIL |
| Structured expected assertion executed dan passed | PASS |

### Perubahan

1. Buat exception types di `diode.py`:

   ```python
   class GeneratedEvidenceError(ValueError): ...
   class GeneratedCompatibilityError(GeneratedEvidenceError): ...
   class GeneratedAssertionFailure(GeneratedEvidenceError): ...
   ```

2. Parser result mengembalikan structured classification, bukan hanya raise
   generic `ValueError`.
3. Process nonzero:
   - Jika valid structured JSON menunjukkan expected assertion failure:
     `GeneratedAssertionFailure` -> FAIL.
   - Bila tidak ada structured assertion record: compatibility/environment ->
     BLOCKED.
4. `diode.result_check()` tetap untuk ordinary commands. Jangan pakai generic
   mapping tersebut untuk generated test outcome.
5. Tambahkan function:

   ```python
   def generated_result_check(...) -> Check:
   ```

### Test

1. Assertion false structured -> FAIL.
2. Syntax diagnostic -> BLOCKED.
3. Module import missing -> BLOCKED.
4. Timeout -> BLOCKED.
5. Privilege error -> BLOCKED.
6. Empty JSON -> BLOCKED.
7. Malformed JSON -> BLOCKED.
8. Expected assertion PASS -> PASS.

### Commit

```text
fix: classify generated verification failures
```

---

## Task 9 - JSON Schema Tree dan Numeric Semantics

### Menyelesaikan

- Medium: JSON Schema integer semantics salah.
- Medium: malformed optional nested schema tidak diperiksa.

### Perubahan

#### 1. Integer semantics

`type: integer` menerima:

```text
1
1.0
-2.0
```

Menolak:

```text
True
1.5
NaN
Infinity
```

Implementasi:

```python
def _is_json_integer(value: Any) -> bool:
    return (
        isinstance(value, int)
        and not isinstance(value, bool)
    ) or (
        isinstance(value, float)
        and math.isfinite(value)
        and value.is_integer()
    )
```

`number` juga harus menolak bool dan non-finite float.

#### 2. Validate schema tree first

Buat public/internal function:

```python
def validate_schema(schema: Any, root: Mapping[str, Any] | None = None, path: str = "<schema>") -> None:
```

Function harus menelusuri semua subschema tanpa bergantung instance:

- `$defs` values
- `properties` values
- `patternProperties` values
- `items`
- `additionalProperties` bila schema object
- `$ref` syntax dan target existence

Validasi seluruh keyword shape, unknown keyword, regex, min/max value, unique
required, type names, enum non-empty.

`validate()` wajib:

```python
validate_schema(schema)
_validate(instance, schema, schema, path)
```

Jangan ulang validate tree pada setiap recursive instance node; lakukan sekali
di public entry point.

### Test

1. `1.0` accepted as integer.
2. `1.5` rejected as integer.
3. `True` rejected as integer/number.
4. NaN/Infinity rejected.
5. Optional absent property dengan unsupported nested keyword tetap
   `SchemaError`.
6. Optional absent property dengan malformed `minLength` tetap error.
7. Malformed `$defs` ditolak.
8. Invalid regex pada absent `patternProperties` ditolak.
9. Semua repo schema lolos `validate_schema`.

### Commit

```text
fix: validate schema trees and numeric semantics
```

---

## Task 10 - Realistic Fake PCB dan Generated Flow Tests

### Menyelesaikan

- High: tests hanya assert source strings.
- Medium: fake `pcb` tidak menguji generated result contract.

### Perubahan

#### `tests/helpers.py`

Upgrade `make_fake_pcb` supaya:

1. `--help` return zero.
2. `pcb test FILE -f json`:
   - Pastikan FILE ada.
   - Jika filename generated connectivity, emit exact structured record untuk
     `PcbAgentConnectivity._check_connectivity`.
   - Jika generated specification, emit exact structured record untuk
     `PcbAgentSpecification._check_specification`.
   - Emit summary konsisten.
3. Mode behavior dikontrol marker/environment test-only:
   - PASS.
   - ASSERTION_FAIL.
   - EMPTY_RESULTS.
   - MALFORMED_JSON.
   - SUMMARY_MISMATCH.
   - TOOL_ERROR.
4. Fake harus menolak generated path yang salah.

### Unit/Contract Tests

Tambahkan:

1. Generated renderer source path relative benar.
2. Generated names injection-safe.
3. Generated result PASS.
4. Generated assertion FAIL.
5. Empty result BLOCKED.
6. Malformed result BLOCKED.
7. Summary mismatch BLOCKED.
8. Wrong bench/check identity BLOCKED.
9. Connectivity/spec filenames berbeda.
10. Evidence retained + hashes cocok.

### Real Syntax Validation

Unit string assertions bukan bukti syntax. Tandai test berikut dengan integration
marker atau environment capability:

```python
@unittest.skipUnless(real_diode_available(), "requires Diode")
```

Test tersebut dituntaskan pada Task 12.

### Commit

```text
test: exercise generated verification result contracts
```

---

## Task 11 - Selesaikan Semua Pyright Errors

### Menyelesaikan

- High: required CI typecheck gagal.

### Aturan

Jangan mematikan `reportUnusedImport`, `typeCheckingMode`, file, atau job CI.
Jangan menambah broad `# type: ignore` untuk menutupi design error. Ignore lokal
hanya bila library typing defect dapat dijelaskan.

### Error Groups dan Fix

#### `cli.py`

1. Hapus import unused `fnmatch`.
2. Pastikan report status narrowed sebelum lookup:

   ```python
   status = report.status
   if status is None:
       raise ValueError("report status was not aggregated")
   return EXIT_CODES[status]
   ```

3. `_tool_check` callback typed `Callable[[ProjectState], ProcessResult]`.
4. Backend protocol harus konsisten. `CodexBackend.execute` saat ini return
   `None`, sedangkan command backend return `BackendResult`. Buat Protocol/base
   method dengan satu return type atau pisahkan branch sebelum execute.
5. Jangan access `.process` pada optional result tanpa narrowing.

#### `contracts.py`

1. Setelah runtime validation, narrow `name`, `source`, `test`, `kind`,
   `requirement` ke exact string variables.
2. Jangan mengandalkan JSON Schema runtime untuk static typing.

#### `diode.py`

1. Hapus unused typing imports.
2. `configured_command` return type jangan include `None` bila function tidak
   pernah return None.
3. Pastikan command tuple/list non-empty secara type-visible.

#### `generated_testbench.py`

Hapus unused `Any`, atau gunakan type alias yang benar.

#### `jsonschema.py`

Narrow dict/list branches dengan local typed variables. `_json_equal` harus
tidak index union `bool | dict` tanpa narrowing.

#### `process.py`

Samakan `Popen` generic dengan actual mode. Karena output diarahkan ke binary
temporary handles, gunakan `Popen[bytes]` pada `_kill_process_tree`, atau ubah
subprocess mode secara konsisten.

### Verification

```powershell
python -m pyright
```

Expected exact:

```text
0 errors, 0 warnings, 0 informations
```

Lalu:

```powershell
python -m pytest tests/ -q
```

### Commit

```text
fix: satisfy strict project type checks
```

---

## Task 12 - Empirical Diode Spike dan Real Generated Tests

### Menyelesaikan

- Critical: LED/resistor mapping belum punya evidence cukup.
- Critical: generated TestBench belum pernah dijalankan nyata.

### Environment Wajib

Gunakan WSL2 Ubuntu dan ext4 filesystem. Jangan jalankan repo langsung di
`/mnt/c` karena integration result sebelumnya menemukan permission semantics
bermasalah.

### Langkah

1. Copy branch ke ext4:

   ```bash
   cp -a /mnt/c/Users/jrjua/diodeinc ~/pcb-agent-review
   cd ~/pcb-agent-review
   git switch fix/review-remediation
   ```

2. Capture exact versions:

   ```bash
   pcb --version
   pcb toolchain show
   ```

3. Generate connectivity/spec TestBench untuk `valid-blinky` melalui helper
   script/test, lalu run:

   ```bash
   cd fixtures/valid-blinky
   pcb test tests/.pcb-agent-connectivity.generated.zen -f json \
     > /tmp/connectivity-result.json
   pcb test tests/.pcb-agent-specification.generated.zen -f json \
     > /tmp/specification-result.json
   sha256sum /tmp/*-result.json
   ```

4. Verify actual:
   - Module path resolves.
   - Bench/check identity fields.
   - Component suffix resistor.
   - Resistor pin names.
   - LED suffix/pin names.
   - Value and package property API.
5. Run invalid fixtures:
   - Wrong value must structured FAIL in specification.
   - Wrong connectivity must structured FAIL in connectivity.
6. Capture raw JSON in a versioned test evidence directory, for example:

   ```text
   tests/evidence/diode-0.4.34/
   ```

   Include SHA-256 manifest.
7. Update adapter registry only for exact verified `pcbc` version.
8. Update `docs/spike-diode-net-naming.md`:
   - Status no longer DEFERRED for tested mappings.
   - Commands, date, version, artifact hashes.
   - Every mapping `VERIFIED` or `REQUIRES TEST`.
9. Add integration test replaying captured JSON parser contract.
10. Add optional live integration test that skips only when Diode absent.

### Acceptance

- Generated connectivity TestBench compiles and runs under pinned Diode.
- Generated specification TestBench compiles and runs.
- Valid fixture PASS.
- Invalid connectivity fixture FAIL.
- Invalid value fixture FAIL.
- Mapping registry references evidence SHA.
- Unsupported generic remains BLOCKED.

### Commit

```text
test: verify generated TestBenches with Diode
```

---

## Task 13 - Pisahkan Canonical Path Regression Tests

### Menyelesaikan

- Low: source traversal test tertanam dalam test lain.

### Perubahan

`tests/test_contracts.py` harus memiliki function terpisah:

```python
test_source_parent_traversal_is_rejected
test_testbench_parent_traversal_is_rejected
test_absolute_source_is_rejected
test_absolute_testbench_is_rejected
test_testbench_symlink_escape_is_rejected
test_unknown_connectivity_component_is_rejected
test_unknown_required_power_net_is_rejected
test_unknown_pullup_component_is_rejected
test_unknown_pullup_rail_is_rejected
```

Jangan nested test logic setelah assertion dari test lain.

### Acceptance

- Pytest output menampilkan setiap case secara terpisah.
- Failure diagnostic menunjukkan invariant yang rusak.

### Commit

```text
test: separate canonical path regression cases
```

---

## Task 14 - Final Verification, Docs, dan PR Update

### Full Verification

Windows:

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest tests/ -v
python -m pyright
git diff --check master...HEAD
```

WSL ext4:

```bash
python -m pytest tests/ -v
python -m pyright
python pcb-agent verify \
  --project fixtures/valid-blinky \
  --profile schematic \
  --format json
python pcb-agent verify \
  --project fixtures/invalid-connectivity \
  --profile schematic \
  --format json
python pcb-agent verify \
  --project fixtures/invalid-value \
  --profile schematic \
  --format json
```

Expected:

| Fixture | DIODE_BUILD | ZENER_TEST | CONNECTIVITY | SPECIFICATION | Overall |
|---|---|---|---|---|---|
| valid-blinky | PASS | PASS | PASS | PASS | PASS |
| invalid-connectivity | PASS | FAIL or generated connectivity FAIL | FAIL | factual dependent result | FAIL |
| invalid-value | PASS | FAIL or generated specification FAIL | factual dependent result | FAIL | FAIL |
| invalid-syntax | FAIL | dependent FAIL | dependent FAIL | dependent FAIL | FAIL |

### Documentation

Update:

- `README.md`: generated evidence flow dan fail-closed unsupported adapters.
- `AGENT_PROTOCOL.md`: unsupported mapping -> BLOCKED.
- `INTEGRATION_RESULTS.md`: exact WSL run, versions, exits, artifact hashes.
- `docs/spike-diode-net-naming.md`: verified mapping table.

### Evidence Audit

Periksa report memuat:

- Generated TestBench relative path/hash.
- Raw result relative path/hash.
- Exact tool version.
- Sanitized argv.
- No absolute home path.
- `production_ready: false`.
- `fabrication_approved: false`.

### PR Checks

```powershell
git status --short
git diff --check master...HEAD
gh pr checks 1
```

Semua required checks harus PASS. Jangan merge bila live Diode generated test
belum terbukti.

### Final Review

Jalankan strict review baru terhadap:

```text
master...fix/review-remediation
```

Fokus:

- False PASS.
- Generated-code injection.
- FAIL/BLOCKED classification.
- Evidence integrity.
- Path containment.
- Versioned adapter evidence.

### Commit

```text
docs: record generated verification evidence
```

---

## Traceability

| Review Finding | Task |
|---|---|
| Generated module path salah | 1, 12 |
| Empty results false PASS | 2, 10 |
| LED mapping belum verified | 3, 12 |
| Net names menjadi identifiers | 4 |
| Diagnostic source injection | 4 |
| Connectivity semantics diabaikan | 5, 12 |
| `project.test` canonical bypass | 6, 13 |
| Cross-contract references invalid | 6, 13 |
| Specification memakai filename connectivity | 7 |
| FAIL/BLOCKED salah | 8, 10 |
| Generated artifact tidak masuk evidence | 7 |
| JSON integer semantics | 9 |
| Malformed absent nested schema | 9 |
| Pyright CI gagal | 11 |
| Tests hanya assert strings | 10, 12 |
| Fake pcb tidak realistis | 10 |
| Traversal test nested | 13 |
| Trailing whitespace | 0 |

## Definition of Done

Remediation selesai hanya bila:

1. Exit zero dan empty/unrelated results tidak dapat menghasilkan PASS.
2. Generated module path benar dan dibuktikan Diode nyata.
3. Contract values tidak dapat menjadi identifier atau menginjeksi source.
4. Hanya versioned, evidence-backed adapters yang aktif.
5. Semua schema-supported contract semantics diverifikasi atau explicit BLOCKED.
6. Canonical test/source containment enforced di contract loader.
7. Generated source dan result retained, hashed, dan linked dari report.
8. Assertion mismatch = FAIL; compatibility/environment/evidence problem = BLOCKED.
9. JSON Schema subset mengikuti integer semantics dan memvalidasi seluruh tree.
10. Fake dan live integration tests mencakup generated flow.
11. `python -m pyright` menghasilkan nol error.
12. `git diff --check` bersih.
13. Windows dan WSL pytest lolos.
14. PR required checks PASS.
15. Valid fixture PASS dan invalid fixtures FAIL berdasarkan deterministic
    evidence.
16. `production_ready` dan `fabrication_approved` selalu `false`.
