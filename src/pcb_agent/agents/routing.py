"""
Routing agent implementation.
Parse kicad-drc.json, diagnose violations, apply targeted fixes.
"""

import json
import subprocess
from pathlib import Path
from typing import Dict, Any, List


async def run_routing_agent(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Parse DRC violations, diagnose, fix, loop until KICAD_DRC PASS.
    
    Returns:
        {
            "status": "PASS | FAIL | HUMAN_REVIEW",
            "violations_fixed": N,
            "iterations": N,
            "message": "..."
        }
    """
    project_dir = Path(input_data["project_dir"])
    board_file = Path(input_data["board_file"])
    
    max_iterations = 5
    iteration = 0
    violations_fixed = 0
    last_count = None
    
    while iteration < max_iterations:
        iteration += 1
        
        # Run kicad-cli drc
        drc_result = _run_kicad_drc(board_file)
        
        if drc_result["status"] == "PASS":
            return {
                "status": "PASS",
                "violations_fixed": violations_fixed,
                "iterations": iteration,
                "message": f"DRC clean after {iteration} iterations",
            }
        
        violations = drc_result.get("violations", [])
        violation_count = len(violations)
        
        if violation_count == last_count:
            # Stuck: same violation count 2×
            return {
                "status": "HUMAN_REVIEW",
                "violations_fixed": violations_fixed,
                "iterations": iteration,
                "message": f"stuck at {violation_count} violations",
            }
        
        last_count = violation_count
        
        # Diagnose and fix
        fixes_applied = _diagnose_and_fix(board_file, violations)
        violations_fixed += fixes_applied
    
    return {
        "status": "HUMAN_REVIEW",
        "violations_fixed": violations_fixed,
        "iterations": iteration,
        "message": f"max {max_iterations} iterations exceeded, {violation_count} violations remain",
    }


def _run_kicad_drc(board_file: Path) -> Dict[str, Any]:
    """Run kicad-cli pcb drc, parse output."""
    output_file = board_file.parent / "kicad-drc.json"
    
    cmd = [
        "kicad-cli", "pcb", "drc",
        "--output", str(output_file),
        "--format", "json",
        str(board_file)
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if not output_file.exists():
        return {
            "status": "BLOCKED",
            "message": f"kicad-cli drc failed: {result.stderr}",
        }
    
    drc_data = json.loads(output_file.read_text())
    
    violations = drc_data.get("violations", [])
    if not violations:
        return {"status": "PASS", "violations": []}
    
    return {"status": "FAIL", "violations": violations}


def _diagnose_and_fix(board_file: Path, violations: List[Dict]) -> int:
    """
    Diagnose violation types and apply targeted fixes.
    
    Returns: number of fixes applied.
    """
    fixes = 0
    
    # Group violations by type
    by_type = {}
    for v in violations:
        vtype = v.get("type", "unknown")
        by_type.setdefault(vtype, []).append(v)
    
    # Fix clearance violations
    if "clearance" in by_type:
        fixes += _fix_clearance(board_file, by_type["clearance"])
    
    # Fix track_width violations
    if "track_width" in by_type:
        fixes += _fix_track_width(board_file, by_type["track_width"])
    
    # Fix annular_ring violations
    if "annular_ring" in by_type:
        fixes += _fix_annular_ring(board_file, by_type["annular_ring"])
    
    # Fix stub violations (trace segment shorter than via diameter)
    if "length_out_of_range" in by_type:
        fixes += _fix_stub(board_file, by_type["length_out_of_range"])
    
    return fixes


def _fix_clearance(board_file: Path, violations: List[Dict]) -> int:
    """
    Fix clearance violations by:
    1. Identify minimum required clearance from violations
    2. Update board design rules
    3. Re-run freerouting with relaxed clearance
    """
    # Placeholder: parse violations, find min clearance needed
    # Real implementation would:
    # - Read .kicad_pcb
    # - Edit (setup (pcb_stackup ...)) clearance
    # - Rip up affected tracks
    # - Re-invoke freerouting
    return 0


def _fix_track_width(board_file: Path, violations: List[Dict]) -> int:
    """Fix track_width violations by widening thin traces."""
    # Placeholder: identify thin tracks, widen to min width
    return 0


def _fix_annular_ring(board_file: Path, violations: List[Dict]) -> int:
    """Fix annular_ring violations by enlarging via pads."""
    # Placeholder: identify small vias, increase drill/pad size
    return 0


def _fix_stub(board_file: Path, violations: List[Dict]) -> int:
    """Fix stub violations by removing short trace segments."""
    # Placeholder: identify stubs, remove or extend to min length
    return 0
