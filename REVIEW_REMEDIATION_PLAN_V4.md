# Review Remediation Plan V4

Target branch: `fix/review-remediation`

PR: `https://github.com/GSPETech/pcb-agent/pull/1`

Plan ini menutup seluruh temuan review final: 2 Critical, 5 High, 7 Medium, dan
7 Low. Verdict review terakhir adalah **belum aman di-merge**. Plan ini
menghilangkan status tersebut.

## Aturan Eksekusi

1. Kerjakan task berurutan. Task berikutnya bergantung pada sebelumnya.
2. Satu task satu commit Conventional Commits.
3. Jangan mengaktifkan adapter produksi tanpa captured Diode evidence.
4. Evidence malformed, kosong, atau tidak konsisten selalu `BLOCKED`.
5. Unsupported contract semantics selalu `BLOCKED`, bukan silent skip.
6. Jalankan setelah setiap task:

   ```powershell
   python -m pytest tests/ -q
   python -m pyright
   git diff --check
   ```

7. Jangan merge sebelum Task 0 sampai Task 8 selesai dan CI hijau.

## Task Map

| Task | Severity | Fokus | Commit |
|---|---|---|---|
| 0 | Low | Trailing whitespace dan baseline | `style: clean generated evidence whitespace` |
| 1 | Critical | `mpn` dan constraint connectivity tidak di-assert | `fix: assert every specification constraint` |
| 2 | High | CRLF hash mismatch di Windows | `fix: write generated evidence with LF newlines` |
| 3 | High | Adapter registry key dan `pcbc_version` | `fix: key adapters by kind and thread pcbc version` |
| 4 | High | `check spec` dan `check connectivity` exit 4 | `fix: separate check scope from report profile` |
| 5 | High | Klasifikasi tidak membaca artifact ter-hash | `fix: classify from verified evidence bytes` |
| 6 | Medium | Dead code dan `NameError` laten | `refactor: remove unreachable classifier branch` |
| 7 | Medium | Prerequisite gagal seharusnya BLOCKED | `fix: block dependent gates on failed prerequisite` |
| 8 | Medium | Validasi `rules`, keyword walker, reports tampering | `fix: close remaining fail-closed gaps` |
| 9 | Medium | Test PASS path dan pullup coverage | `test: cover green run and pullup topology` |
| 10 | Low | Sisa dead code, path absolut, provenance | `refactor: tidy evidence metadata and dead code` |
| 11 | Final | Verifikasi penuh, docs, PR | `docs: finalize generated verification contract` |

---

## Task 0 - Whitespace dan Baseline

### Menyelesaikan

- Low: 8 trailing-whitespace findings yang terlewat commit `190221c`.

### Lokasi Persis

| File | Baris |
|---|---|
| `src/pcb_agent/diode.py` | 370, 372 |
| `src/pcb_agent/generated_testbench.py` | 213, 222, 226, 231, 237, 239 |

Seluruhnya adalah baris yang hanya berisi spasi. Konten kode tidak boleh berubah.

### Langkah

1. Konfirmasi posisi:

   ```powershell
   git diff --check master...HEAD
   ```

2. Hapus hanya trailing spaces dan tabs. Jangan reformat file.
3. Pastikan tidak ada perubahan semantik:

   ```powershell
   git diff --ignore-all-space master...HEAD -- src/pcb_agent/diode.py
   ```

   Output harus sama dengan sebelum perubahan.

4. Baseline:

   ```powershell
   python -m pytest tests/ -q
   python -m pyright
   git diff --check master...HEAD
   ```

### Acceptance

- `git diff --check master...HEAD` tanpa output.
- pytest minimal `138 passed, 5 skipped`.
- pyright `0 errors`.

### Commit

```text
style: clean generated evidence whitespace
```

---

## Task 1 - Assert Setiap Specification Constraint

### Menyelesaikan

- Critical 1: `mpn` divalidasi lalu tidak pernah di-assert.
- Critical 2: constraint pada requirement `type: "connectivity"` dibuang diam-diam.

### Masalah Persis

#### Critical 1

`src/pcb_agent/generated_testbench.py:456-458`:

```python
elif key == "mpn":
    if adapter.mpn_accessor is None:
        raise GeneratorError(f"adapter for {kind} has no verified mpn accessor")
```

Cabang memeriksa accessor lalu berhenti. Tidak ada `lines.append(...)`.

Rantai kegagalannya:

1. Requirement dengan constraint hanya `mpn` masuk cabang ini.
2. Bila `mpn_accessor` tidak `None`, tidak ada assertion dihasilkan.
3. Assertion `in components` di line 428-432 tetap ditambahkan.
4. `components_with_assertions.add(subject)` di line 433 dieksekusi.
5. Ownership guard di line 465-473 melewati subject tersebut.
6. `if not lines[3:]` di line 475 terpenuhi karena ada satu assertion.
7. `SPECIFICATION` dapat `PASS` dengan `mpn` tanpa verifikasi.

Bertentangan dengan `README.md:78-80`.

#### Critical 2

`src/pcb_agent/generated_testbench.py:386-387`:

```python
if rtype == "connectivity":
    continue
```

`continue` dieksekusi sebelum constraint diperiksa. Contract berikut menghasilkan
nol assertion tanpa error:

```json
{
  "id": "REQ-001",
  "type": "connectivity",
  "subject": "R1",
  "constraints": {"value": "1kohm"}
}
```

Ownership guard di 465-473 hanya menutup properti dari
`expected-connectivity.json`, bukan constraint sisi `SPEC.json`.

### Keputusan Desain

Freeze aturan berikut:

| Requirement type | Constraint key diizinkan | Lainnya |
|---|---|---|
| `connectivity` | `members` | `GeneratorError` |
| lainnya | `value`, `package`, `mpn` | `GeneratorError` |

`mpn` tidak punya accessor terverifikasi. Sampai Task 11 spike memberi bukti,
`mpn` selalu `GeneratorError`.

### Perubahan

#### 1. Validasi constraint connectivity

Ganti blok di line 386-387:

```python
if rtype == "connectivity":
    unexpected = set(constraints) - {"members"}
    if unexpected:
        raise GeneratorError(
            f"requirement {rid} of type connectivity declares "
            f"unsupported constraints: {sorted(unexpected)}"
        )
    continue
```

Letakkan sebelum merge dari connectivity component fields, supaya constraint SPEC
yang salah tempat langsung ditolak.

