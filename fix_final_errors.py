import re
import os

with open("pipeline/hardware.py", "r") as f:
    c = f.read()
if "import socket" not in c:
    c = c.replace("import os", "import os\nimport socket")
with open("pipeline/hardware.py", "w") as f:
    f.write(c)

with open("pipeline/reports.py", "r") as f:
    c = f.read()
c = c.replace("from .utils import", "from .utils import _as_number,")
imports = "from .state import _load_pipeline_state\nfrom .config import StepResult\nfrom .registry import STAGE_LABELS, tool_display_name\n"
c = c.replace("from datetime import datetime\n", "from datetime import datetime\n" + imports)
with open("pipeline/reports.py", "w") as f:
    f.write(c)

with open("ui/dialogs/job_dialogs.py", "r") as f:
    c = f.read()
imports = "from remote.remote_runner import RemoteRunner, RemoteRunConfig\nfrom ui.formatters import truncate_middle\n"
c = imports + c
with open("ui/dialogs/job_dialogs.py", "w") as f:
    f.write(c)
