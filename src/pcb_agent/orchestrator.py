"""
Orchestrator agent — coordinate schematic → layout → routing workflow.
"""

import json
import hashlib
from pathlib import Path
from typing import Dict, Any, Literal

ProfileType = Literal["schematic", "layout", "full"]
StatusType = Literal["PASS", "FAIL", "BLOCKED", "HUMAN_REVIEW"]


async def run_orchestrator(
    task: str, project_dir: str, profile: ProfileType = "full"
) -> Dict[str, Any]:
    """
    Delegate to specialized agents based on profile.
    
    Args:
        task: User task description
        project_dir: Absolute path to project
        profile: schematic | layout | full
    
    Returns:
        {
            "status": "PASS | FAIL | BLOCKED | HUMAN_REVIEW",
            "summary": "...",
            "phases": {"schematic": {...}, "layout": {...}, "routing": {...}},
            "files_created": [...],
        }
    """
    project_path = Path(project_dir).resolve()
    if not project_path.is_absolute():
        return {
            "status": "BLOCKED",
            "message": f"project_dir must be absolute: {project_dir}",
        }

    phases = {}
    files_created = []

    # Parse intent
    if profile == "schematic" or profile == "full":
        # Delegate to schematic-agent
        from .agents.schematic import run_schematic_agent

        schematic_input = {
            "project_dir": str(project_path),
            "module_name": _extract_module_name(task),
            "requirements": _extract_requirements(task),
            "profile": "schematic",
        }

        schematic_result = await run_schematic_agent(schematic_input)
        phases["schematic"] = schematic_result
        files_created.extend(schematic_result.get("files_written", []))

        if schematic_result["status"] != "PASS":
            return {
                "status": schematic_result["status"],
                "summary": f"Schematic {schematic_result['status']} after {schematic_result.get('iterations', 0)} iterations",
                "phases": phases,
                "files_created": files_created,
            }

    if profile == "layout" or profile == "full":
        # Delegate to layout-agent
        from .agents.layout import run_layout_agent

        layout_input = {
            "project_dir": str(project_path),
            "profile": "layout",
            "constraints": _extract_constraints(task),
        }

        layout_result = await run_layout_agent(layout_input)
        phases["layout"] = layout_result

        if layout_result["status"] != "PASS":
            return {
                "status": layout_result["status"],
                "summary": f"Schematic PASS, Layout {layout_result['status']} after {layout_result.get('iterations', 0)} iterations",
                "phases": phases,
                "files_created": files_created,
            }

        # Delegate to routing-agent
        from .agents.routing import run_routing_agent

        routing_input = {
            "project_dir": str(project_path),
            "board_file": str(project_path / "build" / "board.kicad_pcb"),
            "profile": "layout",
        }

        routing_result = await run_routing_agent(routing_input)
        phases["routing"] = routing_result

        if routing_result["status"] != "PASS":
            return {
                "status": routing_result["status"],
                "summary": f"Schematic PASS, Layout PASS, Routing {routing_result['status']} ({routing_result.get('violations_fixed', 0)} violations)",
                "phases": phases,
                "files_created": files_created,
            }

    # All PASS
    summary_parts = []
    if "schematic" in phases:
        summary_parts.append(
            f"Schematic PASS ({phases['schematic'].get('iterations', 0)} iter)"
        )
    if "layout" in phases:
        summary_parts.append(
            f"Layout PASS ({phases['layout'].get('iterations', 0)} iter)"
        )
    if "routing" in phases:
        summary_parts.append(
            f"DRC PASS ({phases['routing'].get('violations_fixed', 0)} violations fixed)"
        )

    return {
        "status": "PASS",
        "summary": ", ".join(summary_parts) + ". Ready for review.",
        "phases": phases,
        "files_created": files_created,
    }


def _extract_module_name(task: str) -> str:
    """Extract module name from task description."""
    # Simple heuristic: "buat schematic GPS tracker" → "GPS_TRACKER"
    tokens = task.upper().split()
    if "SCHEMATIC" in tokens:
        idx = tokens.index("SCHEMATIC")
        return "_".join(tokens[idx + 1 :]).replace(" ", "_")
    return "MODULE"


def _extract_requirements(task: str) -> list:
    """Extract requirements from task description."""
    # Placeholder: return generic requirements
    return [
        "Component placement",
        "Net connectivity",
        "Design rule compliance",
    ]


def _extract_constraints(task: str) -> dict:
    """Extract board constraints from task description."""
    # Placeholder: return default constraints
    return {
        "board_outline": {"width": 50, "height": 30, "unit": "mm"},
        "layer_count": 2,
    }
