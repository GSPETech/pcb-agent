# PCB Agent MCP Server

Model Context Protocol server untuk pcb-agent. Expose orchestrator sebagai tool
yang bisa dipanggil dari opencode, Claude Desktop, atau CLI lain.

## Installation

```bash
cd ~/.agents/mcp-servers
git clone https://github.com/GSPETech/pcb-agent pcb-agent-mcp
cd pcb-agent-mcp
pip install -e .
```

Register di `~/.config/opencode/opencode.json`:

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

## Tools exposed

### `pcb_design`

Input:
```json
{
  "task": "buat schematic GPS tracker",
  "project_dir": "/tmp/gps_tracker",
  "profile": "schematic | layout | full"
}
```

Output:
```json
{
  "status": "PASS | FAIL | BLOCKED | HUMAN_REVIEW",
  "summary": "Schematic PASS (3 iter), Layout PASS (2 iter), DRC PASS (4 iter)",
  "files_created": ["src/gps_module.zen", "tests/gps_test.zen"],
  "artifacts": ["reports/af71663/raw/kicad-drc.json"]
}
```

### `pcb_verify`

Input:
```json
{
  "project_dir": "/tmp/gps_tracker",
  "profile": "schematic | layout"
}
```

Output: sama dengan `pcb-agent verify --format json`

### `pcb_repair`

Input:
```json
{
  "project_dir": "/tmp/gps_tracker",
  "gate": "CONNECTIVITY | SPECIFICATION | PLACEMENT | ROUTE | KICAD_DRC",
  "max_iterations": 5
}
```

Output:
```json
{
  "status": "PASS | HUMAN_REVIEW",
  "iterations": 3,
  "fixes_applied": ["renamed net +5V → VDD_5V", "increased clearance 0.2→0.25mm"]
}
```

## CLI integration

Add command ke opencode:

```bash
# ~/.claude/commands/pcb_agent.sh
#!/bin/bash
# Usage: /pcb_agent "buat schematic GPS"

TASK="$1"
PROJECT_DIR="${2:-$(pwd)/pcb_project}"

opencode tool call pcb-agent pcb_design \
  --task "$TASK" \
  --project_dir "$PROJECT_DIR" \
  --profile full
```

Register di `~/.claude/CLAUDE.md`:

```markdown
## Custom Commands

- `/pcb_agent "task"` — delegate to pcb-agent orchestrator
  - Example: `/pcb_agent "buat schematic GPS tracker"`
  - Creates project di `./pcb_project` atau `--dir` path
  - Full workflow: schematic → layout → routing
```

## Usage from opencode

```
user: /pcb_agent "buat schematic GPS tracker"
  ↓
opencode → MCP call pcb_design
  ↓
pcb-agent orchestrator → schematic-agent → layout-agent → routing-agent
  ↓
return summary ke user
```

## Usage from code

```python
from mcp import ClientSession
from mcp.client.stdio import stdio_client

async with stdio_client(["python", "-m", "pcb_agent.mcp_server"]) as (read, write):
    async with ClientSession(read, write) as session:
        result = await session.call_tool("pcb_design", {
            "task": "buat schematic GPS tracker",
            "project_dir": "/tmp/gps",
            "profile": "full"
        })
        print(result.content)
```

## Security

- MCP server runs in same process as opencode → no network boundary
- Workspace isolation via `project_dir` absolute path check
- `pcb-agent verify` policy enforced (no edit contracts during backend run)
- Symlink/traversal checks active

## Implementation

File `src/pcb_agent/mcp_server.py`:

```python
from mcp.server import Server
from mcp.types import Tool, TextContent
import json, asyncio

app = Server("pcb-agent")

@app.list_tools()
async def list_tools():
    return [
        Tool(name="pcb_design", description="Design PCB end-to-end", 
             inputSchema={
                 "type": "object",
                 "properties": {
                     "task": {"type": "string"},
                     "project_dir": {"type": "string"},
                     "profile": {"type": "string", "enum": ["schematic", "layout", "full"]}
                 },
                 "required": ["task", "project_dir"]
             })
    ]

@app.call_tool()
async def call_tool(name: str, arguments: dict):
    if name == "pcb_design":
        # Invoke orchestrator
        from .orchestrator import run_orchestrator
        result = await run_orchestrator(
            task=arguments["task"],
            project_dir=arguments["project_dir"],
            profile=arguments.get("profile", "full")
        )
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
```

ponytail: no streaming progress, no cancel. Add when long-running board needed.
