# Implementation Plan

Target: menutup gap antara `ARCHITECTURE_PROPOSAL.md` dan implementasi nyata.

Baseline saat plan ini dibuat:

- Commit: `173dd90`
- Test: `29 passed, 3 skipped, 11 subtests passed`
- Python: 3.11+ , stdlib only (tidak ada dependency pihak ketiga)

## Aturan wajib untuk pengerjaan

1. Jangan tambah dependency pihak ketiga. `pyproject.toml` harus tetap
   `dependencies = []`. README menjanjikan "Core has no third-party Python
   dependency".
2. Jangan ubah file berikut untuk membuat test lolos: `fixtures/*/SPEC.json`,
   `fixtures/*/ACCEPTANCE.json`, `fixtures/*/expected-connectivity.json`,
   `fixtures/*/tests/**`, `schemas/**`.
3. Setelah setiap task, jalankan dari root repo:
   ```
   python -m pytest tests/ -q
   ```
   Semua task selesai hanya jika test lolos.
4. Satu task = satu commit. Format Conventional Commits.
5. Jangan tambah komentar kode kecuali diminta eksplisit di task.
6. Kerjakan task berurutan. Task N mengandalkan task sebelumnya.

## Ringkasan task

| # | Task | Ukuran | Tergantung |
|---|---|---|---|
| 1 | Fix bug `state.py::_read_file` | Small | - |
| 2 | Fix label check `layout` | Small | - |
| 3 | Bersihkan import mati | Small | - |
| 4 | Konfigurasi pytest + pyright | Small | - |
| 5 | CI GitHub Actions | Small | 4 |
| 6 | Validator JSON Schema stdlib | Medium | - |
| 7 | Sambungkan schema ke `contracts.py` | Medium | 6 |
| 8 | Load `config/policies.toml` | Medium | - |
| 9 | Check CONNECTIVITY nyata (fase A) | Large | 7 |
| 10 | Check SPECIFICATION nyata (fase A) | Medium | 9 |
| 11 | Command `init` | Medium | 8 |
| 12 | Fixture `acceptance-tampered` | Small | 9 |
| 13 | Fixture `path-traversal` | Small | 8 |
| 14 | Spike net-naming Diode (fase B) | Research | 9 |

---

## Task 1 — Fix bug `state.py::_read_file`

### Masalah

`src/pcb_agent/state.py:53-65` memanggil `resolve_workspace_path` dan
`require_regular_file` tanpa mengimpornya. Terbukti dengan:

```
python -c "import sys; sys.path.insert(0,'src'); from pcb_agent.state import _read_file; from pathlib import Path; _read_file(Path('fixtures/valid-blinky'),'SPEC.json')"
```

Hasil: `NameError: name 'resolve_workspace_path' is not defined`

Fungsi ini saat ini tidak dipanggil dari mana pun (dead code), tetapi tetap
ranjau bagi pengerjaan berikutnya.

### Keputusan

Hapus fungsi. Tanggung jawabnya sudah dipegang
`src/pcb_agent/contracts.py::_read_required` yang benar dan sudah diuji.

### Langkah

1. Buka `src/pcb_agent/state.py`.
2. Hapus seluruh blok baris 53-65 (definisi `def _read_file` sampai
   `return data`), termasuk dua baris kosong yang mengikutinya.
3. Pastikan tidak ada pemanggil. Verifikasi:
   ```
   findstr /S /N "_read_file" src\ tests\
   ```
   Harus tidak ada hasil.

### Kriteria selesai

- `findstr /S /N "_read_file" src\ tests\` kosong.
- `python -m pytest tests/ -q` lolos.

### Commit

```
fix: drop broken unused _read_file helper
```

---

## Task 2 — Fix label check pada command `layout`

### Masalah

`src/pcb_agent/cli.py:352-353`:

```python
elif args.command == "layout":
    checks = [_diode_command(project, "layout-command", "LAYOUT_SYNC")]
```

`layout-command` adalah command generate (`pcb layout ... --no-open -f json`),
bukan sync. Di `_verify` (`cli.py:188-193`) pemetaannya benar:

- `layout-command` -> `LAYOUT_GENERATE`
- `layout-check-command` -> `LAYOUT_SYNC`

Jadi `pcb-agent layout` melaporkan hasil generate dengan ID `LAYOUT_SYNC`.
Laporan jadi salah nama.

### Keputusan

Command `layout` menjalankan generate lalu sync, sama seperti `_verify`, supaya
konsisten. Sync hanya jalan jika generate PASS.

### Langkah

1. Buka `src/pcb_agent/cli.py`.
2. Ganti blok:
   ```python
   elif args.command == "layout":
       checks = [_diode_command(project, "layout-command", "LAYOUT_SYNC")]
   ```
   menjadi:
   ```python
   elif args.command == "layout":
       generation = _diode_command(project, "layout-command", "LAYOUT_GENERATE")
       checks = [generation]
       if generation.status == CheckStatus.PASS:
           checks.append(_diode_command(project, "layout-check-command", "LAYOUT_SYNC"))
       else:
           checks.append(_check("LAYOUT_SYNC", CheckStatus.BLOCKED,
                                "layout generation did not pass"))
   ```

### Kriteria selesai

- `python -m pytest tests/ -q` lolos.
- Tidak ada lagi kemunculan `"layout-command", "LAYOUT_SYNC"` di repo:
  ```
  findstr /S /N "layout-command\", \"LAYOUT_SYNC" src\
  ```
  Harus kosong.

### Commit

```
fix: label layout generate and sync checks separately
```

---

## Task 3 — Bersihkan import mati

### Masalah

Dua tempat:

1. `src/pcb_agent/state.py:5` — `import hashlib`. Setelah Task 1, tidak ada
   pemakaian. Verifikasi: `findstr /N "hashlib" src\pcb_agent\state.py` hanya
   memberi baris import.
2. `src/pcb_agent/backends/command.py` — `run_process` diimpor di baris 9
   (top-level) lalu diimpor ulang di dalam `probe()` baris 31.

### Langkah

1. `src/pcb_agent/state.py`: hapus baris `import hashlib`.
2. `src/pcb_agent/backends/command.py`: hapus dua baris di dalam `probe()`:
   ```python
   from ..process import run_process

   ```
   Sisakan hanya `return run_process(workspace, [self.argv[0], "--help"], timeout=30)`.
   Import top-level di baris 9 sudah menyediakannya.
3. Cek sisa import mati di seluruh `src/`. Karena tidak ada linter terpasang,
   lakukan manual: untuk setiap nama pada baris `import X` dan
   `from Y import X`, hitung kemunculan `X` di file yang sama:
   ```
   findstr /N "os\." src\pcb_agent\state.py
   findstr /N "subprocess" src\pcb_agent\state.py
   findstr /N "Any\|Mapping" src\pcb_agent\state.py
   ```
   Hapus yang hanya muncul di baris import. Jangan hapus yang dipakai di
   anotasi tipe.

### Kriteria selesai

- `python -m pytest tests/ -q` lolos.
- `python -c "import sys; sys.path.insert(0,'src'); import pcb_agent.cli"` sukses
  tanpa error.

### Commit

```
chore: remove dead imports
```

---

## Task 4 — Konfigurasi pytest + pyright

### Masalah

`pyproject.toml` hanya punya `[tool.pyright]`. Tidak ada konfigurasi pytest,
sehingga `tests/helpers.py` harus menyisipkan `src/` ke `sys.path` secara manual.
Tidak ada linter.

### Langkah

1. Buka `pyproject.toml`.
2. Tambahkan di akhir file:
   ```toml
   [tool.pytest.ini_options]
   testpaths = ["tests"]
   pythonpath = ["src"]
   addopts = "-q"

   [tool.pyright]
   pythonVersion = "3.11"
   include = ["src"]
   typeCheckingMode = "standard"
   reportUnusedImport = "error"
   ```
   Hapus blok `[tool.pyright]` lama di baris 11-13 supaya tidak duplikat.
3. Jangan hapus penyisipan `sys.path` di `tests/helpers.py`. Itu tetap
   diperlukan agar test bisa dijalankan langsung tanpa pytest.

### Kriteria selesai

- `python -m pytest` (tanpa argumen) menemukan dan menjalankan test.
- `python -m pytest tests/ -q` lolos.

### Catatan

`pythonpath` di pytest butuh pytest >= 7.0. Jika `python -m pytest --version`
melaporkan versi lebih rendah, hapus baris `pythonpath` dan biarkan
`tests/helpers.py` yang menangani.

### Commit

```
chore: configure pytest and pyright
```

---

## Task 5 — CI GitHub Actions

### Masalah

Tidak ada `.github/`. `ARCHITECTURE_PROPOSAL.md` §16 menjanjikan matriks
cross-platform, nol otomasi.

### Langkah

1. Buat direktori `.github/workflows/`.
2. Buat file `.github/workflows/ci.yml` dengan isi tepat:

```yaml
name: ci

