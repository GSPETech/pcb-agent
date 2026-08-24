# Brainstorm dan rancang arsitektur PCB AI Agent berbasis Diode

Bertindaklah sebagai gabungan:

* Principal systems architect.
* PCB design automation engineer.
* EDA toolchain engineer.
* AI agent framework designer.
* DevOps dan security engineer.

Tugas Anda adalah melakukan brainstorming mendalam dan menghasilkan blueprint implementasi untuk sistem AI agent vendor-netral yang dapat merancang, memeriksa, dan memperbaiki PCB berbasis Diode/Zener.

Ini adalah fase analisis dan desain. Jangan melakukan instalasi, menulis implementasi final, atau mengubah sistem pada fase ini.

## Konteks

Resource publik yang sudah dapat diverifikasi:

```text
Diode PCB:
https://github.com/diodeinc/pcb

Dokumentasi:
https://docs.pcb.new
```

Diode menyediakan:

* CLI `pcb`.
* Toolchain/compiler `pcbc`.
* Zener, bahasa schematic-as-code berbasis Starlark.
* Build dan validasi desain.
* Dependency/module management.
* Pembuatan file layout KiCad.
* Integrasi dengan KiCad 10.x untuk layout.

Nama berikut tidak boleh dianggap sebagai dependency karena belum tersedia sebagai resource publik yang dapat diverifikasi:

```text
Circuitforge
Zenforge
Zenpilot versi PCB
```

Namun konsep agent autonomous seperti yang dikaitkan dengan Zenpilot akan direalisasikan sendiri melalui:

```text
AI CLI
+ portable agent protocol
+ reusable AI skill
+ deterministic PCB harness
+ Diode compiler
+ KiCad CLI
+ acceptance tests
+ bounded iteration loop
```

## Keputusan awal pengguna

Pengguna ingin melewati fase smoke test manual yang terpisah.

Artinya:

* Jangan meminta pengguna membuat Blinky secara manual terlebih dahulu.
* Preflight, instalasi, dan smoke test harus menjadi bagian otomatis dari bootstrap dan test fixture.
* Sistem tetap wajib memiliki desain valid dan invalid sebagai pembuktian bahwa validator bekerja.
* Jangan menghapus validation gate hanya karena fase manual dilewati.

## Tujuan sistem

Rancang sistem yang nantinya dapat digunakan seperti:

```bash
pcb-agent doctor
pcb-agent init my-board
pcb-agent verify
pcb-agent run --backend codex "Buat board sensor suhu"
pcb-agent run --backend claude "Periksa dan perbaiki schematic"
pcb-agent run --backend gemini "Analisis kegagalan build"
pcb-agent report
```

Backend AI tidak boleh menjadi source of truth.

Source of truth harus terdiri dari:

```text
Specification
Acceptance criteria
Expected connectivity
Diode compiler result
Deterministic tests
KiCad DRC
Engineering review checklist
```

## Prinsip arsitektur

Sistem harus mempunyai tiga lapisan terpisah.

### Lapisan 1 — Deterministic PCB harness

Bertanggung jawab untuk:

* Environment detection.
* Dependency checks.
* Diode invocation.
* Build Zener.
* Dependency resolution.
* Connectivity validation.
* Specification validation.
* Layout generation.
* KiCad DRC.
* SPICE jika tersedia.
* Report generation.
* Exit code yang konsisten.

Lapisan ini harus dapat digunakan tanpa AI.

### Lapisan 2 — Portable agent protocol

Berisi aturan kerja yang dapat dibaca oleh AI CLI apa pun.

Contoh target:

```text
AGENT_PROTOCOL.md
SPEC.md atau SPEC.yaml
ACCEPTANCE.md
expected-connectivity.yaml
verify-report.json
```

Protocol harus menjelaskan:

* File yang boleh diubah.
* File yang tidak boleh diubah.
* Command verifikasi wajib.
* Maksimal iterasi.
* Kapan agent harus berhenti.
* Kapan harus meminta keputusan pengguna.
* Format laporan.
* Larangan memanipulasi acceptance test.

### Lapisan 3 — AI adapters dan skill

Adapter yang direncanakan:

```text
Codex CLI
Claude Code
Gemini CLI
Aider
Custom CLI
```

Skill `diode-pcb-agent` berfungsi sebagai panduan workflow dan domain knowledge, bukan sebagai compiler.

Skill tidak boleh memuat logic validasi penting yang hanya dapat diperiksa oleh AI. Logic kritis harus berada dalam script deterministik.

## Batasan fase brainstorming

Jangan:

* Menginstal package.
* Menggunakan `sudo`.
* Mengubah file sistem.
* Membuat repository final.
* Menjalankan AI CLI lain secara nested.
* Membuat skill final.
* Menganggap nama command CLI tanpa verifikasi.
* Mengarang kemampuan Diode.
* Mengarang output netlist, JSON, ERC, atau SPICE.
* Menganggap Diode menghasilkan `.kicad_sch`.
* Menganggap desain siap produksi jika berhasil compile.
* Menggunakan Circuitforge, Zenforge, atau Zenpilot sebagai dependency.
* Memesan atau mengirim PCB ke manufacturer.

Boleh melakukan:

* Membaca dokumentasi.
* Membaca source repository.
* Memeriksa current CLI help secara read-only jika tool sudah tersedia.
* Membandingkan alternatif arsitektur.
* Membuat pseudocode.
* Membuat struktur folder konseptual.
* Membuat schema konseptual.
* Mengidentifikasi eksperimen teknis yang dibutuhkan.

## Tahap 1 — Verifikasi fakta dan capability map

Pelajari dokumentasi dan source terbaru Diode.

Pisahkan semua temuan menjadi:

```text
VERIFIED
LIKELY BUT NOT VERIFIED
NOT AVAILABLE
REQUIRES EMPIRICAL TEST
```

Verifikasi minimal:

* OS yang didukung.
* Cara instalasi.
* Peran `pcb` dan `pcbc`.
* Format Zener.
* `pcb-version`.
* Command build.
* Command sync.
* Command layout.
* Apakah test command tersedia.
* Apakah simulation command tersedia.
* Apakah output machine-readable tersedia.
* Apakah netlist dapat diekspor.
* Apakah generated output mencakup `.kicad_pcb`.
* Apakah `.kicad_sch` dapat dihasilkan.
* Batas integrasi KiCad.
* Kemampuan KiCad CLI untuk DRC.
* Apakah ERC relevan jika tidak ada `.kicad_sch`.
* File yang dianggap source dan generated.
* Perilaku update/synchronization layout.

Jangan menyimpulkan fitur dari nama file saja. Berikan sumber untuk setiap klaim penting.

Buat capability matrix:

```text
Capability
Tool
Verified command/API
Input
Output
Machine-readable
Can run headless
Risks
Status
```

## Tahap 2 — Definisikan use case konkret

Gunakan minimal enam use case:

1. Membuat LED Blinky sederhana.
2. Membuat regulator 5 V ke 3,3 V.
3. Membuat sensor I²C dengan pull-up.
4. Menambahkan decoupling capacitor pada IC.
5. Memperbaiki pin yang salah atau floating.
6. Menganalisis kegagalan layout/DRC.

Tambahkan negative use cases:

1. Agent mengubah acceptance test agar lolos.
2. Agent memilih footprint yang tidak sesuai MPN.
3. Compiler lolos tetapi nilai komponen salah.
4. Layout tersedia tetapi routing belum selesai.
5. DRC tidak dapat dijalankan karena KiCad tidak tersedia.
6. Datasheet tidak ditemukan.
7. Model SPICE tidak tersedia.
8. AI CLI berhenti di tengah iterasi.
9. AI CLI menghasilkan output non-structured.
10. Agent berulang kali membuat perubahan yang sama.

Untuk setiap use case, jelaskan:

```text
Input
Expected behavior
Deterministic checks
AI judgment
Human judgment
Failure condition
Artifacts
```

## Tahap 3 — Tentukan boundary dan responsibility

Buat responsibility matrix untuk:

```text
User
AI CLI
Agent skill
PCB harness
Diode compiler
KiCad
SPICE
Datasheet
Human engineer
```

Gunakan kategori:

```text
Creates
Validates
Approves
May modify
Must not modify
```

Jawab secara eksplisit:

