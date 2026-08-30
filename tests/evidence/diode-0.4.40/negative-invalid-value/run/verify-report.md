# PCB Verification Report

> **Verification PASS does not mean production-ready. Fabrication requires review and approval by a human engineer.**

- Project: `invalid-value`
- Status: **BLOCKED**
- Production ready: **false**
- Fabrication approved: **false**
- Timestamp: `2026-08-29T20:22:21.126801+00:00`

## Checks

| ID | Status | Severity | Required | Message |
|---|---|---|---:|---|
| `CONTRACT` | PASS | error | true | project contracts loaded and hashed |
| `DIODE_BUILD` | PASS | error | true | command exited 0 |
| `ZENER_TEST` | FAIL | error | true | command exited 1 |
| `CONNECTIVITY` | BLOCKED | error | true | locked Zener TestBench did not pass; connectivity was not verified |
| `SPECIFICATION` | BLOCKED | error | true | locked Zener TestBench did not pass; specification was not verified |
| `LAYOUT_GENERATE` | SKIPPED | error | false | layout profile not active |
| `LAYOUT_SYNC` | SKIPPED | error | false | layout profile not active |
| `KICAD_DRC` | SKIPPED | error | false | layout profile not active |
| `SIMULATION` | SKIPPED | error | false | simulation is not implemented |
