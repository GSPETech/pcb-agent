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

    def test_source_traversal_is_rejected(self) -> None:
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


if __name__ == "__main__":
    unittest.main()
