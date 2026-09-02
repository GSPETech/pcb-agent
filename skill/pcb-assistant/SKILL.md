# PCB Assistant (Orchestrator)

Delegate high-level PCB design tasks ke specialized agents. Coordinate
schematic → layout → routing loop sampai PASS atau escalate BLOCKED/HUMAN_REVIEW.

## Trigger

User prompt: "buat schematic GPS", "design PCB untuk LoRa node", "routing board
ini", "fix DRC violation".

## Workflow

```
User request
  ↓ parse intent (schematic-only / full board / routing-only)
  ↓
schematic-agent
  ├─ tulis .zen + tests/<name>.zen
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
  ├─ diagnose violation (clearance/track_width/stub/annular_ring)
  ├─ apply fix (widen track, move via, rip-up+reroute)
  └─ loop repair sampai KICAD_DRC PASS
  ↓ (PASS)
return summary: "schematic PASS, layout PASS, DRC PASS. Ready for review."
```

## Sub-agent contracts

### schematic-agent input

```json
{
  "project_dir": "/absolute/path/to/project",
  "module_name": "GPS_MODULE",
  "requirements": [
    "GPS receiver U-blox MAX-M10S",
    "USB-C untuk power",
    "LED indikator GPS lock"
  ],
  "profile": "schematic"
}
```

### schematic-agent output

```json
{
  "status": "PASS | FAIL | BLOCKED | HUMAN_REVIEW",
  "checks": {
    "CONTRACT": "PASS",
    "DIODE_BUILD": "PASS",
    "CONNECTIVITY": "PASS",
    "SPECIFICATION": "PASS"
  },
  "iterations": 3,
  "files_written": ["src/gps_module.zen", "tests/gps_test.zen"],
  "message": "schematic verified, connectivity PASS"
}
```

### layout-agent input

```json
{
  "project_dir": "/absolute/path/to/project",
  "profile": "layout",
  "constraints": {
    "board_outline": {"width": 50, "height": 30, "unit": "mm"},
    "placement_hint": "GPS module top-left, USB bottom edge center",
    "layer_count": 2
  }
}
```

### layout-agent output

```json
{
  "status": "PASS | BLOCKED",
  "checks": {
    "LAYOUT_GENERATE": "PASS",
    "PLACEMENT": "PASS",
    "ROUTE": "PASS",
    "LAYOUT_SYNC": "PASS"
  },
  "iterations": 2,
  "message": "placement done, freerouting PASS"
}
```

### routing-agent input

```json
{
  "project_dir": "/absolute/path/to/project",
  "board_file": "build/board.kicad_pcb",
  "profile": "layout"
}
```

### routing-agent output

```json
{
  "status": "PASS | FAIL",
  "checks": {
    "KICAD_DRC": "PASS"
  },
  "violations_fixed": 12,
  "iterations": 4,
  "message": "12 clearance violations fixed, DRC clean"
}
```

## Escalation rules

| Sub-agent status | Action |
|---|---|
| PASS | proceed ke agent berikutnya |
| FAIL (iterations < 5) | sub-agent loop sendiri |
| FAIL (iterations >= 5) | escalate HUMAN_REVIEW, stop orchestrator |
| BLOCKED (pcb not found) | stop, return BLOCKED ke user |
| BLOCKED (version mismatch) | stop, return BLOCKED ke user |
| HUMAN_REVIEW | stop, return HUMAN_REVIEW ke user |

## Intent detection

| User prompt | Delegate to |
|---|---|
| "buat schematic X" | schematic-agent only |
| "design PCB X" | schematic → layout → routing |
| "fix DRC" | routing-agent only (existing board) |
| "improve placement" | layout-agent only (re-run PLACEMENT) |
| "verify project" | all three (full gate cascade) |

## Loop bound

Orchestrator tidak loop sendiri. Sub-agent loop sampai PASS atau max 5
iteration. Orchestrator hanya run setiap sub-agent **sekali** per phase.

## Output ke user

```
Schematic: PASS (3 iterations)
  - GPS_MODULE.zen written
  - CONNECTIVITY verified
  - SPECIFICATION verified

Layout: PASS (2 iterations)
  - Placement completed
  - Freerouting PASS

Routing: PASS (4 iterations)
  - 12 DRC violations fixed
  - KICAD_DRC clean

Status: Ready for review. fabrication_approved=false (human review required).
```

## Implementation notes

Orchestrator **tidak** baca `.zen` atau contract langsung. Sub-agent handle
semua file I/O dan `pcb-agent verify` call. Orchestrator hanya:

1. Parse user intent → phase sequence
2. Construct input JSON untuk sub-agent
3. Invoke sub-agent via Task tool
4. Parse output JSON
5. Decide: proceed, escalate, atau stop
6. Return summary ke user

ponytail: no telemetry logging, no checkpoint serialization. Add when
multi-board batch processing needed.
