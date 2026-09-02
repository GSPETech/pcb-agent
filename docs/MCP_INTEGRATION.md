# MCP Integration Guide

**Expose PCB Agent as Model Context Protocol server for AI-powered PCB design.**

---

## Overview

MCP server wraps PCB Agent orchestrator as tools callable from:
- OpenCode CLI
- Claude Desktop
- Any MCP client

**Benefits:**
- Natural language PCB design (`"buat GPS tracker"`)
- Automatic repair loops (schematic → layout → routing)
- Structured results (JSON with evidence hashes)
- No manual gate invocation

---

## Architecture

```
User
  ↓ "/pcb_agent buat GPS tracker"
OpenCode / Claude Desktop
  ↓ MCP protocol (JSON-RPC over stdio)
pcb_agent.mcp_server
  ↓ Python async
orchestrator.run_orchestrator()
  ├→ schematic_agent (max 5 iter)
  ├→ layout_agent (max 5 iter)
  └→ routing_agent (max 10 iter)
  ↓
{status: "PASS", summary: "...", files_created: [...]}
  ↓ MCP TextContent
User sees result
```

---

## Installation

### 1. Install MCP SDK

```bash
pip install mcp
```

### 2. Clone PCB Agent

```bash
cd ~/.agents/mcp-servers
git clone https://github.com/GSPETech/pcb-agent pcb-agent-mcp
cd pcb-agent-mcp
pip install -e .
```

### 3. Test Server

```bash
python -m pcb_agent.mcp_server
# Should start and wait for stdin (MCP protocol)
# Ctrl+C to exit
```

---

## OpenCode Integration

### 1. Register Server

Edit `~/.config/opencode/opencode.json`:

```json
{
  "mcpServers": {
    "pcb-agent": {
      "command": "python",
      "args": ["-m", "pcb_agent.mcp_server"],
      "env": {
        "PCB_AGENT_ROOT": "/home/user/pcb-agent",
        "PATH": "/usr/local/bin:/usr/bin:/bin"
      }
    }
  }
}
```

**Windows:**
```json
{
  "mcpServers": {
    "pcb-agent": {
      "command": "python",
      "args": ["-m", "pcb_agent.mcp_server"],
      "env": {
        "PCB_AGENT_ROOT": "C:\\Users\\user\\pcb-agent",
        "PATH": "C:\\Python311;C:\\Python311\\Scripts;%PATH%"
      }
    }
  }
}
```

### 2. Verify Registration

```bash
opencode mcp list
# Should show:
# pcb-agent: python -m pcb_agent.mcp_server
```

### 3. Test Tool Call

```bash
opencode tool call pcb-agent pcb_design \
  --task "buat schematic LED blinker" \
  --project_dir /tmp/test_board \
  --profile schematic
```

**Expected output:**
```json
{
  "status": "PASS",
  "summary": "Schematic PASS (2 iter). Ready for review.",
  "phases": {
    "schematic": {
      "status": "PASS",
      "iterations": 2,
      "files_written": ["src/board.zen", "tests/board_test.zen"]
    }
  },
  "files_created": ["src/board.zen", "tests/board_test.zen"]
}
```

---

## Claude Desktop Integration

### 1. Register Server

Edit `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "pcb-agent": {
      "command": "python3",
      "args": ["-m", "pcb_agent.mcp_server"],
      "env": {
        "PCB_AGENT_ROOT": "/Users/user/pcb-agent"
      }
    }
  }
}
```

### 2. Restart Claude Desktop

Tools appear in tool palette after restart.

### 3. Use in Chat