#### 2. `mpn` selalu memblokir

Ganti cabang di line 456-458:

```python
elif key == "mpn":
    raise GeneratorError(
        f"mpn assertion is unsupported for {kind}; "
        f"no verified accessor has been captured"
    )
```

Hapus field `mpn_accessor` dari `ComponentAdapter`, atau pertahankan tetapi
jangan pernah dipakai untuk mengizinkan skip. Pilihan pertama lebih jujur karena
field yang tidak dapat dipakai adalah jebakan.

Jika `mpn_accessor` dipertahankan untuk Task 11, cabang harus:

```python
elif key == "mpn":
    if adapter.mpn_accessor is None:
        raise GeneratorError(f"adapter for {kind} has no verified mpn accessor")
    lines.append(
        "    check(components["
        f"{_zener_string(diode_ref)}"
        f"].{adapter.mpn_accessor}.value == "
        f"{_zener_string(str(expected_value))}, "
        f"{_zener_string(f'wrong mpn for {subject}')})"
    )
```

Jangan biarkan cabang tanpa `lines.append`.

#### 3. Guard struktural

Tambahkan invariant yang menangkap kelas bug ini secara umum. Sebelum
`if not lines[3:]`, hitung jumlah constraint yang diproses dan jumlah assertion
constraint yang dihasilkan:

```python
if asserted_constraints != expected_constraints:
    raise GeneratorError(
        f"generated {expected_constraints} constraints but only "
        f"{asserted_constraints} assertions; refusing incomplete evidence"
    )
```

Ini mencegah cabang baru di masa depan lupa menghasilkan assertion.

### Test

Tambahkan ke `tests/test_generated_testbench.py`:

1. Requirement dengan constraint hanya `mpn` menghasilkan `GeneratorError`.
2. Requirement `type: "connectivity"` dengan constraint `value` menghasilkan
   `GeneratorError`.
3. Requirement `type: "connectivity"` dengan constraint `package` menghasilkan
   `GeneratorError`.
4. Requirement `type: "connectivity"` dengan constraint `members` diterima.
5. Connectivity component dengan `mpn` menghasilkan `GeneratorError`.
6. Requirement dengan `value` dan `mpn` menghasilkan `GeneratorError`, bukan
   assertion `value` saja.
7. Jumlah `check(` dalam generated source sama dengan jumlah constraint yang
   didukung plus satu presence assertion per component.

Test nomor 7 adalah yang paling penting. Ia mengunci invariant, bukan kasus.

### Acceptance

- Tidak ada cabang constraint yang berakhir tanpa `lines.append`.
- `mpn` tidak dapat menghasilkan `PASS`.
- Constraint salah-tempat pada requirement connectivity ditolak.
- Jumlah assertion dapat diverifikasi terhadap jumlah constraint.

### Commit

```text
fix: assert every specification constraint
```

---

## Task 2 - LF Newlines untuk Generated Evidence

### Menyelesaikan

- High 1: hash mismatch permanen di Windows.

### Masalah Persis

Tiga lokasi di `src/pcb_agent/diode.py`:

| Baris | Kode |
|---|---|
| 305 | `test_path.write_text(generated_source, encoding="utf-8")` |
| 311 | `evidence_source.write_text(generated_source, encoding="utf-8")` |
| 317 | `raw_path.write_text(result.stdout, encoding="utf-8")` |

`Path.write_text()` tanpa `newline` memakai `os.linesep` translation. Di Windows
setiap `\n` menjadi `\r\n`.

Line 312-314 kemudian membandingkan:

```python
retained_hash = hashlib.sha256(evidence_source.read_bytes()).hexdigest()
if retained_hash != hashlib.sha256(generated_source.encode("utf-8")).hexdigest():
    raise GeneratedCompatibilityError("retained generated source hash mismatch")
```

Digest file CRLF tidak mungkin sama dengan digest string LF. Setelah registry
terisi, kedua generated check permanen `BLOCKED` di Windows.

### Perubahan

Repo sudah punya pola benar di `state._atomic_write` dan `report._atomic_write`.
Ikuti pola itu.

#### 1. Ketiga write eksplisit LF

```python
test_path.write_text(generated_source, encoding="utf-8", newline="\n")
evidence_source.write_text(generated_source, encoding="utf-8", newline="\n")
raw_path.write_text(result.stdout, encoding="utf-8", newline="\n")
```

#### 2. Pertimbangkan write bytes

Untuk evidence yang di-hash, menulis bytes lebih tegas daripada mengandalkan
parameter newline:

```python
evidence_source.write_bytes(generated_source.encode("utf-8"))
raw_path.write_bytes(result.stdout.encode("utf-8"))
```

Ini menghilangkan seluruh kelas bug newline translation. Pilih satu pendekatan
dan pakai konsisten.

#### 3. Normalisasi stdout

`result.stdout` dapat memuat `\r\n` dari tool. Bila artifact hash harus stabil
lintas platform, normalisasi sebelum write dan hash:

```python
normalized_stdout = result.stdout.replace("\r\n", "\n")
```

Keputusan ini harus eksplisit dan didokumentasikan, karena ia mengubah byte
evidence. Alternatif: simpan raw bytes apa adanya dan jangan bandingkan lintas
platform.

### Test

Test harus berjalan di Windows dan Linux, bukan skip di Windows.

1. Generated source berisi banyak newline ditulis lalu di-hash; digest file sama
   dengan digest `encode("utf-8")`.
2. Retained artifact tidak memuat byte `\r`.
3. Result JSON dengan newline embedded ditulis lalu di-hash; digest cocok.
4. Round-trip: write, read, hash, verify lewat `_verify_retained_artifact`.
5. Jalankan `execute_generated_test` dengan fake tool dan adapter stub, lalu
   pastikan tidak ada `GeneratedCompatibilityError`.

Test nomor 5 yang membuktikan bug ini benar-benar hilang. Test 1 sampai 4 hanya
memeriksa mekanisme.

### Acceptance

- Tidak ada `write_text` tanpa `newline="\n"` untuk artifact ter-hash.
- Digest file dan digest in-memory identik di Windows.
- Test hash round-trip lolos di kedua platform CI.

### Commit

```text
fix: write generated evidence with LF newlines
```

---

## Task 3 - Adapter Registry Key dan `pcbc_version`

### Menyelesaikan