* Siapa yang membuat Zener?
* Siapa yang menentukan compile berhasil?
* Siapa yang memeriksa konektivitas?
* Siapa yang memeriksa kesesuaian datasheet?
* Siapa yang menentukan layout valid?
* Siapa yang dapat menyetujui fabrication?
* Apa yang tidak boleh diputuskan AI?

## Tahap 4 — Rancang repository utama

Evaluasi struktur berikut dan perbaiki bila diperlukan:

```text
pcb-ai-agent/
├── AGENT_PROTOCOL.md
├── AGENTS.md
├── CLAUDE.md
├── GEMINI.md
├── SPEC.md
├── ACCEPTANCE.md
├── pcb-agent
├── config/
│   ├── agents.toml
│   └── policies.toml
├── fixtures/
│   ├── valid-blinky/
│   ├── invalid-connectivity/
│   ├── invalid-value/
│   └── invalid-package/
├── scripts/
│   ├── bootstrap
│   ├── doctor
│   ├── build
│   ├── check-schematic
│   ├── generate-layout
│   ├── run-drc
│   ├── verify-all
│   ├── report
│   └── run-agent
├── prompts/
│   └── design-agent.md
├── schemas/
│   ├── specification.schema.json
│   ├── connectivity.schema.json
│   └── verification-report.schema.json
├── tests/
├── reports/
├── projects/
└── skill/
    └── diode-pcb-agent/
        ├── SKILL.md
        ├── agents/
        │   └── openai.yaml
        ├── scripts/
        ├── references/
        └── assets/
```

Tentukan:

* Apa yang harus berada di harness.
* Apa yang harus berada di skill.
* Apa yang board-specific.
* Apa yang reusable.
* Apa yang generated.
* Apa yang harus masuk `.gitignore`.
* Apa yang tidak boleh diduplikasi.
* Apakah skill sebaiknya berada di repository yang sama atau dipisahkan.

Skill tidak perlu mempunyai:

```text
README.md
INSTALLATION_GUIDE.md
QUICK_REFERENCE.md
CHANGELOG.md
```

Informasi skill harus dibagi melalui:

```text
SKILL.md
scripts/
references/
assets/
```

## Tahap 5 — Rancang command contract

Evaluasi interface berikut:

```bash
pcb-agent bootstrap
pcb-agent doctor
pcb-agent init <project>
pcb-agent build [project]
pcb-agent check schematic [project]
pcb-agent check spec [project]
pcb-agent check connectivity [project]
pcb-agent layout [project]
pcb-agent drc [project]
pcb-agent verify [project]
pcb-agent run --backend <backend> "<task>"
pcb-agent report [project]
pcb-agent clean --dry-run
```

Untuk setiap command, definisikan:

* Tujuan.
* Input.
* Output.
* Side effect.
* Exit code.
* Machine-readable output.
* Human-readable output.
* Idempotency.
* Prerequisite.
* Failure cases.
* Security concerns.

Usulkan exit-code contract yang konsisten, misalnya:

```text
0 = seluruh pemeriksaan wajib lolos
1 = validation failure
2 = dependency atau environment blocker
3 = invalid specification/configuration
4 = agent execution failure
5 = human decision required
```

Evaluasi apakah exit code tersebut cukup atau terlalu kompleks.

## Tahap 6 — Pilih teknologi implementasi harness

Bandingkan:

```text
Bash
Python
Rust
Node.js
Hybrid
```

Gunakan kriteria:

* Cross-platform.
* Kemudahan memanggil subprocess.
* Structured logging.
* JSON/YAML handling.
* Keamanan argument handling.
* Dependency footprint.
* Windows/WSL compatibility.
* Testing.
* Distribusi.
* Maintenance.
* Kemampuan integrasi AI CLI.

Berikan rekomendasi utama dan alternatif.

Pertimbangkan pendekatan:

```text
Python standard library untuk core
Shell/PowerShell hanya sebagai launcher tipis
```

Namun jangan memilihnya tanpa analisis.

## Tahap 7 — Rancang data contract

Usulkan schema untuk:

### Project specification

Contoh konseptual:

