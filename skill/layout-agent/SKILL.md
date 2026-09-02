# Layout Agent

Run `pcb-agent verify --profile layout`, parse PLACEMENT/ROUTE/KICAD_DRC
failures, adjust constraints atau design rules, loop repair sampai PASS.

## Input contract

```json
{
  "project_dir": "/absolute/path",
  "profile": "layout",
  "constraints": {
    "board_outline": {"width": 50, "height": 30, "unit": "mm"},
    "placement_hint": "GPS module top-left, USB bottom edge center",
    "layer_count": 2,
    "track_width": {"default": 0.2, "power": 0.5, "unit": "mm"},
    "clearance": {"default": 0.2, "unit": "mm"}
  }
}
```

## Output contract

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
  "message": "placement deterministic, freerouting PASS",
  "fingerprint": "sha256:def..."
}
```

## Workflow

```
1. Write project.toml [layout] section dengan constraints
2. Run: pcb-agent verify --project <dir> --profile layout --format json
3. Parse JSON result
4. If LAYOUT_GENERATE FAIL:
   - Parse diode_layout.json stderr
   - Diagnose: footprint missing / courtyard overlap
   - Edit project.toml footprint mapping atau adjust spacing
5. If PLACEMENT FAIL:
   - Parse placement.json
   - Diagnose: courtyard collision / board too small
   - Adjust board_outline atau component grouping
6. If ROUTE FAIL:
   - Parse freerouting.json
   - Diagnose: unrouted nets / DRC spacing
   - Widen clearance atau track_width, re-run
7. If LAYOUT_SYNC FAIL:
   - Parse layout_sync.json
   - Fix: re-generate kicad_pcb (should be idempotent)
8. Fingerprint checks
9. iteration++, goto 2
10. If PASS: return output JSON
```

## Loop bound

Max 5 iterations. Iteration 6 → escalate HUMAN_REVIEW.

## Fingerprint anti-stuck

```python
fp = hashlib.sha256()
fp.update(result["status"].encode())
for gate in ["LAYOUT_GENERATE", "PLACEMENT", "ROUTE", "LAYOUT_SYNC"]:
    fp.update(f"{gate}:{result['checks'][gate]['status']}".encode())
fingerprint = fp.hexdigest()
```

## Repair strategy per gate

| Gate | Failure | Fix |
|---|---|---|
| LAYOUT_GENERATE | footprint not found | add footprint library path di project.toml |
| LAYOUT_GENERATE | courtyard overlap | increase component spacing constraint |
| PLACEMENT | board too small | increase board_outline width/height |
| PLACEMENT | group collision | adjust placement_hint grouping |
| ROUTE | unrouted nets | widen clearance, increase track_width |
| ROUTE | DRC spacing | same as unrouted |
| LAYOUT_SYNC | .kicad_pcb mismatch | re-run `pcb layout --check` (should auto-fix) |

## Prerequisites probe

Sebelum run, cek:

```bash
command -v freerouting || return BLOCKED "freerouting not found"
python3 -c "import pcbnew" || return BLOCKED "pcbnew Python binding not found"
pcb --version | grep 0.4.40 || return BLOCKED "pcb version != 0.4.40"
```

## Determinisme placement

PLACEMENT deterministik: dua run pada netlist identik → Edge.Cuts identik
byte-per-byte. Kalau hasil berbeda = bug di harness, bukan failure mode yang
bisa di-repair.

## Determinisme routing

Freerouting 2.3.0 deterministik: dua run pada DSN identik → SES identik. Kalau
berbeda = environment issue (Java version, locale), bukan design issue.

## Escalation trigger

| Condition | Action |
|---|---|
| `freerouting` not found | return BLOCKED |
| `pcbnew` import fail | return BLOCKED |
| `pcb` version != 0.4.40 | return BLOCKED |
| iteration > 5 | return HUMAN_REVIEW |
| fingerprint stuck 2× | return HUMAN_REVIEW |
| LAYOUT_GENERATE BLOCKED | return BLOCKED |

## Example interaction

Input:
```json
{
  "project_dir": "/tmp/gps_tracker",
  "profile": "layout",
  "constraints": {"board_outline": {"width": 50, "height": 30, "unit": "mm"}}
}
```

Iteration 1:
- Write project.toml [layout]
- Run verify → PLACEMENT FAIL (board 48mm computed, constraint 50mm OK, but courtyard overlap)

Iteration 2:
- Parse placement.json → "U1 courtyard overlaps C1"
- Edit project.toml → increase component spacing 2mm → 3mm
- Run verify → ROUTE FAIL (3 nets unrouted)

Iteration 3:
- Parse freerouting stderr → "clearance 0.2mm too tight"
- Edit project.toml → clearance 0.15mm
- Run verify → PASS

Return:
```json
{
  "status": "PASS",
  "checks": {"LAYOUT_GENERATE": "PASS", "PLACEMENT": "PASS", "ROUTE": "PASS", "LAYOUT_SYNC": "PASS"},
  "iterations": 3,
  "message": "layout verified, 3 iterations"
}
```

ponytail: no manual placement override, no keepout zones, no teardrops. Add
when high-speed design needed.