- High 2: `build_adapter_registry` memakai key salah.
- High 3: `pcbc_version` tidak pernah disambungkan.

### Masalah Persis

#### High 2

`src/pcb_agent/generated_testbench.py:51`:

```python
registry[adapter.instance_suffix] = adapter
```

Menyimpan dengan key `"R"`.

`src/pcb_agent/generated_testbench.py:68`:

```python
adapter = _ADAPTERS.get(kind)
```

Lookup dengan key `"resistor"`.

`ComponentAdapter` tidak punya field `kind`, sehingga builder tidak dapat
menghasilkan registry yang berfungsi. Prosedur di
`docs/spike-diode-net-naming.md:142` tidak dapat dijalankan.

#### High 3

`src/pcb_agent/generated_testbench.py:257` dan `:350` default
`pcbc_version="unknown"`. Caller `src/pcb_agent/cli.py:187` dan `:215` tidak
mengirim versi.

`adapter_for` di line 71 membandingkan terhadap literal `"unknown"`. Adapter
dengan `verified_pcbc_versions={"0.4.34"}` selalu ditolak. Satu-satunya cara
menjalankan pipeline adalah menambahkan `"unknown"` ke verified set, yang
membatalkan jaminan `README.md:52-54`.

Catatan penting: `contracts.py:132` memuat `[toolchain].pcb_version` bernilai
`"0.4"` di fixtures. Itu versi toolchain author intent, bukan versi build `pcbc`.
Keduanya tidak boleh dicampur.

### Perubahan

#### 1. Tambahkan `kind` ke adapter

```python
@dataclass(frozen=True)
class ComponentAdapter:
    kind: str
    instance_suffix: str
    pins: Mapping[str, str]
    verified_pcbc_versions: frozenset[str]
    evidence_sha256: str
    value_accessor: str | None = None
    package_accessor: str | None = None
    pullup_pin_pair: tuple[str, str] | None = None
```

Validasi `kind` dengan regex identifier di `__post_init__` atau di builder.

#### 2. Builder key benar dan tolak duplikat

```python
def build_adapter_registry(
    entries: Iterable[ComponentAdapter],
) -> dict[str, ComponentAdapter]:
    registry: dict[str, ComponentAdapter] = {}
    for adapter in entries:
        if not isinstance(adapter.kind, str) or not adapter.kind:
            raise ValueError("adapter kind must be non-empty string")
        if not isinstance(adapter.evidence_sha256, str) or not adapter.evidence_sha256:
            raise ValueError("adapter evidence_sha256 must be non-empty string")
        if adapter.kind in registry:
            raise ValueError(f"duplicate adapter kind: {adapter.kind}")
        registry[adapter.kind] = adapter
    return registry
```

Validasi format `evidence_sha256`: harus `sha256:` diikuti 64 hex lowercase.

#### 3. Probe versi `pcbc` nyata

`doctor_probes` sudah menjalankan `pcb --version`. Buat fungsi terpisah agar
dapat dipakai oleh verify path:

```python
def probe_pcbc_version(project: ProjectState) -> str:
```

Alur:

1. Jalankan `pcb --version`.
2. Non-zero atau timeout: raise `GeneratedCompatibilityError`.
3. Parse output dengan regex yang ketat. Jangan menerima string bebas.
4. Tidak dapat diparse: raise `GeneratedCompatibilityError`.
5. Return exact version string.

Bentuk output nyata belum diverifikasi. Karena itu parser harus fail closed dan
Task 11 harus mencatat bentuk sebenarnya.

#### 4. Sambungkan ke renderer

Hapus default `"unknown"`. Jadikan parameter wajib:

```python
def render_connectivity_testbench(
    project: ProjectState,
    pcbc_version: str,
    bench_name: str = "PcbAgentConnectivity",
    case_name: str = "contract",
) -> str:
```

`cli.py` harus probe versi dulu, dan kegagalan probe menjadi `BLOCKED`:

```python
try:
    pcbc_version = diode.probe_pcbc_version(project)
except diode.GeneratedCompatibilityError as error:
    return _check("CONNECTIVITY", CheckStatus.BLOCKED, f"toolchain version unknown: {error}")
```

#### 5. Jangan campur dengan `[toolchain].pcb_version`

Kalau ingin memeriksa konsistensi kontrak versus installed, lakukan sebagai
check terpisah dengan pesan jelas. Jangan pakai `pcb_version` kontrak sebagai
`pcbc_version` adapter.

### Test

1. `build_adapter_registry` menghasilkan key `"resistor"`, bukan `"R"`.
2. Duplicate kind ditolak.
3. Empty kind ditolak.
4. Empty evidence ditolak.
5. Malformed evidence digest ditolak.
6. `adapter_for("resistor", "0.4.34")` berhasil setelah registry dibangun lewat
   builder.
7. `probe_pcbc_version` menolak output tidak dapat diparse.
8. `probe_pcbc_version` menolak exit non-zero.
9. CLI menghasilkan `BLOCKED` ketika probe versi gagal.
10. Renderer tidak dapat dipanggil tanpa `pcbc_version`.

### Acceptance

- Registry dapat diisi lewat API yang tersedia.
- Versi berasal dari tool nyata, bukan literal `"unknown"`.
- Version gate bermakna, bukan vacuous.
- Kegagalan probe versi menghasilkan `BLOCKED`.

### Commit

```text
fix: key adapters by kind and thread pcbc version
```

---

## Task 4 - Pisahkan Check Scope dari Report Profile

### Menyelesaikan

- High 4: `check spec` dan `check connectivity` selalu exit 4.

### Masalah Persis

`src/pcb_agent/cli.py:57`:

```python
check.add_argument("profile", choices=("schematic", "spec", "connectivity"), nargs="?", default="schematic")
```

Positional bernama `profile`, sehingga menimpa `args.profile`.

`cli.py:493-496` menetapkan `args.profile`, lalu `cli.py:538` meneruskannya ke
`VerificationReport`. `models.py:90-91` menolak nilai selain `schematic` dan
`layout`, menghasilkan `ValueError` yang menjadi exit 4.

Dua command yang diiklankan `README.md:27` mati. Bug ini pre-existing dari
master, tetapi branch ini merombak kode yang mengindeksnya di `cli.py:515-518`.

### Perubahan

#### 1. Dest terpisah

```python
check = sub.add_parser("check")
check.add_argument(
    "scope",
    choices=("schematic", "spec", "connectivity"),
    nargs="?",
    default="schematic",
)
```

