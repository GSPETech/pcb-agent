wsl_board_zen = r'\\wsl.localhost\Ubuntu-24.04\home\rendra\dwm-tag-passive\src\board.zen'
content = open(wsl_board_zen, 'r', encoding='utf-8').read()

import re
# Replace footprint='...' with footprint='@stdlib/kicad-footprints/TestPoint.pretty/TestPoint_Pad_D1.0mm.kicad_mod'
content = re.sub(r"footprint='[^']+'", "footprint='@stdlib/kicad-footprints/TestPoint.pretty/TestPoint_Pad_D1.0mm.kicad_mod'", content)

with open(wsl_board_zen, 'w', encoding='utf-8') as f:
    f.write(content)
