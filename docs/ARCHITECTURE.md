# Architecture

**PCB Agent harness design and verification model.**

---

## Design Goals

1. **Determinism:** Same contracts + same source → same verdict
2. **Fail-closed:** Unknown/unsupported → `BLOCKED`, never silent `PASS`
3. **Attestation:** Every verdict backed by hash-verified evidence
4. **Separation:** AI proposes, locked TestBenches decide
5. **Portability:** Stdlib-only core, no vendor lock-in

---

## System Layers

```
┌─────────────────────────────────────────────┐
│  CLI / MCP Server                           │  User interface
├─────────────────────────────────────────────┤
│  Orchestrator                               │  Workflow coordination
│  ├→ Schematic Agent                         │
│  ├→ Layout Agent                            │
│  └→ Routing Agent                           │
├─────────────────────────────────────────────┤
│  Verification Engine                        │  Gate execution
│  ├→ Contract Parser                         │
│  ├→ TestBench Generator                     │
│  ├→ Evidence Validator                      │
│  └→ Report Builder                          │
├─────────────────────────────────────────────┤
│  Adapter Registry                           │  Component kind mapping
│  └→ Evidence Bundle (SHA-256 manifest)      │
├─────────────────────────────────────────────┤
│  Process Isolation                          │  Sandbox, policy enforcement
├─────────────────────────────────────────────┤
│  External Tools                             │
│  ├→ Diode toolchain (pcb, pcbc)            │
│  ├→ KiCad (kicad-cli, pcbnew)              │
│  └→ Freerouting                             │
└─────────────────────────────────────────────┘
```

---

## Verification Model

### Trust Boundary

```
           AI Backend                 Harness
    ┌───────────────────┐      ┌─────────────────┐
    │  Propose edits    │      │  Generate       │
    │  to src/          │─────▶│  TestBench      │
    │                   │      │  from contracts │
    └───────────────────┘      └────────┬────────┘
                                        │
           ❌ NEVER CROSS               │ hash + snapshot
                │                       │
                ▼                       ▼
    ┌───────────────────┐      ┌─────────────────┐
    │  contracts/       │      │  Locked         │
    │  SPEC.json        │◀─────│  TestBench      │
    │  ACCEPTANCE.json  │      │  (trusted copy) │
    │  expected-*.json  │      └────────┬────────┘
    │  tests/*.zen      │               │
    └───────────────────┘               │ pcb test
                                        ▼
                                ┌─────────────────┐
                                │  Evidence       │
                                │  (JSON result)  │
                                └────────┬────────┘
                                         │ parse + verify
                                         ▼
                                    PASS / FAIL
```

**Key invariant:** AI never decides gate truth. Only locked TestBenches (owned and hashed by harness) emit verdicts.

---

## Gate Dependency Graph

```
schematic profile:
  CONTRACT ──→ DIODE_BUILD ──→ CONNECTIVITY ──→ SPECIFICATION
                                                      │
                                                      ↓
                                                   REPORT

layout profile:
  (all schematic) ──→ LAYOUT_GENERATE ──→ PLACEMENT ──→ ROUTE
                                                         │
                                                         ↓
                                              LAYOUT_SYNC ──→ KICAD_DRC
                                                                  │
                                                                  ↓
                                                               REPORT
```

**Cascade rule:** Failed/blocked prerequisite → dependents `BLOCKED`, never `FAIL`.

---

## Adapter Registry

### Purpose

Map abstract component kinds (`resistor`, `led`) to concrete Diode API:
```python
{
    "kind": "resistor",
    "verified_pcbc_versions": ["0.4.40"],
    "evidence_sha256": "a3f2...",
    "properties": {
        "value": "comp.resistance",
        "package": "comp.package"
    },
    "pins": {
        "pullup_pair": ["1", "2"]
    }
}
```

### Lifecycle

1. **Capture:** Run real Diode on fixture, record API behavior
2. **Register:** Store accessor + evidence hash in `generated_testbench.py`
3. **Validate:** Lazily verify evidence exists and matches hash on first use
4. **Generate:** Emit TestBench using verified accessors
5. **Block:** Unsupported kind/version → `BLOCKED`, never guess

**Evidence bundle:** `tests/evidence/diode-0.4.40/manifest.sha256` (148 entries)

---

## TestBench Generation

### Input (contracts)

```json
// SPEC.json
{
  "requirements": [
    {
      "id": "REQ-001",
      "description": "LED current limiting",
      "constraints": [
        {"type": "value", "component": "R1", "expected": "330Ω"}
      ]
    }
  ]
}

// expected-connectivity.json
{
  "components": {
    "R1": {"kind": "resistor", "value": "330Ω", "package": "0603"}
  },
  "nets": {
    "GPIO_LED": {"members": ["MCU.PA5", "R1.2"]}
  }
}
```

### Output (generated TestBench)

