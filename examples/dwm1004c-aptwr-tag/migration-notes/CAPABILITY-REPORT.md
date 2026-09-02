# CAPABILITY-REPORT — dwm-tag-passive (DWM1004C APTWR TAG, passive layer)

- Date: 2026-08-31
- Project: `/home/rendra/dwm-tag-passive` (profile: `schematic`)
- Purpose: pcb-agent capability test on the 57-component passive layer of the DWM1004C APTWR TAG. Not a fabrication effort.

## 1. Summary

- Built a passive-only capability model (57 components, 39 nets, 114 pin members) in ZEN from a fresh KiCad netlist export; authored SPEC/ACCEPTANCE/expected-connectivity contracts; ran doctor + verify under pcbc 0.4.40.
- Result: **verify status PASS** (all 5 required gates PASS), with `production_ready: false`, `fabrication_approved: false`, `human_review_required: true`.
- Key toolchain finding: Tvs package `SOD-923` (per BOM) is **not** in the stdlib enum; the documented SOD option for Tvs is `SOD-882`. Rejection captured verbatim in section 9; deviation approved and applied to D1.

## 2. Provenance & environment

| Item | Value |
|---|---|
| Harness (WSL) | `/home/rendra/pcbagent-dwm` @ HEAD `76b9d4882b4425774e3772fcaf780358c57e91d5` ("Merge pull request #6 from GSPETech/fix/pr5-review-findings") |
| Harness (Windows mirror) | `C:\Users\jrjua\diodeinc` |
| Evidence integrity | `manifest.sha256` = `5a22245ff49e72cb7a8ca72a67793f7cb367b463707ddab7e576883e2fa6728e`; `manifest-attestation.json` = `6eed2e3c893090cfc2c9952b4c7710e7b33fcc6c6412472ab2f707411dc98ac8` — both match the harness tree (re-verified 2026-09-01) |
| Harness clone state | `/home/rendra/pcbagent-dwm` @ HEAD `76b9d4882b4425774e3772fcaf780358c57e91d5`; working tree clean except one untracked dir `src/pcb_agent.egg-info/` (build artifact, not deleted); `tests/evidence/diode-0.4.40/` shows **no diff** |
| Toolchain | pcbc **0.4.40** (default installed is 0.4.41; never used for execution) |
| Version pinning | PATH wrapper `/tmp/pcb-pin-0.4.40/pcb` routing to the documented version lane (`pcb +0.4.40 ...`). Pinning `pcb-version = "0.4.40"` in `pcb.toml` is rejected by the shim (major.minor only); a `pcb-version` file is inert in shim 0.2.6. `pcb.toml` kept at `"0.4"`. |
| Reproducibility | The pin lane lives under `/tmp/` and is **ephemeral** (cleared on reboot); it must be recreated to re-run at exactly 0.4.40. A 2026-09-01 re-run reproduced the reference: doctor `20260831T235437.603975Z-78508` PASS and verify `20260831T235441.398915Z-78536` PASS, with **byte-identical generated testbenches** and identical contract hashes; the only per-run differences are the wall-clock `duration` and the random `/tmp/pcb-agent-*` dir names embedded in the result JSON. Two earlier runs (…78414 doctor, …78433 verify) were BLOCKED with `pcb` not on PATH, confirming the harness fails closed when the tool is missing. |
| OS / runtime | WSL Ubuntu-24.04, Linux x86_64, Python 3.12.3 |
| Project files | `pcb.toml`, `project.toml` (profile `schematic`), `SPEC.json`, `ACCEPTANCE.json`, `expected-connectivity.json`, `NET_NAME_MAPPING.md`, `src/board.zen`, `tests/board_test.zen` |
| KiCad source of record | `D:\Project_Rendra\DECAWAVE\SCH-PCB\dwm1004c_aptwr_tag` (read-only; git repo root `D:\Project_Rendra\DECAWAVE` @ HEAD `80b84bf40e770668037259926dbca6e387df626d`, 2026-08-08). Working-tree status: all four `.kicad_sch` **clean** vs HEAD; `dwm1004c_aptwr_tag.kicad_pcb` and `dwm1004c_aptwr_tag.kicad_pro` **modified** (pcb diff is plot-config only: `drillshape` 1→0, `outputdirectory` ""→"CAD-CAM/", no geometry change). A fresh 2026-09-01 netlist re-export differs from `tag-fresh.net` only in the export-timestamp line — **no schematic change** since the capability run. |

