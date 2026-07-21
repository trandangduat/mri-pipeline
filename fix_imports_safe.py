import os
import glob
import re

files = glob.glob("pipeline/*.py") + glob.glob("ui/*.py") + glob.glob("ui/**/*.py", recursive=True) + glob.glob("*.py")
registry_symbols = {"TOOL_DEFS", "DISABLED_DOCKER_IMAGES", "TOOL_DISPLAY_ALIASES", "STAGE_ORDER", "STAGE_LABELS", "tool_display_name", "tool_key_from_display", "is_tool_enabled", "enabled_tools_for_stage"}
presets_symbols = {"PIPELINE_MODES", "PIPELINE_MODE_ALIASES", "VOLUME_SKIPPED_STAGES", "_BASE_FS7_TOOLS", "FREESURFER_7_TOOLS", "FREESURFER_7_SURFACE_TOOLS", "FREESURFER_8_TOOLS", "FREESURFER_8_SURFACE_TOOLS", "FASTSURFER_TOOLS", "FASTSURFER_SURFACE_TOOLS", "VOLUME_STATS", "THICKNESS_STATS", "PRESET_CONFIGS"}

for fpath in files:
    if fpath in ("pipeline/registry.py", "pipeline/presets.py", "split_config.py", "fix_imports_safe.py"):
        continue
        
    try:
        with open(fpath, "r") as f:
            lines = f.readlines()
            
        new_lines = []
        changed = False
        
        for i, line in enumerate(lines):
            match = re.match(r"^(from (?:\.|pipeline\.)config import )(.*)", line)
            if match:
                base_import = match.group(1)
                symbols_str = match.group(2)
                
                # handle line continuation/parentheses naively if needed, but in our codebase they are mostly single line without parens
                symbols = [s.strip() for s in symbols_str.split(',')]
                
                config_syms = []
                registry_syms = []
                presets_syms = []
                
                for s in symbols:
                    if not s: continue
                    if s in registry_symbols:
                        registry_syms.append(s)
                    elif s in presets_symbols:
                        presets_syms.append(s)
                    else:
                        config_syms.append(s)
                        
                if registry_syms or presets_syms:
                    changed = True
                    prefix = "." if fpath.startswith("pipeline/") else "pipeline."
                    
                    if config_syms:
                        new_lines.append(f"{base_import}{', '.join(config_syms)}\n")
                    if registry_syms:
                        new_lines.append(f"from {prefix}registry import {', '.join(registry_syms)}\n")
                    if presets_syms:
                        new_lines.append(f"from {prefix}presets import {', '.join(presets_syms)}\n")
                else:
                    new_lines.append(line)
            else:
                new_lines.append(line)
                
        if changed:
            with open(fpath, "w") as f:
                f.writelines(new_lines)
            print(f"Fixed {fpath}")
            
    except Exception as e:
        print(f"Error {fpath}: {e}")