```python
# tests/.pcb-agent-specification.generated.zen
from diode import *

def test_REQ_001_LED_current_limiting(module, inputs):
    r1 = module.components()["R1"]
    # Adapter registry provides accessor:
    check(r1.resistance == "330Ω", "R1 value")
    check(r1.package == "0603", "R1 package")
```

**Hash chain:** contracts SHA-256 → generator → source SHA-256 → `pcb test` → result SHA-256 → verdict

---

## Security Model

### Workspace Containment

- All file ops canonicalized via `Path.resolve()`
- CWD never leaves workspace
- Symlinks rejected (except known bug S3)
- Executable search limited to system PATH (S2 bypass exists)

### Protected Files

Hashed before backend run, verified after:
```python
PROTECTED = [
    "project.toml",
    "SPEC.json",
    "ACCEPTANCE.json",
    "expected-connectivity.json",
    "tests/**/*.zen"  # all locked TestBenches
]
```

Mutation → `BLOCKED` + exit 4.

### Process Isolation

**Allowlist:**
```python
ENV_ALLOWLIST = [
    "PATH", "HOME", "USER", "TMPDIR",
    "LANG", "LC_*",
    "PCB_*"  # toolchain config
]
```

**Blocklist:**
```python
ENV_BLOCKLIST = [
    "LD_PRELOAD", "LD_LIBRARY_PATH",
    "PYTHONPATH", "NODE_PATH",
    "AWS_*", "GITHUB_TOKEN"
]
```

**Known hole (S6):** `HOME` passes through → child reads `~/.pcb` credentials.

### Output Sanitization

**Redacted patterns:**
```python
SECRET_PATTERNS = [
    r"sk-[A-Za-z0-9]{48}",           # OpenAI
    r"ghp_[A-Za-z0-9]{36}",          # GitHub
    r"xoxb-[0-9]{10,13}-[A-Za-z0-9]+" # Slack (S8: missing)
]
```

**Path sanitization:** Absolute home paths rewritten to `~` (S5: inconsistent).

---

## Report Structure

```json
{
  "run_id": "a3f2e1c4",
  "timestamp": "2026-09-02T14:32:10Z",
  "profile": "layout",
  "project": {
    "root": "/home/user/my_board",
    "git_branch": "feat/gps-tracker",
    "git_dirty": true,
    "git_commit": "a3f2e1c"
  },
  "gates": [
    {
      "id": "CONNECTIVITY",
      "status": "PASS",
      "duration_ms": 1243,
      "evidence": {
        "testbench_source_sha256": "7a3c...",
        "result_sha256": "9f2b...",
        "result_path": "reports/a3f2e1c4/raw/connectivity-result.json"
      }
    }
  ],
  "summary": {
    "status": "PASS",
    "passed": 7,
    "failed": 0,
    "blocked": 0
  },
  "safety": {
    "production_ready": false,
    "fabrication_approved": false,
    "human_review_required": true
  }
}
```

---

## AI Backend Integration

### Command Backend

```toml
# config/backends.toml
[[backends.command]]
name = "local-ai"
argv = ["python", "agent.py"]
input_method = "stdin"  # or "argv"
timeout_seconds = 300
max_iterations = 5
```

### Backend Lifecycle

```
1. Snapshot protected files (hash)
2. Set PCB_AGENT_ACTIVE=1
3. Fork backend process with allowlisted env
4. Transport task (stdin or argv)
5. Wait for exit (timeout 300s)
6. Verify protected files unchanged
7. Run independent verification
8. Fingerprint result (status + message hash)
9. Compare with previous iterations
10. If identical → no-progress → exit 4
11. If PASS → return
12. If iter < 5 → goto 2
13. Else → iteration limit → exit 4
```

**Guard (S7):** Backend check is `os.environ.get("PCB_AGENT_TEST_BACKEND") == "1"` → trivial bypass.

---

## Orchestrator Flow

### Full Profile

```python
async def run_orchestrator(task, project_dir, profile="full"):
    # Parse intent
    module_name = extract_module_name(task)
    requirements = extract_requirements(task)
    
    # Phase 1: Schematic
    schematic_result = await run_schematic_agent({
        "project_dir": project_dir,
        "module_name": module_name,
        "requirements": requirements
    })
    if schematic_result["status"] != "PASS":
        return early_exit(schematic_result)
    
    # Phase 2: Layout
    layout_result = await run_layout_agent({
        "project_dir": project_dir,
        "constraints": extract_constraints(task)
    })
    if layout_result["status"] != "PASS":
        return early_exit(layout_result)
    
    # Phase 3: Routing
    routing_result = await run_routing_agent({
        "project_dir": project_dir,
        "board_file": f"{project_dir}/build/board.kicad_pcb"
    })
    
    return {
        "status": routing_result["status"],
        "summary": summarize_phases([schematic, layout, routing]),
        "phases": {"schematic": ..., "layout": ..., "routing": ...}
    }
```

### Agent Delegation

