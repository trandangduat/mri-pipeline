import ast
import tokenize
from io import BytesIO

def get_node_name(node):
    if isinstance(node, ast.Assign) and getattr(node.targets[0], 'id', None):
        return node.targets[0].id
    if isinstance(node, ast.AnnAssign) and getattr(node.target, 'id', None):
        return node.target.id
    if isinstance(node, ast.FunctionDef):
        return node.name
    if isinstance(node, ast.ClassDef):
        return node.name
    return None

def main():
    registry_names = {"TOOL_DEFS", "DISABLED_DOCKER_IMAGES", "TOOL_DISPLAY_ALIASES", "STAGE_ORDER", "STAGE_LABELS", "tool_display_name", "tool_key_from_display", "is_tool_enabled", "enabled_tools_for_stage"}
    presets_names = {"PIPELINE_MODES", "PIPELINE_MODE_ALIASES", "VOLUME_SKIPPED_STAGES", "_BASE_FS7_TOOLS", "FREESURFER_7_TOOLS", "FREESURFER_7_SURFACE_TOOLS", "FREESURFER_8_TOOLS", "FREESURFER_8_SURFACE_TOOLS", "FASTSURFER_TOOLS", "FASTSURFER_SURFACE_TOOLS", "VOLUME_STATS", "THICKNESS_STATS", "PRESET_CONFIGS"}

    with open("pipeline/config.py", "r") as f:
        src = f.read()

    tree = ast.parse(src)
    
    registry_src = "from __future__ import annotations\n\n"
    presets_src = "from __future__ import annotations\n\n"
    config_src = ""
    
    # We will use ast.get_source_segment which accurately grabs the source block
    # However, comments before the node might be lost.
    # A line-based approach using node.lineno and node.end_lineno is better.
    
    lines = src.split('\n')
    used_lines = set()
    
    for node in tree.body:
        name = get_node_name(node)
        if name:
            start = node.lineno - 1
            # Adjust start for decorators
            if hasattr(node, 'decorator_list') and node.decorator_list:
                start = node.decorator_list[0].lineno - 1
            end = node.end_lineno
            block = '\n'.join(lines[start:end]) + '\n\n'
            
            if name in registry_names:
                registry_src += block
                used_lines.update(range(start, end))
            elif name in presets_names:
                presets_src += block
                used_lines.update(range(start, end))
                
    # Reconstruct config_src from lines not in used_lines
    config_lines = []
    i = 0
    while i < len(lines):
        if i not in used_lines:
            config_lines.append(lines[i])
        i += 1
        
    config_src = '\n'.join(config_lines)
    # clean up multiple empty lines
    import re
    config_src = re.sub(r'\n{3,}', '\n\n', config_src)
    
    with open("pipeline/registry.py", "w") as f:
        f.write(registry_src)
        
    with open("pipeline/presets.py", "w") as f:
        f.write(presets_src)
        
    with open("pipeline/config.py", "w") as f:
        f.write(config_src)
        
    print("Split completed successfully!")

if __name__ == "__main__":
    main()
