# Agent Instructions

Baca dan patuhi `AGENT_PROTOCOL.md`. Gunakan `prompts/design-agent.md` untuk
design/repair task dan `skill/diode-pcb-agent/SKILL.md` untuk workflow domain.

Jangan ubah acceptance, expected connectivity, tests, policy, schema, validator,
atau evidence untuk membuat run lolos. Verification `PASS` bukan fabrication
approval.

## Repository scope

Repository ini berisi **harness saja**. Board project, deliverable, arsip,
dan scratch export tidak disimpan di sini — lihat `.gitignore`. Fixture di
`fixtures/` dan evidence bundle di `tests/evidence/` adalah milik repo dan
harus tetap tracked.

## Toolchain requirement

Adapter registry dipin ke `pcbc 0.4.40`
(`_CAPTURED_PCBC_VERSION` di `src/pcb_agent/generated_testbench.py`). Gate
`CONNECTIVITY` dan `SPECIFICATION` menjadi `BLOCKED` pada versi lain — ini
fail-closed yang disengaja, bukan bug.

`pcb.toml` hanya menerima lane (`pcb-version = "0.4"`), bukan patch. Untuk
memaksa toolchain tepat, pasang shim di depan `PATH`:

```sh
pcb toolchain install 0.4.40
mkdir -p /tmp/pcbshim
printf '#!/bin/bash\nexec "$HOME/.local/bin/pcb" +0.4.40 "$@"\n' > /tmp/pcbshim/pcb
chmod +x /tmp/pcbshim/pcb
export PATH="/tmp/pcbshim:$PATH"
```

Windows-native `pcb build` gagal `os error 1314` (privilege symlink). Jalankan
build/verify di WSL2, atau aktifkan Developer Mode.

## Menyiapkan project agar bisa diverifikasi

Harness butuh empat file di root project, plus locked TestBench:

| File | Isi |
|---|---|
| `project.toml` | `profile`, `source`, `test`, `[toolchain]`, `[layout]` |
| `SPEC.json` | requirement `REQ-nnn` + constraint |
| `ACCEPTANCE.json` | check `ACC-nnn` memetakan setiap requirement |
| `expected-connectivity.json` | components, nets, rules |
| `tests/<name>.zen` | locked TestBench, nama harus cocok `ACCEPTANCE.checks[].test` |

Template ada di `skill/diode-pcb-agent/assets/project-template/`.

### Layout project yang didukung

Snapshot terpercaya menyalin `src/**`, `modules/**`, `components/**`, `*.zen`
di root, plus `pcb.toml` dan `pcb-version`. Dua bentuk repo sama-sama jalan:

- fixture layout: source di `src/board.zen`
- board-repository layout (hasil `pcb new board` / `pcb import`): entry point
  `.zen` di root, subcircuit di `modules/` dan `components/`

### Aturan penamaan yang wajib dipatuhi

Nama net dan ref komponen di-render menjadi Zener source, jadi setiap segmen
harus cocok `[A-Za-z][A-Za-z0-9_-]*`. Ref hierarkis dipisah titik
(`IMU.R17`, `POWER.C1`); net di-key dengan nama polos seperti yang
dikembalikan `module.nets()`.

Nama hasil `pcb import` sering tidak sah dan harus dinormalisasi lebih dulu:

| Import | Ganti |
|---|---|
| `+3_3V` | `VDD_3V3` |
| `IMU_XTAL+` | `IMU_XTAL_P` |
| `Net-(U1-VOUT)` | `NET_U1_VOUT` |
| `/IMU/BNO_SCL` | `IMU_BNO_SCL` |

Rename hanya ejaan; keanggotaan dan topologi net tidak boleh berubah.

### Kind komponen yang terdaftar

`resistor`, `led`, `capacitor`, `inductor`, `ferrite_bead`, `thermistor`,
`zener`, `rectifier`, `tvs`. Crystal sengaja absen — lihat
`docs/spike-diode-net-naming.md`.

Kind lain (IC, konektor, switch, testpoint) tidak punya adapter terverifikasi
dan **selalu** `BLOCKED`. Jangan menambah kind tanpa evidence capture; jangan
menghapus komponen dari kontrak supaya lolos. `pcb import` mengeluarkan part
yang tidak dikenalnya sebagai `Component()` dengan `type=None`, sehingga di
luar jangkauan registry.

Cek kind nyata sebelum menulis kontrak, dengan TestBench probe:

```python
def probe(module, inputs):
    for key, comp in sorted(module.components().items()):
        print(key + " type=" + str(comp.type))
    check(False, "probe")
```

## Menjalankan verifikasi

```sh
./pcb-agent doctor --project <DIR> --format json
./pcb-agent verify --project <DIR> --profile schematic --format json
./pcb-agent verify --project <DIR> --profile layout --format json
```

Profil `layout` menjalankan gate berurutan:

| Gate | Perintah | Catatan |
|---|---|---|
| `LAYOUT_GENERATE` | `pcb layout` | semua footprint di origin, tanpa Edge.Cuts |
| `PLACEMENT` | internal | placement deterministik + outline diturunkan dari hasilnya |
| `ROUTE` | `freerouting` | DSN keluar, SES masuk, lewat `pcbnew` Python |
| `LAYOUT_SYNC` | `pcb layout --check` | |
| `KICAD_DRC` | `kicad-cli pcb drc` | |

Profil `layout` **tidak** menghasilkan `.kicad_sch`; jalankan `pcb apply` bila
schematic KiCad dibutuhkan.

### Prasyarat gate PLACEMENT dan ROUTE

`PLACEMENT` mengelompokkan komponen per modul Zener (dari property `Path`),
memberi setiap komponen sel seukuran courtyard-nya sendiri, lalu menurunkan
Edge.Cuts persegi dari bounding box hasil placement. Deterministik dan idempoten.

`ROUTE` butuh dua binary di `PATH`:

```sh
# Freerouting 2.3.0, verifikasi checksum rilis resmi sebelum dipakai
freerouting --help

# pcbnew Python binding untuk konversi DSN/SES (kicad-cli tidak punya)
python3 -c "import pcbnew; print(pcbnew.GetBuildVersion())"
```

Keduanya di-probe lebih dulu; bila absen gate menjadi `BLOCKED`, bukan `FAIL`.
Determinisme Freerouting sudah diukur: dua run pada DSN identik menghasilkan
SES identik byte-per-byte.

`ROUTE` `PASS` hanya berarti trace dihasilkan dan diterapkan ke board. Apakah
board layak diputuskan oleh `KICAD_DRC` sebagai gate tersendiri.

Exit code ada di `AGENT_PROTOCOL.md`. `FAIL` berarti gate berjalan dan
menemukan mismatch nyata; `BLOCKED` berarti gate tidak dapat dievaluasi.

## Sebelum commit

```sh
python -m pytest -q
python -m pyright
```

Keduanya harus bersih. Jangan commit arsip, board deliverable, atau
`reports/`.
