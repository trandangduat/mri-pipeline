import os

with open("ui/main.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

# Extract lines from 47 to 139 (0-indexed 46 to 139)
start_idx = 46
end_idx = 139
presets_code = "".join(lines[start_idx:end_idx]).replace("    ", "", 1) # remove one level of indentation

# Remove the lines from main.py
del lines[start_idx:end_idx]

# Prepend imports to main.py
import_str = """
from pipeline_runner import (
    PIPELINE_MODES, PIPELINE_MODE_ALIASES, VOLUME_SKIPPED_STAGES, PRESET_CONFIGS,
)
"""
# Find where from pipeline_runner import ( is
for i, line in enumerate(lines):
    if line.startswith("from pipeline_runner import ("):
        # Insert the imports before it
        lines.insert(i, import_str.strip() + "\n")
        break

with open("ui/main.py", "w", encoding="utf-8") as f:
    f.writelines(lines)

with open("pipeline/config.py", "a", encoding="utf-8") as f:
    f.write("\n\n" + presets_code + "\n")

print("Done extracting presets.")