on:
  push:
    branches: ["**"]
  pull_request:

jobs:
  test:
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, windows-latest]
        python: ["3.11", "3.13"]
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python }}
      - name: Install pytest
        run: python -m pip install --upgrade pytest
      - name: Run tests
        run: python -m pytest tests/ -q

  typecheck:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Install pyright
        run: python -m pip install --upgrade pyright
      - name: Run pyright
        run: python -m pyright
```

3. Diode dan KiCad tidak dipasang di CI. Test yang butuh keduanya sudah
   di-skip lewat mekanisme yang ada di `tests/test_fake_backend.py`. Jangan
   tambah instalasi Diode/KiCad di CI pada task ini.

### Kriteria selesai

- File `.github/workflows/ci.yml` ada dan YAML-nya valid:
  ```
  python -c "import sys; sys.exit(0)"
  ```
  (validasi nyata terjadi saat push; cukup pastikan indentasi 2 spasi konsisten)
- `python -m pytest tests/ -q` masih lolos lokal.

### Commit

```
ci: add test and typecheck workflow
```

---

## Task 6 — Validator JSON Schema stdlib

### Masalah

`schemas/connectivity.schema.json`, `schemas/specification.schema.json`, dan
`schemas/verification-report.schema.json` ditulis lengkap (draft 2020-12) tapi
tidak dipakai satu baris pun:

```
findstr /S /I "schemas" src\pcb_agent\*.py
```
Hasil kosong.

Sementara `contracts.py` punya ~30 check manual yang menduplikasi isi schema.
Sumber kebenaran ganda.

### Batasan

Tidak boleh pakai paket `jsonschema`. Harus stdlib. Jadi tulis validator subset
yang hanya mendukung keyword yang benar-benar dipakai oleh tiga schema di repo.

### Keyword yang wajib didukung

Baca ketiga file schema dan pastikan validator menangani keyword ini saja:

- `type` (`object`, `array`, `string`, `integer`, `number`, `boolean`)
- `properties`
- `required`
- `additionalProperties` (bentuk boolean dan bentuk subschema)
- `patternProperties`
- `items`
- `enum`
- `const`
- `pattern`
- `minLength`
- `maxLength`
- `minItems`
- `uniqueItems`
- `$defs` dan `$ref` (hanya bentuk lokal `#/$defs/NAMA`)

Jika saat implementasi ditemukan keyword lain di file schema, dukung juga.
Jangan diam-diam mengabaikan keyword yang tidak dikenal.

### Langkah

1. Buat file baru `src/pcb_agent/jsonschema.py`.
2. Isi dengan struktur ini:

```python
"""Minimal JSON Schema subset validator, standard library only."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


SCHEMA_ROOT = Path(__file__).resolve().parent.parent.parent / "schemas"

_TYPES = {
    "object": dict,
    "array": list,
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
}

_SUPPORTED = frozenset({
    "$schema", "$id", "$defs", "$ref", "title", "description",
    "type", "properties", "required", "additionalProperties",
    "patternProperties", "items", "enum", "const", "pattern",
    "minLength", "maxLength", "minItems", "uniqueItems",
})


class SchemaError(ValueError):
    pass


def load_schema(name: str) -> dict[str, Any]:
    path = (SCHEMA_ROOT / name).resolve()
    if SCHEMA_ROOT.resolve() not in path.parents:
        raise SchemaError(f"schema path escapes schemas directory: {name}")
    return json.loads(path.read_text(encoding="utf-8"))


def validate(instance: Any, schema: dict[str, Any], name: str = "") -> None:
    """Raise SchemaError on first violation. Returns None on success."""
    _validate(instance, schema, schema, name or "<root>")


def _validate(instance: Any, schema: Any, root: dict[str, Any], path: str) -> None:
    ...
```

3. Implementasi `_validate` dengan urutan pemeriksaan berikut. Setiap kegagalan
   melempar `SchemaError` dengan pesan yang menyebut `path`.

   a. Jika `schema` adalah `bool`: `True` selalu lolos, `False` selalu gagal.

   b. Tolak keyword tak dikenal:
      ```python
      unknown = set(schema) - _SUPPORTED
      if unknown:
          raise SchemaError(f"{path}: unsupported schema keywords: {sorted(unknown)}")
      ```

   c. `$ref`: hanya bentuk `#/$defs/NAMA`. Resolve dari `root["$defs"][NAMA]`,
      lalu validasi ulang terhadap subschema itu dan hentikan pemrosesan
      keyword lain pada level ini.

   d. `type`: cek `isinstance`. Perhatikan dua jebakan Python:
      - `bool` adalah subclass `int`. Untuk `type: integer` atau
        `type: number`, tolak `bool` secara eksplisit.
      - `type` boleh berupa list. Lolos jika cocok salah satu.

   e. `const`: bandingkan dengan `!=`. Untuk nilai `False`, gunakan
      perbandingan yang juga membedakan tipe, karena `0 == False` di Python:
      ```python
      if "const" in schema:
          expected = schema["const"]
          if instance != expected or type(instance) is not type(expected):
              raise SchemaError(f"{path}: expected const {expected!r}")
      ```
      Ini penting karena `verification-report.schema.json` memakai
      `"const": false` untuk `production_ready` dan `fabrication_approved`.

   f. `enum`: `if instance not in schema["enum"]: raise`.

   g. Untuk string: `pattern` (pakai `re.search`, bukan `re.match`, sesuai
      semantik JSON Schema), `minLength`, `maxLength`.

   h. Untuk object:
      - `required`: setiap nama harus ada sebagai key.
      - `properties`: validasi setiap key yang cocok.
      - `patternProperties`: untuk setiap key instance, jika cocok pola,
        validasi terhadap subschema-nya.
      - `additionalProperties`: key yang tidak tertangani `properties` maupun
        `patternProperties`. Jika bernilai `False`, tolak. Jika subschema,
        validasi.

   i. Untuk array: `items` (validasi setiap elemen), `minItems`,
      `uniqueItems` (bandingkan dengan serialisasi
      `json.dumps(x, sort_keys=True)` karena dict tidak hashable).