```
User: Design a GPS tracker PCB with IMU sensor

Claude: I'll use the pcb_design tool...
[calls pcb_design with task="GPS tracker with IMU sensor"]

Result:
✓ Schematic PASS (3 iterations)
  - Created GPS module with antenna and power
  - Created IMU module (BNO055) with I2C
  - Connected both to MCU (STM32F103)
✓ Layout PASS (2 iterations)
  - Placed GPS and IMU near antenna connector
  - Routed I2C with proper pull-ups
✓ DRC PASS (5 violations fixed)
  - Fixed 3 clearance violations
  - Fixed 2 unconnected items

Files created:
- src/gps_module.zen
- src/imu_module.zen
- src/mcu_module.zen
- tests/gps_test.zen
- tests/imu_test.zen

Report: reports/b4e2f1a3/verify-report.json
```

---

## Custom CLI Command

### Create Wrapper Script

```bash
# ~/.claude/commands/pcb_agent.sh
#!/bin/bash

TASK="$1"
PROJECT_DIR="${2:-$(pwd)/pcb_project}"
PROFILE="${3:-full}"

if [ -z "$TASK" ]; then
    echo "Usage: /pcb_agent \"task\" [project_dir] [profile]"
    echo "Example: /pcb_agent \"buat GPS tracker\" ./my_board schematic"
    exit 1
fi

opencode tool call pcb-agent pcb_design \
  --task "$TASK" \
  --project_dir "$PROJECT_DIR" \
  --profile "$PROFILE"
```

```bash
chmod +x ~/.claude/commands/pcb_agent.sh
```

### Register in CLAUDE.md

```markdown
## Custom Commands

- `/pcb_agent "task" [dir] [profile]` — delegate to pcb-agent orchestrator
  - Example: `/pcb_agent "buat schematic GPS tracker"`
  - Example: `/pcb_agent "buat power supply 5V" ./psu schematic`
  - Profiles: `schematic` (default), `layout`, `full`
  - Creates project at `./pcb_project` or specified dir
```

### Usage

```bash
# From any directory in OpenCode session
/pcb_agent "buat GPS tracker"

# Specify output directory
/pcb_agent "buat IMU board" ./imu_project

# Schematic only
/pcb_agent "buat power regulator" ./psu schematic
```

---

## Available Tools

### `pcb_design`

**Purpose:** End-to-end PCB design (schematic → layout → routing)

**Input:**
```json
{
  "task": "buat GPS tracker dengan IMU sensor",
  "project_dir": "/tmp/gps_tracker",
  "profile": "full"
}
```

**Fields:**
- `task` (required): Natural language description
- `project_dir` (required): Absolute path to project (created if absent)
- `profile` (optional): `schematic` | `layout` | `full` (default: `full`)

**Output:**
```json
{
  "status": "PASS | FAIL | BLOCKED | HUMAN_REVIEW",
  "summary": "Schematic PASS (3 iter), Layout PASS (2 iter), DRC PASS (7 violations)",
  "phases": {
    "schematic": {"status": "PASS", "iterations": 3, "files_written": [...]},
    "layout": {"status": "PASS", "iterations": 2},
    "routing": {"status": "PASS", "violations_fixed": 7}
  },
  "files_created": ["src/gps_module.zen", "tests/gps_test.zen"]
}
```

**Profiles:**
- `schematic`: CONTRACT → DIODE_BUILD → CONNECTIVITY → SPECIFICATION
- `layout`: (all schematic) → LAYOUT_GENERATE → PLACEMENT → ROUTE → LAYOUT_SYNC → KICAD_DRC
- `full`: Same as `layout`

---

### `pcb_verify`

**Purpose:** Verify existing project (no edits)

**Input:**
```json
{
  "project_dir": "/tmp/gps_tracker",
  "profile": "schematic"
}
```

**Fields:**
- `project_dir` (required): Absolute path
- `profile` (required): `schematic` | `layout`

**Output:** Same as `./pcb-agent verify --format json`

```json
{
  "status": "PASS",
  "gates": [
    {"id": "CONTRACT", "status": "PASS", "duration_ms": 12},
    {"id": "DIODE_BUILD", "status": "PASS", "duration_ms": 523},
    {"id": "CONNECTIVITY", "status": "PASS", "duration_ms": 187}
  ],
  "summary": {"passed": 4, "failed": 0, "blocked": 0}
}
```