```yaml
project:
  name: sensor-board
  pcb_version: "0.4"
  layers: 4

power:
  input_voltage: 5V
  rails:
    - name: 3V3
      voltage: 3.3V

requirements:
  - id: REQ-001
    description: MCU harus memiliki decoupling capacitor
    severity: error
```

### Expected connectivity

```yaml
components:
  R1:
    kind: resistor
    value: 1kohm
    package: "0402"

nets:
  LED_ANODE:
    members:
      - R1.P2
      - D1.A
```

### Verification report

Contoh:

```json
{
  "status": "FAIL",
  "project": "sensor-board",
  "checks": [
    {
      "id": "DIODE_BUILD",
      "status": "PASS",
      "evidence": "...",
      "artifact": "reports/build.log"
    },
    {
      "id": "CONNECTIVITY",
      "status": "FAIL",
      "severity": "error",
      "message": "D1.A tidak terhubung ke LED_ANODE"
    }
  ],
  "human_review_required": true
}
```

Tentukan enum status resmi:

```text
PASS
FAIL
BLOCKED
SKIPPED
WARNING
HUMAN_REVIEW
```

Evaluasi apakah `WARNING` harus menjadi status atau severity.

Tentukan cara membedakan:

* Evidence faktual.
* Inference AI.
* Unverified claim.
* Human approval.

## Tahap 8 — Rancang schematic validation pyramid

Buat beberapa tingkat pemeriksaan:

### Level 1 — Syntax dan compiler

* Zener parsing.
* Module resolution.
* Dependency resolution.
* Board construction.
* Compiler exit code.

### Level 2 — Structural connectivity

* Component instances.
* Pin-to-net mapping.
* Power nets.
* Ground nets.
* Floating pins.
* Duplicate reference.
* Expected component count.

### Level 3 — Specification compliance

* Nilai komponen.
* Package.
* MPN.
* Voltage/current rating.
* Required functional blocks.
* Required test points.
* Required connector.

### Level 4 — Electrical engineering checks

* Decoupling.
* Pull-up/pull-down.
* LED resistor.
* Regulator stability requirements.
* Boot/reset pins.
* ESD protection.
* Power sequencing.
* Thermal estimates.

### Level 5 — Simulation

* SPICE availability.
* Model availability.
* Simulation scenario.
* Pass/fail threshold.

### Level 6 — Layout

* Layout generation.
* Board outline.
* Placement state.
* Routing state.
* KiCad DRC.
* Clearance.
* Unrouted connections.

### Level 7 — Human review

* Datasheet.
* Signal integrity.
* RF.
* EMI/EMC.
* Thermal.
* Mechanical.
* Manufacturing.
* Compliance.
* Fabrication approval.

Untuk setiap level, tentukan:

```text
Deterministic
Heuristic
AI-assisted
Human-only
Required
Optional
Evidence
```

Jelaskan secara khusus bagaimana schematic dapat diperiksa jika Diode tidak menghasilkan `.kicad_sch`.

## Tahap 9 — Rancang autonomy state machine

Gunakan state konseptual:

```text
INIT
DISCOVER
PLAN
EDIT
BUILD
VALIDATE
LAYOUT
REPORT
PASS
RETRY
BLOCKED
HUMAN_DECISION
```

Tentukan:

* Transisi antar-state.
* Maksimal lima iterasi.
* Kondisi retry.
* Kondisi stop.
* Kondisi rollback.
* Kapan perubahan harus di-commit.
* Cara mendeteksi loop tanpa progres.
* Cara membatasi jumlah file yang berubah.
* Cara mencegah agent mengubah acceptance test.
* Cara mencegah agent menonaktifkan validasi.
* Cara menangani timeout.
* Cara menangani AI CLI crash.
* Cara melanjutkan sesi.
* Cara menjaga reproducibility.

Berikan pseudocode agent loop.

Jangan menyarankan AI CLI memanggil dirinya sendiri dari sesi yang sedang aktif. Bedakan:

* Pengguna menjalankan `pcb-agent run`.
* `pcb-agent` memulai satu backend AI.
* Backend melakukan bounded task.
* Backend tidak memulai backend lain.
* Harness menjalankan validator sebagai subprocess biasa.

## Tahap 10 — Rancang backend adapter