4. Buat file test baru `tests/test_jsonschema.py`. Wajib mencakup kasus ini,
   pakai `unittest` seperti file test lain di repo:

   - `load_schema("specification.schema.json")` berhasil dan hasilnya `dict`.
   - Ketiga schema di `schemas/` hanya memakai keyword dalam `_SUPPORTED`.
     Implementasikan dengan menelusuri schema secara rekursif. Test ini
     mencegah schema berkembang melampaui validator tanpa terdeteksi.
   - `validate` menerima `fixtures/valid-blinky/SPEC.json` terhadap
     `specification.schema.json`.
   - `validate` menerima `fixtures/valid-blinky/expected-connectivity.json`
     terhadap `connectivity.schema.json`.
   - `validate` menolak `{"schema_version": "2", ...}` karena `const` gagal.
   - `validate` menolak object yang kehilangan property `required`.
   - `validate` menolak `production_ready: True` terhadap
     `verification-report.schema.json` (`const: false`).
   - `validate` menolak `True` untuk `type: integer` (jebakan bool/int).
   - `validate` menolak array dengan elemen duplikat saat `uniqueItems: true`.
   - `validate` menolak string yang gagal `pattern`.
   - `validate` menolak schema dengan keyword tak dikenal.

### Kriteria selesai

- `python -m pytest tests/ -q` lolos, termasuk `tests/test_jsonschema.py`.
- Ketiga file di `schemas/` lolos test "keyword didukung".
- Tidak ada dependency baru di `pyproject.toml`.

### Commit

```
feat: add stdlib JSON Schema subset validator
```

---

## Task 7 — Sambungkan schema ke `contracts.py`

### Masalah

`contracts.py` memvalidasi manual apa yang sudah dideklarasikan schema.
Setelah Task 6, validasi schema bisa dipakai.

### Keputusan penting

Jangan hapus check manual yang **bukan** ekspresi schema. Schema hanya bisa
memeriksa bentuk satu dokumen. Check berikut adalah aturan lintas-dokumen dan
harus tetap di Python:

- `contracts.py:112-113` — `layout.required` mewajibkan `profile == "layout"`
- `contracts.py:132-143` — setiap acceptance check merujuk requirement ID yang
  ada, dan setiap requirement tercakup
- `contracts.py:139-140` — `expected: "FAIL"` hanya untuk `negative_fixture`
- `contracts.py:144-145` — `project.test` harus di bawah `tests/` dan `.zen`
- `contracts.py:100-104` — `source` dan `test` harus file nyata di workspace
- `contracts.py:82-87` — pengecualian connectivity kosong untuk fixture
  negatif build

Yang boleh dihapus karena murni bentuk dokumen dan sudah dijamin schema:

- `contracts.py:70-71` — root harus object (schema: `type: object`)
- `contracts.py:80-81` — `components` dan `nets` harus object
- `contracts.py:88-90` — setiap component punya `kind` string
- `contracts.py:91-94` — setiap net punya `members` non-kosong berpola `X.Y`
- `contracts.py:114-115` — `production_ready`/`fabrication_approved` false
- `contracts.py:116-117` — `requirements`/`checks` array

Hapus hanya setelah memverifikasi schema benar-benar menjamin hal itu. Buka
file schema dan konfirmasi. Jika schema tidak menjamin, biarkan check Python.

### Masalah yang harus diselesaikan lebih dulu

`ACCEPTANCE.json` tidak punya schema. Yang ada hanya
`specification.schema.json`, `connectivity.schema.json`, dan
`verification-report.schema.json`.

