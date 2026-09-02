# Schematic Agent

Write `.zen` source + locked TestBench, verify dengan `pcb-agent verify --profile
schematic`, loop repair sampai CONNECTIVITY + SPECIFICATION PASS.

## Input contract

```json
{
  "project_dir": "/absolute/path",
  "module_name": "GPS_MODULE",
  "requirements": [
    "GPS receiver U-blox MAX-M10S",
    "USB-C untuk power",
    "LED indikator GPS lock"
  ],
  "profile": "schematic"
}
```

## Output contract

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
  "message": "schematic verified, connectivity PASS",
  "fingerprint": "sha256:abc..."
}
```

## Workflow

```
1. Parse requirements → component list + nets
2. Write src/<module>.zen
3. Write SPEC.json (REQ-001: "GPS receiver present", ...)
4. Write tests/<module>_test.zen (locked TestBench)
5. Write ACCEPTANCE.json (ACC-001 → REQ-001)
6. Write expected-connectivity.json
7. Write project.toml (profile schematic, test path)
8. Run: pcb-agent verify --project <dir> --profile schematic --format json
9. Parse JSON result
10. If FAIL:
    - Baca report artifacts (diode_build.json, connectivity_check.json)
    - Diagnose: syntax error / missing component / wrong net
    - Edit .zen
    - Fingerprint = hash(status + checks.keys + message)
    - If fingerprint == last_fingerprint: stuck, escalate HUMAN_REVIEW
    - iteration++, goto 8
11. If BLOCKED: return BLOCKED ke orchestrator
12. If PASS: return output JSON
```

## Loop bound

Max 5 iterations. Iteration 6 → escalate HUMAN_REVIEW.

## Fingerprint anti-stuck

```python
import hashlib
fp = hashlib.sha256()
fp.update(result["status"].encode())
fp.update(",".join(sorted(result["checks"].keys())).encode())
fp.update(result["checks"]["DIODE_BUILD"]["message"].encode())
fingerprint = fp.hexdigest()

if fingerprint == last_fingerprint:
    return {"status": "HUMAN_REVIEW", "message": "stuck after edit"}
```

## Component library yang supported

resistor, capacitor, led, inductor, ferrite_bead, thermistor, zener, rectifier,
tvs. IC/konektor/switch → BLOCKED (no adapter). Cek dulu `component.type` via
probe sebelum tulis contract:

```python
def probe(module, inputs):
    for key, comp in sorted(module.components().items()):
        print(f"{key} type={comp.type}")
    check(False, "probe to see types")
```

## Nama net yang valid

`[A-Za-z][A-Za-z0-9_-]*`. Rename hasil `pcb import`:

| Bad | Good |
|---|---|
| `+3_3V` | `VDD_3V3` |
| `IMU_XTAL+` | `IMU_XTAL_P` |
| `Net-(U1-VOUT)` | `NET_U1_VOUT` |
| `/IMU/BNO_SCL` | `IMU_BNO_SCL` |

## Repair strategy per gate

| Gate | Failure mode | Fix |
|---|---|---|
| CONTRACT | file missing | write missing file |
| DIODE_BUILD | syntax error | parse stderr → edit .zen |
| DIODE_BUILD | unknown component | check `component.type` → remove atau ganti kind |
| CONNECTIVITY | net mismatch | edit expected-connectivity.json atau .zen |
| SPECIFICATION | constraint fail | edit SPEC.json atau .zen (change value) |

## Escalation trigger

| Condition | Action |
|---|---|
| `pcb` not found | return BLOCKED |
| version != 0.4.40 | return BLOCKED |
| iteration > 5 | return HUMAN_REVIEW |
| fingerprint stuck 2× | return HUMAN_REVIEW |
| any gate status BLOCKED | return BLOCKED |

## Example interaction

User (via orchestrator):
```json
{
  "project_dir": "/tmp/gps_tracker",
  "module_name": "GPS_MODULE",
  "requirements": ["GPS MAX-M10S", "USB-C power", "LED lock indicator"]
}
```

Agent iteration 1:
- Write `src/gps_module.zen` (GPS module + USB + LED + resistor)
- Write `tests/gps_test.zen` (check 4 components exist)
- Write contracts
- Run verify → CONNECTIVITY FAIL (net name invalid `+5V`)

Agent iteration 2:
- Parse connectivity_check.json → "net +5V contains invalid character"
- Edit `src/gps_module.zen` → rename `+5V` → `VDD_5V`
- Run verify → SPECIFICATION FAIL (LED current > 20mA)

Agent iteration 3:
- Parse spec.json → "REQ-003: LED current < 20mA"
- Edit `src/gps_module.zen` → R1 resistance 1kohm → 2.2kohm
- Run verify → PASS

Return:
```json
{
  "status": "PASS",
  "checks": {"CONTRACT": "PASS", "DIODE_BUILD": "PASS", "CONNECTIVITY": "PASS", "SPECIFICATION": "PASS"},
  "iterations": 3,
  "files_written": ["src/gps_module.zen", "tests/gps_test.zen", "SPEC.json", "ACCEPTANCE.json", "expected-connectivity.json", "project.toml"],
  "message": "schematic verified, 3 iterations"
}
```

ponytail: no BOM generation, no multi-sheet schematic. Add when hierarchical
design needed.
