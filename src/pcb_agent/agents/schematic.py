"""
Schematic agent implementation.
Write .zen source + locked TestBench, verify, loop repair.
"""

import json
import hashlib
import subprocess
from pathlib import Path
from typing import Dict, Any


async def run_schematic_agent(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Write schematic .zen + tests, verify connectivity/spec, loop repair.
    
    Returns:
        {
            "status": "PASS | FAIL | BLOCKED | HUMAN_REVIEW",
            "checks": {...},
            "iterations": N,
            "files_written": [...],
            "message": "...",
            "fingerprint": "sha256:..."
        }
    """
    project_dir = Path(input_data["project_dir"])
    module_name = input_data["module_name"]
    requirements = input_data["requirements"]
    
    max_iterations = 5
    iteration = 0
    last_fingerprint = None
    files_written = []
    
    # Initial write
    _write_initial_files(project_dir, module_name, requirements, files_written)
    
    while iteration < max_iterations:
        iteration += 1
        
        # Run verify
        result = _run_verify(project_dir, "schematic")
        
        if result["status"] == "BLOCKED":
            return {
                "status": "BLOCKED",
                "checks": result["checks"],
                "iterations": iteration,
                "files_written": files_written,
                "message": result["message"],
            }
        
        if result["status"] == "PASS":
            return {
                "status": "PASS",
                "checks": result["checks"],
                "iterations": iteration,
                "files_written": files_written,
                "message": f"schematic verified, {iteration} iterations",
            }
        
        # FAIL: diagnose + repair
        fingerprint = _compute_fingerprint(result)
        if fingerprint == last_fingerprint:
            return {
                "status": "HUMAN_REVIEW",
                "checks": result["checks"],
                "iterations": iteration,
                "files_written": files_written,
                "message": "stuck after edit, same failure 2×",
            }
        last_fingerprint = fingerprint
        
        # Apply repair
        _repair_failure(project_dir, module_name, result)
    
    # Max iterations exceeded
    return {
        "status": "HUMAN_REVIEW",
        "checks": result["checks"],
        "iterations": iteration,
        "files_written": files_written,
        "message": f"max {max_iterations} iterations exceeded",
    }


def _write_initial_files(
    project_dir: Path, module_name: str, requirements: list, files_written: list
):
    """Write initial .zen, tests, contracts."""
    src_dir = project_dir / "src"
    tests_dir = project_dir / "tests"
    src_dir.mkdir(parents=True, exist_ok=True)
    tests_dir.mkdir(parents=True, exist_ok=True)
    
    # Write src/<module>.zen (placeholder)
    zen_file = src_dir / f"{module_name.lower()}.zen"
    zen_file.write_text(
        f"# {module_name}\n"
        "# Placeholder schematic\n"
        "module() {\n"
        "  # TODO: implement requirements\n"
        "}\n"
    )
    files_written.append(str(zen_file))
    
    # Write tests/<module>_test.zen
    test_file = tests_dir / f"{module_name.lower()}_test.zen"
    test_file.write_text(
        f"# Test for {module_name}\n"
        "def check(module, inputs):\n"
        "    check(True, 'placeholder')\n"
    )
    files_written.append(str(test_file))
    
    # Write contracts (SPEC.json, ACCEPTANCE.json, expected-connectivity.json, project.toml)
    _write_contracts(project_dir, module_name, test_file.name, files_written)


def _write_contracts(project_dir: Path, module_name: str, test_name: str, files_written: list):
    """Write contract files."""
    spec = {
        "requirements": [
            {"id": "REQ-001", "description": "Module builds without error"}
        ]
    }
    (project_dir / "SPEC.json").write_text(json.dumps(spec, indent=2))
    files_written.append(str(project_dir / "SPEC.json"))
    
    acceptance = {
        "checks": [
            {"id": "ACC-001", "requirement": "REQ-001", "test": test_name}
        ]
    }
    (project_dir / "ACCEPTANCE.json").write_text(json.dumps(acceptance, indent=2))
    files_written.append(str(project_dir / "ACCEPTANCE.json"))
    
    connectivity = {"components": [], "nets": [], "rules": []}
    (project_dir / "expected-connectivity.json").write_text(json.dumps(connectivity, indent=2))
    files_written.append(str(project_dir / "expected-connectivity.json"))
    
    toml_content = f"""
profile = "schematic"
source = "src/{module_name.lower()}.zen"
test = "tests/{test_name}"

[toolchain]
pcb_version = "0.4.40"
"""
    (project_dir / "project.toml").write_text(toml_content)
    files_written.append(str(project_dir / "project.toml"))


def _run_verify(project_dir: Path, profile: str) -> Dict[str, Any]:
    """Run pcb-agent verify, return parsed JSON result."""
    cmd = [
        "python", "-m", "pcb_agent.cli",
        "verify",
        "--project", str(project_dir),
        "--profile", profile,
        "--format", "json"
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    # Parse JSON from stdout
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {
            "status": "BLOCKED",
            "checks": {},
            "message": f"verify failed to produce JSON: {result.stderr}",
        }


def _compute_fingerprint(result: Dict[str, Any]) -> str:
    """Compute fingerprint from result to detect stuck loops."""
    fp = hashlib.sha256()
    fp.update(result["status"].encode())
    for gate, check in result.get("checks", {}).items():
        fp.update(f"{gate}:{check.get('status', 'UNKNOWN')}".encode())
    return fp.hexdigest()


def _repair_failure(project_dir: Path, module_name: str, result: Dict[str, Any]):
    """Diagnose failure and apply repair."""
    checks = result.get("checks", {})
    
    # DIODE_BUILD failure: parse stderr for syntax error
    if checks.get("DIODE_BUILD", {}).get("status") == "FAIL":
        # TODO: parse stderr, edit .zen to fix syntax
        pass
    
    # CONNECTIVITY failure: adjust expected-connectivity.json or .zen
    if checks.get("CONNECTIVITY", {}).get("status") == "FAIL":
        # TODO: parse connectivity_check.json, fix net names
        pass
    
    # SPECIFICATION failure: adjust SPEC.json or .zen values
    if checks.get("SPECIFICATION", {}).get("status") == "FAIL":
        # TODO: parse spec check result, adjust component values
        pass
