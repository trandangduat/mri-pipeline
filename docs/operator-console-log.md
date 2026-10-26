# Log

The console belongs to the selected job and subject.
One text area shows every recorded stage and attempt, including its saved output tail.
Stage names, tools, start times, status, errors, and retry decisions appear inside the text.
The card contains its title, Download button, Summary/Detailed controls, search, and one scrolling text area.
Summary shows stage activity. Detailed includes the output tails for all stages in the same text area.
Search filters displayed lines without making another server request.
The line number column stays aligned when long lines wrap.
Search preserves the original positions within the displayed text.
Line numbers are excluded from text selection and do not change downloaded files.
There is no stage selector or separate metadata panel.
The two streams remain combined, as in the existing executor.

## New jobs

The worker marks new jobs with `console_log_version: 1`.
The executor drains output while the tool runs.
It writes complete captured bytes to the job's `console` directory.
Only the last 64 KiB remain in the execution result buffer.
Existing short diagnostic logs remain available.

Each capture has a unique record identifier and a separate metadata file.
Metadata identifies the job, subject, input, stage, attempt, start, status, exit code, and saved byte count.
The scheduler adds its actual retry decision after committing a result.
Capture failures are marked separately from processing success.
The original scheduler checkout is unchanged.

Each stage shows up to 200 output lines. The complete view has a 64 KiB text limit.
Line counts describe saved output. Long individual lines can also require byte truncation.
Scrolling upward pauses the displayed output. Scrolling back to the bottom resumes updates.

The expanded console requests updates about every ten seconds during execution.
Requests do not overlap within a console instance.
Changing subjects disposes the earlier request and clears its display state.
Terminal state changes trigger a final read.
Collapsed consoles do not poll.
If an older running backend cannot provide the combined format, the console shows its recorded stage activity.
It requests a restart to include tool output. It does not report existing records as missing.
Current backends advertise their supported formats and reject unknown modes.

Activity reads are incremental and cached.
Each cached history retains at most 20,000 non-metric events and 4 MiB of source event data.
The reader reports when earlier activity falls outside that limit.
Tool output files remain independent of the activity history limit.

## Older jobs

Older jobs do not need modification or another MRI run.
The reader uses existing events, scheduler attempts, and verified subject log directories.
Completed SQLite records use immutable, read-only access.
The reader skips a database with a nonempty WAL file.
It does not import or change the original scheduler package.

Exact subject fields and prefixes take priority.
Unlabeled events require a verified single-subject or exclusive sequential context.
Concurrent messages without a confirmed subject remain unassigned.
The subject console never falls back to the complete shared job log.

Older tool logs can combine attempts and omit earlier output.
The console identifies that limitation.
Recorded stage metadata can appear without claiming an exact output-to-attempt mapping.
Missing times, exit codes, and attempt numbers remain unavailable.
New jobs never reuse older output files as current capture records.

## Download

The card header contains the Download button.
It saves all available selected-subject tool output, including content hidden by display limits.
The backend streams source files into the selected local file.
It does not load the complete export into browser memory.
It refuses to overwrite existing files.

The combined log contains activity, stage boundaries, original output bytes, and an export manifest footer.
The footer records source identifiers, byte ranges, lengths, and SHA-256 values.
Use `monitor_operator_console.py verify-export` to compare them with independently read server files.
A running-job export is a snapshot. Later output can extend the source files.
Missing historical output cannot be recovered by exporting.

## Manual test workspace

Load `configs/workspaces/FS8_Volume_Console_Test_3Subjects.json` through the UI.
It selects the FreeSurfer 8 Volume preset and policy B6.
It includes scans I7025, I7274, and I7054 from three different ADNI subjects.
Each existing server series contains 160 DICOM files.
Only reorientation, segmentation, and statistics extraction are enabled.

The workspace uses eight CPU threads, 50% RAM, and a three-task concurrency ceiling.
It disables warmup and resume.
Its separate server workspace is `/home/catcd1/neuroflow_console_test_fs8_volume_20261027`.
Its output directory is that workspace's `outputs` directory.
The UI creates the server workspace during normal job preparation.
No job was started during implementation.

Restart NeuroFlow through `run-gui.bat` before reviewing this change.
This reloads backend source and the native Save dialog permission.
See `docs/operator-console-monitoring.md` for capture commands and manual checkpoints.