#### 2. Jangan sentuh `args.profile` untuk check

`hasattr(args, "profile")` di `cli.py:493` sekarang `False` untuk `check`.
Report profile harus diambil dari project:

```python
elif args.command == "check":
    checks = _schematic_checks(project, run)
    if args.scope == "spec":
        checks = [next(c for c in checks if c.id == "SPECIFICATION")]
    elif args.scope == "connectivity":
        checks = [next(c for c in checks if c.id == "CONNECTIVITY")]
```

Pakai seleksi berdasarkan `check.id`, bukan index list. Index rapuh terhadap
perubahan urutan.

#### 3. Persist dengan profile valid

```python
return _persist(project, run, checks, args.format, project.profile, ...)
```

### Test

1. `main(["check", "schematic", fixture])` tidak exit 4.
2. `main(["check", "spec", fixture])` tidak exit 4.
3. `main(["check", "connectivity", fixture])` tidak exit 4.
4. `check spec` menghasilkan tepat satu check dengan id `SPECIFICATION`.
5. `check connectivity` menghasilkan tepat satu check dengan id `CONNECTIVITY`.
6. Report yang ditulis memuat `profile` valid.
7. Exit code sesuai status check yang dipilih.

### Acceptance

- Ketiga scope `check` berfungsi.
- Report profile selalu `schematic` atau `layout`.
- Seleksi check berdasarkan id, bukan index.

### Commit

```text
fix: separate check scope from report profile
```

---

## Task 5 - Klasifikasi dari Byte Terverifikasi

### Menyelesaikan

- High 5: klasifikasi membaca stdout, bukan artifact yang di-hash.

### Masalah Persis

`src/pcb_agent/diode.py:451` me-rehash `outcome.result_path`.

`src/pcb_agent/diode.py:356` memutuskan status dari `outcome.process.stdout`.

Byte yang diverifikasi dan byte yang menentukan status bukan objek yang sama. Di
Windows sebelum Task 2 keduanya bahkan tidak byte-identical. `result_sha256` di
report tidak meng-attest input yang menghasilkan status.

Ini memutus rantai atestasi. Auditor yang memverifikasi hash tidak membuktikan
apa pun tentang keputusan yang diambil.

### Perubahan

#### 1. Verifikasi mengembalikan bytes

```python
def _verify_retained_artifact(
    project_root: Path,
    relative_path: str,
    expected_sha256: str,
) -> bytes:
```

Alur:

1. Resolve dalam workspace, tolak escape.
2. Tolak symlink, wajib regular file.
3. Validasi format digest.
4. Baca bytes.
5. Hitung digest, bandingkan.
6. Return bytes.

#### 2. Klasifikasi menerima bytes

```python
def _classify_generated_check(
    result_bytes: bytes,
    process: ProcessResult,
    bench_name: str,
    check_name: str,
) -> CheckStatus:
```

Parse `json.loads(result_bytes.decode("utf-8"))`. Jangan pakai `process.stdout`.

`process` tetap diperlukan untuk `returncode`, `timed_out`, dan `stderr`.

#### 3. Derive digest dari byte yang sama

`result_sha256` harus dihitung dari bytes yang di-write dan dibaca kembali,
bukan dari `result.stdout` in-memory. Setelah Task 2 keduanya identik, tetapi
menghitung dari retained bytes membuat invariant eksplisit.

#### 4. Truncation check

`proc.output_truncated` tetap diperiksa sebelum parse, karena artifact yang
truncated adalah evidence tidak lengkap.

### Test

1. Retained result dimutasi setelah `GeneratedTestResult` dibuat: `BLOCKED`.
2. Retained result dihapus: `BLOCKED`.
3. Retained result diganti symlink: `BLOCKED`.
4. Retained result di luar project root: `BLOCKED`.
5. `stdout` berbeda dari retained file: status berasal dari file, bukan stdout.
6. Digest format invalid: `BLOCKED`.
7. Retained result valid dan konsisten: `PASS`.

Test nomor 5 adalah inti task ini. Buat stdout memuat payload PASS dan retained
file memuat payload FAIL, lalu pastikan hasilnya `FAIL`.

### Acceptance

- Status berasal dari byte yang di-hash.
- `result_sha256` meng-attest input keputusan.
- Divergensi stdout versus file tidak dapat memalsukan status.

### Commit

```text
fix: classify from verified evidence bytes
```

---

## Task 6 - Hapus Blok Tak Terjangkau

### Menyelesaikan

- Medium 1: 40 baris mati memanggil nama tak terdefinisi.

### Masalah Persis

`src/pcb_agent/diode.py:388-427`. Kedua cabang `if proc.returncode == 0:` dan
`else:` di line 378-387 melakukan `return`, sehingga seluruh blok setelahnya
tidak terjangkau.

Line 419 memanggil `_payload_has_failure`, yang tidak ada di `src/`. Nama itu
hanya muncul di `REVIEW_REMEDIATION_PLAN_V3.md:99`.

Pyright tidak menandainya karena unreachable. Refactor yang menghapus satu
`return` akan mengubahnya menjadi `NameError` di dalam classifier, yang tidak
ditangkap `generated_check` dan menjadi crash tak tertangani.

### Perubahan

1. Hapus line 388-427 sepenuhnya.
2. Konfirmasi tidak ada referensi tersisa:

   ```powershell
   findstr /S /N "_payload_has_failure" src tests
   ```

   Harus kosong.

3. Pastikan `_classify_generated_check` berakhir tepat setelah cabang
   `returncode`.

### Test

1. Test klasifikasi existing tetap lolos.
2. `findstr` untuk `_payload_has_failure` kosong.
3. Tambahkan test yang memanggil classifier dengan semua kombinasi
   `returncode` nol dan non-nol untuk memastikan tidak ada jalur jatuh ke akhir
   fungsi tanpa return.

### Acceptance

- Tidak ada dead code di classifier.
- Tidak ada referensi ke nama tak terdefinisi.
- Semua jalur classifier mengembalikan `CheckStatus`.

### Commit

```text
refactor: remove unreachable classifier branch
```

---

## Task 7 - Prerequisite Gagal Menjadi BLOCKED

### Menyelesaikan

- Medium 5: build gagal dilaporkan `FAIL` untuk check yang tidak pernah berjalan.

### Masalah Persis

