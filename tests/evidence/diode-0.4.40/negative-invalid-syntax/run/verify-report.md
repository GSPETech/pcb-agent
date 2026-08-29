# PCB Verification Report

> **Verification PASS does not mean production-ready. Fabrication requires review and approval by a human engineer.**

- Project: `invalid-syntax`
- Status: **BLOCKED**
- Production ready: **false**
- Fabrication approved: **false**
- Timestamp: `2026-08-29T03:27:47.167712+00:00`

## Checks

| ID | Status | Severity | Required | Message |
|---|---|---|---:|---|
| `CONTRACT` | PASS | error | true | project contracts loaded and hashed |
| `DIODE_BUILD` | FAIL | error | true | command exited 1 |
| `ZENER_TEST` | BLOCKED | error | true | Diode build did not pass |
| `CONNECTIVITY` | BLOCKED | error | true | Diode build did not pass |
| `SPECIFICATION` | BLOCKED | error | true | Diode build did not pass |
| `LAYOUT_GENERATE` | SKIPPED | error | false | layout profile not active |
| `LAYOUT_SYNC` | SKIPPED | error | false | layout profile not active |
| `KICAD_DRC` | SKIPPED | error | false | layout profile not active |
| `SIMULATION` | SKIPPED | error | false | simulation is not implemented |
