# Add download sizes for missing Docker images

## Goal

Show the compressed download size before users pull every missing Docker image represented by `TOOL_DEFS`, while preserving the distinct local `Disk` and `Content` values for installed images.

## Behavior

- Missing local image cards show `Download ~13.3 GB` when registry metadata is available.
- The value is the sum of compressed image layer sizes for the Docker daemon's platform, obtained from the remote manifest without pulling the image.
- Do not label this value as disk usage or installed size.
- Registry/network/unsupported-manifest failures must not fail the overall Tools response. Return no value and let the card show `Download size unavailable`.
- Installed cards keep their existing `Disk` and `Content` display unchanged.
- Server-target missing cards should also receive registry download size where feasible because the manifest is public and queried without pulling. If the remote platform is not currently available in the image-state response, use the Docker host platform selection supported by the manifest command and document this as an estimate; do not broaden remote execution logic.

## Implementation

1. Add a focused helper in `pipeline/docker_ops.py` (or the smallest suitable Docker metadata module) that runs `docker manifest inspect --verbose <image>` with a bounded timeout and parses JSON.
2. Handle both response shapes:
   - A single verbose manifest object.
   - A list of platform manifests for a multi-platform index.
3. Select a real runnable image manifest, excluding attestation entries such as `os/architecture = unknown`. Prefer `linux/amd64` because the current project images and runtime target that platform; if the manifest is single-platform, use it directly. Keep selection logic small and explicit.
4. Sum numeric `size` values from the selected `OCIManifest.layers`. Ignore malformed entries. Return `None` on command errors, invalid JSON, no suitable manifest, or no valid layers.
5. Add an injectable `download_size_provider` to `LocalToolService` so tests do not access the network. For each missing image, call it and expose formatted `download_size` in the response. Since image references are already grouped uniquely by `_image_tools`, each image should be queried at most once per status request.
6. Avoid making image-status failure depend on registry availability. Catch provider failures per image and set `download_size` to `None`.
7. Expose `download_size` in `tauri-app/src/api/schemas.ts`.
8. Update `MissingImageCard` in `tauri-app/src/components/ImageCard.tsx`:
   - Render `Download ~<value>` with the existing download icon when present.
   - Add a title explaining that it is compressed registry data and actual transfer can be lower when layers are already cached.
   - Render a muted `Download size unavailable` when absent, so every missing card communicates size status rather than showing nothing.
   - Do not render `Disk` or `Content` metadata for missing cards.
9. Keep `InstalledImageCard` behavior unchanged except for any shared type fixture updates required by the new optional field.

## Tests

- In `tests/test_docker_ops.py`, add focused tests for:
  - Summing layer sizes from a single manifest.
  - Selecting the runnable amd64 image from a multi-platform list and excluding attestation manifests.
  - Invalid JSON or failed command returning `None`.
- In `tests/test_app_backend_tools.py`, inject distinct download sizes and verify missing images expose formatted `download_size`, while installed image fields remain unchanged.
- Update `tauri-app/test/ImageCard.test.tsx` to verify a missing card renders `Download ~...` and the unavailable fallback.

## Verification

- Run `pytest tests/test_docker_ops.py tests/test_app_backend_tools.py`.
- Run `npm test -- --run test/ImageCard.test.tsx` in `tauri-app`.
- Run `npm run typecheck` in `tauri-app`.
- Search for `download_size` consumers and inspect the final diff to ensure no pull/remove/remote-job behavior or unrelated UI is changed.

## Constraints

- No image pull, blob download, or registry credential storage is allowed for size lookup.
- Do not hardcode sizes in `TOOL_DEFS`; tags can change.
- Do not estimate local installed disk usage from compressed download size.
- Keep all failures non-fatal and time bounded.

## Performance correction

The first implementation was measured against all 10 unique `TOOL_DEFS` images and took about 158 seconds because `docker manifest inspect` ran sequentially. Correct this before completion:

1. For unqualified Docker Hub references used by this project, query the public Docker Hub tag endpoint with Python standard-library HTTP and a short timeout: `https://hub.docker.com/v2/repositories/<namespace>/<repository>/tags/<tag>`.
2. Select the `images` entry for `linux/amd64`, exclude `unknown` attestations, and read its numeric `size`. The endpoint's FS8 value was verified as `14297922800`, equivalent to `13.3 GB` with the app formatter.
3. Parse repository and tag safely, including explicit tags. Do not treat a registry port as a tag. The project references are standard `namespace/repository:tag` Docker Hub references; keep parsing scoped and tested.
4. Retain manifest inspection only as a bounded fallback where useful, or remove it if it adds no value for the current supported image set. A failed lookup remains non-fatal.
5. Query all missing unique images concurrently with a small bounded worker pool, not serially. Add a service-level TTL cache for successful lookups so repeated Tools refreshes do not repeatedly hit Docker Hub. Do not permanently cache failures.
6. Keep total worst-case page delay bounded to a practical duration. Reduce individual network/fallback timeout as needed; a missing size is preferable to blocking the Tools page.
7. Add critical tests for Docker Hub response parsing, bounded concurrent batch behavior at the service level, and cache reuse. Avoid tests that access the real network.
8. Re-run the real all-image timing probe after implementation and report its duration and which images remain unavailable.