Untuk setiap backend:

```text
Codex CLI
Claude Code
Gemini CLI
Aider
Custom
```

Analisis:

* Noninteractive invocation.
* Cara memberikan system/project instructions.
* Cara memberikan task.
* Workspace permission.
* Network permission.
* Output capture.
* Structured output.
* Exit code.
* Resume capability.
* Cost/token controls.
* Timeout.
* Model selection.
* Approval mechanism.
* Versi CLI.
* Risiko breaking change.

Gunakan adapter interface konseptual:

```python
class AgentBackend:
    def detect(self): ...
    def version(self): ...
    def prepare(self, task, workspace): ...
    def execute(self, task, workspace, timeout): ...
    def collect_result(self): ...
    def terminate(self): ...
```

Jangan hardcode flag sebelum membaca `--help` versi CLI yang terpasang.

Bahas risiko command injection. Task pengguna tidak boleh langsung digabungkan menjadi shell command string tanpa escaping atau argument array.

## Tahap 11 — Rancang skill `diode-pcb-agent`

Skill harus ringkas dan menggunakan progressive disclosure.

Usulkan:

```text
diode-pcb-agent/
├── SKILL.md
├── agents/
│   └── openai.yaml
├── scripts/
│   └── inspect-verification-report.py
├── references/
│   ├── zener-workflow.md
│   ├── schematic-review.md
│   ├── layout-review.md
│   └── failure-classification.md
└── assets/
    └── project-template/
```

Tentukan:

* Nama skill.
* Description yang membuat skill ter-trigger dengan benar.
* Workflow inti di `SKILL.md`.
* Kapan membaca masing-masing reference.
* Script yang benar-benar reusable.
* Template yang perlu disediakan.
* Informasi yang tidak boleh dimasukkan.
* Batas maksimum kebebasan agent.
* Bagaimana skill menemukan harness.
* Apa yang dilakukan jika `pcb-agent` belum terpasang.
* Bagaimana skill membedakan project Diode dan non-Diode.

Skill harus menginstruksikan agent untuk:

1. Baca specification.
2. Baca acceptance criteria.
3. Jalankan doctor.
4. Edit Zener.
5. Jalankan verify.
6. Baca structured report.
7. Perbaiki maksimal lima kali.
8. Jangan mengubah acceptance test.
9. Berhenti untuk human decision.
10. Jangan menyatakan siap produksi.

Jelaskan keterbatasan bahwa format skill tertentu tidak otomatis kompatibel dengan semua AI CLI. `AGENT_PROTOCOL.md` tetap harus menjadi portable source of truth.

## Tahap 12 — Security dan threat model

Analisis minimal:

* Malicious repository instructions.
* Prompt injection dari README/datasheet.
* Shell injection melalui nama project atau task.
* Secret exposure.
* Network exfiltration.
* Unsafe package installer.
* `curl | bash`.
* Dependency supply-chain.
* Untrusted component library.
* Generated file overwrite.
* Symlink traversal.
* Directory traversal.
* Recursive deletion.
* AI CLI nested execution.
* Infinite iteration.
* Unexpected API cost.
* Fabrication/order side effect.
* Agent mengubah test.
* Agent menyembunyikan DRC error.
* Log menyimpan credential.
* Backend membuka proxy ke jaringan.

Rekomendasikan kontrol:

```text
Workspace-only writes
Network off by default
Explicit network approval
Argument arrays
Path validation
Iteration limit
Timeout
Cost limit
Immutable acceptance files
Git diff inspection
Secret scan
Installer inspection
Version pinning
Dry-run cleanup
No manufacturing action
```

Buat threat matrix:

```text
Threat
Impact
Likelihood
Mitigation
Detection
Residual risk
```

## Tahap 13 — Cross-platform strategy

Bandingkan:

```text
Linux
macOS
Windows native
WSL2
```

Perhatikan:

* Diode native Windows eksperimental.
* KiCad GUI dan CLI.
* WSL path mapping.
* Executable discovery.
* Shell differences.
* Python launcher differences.
* File permissions.
* Line endings.
* Process termination.
* Signal handling.
* Script extensions.

Berikan rekomendasi platform utama dan tingkat dukungan:

