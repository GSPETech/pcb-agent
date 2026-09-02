# PCB Agent

**Deterministic AI-powered PCB design harness for Diode/Zener toolchain.**

Vendor-neutral Python harness that coordinates schematic design, layout generation, and routing verification. AI agents may edit source files within policy boundaries, but **never decide verification truth or fabrication approval**—all gates are decided by locked TestBenches and evidence-backed adapters.

---

## Quick Start

### CLI Usage

```bash
# Verify existing project
./pcb-agent verify --project fixtures/valid-blinky --profile schematic

# Check toolchain and dependencies
./pcb-agent doctor --project fixtures/valid-blinky --format json

# Full layout workflow (schematic → placement → routing → DRC)
./pcb-agent verify --project my_board --profile layout
```

### AI Orchestrator (MCP)

Design PCBs end-to-end with one command:

```bash
/pcb_agent "buat schematic GPS tracker dengan IMU sensor"
```

Orchestrator automatically:
- Creates schematic with components and nets
- Generates layout with deterministic placement
- Routes traces via Freerouting
- Fixes DRC violations iteratively
- Returns `PASS` when all gates green

See [MCP Integration](#mcp-integration) for setup.

---

## Installation

**Requirements:** Python 3.11+, [Diode toolchain](https://github.com/diodeinc/pcb) 0.4.40+, KiCad 10.x (for layout profile)

### Standard

```bash
git clone https://github.com/GSPETech/pcb-agent
cd pcb-agent
python -m pip install -e .
```

Core has **zero third-party Python dependencies**. MCP server requires `mcp` package.

### Windows

```powershell
python pcb-agent doctor --project fixtures/valid-blinky --format json
```

**Note:** Layout profile requires WSL2 or Developer Mode (symlink privilege). Windows-native `pcb build` hits `os error 1314` without it.

---

## Commands

| Command | Purpose | Example |
|---------|---------|---------|
| `doctor` | Probe toolchain & dependencies | `./pcb-agent doctor --project . --format json` |
| `verify` | Run verification gates | `./pcb-agent verify --project . --profile layout` |
| `build` | Build Diode project | `./pcb-agent build --project .` |
| `check` | Run TestBenches | `./pcb-agent check --project .` |
| `layout` | Generate KiCad PCB | `./pcb-agent layout --project .` |
| `drc` | Run KiCad DRC | `./pcb-agent drc --project .` |
| `report` | Generate verification report | `./pcb-agent report --project .` |
| `run` | Delegate to AI backend | `./pcb-agent run --backend command "fix connectivity"` |

All external commands are capability-probed before execution. Netlist export, autorouting, Gerber generation, manufacturing, and ordering are intentionally absent.

---

## Verification Profiles

### `schematic`
Gates: `CONTRACT` → `DIODE_BUILD` → `CONNECTIVITY` → `SPECIFICATION`

Validates component topology, net connectivity, and spec constraints (value, package, pullup) via locked TestBenches. No layout or physical checks.

### `layout`
Gates: (all schematic) → `LAYOUT_GENERATE` → `PLACEMENT` → `ROUTE` → `LAYOUT_SYNC` → `KICAD_DRC`

Runs full physical design flow:
1. **LAYOUT_GENERATE**: `pcb layout` creates `.kicad_pcb` with footprints at origin
2. **PLACEMENT**: Deterministic component placement + Edge.Cuts outline derivation
3. **ROUTE**: Freerouting DSN/SES round-trip via `pcbnew` Python binding
4. **LAYOUT_SYNC**: `pcb layout --check` verifies sync between Zener and KiCad
5. **KICAD_DRC**: `kicad-cli pcb drc` validates manufacturing rules

Missing KiCad or Freerouting → `BLOCKED`. SPICE deferred to future release.

---

## Deterministic Verification

### Core Principle

**AI agents propose. Locked TestBenches decide.**

`CONNECTIVITY` and `SPECIFICATION` gates are decided exclusively by generated TestBenches that the harness owns and hashes. Agents may edit `src/`, `modules/`, `components/`, but **never** contracts (`SPEC.json`, `ACCEPTANCE.json`, `expected-connectivity.json`) or locked TestBenches (`tests/*.zen`).

### Adapter Registry

Component kinds (`resistor`, `led`, `capacitor`, etc.) are resolved through a **versioned adapter registry** keyed by:
- Component kind
- Verified `pcbc` versions (currently `0.4.40`)
- SHA-256 evidence hash from captured Diode runs
- Property accessors (`value`, `package`)
- Pull-up pin pairs (e.g., `["anode", "cathode"]`)

Registry validated lazily against `tests/evidence/diode-0.4.40/manifest.sha256` on first use. **Validation fails closed**—missing or mismatched evidence → `BLOCKED`.

**Registered kinds:** `resistor`, `led`, `capacitor`, `inductor`, `ferrite_bead`, `thermistor`, `zener`, `rectifier`, `tvs`

**Intentionally absent:** Crystal (adapter model cannot represent 1→4 GND pin mapping). ICs, connectors, switches (no verified adapters yet).

### Evidence Chain

Every verification run records:
1. Generated TestBench source + SHA-256
2. Raw `pcb test` JSON result + SHA-256
3. Command metadata (sanitized paths, durations)
4. Immutable safety fields (`production_ready: false`, `fabrication_approved: false`)

Gates digest evidence bytes, not stdout. `result_sha256` attests the exact input that produced the verdict.

### Gate Rules

- **Status vocabulary:** `PASS` | `FAIL` | `BLOCKED` | `SKIPPED`
- **Fail-closed:** Unsupported kind, unverified toolchain version, malformed evidence → `BLOCKED`
- **Exact reconciliation:** `total` = record count, `passed` + `failed` = `total`
- **No silent pass:** Every `value`/`package` constraint must emit an assertion or report `BLOCKED`
- **Topology verification:** `required_pullup` checks exact net membership, not just name existence
- **Dependency cascade:** Failed/blocked prerequisite → dependents `BLOCKED`, never `FAIL`

See `AGENT_PROTOCOL.md` for full contract semantics.

---

## Exit Codes

| Status | Exit | Meaning |
|--------|-----:|---------|
| `PASS` | 0 | All required gates passed |
| `FAIL` | 1 | Deterministic validation failed (design mismatch) |
| `BLOCKED` | 2 | Dependency/toolchain/evidence unavailable |
| Invalid input | 3 | Contract/configuration malformed |
| Backend crash | 4 | Timeout, no-progress, iteration limit |
| `HUMAN_REVIEW` | 5 | Explicit human decision required |

`human_review_required: true` in report does **not** force exit 5. Every report keeps `production_ready: false` and `fabrication_approved: false` regardless of gate status.

---

## MCP Integration

### Setup

1. **Install MCP server:**
```bash
cd ~/.agents/mcp-servers
git clone https://github.com/GSPETech/pcb-agent pcb-agent-mcp
cd pcb-agent-mcp
pip install -e .
```

2. **Register in `opencode.json`:**
```json
{
  "mcpServers": {
    "pcb-agent": {
      "command": "python",
      "args": ["-m", "pcb_agent.mcp_server"],
      "env": {
        "PCB_AGENT_ROOT": "/path/to/pcb-agent"
      }
    }
  }
}
```

3. **Add CLI command:**
```bash
# ~/.claude/commands/pcb_agent.sh
#!/bin/bash
TASK="$1"
PROJECT_DIR="${2:-$(pwd)/pcb_project}"

opencode tool call pcb-agent pcb_design \
  --task "$TASK" \
  --project_dir "$PROJECT_DIR" \
  --profile full
```

### Usage

```bash
# Full workflow
/pcb_agent "buat GPS tracker dengan IMU sensor"

# Schematic only
/pcb_agent "buat schematic power supply 5V" --profile schematic

# Repair specific gate
/pcb_agent repair KICAD_DRC --project ./my_board
```

**Exposed tools:**
- `pcb_design` — orchestrate schematic → layout → routing
- `pcb_verify` — run verification gates
- `pcb_repair` — fix specific gate failure with loop detection

### Agent Flow

```
user: /pcb_agent "buat GPS tracker"
  ↓
MCP pcb_design tool
  ↓
orchestrator.py
  ├→ schematic_agent
  │   └→ repair loop (max 5 iter) → PASS
  ├→ layout_agent
  │   └→ repair loop (max 5 iter) → PASS
  └→ routing_agent
      └→ DRC fix loop (max 10 iter) → PASS
  ↓
return: {
  "status": "PASS",
  "summary": "Schematic PASS (2 iter), Layout PASS (3 iter), DRC PASS (7 violations fixed)",
  "files_created": ["src/gps_module.zen", "tests/gps_test.zen"]
}
```

---

## Reports

Runs write structured reports to `reports/<run-id>/`:
- `verify-report.json` — full verification result with evidence hashes
- `summary.md` — human-readable gate status + durations
- `raw/` — captured evidence (TestBench source, JSON results, DRC output)

Reports include:
- ✓ Check statuses with durations
- ✓ Sanitized command metadata (no absolute home paths)
- ✓ SHA-256 hashes for all generated/captured artifacts
- ✓ Git worktree status (dirty allowed, reported when available)
- ✓ Immutable safety fields (`production_ready: false`, `fabrication_approved: false`)

**Note:** Symlink to `reports/` in project root → writes outside workspace. See security findings.

---

## AI Backends

Generic command backend:
- Reads TOML argv array from config
- Transports task via stdin or literal argv (no shell interpolation)
- Limited to 5 attempts per `run` invocation
- Rejects nested `PCB_AGENT_ACTIVE` (no backend-spawns-backend)
- Protects contracts and locked TestBenches (hash-verified, denied in edit allowlist)
- Detects no-progress via fingerprint comparison
- Independently invokes `verify` after each edit

**Codex adapter:** Probes `codex exec --help` only; invocation disabled until version flags verified.

**Repository skill:** `agents/openai.yaml` intentionally `BLOCKED`—no consumer format verified.

---

## Security Boundary

### Workspace Isolation
- ✓ Executables inside workspace rejected
- ✓ CWD and all file ops must stay in canonical workspace
- ✓ Protected files hashed and snapshotted before backend runs
- ✓ Trusted TestBenches run from harness-owned evidence copy

### Process Containment
- ✓ Child environment allowlisted (no `LD_PRELOAD`, `PYTHONPATH`)
- ✓ Secrets redacted from logs (`sk-`, `ghp_`, `xoxb-`, private keys, JWT)
- ✓ stdout/stderr bounded (no DOS via infinite output)

### Network Policy
- ✗ **Network deny is assertion-only, no OS-level sandbox**
- ⚠ MVP: only fake/local backends should be configured until enforcement exists

### Absent by Design
- No `sudo` or privilege escalation
- No installer execution
- No recursive cleanup beyond `reports/`
- No autorouter, manufacturing, or ordering actions

### Known Issues
See [Security Findings](#security-findings) for active vulnerabilities (S1-S10).

---

## Project Structure

### Required Files (project root)
```
project.toml              # profile, source, test, [toolchain], [layout]
SPEC.json                 # requirements with constraints
ACCEPTANCE.json           # checks mapping requirements
expected-connectivity.json # components, nets, design rules
tests/<name>.zen          # locked TestBench (name matches ACCEPTANCE.checks[].test)
```

Templates: `skill/diode-pcb-agent/assets/project-template/`

### Supported Layouts
1. **Fixture layout:** `src/board.zen` entry point
2. **Board repository:** `.zen` files at root, subcircuits in `modules/` and `components/`

Both produce identical snapshot for verification (`src/**`, `modules/**`, `components/**`, `*.zen`, `pcb.toml`, `pcb-version`).

### Naming Rules

Net and component ref names must match `[A-Za-z][A-Za-z0-9_-]*` (rendered into Zener source). Hierarchical refs use dot separator (`IMU.R17`, `POWER.C1`).

**Common violations from `pcb import`:**
| Import name | Normalized |
|-------------|------------|
| `+3_3V` | `VDD_3V3` |
| `IMU_XTAL+` | `IMU_XTAL_P` |
| `Net-(U1-VOUT)` | `NET_U1_VOUT` |
| `/IMU/BNO_SCL` | `IMU_BNO_SCL` |

Rename **only** spelling; topology and net membership unchanged.

---

## Toolchain Requirements

### Diode
- **Version:** 0.4.40 (adapter registry pinned)
- **Install:** `pcb toolchain install 0.4.40`
- **Verify:** `pcb --version`

**Pin version in project:**
```bash
mkdir -p /tmp/pcbshim
printf '#!/bin/bash\nexec "$HOME/.local/bin/pcb" +0.4.40 "$@"\n' > /tmp/pcbshim/pcb
chmod +x /tmp/pcbshim/pcb
export PATH="/tmp/pcbshim:$PATH"
```

**Known issue:** Registry rejects 0.4.41+ → `BLOCKED`. Re-capture evidence or accept lane-range (future work).

### KiCad (layout profile only)
- **Version:** 10.x (10.0.3, 10.0.5 verified)
- **Required:**
  - `kicad-cli` in `PATH`
  - `pcbnew` Python binding for DSN/SES conversion
- **Verify:**
```bash
kicad-cli version
python3 -c "import pcbnew; print(pcbnew.GetBuildVersion())"
```

### Freerouting (layout profile only)
- **Version:** 2.3.0
- **Verify:** `freerouting --help`
- **Determinism:** Verified byte-identical SES output on identical DSN input

Missing `kicad-cli`, `pcbnew`, or `freerouting` → gates `BLOCKED`, not `FAIL`.

---

## Development

### Tests
```bash
python -m pytest -q          # 304 pass / 19 skip
python -m pyright            # clean
```

**CI:** `.github/workflows/ci.yml` runs pytest on ubuntu+windows × py3.11/3.13, pyright ubuntu/3.11 only.

**Known gaps:**
- `tests/` not typechecked (pyright `include=["src"]`)
- No lint job (no ruff/black config)
- 19 Windows skips cover security-critical symlink/traversal checks

### Before Commit
```bash
python -m pytest -q
python -m pyright
git diff --check  # catch trailing whitespace
```

Never commit:
- Archives, board deliverables, `reports/` runs
- Scratch exports (`*.zip`, `*.tar.gz`, `diodeinc_scratch_*/`)
- Secrets (`.env`, `credentials.json`, private keys)

### Branch Strategy
- `master` — stable
- `feat/*` — features
- `fix/*` — bug fixes

Always push to feature branch, never directly to `master`. Use `gh pr create` for PRs.

---

## Security Findings

| ID | Severity | Issue | Location |
|----|----------|-------|----------|
| S1 | High | `reports/` symlink writes outside workspace | `state.py:70-73` |
| S2 | High | `trusted_executable_roots` never passed → any PATH exe accepted | `process.py:103` |
| S3 | Medium | Symlink check after `resolve()` always False (no-op) | `kicad.py:18-19` |
| S4 | High | `src/**` snapshot follows symlinks despite `allow_symlinks=false` | `diode.py:264,332` |
| S5 | Low | Absolute home paths in reports violate attestation portability | `process.py:117` |
| S6 | High | Env passes `HOME`/`USERPROFILE` → child reads `~/.pcb` creds | `process.py:19` |
| S7 | Critical | Backend guard is env var check, one `export` from bypass | `backends/command.py:34` |
| S8 | Medium | Secret redaction misses `xoxb-`, `-----BEGIN PRIVATE KEY-----`, JWT | `process.py:22-26` |
| S9 | **Critical** | `.git` eligible for `unlink()` in restore → repo corruption | `cli.py:413-423` |
| S10 | High | Pre-existing symlinks unlinked, never restored | `cli.py:426-429` |

**S9/S10 are destructive.** Fix before any backend run on real repo.

---

## Correctness Findings

- Windows lock never reclaimable: `os.kill(pid,0)` raises `OSError [WinError 87]`, not `ProcessLookupError` → stale lock forever (`policy.py:33-37`)
- `BLOCKED` ranked above `FAIL` → contradicts `AGENT_PROTOCOL.md:76` (`models.py:50-56`)
- `HUMAN_REVIEW` never emitted (`human_review_required` hardcoded `True`) → exit 5 dead (`models.py:16,93`)
- `PathViolation` (ValueError subclass) → exit 4, contract says 3 (`cli.py:634,692`)
- Status vocab split: generated checks accept `PASS|PASSED|OK`, locked acceptance demands `"pass"` (`diode.py:130` vs `:248`)
- Fingerprint hashes only status+message → two different compile errors identical → premature exit 4 (`cli.py:447`)
- `configured_command` validates literals it wrote, reads nothing from `project.toml` (`diode.py:55-72`)

---

## Known Limitations

### Design
- **No fabrication approval:** `PASS` ≠ production-ready. Human review required.
- **Component coverage:** Only 9 passive kinds. ICs, connectors, switches absent.
- **Crystal support:** Blocked by 1→4 GND pin mapping (adapter model limitation).
- **MPN verification:** No verified accessor → always `BLOCKED`.
- **SPICE:** Deferred to future release.

### Toolchain
- **Version pin fragile:** Adapter registry rejects 0.4.41+ → weekly upstream releases break harness.
- **Upstream supersedes harness:** `diodeinc/pcb` now ships `skills/`, `pcb dfm`, `pcb sync`, `pcb toolchain pin`—harness reimplements worse.
- **No lane-range support:** Must re-capture 148-entry evidence bundle per patch release.

### Platform
- **Windows:** Layout profile requires WSL2 or Developer Mode (symlink privilege).
- **Determinism:** Freerouting verified deterministic; placement is deterministic; but no CI job enforces it.

---

## Integration Results

**Empirical run 2026-08-29 (Diode 0.4.40, WSL2):**
- ✓ `valid-blinky` → full `PASS`
- ✓ `invalid-syntax` → `DIODE_BUILD` `FAIL`
- ✓ `invalid-connectivity`, `invalid-value` → build `PASS`, locked test `FAIL`
- ✓ KiCad 10.0.5 DRC → exit 5 for 3 violations (harness mapped correctly)
- ✓ End-to-end layout harness → generated board, ran Diode layout check, ran KiCad JSON DRC
- ✗ Generated `valid-blinky` layout → `FAIL` (missing outline, 5 silkscreen warnings, 1 unconnected)

**Evidence:** `tests/evidence/diode-0.4.40/manifest.sha256` (148 entries), `docs/spike-diode-net-naming.md`

---

## Contributing

1. Read `AGENT_PROTOCOL.md` and `REVIEW_REMEDIATION_PLAN_V2.md`
2. Fix S9/S10 first (destructive paths)
3. Add tests for new gates/adapters
4. Capture evidence before registering new component kinds
5. Run `pytest` + `pyright` + `git diff --check` before commit
6. Never edit contracts, locked TestBenches, or evidence to make tests pass

---

## License

See `LICENSE` file.

---

## Fabrication Disclaimer

**Verification `PASS` does not mean production-ready.**

All reports carry `production_ready: false` and `fabrication_approved: false`. Fabrication requires:
- Human review by qualified engineer
- Physical inspection of generated layout
- Validation against design intent and requirements
- Sign-off before manufacturing

This harness validates adherence to contracts and design rules. It does **not** validate safety, functionality, or fitness for purpose.
