# Synthetic surface-atlases content pack tooling (fixtures / internal test only).
# Do NOT use this to publish proprietary atlas binaries without redistribution rights.

## Pack ID

`surface-atlases`

## Manifest / index fields

- `pack_id`, `version`, `product_version`
- `os`, `arch`
- `url` (https for remote install)
- `archive_sha256`
- `licences`
- `unpacked_size`
- `resource_root_mapping` (must include `atlas-assets`)

The detached Ed25519 signature covers canonical index JSON
(`sort_keys=True`, separators `(',', ':')`). The zip archive contains
`manifest.json` with per-file `path` / `size` / `sha256`, plus the file
payloads. Never include the two orphan Yale annotations
(`Yale_Brain_Atlas_*_fsaverage.annot` without `_new`).

## Verification key

The app pins `CONTENT_PACK_ED25519_PUBLIC_KEY_B64` in
`pipeline/content_packs.py`. The matching private key is offline-only.

## Redistribution

**Redistribution rights and notices are still required before shipping real
Destrieux / Yale / Kong / Schaefer binaries in a published surface-atlases
pack.** Tests use synthetic fixtures under `tests/content_pack_fixtures.py`
only.