```text
Tier 1
Tier 2
Experimental
Unsupported
```

## Tahap 14 — Test strategy

Rancang fixture:

```text
valid-blinky
invalid-syntax
invalid-module
invalid-connectivity
invalid-component-value
invalid-package
missing-ground
missing-decoupling
layout-unrouted
drc-clearance-error
missing-kicad
missing-spice-model
```

Untuk setiap fixture tentukan:

* Tujuan.
* Expected exit code.
* Expected report.
* Apakah membutuhkan Diode.
* Apakah membutuhkan KiCad.
* Apakah hanya unit test.
* Apakah integration test.
* Apakah end-to-end test.

Rancang test layers:

```text
Unit
Contract
Integration
End-to-end
Negative
Regression
Security
Cross-platform
```

Wajib ada test yang membuktikan bahwa:

* Desain valid diterima.
* Desain invalid ditolak.
* Acceptance file yang berubah terdeteksi.
* Backend crash ditangani.
* KiCad tidak tersedia menghasilkan `BLOCKED`, bukan false PASS.
* SPICE tidak tersedia menghasilkan `SKIPPED/BLOCKED` yang benar.
* Compile berhasil tidak otomatis menghasilkan status production-ready.

## Tahap 15 — Observability dan reporting

Rancang:

```text
Human-readable Markdown report
Machine-readable JSON report
Per-command log
Per-iteration log
Artifact manifest
Version manifest
```

Setiap report harus mencatat:

```text
Timestamp
OS
Tool versions
Project
Source commit
Specification hash
Acceptance hash
Command
Exit code
Duration
Status
Evidence
Artifact
Agent inference
Human review requirement
```

Hindari log:

```text
API key
Authorization header
Full environment dump
Sensitive home-directory contents
AI credential
```

## Tahap 16 — Implementation roadmap

Buat roadmap tanpa fase smoke-test manual terpisah.

Gunakan milestone konseptual:

### Milestone A — Architecture contract

* Command contract.
* Data schema.
* State machine.
* Threat model.
* Repository structure.

### Milestone B — Deterministic harness

* Bootstrap.
* Doctor.
* Build.
* Verify.
* Structured report.
* Valid dan invalid fixture.

### Milestone C — Diode/KiCad integration

* Zener build.
* Layout generation.
* DRC.
* Connectivity inspection.
* Capability detection.

### Milestone D — Generic agent protocol

* Portable instructions.
* Locked acceptance.
* Iteration contract.
* Human escalation.

### Milestone E — Backend pertama

* Pilih satu backend referensi.
* Adapter detection.
* Safe invocation.
* Timeout dan report.

### Milestone F — Skill

* SKILL.md.
* References.
* Reusable scripts.
* Template.
* Skill validation.

### Milestone G — Backend tambahan

* Claude Code.
* Gemini CLI.
* Aider.
* Custom adapter.

### Milestone H — Hardening

* Security tests.
* Cross-platform tests.
* Failure recovery.
* Documentation pengguna.

Untuk setiap milestone, berikan:

```text
Goal
Deliverables
Dependencies
Risks
Acceptance criteria
Estimated complexity
Can run in parallel
```

Jangan memberikan estimasi waktu yang tidak berdasar. Gunakan ukuran:

```text
Small
Medium
Large
Research spike
```

## Tahap 17 — Open questions dan research spikes

Identifikasi pertanyaan yang belum dapat dijawab tanpa eksperimen, misalnya:

* Apakah compiler menyediakan output netlist machine-readable?
* Bagaimana mengambil pin-to-net mapping?
* Apakah layout dapat dihasilkan headless?
* Apakah layout synchronization idempotent?
* Bagaimana DRC dijalankan pada KiCad 10?
* Apakah Diode menyediakan test framework?
* Apakah SPICE tersedia dan bagaimana model dipasangkan?
* Apa perbedaan output antar-OS?
* Backend AI mana yang mempunyai structured output stabil?

Untuk setiap pertanyaan, buat research spike:

```text
Question
Why it matters
Minimal experiment
Expected artifact
Success criterion
Failure fallback
```

## Tahap 18 — Bandingkan alternatif arsitektur

Bandingkan minimal:

### Alternatif A

