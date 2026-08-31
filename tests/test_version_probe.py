"""Tests for the strict pcbc version probe."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pcb_agent import diode
from pcb_agent.process import ProcessResult
from pcb_agent.state import load_project

from helpers import make_fake_pcb, write_contract


def _version_result(stdout: str, returncode: int = 0, timed_out: bool = False) -> ProcessResult:
    return ProcessResult(
        ("pcb", "--version"),
        returncode,
        stdout,
        "",
        0.1,
        timed_out,
        False,
        {},
    )


class ProbePcbcVersionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        write_contract(self.root)
        self.project = load_project(self.root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _probe(self, result: ProcessResult) -> str:
        with patch("pcb_agent.diode.run_process", return_value=result):
            return diode.probe_pcbc_version(self.project)

    def test_parses_version_from_output(self) -> None:
        self.assertEqual(self._probe(_version_result("pcbc 0.4.34")), "0.4.34")

    def test_parses_version_with_surrounding_text(self) -> None:
        stdout = "pcb 0.2.6\npcbc 0.4.34 (release)\n"
        self.assertEqual(self._probe(_version_result(stdout)), "0.4.34")

    def test_rejects_unparseable_output(self) -> None:
        with self.assertRaises(diode.GeneratedCompatibilityError) as ctx:
            self._probe(_version_result("some unrelated banner"))
        self.assertIn("cannot parse", str(ctx.exception))

    def test_rejects_partial_version(self) -> None:
        with self.assertRaises(diode.GeneratedCompatibilityError):
            self._probe(_version_result("pcbc 0.4"))

    def test_rejects_nonzero_exit(self) -> None:
        with self.assertRaises(diode.GeneratedCompatibilityError) as ctx:
            self._probe(_version_result("pcbc 0.4.34", returncode=1))
        self.assertIn("exited 1", str(ctx.exception))

    def test_rejects_timeout(self) -> None:
        with self.assertRaises(diode.GeneratedCompatibilityError) as ctx:
            self._probe(_version_result("", timed_out=True))
        self.assertIn("timed out", str(ctx.exception))


class VersionProbeGatesGeneratedChecksTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        write_contract(self.root)
        self.project = load_project(self.root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _gate(self, check_id: str, probe: "cli.ToolVersionProbe"):
        from pcb_agent import cli
        from pcb_agent.models import Check, CheckStatus, Severity

        passing_test = Check(
            "ZENER_TEST", CheckStatus.PASS, Severity.ERROR, "ok", "tool", (), 0, 0.1, {}, True
        )
        if check_id == "CONNECTIVITY":
            return cli._connectivity_check(self.project, passing_test, None, probe)
        return cli._specification_check(self.project, passing_test, None, probe)

    def test_connectivity_blocked_when_version_probe_fails(self) -> None:
        from pcb_agent import cli
        from pcb_agent.models import CheckStatus

        probe = cli.ToolVersionProbe(
            None, None, diode.GeneratedCompatibilityError("cannot parse pcbc version")
        )
        check = self._gate("CONNECTIVITY", probe)
        self.assertEqual(check.status, CheckStatus.BLOCKED)
        self.assertIn("toolchain version unknown", check.message)

    def test_specification_blocked_when_version_probe_fails(self) -> None:
        from pcb_agent import cli
        from pcb_agent.models import CheckStatus

        probe = cli.ToolVersionProbe(
            None, None, diode.GeneratedCompatibilityError("cannot parse pcbc version")
        )
        check = self._gate("SPECIFICATION", probe)
        self.assertEqual(check.status, CheckStatus.BLOCKED)
        self.assertIn("toolchain version unknown", check.message)

    def test_unrunnable_probe_blocks_with_blocked_message(self) -> None:
        from pcb_agent import cli
        from pcb_agent.models import CheckStatus

        probe = cli.ToolVersionProbe(None, None, FileNotFoundError("pcb missing"))
        for check_id in ("CONNECTIVITY", "SPECIFICATION"):
            with self.subTest(check_id=check_id):
                check = self._gate(check_id, probe)
                self.assertEqual(check.status, CheckStatus.BLOCKED)
                self.assertIn("toolchain version probe blocked", check.message)


class ToolVersionCaptureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        write_contract(self.root)
        self.project = load_project(self.root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_captures_pcbc_version_in_report(self) -> None:
        from pcb_agent import cli

        version_result = ProcessResult(
            ("pcb", "--version"), 0, "pcbc 0.4.40\n", "", 0.1, False, False, {}
        )
        with patch("pcb_agent.diode.run_process", return_value=version_result):
            probe = cli._probe_tool_version(self.project)
        self.assertIsNone(probe.error)
        self.assertEqual(probe.pcbc, "0.4.40")
        versions = cli._tool_versions(probe)
        self.assertEqual(versions.get("pcbc"), "0.4.40")
        self.assertEqual(versions.get("pcb"), "pcbc 0.4.40")

    def test_version_probe_failure_yields_no_pcbc_entry(self) -> None:
        from pcb_agent import cli

        with patch(
            "pcb_agent.diode.run_process",
            return_value=_version_result("some unrelated banner"),
        ):
            probe = cli._probe_tool_version(self.project)
        self.assertIsNotNone(probe.error)
        self.assertIsNone(probe.pcbc)
        versions = cli._tool_versions(probe)
        self.assertNotIn("pcbc", versions)
        self.assertNotIn("pcb", versions)

    def test_report_serializes_versions(self) -> None:
        from pcb_agent.models import Check, CheckStatus, VerificationReport

        report = VerificationReport(
            "board",
            (Check("ok", CheckStatus.PASS),),
            versions={"pcbc": "0.4.40", "pcb": "pcbc 0.4.40"},
        )
        data = report.to_dict()
        self.assertEqual(data["versions"], {"pcbc": "0.4.40", "pcb": "pcbc 0.4.40"})


class OneProbePerInvocationTests(unittest.TestCase):
    """`pcb --version` is spawned exactly once per CLI invocation.

    The generated compatibility checks and the report's diagnostic
    `versions` must derive from the same probe output, and a diagnostic
    probe failure must never gate doctor/build or other unrelated commands.
    """

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.project_root = self.base / "project"
        write_contract(self.project_root)
        self.project = load_project(self.project_root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _fake_tool_path(self) -> str:
        tools = self.base / "tools"
        tools.mkdir(exist_ok=True)
        make_fake_pcb(tools)
        self._original_path = os.environ.get("PATH", "")
        os.environ["PATH"] = f"{tools}{os.pathsep}{self._original_path}"
        return str(tools)

    def _restore_path(self) -> None:
        os.environ["PATH"] = self._original_path

    def test_verify_invokes_pcb_version_exactly_once(self) -> None:
        if os.name == "nt":
            self.skipTest("Windows fake batch executable rejected by security policy")
        import contextlib
        import io

        from pcb_agent import cli

        self._fake_tool_path()
        try:
            calls: list[tuple[str, ...]] = []
            real_run_process = diode.run_process

            def counting(workspace, argv, **kwargs):
                calls.append(tuple(argv))
                return real_run_process(workspace, argv, **kwargs)

            with patch("pcb_agent.diode.run_process", side_effect=counting):
                with contextlib.redirect_stdout(io.StringIO()):
                    cli.main(["verify", str(self.project_root)])
        finally:
            self._restore_path()
        version_calls = [argv for argv in calls if argv == ("pcb", "--version")]
        self.assertEqual(len(version_calls), 1)

    def test_connectivity_and_specification_receive_identical_parsed_version(self) -> None:
        from pcb_agent import cli
        from pcb_agent.models import Check, CheckStatus, Severity

        probe = cli.ToolVersionProbe("pcb 0.2.6\npcbc 0.4.34", "0.4.34", None)
        passing_test = Check(
            "ZENER_TEST", CheckStatus.PASS, Severity.ERROR, "ok", "tool", (), 0, 0.1, {}, True
        )
        seen: dict[str, object] = {}

        def fake_render_connectivity(project, version):
            seen["connectivity"] = version
            return "source"

        def fake_render_specification(project, version):
            seen["specification"] = version
            return "source"

        with patch(
            "pcb_agent.generated_testbench.render_connectivity_testbench",
            side_effect=fake_render_connectivity,
        ), patch(
            "pcb_agent.generated_testbench.render_specification_testbench",
            side_effect=fake_render_specification,
        ):
            cli._connectivity_check(self.project, passing_test, None, probe)
            cli._specification_check(self.project, passing_test, None, probe)
        self.assertEqual(seen["connectivity"], "0.4.34")
        self.assertEqual(seen["specification"], "0.4.34")

    def test_report_versions_remain_schema_valid(self) -> None:
        from pcb_agent import cli
        from pcb_agent.jsonschema import load_schema, validate
        from pcb_agent.models import Check, CheckStatus, VerificationReport

        version_result = ProcessResult(
            ("pcb", "--version"), 0, "pcb 0.2.6\npcbc 0.4.34\n", "", 0.1, False, False, {}
        )
        with patch("pcb_agent.diode.run_process", return_value=version_result):
            probe = cli._probe_tool_version(self.project)
        report = VerificationReport(
            "board",
            (Check("ok", CheckStatus.PASS),),
            versions=cli._tool_versions(probe),
        )
        # Round-trip through JSON exactly like the on-disk report.
        import json

        validate(
            json.loads(json.dumps(report.to_dict())),
            load_schema("verification-report.schema.json"),
        )

    def _version_failing_run_process(self):
        real_run_process = diode.run_process

        def selective(workspace, argv, **kwargs):
            if tuple(argv) == ("pcb", "--version"):
                raise FileNotFoundError("pcb --version unavailable")
            return real_run_process(workspace, argv, **kwargs)

        return selective

    def _latest_report_dict(self):
        import json

        from pcb_agent.state import latest_report

        return json.loads(latest_report(self.project).read_text(encoding="utf-8"))

    def test_build_not_gated_by_version_probe_failure(self) -> None:
        if os.name == "nt":
            self.skipTest("Windows fake batch executable rejected by security policy")
        import contextlib
        import io

        from pcb_agent import cli

        self._fake_tool_path()
        try:
            with patch(
                "pcb_agent.diode.run_process",
                side_effect=self._version_failing_run_process(),
            ), contextlib.redirect_stdout(io.StringIO()):
                exit_code = cli.main(["build", str(self.project_root)])
            report = self._latest_report_dict()
        finally:
            self._restore_path()
        self.assertEqual(exit_code, 0)
        self.assertEqual(report["versions"], {})
        for check in report["checks"]:
            self.assertNotIn("toolchain version", check["message"])

    def test_doctor_completes_despite_version_probe_failure(self) -> None:
        if os.name == "nt":
            self.skipTest("Windows fake batch executable rejected by security policy")
        import contextlib
        import io

        from pcb_agent import cli

        self._fake_tool_path()
        try:
            with patch(
                "pcb_agent.diode.run_process",
                side_effect=self._version_failing_run_process(),
            ), contextlib.redirect_stdout(io.StringIO()):
                exit_code = cli.main(["doctor", str(self.project_root)])
            report = self._latest_report_dict()
        finally:
            self._restore_path()
        # The probe failure is diagnostic: doctor completes, writes a
        # report, and no check carries the new probe's blocking message.
        self.assertIn(exit_code, (0, 1, 2, 5))
        self.assertEqual(report["versions"], {})
        for check in report["checks"]:
            self.assertNotIn("toolchain version", check["message"])


if __name__ == "__main__":
    unittest.main()
