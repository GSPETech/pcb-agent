# PCB Agent Coordination Test

Test orchestrator dengan fixture `valid-blinky`.

## Blocker saat ini

**Toolchain `pcb` belum terinstall di WSL** → DIODE_BUILD BLOCKED.

Windows native `pcb build` gagal symlink privilege (os error 1314). Harness
butuh WSL + toolchain `pcb 0.4.40` terinstall.

## Setup yang dibutuhkan (satu kali)

```bash
# Di WSL Ubuntu-24.04
curl -sSL https://install.diode.io | bash
pcb toolchain install 0.4.40

# Buat shim yang pin versi
mkdir -p /tmp/pcbshim
printf '#!/bin/bash\nexec "$HOME/.local/bin/pcb" +0.4.40 "$@"\n' > /tmp/pcbshim/pcb
chmod +x /tmp/pcbshim/pcb
export PATH="/tmp/pcbshim:$PATH"

# Verifikasi
pcb --version  # harus cetak "pcbc 0.4.40"
```

## Setelah toolchain ready

```bash
# Test schematic-agent secara langsung
cd /mnt/c/Users/jrjua/diodeinc
python3 -m pcb_agent.cli verify --project fixtures/valid-blinky --profile schematic --format json

# Expected: CONTRACT PASS, DIODE_BUILD PASS, CONNECTIVITY PASS, SPECIFICATION PASS
```

## Skill orchestrator yang sudah dibuat

| Skill | Status | Path |
|---|---|---|
| `pcb-assistant` | ✅ written | `skill/pcb-assistant/SKILL.md` |
| `schematic-agent` | ✅ written | `skill/schematic-agent/SKILL.md` |
| `layout-agent` | ✅ written | `skill/layout-agent/SKILL.md` |
| `routing-agent` | ✅ written | `skill/routing-agent/SKILL.md` |

Semua 4 skill sudah lengkap dengan:
- Input/output contract (JSON dict)
- Loop repair dengan fingerprint anti-stuck
- Escalation trigger (BLOCKED vs HUMAN_REVIEW)
- Exit code semantics sesuai `AGENT_PROTOCOL.md`

## Next step setelah toolchain ready

1. Verifikasi `valid-blinky` PASS di WSL
2. Test orchestrator: user prompt → `pcb-assistant` → delegate → schematic-agent → PASS
3. Buat fixture GPS sederhana untuk test end-to-end (schematic → layout → routing)
4. Commit & push implementasi koordinasi

## Arsitektur koordinasi yang diimplementasikan

```
User: "buat schematic GPS tracker"
  ↓
pcb-assistant (orchestrator)
  ↓
schematic-agent
  ├─ tulis GPS_MODULE.zen
  ├─ tulis tests/gps_test.zen
  ├─ verify --profile schematic
  └─ loop repair sampai CONNECTIVITY + SPECIFICATION PASS
  ↓ (PASS)
layout-agent
  ├─ verify --profile layout
  ├─ parse PLACEMENT/ROUTE failure
  └─ adjust constraint, loop repair
  ↓ (PASS)
routing-agent
  ├─ parse kicad-drc.json
  ├─ diagnose violation (clearance/track_width/stub)
  ├─ apply targeted fix (move track, widen, rip-up+reroute)
  └─ loop repair sampai KICAD_DRC PASS
  ↓ (PASS)
return ke user: "Ready for review, fabrication_approved=false"
```

Semua sub-agent bounded (max 5 iteration), fingerprint-tracked (anti infinite
loop), escalate BLOCKED/HUMAN_REVIEW ke orchestrator, orchestrator stop
immediately on first non-PASS dari sub-agent.
