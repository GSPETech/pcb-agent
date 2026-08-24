# Real Integration Results

Date: 2026-08-24

## Installed Tools

- Windows Diode installer snapshot: `ee4e7e2b90fbe5f787d165a0780eba42664449ab`
- Windows installer SHA-256: `817aca9888b910a72c72d5eb5f2ad3d0b6fdf576448ab0eea06cd77c3d050986`
- WSL installer SHA-256: `cbd878d54d1cb01377eba95fb98402a6240f956559d16a8e87220126061c4c85`
- Diode: `pcbc 0.4.34`, shim `0.2.6`
- KiCad CLI runtime: `10.0.3`

## Diode Fixtures

| Fixture | Build | Test | Result |
|---|---|---|---|
| `valid-blinky` | PASS, 2 components | PASS, 2/2 checks | PASS |
| `invalid-syntax` | FAIL, parse error | Not required | Expected rejection |
| `invalid-connectivity` | PASS, 2 components | FAIL, missing GND | Expected rejection |
| `invalid-value` | PASS, 2 components | FAIL, R1 not 1 kohm | Expected rejection |

Runs used copies on WSL ext4 filesystem. Direct `/mnt/c` execution was blocked
by permission semantics. Protected acceptance files remain byte-identical to
checkpoint `5409121`; only TestBench implementation code was corrected to the
empirically observed Diode 0.4.34 API.

## KiCad

Direct `kicad-cli pcb drc --format json --severity-all
--exit-code-violations` ran against Diode source fixture
`crates/pcb-layout/tests/resources/tracks/module/layout.kicad_pcb`.

- Exit: `5`
- Violations: `3`
- Unconnected items: `0`
- Raw JSON SHA-256: `40204b9fbd90f3224fb6e43f79f656fe005b1200a8a48fdd4fb3cb6d2ffcbd0f`
- Expected harness interpretation: deterministic `FAIL`, not environment
  `BLOCKED`. Direct CLI mapping was exercised; end-to-end harness layout report
  remains blocked because no project layout was generated.

## Blocked

- Windows-native Diode: OS error 1314, required symlink privilege unavailable.
- WSL Diode layout: `ModuleNotFoundError: No module named 'pcbnew'`.
- End-to-end layout profile remains `BLOCKED`; direct DRC adapter contract is
  empirically verified.

Verification PASS never means production-ready. Fabrication still requires
human engineering review and approval.
