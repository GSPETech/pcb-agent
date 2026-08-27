from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from helpers import write_contract
from pcb_agent.contracts import ContractError, REQUIRED_FILES, load_project_contract


class ContractTests(unittest.TestCase):
    def test_valid_strict_contract_loads_and_hashes_every_required_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_contract(root)
            contract = load_project_contract(root)
            self.assertEqual(contract.name, "test-project")
            self.assertEqual(set(contract.hashes), set(REQUIRED_FILES))
            self.assertTrue(all(value.startswith("sha256:") for value in contract.hashes.values()))

    def test_missing_empty_and_malformed_contracts_are_rejected(self) -> None:
        cases = {
            "missing": lambda root: (root / "SPEC.json").unlink(),
            "empty": lambda root: (root / "SPEC.json").write_text("", encoding="utf-8"),
            "malformed": lambda root: (root / "SPEC.json").write_text("{", encoding="utf-8"),
        }
        for label, corrupt in cases.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                write_contract(root)
                corrupt(root)
                with self.assertRaises((ContractError, FileNotFoundError)):
                    load_project_contract(root)

    def test_wrong_shapes_and_unsafe_acceptance_are_rejected(self) -> None:
        replacements = (
            ("SPEC.json", []),
            ("expected-connectivity.json", {"components": [] , "nets": {}}),
            ("ACCEPTANCE.json", {"checks": [], "production_ready": True, "fabrication_approved": False}),
        )
        for filename, value in replacements:
            with self.subTest(filename=filename), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                write_contract(root)
                (root / filename).write_text(json.dumps(value), encoding="utf-8")
                with self.assertRaises(ContractError):
                    load_project_contract(root)

    def test_duplicate_requirement_ids_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_contract(root)
            spec = json.loads((root / "SPEC.json").read_text())
            spec["requirements"].append(spec["requirements"][0])
            (root / "SPEC.json").write_text(json.dumps(spec))
            with self.assertRaises(ContractError) as ctx:
                load_project_contract(root)
            self.assertIn("requirement IDs must be unique", str(ctx.exception))

    def test_invalid_project_name_in_toml_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_contract(root)
            config = (root / "project.toml").read_text()
            (root / "project.toml").write_text(config.replace('name = "test-project"', 'name = "123"'))
            with self.assertRaises(ContractError) as ctx:
                load_project_contract(root)
            self.assertIn("project.name must be a valid string", str(ctx.exception))

    def test_project_name_mismatch_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_contract(root)
            spec = json.loads((root / "SPEC.json").read_text())
            spec["project"]["name"] = "different-name"
            (root / "SPEC.json").write_text(json.dumps(spec))
            with self.assertRaises(ContractError) as ctx:
                load_project_contract(root)
            self.assertIn("project name mismatch", str(ctx.exception))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "project"
            root.mkdir()
            write_contract(root)
            outside = root.parent / "outside.zen"
            outside.write_text("Board()", encoding="utf-8")
            config = (root / "project.toml").read_text(encoding="utf-8")
            (root / "project.toml").write_text(config.replace("src/board.zen", "../outside.zen"), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_project_contract(root)


    def test_unknown_connectivity_component_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_contract(root)
            conn = json.loads((root / "expected-connectivity.json").read_text())
            conn["nets"]["N1"]["members"].append("MISSING.P1")
            (root / "expected-connectivity.json").write_text(json.dumps(conn))
            with self.assertRaises(ContractError) as ctx:
                load_project_contract(root)
            self.assertIn("unknown component", str(ctx.exception))

    def test_unknown_required_power_net_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_contract(root)
            conn = json.loads((root / "expected-connectivity.json").read_text())
            conn["rules"]["required_power_nets"] = ["GHOST"]
            (root / "expected-connectivity.json").write_text(json.dumps(conn))
            with self.assertRaises(ContractError) as ctx:
                load_project_contract(root)
            self.assertIn("GHOST", str(ctx.exception))

    def test_unknown_pullup_component_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_contract(root)
            conn = json.loads((root / "expected-connectivity.json").read_text())
            conn["nets"]["N1"]["required_pullup"] = {"component": "MISSING", "rail": "N1"}
            (root / "expected-connectivity.json").write_text(json.dumps(conn))
            with self.assertRaises(ContractError) as ctx:
                load_project_contract(root)
            self.assertIn("MISSING", str(ctx.exception))

    def test_unknown_pullup_rail_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_contract(root)
            conn = json.loads((root / "expected-connectivity.json").read_text())
            conn["nets"]["N1"]["required_pullup"] = {"component": "U1", "rail": "MISSING"}
            (root / "expected-connectivity.json").write_text(json.dumps(conn))
            with self.assertRaises(ContractError) as ctx:
                load_project_contract(root)
            self.assertIn("MISSING", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
