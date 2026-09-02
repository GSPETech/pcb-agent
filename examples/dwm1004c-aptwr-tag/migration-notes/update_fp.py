import re

wsl_board_zen = r'\\wsl.localhost\Ubuntu-24.04\home\rendra\dwm-tag-passive\src\board.zen'
content = open(wsl_board_zen, 'r', encoding='utf-8').read()

# Replace the testpoint footprint with the custom footprints
for ref in ['U1', 'U2', 'U4', 'U5', 'U6', 'J1', 'J2', 'J3', 'J4', 'S1']:
    # Regex to match the footprint of specific ref
    pattern = rf"({ref} = Component\([^)]*footprint=)'[^']+'"
    replacement = rf"\g<1>'custom_footprints/{ref}.kicad_mod'"
    content = re.sub(pattern, replacement, content)

with open(wsl_board_zen, 'w', encoding='utf-8') as f:
    f.write(content)

print("Updated footprints")