`src/pcb_agent/cli.py:245-250`: ketika `DIODE_BUILD` gagal, `CONNECTIVITY` dan
`SPECIFICATION` mewarisi `FAIL`.

`src/pcb_agent/cli.py:177-178` dan `:210-211`: ketika `ZENER_TEST` gagal,
generated check mewarisi statusnya.

Tidak ada evidence connectivity atau specification yang dikumpulkan. Klasifikasi
benar untuk situasi tidak-dapat-diverifikasi-karena-prasyarat-gagal adalah
`BLOCKED`.

Cabang layout di `cli.py:273-276` justru sudah memakai `BLOCKED` untuk situasi
identik. Jadi ini inkonsistensi internal, bukan pilihan desain.

`tests/test_integration.py:68-71` mengunci semantik yang salah.

### Prinsip

Distingsi ini adalah inti kontrak status agent:

- `FAIL` berarti gate berjalan dan menemukan mismatch nyata.
- `BLOCKED` berarti gate tidak dapat berjalan atau evidence tidak layak dipercaya.

Mewarisi `FAIL` dari prasyarat membuat "tidak diperiksa" terlihat seperti "sudah
diperiksa dan salah".

### Perubahan

#### 1. Build gagal

```python
dependent_status = (
    CheckStatus.BLOCKED
    if checks[-1].status in {CheckStatus.FAIL, CheckStatus.BLOCKED}
    else checks[-1].status
)
checks.extend([
    _check("ZENER_TEST", dependent_status, "Diode build did not pass"),
    _check("CONNECTIVITY", dependent_status, "Diode build did not pass"),
    _check("SPECIFICATION", dependent_status, "Diode build did not pass"),
])
```

`ZENER_TEST` juga `BLOCKED`, karena test tidak dijalankan.

#### 2. Generated check dengan ZENER_TEST gagal

```python
def _connectivity_check(project, test, run):
    if test.status != CheckStatus.PASS:
        return _check(
            "CONNECTIVITY",
            CheckStatus.BLOCKED,
            "locked Zener TestBench did not pass; connectivity was not verified",
        )
```

Sama untuk `_specification_check`.

#### 3. Verifikasi agregasi

`aggregate_status` memberi prioritas `BLOCKED` di atas `FAIL`. Setelah perubahan
ini, build gagal menghasilkan overall `BLOCKED` exit 2, bukan `FAIL` exit 1.

Ini perubahan perilaku yang harus disengaja dan didokumentasikan. Pertimbangkan:
apakah build gagal seharusnya exit 1 karena desain memang salah, atau exit 2
karena gate lain tidak dapat dievaluasi?

Rekomendasi: `DIODE_BUILD` tetap `FAIL` karena compiler benar-benar menolak
source. Gate dependen menjadi `BLOCKED`. Overall menjadi `BLOCKED` exit 2 karena
ada gate required yang tidak dapat dievaluasi. Ini konsisten dengan precedence
di `ARCHITECTURE_PROPOSAL.md`.

#### 4. Update test

`tests/test_integration.py:68-71` harus berubah:

```python
self.assertEqual(statuses.get("DIODE_BUILD"), CheckStatus.FAIL)
self.assertEqual(statuses.get("ZENER_TEST"), CheckStatus.BLOCKED)
self.assertEqual(statuses.get("CONNECTIVITY"), CheckStatus.BLOCKED)
self.assertEqual(statuses.get("SPECIFICATION"), CheckStatus.BLOCKED)
```

### Test

1. Build gagal: `DIODE_BUILD` FAIL, tiga gate dependen BLOCKED.
2. Build gagal: overall status BLOCKED, exit 2.
3. `ZENER_TEST` gagal: generated check BLOCKED dengan pesan menyebut TestBench.
4. `ZENER_TEST` BLOCKED: generated check BLOCKED.
5. Semua prasyarat PASS: generated check dievaluasi normal.
6. Pesan check menjelaskan gate mana yang gagal.

### Acceptance

- Tidak ada gate yang melaporkan `FAIL` tanpa mengumpulkan evidence.
- Semantik konsisten dengan cabang layout.
- Perubahan exit code terdokumentasi.

### Commit

```text
fix: block dependent gates on failed prerequisite
```

---

## Task 8 - Tutup Sisa Celah Fail-Closed

### Menyelesaikan

- Medium 3: field `rules` tidak divalidasi.
- Medium 4: `collect_used_keywords` hanya satu tingkat.
- Medium 7: tampering di bawah `reports/` tidak terlihat.

### 8.1 Validasi `rules`

#### Masalah

`src/pcb_agent/generated_testbench.py:30` mendefinisikan
`_CONNECTIVITY_FIELDS["rules"]`, dan line 136 menghitung `supported`. Keduanya
tidak pernah dipakai untuk `rules`.

`nets` dan `components` punya penolakan unexpected-field di line 142 dan 175.
`rules` tidak. Key rule tak dikenal diabaikan diam-diam.

Saat ini tertutup hanya oleh `additionalProperties: false` di
`schemas/connectivity.schema.json`. Klaim generator punya validasi fail-closed
independen tidak benar.

#### Perubahan

```python
unexpected = set(rules) - supported["rules"]
if unexpected:
    raise GeneratorError(
        f"rules declares unsupported fields: {sorted(unexpected)}"
    )
```

Letakkan di `_validate_connectivity_shape`, sejajar dengan validasi `nets` dan
`components`.

#### Test

1. `rules` dengan key tak dikenal menghasilkan `GeneratorError`.
2. `rules` dengan hanya `forbid_unlisted_members` diterima.
3. `rules` dengan hanya `required_power_nets` diterima.
4. `rules` kosong diterima.

### 8.2 Perbaiki `collect_used_keywords`

#### Masalah

`src/pcb_agent/jsonschema.py:346-363`. `walk` hanya recurse untuk key dalam
`{"$defs","properties","patternProperties","items","additionalProperties"}`.
Anak dari `properties` adalah nama properti, yang tidak ada dalam set itu.
Subschema per-properti tidak pernah dikunjungi.

Hasil nyata untuk `connectivity.schema.json`:

```text
['additionalProperties', 'properties', 'required', 'type']
```

Hilang: `const`, `pattern`, `minItems`, `minLength`, `uniqueItems`, `enum`.

`used.update(node)` juga menelan nama properti sebagai keyword.

Test `test_all_used_keywords_are_supported` hanya memeriksa set tidak kosong,
dan fungsi sudah memfilter ke `_SUPPORTED`. Test tidak mungkin gagal.