Skill-centric:

```text
AI Skill → langsung menjalankan Diode/KiCad
```

### Alternatif B

Harness-centric:

```text
AI CLI → portable protocol → deterministic harness
```

### Alternatif C

Service architecture:

```text
AI CLI → local API/service → Diode/KiCad workers
```

Bandingkan:

* Portability.
* Security.
* Complexity.
* Testability.
* Reproducibility.
* Offline capability.
* Maintenance.
* Multi-user use.
* CI integration.
* Debuggability.

Berikan rekomendasi dan jelaskan alasan teknisnya.

## Pertanyaan brainstorming utama

Jawab dengan konkret:

1. Apakah `pcb-agent` sebaiknya CLI Python, Rust, atau hybrid?
2. Apakah AI backend sebaiknya dipanggil oleh harness atau pengguna?
3. Bagaimana mencegah recursive/nested agent?
4. Bagaimana menjaga adapter tetap kompatibel ketika CLI berubah?
5. Bagaimana mengunci acceptance test tanpa membuat workflow menyulitkan?
6. Bagaimana memeriksa schematic-as-code tanpa schematic grafis?
7. Bagaimana memperoleh konektivitas dari compiler secara terpercaya?
8. Bagaimana membedakan compiler validation dan engineering correctness?
9. Kapan status harus `FAIL`, `BLOCKED`, atau `SKIPPED`?
10. Bagaimana memastikan laporan menyertakan evidence?
11. Bagaimana skill digunakan jika harness belum terpasang?
12. Apakah skill dan harness harus berada dalam satu repository?
13. Apa MVP minimum yang masih mempunyai nilai engineering?
14. Apa fitur yang harus sengaja ditunda?
15. Bagaimana memastikan sistem tidak pernah menyatakan fabrication-ready secara otomatis?

## Format output wajib

Susun hasil brainstorming dengan struktur:

```text
1. Executive summary
2. Verified facts
3. Assumptions and unknowns
4. Recommended architecture
5. Alternative architectures
6. Component responsibility matrix
7. Repository structure
8. Command contract
9. Data contract
10. Autonomy state machine
11. Schematic validation strategy
12. Layout and DRC strategy
13. AI backend adapter strategy
14. Skill design
15. Security threat model
16. Cross-platform strategy
17. Test strategy
18. Observability and reporting
19. Research spikes
20. Implementation roadmap
21. Deferred features
22. Decision log
23. Final recommendation
24. Questions requiring user decision
```

Gunakan:

* Tabel untuk perbandingan dan responsibility matrix.
* Mermaid untuk architecture dan state machine.
* Pseudocode untuk agent loop.
* Contoh JSON/YAML untuk data contract.
* Status `VERIFIED`, `ASSUMPTION`, `UNKNOWN`, atau `REQUIRES TEST` pada klaim teknis.

## Kriteria keberhasilan brainstorming

Brainstorming dianggap selesai jika:

* Arsitektur tidak bergantung pada satu AI CLI.
* Harness dapat berjalan tanpa AI.
* Skill bukan tempat validation logic utama.
* Capability Diode dipisahkan antara fakta dan asumsi.
* Schematic validation memiliki evidence yang jelas.
* Layout DRC tidak disamakan dengan schematic validation.
* Compile success tidak disamakan dengan engineering correctness.
* Ada positive dan negative fixtures.
* Ada state machine dengan iteration limit.
* Ada threat model.
* Ada data contract machine-readable.
* Ada strategi cross-platform.
* Ada research spikes untuk unknown.
* Ada roadmap implementasi.
* Tidak ada dependency Circuitforge, Zenforge, atau Zenpilot.
* Tidak ada instalasi atau perubahan sistem selama fase brainstorming.

## Perilaku akhir

Jangan langsung mengimplementasikan hasil brainstorming.

Akhiri dengan:

1. Rekomendasi arsitektur utama.
2. Lima keputusan terpenting.
3. Daftar unknown yang harus diuji.
4. Scope MVP yang disarankan.
5. Maksimal lima pertanyaan yang benar-benar membutuhkan keputusan pengguna.
6. Prompt implementasi berikutnya dalam bentuk outline saja, bukan implementasi penuh.
