# Native scheduler benchmark exports

NeuroFLOW Scheduler jobs now write their own benchmark reports and runtime image receipts.
The worker also verifies the deployed source against the upload manifest before processing.
These changes are implemented in commits `79bcb1f` and `b4b561f`.
The scheduler algorithm remains unchanged.

## Job files

| File | Contents |
|---|---|
| `benchmark_steps.tsv` | 58 columns, including every committed attempt, selected configuration, measured resources, and sample counts. |
| `benchmark_summary.tsv` | 37 columns with job, scan, and stage/tool summaries. |
| `container_images.txt` | Requested images, immutable image IDs, repository digests, container names, and receipt status. |
| `container_images/*.json` | Per-container runtime image receipts. |
| `source_revision.json` | Actual deployed source hashes, declared Git revision, and source-validation results. |

The adapter exports benchmark reports after committed results.
The worker exports them again after writing the final job status, so final wall time and status are available.
Reports retain failed attempts and retries. Missing benchmark values remain `NA`.
The Standard Runner benchmark headers also match the fields its writer produces.

Docker execution resolves the selected image before launch and uses its immutable local image ID.
Receipts retain the requested tag and available repository digests alongside the execution status.

Source verification rejects missing, changed, and unexpected runtime source files.
Two removed GPU setup helpers may remain in reused deployment directories.
The worker records those known legacy files separately and preserves diagnostics before reporting a source mismatch.
Runtime hashes describe original bytes; line-ending differences can change a raw hash without changing source content.

## RAM telemetry checks

`tests/test_ram_sampler_evidence.py` contains 18 focused cases:

- Six cases exercise the real sampler thread and parser with mocked Docker replies: missing RAM, an empty reply, command failure, timeout, one measured byte, and 2 measured MiB.
- Twelve cases carry missing or measured RAM through CPU results into the real B0, B1, B6, and B7 scheduler paths and both observation exports.

Missing RAM remains unavailable, produces an explicit validation failure, and creates no accepted profile observation.
Genuine measurements retain their values and use ceiling conversion to MiB.
Docker process calls are mocked; these tests do not start containers or MRI processing.
They require the existing scheduler source checkout and test dependencies, like the other adapter tests.

Run from the repository root:

```text
python -m pytest tests/test_ram_sampler_evidence.py -q
```

`tests/test_native_benchmark_exports.py` covers native report contents, image receipts, and source verification.
The earlier reporting selection passed 164 tests; the final source-verification selection passed 19 tests.
Those selections overlap and do not represent separate counts of unique tests.
The 18 RAM cases also passed against application revision `b4b561f` before being copied into the tracked test directory.

The handover ZIPs, original experiment reports, and server snapshots remain separate delivery artifacts.
