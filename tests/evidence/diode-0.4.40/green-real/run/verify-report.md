# PCB Verification Report

> **Verification PASS does not mean production-ready. Fabrication requires review and approval by a human engineer.**

- Project: `green-real`
- Status: **PASS**
- Production ready: **false**
- Fabrication approved: **false**
- Timestamp: `2026-08-29T14:30:17.783393+00:00`

## Checks

| ID | Status | Severity | Required | Message |
|---|---|---|---:|---|
| `CONTRACT` | PASS | error | true | project contracts loaded and hashed |
| `DIODE_BUILD` | PASS | error | true | command exited 0 |
| `ZENER_TEST` | PASS | error | true | command exited 0 |
| `CONNECTIVITY` | PASS | error | true | connectivity generated assertion passed |
| `SPECIFICATION` | PASS | error | true | specification generated assertion passed |
| `LAYOUT_GENERATE` | SKIPPED | error | false | layout profile not active |
| `LAYOUT_SYNC` | SKIPPED | error | false | layout profile not active |
| `KICAD_DRC` | SKIPPED | error | false | layout profile not active |
| `SIMULATION` | SKIPPED | error | false | simulation is not implemented |
