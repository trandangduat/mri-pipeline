# Monitor the Operator Console redesign

Use `scripts/monitor_operator_console.py` for the next job started through the UI.
The monitor runs on this computer. It reads catcd1 through one persistent SSH connection.
It does not start, stop, or modify MRI jobs.
It creates no server files and installs no server packages.
It does not change NeuroFLOW-private.

The console redesign saves new tool output under each job's `console` directory.
The monitor includes that directory in its storage measurements.
Use this script for the redesign's manual review.

## Measurements

| Area | Recorded information |
|---|---|
| Local UI | Process CPU, RAM, thread count, and available process I/O counters |
| Local backend | The same process measurements, separate from the UI |
| Monitor overhead | Local monitor CPU and RAM; remote probe CPU, duration, and payload bytes |
| Local network | Received and sent bytes for each network interface |
| Server | Host CPU counters, available RAM, network counters, and free disk space |
| Worker | Worker CPU, RAM, and available I/O counters |
| Tasks | Recent existing container metric records, with their original timestamps |
| Log storage | Discovered log file counts and total saved bytes |
| Connections | Current TCP connections to the configured server address and SSH port |
| UI checkpoints | Your phase, selected subject, stage, attempt, manual result, notes, and evidence path |
| UI requests | Optional HAR request times, status errors, and known response body sizes |
| Download | Combined export verification against independently read server files; optional raw file comparisons |

Local samples use a five-second interval.
Remote samples use a thirty-second interval.
File inventories include paths every five minutes. Other remote samples contain counts and sizes only.
The remote probe reads at most 64 KiB from the existing task metric tail each time.
It does not call Docker or run MRI tools.
The default log inventory limit is 1,000 files.
Inventory limits are recorded. Partial inventories must not be treated as complete totals.

## Start capture

Start the job through NeuroFlow. Copy its exact server job directory from the UI.
Run this command from the repository root in PowerShell:

```powershell
$session = 'build/operator_console_monitor/NEW_JOB_ID'
.venv/Scripts/python.exe scripts/monitor_operator_console.py capture `
  --session $session `
  --job-dir '/home/catcd1/YOUR_WORKSPACE/NEW_JOB_ID'
```

Replace both placeholders. Do not copy another job's directory.
The monitor can wait if the specified directory does not exist yet.
It does not discover or attach to unrelated jobs automatically.

Server defaults are `10.8.0.1:19622`, user `catcd1`, and key `~/.ssh/duat`.
The monitor checks the existing SSH known-host records.
It rejects unknown host keys instead of changing known_hosts.

The repository environment already contains psutil and paramiko.
Use `.venv/Scripts/python.exe`, rather than the system Python.

Use `--app-pid NUMBER` if UI process discovery misses your application.
Use `--backend-pid NUMBER` if backend discovery misses your backend.
Both options include child processes and can be repeated.
Check the recorded process names before interpreting their totals.

Use `--remote-log-root '/absolute/log/directory'` for a future log location outside the discovered roots.
Repeat this option when needed. Use specific log directories, not the MRI data root.

The monitor normally stops two minutes after observing a terminal job state.
Use `--finish-grace 600` to allow ten minutes for final UI checks.
Use `--duration 1800` for a thirty-minute capture limit.
Press Ctrl+C to stop sooner and generate the report.
Closing the terminal forcibly can prevent the final report. Saved JSONL samples remain usable.

## Mark manual UI phases

Open another PowerShell terminal in the repository root.
Set `$session` to the same directory.
Keep each main phase open for approximately two minutes.
Open the console early if the job finishes quickly.

```powershell
$session = 'build/operator_console_monitor/NEW_JOB_ID'
.venv/Scripts/python.exe scripts/monitor_operator_console.py mark --session $session --phase closed
```

Then expand the text console and record the change:

```powershell
.venv/Scripts/python.exe scripts/monitor_operator_console.py mark --session $session --phase console --subject 'SUBJECT_ID'
```

Record a stage or attempt when you review its text section:

```powershell
.venv/Scripts/python.exe scripts/monitor_operator_console.py mark `
  --session $session --phase console --subject 'SUBJECT_ID' --stage 'STAGE_KEY' --attempt 'ATTEMPT_ID'
```

Use the actual subject, stage, and attempt shown by the application.
Marks describe your observations. They do not automatically verify UI content.

Record a subject isolation check after switching between two active subjects:

```powershell
.venv/Scripts/python.exe scripts/monitor_operator_console.py mark `
  --session $session --phase console --subject 'SUBJECT_ID' `
  --check subject_isolation --result pass `
  --note 'Only the selected subject appears.' `
  --evidence 'C:/path/to/manual-screenshot.png'
