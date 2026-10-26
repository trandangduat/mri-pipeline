# Local and SSH runtime audit

Date: 2026-10-27

Reviewed application commit: `aa68ab6`.

## Result

Local execution has confirmed startup and monitoring faults.
These faults can affect machines with enough CPU and RAM.
The shared worker passed the checks described below.
This review does not certify real Docker execution or MRI output quality.

No Docker installation, image download, SSH connection, or real MRI processing occurred.
No application execution code changed during this review.

## Shared processing path

Both launchers run `pipeline.job_worker`.
The worker selects the standard runner or the NeuroFLOW scheduler.
Both paths use the same stage definitions, container command builder, and Docker executor.
They also share progress events, stop markers, result reports, and per-subject status logic.

SSH testing therefore supports confidence in the shared processing code.
It does not verify the local launcher, Windows bundle, or Docker Desktop resource limits.

| Area | Local | SSH |
| --- | --- | --- |
| Worker | `pipeline.job_worker` | Same worker on the server |
| Stage execution | Shared Docker executor | Same executor on the server |
| Scheduler package | Source fallback only; missing from inspected bundles | Source upload and dependency checks |
| RAM preflight | No profile peak check | Compares allocated RAM with profile peak |
| Image preflight | License probe checks its selected image only | Checks selected tool images before worker launch |
| Launcher output | Discarded | Saved in `launcher.log` |
| Worker failure detection | Status files only | Exit file and process existence |
| Resource budget | Host hardware | Server hardware |

## Finding 1: scheduler absent from current Windows bundles [P1]

The inspected build and installed bundle contain zero `neuroflow` modules.
Neither bundle contains the source fallback directory.
The build warning file also reports missing `neuroflow` and `neuroflow.configuration` imports.

Enabling the scheduler therefore fails when these bundles reach scheduler execution.
The application's readiness check does not detect this missing dependency.

The source checkout can work when `NeuroFLOW-private/src` is available.
Our scheduler simulation used the existing private source checkout explicitly.
That successful simulation does not clear the packaged application fault.

Source references:

- `packaging/windows/neuroflow-backend.spec:17`: only the application root enters the analysis search path.
- `packaging/windows/neuroflow-backend.spec:19`: resources omit the scheduler source fallback.
- `requirements.txt:1`: dependencies omit the scheduler package.
- `app_backend/capabilities.py:9`: readiness checks do not include the scheduler.
- `pipeline/neuroflow_adapter.py:130`: runtime fallback depends on an external source directory.
- `remote/remote_runner.py:568`: SSH checks and prepares scheduler dependencies.

Recommendation: include the scheduler in the bundle and verify its imports before accepting scheduler jobs.
Add a clean bundled-runtime check that does not require Docker.

## Finding 2: an exited local worker can remain running forever [P1]

The local launcher reports success immediately after process creation.
The monitor only reads status and exit-code files.
It does not check whether the worker process still exists.

A worker can fail during imports, get killed, or exit before writing those files.
The job then remains running.
A stop request only writes a marker that the absent worker cannot read.
The job can remain blocked from deletion through the normal interface.

The simulated dead worker remained running before and after a stop request.
No real process was created for this reproduction.

The launcher also discards standard output and error output.
An early import failure therefore leaves no useful launcher log.
SSH saves that output and checks whether the worker process remains alive.

Source references:

- `app_backend/jobs.py:55`: process creation precedes successful startup reporting.
- `app_backend/jobs.py:229`: status refresh lacks a process-existence check.
- `app_backend/jobs.py:296`: worker output and errors are discarded.
- `remote/remote_runner.py:956`: SSH creates a launcher log.
- `remote/remote_runner.py:1025`: SSH checks worker process existence.

Recommendation: record launcher output and verify worker readiness.
Check worker process identity during status refresh and record unexpected exits as failures.

## Finding 3: local preflight omits RAM and complete image checks [P2]

Local preflight validates paths and tools, checks the license, and starts the worker.
It does not compare allocated RAM with the selected profile's required RAM.
It also lacks a complete selected-image check.

The FreeSurfer license probe checks one licensed tool image.
This does not cover tools that need no license or additional images in custom pipelines.