#### Perubahan

Tulis ulang dengan struktur benar:

```python
def collect_used_keywords(schema: Any) -> set[str]:
    used: set[str] = set()

    def walk(node: Any) -> None:
        if isinstance(node, bool) or not isinstance(node, dict):
            return
        used.update(node.keys())
        for container in ("$defs", "properties", "patternProperties"):
            value = node.get(container)
            if isinstance(value, dict):
                for sub in value.values():
                    walk(sub)
        for direct in ("items", "additionalProperties"):
            if direct in node:
                walk(node[direct])

    walk(schema)
    return used
```

Jangan filter ke `_SUPPORTED` di dalam fungsi. Test yang harus membandingkan.

#### Test

```python
for name in ALL_SCHEMAS:
    used = collect_used_keywords(load_schema(name))
    unsupported = used - _SUPPORTED
    self.assertEqual(unsupported, set(), msg=f"{name} uses {sorted(unsupported)}")
```

Tambahkan test negatif: schema sintetis dengan keyword tak dikenal di dalam
subschema `properties` harus terdeteksi.

Perhatikan: nama properti akan ikut terkumpul. Karena itu test harus memakai
schema repo yang nama propertinya tidak bertabrakan dengan keyword, atau
fungsi harus membedakan posisi keyword versus nama properti. Pendekatan kedua
lebih benar tetapi lebih rumit. Pilih satu dan dokumentasikan.

### 8.3 Reports Tampering

#### Masalah

`src/pcb_agent/cli.py:291-292` dan `:303`: `_workspace_hashes` dan
`_snapshot_paths` mengecualikan seluruh `reports/`. Backend dapat menulis ulang
`verify-report.json` dan raw evidence tanpa muncul di `changed`.

`config/policies.toml` deny pattern `reports/raw/**` tidak pernah cocok dengan
path nyata `reports/<run-id>/raw/...`.

Containment bertahan hanya secara insidental, karena allow list terbatas pada
`src/**/*.zen` dan `layout/**/*.kicad_pcb`.

#### Perubahan

1. Ubah deny pattern:

   ```toml
   deny = [
     "SPEC.json",
     "ACCEPTANCE.json",
     "expected-connectivity.json",
     "tests/**",
     "config/**",
     "schemas/**",
     "reports/**",
   ]
   ```

2. Sertakan `reports/` dalam hash sweep. Karena harness sendiri menulis ke
   `reports/` selama run, perlu pemisahan:
   - Hash `reports/` sebelum backend dijalankan.
   - Hash lagi setelah backend selesai.
   - Perubahan apa pun di `reports/` oleh backend adalah policy violation.
   - Write oleh harness terjadi setelah backend selesai, jadi tidak bentrok.

3. Alternatif lebih sederhana: buat run directory read-only selama backend
   berjalan, atau tulis evidence hanya setelah backend selesai. Pilih yang
   sesuai dengan urutan eksekusi nyata.

#### Test

1. Backend memodifikasi `reports/<run>/verify-report.json`: policy violation.
2. Backend memodifikasi `reports/<run>/raw/*.json`: policy violation.
3. Backend membuat file baru di `reports/`: policy violation.
4. Deny pattern `reports/**` cocok dengan `reports/run-1/raw/data.json`.
5. Harness sendiri tetap dapat menulis report setelah backend selesai.

### Acceptance

- `rules` divalidasi independen dari schema.
- `collect_used_keywords` menemukan seluruh keyword bersarang.
- Test keyword dapat gagal ketika schema memakai keyword tak didukung.
- Tampering di `reports/` terdeteksi.
- Deny pattern cocok dengan path nyata.

### Commit

```text
fix: close remaining fail-closed gaps
```

---

## Task 9 - Test PASS Path dan Pullup Coverage

### Menyelesaikan

- Medium 6: tidak ada test untuk run yang benar-benar hijau.
- Medium 2: `failed_count > 0` bukan diskriminator seperti klaim test.
- Low 8: jalur pull-up belum teruji.

### 9.1 Green Run

#### Masalah

`tests/test_fake_backend.py:131` mengubah `assertEqual(valid, 0)` menjadi
`assertEqual(valid, 2)`.

Fake `pcb` di `tests/helpers.py:109` mengeluarkan `"name": "BlinkyTest.default"`,
sedangkan `fixtures/valid-blinky/ACCEPTANCE.json` menuntut
`BlinkyTest.component_value` dan `BlinkyTest.connectivity`.

`diode.execute:246` raise `pcb test JSON lacks passing acceptance result`,
sehingga `ZENER_TEST` menjadi `BLOCKED` dan run exit 2.

Jalur `PASS` melalui `_persist` dan `EXIT_CODES` tidak terlatih sama sekali.

#### Perubahan

1. Fake `pcb` harus membaca acceptance nyata atau mengeluarkan kedua nama test:

   ```python
   payload = {
       "results": [
           {"test_bench_name": "BlinkyTest", "check_name": "component_value", "status": "PASS"},
           {"test_bench_name": "BlinkyTest", "check_name": "connectivity", "status": "PASS"},
       ],
       "summary": {"total": 2, "passed": 2, "failed": 0, "failures": 0, "errors": 0},
   }
   ```

2. Registrasikan adapter stub dalam test agar generated check dapat PASS.
   Adapter stub hanya untuk test, jangan masuk registry produksi.

3. Restore assertion exit 0.

#### Test

1. Fixture valid dengan fake tool dan adapter stub: exit 0.
2. Report memuat `status: "PASS"`.
3. Report tetap memuat `production_ready: false`.
4. Report tetap memuat `fabrication_approved: false`.
5. Semua gate required PASS.

Poin 3 dan 4 penting. Jalur PASS adalah tempat paling mungkin invariant
keamanan bocor, dan sampai sekarang tidak pernah dieksekusi test.

### 9.2 `failed_count` Discriminator

#### Masalah

`src/pcb_agent/diode.py:385` dan `tests/test_generated_result.py:182-193`.

`_summary_matches_records` sudah memaksa `summary.failed` sama dengan jumlah
record `FAIL`. Jadi pada line 385, record `FAIL` sudah menjamin `failed >= 1`.

Test `test_expected_failure_with_nonzero_exit_but_zero_failed_is_blocked` lolos
karena payload ditolak di reconciliation line 364, bukan di 385. Aturan yang
dinamai belum teruji.

