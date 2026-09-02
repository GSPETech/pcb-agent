# Routing Agent

Parse `kicad-drc.json`, diagnose violation types (clearance, track_width, stub,
annular_ring), apply targeted fixes, loop repair sampai KICAD_DRC PASS.

## Input contract

```json
{
  "project_dir": "/absolute/path",
  "board_file": "build/board.kicad_pcb",
  "profile": "layout"
}
```

## Output contract

```json
{
  "status": "PASS | FAIL",
  "checks": {
    "KICAD_DRC": "PASS"
  },
  "violations_fixed": 12,
  "iterations": 4,
  "message": "12 clearance violations fixed, DRC clean",
  "fingerprint": "sha256:ghi..."
}
```

## Workflow

```
1. Run: pcb-agent verify --project <dir> --profile layout --format json
   (gates LAYOUT_GENERATE..LAYOUT_SYNC assumed PASS dari layout-agent)
2. Parse result["checks"]["KICAD_DRC"]
3. If FAIL:
   - Baca artifact kicad-drc.json
   - Group violations by type: clearance / track_width / drill / stub / annular_ring
   - Diagnose root cause per group
   - Apply fix strategy
4. Fingerprint: violation count per type
5. iteration++, goto 1
6. If PASS: return output JSON
```

## Loop bound

Max 5 iterations. Iteration 6 → escalate HUMAN_REVIEW.

## Fingerprint anti-stuck

```python
import json, hashlib
drc = json.load(open("reports/.../raw/kicad-drc.json"))
violation_counts = {}
for v in drc.get("violations", []):
    vtype = v.get("type", "unknown")
    violation_counts[vtype] = violation_counts.get(vtype, 0) + 1

fp = hashlib.sha256()
fp.update(json.dumps(violation_counts, sort_keys=True).encode())
fingerprint = fp.hexdigest()
```

Kalau fingerprint sama 2× berturut-turut = fix tidak efektif, escalate
HUMAN_REVIEW.

## Violation types & fix strategy

| Type | Root cause | Fix |
|---|---|---|
| `clearance` | track too close | widen clearance di design rules, re-route |
| `track_width` | trace too narrow for current | edit project.toml track_width, re-route |
| `drill_out_of_range` | via drill < manufacturer min | edit via size di design rules |
| `annular_ring_too_small` | pad too small for drill | increase pad size di footprint atau decrease drill |
| `dangling_track` | stub > λ/10 | rip-up stub segment, re-route to pad center |
| `starved_thermal` | thermal relief spoke < min | widen thermal spoke di zone settings |
| `copper_sliver` | acute angle fill | adjust zone fill strategy (solid → hatched) |

## DRC JSON structure

```json
{
  "violations": [
    {
      "type": "clearance",
      "description": "Clearance violation between track and pad",
      "severity": "error",
      "items": [
        {"uuid": "...", "pos": {"x": 120.5, "y": 85.2}}
      ]
    }
  ],
  "unconnected_items": []
}
```

## Repair actions

### clearance violation

1. Parse affected net from violation UUID
2. Read current clearance rule untuk net class
3. Increase clearance +0.05mm
4. Write updated design rules ke project.toml
5. Re-run `pcb layout` (trigger re-route)

### track_width violation

1. Parse net name
2. Classify: power net (VDD*, GND) vs signal
3. Increase track_width: power +0.1mm, signal +0.05mm
4. Write project.toml
5. Re-route

### stub (dangling_track)

1. Parse track segment UUID
2. Load .kicad_pcb via `pcbnew` Python
3. Find segment, check endpoints
4. If one endpoint not on pad: delete segment
5. Save .kicad_pcb
6. Re-run LAYOUT_SYNC

### annular_ring

1. Parse via UUID
2. Read drill size, compute pad size needed (drill + 2×min_annular)
3. Edit footprint via size
4. Re-generate layout

## Prerequisites

```python
import pcbnew  # KiCad Python binding
```

Kalau import fail → return BLOCKED.

## Escalation trigger

| Condition | Action |
|---|---|
| `kicad-cli` not found | return BLOCKED |
| `pcbnew` import fail | return BLOCKED |
| iteration > 5 | return HUMAN_REVIEW |
| fingerprint stuck 2× | return HUMAN_REVIEW |
| violation count increase | return HUMAN_REVIEW (regression) |

## Example interaction

Input:
```json
{
  "project_dir": "/tmp/gps_tracker",
  "board_file": "build/board.kicad_pcb",
  "profile": "layout"
}
```

Iteration 1:
- Run verify → KICAD_DRC FAIL (12 violations)
- Parse kicad-drc.json:
  - 8× clearance (track-to-track 0.15mm, rule 0.2mm)
  - 3× track_width (0.15mm, min 0.2mm)
  - 1× dangling_track (stub 2mm)

Iteration 2:
- Increase clearance 0.2mm → 0.25mm
- Increase track_width default 0.2mm → 0.22mm
- Write project.toml, re-route
- Run verify → KICAD_DRC FAIL (1 violation: stub masih ada)

Iteration 3:
- Load .kicad_pcb via pcbnew
- Delete stub segment UUID ...
- Save, re-sync
- Run verify → PASS

Return:
```json
{
  "status": "PASS",
  "checks": {"KICAD_DRC": "PASS"},
  "violations_fixed": 12,
  "iterations": 3,
  "message": "12 violations fixed (8 clearance, 3 track_width, 1 stub)"
}
```

ponytail: no impedance-controlled routing, no length matching, no diff-pair
tuning. Add when high-speed SerDes needed.
