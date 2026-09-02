"""Repair agent — targeted fix for specific gate failure."""

import json
from pathlib import Path
from typing import Dict, Any

from .agents.schematic import _run_verify, _repair_failure, _compute_fingerprint
from .agents.routing import _run_kicad_drc, _diagnose_and_fix


async def run_repair(
    project_dir: str, gate: str, max_iterations: int = 5
) -> Dict[str, Any]:
    """
    Repair specific gate failure in isolation.
    
    Args:
        project_dir: Absolute path to project
        gate: CONNECTIVITY | SPECIFICATION | PLACEMENT | ROUTE | KICAD_DRC
        max_iterations: Max repair attempts
    
    Returns:
        {
            "status": "PASS | HUMAN_REVIEW",
            "iterations": N,
            "fixes_applied": [...]
        }
    """
    project_path = Path(project_dir).resolve()
    
    if gate in ["CONNECTIVITY", "SPECIFICATION"]:
        return await _repair_schematic_gate(project_path, gate, max_iterations)
    elif gate in ["PLACEMENT", "ROUTE"]:
        return await _repair_layout_gate(project_path, gate, max_iterations)
    elif gate == "KICAD_DRC":
        return await _repair_drc(project_path, max_iterations)
    else:
        return {
            "status": "BLOCKED",
            "message": f"unknown gate: {gate}",
        }


async def _repair_schematic_gate(
    project_dir: Path, gate: str, max_iterations: int
) -> Dict[str, Any]:
    """Repair CONNECTIVITY or SPECIFICATION gate."""
    iteration = 0
    last_fingerprint = None
    fixes_applied = []
    
    while iteration < max_iterations:
        iteration += 1
        
        result = _run_verify(project_dir, "schematic")
        
        if result["status"] == "PASS":
            return {
                "status": "PASS",
                "iterations": iteration,
                "fixes_applied": fixes_applied,
            }
        
        # Check if target gate passed
        gate_status = result.get("checks", ).get(gate, {}).get("status")
        if gate_status == "PASS":
            return {
                "status": "PASS",
                "iterations": iteration,
                "fixes_applied": fixes_applied,
            }
        
        # Detect stuck
        fp = _compute_fingerprint(result)
        if fp == last_fingerprint:
            return {
                "status": "HUMAN_REVIEW",
                "iterations": iteration,
                "fixes_applied": fixes_applied,
                "message": "stuck, same failure 2×",
            }
        last_fingerprint = fp
        
        # Apply repair
        _repair_failure(project_dir, "MODULE", result)
        fixes_applied.append(f"iteration {iteration}: attempted repair")
    
    return {
        "status": "HUMAN_REVIEW",
        "iterations": iteration,
        "fixes_applied": fixes_applied,
        "message": f"max {max_iterations} iterations exceeded",
    }


async def _repair_layout_gate(
    project_dir: Path, gate: str, max_iterations: int
) -> Dict[str, Any]:
    """Repair PLACEMENT or ROUTE gate."""
    from .agents.layout import _run_verify, _repair_placement, _repair_route
    
    iteration = 0
    last_fingerprint = None
    fixes_applied = []
    
    while iteration < max_iterations:
        iteration += 1
        
        result = _run_verify(project_dir, "layout")
        
        gate_status = result.get("checks", {}).get(gate, {}).get("status")
        if gate_status == "PASS":
            return {
                "status": "PASS",
                "iterations": iteration,
                "fixes_applied": fixes_applied,
            }
        
        # Detect stuck
        import hashlib
        fp = hashlib.sha256(
            json.dumps(result.get("checks", {}), sort_keys=True).encode()
        ).hexdigest()
        if fp == last_fingerprint:
            return {
                "status": "HUMAN_REVIEW",
                "iterations": iteration,
                "fixes_applied": fixes_applied,
                "message": "stuck, same failure 2×",
            }
        last_fingerprint = fp
        
        # Apply repair
        if gate == "PLACEMENT":
            _repair_placement(project_dir, {}, result["checks"]["PLACEMENT"])
            fixes_applied.append(f"iteration {iteration}: adjusted board outline")
        elif gate == "ROUTE":
            _repair_route(project_dir, {}, result["checks"]["ROUTE"])
            fixes_applied.append(f"iteration {iteration}: relaxed clearance")
    
    return {
        "status": "HUMAN_REVIEW",
        "iterations": iteration,
        "fixes_applied": fixes_applied,
        "message": f"max {max_iterations} iterations exceeded",
    }


async def _repair_drc(project_dir: Path, max_iterations: int) -> Dict[str, Any]:
    """Repair KICAD_DRC violations."""
    board_file = project_dir / "build" / "board.kicad_pcb"
    
    iteration = 0
    violations_fixed = 0
    last_count = None
    
    while iteration < max_iterations:
        iteration += 1
        
        drc_result = _run_kicad_drc(board_file)
        
        if drc_result["status"] == "PASS":
            return {
                "status": "PASS",
                "iterations": iteration,
                "fixes_applied": [f"fixed {violations_fixed} violations"],
            }
        
        violations = drc_result.get("violations", [])
        violation_count = len(violations)
        
        if violation_count == last_count:
            return {
                "status": "HUMAN_REVIEW",
                "iterations": iteration,
                "fixes_applied": [f"fixed {violations_fixed} violations"],
                "message": f"stuck at {violation_count} violations",
            }
        
        last_count = violation_count
        
        fixes = _diagnose_and_fix(board_file, violations)
        violations_fixed += fixes
    
    return {
        "status": "HUMAN_REVIEW",
        "iterations": iteration,
        "fixes_applied": [f"fixed {violations_fixed} violations"],
        "message": f"max {max_iterations} iterations exceeded",
    }
