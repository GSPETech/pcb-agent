# Quick Start Guide

**Get running with PCB Agent in 5 minutes.**

---

## Prerequisites

- Python 3.11+
- [Diode toolchain](https://github.com/diodeinc/pcb) 0.4.40+
- (Optional) KiCad 10.x for layout profile
- (Optional) Freerouting 2.3.0 for autorouting

---

## Installation

```bash
# Clone repo
git clone https://github.com/GSPETech/pcb-agent
cd pcb-agent

# Optional: editable install
python -m pip install -e .

# Verify
./pcb-agent --version
```

---

## First Verification

```bash
# Check toolchain
./pcb-agent doctor --project fixtures/valid-blinky --format json

# Run schematic verification
./pcb-agent verify --project fixtures/valid-blinky --profile schematic
```

**Expected output:**
```
✓ CONTRACT        PASS  (12ms)
✓ DIODE_BUILD     PASS  (523ms)
✓ CONNECTIVITY    PASS  (187ms)
✓ SPECIFICATION   PASS  (201ms)

Status: PASS
Report: reports/a3f2e1c4/verify-report.json
```

---

## Try Invalid Fixture

```bash
./pcb-agent verify --project fixtures/invalid-connectivity --profile schematic
```

**Expected output:**
```
✓ CONTRACT        PASS  (11ms)
✓ DIODE_BUILD     PASS  (498ms)
✗ CONNECTIVITY    FAIL  (192ms)
  Net GPIO_LED: expected [MCU.PA5, R1.2], found [MCU.PA5]
⊘ SPECIFICATION   BLOCKED (dependency failed)

Status: FAIL
```

---

## Create Your First Project

### 1. Initialize

```bash
mkdir my_board
cd my_board

# Copy template
cp -r ../skill/diode-pcb-agent/assets/project-template/* .
```

**Result:**
```
my_board/
├── project.toml
├── SPEC.json
├── ACCEPTANCE.json
├── expected-connectivity.json
├── src/
│   └── board.zen
└── tests/
    └── board_test.zen
```

### 2. Edit Source

```python
# src/board.zen
from diode import Module, Resistor, LED

class Board(Module):
    def circuit(self):
        self.vdd = Power()
        self.gnd = Ground()
        
        # LED with current limiting resistor
        self.r1 = Resistor("330Ω", "0603")
        self.led1 = LED("red", "0603")
        
        # Connections
        self.vdd.connect(self.r1.p1)
        self.r1.p2.connect(self.led1.anode)
        self.led1.cathode.connect(self.gnd)
```

### 3. Write Contracts

```json
// expected-connectivity.json
{
  "components": {
    "R1": {
      "kind": "resistor",
      "value": "330Ω",
      "package": "0603"
    },
    "LED1": {
      "kind": "led",
      "package": "0603"
    }
  },
  "nets": {
    "VDD": {"members": ["R1.1"]},
    "NET_R_LED": {"members": ["R1.2", "LED1.anode"]},
    "GND": {"members": ["LED1.cathode"]}
  }
}
```

```json
// SPEC.json
{
  "requirements": [
    {
      "id": "REQ-001",
      "description": "Current limiting resistor",
      "type": "specification",
      "constraints": [
        {"type": "value", "component": "R1", "expected": "330Ω"}
      ]
    }
  ]
}
```

```json
// ACCEPTANCE.json
{
  "checks": [
    {
      "id": "ACC-001",
      "requirement": "REQ-001",
      "test": "board_test",
      "description": "Verify R1 value"
    }
  ]
}
```

### 4. Write TestBench

```python
# tests/board_test.zen
from diode import *

def test_current_limiting(module, inputs):
    r1 = module.components()["R1"]
    check(r1.resistance == "330Ω", "R1 value")
    check(r1.package == "0603", "R1 package")
```

### 5. Verify

```bash
./pcb-agent verify --project . --profile schematic
```

---

## Layout Workflow

### Requirements

```bash
# Install KiCad
sudo add-apt-repository ppa:kicad/kicad-8.0-releases
sudo apt update
sudo apt install kicad

# Install Freerouting
wget https://github.com/freerouting/freerouting/releases/download/v2.3.0/freerouting-2.3.0.jar
echo '#!/bin/bash\njava -jar /path/to/freerouting-2.3.0.jar "$@"' > ~/bin/freerouting
chmod +x ~/bin/freerouting

# Verify
kicad-cli version
freerouting --help
python3 -c "import pcbnew; print(pcbnew.GetBuildVersion())"
```

### Run Layout

```bash
./pcb-agent verify --project fixtures/valid-blinky --profile layout
```

**Gates executed:**
1. CONTRACT (parse contracts)
2. DIODE_BUILD (build schematic)
3. CONNECTIVITY (locked TestBench)
4. SPECIFICATION (locked TestBench)
5. LAYOUT_GENERATE (pcb layout)
6. PLACEMENT (deterministic component placement)
7. ROUTE (Freerouting DSN/SES)
8. LAYOUT_SYNC (pcb layout --check)
9. KICAD_DRC (kicad-cli pcb drc)

**Output:**
```
build/
├── board.kicad_pcb   # Generated PCB
├── board.dsn         # Freerouting input
└── board.ses         # Freerouting output

reports/<run-id>/
├── verify-report.json
├── summary.md
└── raw/
    ├── connectivity-result.json
    ├── specification-result.json
    └── kicad-drc.json
```

---

## AI Orchestrator (MCP)

### Setup

1. **Install MCP server:**
```bash
cd ~/.agents/mcp-servers
git clone https://github.com/GSPETech/pcb-agent pcb-agent-mcp
cd pcb-agent-mcp
pip install -e .
pip install mcp
```

2. **Configure opencode:**
```json
// ~/.config/opencode/opencode.json
{
  "mcpServers": {
    "pcb-agent": {
      "command": "python",
      "args": ["-m", "pcb_agent.mcp_server"],
      "env": {
        "PCB_AGENT_ROOT": "/home/user/pcb-agent"
      }
    }
  }
}
```

3. **Add command:**
```bash
# ~/.claude/commands/pcb_agent.sh
#!/bin/bash
TASK="$1"
DIR="${2:-./pcb_project}"
opencode tool call pcb-agent pcb_design --task "$TASK" --project_dir "$DIR" --profile full
chmod +x ~/.claude/commands/pcb_agent.sh
```

### Usage

```bash
# Full workflow
/pcb_agent "buat GPS tracker dengan IMU sensor"

# Output:
# ✓ Schematic PASS (3 iterations)
# ✓ Layout PASS (2 iterations)  
# ✓ DRC PASS (5 violations fixed)
# Files: src/gps_module.zen, src/imu_module.zen, tests/gps_test.zen
# Report: reports/b4e2f1a3/verify-report.json
```

---

## Common Issues

### `BLOCKED: adapter for resistor not verified against pcbc 0.4.42`

**Cause:** Registry pinned to 0.4.40, but 0.4.42 installed.

**Fix (temporary):**
```bash
pcb toolchain install 0.4.40
mkdir -p /tmp/pcbshim
printf '#!/bin/bash\nexec "$HOME/.local/bin/pcb" +0.4.40 "$@"\n' > /tmp/pcbshim/pcb
chmod +x /tmp/pcbshim/pcb
export PATH="/tmp/pcbshim:$PATH"
./pcb-agent verify --project . --profile schematic
```

**Fix (permanent):** Wait for lane-range adapter support (issue #10).

---

### Windows `os error 1314` (symlink privilege)

**Cause:** `pcb build` creates symlinks without privilege.

**Fix 1 (recommended):** Use WSL2
```powershell
wsl -d Ubuntu-24.04
cd /mnt/c/Users/user/pcb-agent
./pcb-agent verify --project fixtures/valid-blinky --profile schematic
```

**Fix 2:** Enable Developer Mode (Settings → Update & Security → For developers → Developer Mode)

---

### `BLOCKED: kicad-cli not found`

**Cause:** KiCad not in PATH or not installed.

**Fix:**
```bash
# Ubuntu/Debian
sudo apt install kicad

# macOS
brew install kicad

# Windows
# Download from https://www.kicad.org/download/
# Add to PATH: C:\Program Files\KiCad\8.0\bin
```

---

### `ModuleNotFoundError: No module named 'pcbnew'`

**Cause:** KiCad Python binding not installed or wrong Python version.

**Fix:**
```bash
# Ubuntu/Debian (installed with kicad package)
python3 -c "import pcbnew"

# If error: use system Python that KiCad was built against
which python3  # /usr/bin/python3
/usr/bin/python3 -m pip install --user -e .
```

---

### Stale lock file

**Symptom:**
```
Error: Lock file exists: .pcb-agent-lock
```

**Cause:** Previous run crashed without cleanup.

**Fix:**
```bash
rm .pcb-agent-lock
```

**Permanent fix:** Issue #8 (Windows lock reclaim broken).

---

## Next Steps

- Read [Architecture](ARCHITECTURE.md) for design details
- Read [AGENT_PROTOCOL.md](../AGENT_PROTOCOL.md) for contract semantics
- Try [invalid fixtures](../fixtures/) to see failure modes
- Build layout workflow with `--profile layout`
- Integrate with your AI agent via MCP

---

## Getting Help

- Issues: https://github.com/GSPETech/pcb-agent/issues
- Docs: https://github.com/GSPETech/pcb-agent/tree/master/docs
- Diode upstream: https://github.com/diodeinc/pcb
