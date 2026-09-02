#!/usr/bin/env python3
"""
MCP server untuk pcb-agent orchestrator.
Expose tools: pcb_design, pcb_verify, pcb_repair.
"""

from mcp.server import Server
from mcp.types import Tool, TextContent
import json
import os
import sys

app = Server("pcb-agent")


@app.list_tools()
async def list_tools():
    return [
        Tool(
            name="pcb_design",
            description="Design PCB end-to-end: schematic → layout → routing",
            inputSchema={
                "type": "object",
                "properties": {
                    "task": {
                        "type": "string",
                        "description": "User task, e.g. 'buat schematic GPS tracker'",
                    },
                    "project_dir": {
                        "type": "string",
                        "description": "Absolute path to project directory",
                    },
                    "profile": {
                        "type": "string",
                        "enum": ["schematic", "layout", "full"],
                        "description": "Workflow phase: schematic-only, layout-only, or full cascade",
                    },
                },
                "required": ["task", "project_dir"],
            },
        ),
        Tool(
            name="pcb_verify",
            description="Verify existing PCB project",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_dir": {"type": "string"},
                    "profile": {
                        "type": "string",
                        "enum": ["schematic", "layout"],
                    },
                },
                "required": ["project_dir", "profile"],
            },
        ),
        Tool(
            name="pcb_repair",
            description="Repair specific gate failure",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_dir": {"type": "string"},
                    "gate": {
                        "type": "string",
                        "enum": [
                            "CONNECTIVITY",
                            "SPECIFICATION",
                            "PLACEMENT",
                            "ROUTE",
                            "KICAD_DRC",
                        ],
                    },
                    "max_iterations": {"type": "integer", "default": 5},
                },
                "required": ["project_dir", "gate"],
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict):
    if name == "pcb_design":
        from .orchestrator import run_orchestrator

        result = await run_orchestrator(
            task=arguments["task"],
            project_dir=arguments["project_dir"],
            profile=arguments.get("profile", "full"),
        )
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    elif name == "pcb_verify":
        from .cli import verify_project

        result = verify_project(
            project_dir=arguments["project_dir"],
            profile=arguments["profile"],
            format="json",
        )
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    elif name == "pcb_repair":
        from .repair import run_repair

        result = await run_repair(
            project_dir=arguments["project_dir"],
            gate=arguments["gate"],
            max_iterations=arguments.get("max_iterations", 5),
        )
        return [TextContent(type="text", text=json.dumps(result, indent=2))]


async def main():
    from mcp.server.stdio import stdio_server

    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
