# PRODUCTION-READINESS — dwm-tag-passive (DWM1004C APTWR TAG)

- Date: 2026-09-01
- Companion to `CAPABILITY-REPORT.md` (schematic-profile capability model, verify PASS).
- Purpose: a **human-executable** fabrication-readiness checklist for the DWM1004C APTWR TAG.
- This is **not** a fabrication deliverable and does **not** approve fabrication.

## 0. Status (do not change without a human engineer's sign-off)

| Flag | Value | Source |
|---|---|---|
| verify status | PASS (capability only) | `CAPABILITY-REPORT.md` §11, verify-report.json |
| `production_ready` | **false** | verify-report.json |
| `fabrication_approved` | **false** | verify-report.json |
| `human_review_required` | true | verify-report.json |
| Physical layer verified | **No** — LAYOUT / DRC / SIMULATION gates SKIPPED by design (schematic profile) | — |

KiCad is the production tool of record. The pcb-agent `board.zen` model is a verification/capability artifact only.

## 1. Board facts to hold before any fab step

- **Real stack-up is 2-layer** (F.Cu + B.Cu, no internal copper). `board.zen` declares `layers = 4`, but that is a capability-model placeholder with **no physical meaning** — do **not** send a 4-layer stack-up to the fab.
- Board is **read-only** to this agent. All steps below are for a human with the KiCad source tree.

## 2. Blocking actions (must be done, in order, before Gerbers are regenerated)

### 2.1 Re-sync schematic reference designators to the board (DRC `--schematic-parity`: 6 mismatches)
The board still carries **legacy footprint names** while the schematic uses the current J-numbers:

| Board footprint (pos) | Inferred current ref | Note |
|---|---|---|
| `UART` (127.25, 93.33), PinHeader 1x02 vert | `J1` (Conn_01x02) | DWM_RX1 / DWM_TX1 side; confirm |
| `Prog` (127.28, 112.81), PinHeader 1x06 horiz | `J4` (Conn_01x06) | MCU_BOOT / SWCLK / SWDIO; confirm |
| `BAT` (158.0, 105.45), PinHeader 1x02 vert | `J2` (BAT) | battery connector; confirm |

- **Do:** open the board, *Update PCB from Schematic*, rename the three footprints to `J1`/`J2`/`J4` (verify the intended mapping before renaming).
- **Verify:** re-run `kicad-cli pcb drc --schematic-parity` → **0** `missing_footprint` / `extra_footprint` parity items.

### 2.2 Clear the 4 DRC **errors** (`hole_clearance`)
- Board rule requires **0.2540 mm** clearance; actual **0.2349 mm** at the USB-C `J3` pads: `B4_A9 [VUSB]`, `B1_A12 [GND]`, `A1_B12 [GND]`, `A4_B9 [VUSB]` (plus the J3 NPTH pad).
- **Do:** fix the pad/clearance geometry on the USB-C footprint **or** consciously relax the board clearance rule. Do not ship with a clearance violation.
- **Verify:** re-run DRC → **0** errors.

### 2.3 Regenerate Gerbers from the corrected board — do **not** reuse existing CAD-CAM files
- The untracked `CAD-CAM/` folder holds Gerbers from **Aug 7/10**, which **predate** the plot-config change (board `outputdirectory` ""→"CAD-CAM/", `drillshape` 1→0) **and** the six design changes in `CAPABILITY-REPORT.md` §4. They are **stale**.
- **Do:** regenerate Gerbers/fabrication files from the corrected 2-layer board, then re-verify (Gerber viewer + fab DRC) before release.
- **Verify:** new CAD-CAM files timestamped after the corrections; no reuse of the Aug 7/10 set.

## 3. Non-blocking DRC warnings to resolve (20)

