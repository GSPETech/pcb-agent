# Examples

Real projects verified with `pcb-agent`, kept so the harness's behaviour on
actual designs can be inspected and re-run.

| Example | What it shows |
|---|---|
| [`dwm1004c-aptwr-tag/`](dwm1004c-aptwr-tag/) | 72-component UWB tag migrated from KiCad. Hierarchical modules, placement and routing gates, and the coverage limits of the adapter registry. |

These are not pytest fixtures. They need a real `pcbc` toolchain, and the layout
profile additionally needs `freerouting` and the `pcbnew` Python bindings, none
of which are available in CI. Fixtures that CI does run live in `fixtures/`.
