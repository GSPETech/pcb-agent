# PCB Verification Report

> **Verification PASS does not mean production-ready. Fabrication requires review and approval by a human engineer.**

- Project: `dwm1004c-aptwr-tag`
- Status: **FAIL**
- Production ready: **false**
- Fabrication approved: **false**
- Timestamp: `2026-09-01T17:07:38.402464+00:00`

## Checks

| ID | Status | Severity | Required | Message |
|---|---|---|---:|---|
| `CONTRACT` | PASS | error | true | project contracts loaded and hashed |
| `DIODE_BUILD` | PASS | error | true | command exited 0 |
| `ZENER_TEST` | PASS | error | true | command exited 0 |
| `CONNECTIVITY` | PASS | error | true | connectivity generated assertion passed |
| `SPECIFICATION` | PASS | error | true | specification generated assertion passed |
| `LAYOUT_GENERATE` | PASS | error | true | command exited 0 |
| `PLACEMENT` | PASS | error | true | placed 72 footprints; board 63.32 x 89.38 mm |
| `ROUTE` | PASS | error | true | routed 361 wires and 95 vias |
| `LAYOUT_SYNC` | FAIL | error | true | command exited 1 |
| `KICAD_DRC` | FAIL | error | true | KiCad DRC found violations |
| `SIMULATION` | SKIPPED | error | false | simulation is not implemented |