Each agent:
1. Reads current state
2. Proposes edit (via LLM or rule-based)
3. Applies edit to `src/`
4. Calls `verify --profile <profile>`
5. If `PASS` → return
6. If `FAIL` → parse diagnostics → goto 2
7. If `BLOCKED` → escalate to human
8. If max_iterations → `HUMAN_REVIEW`

---

## Determinism Strategy

### Sources of Non-Determinism

❌ **Avoided:**
- LLM sampling during verification (agents propose, TestBenches decide)
- Network I/O during gates (all local file ops)
- Floating-point comparison (string equality on resistance values)
- Timestamp in verdict (timestamp in report only)

✓ **Accepted:**
- Placement algorithm (deterministic given component list + modules)
- Freerouting (empirically verified byte-identical on same DSN)

### Verification

```bash
# Reproducibility test
./pcb-agent verify --project fixtures/valid-blinky --profile layout > run1.json
./pcb-agent verify --project fixtures/valid-blinky --profile layout > run2.json
diff <(jq -S 'del(.timestamp, .run_id)' run1.json) \
     <(jq -S 'del(.timestamp, .run_id)' run2.json)
# Expected: no diff
```

**CI gap:** No automated reproducibility job yet.

---

## Performance Characteristics

### Schematic Profile

- Contract parse: ~10ms
- Diode build: ~500ms (fixture), ~2s (real board)
- TestBench generate: ~50ms
- `pcb test` run: ~200ms per check
- Evidence hash: ~20ms
- **Total:** ~1-3s for fixture, ~5-10s for real board

### Layout Profile

- LAYOUT_GENERATE: ~1-2s
- PLACEMENT: ~500ms (50 components)
- ROUTE (Freerouting): ~10-60s (depends on complexity)
- LAYOUT_SYNC: ~500ms
- KICAD_DRC: ~2-5s
- **Total:** ~15-70s

### Backend Loop

- Iteration overhead: ~2s (snapshot + verify + fingerprint)
- Agent LLM call: ~5-20s (depends on model)
- **Max time (5 iter):** ~2min (schematic), ~6min (layout)

---

## Extension Points

### New Component Kind

1. Create fixture: `fixtures/kind-<name>/`
2. Run `pcb build && pcb test` → capture evidence
3. Analyze JSON → extract property accessors
4. Register in `generated_testbench.py:captured_adapter_registry()`
5. Add evidence to `tests/evidence/diode-0.4.40/manifest.sha256`
6. Write test: `tests/test_adapters.py::test_<kind>_adapter`

### New Gate

1. Define in `models.py:GateID`
2. Implement in `gates/<name>.py`
3. Add to profile in `profiles.py`
4. Write evidence validator in `evidence.py`
5. Add to report schema in `report.py`
6. Write test with fixture that passes + fails

### New Backend

1. Create adapter in `backends/<name>.py`
2. Implement `run_backend(task, project_dir) -> BackendResult`
3. Register in `backends/__init__.py`
4. Add config schema to `config/backends.toml`
5. Write test with mock backend

---

## Testing Strategy

### Unit Tests

- Adapter registry validation
- TestBench generation (mocked `pcb test`)
- Evidence parsing (real captured JSON)
- Path validation (symlink, traversal, escape)
- Secret redaction

### Integration Tests

- Fixture verification end-to-end
- Invalid fixture rejection (syntax, connectivity, value)
- Profile execution (schematic, layout)
- Report generation

### Evidence Tests

- Hash verification against manifest
- Adapter accessor extraction
- Result reconciliation (counts, statuses)

**Coverage:** ~85% (src/), 19 Windows skips (symlink checks)

---

## Known Tech Debt

1. **Version pin fragile:** Re-capture 148 entries per patch → accept lane-range
2. **Upstream duplication:** Diode now ships `skills/`, `pcb dfm` → reconsider scope
3. **Status vocab split:** `PASS|PASSED|OK` vs `"pass"` → unify
4. **Fingerprint shallow:** Hash only status+message → miss compile error detail
5. **Lock reclaim broken:** Windows `os.kill(pid,0)` → stale lock forever
6. **Symlink check no-op:** After `resolve()` → always False (S3)
7. **Reports escape workspace:** Symlink attack (S1)
8. **Backend guard trivial:** Env var check (S7)
9. **Destructive restore:** `.git` unlink (S9), symlinks dropped (S10)
10. **Docs stale:** 230KB planning/review vs 120KB src → consolidate

---

## Future Work

### Short-Term

- Fix S9/S10 (destructive paths)
- Bind locked TestBench hash in `verify`
- Add lint job (ruff/black)
- Windows lock reclaim fix
- Consolidate docs

### Medium-Term

- Lane-range adapter support (`0.4.x`)
- CI auto-recapture on upstream release
- Streaming progress for MCP
- Cancel support for long-running routes
- Reproducibility CI job

### Long-Term

- SPICE gate implementation
- Crystal adapter (solve 1→4 GND mapping)
- IC/connector adapters
- OS-level network sandbox
- Gerber generation gate
- Manufacturing DFM gate