## 3. Fresh netlist export

- File: `C:\Users\jrjua\AppData\Local\Temp\opencode\dwm-netlist\tag-fresh.net` (WSL: `/mnt/c/Users/jrjua/AppData/Local/Temp/opencode/dwm-netlist/tag-fresh.net`)
- Exported by Eeschema `10.99.0-1181-g2d5a581dc2` on `2026-08-31T12:38:47`, from the current source tree.
- SHA-256: `ad2e7b052b43228848cd539e33e1e27500603163137e07439761581fea56df75`
- Contents: **72 components, 71 nets** (KiCad S-expr export format).

## 4. Fresh vs stale delta

Stale reference: `D:\Project_Rendra\DECAWAVE\SCH-PCB\dwm1004c_aptwr_tag\netlist\dwm1004c_aptwr_tag.net` (Eeschema 9.0.7 **S-expr** export, 2-space indent; 60 nets / 65 components).

| Category | Count | Items |
|---|---|---|
| Components only in fresh | 10 | C24, C25, C26, FB1, R16, R19, R27, RX1, TX1, U2 |
| Components only in stale | 3 | C7, SW2, U7 |
| Nets only in fresh | 17 | (see `NET_NAME_MAPPING.md`) |
| Nets only in stale | 6 | DWM_NRST, /POWER/OUT, Net-(J1-D+), Net-(U7-VDD), unconnected-(J1-ID-Pad4), unconnected-(S1-Pad1) |
| Common nets | 54 | **19 have membership changes** (pin-set of ref,pin differs) |

**The 19 membership-changed common nets** (verified with two independent S-expr parsers; pin-sets compared as sets of (ref, pin)): `+3.3V`, `/IMU/BNO_SCL`, `/IMU/BNO_SDA`, `/MAIN MODULE TAG/CONFIG`, `/MAIN MODULE TAG/DWM_RX1`, `/MAIN MODULE TAG/DWM_TX1`, `/MAIN MODULE TAG/MCU_BOOT`, `/MAIN MODULE TAG/SWCLK`, `/MAIN MODULE TAG/SWDIO`, `/POWER/BAT+`, `/POWER/BIN`, `/POWER/EN`, `/POWER/GPOUT`, `/POWER/SRN`, `GND`, `Net-(U6-TS{slash}MR)`, `Net-(U6-~{CE})`, `VCC`, `VUSB`.

These 19 collapse into **6 real design changes** between the stale (2026-07-17) and fresh (2026-08-31) exports:

1. **I2C pull-up swap + fuel-gauge renumber (U7→U2).** `/IMU/BNO_SCL` and `/IMU/BNO_SDA`: stale `R13.2+U7.2` / `R12.2+U7.1` → fresh `R12.2+U2.2` / `R13.2+U2.1`. The I2C pull-ups R12/R13 move to the opposite bus line and the fuel gauge is renumbered U7→U2 (BQ27441). **This is a real design change; the prior "no changes" claim was incorrect.**
2. **Capacitor polarity flip (C3, C4).** `/POWER/BAT+` (C4) and `/POWER/GPOUT` (C3): pin-1/pin-2 orientation reverses (C4.2→C4.1, C3.1→C3.2), i.e. the polarized orientation was flipped.
3. **Fuel-gauge renumber on power nets (U7→U2).** `/POWER/BAT+` (U7.6,U7.8→U2.6,U2.8), `/POWER/SRN` (U7.7→U2.7), `/POWER/BIN` (U7.10→U2.10), `/POWER/GPOUT` (U7.12→U2.12).
4. **USB connector migration (J1 USB-A → J3 USB-C) + header renumbering.** `VUSB` (stale J1.1 → fresh J3.A4_B9+J3.B4_A9) and `GND` (stale J1.5,J1.SH1–SH6 → fresh J3.S1–S4,J3.A1_B12,J3.B1_A12). Consequential renumbering: stale J3 (PROG header) → fresh J4; stale J1 (USB-A) → fresh J1 (2-pin header); fresh J3 = USB-C. This also shifts `/MAIN MODULE TAG/MCU_BOOT`, `SWCLK`, `SWDIO` (J3.2/3/4 → J4.1/3/4) and `DWM_RX1`/`DWM_TX1` (J4.2/3 → J1.1/2 + new test points RX1/TX1).
5. **/POWER/EN enable path.** Stale `R25.2` → fresh `R27.2 + S1.2` (S1 now on the enable net; was on VCC).
6. **Component churn.** Added C24/C25/C26, FB1, R16, R19, R27, RX1, TX1, U2; removed C7, SW2, U7 — surfacing as membership deltas on `+3.3V`, `GND`, `/POWER/SRN`, `/MAIN MODULE TAG/CONFIG`, `Net-(U6-TS{slash}MR)`, `Net-(U6-~{CE})`, `VCC`.

**Count note:** an earlier working note cited "20 common nets changed"; every deterministic recomputation (pin-set membership, pin+pinfunction, common-component-only, moved-pin source/destination) yields **19**. This report uses the verified **19** and flags the "20" as an unexplained off-by-one for human confirmation — it is not asserted.

Interpretation: the design was updated after the stale export (C24-C26, R16/R19/R27, FB1, U2 added; C7, SW2, U7 removed) with the six real changes above. The model in this report is built exclusively from the **fresh** export.

## 5. Model scope (57 components)

| Kind | Count | References |
|---|---|---|
| capacitor | 25 | C1-C26 (C7 not present in current design) |
| resistor | 26 | R1-R27 (R24 not present in current design) |
| inductor | 1 | L1 |
| ferrite_bead | 1 | FB1 |
| led | 3 | D2, D3, D5 |
| tvs | 1 | D1 |

Contract artifacts sized to scope:

- `SPEC.json`: 57 requirements (one per reference; `REQ-054` = D1).
- `ACCEPTANCE.json`: 57 checks (all `kind: zener_test`, `test: DwmTagPassive.default`).
- `expected-connectivity.json`: 39 nets / 114 pin members; rules: `forbid_unlisted_members: true`, `required_power_nets: [P3V3, GND, VCC, VUSB, POWER_BAT_P]`.
- `src/board.zen`: 106 lines (57 component instances + 1 `Board` instance).
- `tests/board_test.zen`: 57 presence checks (`DwmTagPassive` testbench).

**Acceptance mapping (disclosure):** all 57 `ACCEPTANCE.json` checks are `DwmTagPassive.default` **presence-only** assertions (satisfied by the ZENER_TEST gate). The **value/package** requirements are carried by `SPEC.json` / `expected-connectivity.json` and enforced by the **SPECIFICATION** gate; the **net membership** is enforced by the **CONNECTIVITY** gate. So "57 checks PASS" means all 57 references are present with their required value/package and net membership — it is not a separate 57-fold electrical sign-off.
## 6. Exclusions (15 of 72 fresh components)

| Reference(s) | Reason |
|---|---|
| TH1 | NTC thermistor, footprint `RES-TH_BD2.8_NTC-10K` (through-hole); stdlib thermistor generics are SMD-only |
| RX1, TX1 | Test points; no `test_point` adapter in stdlib |
| Y1 | Crystal; pin topology (1-to-many / 4-pin GND) unsupported by stdlib -> fail-closed, not modeled |
| U1, U2, U4, U5, U6 | ICs; passive-only capability model (section 7, deviation 8) |
| J1, J2, J3, J4 | Connectors; out of scope |
| S1, SW1 | Switches; out of scope |