---

### `pcb_repair`

**Purpose:** Fix specific gate failure with loop detection

**Input:**
```json
{
  "project_dir": "/tmp/gps_tracker",
  "gate": "KICAD_DRC",
  "max_iterations": 5
}
```

**Fields:**
- `project_dir` (required): Absolute path
- `gate` (required): `CONNECTIVITY` | `SPECIFICATION` | `PLACEMENT` | `ROUTE` | `KICAD_DRC`
- `max_iterations` (optional): Max repair attempts (default: 5)

**Output:**
```json
{
  "status": "PASS | HUMAN_REVIEW",
  "iterations": 3,
  "fixes_applied": [
    "Increased track width 0.2mm → 0.25mm (clearance violation)",
    "Added via to GND plane (unconnected net)",
    "Moved C1 away from edge (courtyard violation)"
  ]
}
```

---

## Error Handling

### Tool Not Found

```json
{
  "error": "Tool pcb_design not found",
  "available_tools": ["pcb_design", "pcb_verify", "pcb_repair"]
}
```

**Fix:** Check MCP server registration in `opencode.json`.

---

### Module Import Error

```
ModuleNotFoundError: No module named 'mcp'
```

**Fix:**
```bash
pip install mcp
```

---

### Project Directory Not Absolute

```json
{
  "status": "BLOCKED",
  "message": "project_dir must be absolute: ./my_board"
}
```

**Fix:** Use absolute path:
```bash
/pcb_agent "task" "$(pwd)/my_board"
```

---

### Toolchain Not Found

```json
{
  "status": "BLOCKED",
  "message": "pcb command not found in PATH"
}
```

**Fix:**
```bash
# Add to opencode.json env
"PATH": "/home/user/.local/bin:/usr/local/bin:/usr/bin:/bin"
```

---

## Agent Orchestrator Details

### Schematic Agent

1. Parse task → extract module name + requirements
2. Generate contracts (SPEC.json, expected-connectivity.json, ACCEPTANCE.json)
3. Generate Zener source (src/board.zen)
4. Generate locked TestBench (tests/board_test.zen)
5. Run `verify --profile schematic`
6. If FAIL → parse diagnostics → regenerate → goto 5 (max 5 iter)
7. If PASS → return

**No-progress detection:** Hash (status + message) → if identical to previous → exit.

---

### Layout Agent

1. Read schematic result → extract component list
2. Run `pcb layout` → generate `.kicad_pcb`
3. Run `PLACEMENT` gate → deterministic placement + outline
4. Run `verify --profile layout`
5. If FAIL → adjust constraints → goto 2 (max 5 iter)
6. If PASS → return

**Determinism:** Placement groups by module (from Zener `Path` property), allocates grid cells, derives Edge.Cuts from bounding box.

---

### Routing Agent

1. Read layout result → get `.kicad_pcb` path
2. Export DSN via `pcbnew` Python
3. Run `freerouting` → get SES
4. Import SES via `pcbnew` Python
5. Run `kicad-cli pcb drc`
6. If violations → parse → adjust rules → goto 2 (max 10 iter)
7. If PASS → return

**Freerouting determinism:** Empirically verified byte-identical SES on same DSN.

---

## Streaming Progress (Future)

Current implementation returns only final result. For long-running layout/routing, streaming would help:

```python
@app.call_tool()
async def call_tool(name: str, arguments: dict):
    if name == "pcb_design":
        async for progress in run_orchestrator_streaming(...):
            yield TextContent(type="text", text=json.dumps(progress))
```

