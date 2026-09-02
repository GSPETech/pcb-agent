"""
Layout agent implementation.
Run placement + routing, parse failures, adjust constraints.
"""

import json
import subprocess
from pathlib import Path
from typing import Dict, Any


async def run_layout_agent(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Run PLACEMENT + ROUTE gates, parse failures, loop repair.
    
    Returns:
        {
            "status": "PASS | FAIL | BLOCKED | HUMAN_REVIEW",
            "gates": {...},
            "iterations": N,
            "message": "..."
        }
    """
    project_dir = Path(input_data["project_dir"])
    constraints = input_data.get("constraints", {})
    
    max_iterations = 5
    iteration = 0
    last_fingerprint = None
    
    while iteration < max_iterations:
        iteration += 1
        
        # Run verify --profile layout
        result = _run_verify(project_dir, "layout")
        
        if result["status"] == "BLOCKED":
            return {
                "status": "BLOCKED",
                "gates": result.get("checks", {}),
                "iterations": iteration,
                "message": result.get("message", "unknown blocker"),
            }
        
        if result["status"] == "PASS":
            return {
                "status": "PASS",
                "gates": result.get("checks", {}),
                "iterations": iteration,
                "message": f"layout verified, {iteration} iterations",
            }
        
        # FAIL: check which gate
        gates = result.get("checks", {})
        
        if gates.get("PLACEMENT", {}).get("status") == "FAIL":
            _repair_placement(project_dir, constraints, gates["PLACEMENT"])
        
        elif gates.get("ROUTE", {}).get("status") == "FAIL":
            _repair_route(project_dir, constraints, gates["ROUTE"])
        
        else:
            # Unknown failure
            return {
                "status": "HUMAN_REVIEW",
                "gates": gates,
                "iterations": iteration,
                "message": "unknown gate failure",
            }
        
        # Check stuck
        import hashlib
        fp = hashlib.sha256(json.dumps(gates, sort_keys=True).encode()).hexdigest()
        if fp == last_fingerprint:
            return {
                "status": "HUMAN_REVIEW",
                "gates": gates,
                "iterations": iteration,
                "message": "stuck after constraint edit, same failure 2×",
            }
        last_fingerprint = fp
    
    return {
        "status": "HUMAN_REVIEW",
        "gates": gates,
        "iterations": iteration,
        "message": f"max {max_iterations} iterations exceeded",
    }


def _run_verify(project_dir: Path, profile: str) -> Dict[str, Any]:
    """Run pcb-agent verify --profile layout."""
    cmd = [
        "python", "-m", "pcb_agent.cli",
        "verify",
        "--project", str(project_dir),
        "--profile", profile,
        "--format", "json"
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {
            "status": "BLOCKED",
            "message": f"verify failed: {result.stderr}",
        }


def _repair_placement(project_dir: Path, constraints: dict, gate_result: dict):
    """
    Diagnose PLACEMENT failure and adjust constraints.
    
    Common failures:
    - Courtyard overlap → increase spacing
    - Component off-board → enlarge outline
    """
    message = gate_result.get("message", "")
    
    # Placeholder: increase board size 10%
    outline = constraints.get("board_outline", {"width": 50, "height": 30})
    outline["width"] = int(outline["width"] * 1.1)
    outline["height"] = int(outline["height"] * 1.1)
    
    # Write constraint to project metadata (not implemented in harness yet)
    # In real implementation, write to project.toml [layout] section
    pass


def _repair_route(project_dir: Path, constraints: dict, gate_result: dict):
    """
    Diagnose ROUTE failure and adjust design rules.
    
    Common failures:
    - Unrouted nets → relax clearance
    - Too many vias → increase layer count
    """
    message = gate_result.get("message", "")
    
    # Placeholder: relax clearance by 10%
    # Real implementation would edit freerouting DSN rules
    pass