Note: C7 and R24 are absent from the fresh netlist (not present in the current design), so they are outside the scope by definition. 72 fresh - 57 in scope - 15 excluded = 0 unaccounted.

## 7. Approved deviations (9)

1. **R18, R22** — BOM DNP; modeled as `0ohm` resistors so the nets remain connected.
2. **D1** — probed BOM package `SOD-923` first (build fails, section 9), then deviated to `SOD-882`, the only SOD package in the Tvs enum.
3. **D1 (direction)** — fresh netlist D1 part `ESD9B5.0ST5G` is a **bidirectional** ESD diode (onsemi ESD9B family), but the stdlib `tvs` generic only models a unidirectional `Tvs(A=…, K=…)`; the model therefore records it as `Tvs(A=GND, K=VUSB)`. This is a **capability gap**: the A/K orientation is a modeling abstraction and must not be read as the real polarity. Bidirectional TVS is not representable in stdlib.
4. **D1** — no value assertion: the BOM value is an MPN (`ESD9B5.0ST5G`), stdlib has no `mpn` field, and inferring "5V" from the MPN was refused.
5. **D2, D3, D5** — the fresh netlist "values" for these LEDs are **function labels, not colors** (D2=`STAT2`, D3=`STAT1`, D5=`DWM_LED`); the stdlib `led` generic exposes no value/color accessor that can carry a function label, so the model asserts `color="green"` (a placeholder, not from the netlist) and `package="0805"` only, with **no value assertion**.
6. **TH1** — excluded (section 6).
7. **RX1, TX1** — excluded (section 6).
8. **Passive-only nets** — all 39 nets contain passive pins only; IC/connector/switch endpoints are omitted from membership. This is omission, not concealment: the model does not assert the existence of those connections.
9. **Net-name mapping** — full KiCad hierarchical -> flat ZEN mapping applied (39 rows, section 8).

## 8. Net-name mapping (39)

| Original (KiCad) | ZEN |
|---|---|
| `+3.3V` | `P3V3` |
| `/IMU/ADDR_SEL` | `IMU_ADDR_SEL` |
| `/IMU/BNO_SCL` | `IMU_BNO_SCL` |
| `/IMU/BNO_SDA` | `IMU_BNO_SDA` |
| `/IMU/IMU_NRST` | `IMU_IMU_NRST` |
| `/IMU/XTAL+` | `IMU_XTAL_P` |
| `/IMU/XTAL-` | `IMU_XTAL_N` |
| `/MAIN MODULE TAG/CONFIG` | `MAIN_CONFIG` |
| `/MAIN MODULE TAG/DWM_IND` | `MAIN_DWM_IND` |
| `/MAIN MODULE TAG/MCU_BOOT` | `MAIN_MCU_BOOT` |
| `/POWER/BAT+` | `POWER_BAT_P` |
| `/POWER/BIN` | `POWER_BIN` |
| `/POWER/EN` | `POWER_EN` |
| `/POWER/GPOUT` | `POWER_GPOUT` |
| `/POWER/LX1` | `POWER_LX1` |
| `/POWER/LX2` | `POWER_LX2` |
| `/POWER/MODE` | `POWER_MODE` |
| `/POWER/SRN` | `POWER_SRN` |
| `/POWER/STAT1` | `POWER_STAT1` |
| `/POWER/STAT2` | `POWER_STAT2` |
| `GND` | `GND` |
| `Net-(D2-A)` | `D2_ANODE` |
| `Net-(D3-A)` | `D3_ANODE` |
| `Net-(D5-K)` | `D5_K` |
| `Net-(J3-CC1)` | `J3_CC1` |
| `Net-(J3-CC2)` | `J3_CC2` |
| `Net-(R23-Pad1)` | `R23_PAD1` |
| `Net-(R25-Pad2)` | `R25_PAD2` |
| `Net-(U1-FB)` | `U1_FB` |
| `Net-(U1-VOUT)` | `U1_VOUT` |
| `Net-(U2-VDD)` | `U2_VDD` |
| `Net-(U4-CAP)` | `U4_CAP` |
| `Net-(U4-NBOOT_LOAD_PIN)` | `U4_NBOOT_LOAD` |
| `Net-(U6-ILIM{slash}VSET)` | `U6_ILIM_VSET` |
| `Net-(U6-ISET)` | `U6_ISET` |
| `Net-(U6-TS{slash}MR)` | `U6_TS_MR` |
| `Net-(U6-~{CE})` | `U6_CE_N` |
| `VCC` | `VCC` |
| `VUSB` | `VUSB` |

