# Layout Review

Run layout only after schematic gates pass and task includes layout scope.
Treat `.kicad_pcb` as maintained state: preserve placement, routing, zones, and
human edits. Capture pre/post hash and semantic diff before accepting update.

Suggested sequence after installed help confirms flags:

```sh
pcb layout --no-open board.zen
pcb layout --check -f json board.zen
kicad-cli pcb drc --format json --output drc.json --severity-all --exit-code-violations board.kicad_pcb
```

KiCad exit `5` with `--exit-code-violations` means DRC violations and maps to
domain `FAIL`, not tool blocker. Other exits need classification from stderr,
version, and artifact availability.

Do not mutate board during default verification with save/refill options.
Check outline, layer count, unrouted connections, clearance, placement state,
and raw DRC. Require human review for return paths, SI/RF, thermal, mechanical,
DFM, EMI/EMC, and fabrication.