- `track_dangling` ×2 — delete or connect: `[+3.3V]` F.Cu 0.125 mm at (148.625, 103.9125); `[/IMU/BNO_SDA]` B.Cu 0.2048 mm at (157.738, 108.3).
- `silk_edge_clearance` ×5 — resolve.
- `lib_footprint_mismatch` ×7 — footprints locally edited away from the library copy: `logogspe/G***`, `SON-12_L4.0-W2.5...` (U2), `PinHeader_1x02` ×2 (UART/BAT), `PinHeader_1x06` (Prog), `L0603` (FB1), `RES-TH_BD2.8_NTC-10K` (TH1). Accept the edits or re-sync to library.
- `lib_footprint_issues` ×6 — footprint libraries not enabled in this config: `Decawave_UWB_RF` (U5), `TPS631000DRLR` (U1), `TYPE-C-31-M-12` (J3), `JS102011SAQN` (S1), `BNO055` (U4), `BQ25185DLHR` (U6). Enable the libraries so these resolve.

## 4. ERC findings (44 = 12 environmental / 7 intentional / 25 real)

Evidence: `C:\Users\jrjua\AppData\Local\Temp\opencode\dwm-prod-drive\erc.json` (kicad-cli 10.99.0, `--severity-all`).

- **Environmental (12)** — toolchain/library config, not design: 6 `footprint_link_issues` (BNO055, Decawave_UWB_RF libs) + 6 `lib_symbol_issues` (hardcoded `C:/Users/iotgs/...` paths from another machine). Fix library config or accept.
- **Intentional by design (7)** — confirm before release: J3 `A6/A7/A8` (DP1/DN1/SBU1, power-only USB-C), U2 pins `4/9/11` (NC), U5 `RESV@15`.
- **Real findings (25) — resolve before fab:**
  - 1 `undefined_netclass` — `PWR_VUSB` (define the netclass).
  - 1 `lib_symbol_mismatch` — `FB1` (locally edited symbol).
  - 5 `multiple_net_names` — `VUSB`/`VBUS`, `BAT+`/`SRP`, `GND`/`BAT-`, `GPOUT`/`PWR_INT`, `+3.3V`/`VDDIO` (unify names).
  - 12 `pin_to_pin` — `U2` (BQ27441) + `FB1` pins typed `Unspecified` (set pin types).
  - 1 `pin_not_driven` — `U5 INT2` input (drive or mark NC).
  - 5 `power_pin_not_driven` — `#PWR011`, `#PWR020`, `#PWR01`, `#PWR035`, `U5 RESV15`.

## 5. Open engineering decisions (human)

1. **D1 ESD device** — fresh netlist part `ESD9B5.0ST5G` is a **bidirectional** ESD diode; the capability model can only express a unidirectional `Tvs(A=GND, K=VUSB)` (capability gap). Confirm the real ESD part and polarity before assembly.
2. **D1 package** — BOM says `SOD-923`; stdlib Tvs enum rejected it, model uses `SOD-882`. Confirm the final physical package.
3. **R18 / R22** — netlist marks them **DNP**; the model treats them as `0ohm`. Decide DNP vs 0Ω for the assembly list.
4. **USB-C is power-only** — DP/DN/SBU unconnected. Confirm intentional.
5. **U5 `INT2`** — not driven. Confirm.
6. **`PWR_VUSB` netclass** — undefined. Define.
7. **Confirm the 6 design changes / 19 changed nets** in `CAPABILITY-REPORT.md` §4 are intentional (I2C pull-up swap + U7→U2 renumber, C3/C4 polarity flip, fuel-gauge renumber, USB-A→USB-C migration + header renumber, `/POWER/EN` path, component churn).
8. **"20 vs 19" common-net count** — deterministic recomputation yields **19**; the earlier "20" is an unexplained off-by-one. Confirm 19.

## 6. Go / No-Go

- A **human engineer** must complete §2 (blocking), resolve the §4 real ERC findings and §3 DRC warnings, and make the §5 decisions, then sign off.
- The pcb-agent harness **cannot** approve fabrication. Its verify PASS is a schematic-profile capability result only.

## 7. Safety (verbatim)

```
Verification PASS is not fabrication approval.
production_ready remains false.
fabrication_approved remains false.
```