Maka: buat `schemas/acceptance.schema.json` baru. Turunkan bentuknya dari
`fixtures/*/ACCEPTANCE.json` yang ada (keempatnya) plus
`skill/diode-pcb-agent/assets/project-template/ACCEPTANCE.json`. Bentuk yang
harus ditangkap:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "acceptance.schema.json",
  "type": "object",
  "required": ["schema_version", "checks", "production_ready", "fabrication_approved"],
  "additionalProperties": false,
  "properties": {
    "schema_version": {"const": "1"},
    "production_ready": {"const": false},
    "fabrication_approved": {"const": false},
    "checks": {
      "type": "array",
      "minItems": 1,
      "items": {
        "type": "object",
        "required": ["id", "requirement", "kind", "expected"],
        "additionalProperties": false,
        "properties": {
          "id": {"type": "string", "minLength": 1},
          "requirement": {"type": "string", "pattern": "^REQ-[0-9]+$"},
          "kind": {"enum": ["zener_test", "diode_build"]},
          "test": {"type": "string", "minLength": 1},
          "expected": {"enum": ["PASS", "FAIL"]},
          "reason": {"type": "string"}
        }
      }
    }
  }
}
```

Sebelum menulis final, baca kelima file `ACCEPTANCE.json` dan pastikan tidak ada
property lain. Jika ada, tambahkan. `additionalProperties: false` akan membuat
test gagal jika terlewat, jadi kesalahan akan terdeteksi.

### Langkah

1. Buat `schemas/acceptance.schema.json` seperti di atas, disesuaikan dengan
   isi nyata fixture.
2. Buka `src/pcb_agent/contracts.py`. Tambahkan import:
   ```python
   from .jsonschema import SchemaError, load_schema, validate
   ```
3. Tambahkan konstanta setelah `REQUIRED_FILES`:
   ```python
   _SCHEMA_BY_FILE = {
       "SPEC.json": "specification.schema.json",
       "ACCEPTANCE.json": "acceptance.schema.json",
       "expected-connectivity.json": "connectivity.schema.json",
   }
   ```
4. Di `load_project_contract`, setelah blok parsing JSON/TOML (setelah baris 69)
   dan sebelum check manual, tambahkan:
   ```python
   documents = {
       "SPEC.json": specification,
       "ACCEPTANCE.json": acceptance,
       "expected-connectivity.json": connectivity,
   }
   for filename, schema_name in _SCHEMA_BY_FILE.items():
       try:
           validate(documents[filename], load_schema(schema_name), filename)
       except SchemaError as error:
           raise ContractError(f"{filename} violates schema: {error}") from error
   ```
5. Hapus check manual yang sudah dijamin schema (daftar di atas), satu per satu.
   Setelah setiap penghapusan jalankan `python -m pytest tests/ -q`. Jika ada
   test yang gagal, berarti schema tidak menjamin hal itu. Kembalikan check
   Python-nya dan catat di commit message.
6. `tests/test_contracts.py` sudah punya test yang mengharapkan `ContractError`
   untuk bentuk salah (`SPEC.json` sebagai array, `components` sebagai array,
   `production_ready: true`). Test ini harus tetap lolos, sekarang lewat jalur
   schema. Jangan ubah file test.

### Catatan penting soal fixture negatif

`fixtures/invalid-syntax/expected-connectivity.json` punya `components` dan
`nets` kosong. `connectivity.schema.json` mungkin tidak melarangnya (perlu
dibaca). Jika schema melarang array/objek kosong, jangan ubah fixture. Ubah
schema agar mengizinkan kosong, dan biarkan aturan "tidak boleh kosong kecuali
fixture negatif build" tetap di Python (`contracts.py:82-87`).

### Kriteria selesai

- `python -m pytest tests/ -q` lolos.
- Keempat fixture memuat kontraknya:
  ```
  python pcb-agent doctor --project fixtures/valid-blinky --format json
  python pcb-agent doctor --project fixtures/invalid-syntax --format json
  python pcb-agent doctor --project fixtures/invalid-value --format json
  python pcb-agent doctor --project fixtures/invalid-connectivity --format json
  ```
  Semua harus keluar tanpa exit code 3 (invalid config).
- `findstr /S /I "schemas" src\pcb_agent\*.py` sekarang memberi hasil.

### Commit

```
feat: validate project contracts against JSON schemas
```

---

## Task 8 — Load `config/policies.toml`

### Masalah

`config/policies.toml` dan `config/agents.toml` tidak dibaca kode mana pun:

```
findstr /S /I "config/" src\pcb_agent\*.py
```
Hasil kosong.

Akibatnya nilai berikut hardcoded atau hilang:

| Isi policy | Lokasi hardcoded sekarang |
|---|---|
| `max_iterations = 5` | `cli.py:260` batas `1 <= n <= 5`, dan default `cli.py:66` |
| `[workspace] max_changed_files = 20` | `cli.py:298` literal `20` |
| `[files] allow` | `cli.py:246-249` `_allowed_backend_path`, pola literal |
| `[files] deny` | tidak diterapkan sama sekali |
| `[checks] required` | tidak diterapkan; `required=` ditentukan per pemanggilan |
| `[commands] allow/deny` | `diode.py:32-36` daftar literal |

### Ruang lingkup task ini

Jangan coba menerapkan semuanya sekaligus. Task ini menangani tiga hal saja:

1. `max_iterations`
2. `workspace.max_changed_files`
3. `files.allow` dan `files.deny`

`[checks]` dan `[commands]` ditunda; catat sebagai komentar di bagian
"Ditunda" pada commit body.

### Langkah

1. Buat file baru `src/pcb_agent/config.py`:

```python
"""Locked harness policy loaded from config/policies.toml."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path


CONFIG_ROOT = Path(__file__).resolve().parent.parent.parent / "config"


class PolicyConfigError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class Policy:
    max_iterations: int
    max_changed_files: int
    allow_files: tuple[str, ...]
    deny_files: tuple[str, ...]
    allow_symlinks: bool
    allow_path_escape: bool

    @classmethod
    def load(cls, path: Path | None = None) -> "Policy":
        target = path or (CONFIG_ROOT / "policies.toml")
        try:
            data = tomllib.loads(target.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError) as error:
            raise PolicyConfigError(f"cannot load policy: {error}") from error
        return cls._from_mapping(data)

    @classmethod
    def _from_mapping(cls, data: dict) -> "Policy":
        ...
```

2. Implementasi `_from_mapping` dengan validasi ketat. Setiap field wajib ada
   dan bertipe benar, kalau tidak lempar `PolicyConfigError`:
   - `max_iterations`: int, `1 <= n <= 5`
   - `workspace.max_changed_files`: int, `>= 1`
   - `workspace.allow_symlinks`: bool, dan **harus** `False`. Jika `True`,
     lempar `PolicyConfigError`. Ini invariant keamanan, bukan opsi.
   - `workspace.allow_path_escape`: bool, harus `False`, sama alasannya.
   - `files.allow`: list of non-empty str, tidak kosong
   - `files.deny`: list of non-empty str, tidak kosong
   - `network`: harus string `"deny"`
   - `production_ready` dan `fabrication_approved`: harus `False`

3. Buka `src/pcb_agent/cli.py`:

   a. Tambah import: `from .config import Policy, PolicyConfigError`

   b. Di `main()`, muat policy sekali di awal blok `try`, sebelum
      `load_project`:
      ```python
      policy = Policy.load()
      ```
      Tangkap `PolicyConfigError` di blok `except` dan kembalikan exit code 3
      (invalid configuration). Tambahkan `PolicyConfigError` ke tuple
      exception di `cli.py:367`, dan tambah cabang:
      ```python
      if isinstance(error, (ConfigurationError, PolicyConfigError)):
          return 3
      ```

   c. Teruskan `policy` ke `_run_backend` dan `_run_backend_unlocked` sebagai
      parameter baru.

   d. Di `_run_backend_unlocked`, ganti `cli.py:260-261`:
      ```python
      if not 1 <= args.max_iterations <= 5:
      ```
      menjadi:
      ```python
      if not 1 <= args.max_iterations <= policy.max_iterations:
      ```

   e. Ganti `cli.py:298` literal `20`:
      ```python
      if len(changed) > policy.max_changed_files:
      ```

   f. Ubah `_allowed_backend_path` agar memakai policy:
      ```python
      def _allowed_backend_path(path: str, profile: str, policy: Policy) -> bool:
          if any(fnmatch(path, pattern) for pattern in policy.deny_files):
              return False
          for pattern in policy.allow_files:
              if pattern.endswith(".kicad_pcb") and profile != "layout":
                  continue
              if fnmatch(path, pattern):
                  return True
          return False
      ```
      Perbaiki pemanggilnya di `cli.py:285`.

### Jebakan `fnmatch`

`fnmatch` tidak memperlakukan `**` seperti glob rekursif. `fnmatch("src/a/b.zen",
"src/**/*.zen")` bisa memberi hasil tak terduga karena `*` pada `fnmatch`
mencocokkan `/` juga. Kode lama menyiasatinya dengan dua pola
(`src/*.zen` dan `src/**/*.zen`).

Karena `config/policies.toml` hanya mencantumkan `src/**/*.zen`, tambahkan
normalisasi di `Policy._from_mapping`: untuk setiap pola yang memuat `/**/`,
tambahkan juga varian tanpa `/**` ke daftar. Contoh: `src/**/*.zen` menghasilkan
`("src/**/*.zen", "src/*.zen")`. Lakukan hal sama untuk `deny_files`.

Tulis test yang membuktikan `src/blinky.zen` dan `src/nested/blinky.zen`
keduanya diizinkan, dan `SPEC.json` ditolak.

4. Buat `tests/test_config.py`. Wajib mencakup:
   - `Policy.load()` berhasil pada `config/policies.toml` nyata, dan
     `max_iterations == 5`, `max_changed_files == 20`.
   - `allow_symlinks = true` di TOML sementara menyebabkan `PolicyConfigError`.
   - `allow_path_escape = true` menyebabkan `PolicyConfigError`.
   - `max_iterations = 6` menyebabkan `PolicyConfigError`.
   - `network = "allow"` menyebabkan `PolicyConfigError`.
   - `production_ready = true` menyebabkan `PolicyConfigError`.
   - `files.allow` hilang menyebabkan `PolicyConfigError`.
   - Normalisasi pola `**` bekerja: `src/blinky.zen` dan `src/a/b.zen`
     diizinkan.
   - TOML rusak menyebabkan `PolicyConfigError`.

   Gunakan `tempfile.TemporaryDirectory` untuk menulis TOML varian. Jangan
   ubah `config/policies.toml` yang asli.

5. `tests/test_fake_backend.py` mengetes batas iterasi dan tamper. Jalankan dan
   pastikan tetap lolos. Jika test memanggil fungsi yang tanda tangannya
   berubah, sesuaikan pemanggilan di test, bukan logikanya.

### Kriteria selesai

- `python -m pytest tests/ -q` lolos.
- `findstr /S /I "policies.toml" src\pcb_agent\*.py` memberi hasil.
- Tidak ada lagi literal `20` untuk batas file berubah di `cli.py`.

### Commit

```
feat: enforce policies.toml for iterations and file allowlist

Ditunda: [checks] required dan [commands] allow/deny belum diterapkan.
```

---

## Task 9 — Check CONNECTIVITY nyata (fase A)

### Masalah

Ini gap terbesar. `src/pcb_agent/cli.py:163-170`:

```python
def _schematic_checks(project: ProjectState, run: RunState | None = None) -> list[Check]:
    test = _diode_command(project, "test-command", "ZENER_TEST", run.raw_directory if run else None)
    status = test.status
    return [
        test,
        _check("CONNECTIVITY", status, "connectivity covered by trusted Zener TestBench result"),
        _check("SPECIFICATION", status, "specification covered by trusted Zener TestBench result"),
    ]
```

CONNECTIVITY dan SPECIFICATION hanya menyalin status `ZENER_TEST`.
`expected-connectivity.json` dimuat, di-hash, divalidasi bentuknya, lalu
**tidak pernah dibandingkan dengan apa pun**.

Konsekuensi nyata: `expected-connectivity.json` bisa mendeklarasikan net yang
tidak ada di `.zen` dan tidak diperiksa TestBench, dan run tetap PASS. Kontrak
jadi dekorasi.

### Kenapa fase A dan bukan langsung ideal

Solusi ideal menurut `ARCHITECTURE_PROPOSAL.md` §11 adalah harness membangkitkan
TestBench dari `expected-connectivity.json`. Itu butuh peta nama net Diode yang
belum diketahui.

Bukti dari `fixtures/valid-blinky/tests/blinky_test.zen:17-22`:

```python
check(nets.get("VCC", []) == [("BlinkyTest__default.R1.R", "1")], ...)
check(nets.get("GND", []) == [("BlinkyTest__default.D1.LED", "K")], ...)
check(("BlinkyTest__default.R1.R", "2") in led_anode, ...)
check(("BlinkyTest__default.D1.LED", "A") in led_anode, ...)
```

Sedangkan `expected-connectivity.json` menuliskannya sebagai `R1.P1`, `R1.P2`,
`D1.A`, `D1.K`.

Jadi pemetaannya:

| Kontrak | Path komponen Diode | Nama pin Diode |
|---|---|---|
| `R1.P1` | `R1.R` | `"1"` |
| `R1.P2` | `R1.R` | `"2"` |
| `D1.A` | `D1.LED` | `"A"` |
| `D1.K` | `D1.LED` | `"K"` |

Suffix path (`R` vs `LED`) dan nama pin bergantung generic module yang dipakai.
Peta lengkap untuk semua generic stdlib belum diketahui. Menebaknya melanggar
`AGENT_PROTOCOL.md` (jangan mengarang kemampuan/schema).

Maka fase A memakai check yang **bisa** dilakukan tanpa peta itu.

### Fase A: coverage check statis

CONNECTIVITY memeriksa bahwa TestBench yang terkunci benar-benar menegaskan
setiap net dan setiap pin member yang dideklarasikan
`expected-connectivity.json`. Ini deterministik, punya evidence, dan menangkap
kegagalan nyata: kontrak menyebut sesuatu yang tidak pernah diuji.

Ini bukan pengganti pemeriksaan netlist. Ini gate anti-divergensi kontrak.
Wajib ditandai jelas di pesan check dan di dokumentasi bahwa cakupannya
terbatas.

### Aturan check

Diberikan `connectivity = expected-connectivity.json` dan teks sumber
`project.test`:

1. Untuk setiap nama net di `connectivity["nets"]`: nama net itu harus muncul
   sebagai literal string di sumber TestBench. Jika tidak,
   `CONNECTIVITY = FAIL` dengan pesan menyebut net mana.

2. Untuk setiap member `REF.PIN` di setiap net: `REF` harus muncul sebagai
   literal di sumber TestBench. `PIN` tidak diperiksa pada fase A, karena
   penamaannya berbeda (lihat tabel di atas). Catat batasan ini di pesan check.

3. Untuk setiap referensi komponen di `connectivity["components"]`: harus muncul
   sebagai literal di sumber TestBench.

4. Untuk setiap net di `connectivity["rules"]["required_power_nets"]`: harus ada
   di `connectivity["nets"]`. Jika tidak, `FAIL`. Ini check
   internal-consistency kontrak, tidak butuh TestBench.

5. Jika `ZENER_TEST` bukan PASS, `CONNECTIVITY` mewarisi statusnya dan tidak
   menjalankan coverage check. Alasan: tanpa test yang lolos, coverage tidak
   bermakna.

6. Pengecualian fixture negatif build: jika `connectivity["components"]` dan
   `["nets"]` kosong (kasus `fixtures/invalid-syntax`), lewati aturan 1-3,
   status `SKIPPED`, `required=False`, pesan menyebut fixture negatif build.

### Langkah

1. Buat file baru `src/pcb_agent/connectivity.py`:

```python
"""Deterministic contract-coverage checks over the locked TestBench."""

from __future__ import annotations

from typing import Any, Mapping


class CoverageResult:
    ...


def coverage_failures(
    connectivity: Mapping[str, Any], testbench_source: str
) -> tuple[str, ...]:
    """Return human-readable failures. Empty tuple means covered."""
    ...
```

2. Implementasi `coverage_failures` sesuai aturan 1-4 di atas. Kembalikan tuple
   pesan, satu per pelanggaran, terurut deterministik (`sorted`). Jangan
   berhenti di pelanggaran pertama; laporkan semua supaya bisa diperbaiki
   sekaligus.

   Untuk pencocokan literal, gunakan pengecekan substring sederhana pada teks
   sumber. Jangan parse Starlark. Contoh:
   ```python
   if net_name not in testbench_source:
       failures.append(f"net not asserted in TestBench: {net_name}")
   ```

3. Buka `src/pcb_agent/cli.py`, ganti `_schematic_checks`:

```python
def _schematic_checks(project: ProjectState, run: RunState | None = None) -> list[Check]:
    test = _diode_command(project, "test-command", "ZENER_TEST", run.raw_directory if run else None)
    return [test, _connectivity_check(project, test), _specification_check(project, test)]
```

4. Tambahkan `_connectivity_check`:

```python
def _connectivity_check(project: ProjectState, test: Check) -> Check:
    if test.status != CheckStatus.PASS:
        return _check("CONNECTIVITY", test.status, "Zener TestBench did not pass")
    connectivity = project.connectivity
    if not connectivity["components"] and not connectivity["nets"]:
        return _check("CONNECTIVITY", CheckStatus.SKIPPED,
                      "build-negative fixture declares no expected connectivity",
                      required=False)
    try:
        source = (project.root / project.test).read_text(encoding="utf-8")
    except OSError as error:
        return _check("CONNECTIVITY", CheckStatus.BLOCKED, str(error))
    failures = coverage_failures(connectivity, source)
    if failures:
        return _check("CONNECTIVITY", CheckStatus.FAIL, "; ".join(failures))
    return _check("CONNECTIVITY", CheckStatus.PASS,
                  "every expected net and component reference is asserted by the locked TestBench; "
                  "pin-level netlist comparison is not yet implemented")
```

5. `ProjectState` saat ini tidak menyimpan `connectivity`. Cek
   `src/pcb_agent/state.py` — `ProjectState` punya field `root, name, config,
   hashes, profile, source, test, board, acceptance`. Tambahkan field
   `connectivity: Mapping[str, Any]` dan `specification: Mapping[str, Any]`,
   lalu isi dari `ProjectContract` di `load_project`. `ProjectContract` sudah
   punya keduanya (`contracts.py:37-39`).

6. Buat `tests/test_connectivity.py`. Wajib mencakup:
   - Fixture `valid-blinky` nyata: `coverage_failures` mengembalikan tuple
     kosong. Baca `fixtures/valid-blinky/expected-connectivity.json` dan
     `fixtures/valid-blinky/tests/blinky_test.zen` langsung dari disk.
   - Net yang tidak disebut TestBench menghasilkan failure yang memuat nama net.
   - Referensi komponen yang tidak disebut menghasilkan failure.
   - `required_power_nets` yang menyebut net tak terdaftar menghasilkan failure.
   - Beberapa pelanggaran sekaligus menghasilkan beberapa failure, terurut.
   - Connectivity kosong plus TestBench kosong tidak melempar exception.

7. Verifikasi terhadap ketiga fixture negatif juga: `invalid-value` dan
   `invalid-connectivity` punya `expected-connectivity.json` yang sama dengan
   `valid-blinky` dan TestBench yang menyebut net yang sama, jadi
   `coverage_failures` harus kosong untuk keduanya. Yang gagal pada fixture itu
   adalah `ZENER_TEST`, bukan coverage. Tambahkan test yang menegaskan ini,
   supaya pembagian tanggung jawab antar-check terkunci.

### Kriteria selesai

- `python -m pytest tests/ -q` lolos.
- Pesan check CONNECTIVITY tidak lagi berbunyi "covered by trusted Zener
  TestBench result".
- `findstr /S /N "covered by trusted" src\` kosong.
- Membuat file uji sementara yang menghapus satu net dari
  `expected-connectivity.json` salinan (di direktori temporary, bukan fixture
  asli) menghasilkan CONNECTIVITY FAIL.

### Commit

```
feat: check expected connectivity coverage against locked TestBench

Fase A. Perbandingan pin-level netlist masih belum ada; lihat task 14.
```

---

## Task 10 — Check SPECIFICATION nyata (fase A)

### Masalah

Sama seperti Task 9: SPECIFICATION menyalin status `ZENER_TEST`.
`SPEC.json.requirements` tidak dibandingkan dengan apa pun.

### Aturan check

Diberikan `specification`, `acceptance`, dan teks sumber `project.test`:

1. Setiap requirement yang punya `constraints` harus punya setidaknya satu
   acceptance check `kind == "zener_test"` yang merujuknya. Jika hanya ada
   check `diode_build`, itu tidak cukup untuk memverifikasi nilai. `FAIL`.

   Catatan: `contracts.py:142-143` sudah memastikan setiap requirement tercakup
   *sesuatu*. Check ini lebih ketat: requirement dengan constraint butuh
   verifikasi tingkat test, bukan hanya build.

2. Setiap nilai constraint harus muncul sebagai literal di sumber TestBench.
   Contoh: `fixtures/valid-blinky/SPEC.json` REQ-001 punya constraint value
   `1kohm` dan package `0402`. Keduanya muncul di `blinky_test.zen:10-11`.
   Jika nilai constraint tidak muncul, `FAIL` dengan pesan menyebut
   requirement ID dan nilai yang hilang.

3. Setiap `subject` requirement (jika ada) harus muncul sebagai literal di
   sumber TestBench.

4. Setiap nama test pada acceptance `kind == "zener_test"` harus punya
   bagian setelah titik yang muncul sebagai nama fungsi di sumber TestBench.
   Contoh: acceptance `BlinkyTest.component_value` mengharuskan
   `def component_value` ada di sumber. Ini menangkap acceptance yang merujuk
   test yang tidak ada.

5. Jika `ZENER_TEST` bukan PASS, warisi statusnya tanpa menjalankan check.

6. Fixture negatif build (`kind == "diode_build"` dengan `expected == "FAIL"`,
   seperti `fixtures/invalid-syntax`): status `SKIPPED`, `required=False`.

### Langkah

1. Tambahkan ke `src/pcb_agent/connectivity.py` (atau buat
   `src/pcb_agent/specification.py` jika lebih rapi):

```python
def specification_failures(
    specification: Mapping[str, Any],
    acceptance: Mapping[str, Any],
    testbench_source: str,
) -> tuple[str, ...]:
    ...
```

2. Implementasi aturan 1-4. Kembalikan tuple pesan terurut.

   Untuk aturan 2, ambil nilai constraint dari `requirement["constraints"]`.
   Nilainya bisa string, int, atau bool. Konversi ke string sebelum mencari
   substring. Lewati nilai numerik seperti `minimum_count` yang tidak
   dimaksudkan muncul literal di test — batasi pencarian pada constraint key
   yang bertipe string. Baca `fixtures/valid-blinky/SPEC.json` dan
   `skill/diode-pcb-agent/assets/project-template/SPEC.json` untuk melihat key
   yang benar-benar dipakai sebelum memutuskan.

3. Tambahkan `_specification_check` di `cli.py`, pola sama dengan
   `_connectivity_check`.

4. Buat test di `tests/test_specification.py`. Wajib mencakup:
   - `valid-blinky` nyata: tidak ada failure.
   - `invalid-value` nyata: SPEC menuntut `1kohm`, TestBench juga menegaskan
     `1kohm`. Jadi coverage lolos; yang gagal `ZENER_TEST`. Tegaskan ini.
   - Requirement dengan constraint yang nilainya tidak ada di TestBench
     menghasilkan failure.
   - Acceptance yang merujuk test tak ada (`BlinkyTest.tidak_ada`) menghasilkan
     failure.
   - Requirement dengan constraint yang hanya punya acceptance `diode_build`
     menghasilkan failure.
   - `subject` yang tidak muncul di TestBench menghasilkan failure.

### Kriteria selesai

- `python -m pytest tests/ -q` lolos.
- Keempat fixture menghasilkan status yang sama seperti sebelum task ini untuk
  keseluruhan run. Artinya: coverage check tidak mengubah hasil fixture yang
  sudah benar, hanya menambah gate. Verifikasi dengan menjalankan
  `python pcb-agent verify --project fixtures/valid-blinky --profile schematic`
  jika Diode tersedia. Jika Diode tidak tersedia di mesin, cukup andalkan
  unit test.

### Commit

```
feat: check specification constraints coverage against locked TestBench
```

---

## Task 11 — Command `init`

### Masalah

`_parser()` di `cli.py:43-69` hanya mendaftarkan `doctor build layout drc verify
report check run`. Command `init` tidak ada, padahal
`skill/diode-pcb-agent/assets/project-template/` sudah lengkap (7 file) dan
`ARCHITECTURE_PROPOSAL.md` §8 mendefinisikannya sebagai normatif.

### Kontrak command

Dari `ARCHITECTURE_PROPOSAL.md` §8:

- Tujuan: membuat contract/template board baru
- Output: JSON path yang dibuat, plus ringkasan
- Side effect: membuat direktori baru
- Exit: `0` sukses, `3` input invalid
- Keamanan: tolak target tidak kosong, traversal, symlink, overwrite

### Langkah

1. Tambahkan subparser di `_parser()`:
   ```python
   init = sub.add_parser("init")
   init.add_argument("name")
   init.add_argument("--into", default=".")
   init.add_argument("--format", choices=("human", "json"), default="human")
   ```

2. Validasi `name` dengan ketat. Tolak jika tidak cocok
   `^[a-z0-9][a-z0-9-]{0,63}$`. Alasan: nama masuk ke `SPEC.json.project.name`
   yang schema-nya punya pattern, dan masuk ke nama direktori. Nama seperti
   `../evil` atau `a;rm -rf` harus ditolak dengan exit 3.

3. Buat fungsi `_init(args) -> int` di `cli.py`. Alurnya:

   a. Resolve target: `Path(args.into).resolve() / args.name`.

   b. Tolak jika target sudah ada dan tidak kosong. Tolak jika target adalah
      symlink. Tolak jika `Path(args.into).resolve()` bukan direktori.

   c. Tentukan sumber template:
      ```python
      TEMPLATE_ROOT = Path(__file__).resolve().parent.parent.parent / "skill" / "diode-pcb-agent" / "assets" / "project-template"
      ```

   d. Salin tujuh file berikut dari template ke target, mempertahankan struktur:
      - `src/board.zen`
      - `tests/board_test.zen`
      - `SPEC.json`
      - `ACCEPTANCE.json`
      - `expected-connectivity.json`
      - `project.toml`
      - `pcb.toml`

      Gunakan `shutil.copy2`. Buat direktori induk dengan
      `mkdir(parents=True, exist_ok=True)`.

      Jangan pakai `shutil.copytree` pada seluruh direktori template, karena
      `skill/diode-pcb-agent/assets/project-template/` bisa berisi
      `__pycache__` atau file lain. Salin daftar eksplisit.

   e. Ganti nama project di file yang menyebutnya. Template memakai
      `template-board` dan `template_board`. Baca kelima file teks
      (`SPEC.json`, `project.toml`, `pcb.toml`, `src/board.zen`,
      `tests/board_test.zen`), ganti:
      - `template-board` -> `args.name`
      - `template_board` -> `args.name.replace("-", "_")`

      Tulis kembali dengan `newline="\n"` supaya konsisten dengan
      `.gitattributes` LF.

      Verifikasi dulu string mana yang benar-benar ada dengan:
      ```
      findstr /S /N "template" skill\diode-pcb-agent\assets\project-template\*
      ```
      Sesuaikan daftar penggantian dengan hasil nyata.

   f. Setelah menyalin, muat kontrak yang baru dibuat untuk membuktikannya
      valid:
      ```python
      load_project(target)
      ```
      Jika melempar, hapus target yang baru dibuat (hanya jika task ini yang
      membuatnya) dan kembalikan exit 3. Ini mencegah `init` menghasilkan
      project yang langsung ditolak `verify`.

   g. Output. Untuk `--format json`:
      ```python
      print(json.dumps({"project": args.name, "root": str(target),
                        "created": sorted(created_relative_paths),
                        "production_ready": False,
                        "fabrication_approved": False}, sort_keys=True))
      ```
      Untuk `human`: cetak root dan daftar file, lalu baris
      `production_ready: false; fabrication_approved: false`.

4. Di `main()`, tangani `init` **sebelum** `load_project`, karena project belum
   ada saat command dijalankan:
   ```python
   args = _parser().parse_args(argv)
   if args.command == "init":
       return _init(args)
   ```
   Letakkan sebelum blok `try` yang memanggil `load_project`, atau di dalam
   `try` tapi sebagai cabang pertama.

5. Buat `tests/test_init.py`. Wajib mencakup:
   - `init` di direktori temporary membuat ketujuh file.
   - Project hasil `init` bisa dimuat `load_project` tanpa error.
   - Nama project di `SPEC.json` sudah diganti, bukan `template-board`.
   - Nama tidak valid (`../evil`, `A_B`, string kosong, `a;b`) menghasilkan
     exit 3 dan tidak membuat file apa pun.
   - Target yang sudah ada dan tidak kosong menghasilkan exit non-zero dan
     tidak menimpa file yang ada.
   - `--format json` menghasilkan JSON valid yang memuat
     `"production_ready": false`.

   Gunakan `main(["init", "nama", "--into", str(tmpdir)])` untuk memanggil.

### Kriteria selesai

- `python -m pytest tests/ -q` lolos.
- Manual: `python pcb-agent init demo-board --into <tempdir>` lalu
  `python pcb-agent doctor --project <tempdir>/demo-board` tidak memberi exit 3.

### Commit

```
feat: add init command using project template
```

---

## Task 12 — Fixture `acceptance-tampered`

### Masalah

`ARCHITECTURE_PROPOSAL.md` §17 mendaftarkan 18 fixture. Repo punya 4.
`acceptance-tampered` adalah salah satu yang paling penting karena membuktikan
deteksi manipulasi acceptance, yang jadi klaim keamanan utama repo.

Saat ini deteksi tamper hanya diuji di `tests/test_fake_backend.py` lewat unit
test dengan backend palsu. Belum ada fixture yang bisa dijalankan lewat CLI.

### Ruang lingkup

Fixture ini tidak butuh Diode. Ia menguji lapisan `ProtectedHashes`.

### Langkah

1. Buat direktori `fixtures/acceptance-tampered/` dengan struktur sama seperti
   `fixtures/valid-blinky/`, minus `.pcb/` dan `reports/`. Salin dari
   `valid-blinky`:
   - `SPEC.json`
   - `ACCEPTANCE.json`
   - `expected-connectivity.json`
   - `pcb.toml`
   - `project.toml`
   - `src/blinky.zen`
   - `tests/blinky_test.zen`

2. Ubah `project.toml`: `name = "acceptance-tampered"`. Ubah `pcb.toml` sama.
   Ubah `SPEC.json` `project.name` menjadi `acceptance-tampered`.

3. Fixture ini **tidak** boleh punya file yang sudah rusak. Yang diuji adalah
   perilaku harness ketika file dimodifikasi **selama** run. Jadi fixture-nya
   valid; test-nya yang melakukan tamper.

4. Tambahkan test ke `tests/test_policy.py` (atau file baru
   `tests/test_fixture_tampered.py`):

   - Salin `fixtures/acceptance-tampered/` ke direktori temporary. Jangan
     jalankan test langsung di dalam `fixtures/`, karena akan mengotori repo.
   - `ProtectedHashes.capture` pada salinan.
   - Modifikasi `ACCEPTANCE.json` di salinan (ubah `expected` dari `PASS` ke
     `FAIL`).
   - `verify()` harus melempar `PolicyViolation` dengan pesan memuat
     `ACCEPTANCE.json`.
   - Kasus kedua: modifikasi `tests/blinky_test.zen` (hapus satu baris
     `check(...)`). `ProtectedHashes.capture` dengan `project.test` termasuk
     dalam daftar protected harus mendeteksinya.

5. Tambahkan `fixtures/acceptance-tampered/reports/` ke `.gitignore` jika perlu.
   Cek `.gitignore` yang ada: sudah memuat `reports/runs/` dan `reports/raw/`,
   tapi tidak `fixtures/*/reports/`. Karena
   `fixtures/valid-blinky/reports/20260824T.../` saat ini terlacak git,
   jangan ubah aturan itu pada task ini.

### Kriteria selesai

- `python -m pytest tests/ -q` lolos.
- `python pcb-agent doctor --project fixtures/acceptance-tampered --format json`
  tidak memberi exit 3.

### Commit

```
test: add acceptance-tampered fixture and tamper detection test
```

---

## Task 13 — Fixture `path-traversal`

### Masalah

`ARCHITECTURE_PROPOSAL.md` §17 mendaftarkan fixture `path-traversal` dengan
hasil yang diharapkan `Security FAIL / 1`.

`tests/test_paths.py` sudah menguji `resolve_workspace_path` dan
`validate_executable` di tingkat unit. `tests/test_contracts.py` menguji
`../outside.zen` di `project.toml`. Yang belum ada: fixture yang bisa dijalankan
lewat CLI.

### Langkah

1. Buat `fixtures/path-traversal/` dengan tujuh file seperti Task 12, tapi
   dengan `project.toml` yang sengaja rusak:
   ```toml
   [project]
   name = "path-traversal"
   profile = "schematic"
   source = "../valid-blinky/src/blinky.zen"
   test = "tests/blinky_test.zen"

   [toolchain]
   pcb_version = "0.4"

   [layout]
   required = false
   ```

   `source` menunjuk ke luar project root.

2. Karena `load_project_contract` akan menolak fixture ini, `doctor` pun akan
   gagal dengan exit 3. Itu perilaku yang benar dan yang diuji.

   Catat di file `fixtures/path-traversal/README.md` satu paragraf singkat:
   fixture ini sengaja invalid, diharapkan ditolak, jangan "diperbaiki".
   Ini penting karena agent berikutnya bisa mengira ini bug.

3. Tambahkan test di `tests/test_contracts.py` atau file baru:
   ```python
   def test_path_traversal_fixture_rejected(self):
       with self.assertRaises((ContractError, ValueError)):
           load_project_contract(ROOT / "fixtures" / "path-traversal")
   ```

4. Tambahkan juga test tingkat CLI yang menegaskan exit code:
   ```python
   code = main(["doctor", "--project", str(ROOT / "fixtures" / "path-traversal")])
   self.assertEqual(code, 3)
   ```
   Perhatikan: `main` mencetak ke stderr. Bungkus dengan
   `contextlib.redirect_stderr(io.StringIO())` supaya output test bersih.

5. Pastikan fixture ini tidak merusak test lain yang melakukan iterasi atas
   seluruh `fixtures/`. Cari dulu:
   ```
   findstr /S /N "fixtures" tests\*.py
   ```
   Jika ada test yang mengasumsikan semua fixture bisa dimuat, kecualikan
   `path-traversal` secara eksplisit.

### Kriteria selesai

- `python -m pytest tests/ -q` lolos.
- `python pcb-agent doctor --project fixtures/path-traversal` keluar dengan
  exit code 3.

### Commit

```
test: add path-traversal fixture rejected by contract loader
```

---

## Task 14 — Spike net-naming Diode (fase B)

### Status

Research spike. Bukan implementasi. Hasilnya adalah dokumen, bukan kode
produksi.

### Pertanyaan yang harus dijawab

Untuk membangkitkan TestBench dari `expected-connectivity.json` seperti diminta
`ARCHITECTURE_PROPOSAL.md` §11, harness butuh peta:

```
(kind kontrak, nama pin kontrak) -> (suffix path Diode, nama pin Diode)
```

Yang sudah diketahui dari `fixtures/valid-blinky/tests/blinky_test.zen`:

| kind | pin kontrak | suffix path | pin Diode |
|---|---|---|---|
| `resistor` | `P1` | `R` | `1` |
| `resistor` | `P2` | `R` | `2` |
| `led` | `A` | `LED` | `A` |
| `led` | `K` | `LED` | `K` |

Yang belum diketahui: semua generic lain. `fixtures/valid-blinky/.pcb/stdlib/`
berisi `Resistor.zen`, `Led.zen`, `Capacitor.zen`, `Crystal.zen`, dan lain-lain.

### Prasyarat lingkungan

Diode `pcbc 0.4.34` hanya berjalan di WSL ext4 menurut
`INTEGRATION_RESULTS.md`. Windows-native diblokir OS error 1314 (butuh
privilege symlink). Jadi spike ini harus dijalankan di WSL, dengan repo
disalin ke filesystem ext4, bukan `/mnt/c`.

### Langkah

1. Baca setiap file `.zen` di `fixtures/valid-blinky/.pcb/stdlib/generics/`.
   Untuk setiap generic, catat:
   - Nama modul
   - Nama komponen internal (yang jadi suffix path)
   - Nama pin yang diekspos ke pemanggil
   - Nama pin sebenarnya pada footprint/symbol

2. Tulis satu `.zen` uji di direktori temporary WSL yang meng-instantiate
   setiap generic sekali, lalu satu TestBench yang mencetak `module.nets()` dan
   `module.components()` mentah. Jalankan:
   ```
   pcb test <file> -f json
   ```
   Simpan output JSON sebagai evidence.

3. Dari output itu, susun tabel pemetaan lengkap.

4. Jawab juga: apakah prefix `BlinkyTest__default.` selalu berbentuk
   `{TestBenchName}__{caseName}.`? Uji dengan mengganti nama TestBench dan nama
   test case, lalu bandingkan.

5. Tulis hasilnya ke `docs/spike-diode-net-naming.md`. Wajib memuat:
   - Versi tepat `pcb` dan `pcbc` yang dipakai
   - Tanggal
   - SHA-256 setiap output JSON mentah yang jadi dasar kesimpulan
   - Tabel pemetaan
   - Status setiap baris: `VERIFIED` atau `REQUIRES TEST`
   - Kesimpulan: apakah pembangkitan TestBench otomatis layak atau tidak

6. Jangan tulis kode generator sebelum dokumen ini selesai dan pemetaannya
   `VERIFIED`. Menebak pemetaan melanggar `AGENT_PROTOCOL.md` bagian "jangan
   mengarang output netlist, JSON, ERC, atau SPICE".

### Kriteria selesai

- `docs/spike-diode-net-naming.md` ada, memuat evidence hash, dan setiap baris
  tabel bertanda status.
- Tidak ada perubahan pada `src/`.

### Commit

```
docs: record Diode net naming spike results
```

---

## Yang sengaja tidak dikerjakan

| Item | Alasan |
|---|---|
| Backend AI nyata (`codex`, `claude`, `gemini`, `aider`) | Butuh isolasi jaringan tingkat OS yang belum ada. README sendiri menyatakan "MVP does not claim OS-level network isolation". Mengaktifkan backend tanpa sandbox memperbesar attack surface tanpa mitigasi. |
| Otomasi SPICE | `cli.py:213` hardcoded SKIPPED. `ARCHITECTURE_PROPOSAL.md` §21 menyatakan ditunda sampai spike command/model/scenario selesai. |
| `bootstrap` command | Butuh unduh dan verifikasi installer Diode. Perlu keputusan pengguna soal consent dan pinning. |
| `clean --dry-run` | Nilainya rendah dibanding risiko. Tidak memblokir apa pun. |
| `[commands] allow/deny` dari policy | `diode.py:32-36` sudah punya allowlist executable yang ketat (`pcb`/`pcbc` saja) plus denylist subcommand. Memindahkannya ke config menambah permukaan salah-konfigurasi tanpa menambah keamanan. Kerjakan hanya jika ada kebutuhan nyata. |
| 12 fixture sisa dari §17 | Sebagian sudah tercakup unit test. Tambahkan saat gate yang relevan benar-benar ada. Fixture tanpa gate yang mengujinya hanya beban perawatan. |
| Menghapus `config/agents.toml` | Masih relevan sebagai deklarasi status backend. Biarkan sampai backend nyata dikerjakan. |

## Urutan eksekusi yang disarankan

Batch 1, aman dan cepat: Task 1, 2, 3, 4, 5.
Batch 2, fondasi validasi: Task 6, 7.
Batch 3, gap terbesar: Task 9, 10.
Batch 4, policy dan kelengkapan: Task 8, 11.
Batch 5, bukti: Task 12, 13.
Batch 6, riset: Task 14.

Task 8 diletakkan setelah Task 9 dan 10 karena keduanya lebih penting dan tidak
bergantung padanya. Jika waktu terbatas, kerjakan sampai Batch 3 saja: itu yang
mengubah kontrak dari dekorasi menjadi gate nyata.