A simulated FreeSurfer request received 163 MiB against a 16,507 MiB profile peak.
Local preflight still reported successful startup after a simulated license pass.

A CAT12 request also passed preflight without any Docker image check.
That reproduction used the real license checker because CAT12 needs no license.
Only the worker process was simulated.

Missing images eventually fail inside the processing runner.
Insufficient scheduler resources can leave tasks waiting instead of reporting an early configuration failure.
SSH performs resource and image checks before launching its worker.

Source references:

- `app_backend/jobs.py:124`: local preflight flow.
- `app_backend/remote.py:585`: SSH RAM preflight.
- `app_backend/remote.py:656`: SSH image preflight.
- `pipeline/docker_ops.py:57`: license probe checks one selected tool image.
- `pipeline/docker_ops.py:313`: stage execution detects missing images later.

Recommendation: add local Docker readiness, selected-image, and profile resource checks before worker launch.
Reuse the resource requirement logic already used by SSH.

## Finding 4: resource budgets ignore Docker Desktop capacity [P2]

The scheduler calculates RAM from the physical host.
The standard runner uses the same physical RAM basis for container memory limits.
CPU validation also uses host core counts.
The code does not inspect the Docker engine's available RAM and CPUs.

Docker Desktop and WSL can have separate memory and CPU limits.
A capable Windows machine can therefore expose fewer resources to Docker than the application assumes.

For example, the simulated 64 GiB host produced a 32 GiB scheduler budget at 50 percent.
That calculation does not account for a smaller Docker allocation.
This can cause excessive scheduling, memory failures, or CPU oversubscription.

The shared runner also uses host RAM on servers.
The difference matters when the Docker engine and the Python process have different resource limits.

Source references:

- `pipeline/hardware.py:59`: physical host memory detection.
- `pipeline/neuroflow_adapter.py:173`: scheduler RAM budget.
- `pipeline/runner.py:99`: container RAM limit.
- `app_backend/run_request.py`: local CPU validation uses host hardware.

Docker documents the separate limits here:
https://docs.docker.com/desktop/settings-and-maintenance/settings/#advanced

Recommendation: query the selected Docker engine and use its effective CPU and RAM capacity.
Use the same capacity for preflight checks, scheduling, and container limits.

## Finding 5: startup can overwrite a completed worker's status [P2]

The parent starts the worker before writing the initial running status.
A fast worker can finish and write its final status first.
The parent then replaces that final status with running.

The reproduction simulated a failure with exit code 42 and an error message.
The parent replaced its status file with running and removed the error message.
The exit-code file allowed the job list to recover the failed state.
The detailed error remained lost.

Source reference: `app_backend/jobs.py:55` through the initial status write.

Recommendation: write initial state before spawning the worker.
Let the worker own its subsequent status transitions.

## Verification

Existing focused backend checks: **57 passed, 1 skipped**.
The skipped check required Windows directory symlink support.
No UI tests ran, as required by AGENTS.md.

Checked modules:

- Local job creation, status, stop markers, and registry writes.
- Shared worker status and progress callbacks.
- Docker command construction and stop handling with simulated subprocesses.
- Packaged and source resource path selection.
- Profile RAM calculations.
- Stage-to-stage input and output handoff with simulated executors.

A real NeuroFLOW scheduler also completed a simulated FreeSurfer 8 volume job.
The worker ran reorientation, segmentation, and statistics stages.
It wrote completed status and a one-subject success summary.
The simulation blocked all external process launches.

## Evidence

Machine-readable evidence:
`outputs/local-runtime-audit-e21b8c45271a4793acd43d9918c78066/evidence.json`.

The evidence contains simulated jobs and synthetic stage files.
It contains no processed MRI results.

## Remaining real-runtime checks

A capable test machine still needs to verify these items:

- Docker Desktop access to actual input, license, atlas, and output mounts.
- Linux container mode and selected tool image compatibility.
- GPU access through Docker when GPU execution is enabled.
- Real memory use, process cancellation, and tool output correctness.

The review found no additional fault in the simulated shared stage sequence or successful worker completion.
The confirmed local faults above still require fixes.
