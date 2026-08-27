"""Deterministic pcb-agent command line."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import platform
import shutil
from dataclasses import replace
from fnmatch import fnmatch
from pathlib import Path
from typing import Callable, Sequence

from . import diode, kicad
from .backends import BackendError, CodexBackend, CommandBackend
from .models import Check, CheckStatus, Severity, VerificationReport
from .policy import PolicyViolation, ProtectedHashes, WorkspaceLock, WorkspaceSnapshot
from .policy_config import Policy, PolicyConfigError, matches as policy_matches
from .state import (
    ConfigurationError,
    ProjectState,
    RunState,
    latest_report,
    load_project,
    new_run,
    write_run_report,
    source_is_dirty,
)


EXIT_CODES = {
    CheckStatus.PASS: 0,
    CheckStatus.FAIL: 1,
    CheckStatus.BLOCKED: 2,
    CheckStatus.HUMAN_REVIEW: 5,
    CheckStatus.SKIPPED: 0,
}
PROTECTED = ("SPEC.json", "ACCEPTANCE.json", "expected-connectivity.json", "project.toml")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pcb-agent")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("doctor", "build", "layout", "drc", "verify", "report"):
        item = sub.add_parser(name)
        item.add_argument("project", nargs="?", default=".")
        item.add_argument("--project", dest="project_option")
        item.add_argument("--format", choices=("human", "json"), default="human")
        if name in {"doctor", "verify"}:
            item.add_argument("--profile", choices=("schematic", "layout"))
        if name == "report":
            item.add_argument("--run")
    check = sub.add_parser("check")
    check.add_argument("profile", choices=("schematic", "spec", "connectivity"), nargs="?", default="schematic")
    check.add_argument("project", nargs="?", default=".")
    check.add_argument("--project", dest="project_option")
    check.add_argument("--format", choices=("human", "json"), default="human")
    run = sub.add_parser("run")
    run.add_argument("task")
    run.add_argument("--project", default=".")
    run.add_argument("--backend", required=True, choices=("codex", "command"))
    run.add_argument("--backend-config")
    run.add_argument("--profile", choices=("schematic", "layout"), default="schematic")
    run.add_argument("--max-iterations", type=int, default=5)
    run.add_argument("--timeout", type=float, default=600.0)
    run.add_argument("--format", choices=("human", "json"), default="human")
    init = sub.add_parser("init")
    init.add_argument("name")
    init.add_argument("--into", default=".")
    init.add_argument("--format", choices=("human", "json"), default="human")
    return parser


def _check(check_id: str, status: CheckStatus, message: str, *, required: bool = True) -> Check:
    return Check(id=check_id, status=status, severity=Severity.ERROR, message=message, required=required)


def _persist(project: ProjectState, run: RunState, checks: Sequence[Check], output_format: str,
             profile: str = "schematic", exit_override: int | None = None) -> int:
    artifacts = tuple(check.evidence for check in checks if check.evidence)
    report = VerificationReport(project.name, tuple(checks), profile=profile, run_id=run.run_id,
                                source_dirty=source_is_dirty(project.root), hashes=project.hashes,
                                artifacts=artifacts)
    path = write_run_report(run, report, project)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if output_format == "json":
        print(json.dumps(payload, sort_keys=True))
    else:
        print(f"{report.status}: {project.name} ({run.run_id})")
        for check in checks:
            print(f"{check.id}: {check.status} - {check.message}")
        print(f"report: {path}")
        print("production_ready: false; fabrication_approved: false")
    return exit_override if exit_override is not None else EXIT_CODES[report.status]


def _tool_check(
    project: ProjectState,
    executable: str,
    probe: Callable[[ProjectState], object],
    *,
    required: bool,
) -> Check:
    try:
        result = probe(project)
    except (FileNotFoundError, OSError, ValueError) as error:
        status = CheckStatus.BLOCKED if required else CheckStatus.SKIPPED
        return _check(executable.upper(), status, str(error), required=required)
    status = CheckStatus.PASS if result.returncode == 0 and not result.timed_out else CheckStatus.BLOCKED
    if not required and status == CheckStatus.BLOCKED:
        status = CheckStatus.SKIPPED
    return _check(executable.upper(), status, f"capability help exited {result.returncode}", required=required)


def _doctor(project: ProjectState, profile: str) -> list[Check]:
    checks = [
        _check("CONTRACT", CheckStatus.PASS, "project contracts loaded and hashed"),
        _check("PLATFORM", CheckStatus.PASS,
               f"{platform.system()} {platform.machine()}; Python {platform.python_version()}"),
        _check("GIT", CheckStatus.PASS if shutil.which("git") else CheckStatus.SKIPPED,
               "git detected" if shutil.which("git") else "git unavailable", required=False),
        _tool_check(project, "pcb", diode.probe, required=True),
        _tool_check(project, "kicad-cli", kicad.probe, required=profile == "layout"),
        _check("SIMULATION", CheckStatus.SKIPPED, "simulation is not implemented", required=False),
    ]
    for name in ("codex", "claude", "gemini", "aider"):
        checks.append(_check(f"AI_{name.upper()}", CheckStatus.PASS if shutil.which(name) else CheckStatus.SKIPPED,
                             f"{name} detected; not invoked" if shutil.which(name) else f"{name} unavailable",
                             required=False))
    if checks[3].status == CheckStatus.PASS:
        try:
            probes = diode.doctor_probes(project)
            status = CheckStatus.PASS if all(item.returncode == 0 and not item.timed_out for item in probes) else CheckStatus.BLOCKED
            checks.append(_check("DIODE_COMMANDS", status, "version/help/toolchain probes completed"))
        except (FileNotFoundError, OSError, ValueError) as error:
            checks.append(_check("DIODE_COMMANDS", CheckStatus.BLOCKED, str(error)))
    return checks


def _diode_command(project: ProjectState, key: str, check_id: str,
                   trusted_root: Path | None = None) -> Check:
    try:
        protected = ProtectedHashes.capture(project.root, PROTECTED)
        result = diode.execute(project, key, trusted_root=trusted_root)
        protected.verify()
        check = diode.result_check(check_id, result)
        if trusted_root is not None:
            evidence_path = trusted_root / f"{check_id.lower()}.json"
            payload = json.dumps({"argv": result.argv, "stdout": result.stdout, "stderr": result.stderr,
                                  "exit_code": result.returncode, "duration": result.duration_seconds},
                                 indent=2) + "\n"
            evidence_path.write_text(payload, encoding="utf-8", newline="\n")
            digest = "sha256:" + hashlib.sha256(evidence_path.read_bytes()).hexdigest()
            evidence = {"path": str(evidence_path), "sha256": digest}
            if key == "test-command":
                evidence["testbench_sha256"] = result.input_hashes["testbench"]
            check = replace(check, evidence=evidence)
        return check
    except ConfigurationError as error:
        return _check(check_id, CheckStatus.BLOCKED, str(error))
    except (FileNotFoundError, OSError, ValueError) as error:
        return _check(check_id, CheckStatus.BLOCKED, str(error))


def _schematic_checks(project: ProjectState, run: RunState | None = None) -> list[Check]:
    test = _diode_command(project, "test-command", "ZENER_TEST", run.raw_directory if run else None)
    return [test, _connectivity_check(project, test), _specification_check(project, test)]


def _connectivity_check(project: ProjectState, test: Check) -> Check:
    if test.status != CheckStatus.PASS:
        return _check("CONNECTIVITY", test.status, "Zener TestBench did not pass")
    connectivity = project.connectivity
    if not connectivity.get("components") and not connectivity.get("nets"):
        return _check("CONNECTIVITY", CheckStatus.SKIPPED,
                      "build-negative fixture declares no expected connectivity",
                      required=False)
    
    return _check(
        "CONNECTIVITY",
        CheckStatus.BLOCKED,
        "pin-level deterministic connectivity evidence is unavailable; "
        "source coverage is advisory only",
    )


def _specification_check(project: ProjectState, test: Check) -> Check:
    if test.status != CheckStatus.PASS:
        return _check("SPECIFICATION", test.status, "Zener TestBench did not pass")
    
    return _check(
        "SPECIFICATION",
        CheckStatus.BLOCKED,
        "deterministic component-property evidence is unavailable; "
        "source coverage is advisory only",
    )


def _verify(project: ProjectState, run: RunState, profile: str) -> list[Check]:
    checks = [
        _check("CONTRACT", CheckStatus.PASS, "project contracts loaded and hashed"),
        _diode_command(project, "build-command", "DIODE_BUILD", run.raw_directory),
    ]
    if checks[-1].status == CheckStatus.PASS:
        checks.extend(_schematic_checks(project, run))
    else:
        dependent_status = checks[-1].status
        checks.extend([
            _check("ZENER_TEST", dependent_status, "build did not pass"),
            _check("CONNECTIVITY", dependent_status, "build did not pass"),
            _check("SPECIFICATION", dependent_status, "build did not pass"),
        ])
    if profile == "layout" and all(check.status == CheckStatus.PASS for check in checks):
        generation = _diode_command(project, "layout-command", "LAYOUT_GENERATE")
        checks.append(generation)
        layout = (_diode_command(project, "layout-check-command", "LAYOUT_SYNC")
                  if generation.status == CheckStatus.PASS else
                  _check("LAYOUT_SYNC", CheckStatus.BLOCKED, "layout generation did not pass"))
        checks.append(layout)
        if generation.status == CheckStatus.PASS:
            try:
                checks.append(kicad.result_check(kicad.drc(project, run), run.raw_directory / "kicad-drc.json"))
            except (ConfigurationError, FileNotFoundError, OSError, ValueError) as error:
                checks.append(_check("KICAD_DRC", CheckStatus.BLOCKED, str(error)))
        else:
            checks.append(_check("KICAD_DRC", CheckStatus.BLOCKED, "layout did not pass"))
    elif profile == "schematic":
        checks.extend([
            _check("LAYOUT_GENERATE", CheckStatus.SKIPPED, "layout profile not active", required=False),
            _check("LAYOUT_SYNC", CheckStatus.SKIPPED, "layout profile not active", required=False),
            _check("KICAD_DRC", CheckStatus.SKIPPED, "layout profile not active", required=False),
        ])
    else:
        checks.extend([
            _check("LAYOUT_GENERATE", CheckStatus.BLOCKED, "schematic prerequisite did not pass"),
            _check("LAYOUT_SYNC", CheckStatus.BLOCKED, "schematic prerequisite did not pass"),
            _check("KICAD_DRC", CheckStatus.BLOCKED, "schematic prerequisite did not pass"),
        ])
    checks.append(_check("SIMULATION", CheckStatus.SKIPPED, "simulation is not implemented", required=False))
    return checks


def _editable_paths(project: ProjectState) -> tuple[str, ...]:
    paths = [path.relative_to(project.root).as_posix() for path in (project.root / "src").rglob("*.zen")]
    paths.extend(path.relative_to(project.root).as_posix() for path in (project.root / "layout").rglob("*.kicad_pcb") if (project.root / "layout").exists())
    return tuple(sorted(paths))


def _workspace_hashes(project: ProjectState) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for path in project.root.rglob("*"):
        relative = path.relative_to(project.root).as_posix()
        if relative == "reports" or relative.startswith("reports/"):
            continue
        if path.is_symlink():
            hashes[relative] = "SYMLINK:" + os.readlink(path)
        elif path.is_file():
            hashes[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


def _snapshot_paths(project: ProjectState) -> tuple[str, ...]:
    return tuple(path.relative_to(project.root).as_posix() for path in project.root.rglob("*")
                 if path.is_file() and not path.is_symlink()
                 and "reports" not in path.relative_to(project.root).parts)


def _backend_changes(before: dict[str, str], after: dict[str, str]) -> tuple[str, ...]:
    return tuple(sorted(path for path in before.keys() | after.keys() if before.get(path) != after.get(path)))


def _allowed_backend_path(path: str, profile: str, policy: Policy) -> bool:
    if any(policy_matches(path, pattern) for pattern in policy.deny_files):
        return False
    for pattern in policy.allow_files:
        if pattern.endswith(".kicad_pcb") and profile != "layout":
            continue
        if policy_matches(path, pattern):
            return True
    return False


def _fingerprint(checks: Sequence[Check], changed: Sequence[str]) -> str:
    value = [(check.id, check.status, check.message) for check in checks], sorted(changed)
    return hashlib.sha256(repr(value).encode()).hexdigest()


def _run_backend_unlocked(args: argparse.Namespace, project: ProjectState, run: RunState,
                           policy: Policy) -> list[Check]:
    if os.environ.get("PCB_AGENT_ACTIVE"):
        return [_check("BACKEND", CheckStatus.BLOCKED, "nested pcb-agent run is forbidden")]
    if not 1 <= args.max_iterations <= policy.max_iterations:
        raise ConfigurationError(f"max-iterations must be between 1 and {policy.max_iterations}")
    protected_paths = (*PROTECTED, project.test)
    protected = ProtectedHashes.capture(project.root, protected_paths)
    editable = _editable_paths(project)
    backend = CodexBackend() if args.backend == "codex" else CommandBackend(args.backend_config or "")
    previous: str | None = None
    for iteration in range(1, args.max_iterations + 1):
        before = _workspace_hashes(project)
        existing = set(_snapshot_paths(project))
        snapshot = WorkspaceSnapshot.capture_before(project.root, existing | set(editable) | set(protected_paths))
        if args.backend == "codex":
            try:
                probe = backend.probe(project.root)
            except (FileNotFoundError, OSError, ValueError) as error:
                return [_check("BACKEND_PROBE", CheckStatus.BLOCKED, str(error))]
            status = CheckStatus.PASS if probe.returncode == 0 and not probe.timed_out else CheckStatus.BLOCKED
            return [_check("BACKEND_PROBE", status, "Codex exec help probe only; invocation disabled")]
        result = backend.execute(args.task, project.root, args.timeout)
        try:
            protected.verify()
        except PolicyViolation:
            snapshot.seal_backend_changes().restore_backend_changes()
            return [_check("POLICY_INTEGRITY", CheckStatus.FAIL, "backend changed protected files")]
        changed = _backend_changes(before, _workspace_hashes(project))
        forbidden = tuple(path for path in changed if not _allowed_backend_path(path, args.profile, policy))
        if forbidden:
            snapshot.seal_backend_changes().restore_backend_changes()
            for relative in forbidden:
                if relative not in existing:
                    candidate = project.root / relative
                    if candidate.is_symlink():
                        candidate.unlink()
                    elif candidate.exists() and candidate.is_file() and project.root in candidate.resolve().parents:
                        candidate.unlink()
            return [_check("POLICY_INTEGRITY", CheckStatus.FAIL,
                           f"backend changed forbidden paths: {', '.join(forbidden)}")]
        sealed = snapshot.seal_backend_changes()
        if len(changed) > policy.max_changed_files:
            sealed.restore_backend_changes()
            raise PolicyViolation(
                f"backend changed more than {policy.max_changed_files} editable files"
            )
        if result.process.timed_out or result.process.returncode != 0:
            snapshot.seal_backend_changes().restore_backend_changes()
            return [_check("BACKEND", CheckStatus.BLOCKED, f"backend exited {result.process.returncode}")]
        checks = _verify(project, run, args.profile)
        if VerificationReport(project.name, tuple(checks)).status == CheckStatus.PASS:
            return [_check("BACKEND", CheckStatus.PASS, f"backend iteration {iteration} completed"), *checks]
        fingerprint = _fingerprint(checks, changed)
        if fingerprint == previous:
            return [_check("BACKEND", CheckStatus.BLOCKED, "no progress fingerprint repeated"), *checks]
        previous = fingerprint
    return [_check("BACKEND", CheckStatus.BLOCKED, "iteration limit reached")]


def _run_backend(args: argparse.Namespace, project: ProjectState, run: RunState,
                 policy: Policy) -> list[Check]:
    lock = WorkspaceLock.acquire(project.root)
    try:
        return _run_backend_unlocked(args, project, run, policy)
    finally:
        lock.release()


def _init(args: argparse.Namespace) -> int:
    name = args.name
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", name):
        print(f"pcb-agent: invalid project name: {name!r}", file=sys.stderr)
        return 3
    try:
        into = Path(args.into).resolve(strict=True)
    except (OSError, RuntimeError) as error:
        print(f"pcb-agent: cannot resolve --into: {error}", file=sys.stderr)
        return 3
    if not into.is_dir():
        print(f"pcb-agent: --into is not a directory: {into}", file=sys.stderr)
        return 3
    target = into / name
    if target.exists():
        try:
            contents = list(target.iterdir())
        except OSError:
            contents = None
        if contents:
            print(f"pcb-agent: target not empty: {target}", file=sys.stderr)
            return 3
    if target.is_symlink():
        print(f"pcb-agent: target is a symlink: {target}", file=sys.stderr)
        return 3

    template_root = (Path(__file__).resolve().parent.parent.parent
                     / "skill" / "diode-pcb-agent" / "assets" / "project-template")
    template_files = (
        "src/board.zen",
        "tests/board_test.zen",
        "SPEC.json",
        "ACCEPTANCE.json",
        "expected-connectivity.json",
        "project.toml",
        "pcb.toml",
    )

    target.mkdir(parents=False, exist_ok=False)
    created: list[str] = []
    try:
        for relative in template_files:
            source = template_root / relative
            destination = target / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            created.append(relative)

        replacements = {
            "template-board": name,
            "template_board": name.replace("-", "_"),
        }
        for relative in created:
            path = target / relative
            if path.suffix not in {".json", ".toml", ".zen"}:
                continue
            text = path.read_text(encoding="utf-8")
            for old, new in replacements.items():
                text = text.replace(old, new)
            path.write_text(text, encoding="utf-8", newline="\n")

        load_project(target)
    except Exception as error:
        shutil.rmtree(target, ignore_errors=True)
        print(f"pcb-agent: init failed: {error}", file=sys.stderr)
        return 3

    if args.format == "json":
        payload = {
            "project": name,
            "root": str(target),
            "created": sorted(created),
            "production_ready": False,
            "fabrication_approved": False,
        }
        print(json.dumps(payload, sort_keys=True))
    else:
        print(f"created {name} at {target}")
        for relative in sorted(created):
            print(f"  {relative}")
        print("production_ready: false; fabrication_approved: false")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "init":
        return _init(args)
    try:
        policy = Policy.load()
        project = load_project(getattr(args, "project_option", None) or args.project)
        if hasattr(args, "profile"):
            args.profile = args.profile or project.profile
            if project.config["layout"]["required"] and args.profile != "layout":
                raise ConfigurationError("layout.required project cannot use schematic profile")
        if args.command == "report":
            try:
                path = ((project.root / "reports" / args.run / "verify-report.json").resolve(strict=True)
                        if args.run else latest_report(project))
                if project.root not in path.parents:
                    raise ValueError("report path escapes project")
            except FileNotFoundError as error:
                print(f"pcb-agent: {error}", file=sys.stderr)
                return 2
            print(path.read_text(encoding="utf-8") if args.format == "json" else path)
            return 0
        run = new_run(project)
        if args.command == "doctor":
            checks = _doctor(project, args.profile)
        elif args.command == "build":
            checks = [_diode_command(project, "build-command", "DIODE_BUILD", run.raw_directory)]
        elif args.command == "check":
            checks = _schematic_checks(project, run)
            if args.profile == "spec":
                checks = [checks[2]]
            elif args.profile == "connectivity":
                checks = [checks[1]]
        elif args.command == "layout":
            generation = _diode_command(project, "layout-command", "LAYOUT_GENERATE")
            checks = [generation]
            if generation.status == CheckStatus.PASS:
                checks.append(_diode_command(project, "layout-check-command", "LAYOUT_SYNC"))
            else:
                checks.append(_check("LAYOUT_SYNC", CheckStatus.BLOCKED,
                                     "layout generation did not pass"))
        elif args.command == "drc":
            try:
                checks = [kicad.result_check(kicad.drc(project, run), run.raw_directory / "kicad-drc.json")]
            except (ConfigurationError, FileNotFoundError, OSError, ValueError) as error:
                checks = [_check("KICAD_DRC", CheckStatus.BLOCKED, str(error))]
        elif args.command == "verify":
            checks = _verify(project, run, args.profile)
        else:
            checks = _run_backend(args, project, run, policy)
        backend_terminal = (args.command == "run" and checks and checks[0].id == "BACKEND"
                            and checks[0].status == CheckStatus.BLOCKED)
        return _persist(project, run, checks, args.format, getattr(args, "profile", project.profile),
                        4 if backend_terminal else None)
    except (ConfigurationError, PolicyConfigError, PolicyViolation, BackendError,
            FileNotFoundError, OSError, ValueError) as error:
        print(f"pcb-agent: {error}", file=sys.stderr)
        if isinstance(error, (ConfigurationError, PolicyConfigError)):
            return 3
        if isinstance(error, PolicyViolation):
            return 1
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