## 9. SOD-923 probe & rejection

- Performed **exactly once** on the real project, under pcbc 0.4.40 (via the pin wrapper), with D1 declared as `package="SOD-923"`.
- Command: `pcb build src/board.zen`
- Exit code: **1**
- stdout: empty (SHA-256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`)
- stderr saved at `/tmp/sod923-probe.stderr`; SHA-256: `2836e90cf8d443db8979fc785b8a34d80aa3861c23a552640bed91f7fd7eb2a3`

Verbatim rejection (stderr):

```
Error: Input 'package' (type) has wrong type for this placeholder: expected enum(DO-219AB, DO-214AC, DO-214AA, DO-214AB, SOD-882), got "SOD-923"
     ╭─[ /home/rendra/dwm-tag-passive/.pcb/stdlib/generics/Tvs.zen:17:1 ]
     │
  17 │ package = config(Package, default=Package("DO-219AB"))
     │ ───┬───
     │    ╰───── Input 'package' (type) has wrong type for this placeholder: expected enum(DO-219AB, DO-214AC, DO-214AA, DO-214AB, SOD-882), got "SOD-923"
     │
     ├─[ /home/rendra/dwm-tag-passive/src/board.zen:99:57 ]
     │
  99 │ ╭─▶ Inductor(name="L1", value="1uH", package="0805", P1=POWER_LX1, P2=POWER_LX2)
 100 │ ├─▶ FerriteBead(name="FB1", value="120ohm", package="0603", P1=U1_VOUT, P2=P3V3)
     │ │
     │ ╰─────────────────────────────────────────────────────────────────────────────────── Error instantiating `Tvs`
 ─────╯

Stack trace (most recent call last):
    /home/rendra/dwm-tag-passive/src/board.zen:101:1 (Error instantiating `Tvs`)
    /home/rendra/dwm-tag-passive/.pcb/stdlib/generics/Tvs.zen:17:1 (Input 'package' (type) has wrong type for this placeholder: expected enum(DO-219AB, DO-214AC, DO-214AA, DO-214AB, SOD-882), got "SOD-923")

✗ board.zen: Build failed
Error: Build failed with errors
```

- Tvs generic (`stdlib/generics/Tvs.zen:17`, pcbc 0.4.40): `package = config(Package, default=Package("DO-219AB"))` — allowed enum: `DO-219AB, DO-214AC, DO-214AA, DO-214AB, SOD-882`.
- Files changed after the probe (deviation applied): `src/board.zen:101`, `SPEC.json` (`REQ-054`), `expected-connectivity.json` (D1 entry). Acceptance semantics unchanged.
## 10. Exit codes

| Command (all under pcbc 0.4.40 via pin wrapper) | Exit | Key output |
|---|---|---|
| `pcb build src/board.zen` (SOD-923 probe) | **1** | section 9 verbatim |
| `pcb build src/board.zen` (final) | 0 | `✓ board.zen (57 components)` |
| `pcb test tests/board_test.zen` (locked test) | 0 | `✓ DwmTagPassive: 1 check passed across 1 case` |
| `python3 /home/rendra/pcbagent-dwm/pcb-agent doctor` | 0 | run `20260831T144227.520569Z-53547`, status PASS |
| `python3 /home/rendra/pcbagent-dwm/pcb-agent verify` | 0 | run `20260831T144235.639929Z-53580`, status PASS |

## 11. Gate status

### doctor (run `20260831T144227.520569Z-53547`, PASS)

| Check | Status | Note |
|---|---|---|
| CONTRACT | PASS | project contracts loaded and hashed |
| PLATFORM | PASS | Linux x86_64; Python 3.12.3 |
| GIT | PASS | git detected |
| PCB | PASS | capability help exited 0 |
| KICAD-CLI | PASS | capability help exited 0 |
| SIMULATION | SKIPPED | simulation is not implemented |
| AI_CODEX | SKIPPED | codex unavailable |
| AI_CLAUDE | PASS | claude detected; not invoked |
| AI_GEMINI | SKIPPED | gemini unavailable |
| AI_AIDER | SKIPPED | aider unavailable |
| DIODE_COMMANDS | PASS | version/help/toolchain probes completed |

### verify (run `20260831T144235.639929Z-53580`, PASS)

| Gate | Provenance | Status | Note |
|---|---|---|---|
| CONTRACT | harness | PASS | project contracts loaded and hashed |
| DIODE_BUILD | tool | PASS | exit 0 |
| ZENER_TEST | tool | PASS | exit 0 |
| CONNECTIVITY | tool | PASS | exit 0; generated assertion, 1 check passed across 1 case |
| SPECIFICATION | tool | PASS | exit 0; generated assertion, 1 check passed across 1 case |
| LAYOUT_GENERATE | harness | SKIPPED | layout profile not active |
| LAYOUT_SYNC | harness | SKIPPED | layout profile not active |
| KICAD_DRC | harness | SKIPPED | layout profile not active |
| SIMULATION | harness | SKIPPED | simulation is not implemented |

Report flags (verify-report.json): `status: PASS`, `production_ready: false`, `fabrication_approved: false`, `human_review_required: true`, `source_dirty: false`, `profile: schematic`, `versions.pcbc: "0.4.40"`, `timestamp: 2026-08-31T14:42:41.781328+00:00`.

## 12. Evidence digests

Contract hashes as recorded in verify-report.json:

| File | SHA-256 |
|---|---|
| `SPEC.json` | `14a6aa20106c892f664be2fa40033446e0f404d44045cce070df99bec6d446c6` |
| `ACCEPTANCE.json` | `768578e776dc244911ea78cfb07123ad8971fb742ec620fd60cfd6b7ac471e29` |
| `expected-connectivity.json` | `0665dd1dd4c843b68a80e17d5dee8bbc247d61c409717b851836b20bf39cbd63` |
| `project.toml` | `d0d3883fa832c103ba00f2a6d5d41dea958a77de372d44dc3e3b8290489ae909` |

Artifacts (SHA-256 of files in `reports/20260831T144235.639929Z-53580/raw/`, re-verified on disk):

| Artifact | SHA-256 |
|---|---|
| `diode_build.json` | `09f03e698d022df15fc3db7ee332c977f6c9d83339f3465102e980144c6a399a` |
| `zener_test.json` | `a661feaafb327d40ae915308767a9b32e44a538fbdd032bea4e86697deb51221` |
| `zener_test.json` (testbench) | `7c223861e181934d89bed3be35de886bdf1a5437ae86ec6fe658d8417f7ddc80` |
| `connectivity-testbench.zen` (generated) | `10022b1f822a8d23088b8d3214d38727abf80e54a7b54d3957f764ccdf06aa9f` |
| `connectivity-result.json` | `3c7292f29b9bd1e80ca0b45758e7f040b31db00ce6f1b31da69399bfc0e449e0` |
| `specification-testbench.zen` (generated) | `6a0e6f683dc9532941452ab3024675b080985734cb685403125f4b557f9098f6` |
| `specification-result.json` | `b04b615082eb04ca2f4bb0b7ab4e6014558f5d3c86c5f233819be2a881f52705` |

## 13. Kinds proven usable (pcbc 0.4.40 + stdlib)

| Kind | Instances | Attributes asserted |
|---|---|---|
| `resistor` | 26 | value (0ohm-100kohm), package (0402/0603/0805), P1/P2 nets |
| `capacitor` | 25 | value (22pF-10uF), package (0402/0603/0805), P1/P2 nets |
| `led` | 3 | `color` (placeholder `green`), package (0805), A/K nets; **no value** (netlist "value" is a function label, deviation 5) |
| `inductor` | 1 | value (1uH), package (0805), P1/P2 nets |
| `ferrite_bead` | 1 | value (120ohm), package (0603), P1/P2 nets |
| `tvs` | 1 | package (`SOD-882`), A/K nets; no value (deviation 4); a bidirectional part modeled as unidirectional A/K (deviation 3) |

**Kinds coverage:** stdlib registers **9** kinds: `resistor`, `capacitor`, `inductor`, `ferrite_bead`, `led`, `tvs` (all exercised above) plus `thermistor`, `zener`, `rectifier` (**not exercised** — TH1 is a through-hole NTC outside the stdlib thermistor generics, and no zener/rectifier parts are in scope). Exercised: 6 kinds / 57 instances; not exercised: 3 kinds.

## 14. Unsupported constructs / limitations

- `tvs` package `SOD-923` — enum-rejected (section 9).
- Crystal (`Y1`) — 1-to-many / 4-pin GND pin topology unsupported by stdlib; fail-closed.
- `test_point` — no generic in stdlib (RX1/TX1).
- Through-hole NTC thermistor (`TH1`) — stdlib thermistor is SMD-only.
- IC / connector / switch instances — outside the passive model scope (U1-U6, J1-J4, S1, SW1).
- `mpn` field — does not exist in stdlib generics (D1 BOM value is an MPN).
- Version pinning — shim rejects `pcb-version = "0.4.40"` (major.minor only); `pcb-version` file inert in shim 0.2.6; supported override is the version lane (`pcb +0.4.40`).
- Schematic profile — LAYOUT / DRC / SIMULATION gates are SKIPPED by design; no physical verification was performed.
- Board stack — `board.zen` declares `layers = 4`, but the production KiCad board is **2-layer** (F.Cu + B.Cu only, no internal copper). The `layers = 4` is a capability-model placeholder with no physical meaning here; it is not asserted by any gate and must not be read as a fab stack-up.

## 15. Authoring cost, honest boundaries, safety

**Authoring cost:** 57 SPEC requirements, 57 ACCEPTANCE checks, 39 nets / 114 pin members, 2 connectivity rules, `board.zen` 106 lines, 57-check testbench, 39-row net-name mapping.

**Honest boundaries:**

- This is a schematic-profile **capability model** of the passive net layer, not a fabrication deliverable.
- Every PASS above was produced under pcbc 0.4.40 with the exact digests in section 12. **Verification PASS is not fabrication approval.**
- KiCad remains the production tool of record; `board.zen` is a verification/capability artifact.
- D1 deviates from the BOM package (`SOD-923` -> `SOD-882`) due to the stdlib enum; this requires human confirmation before any physical build decision.
- Net membership omits IC/connector/switch endpoints by scope (deviation 8); the model does not assert those connections exist.
- No layout, DRC, or simulation evidence exists for this board in this run.

**Safety (verbatim, from verify-report.json):**

```
production_ready: false
fabrication_approved: false
human_review_required: true
```

Verification PASS is not fabrication approval.