**Output:**
```json
{"phase": "schematic", "iteration": 1, "status": "running"}
{"phase": "schematic", "iteration": 1, "status": "FAIL", "message": "Net VDD missing"}
{"phase": "schematic", "iteration": 2, "status": "running"}
{"phase": "schematic", "iteration": 2, "status": "PASS"}
{"phase": "layout", "iteration": 1, "status": "running"}
...
{"status": "PASS", "summary": "..."}
```

ponytail: no streaming, no cancel. Add when long board runs (>2min) need visibility.

---

## Security Notes

MCP server runs in same process as OpenCode → inherits same privileges.

**Workspace isolation:** `project_dir` canonicalized via `Path.resolve()`, checked against workspace root.

**Protected files:** Contracts and locked TestBenches hash-verified, edit-denied during backend runs.

**Known issues:** See README Security Findings (S1-S10).

---

## Testing

### Unit Test

```python
# tests/test_mcp_server.py
import pytest
from pcb_agent.mcp_server import app

@pytest.mark.asyncio
async def test_pcb_design_tool():
    tools = await app.list_tools()
    assert any(t.name == "pcb_design" for t in tools)

@pytest.mark.asyncio
async def test_pcb_design_call(tmp_path):
    result = await app.call_tool("pcb_design", {
        "task": "buat LED blinker",
        "project_dir": str(tmp_path / "test_board"),
        "profile": "schematic"
    })
    assert len(result) == 1
    data = json.loads(result[0].text)
    assert data["status"] in ["PASS", "FAIL", "BLOCKED"]
```

### Integration Test

```bash
# Start server in background
python -m pcb_agent.mcp_server &
MCP_PID=$!

# Send JSON-RPC request
echo '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"pcb_design","arguments":{"task":"buat LED blinker","project_dir":"/tmp/test","profile":"schematic"}}}' | nc localhost 5000

# Cleanup
kill $MCP_PID
```

---

## Troubleshooting

### Server Not Responding

**Check registration:**
```bash
opencode mcp list
opencode mcp test pcb-agent
```

**Check logs:**
```bash
tail -f ~/.config/opencode/logs/mcp-pcb-agent.log
```

---

### Tool Call Timeout

**Increase timeout in opencode.json:**
```json
{
  "mcpServers": {
    "pcb-agent": {
      "command": "python",
      "args": ["-m", "pcb_agent.mcp_server"],
      "timeout": 600000
    }
  }
}
```

---

### Result Truncated

MCP has no built-in size limit, but client may truncate.

**Workaround:** Write full report to file, return only summary:
```python
result = await run_orchestrator(...)
report_path = f"{project_dir}/reports/{run_id}/verify-report.json"
with open(report_path, "w") as f:
    json.dump(result, f, indent=2)

return [TextContent(type="text", text=json.dumps({
    "status": result["status"],
    "summary": result["summary"],
    "report_path": report_path
}))]
```

---

## Examples

### GPS Tracker

```bash
/pcb_agent "buat GPS tracker dengan:
- GPS module NEO-6M
- STM32F103 MCU
- USB connector untuk power dan data
- LED indicator
- Button untuk reset"
```

**Result:**
- `src/gps_module.zen` — NEO-6M + antenna + power
- `src/mcu_module.zen` — STM32F103 + crystal + USB
- `src/ui_module.zen` — LED + button
- `tests/` — locked TestBenches
- `build/board.kicad_pcb` — routed PCB

---

### IMU Sensor Board

```bash
/pcb_agent "buat IMU sensor board:
- BNO055 9-axis IMU
- I2C interface
- 3.3V LDO regulator
- Mounting holes
- 2-layer board" ./imu_board layout
```

**Result:**
- Schematic with BNO055 + LDO + I2C pull-ups
- Layout with 4 mounting holes
- Routed I2C with proper trace width
- DRC clean

---

## Next Steps

- Read [Orchestrator source](../src/pcb_agent/orchestrator.py)
- Read [Agent implementations](../src/pcb_agent/agents/)
- Try repair loop on failing fixture
- Build your own agent with MCP client SDK