#### Perubahan

Pilih satu:

**Opsi A.** Hapus klausa redundan `failed_count > 0`, karena reconciliation sudah
menjaminnya. Tambahkan komentar yang menjelaskan mengapa.

**Opsi B.** Pertahankan sebagai defense-in-depth, dan tulis test yang benar-benar
mencapai line 385: payload dengan summary yang reconcile, satu record `FAIL`,
satu record `PASS`, dan `failed` bernilai benar.

Rekomendasi Opsi A. Kode yang tidak dapat dijangkau oleh test adalah kode yang
tidak dapat dipercaya.

### 9.3 Pullup Coverage

#### Masalah

`tests/test_generated_testbench.py:224-238` bernama
`test_required_pullup_raises_when_unsupported_kind` tetapi meng-assert
`"unverified kind led"`, yang berasal dari `_validate_connectivity_shape:174`,
bukan dari logika pull-up.

Cabang `adapter.pullup_pin_pair is None` di `generated_testbench.py:224-225`,
cabang missing-pin di 235-236, dan assertion topology yang dirender di 242-250
tidak punya test.

#### Perubahan

Tambahkan test yang benar-benar menargetkan logika pull-up:

1. Adapter terdaftar tanpa `pullup_pin_pair`: `GeneratorError` menyebut
   `pullup_pin_pair`.
2. Adapter dengan `pullup_pin_pair` merujuk pin yang tidak ada di `pins`:
   `GeneratorError`.
3. Pull-up valid: generated source memuat assertion untuk kedua pin.
4. Generated source memuat assertion signal net dengan pin pertama.
5. Generated source memuat assertion rail net dengan pin lawan.
6. Generated source tidak bergantung pada urutan iterasi `pins`.
7. Pull-up component tidak ada di `components`: `GeneratorError`.
8. Rail tidak ada di `nets`: `ContractError` dari contract loader.

Poin 6 diuji dengan membuat adapter yang urutan `pins`-nya berbeda dari
`pullup_pin_pair`, lalu memastikan generated source tetap memakai pasangan yang
benar.

### Acceptance

- Ada test yang mencapai exit 0 dan status PASS.
- Invariant keamanan diverifikasi pada jalur PASS.
- Setiap cabang pull-up punya test yang menargetkannya langsung.
- Tidak ada test yang lolos karena alasan berbeda dari namanya.

### Commit

```text
test: cover green run and pullup topology
```

---

## Task 10 - Tidy Evidence Metadata dan Dead Code

### Menyelesaikan

- Low 1: dead code dan parameter tak terpakai.
- Low 2: evidence path absolut untuk check non-generated.
- Low 3: provenance generated check salah label.
- Low 4: `required: []` dan `enum: []` menyimpang dari draft.
- Low 5: `$defs` self-referential memicu `RecursionError`.
- Low 6: regex `patternProperties` dikompilasi ulang per key.

### 10.1 Dead Code

| Lokasi | Masalah | Tindakan |
|---|---|---|
| `diode.py:345` | `check_id` tak terpakai | Hapus parameter |
| `diode.py:273-274` | `bench_name`, `case_name` tak terpakai | Hapus atau pakai untuk validasi |
| `diode.py:53-54` | `GeneratedAssertionFailure` tak dipakai | Hapus atau pakai di Task 5 |
| `diode.py:180-181` | Guard unreachable | Hapus, sudah dijamin `_validate_test_payload` |
| `diode.py:211` | Assign ke diri sendiri | Hapus baris |
| `generated_testbench.py:111-117` | `_check_connector_ref` tak dipanggil | Hapus |
| `generated_testbench.py:374,460` | `unsupported_constraint_seen` tak dibaca | Hapus |
| `generated_testbench.py:106-107` | Guard unreachable | Hapus |
| `contracts.py:52` | Import duplikat | Hapus import lokal |

Setelah setiap penghapusan jalankan pytest. Guard yang tampak unreachable bisa
ternyata dipakai oleh jalur yang tidak diuji.

### 10.2 Relative Path untuk Semua Evidence

#### Masalah

`src/pcb_agent/cli.py:160` dan `src/pcb_agent/kicad.py:64` menyimpan
`str(evidence_path)`, menghasilkan `C:\Users\<user>\...` di `verify-report.json`.

Inkonsisten dengan jaminan relative path yang Task 4 V3 tambahkan untuk
generated evidence, dan membocorkan home directory operator.

#### Perubahan

1. Pindahkan `_relative_evidence_path` ke lokasi yang dapat diimpor kedua modul.
   Pertimbangkan `paths.py` karena itu modul path-safety.
2. Pakai di `cli.py:160` dan `kicad.py:64`.
3. Tolak path yang escape project root.

#### Test

1. Report tidak memuat prefix absolut.
2. Report tidak memuat nama user.
3. Semua evidence path relatif POSIX.
4. Path di luar project root ditolak.

### 10.3 Provenance

`src/pcb_agent/diode.py:487` memakai `"harness"`. Status berasal dari output
`pcb test`, dan schema mengizinkan `"tool"`.

Ubah ke `"tool"`. Ini bukan kosmetik: harness ini bertujuan memisahkan
provenance, jadi salah label merusak tujuannya sendiri.

Pertimbangkan: derivasi harness dari output tool bisa dianggap `"harness"`.
Kalau begitu, dokumentasikan alasannya. Yang tidak boleh adalah label tanpa
alasan.

### 10.4 Deviasi Schema Terdokumentasi

`src/pcb_agent/jsonschema.py:153`, `:231`, `:127`, `:198` menolak `required: []`
dan `enum: []`, yang valid menurut draft 2020-12.

Pilih satu:

- Izinkan array kosong, pertahankan validasi string dan uniqueness.
- Pertahankan penolakan, dan dokumentasikan sebagai deviasi subset yang
  disengaja di docstring modul.

Rekomendasi: dokumentasikan. Schema repo tidak memakai array kosong, dan
penolakan menangkap schema yang kemungkinan salah tulis.

### 10.5 Recursion Guard

`src/pcb_agent/jsonschema.py:186`. Schema dengan `$defs` yang `$ref` ke dirinya
memicu `RecursionError`, yang bukan `ValueError` sehingga lolos dari penanganan
di `contracts.py:93` dan `cli.py:540`, muncul sebagai traceback tak tertangani.

Tambahkan depth guard atau set ref yang sedang diproses:

```python
def _validate(instance, schema, root, path, _refs=frozenset()):
    ...
    if ref in _refs:
        raise SchemaError(f"{path}: circular $ref {ref}")
```

Test dengan schema sintetis yang self-referential.

### 10.6 Regex Caching

`src/pcb_agent/jsonschema.py:258-263`. `_re.compile` di dalam loop bersarang.
`re` punya cache internal, jadi correctness tidak terpengaruh.

Pindahkan compile ke luar loop untuk kejelasan. Prioritas rendah.

### Acceptance

- Tidak ada dead code atau parameter tak terpakai.
- Semua evidence path relatif.
- Provenance sesuai sumber atau terdokumentasi.
- Deviasi schema terdokumentasi.
- Circular `$ref` menghasilkan `SchemaError`.

### Commit

```text
refactor: tidy evidence metadata and dead code
```

---

## Task 11 - Verifikasi Final, Docs, dan PR

### Verifikasi Lokal

```powershell
python -m pytest tests/ -v
python -m pyright
git diff --check master...HEAD
git status --short
```

Expected:

```text
pytest:  semua lolos, jumlah skip hanya untuk kapabilitas eksternal nyata
pyright: 0 errors, 0 warnings, 0 informations
git diff --check: tanpa output
git status: bersih
```

### Verifikasi CLI

```powershell
python pcb-agent doctor --project fixtures/valid-blinky --format json
python pcb-agent check schematic fixtures/valid-blinky
python pcb-agent check spec fixtures/valid-blinky
python pcb-agent check connectivity fixtures/valid-blinky
python pcb-agent doctor --project fixtures/path-traversal
python pcb-agent init demo-board --into <TEMP>
```

Expected:

| Command | Exit |
|---|---|
| `doctor` valid | 0 |
| `check` ketiga scope | bukan 4 |
| `doctor` path-traversal | 3 |
| `init` nama valid | 0 |

### Verifikasi CI

```powershell
gh pr checks 1
```

Seluruh matrix Ubuntu dan Windows serta typecheck harus PASS.

### Documentation

#### `README.md`

Tambahkan atau perbarui:

1. `mpn` tidak didukung dan selalu `BLOCKED`.
2. Requirement `type: "connectivity"` hanya menerima constraint `members`.
3. Setiap cabang constraint wajib menghasilkan assertion; jumlah diverifikasi.
4. Adapter di-key berdasarkan component kind.
5. `pcbc_version` berasal dari probe tool nyata; probe gagal menjadi `BLOCKED`.
6. Prasyarat gagal membuat gate dependen `BLOCKED`, bukan `FAIL`.
7. Semua evidence path relatif terhadap project root.
8. Klasifikasi status berasal dari byte yang di-hash.

#### `docs/spike-diode-net-naming.md`

Tambahkan ke prosedur unblocking:

1. Catat bentuk output `pcb --version` yang sebenarnya, karena parser harus
   ketat.
2. Catat accessor `mpn` bila ada; bila tidak ada, nyatakan eksplisit.
3. Tambahkan `kind` ke contoh registrasi adapter.
4. Tegaskan `pullup_pin_pair` harus dari observasi, bukan urutan `pins`.

#### `AGENT_PROTOCOL.md`

Bila kontrak status berubah karena Task 7, perbarui tabel status dan exit.

### Review Ulang

Jalankan strict review baru terhadap `master...HEAD` dengan fokus:

1. Setiap cabang constraint menghasilkan assertion.
2. Hash evidence konsisten lintas platform.
3. Registry dapat diisi lewat API publik.
4. Version gate bermakna.
5. Klasifikasi dari byte terverifikasi.
6. `FAIL` versus `BLOCKED` konsisten.
7. Tidak ada dead code baru.

### Commit

```text
docs: finalize generated verification contract
```

---

## Traceability

| Finding | Severity | Task |
|---|---|---|
| `mpn` tidak di-assert | Critical | 1 |
| Constraint connectivity dibuang | Critical | 1 |
| CRLF hash mismatch | High | 2 |
| Registry key salah | High | 3 |
| `pcbc_version` vacuous | High | 3 |
| `check spec`/`connectivity` exit 4 | High | 4 |
| Klasifikasi bukan dari byte ter-hash | High | 5 |
| Dead code `_payload_has_failure` | Medium | 6 |
| `failed_count` discriminator | Medium | 9 |
| `rules` tidak divalidasi | Medium | 8 |
| `collect_used_keywords` satu tingkat | Medium | 8 |
| Prerequisite gagal jadi FAIL | Medium | 7 |
| Tidak ada test green run | Medium | 9 |
| Reports tampering | Medium | 8 |
| Dead code lain | Low | 10 |
| Path absolut non-generated | Low | 10 |
| Provenance salah | Low | 10 |
| `required: []` deviasi | Low | 10 |
| Circular `$ref` | Low | 10 |
| Regex recompile | Low | 10 |
| Trailing whitespace | Low | 0 |
| Pullup untested | Low | 9 |

## Definition of Done

1. Setiap cabang constraint menghasilkan assertion atau `GeneratorError`.
2. Jumlah assertion diverifikasi terhadap jumlah constraint.
3. `mpn` tidak dapat menghasilkan `PASS`.
4. Requirement connectivity menolak constraint non-`members`.
5. Digest evidence identik lintas platform.
6. Registry dapat diisi lewat `build_adapter_registry` dan resolve berdasarkan
   kind.
7. `pcbc_version` berasal dari probe nyata; gagal probe menjadi `BLOCKED`.
8. Ketiga scope `check` berfungsi.
9. Status berasal dari byte yang di-hash dan di-attest.
10. Tidak ada dead code atau nama tak terdefinisi.
11. Prasyarat gagal menghasilkan `BLOCKED` untuk gate dependen.
12. `rules` divalidasi independen.
13. `collect_used_keywords` dapat gagal ketika schema melampaui subset.
14. Tampering `reports/` terdeteksi.
15. Ada test yang mencapai exit 0 dengan invariant keamanan diverifikasi.
16. Setiap cabang pull-up punya test langsung.
17. Semua evidence path relatif.
18. pytest lolos.
19. pyright nol error.
20. `git diff --check` bersih.
21. CI seluruhnya PASS.
22. Registry produksi tetap kosong sampai ada captured Diode evidence.
23. `production_ready` dan `fabrication_approved` selalu `false`.
