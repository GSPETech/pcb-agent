# Failure Classification

| Status | Use when | Exit |
|---|---|---:|
| `PASS` | All required checks completed and passed | 0 |
| `FAIL` | Deterministic required check found mismatch | 1 |
| `BLOCKED` | Required dependency/evidence unavailable | 2 |
| `HUMAN_REVIEW` | Required human decision unresolved | 5 |
| `SKIPPED` | Optional/not-applicable check not run | 0 |

Invalid contract/config/input uses exit `3`. Backend crash, timeout, invalid
result envelope, no-progress, or iteration limit uses exit `4` and overall
`BLOCKED` with explicit reason.

`warning` is severity, not status. Optional failed check keeps factual
`FAIL`/`BLOCKED`; policy fixed before run decides whether it changes overall
status. Never rewrite factual status to gain overall PASS.

Precedence: invalid contract, backend failure, required blocker, required
failure, unresolved human gate, then PASS. Preserve raw evidence and provenance:
`tool`, `harness`, `ai_inference`, `unverified_claim`, or `human_approval`.
