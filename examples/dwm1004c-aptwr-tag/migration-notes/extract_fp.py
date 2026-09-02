import re, os

pcb_file = r'D:\Project_Rendra\DECAWAVE\SCH-PCB\dwm1004c_aptwr_tag\dwm1004c_aptwr_tag.kicad_pcb'
with open(pcb_file, 'r', encoding='utf-8') as f:
    content = f.read()

# Extract footprints
out_dir = r'\\wsl.localhost\Ubuntu-24.04\home\rendra\dwm-tag-passive\src\custom_footprints'
os.makedirs(out_dir, exist_ok=True)

refs = ['U1', 'U2', 'U4', 'U5', 'U6', 'J1', 'J2', 'J3', 'J4', 'S1']

# Regex to match (footprint "Lib:Name" ... (property "Reference" "REF" ... )
# Since S-expressions can be nested, regex is tricky. Let's do simple brace matching.

def find_footprints(content, refs):
    results = {}
    idx = 0
    while True:
        idx = content.find('(footprint', idx)
        if idx == -1: break
        
        # find matching closing parenthesis
        depth = 0
        end_idx = idx
        for i in range(idx, len(content)):
            if content[i] == '(': depth += 1
            elif content[i] == ')': depth -= 1
            
            if depth == 0:
                end_idx = i + 1
                break
                
        fp_str = content[idx:end_idx]
        
        # find Reference
        ref_m = re.search(r'\(property\s+"Reference"\s+"([^"]+)"', fp_str)
        if ref_m:
            ref = ref_m.group(1)
            if ref in refs:
                # Remove absolute position (at X Y angle) at the top level
                # The top-level (at ...) is right after the footprint name
                # e.g. (footprint "Name" (layer "F.Cu") (uuid "...") (at X Y)
                fp_clean = re.sub(r'\(at\s+[-0-9.]+\s+[-0-9.]+(\s+[-0-9.]+)?\)', '(at 0 0)', fp_str, count=1)
                results[ref] = fp_clean
        idx = end_idx
    return results

fps = find_footprints(content, refs)
for ref, fp_str in fps.items():
    fp_name = f"{ref}.kicad_mod"
    with open(os.path.join(out_dir, fp_name), 'w', encoding='utf-8') as f:
        f.write(fp_str)
    print(f"Extracted footprint for {ref}")

