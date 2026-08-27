# pcb-ai-agent

Vendor-neutral deterministic harness for Diode/Zener PCB projects. Python core
uses standard library only. AI backends may edit allowed source, but never
decide verification truth or fabrication approval.

## Local Use

Requires Python 3.11+. Run from repository without installation:

```sh
./pcb-agent doctor --project fixtures/valid-blinky --format json
./pcb-agent verify --project fixtures/valid-blinky --profile schematic
```

Windows can use:

```powershell
python pcb-agent doctor --project fixtures/valid-blinky --format json
```

Editable installation is optional: `python -m pip install -e .`. Core has no
third-party Python dependency.

## Commands

`doctor`, `build`, `check`, `layout`, `drc`, `verify`, `report`, and
`run --backend <command|codex> "<task>"` are available. External command flags
are capability-probed before execution. Hidden netlist, KiCad ERC, autorouting,
Gerber generation, manufacturing, and order commands are absent.

## Profiles

- `schematic`: contract, Diode build, immutable-snapshot TestBench, report.
  The harness extracts deterministic testing code from `SPEC.json` and
  `expected-connectivity.json`, rendering a generated TestBench and evaluating
  it strictly against `tests/.pcb-agent-connectivity.generated.zen`. Static
  coverage and unverified mappings return `BLOCKED`.
- `layout`: all schematic gates, Diode layout generation/check, direct KiCad 10
  JSON DRC. Missing required KiCad is `BLOCKED`.

Layout and SPICE checks are `SKIPPED` under schematic profile. SPICE execution
is deferred in MVP.

## Status And Exit

| Status | Exit | Meaning |
|---|---:|---|
| `PASS` | 0 | Required deterministic checks passed |
| `FAIL` | 1 | Deterministic validation failed |
| `BLOCKED` | 2 | Required dependency/evidence unavailable |
| invalid input | 3 | Contract/configuration invalid |
| backend terminal failure | 4 | Crash, timeout, no-progress, iteration limit |
| `HUMAN_REVIEW` | 5 | Explicit human decision blocks continuation |

`human_review_required: true` does not force exit 5. Every report keeps
`production_ready: false` and `fabrication_approved: false`.

## Reports

Runs write `reports/<run-id>/verify-report.json`, Markdown summary, and raw
evidence. Reports include checks, sanitized command metadata, durations, hashes,
and immutable safety fields. Dirty Git worktrees are allowed and reported when
Git metadata is available.

## AI Backends

Generic command backend reads a TOML argv array and transports task through
stdin or one literal argv value. It never uses shell interpolation. Agent runs
are limited to five attempts, reject nested `PCB_AGENT_ACTIVE`, protect contract
and TestBench files, detect no-progress, and independently invoke verification.

Codex adapter only probes `codex exec --help`; invocation remains disabled until
installed-version flags and permission behavior are verified. Repository skill
`agents/openai.yaml` is intentionally `BLOCKED` and absent because no consumer
format was verified.

## Security Boundary

- Executables inside workspace are rejected.
- CWD and files must remain in canonical workspace.
- Child environment is allowlisted; secrets and output are bounded/redacted.
- Protected files are hashed and snapshotted; trusted TestBench runs from
  harness-owned evidence copy.
- Network policy is deny by default. MVP does not claim OS-level network
  isolation for arbitrary backend binaries; only explicitly approved fake/local
  backends should be configured until sandbox enforcement exists.
- No `sudo`, installer execution, recursive cleanup, autorouter, manufacturing,
  or ordering action is provided.

## External Integration Status

Empirical run on 2026-08-24:

- Diode `pcbc 0.4.34` on WSL2 accepted `valid-blinky` build and both locked
  TestBench checks.
- `invalid-syntax` failed build; `invalid-connectivity` and `invalid-value`
  built successfully then failed their locked tests as intended.
- Windows-native Diode remained `BLOCKED` by Windows privilege error 1314.
- KiCad CLI 10.0.3 ran JSON DRC against an official Diode board fixture; it
  returned exit 5 for three violations, matching harness mapping.
- KiCad Linux 10.0.5 and `pcbnew` were installed from signed official KiCad
  PPA. End-to-end layout harness generated a board, ran Diode layout check,
  and ran direct KiCad JSON DRC.
- Generated `valid-blinky` layout correctly remained `FAIL`: missing board
  outline, five silkscreen warnings, and one unconnected item. No routing or
  fabrication artifact was generated.

Fixture syntax and TestBench APIs were corrected against real Diode 0.4.34 and
source snapshot `ee4e7e2b90fbe5f787d165a0780eba42664449ab`.

## Human Limitation

Verification PASS does not mean production-ready. Fabrication requires review
and approval by a human engineer.
