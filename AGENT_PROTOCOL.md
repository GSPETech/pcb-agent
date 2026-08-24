# Portable PCB Agent Protocol v1

## Authority

Source of truth, berurutan: `SPEC.json`, `ACCEPTANCE.json`,
`expected-connectivity.json`, deterministic tool output, dan human engineering
decision. AI narrative bukan evidence.

Automated result selalu memiliki `production_ready = false` dan
`fabrication_approved = false`.

## Required workflow

1. Baca file protocol ini, `SPEC.json`, `ACCEPTANCE.json`, dan
   `expected-connectivity.json` untuk project aktif.
2. Jalankan `pcb-agent doctor --format json` bila harness tersedia. Jika tidak,
   laporkan `BLOCKED`; jangan menginstal tool tanpa approval.
3. Buat plan minimal berdasarkan requirement ID.
4. Edit hanya file allowlist.
5. Jalankan `pcb-agent verify --format json` bila tersedia. Untuk fixture-only
   development, jalankan command Diode eksplisit dalam `project.toml`.
6. Baca structured report dan raw artifact yang dirujuk.
7. Perbaiki maksimal lima iterasi. Hentikan bila fingerprint diff + failure
   berulang tanpa progres.
8. Laporkan perubahan, command, exit code, status, evidence, dan unknown.

## File boundary

Agent boleh mengubah, hanya bila task membutuhkan:

- `src/**/*.zen`
- maintained `layout/**/*.kicad_pcb`, hanya pada explicit layout task
- documentation yang diminta pengguna

Agent dilarang mengubah selama repair run:

- `SPEC.json`
- `ACCEPTANCE.json`
- `expected-connectivity.json`
- `tests/**/*`
- `config/**/*`
- `schemas/**/*`
- validator, report raw, policy, lock, atau evidence artifact

Perubahan terhadap denylist adalah policy failure. Jangan menonaktifkan check,
mengurangi severity, mengubah expected value, atau menghapus test agar lolos.

## Execution boundary

- Satu backend AI per run. Backend tidak boleh memulai backend AI lain.
- Gunakan argument array, bukan interpolated shell command.
- Write harus tetap dalam canonical workspace path; tolak traversal/symlink.
- Network default off. Minta approval untuk host dan tujuan spesifik.
- Jangan menjalankan `sudo`, installer pipe-to-shell, destructive cleanup,
  manufacturing order, atau fabrication upload.
- Jangan mencetak secret, authorization header, full environment, atau home
  directory listing.

## Status and exit contract

| Status | Meaning | Default exit |
|---|---|---:|
| `PASS` | Semua required deterministic checks selesai dan lolos | 0 |
| `FAIL` | Required validation menemukan mismatch | 1 |
| `BLOCKED` | Dependency/evidence wajib tidak tersedia | 2 |
| `HUMAN_REVIEW` | Keputusan engineering manusia belum selesai | 5 |
| `SKIPPED` | Optional check tidak dipilih atau tidak applicable | 0 |

Invalid config memakai exit `3`. Backend crash, timeout, invalid envelope,
iteration limit, atau no-progress memakai exit `4`. `warning` adalah severity,
bukan status.

## Stop conditions

Berhenti dan laporkan tanpa menebak bila:

- requirement ambigu atau saling konflik;
- authoritative datasheet/package evidence tidak ada;
- mandatory tool/evidence `BLOCKED`;
- perubahan butuh file denylist;
- lima iterasi habis atau failure fingerprint berulang;
- layout change berisiko menghapus placement/routing manusia;
- fabrication, safety, compliance, SI/RF, thermal, mechanical, atau DFM butuh
  approval manusia.

## Report minimum

Sertakan project, iteration, changed files, sanitized commands, tool versions,
exit codes, check statuses, evidence paths/hashes bila tersedia, remaining
unknowns, dan `human_review.required`. Jangan menyatakan siap produksi.
