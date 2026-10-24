# Baseline policy integration

The application keeps the original `NeuroFLOW-private` source unchanged.
Integration version: `1.0.0`.

| Policy | Order | Configuration choice | Profile learning | Protected backfill |
|---|---|---|---|---|
| B0 | FIFO by ready time; one active reservation | Explicit fixed stage default | Disabled | Disabled |
| B1 | FIFO; first fit | Explicit fixed stage default | Disabled | Disabled |
| B2 | Shortest initial runtime; first fit | Explicit fixed stage default | Disabled | Disabled |
| B3 | Static critical-path rank; first fit | Fastest feasible static estimate | Disabled | Disabled |
| B4 | Static critical-path rank | Fastest feasible static estimate that preserves the protected start | Disabled | Enabled |
| B5 | FIFO | Original multi-resource selection and resource upgrades | Enabled | Disabled |
| B6 | Original NeuroFLOW | Original NeuroFLOW | Original behavior | Original behavior |
| B7 | HEFT rank and earliest finish | Online insertion on one host | Disabled | HEFT calendar |

FIFO ties use ready time, image insertion order, stage order, and task ID.
B0 waits when the first task cannot fit.
B1 and B2 can select a later task that fits.
B3 and B4 use full descendant costs.
They do not add an aging bonus.
Static configuration ties use RAM, threads, and configuration ID.
B5 retains the configured warm-up switch and success thresholds.
Static policies disable warm-up.

## Fixed configurations

B0, B1, and B2 require one default for each stage with multiple configurations.
The application does not choose the first, smallest, or fastest configuration as a default.
A stage with one declared configuration needs no explicit entry.
The selected default must fit the hard CPU, RAM, and GPU limits.
A temporary shortage does not change this default.

Set `neuroflow_default_configurations` in the run request.
The UI provides a JSON field for these policies.
For example, the FreeSurfer 8 volume preset can use this explicit choice:

```json
{
  "reorient_resize": "cpu_1",
  "subcortical_segmentation": "cpu_1",
  "statistics_atlas_mapping": "cpu_1"
}
```

This example is a user choice, not a new scientific reference default.
A custom preset can declare the same mapping under `metadata.baseline_default_configurations`.
Request values override preset values.
The job record identifies the source of each choice.

## Reused library operations

| Requirement | Original operation | External addition |
|---|---|---|
| Dependency graph | Coordinator creation and image insertion | None |
| Result handling and retry | `report_result`, lifecycle, and persistence | Static profile update override |
| Estimates | Coordinator estimate helper | Static policies retain their initial profiles |
| Resource checks | Policy option preparation and feasibility helpers | Baseline order and admission |
| Critical-path rank | `critical_path_ranks` | Static rank selection without aging |
| Protected backfill | Projection and safety helpers | B4 configuration selection |
| Adaptive resource choice | Base choice, GPU allocation, and CPU enrichment helpers | FIFO order without protected backfill |
| HEFT | Common graph, estimates, and feasibility helpers | Mean-cost rank and resource calendar |
| Reservations and traces | Transactional storage methods | External admission transaction |
| MRI execution | `run_pipeline_stage` and the existing executor | Baseline CPU quota and assigned GPU |

The public scheduler API has no baseline policy hook.
`BaselineCoordinator` therefore extends the original coordinator outside its source folder.
It replaces admission and the static profile update hook.
The application wraps it with the original locking facade.
It does not replace methods or module globals at runtime.
B6 continues to use `AdaptiveScheduler.create()` and `load()` directly.

This integration uses internal coordinator and policy helpers.
`neuroflow-source.json` pins all 26 source modules.
The check normalizes line endings.
An unsupported library version blocks baseline execution before MRI processing.
This check does not change the library.

## Resource and measurement rules

Baseline snapshots contain the configured full resource budget.
The coordinator subtracts active reservations once.
It also applies the configured I/O limit.
Existing B6 snapshot behavior remains unchanged.

Baseline containers receive the selected CPU quota and GPU device.
Measured CPU percentage remains distinct from allocated CPU threads.
Error code 137 alone does not prove a memory failure.
Memory failure classification requires explicit log evidence.

An exception without measurements records unknown values.
It does not create a runtime or RAM sample.
A successful baseline stage without measured peak RAM fails validation.
GPU memory measurements remain optional in the existing measurement interface.
No real GPU or MRI processing forms part of the local checks.

## Job records and recovery

Each baseline job writes `neuroflow_policy_contract.json`.
It records the policy, engine, version, budgets, defaults, profile references, and input checksums.
The workspace database also records the external engine identity.
Decision traces identify the actual baseline policy.
Remote code packaging includes the source fingerprint.
Artifact download includes the policy record.

Recovery checks the record and stored scheduler configuration before recovery writes.
It rejects changed inputs, outputs, profiles, limits, defaults, policies, or integration versions.
Old baseline jobs without this record require a new job directory.
Their results and metadata are not relabelled.

The original result transaction saves each application step and its output path in result metadata.
Recovery reads this evidence through a read-only query.
It restores completed steps without creating new observations.
Missing saved evidence or output files blocks recovery.
Uncommitted tasks execute again and must supply real measurements.
Stop requests drain active results and release reservations before closing.

## HEFT scope

B7 is explicitly the online, single-host variant.
It uses only tasks already admitted to the workspace.
It uses mean static computation costs and zero inter-host communication costs.
It inserts tasks into a CPU, RAM, concurrency, disk, I/O, and exclusive GPU calendar.
It chooses the configuration with the earliest predicted finish.
Current reservations retain their conservative release estimates.
An unknown external release time causes waiting.

Frozen batch HEFT is not enabled.
An explicit batch request is rejected.
The UI labels this policy `HEFT (online)`.

## Validation boundary

Local checks use small graphs, real SQLite persistence, and stubbed MRI tool calls.
They cover ordering, resource safety, adaptation, transactions, recovery, shutdown, and UI request transfer.
They do not run simulation campaigns or MRI jobs.
Server deployment and experiment reruns require separate user authorization.

Validation on 24 October 2026:

- 147 selected Python checks passed.
- 12 frontend checks passed.
- TypeScript checking passed.
- Lint checking passed for the new policy modules and their tests.
- All 427 protected files matched the initial checksums after validation.

The selected Python run excluded two Docker integration checks.
It also excluded three existing failures after reproducing them with original application source:

| Existing check | Reproduced failure |
|---|---|
| `test_executor_removes_running_container_when_stop_is_requested` | The expected call omits Windows process flags. |
| `test_remote_runner_write_config_rejects_attached_job_outside_workspace` | The fake SSH client lacks `write_text_file`. |
| `test_remote_python_version_supports_shell_command` | The implementation rejects shell commands as Python executable paths. |

These results do not represent a fully passing repository test suite.
