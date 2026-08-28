from __future__ import annotations

import json
import os
import shutil
import stat
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def write_contract(root: Path, *, name: str = "test-project") -> None:
    (root / "src").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "src" / "board.zen").write_text("Board()\n", encoding="utf-8")
    (root / "tests" / "board_test.zen").write_text(
        "Module = Module('src/board.zen')\n"
        "def default(module, inputs):\n"
        "    components = module.components()\n"
        "    nets = module.nets()\n"
        "    check('U1' in components)\n"
        "    check('N1' in nets)\n"
        "TestBench(name='BoardTest', module=Module,\n"
        "          test_cases={'default': {}},\n"
        "          checks=[default])\n",
        encoding="utf-8",
    )
    (root / "SPEC.json").write_text(
        json.dumps({
            "schema_version": "1",
            "project": {"name": name, "pcb_version": "0.4", "layers": 4},
            "requirements": [{"id": "REQ-001", "type": "syntax", "description": "board parses", "severity": "error", "evidence_required": ["zener_test"]}],
            "fabrication": {"automatic_approval": False, "human_approval_required": True},
        }),
        encoding="utf-8",
    )
    (root / "ACCEPTANCE.json").write_text(
        json.dumps({
            "schema_version": "1",
            "checks": [{"id": "ACC-001", "requirement": "REQ-001", "kind": "zener_test", "test": "BoardTest.default", "expected": "PASS"}],
            "production_ready": False,
            "fabrication_approved": False,
        }),
        encoding="utf-8",
    )
    (root / "expected-connectivity.json").write_text(
        json.dumps({"schema_version": "1",
                    "components": {"U1": {"kind": "test"}},
                    "nets": {"N1": {"members": ["U1.P1"]}},
                    "rules": {"forbid_unlisted_members": False, "required_power_nets": []}}),
        encoding="utf-8",
    )
    (root / "project.toml").write_text(
        f'''[project]
name = "{name}"
profile = "schematic"
source = "src/board.zen"
test = "tests/board_test.zen"

[toolchain]
pcb_version = "0.4"

[layout]
required = false
''',
        encoding="utf-8",
    )


def copy_python(directory: Path, name: str = "fake-python") -> Path:
    suffix = ".exe" if os.name == "nt" else ""
    target = directory / f"{name}{suffix}"
    shutil.copy2(sys.executable, target)
    if os.name != "nt":
        target.chmod(target.stat().st_mode | stat.S_IXUSR)
    return target


def make_fake_pcb(directory: Path) -> Path:
    script = directory / "fake_pcb.py"
    script.write_text(
        """import pathlib, sys, json
if '--help' in sys.argv:
    raise SystemExit(0)
if '--version' in sys.argv:
    print('pcb 0.2.6')
    print('pcbc 0.4.34')
    raise SystemExit(0)
source = next((arg for arg in sys.argv[1:] if arg.endswith('.zen')), '')
if source and ('invalid-syntax' in source or 'invalid_syntax' in pathlib.Path(source).read_text(errors='ignore')):
    print('fixture rejected', file=sys.stderr)
    raise SystemExit(1)
if '-f' in sys.argv and 'json' in sys.argv:
    if 'connectivity' in source:
        records = [("PcbAgentConnectivity", "_check_connectivity")]
    elif 'specification' in source:
        records = [("PcbAgentSpecification", "_check_specification")]
    else:
        # The locked acceptance for the reference fixture names two checks.
        records = [("BlinkyTest", "component_value"), ("BlinkyTest", "connectivity")]

    status = "PASS"
    if 'invalid-' in source and ('connectivity' in source or 'value' in source):
        status = "FAIL"

    results = [
        {
            "test_bench_name": bench,
            "check_name": check,
            "status": status,
            "name": bench + "." + check,
        }
        for bench, check in records
    ]
    passed = len(results) if status == "PASS" else 0
    failed = len(results) if status == "FAIL" else 0
    payload = {
        "results": results,
        "summary": {
            "total": len(results),
            "passed": passed,
            "failed": failed,
            "failures": failed,
            "errors": 0,
        },
    }
    print(json.dumps(payload))
    raise SystemExit(0)
print('fixture accepted')
""",
        encoding="utf-8",
    )
    if os.name == "nt":
        command = directory / "pcb.cmd"
        command.write_text(f'@"{sys.executable}" "{script}" %*\n', encoding="utf-8")
    else:
        command = directory / "pcb"
        command.write_text(f'#!{sys.executable}\n' + script.read_text(encoding="utf-8"), encoding="utf-8")
        command.chmod(command.stat().st_mode | stat.S_IXUSR)
    return command
