# path-traversal

This fixture is intentionally invalid: `project.toml` declares `source` as a
relative path that escapes the project root. The contract loader must reject
this with `ContractError` / `PathViolation`.

Do not "fix" the source path. The whole point of the fixture is to verify
that the harness refuses project definitions that try to read files outside
their declared workspace.