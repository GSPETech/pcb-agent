# DWM1004C AP-TWR tag

A 72-component UWB tag board, migrated from an existing KiCad project into
Zener and verified with `pcb-agent`. It exists to show what the harness can and
cannot do on a real design, in one place that can be re-run.

Everything here was produced by the tools; nothing is hand-drawn.

## Layout

| Path | What it is |
|---|---|
| `dwm1004c_aptwr_tag.zen` | board entry point |
| `modules/` | `IMU`, `MAIN_MODULE_TAG`, `POWER` subcircuits |
| `components/` | 24 component packages, symbols, and 11 footprints |
| `SPEC.json`, `ACCEPTANCE.json`, `expected-connectivity.json` | harness contracts |
| `project.toml`, `pcb.toml` | project and workspace manifests |
| `tests/dwm_test.zen` | locked TestBench |
| `layout/agent-verified/` | KiCad output produced by the harness |
| `layout/dwm1004c_aptwr_tag/` | KiCad output from manual commands, for comparison |
| `migration-notes/` | reports and one-off scripts kept from the migration |

## Reproducing the verification

The adapter registry is pinned to `pcbc 0.4.40`, and `pcb.toml` only accepts a
lane, so pin the exact toolchain with a shim (see `AGENTS.md`):

```sh
pcb toolchain install 0.4.40
mkdir -p /tmp/pcbshim
printf '#!/bin/bash\nexec "$HOME/.local/bin/pcb" +0.4.40 "$@"\n' > /tmp/pcbshim/pcb
chmod +x /tmp/pcbshim/pcb
export PATH="/tmp/pcbshim:$PATH"

./pcb-agent verify --project examples/dwm1004c-aptwr-tag --profile schematic --format json
./pcb-agent verify --project examples/dwm1004c-aptwr-tag --profile layout --format json
```

The layout profile additionally needs `freerouting` and the `pcbnew` Python
bindings on `PATH`. Without them the `ROUTE` gate reports `BLOCKED`, not `FAIL`.

Run on Linux or WSL2: Windows-native `pcb build` fails with `os error 1314`.

## Recorded result

Schematic profile reaches `PASS` on all five required gates. Layout profile:

```
LAYOUT_GENERATE  PASS
PLACEMENT        PASS   placed 72 footprints; board 63.32 x 89.38 mm
ROUTE            PASS   routed 361 wires and 95 vias
LAYOUT_SYNC      FAIL
KICAD_DRC        FAIL   KiCad DRC found violations
```

The retained report is in `layout/agent-verified/verification/`.

`KICAD_DRC FAIL` is the correct outcome, not a defect in the gates. What the
placement and routing gates changed, measured on this board:

| | before | after |
|---|---:|---:|
| unconnected items | 169 | 6 |
| DRC violations | 285 | 72 |
| courtyard overlaps | 3 | 0 |
| tracks | 0 | 742 |

## Known limitations this board demonstrates

**Coverage is partial.** Only 47 of 72 components are declared in the
contracts, all resistors and capacitors. The rest — ICs, connectors, switches,
the crystal, LEDs, the inductor, the ferrite bead — are emitted by `pcb import`
as bespoke `Component()` with `type=None`, so no verified adapter describes
them. They cannot reach `PASS`; the harness reports `BLOCKED` rather than
guessing.

**59 DRC errors remain**, and they are intrinsic to two imported footprints, not
to placement: `S1` has a pad pitch that bridges its own solder mask, and the
`J3` USB-C footprint has a mask polygon overlapping its own pads. Fixing those
requires editing the footprints.

**The placer is grid-based.** It separates parts enough to route, which is what
it was built for. The board it produces is 63 × 89 mm against the original
50 × 40 mm, because it does not compact the way a human does. The comparison
folder `layout/dwm1004c_aptwr_tag/` uses placement transferred from the original
board and has 9 DRC errors instead of 59 — worth reading side by side.

**The layout profile does not emit `.kicad_sch`.** The schematic in
`layout/agent-verified/` came from a separate `pcb apply schematic` run.

## Not fabrication-ready

Every report carries `production_ready: false` and `fabrication_approved:
false`. Verification `PASS` means the declared contracts held, nothing more.
Fabrication needs review and approval by an engineer.
