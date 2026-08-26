# Fix Docker image size display

## Goal

Show Docker's actual local disk usage separately from the stored content size. Do not present the same `docker image inspect .Size` value under two ambiguous icons.

## Root cause

`app_backend/tools.py` currently reads `docker image inspect --format {{.Size}}` and assigns that one value to both `repo_size` and `uncompressed_size`. With Docker 29's containerd image store, inspect `.Size` is the content size while `docker image ls` reports total disk usage, including compressed content and unpacked snapshots. This causes the app to show about 13.3 GB while Docker reports about 41.3 GB.

## Implementation

1. In `app_backend/tools.py`, replace the ambiguous `ImageInfo.size_bytes` model with explicit content-size and disk-usage values.
2. In `_default_image_info_provider`, keep reading inspect `.Size` as numeric content size and obtain Docker's disk usage from `docker image ls --format {{.Size}} <exact image reference>`. Handle command failure or empty output by returning no disk usage instead of failing image status.
3. Return explicit API fields `disk_usage` and `content_size` for installed local images. Return both as `None` for missing and server images. Remove `repo_size` and `uncompressed_size`; there is no external compatibility requirement in this internal backend/frontend contract.
4. In `tauri-app/src/api/schemas.ts`, update `toolImageSchema` to the new field names.
5. In `tauri-app/src/components/ImageCard.tsx`, show visible text labels rather than unexplained duplicate icons:
   - `Disk <value>` using the hard-drive icon and a title explaining this is Docker's total local disk usage.
   - `Content <value>` using the package icon and a title explaining this is stored image content and may be lower than disk usage.
   Keep the existing compact card layout and design tokens. Missing cards should only render these fields if available.
6. Update only directly affected backend tests in `tests/test_app_backend_tools.py`. Add a focused assertion/test that the provider invokes Docker image listing for disk usage and keeps content size distinct. If direct provider testing would require broad refactoring, inject an `ImageInfo` with distinct values and verify the response contract instead.
7. Add a focused frontend component test only if the existing test setup supports a small render assertion without introducing new infrastructure. Verify the two labels and values are distinguishable.

## Verification

- Run `pytest tests/test_app_backend_tools.py`.
- Run the smallest relevant frontend test command for any changed/added frontend test.
- Run frontend type checking or build if there is no focused component test.
- Inspect the final diff and ensure unrelated files are untouched, apart from this plan file.

## Constraints

- Do not change pull, remove, remote connection, tool grouping, or unrelated card styling behavior.
- Do not attempt registry size lookup for missing images in this change.
- Do not add compatibility aliases for the old ambiguous API names.
