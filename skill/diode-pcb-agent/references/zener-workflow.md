# Zener Workflow

## Verified public syntax

Current docs expose `Module`, `Power`, `Ground`, `Net`, `Board`, generic
components, and `TestBench`. Board manifest is `pcb.toml` with `[workspace]`,
`pcb-version`, and `[board]`.

```python
Resistor = Module("@stdlib/generics/Resistor.zen")
Led = Module("@stdlib/generics/Led.zen")
VCC = Power()
GND = Ground()
LED_ANODE = Net()
Resistor(name="R1", value="1kohm", package="0402", P1=VCC, P2=LED_ANODE)
Led(name="D1", package="0402", color="red", A=LED_ANODE, K=GND)
Board(name="board", layers=4, layout_path="layout/board")
```

Evidence checked 2026-08-24:

- https://docs.pcb.new/pages/spec.md
- https://docs.pcb.new/pages/testing.md
- https://github.com/diodeinc/pcb/blob/ee4e7e2b90fbe5f787d165a0780eba42664449ab/examples/blinky.zen

## Commands

Public documented forms:

```sh
pcb sync --check
pcb build path/to/board.zen
pcb test path/to/board_test.zen -f json
pcb layout --no-open path/to/board.zen
```

Probe installed `pcb help <command>` before adding flags. Do not rely on hidden
netlist output as stable contract. `pcb build` proves compilation, not
engineering correctness. Diode does not provide a verified `.kicad_sch` output
contract for this workflow.

## TestBench

Load board/module, inspect `module.nets` and `module.components`, and use
`check(...)`. Keep acceptance tests immutable during agent repair.