```

Use `--result fail` when you observe a defect.
Use `--result unknown` when the evidence is insufficient.
The monitor records the evidence path. It does not capture or copy screenshots.

Record these checks when applicable:

- `subject_isolation`: No other subject appears after switching or refreshing.
- `stage_header`: The stage, tool, start time, attempt, and status in the text match saved records.
- `live_refresh`: New output appears during execution, with no duplicate lines.
- `tail_limit`: The view remains bounded and shows the correct saved-line count.
- `scroll_pause`: New output does not move the view while you inspect older text.
- `final_refresh`: Final output appears after the job reaches a terminal state.
- `download_complete`: The download includes the beginning and end of all available selected-subject records.
- `old_job`: Existing completed jobs display available records and identify missing output.
- `failure_output`: A failed attempt displays its actual error, exit code, and retry state.

A successful job does not exercise failure or retry behavior.
Use existing failed records for those checks when available.
Do not stop or damage an MRI job to manufacture a failure.

Before downloading, mark the download phase:

```powershell
.venv/Scripts/python.exe scripts/monitor_operator_console.py mark --session $session --phase download --subject 'SUBJECT_ID'
```

## Optional UI request measurements

The script does not intercept application traffic or change the backend.
Exact UI request duration and response sizes require a manual HAR network export.

If application developer tools are available, open their Network panel before the review.
Preserve the network history. Export a HAR file after the review.
Store it inside the ignored session directory.
HAR files can contain input paths, request contents, and credentials. Do not commit or share the original HAR.

The report retains endpoint paths, timings, response sizes, and error counts only.
It does not retain request headers, tokens, queries, or message bodies.
Request timestamps associate measurements with your marked phases.
Requests from other job views in the same HAR are included. Use a dedicated capture window.

```powershell
.venv/Scripts/python.exe scripts/monitor_operator_console.py summarize `
  --session $session --har "$session/ui-network.har"
```

Without a HAR file, request timing remains `Not measured`.
Network interface totals must not be reported as exact UI bandwidth.
VPN interfaces can count the same traffic at different layers. Do not add all interface totals together.

## Verify the new combined subject download

The console's Download button produces one combined `.log` file.
Its footer records the source record identifiers, byte ranges, and SHA-256 values.
The monitor verifies those ranges against independently read server files.
It also checks whether every available saved tool record is included.

Run this command after downloading the selected subject log:

```powershell
.venv/Scripts/python.exe scripts/monitor_operator_console.py verify-export `
  --session $session --subject 'ACTUAL_SUBJECT_ID' `
  --download 'C:/path/to/downloaded-subject.log'
```

Use the actual subject selected in the UI.
A different subject is rejected.
Run verification after completion to compare the final output lengths.
A download during execution is a snapshot. Later output can make its length differ from the current server file.
Checksums cannot recover output that was never saved.

## Optional exact raw download comparison

Run this after the job finishes and its output file stops changing.
Use it only when the UI download is an exact raw copy of one known server file.

```powershell
.venv/Scripts/python.exe scripts/monitor_operator_console.py compare-download `
  --session $session `
  --download 'C:/path/to/downloaded-attempt.log' `
  --remote-source '/home/catcd1/YOUR_WORKSPACE/NEW_JOB_ID/tool_logs/KNOWN_ATTEMPT.log'
```

The command streams both files through SHA-256 and records whether their bytes match.
It also checks whether the server file changed during reading.
It writes the comparison result locally. It does not modify either log file.
The server file must resolve inside the job directory or an explicit remote log root.

Use `verify-export` for the new combined log format.
Do not compare a combined download directly with one constituent source file.
ZIP files and unrelated export formats are not handled by these comparison commands.

## Review the report

Regenerate the report after adding checks or download comparisons:

```powershell
.venv/Scripts/python.exe scripts/monitor_operator_console.py summarize --session $session
```

Include `--har` again when regenerating a report that needs request measurements.

| File | Purpose |
|---|---|
| `session.json` | Configuration, intervals, process identity, and capture times |
| `local_samples.jsonl` | Local process and interface samples |
| `remote_samples.jsonl` | Server, worker, task, log, and probe samples |
| `remote_errors.jsonl` | Failed server samples, when present |
| `marks.jsonl` | Manual phase changes and UI observations |
| `download_checks.jsonl` | Exact raw download comparisons, when requested |
| `summary.json` | Numeric summaries, missing measurements, and measurement limits |
| `report.md` | Short review report |

Review memory growth, CPU changes, request sizes, request duration, SSH connection counts, and monitor overhead.
Compare phases only when their processing conditions are similar.
Changing MRI stages can change resource usage independently of the console.
One monitored job can expose defects. It cannot prove zero performance cost under every workload.

The worker CPU measurement excludes Docker container processes.
Recent task metrics provide separate context from existing pipeline records.
Host values include other server workloads.
Process RAM totals can count shared pages more than once.
The monitor does not measure rendered frames, input response time, or exact per-process network bandwidth.
The user performs all UI checks manually.
