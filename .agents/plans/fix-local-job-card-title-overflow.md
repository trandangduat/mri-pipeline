# Plan: Fix Local Job Card Title Overflow

## Goal

Make Local Job cards visually match Server Job cards when local job names are long. Prevent the job title from overflowing into the status badge or making the card header look stretched.

## Root Cause

`JobCard` is shared by Local Jobs and Server Jobs. Its title has `min-w-0`, `flex-1`, and `whitespace-nowrap`, but no overflow treatment. Long local job names therefore paint underneath the fixed status badge. Server cards only look correct when their names happen to be shorter.

## Changes

### `tauri-app/src/pages/JobsPage.tsx`

- Add Tailwind truncation to the shared `JobCard` title.
- Keep the existing `title={title}` attribute so the complete job name remains available on hover.
- Do not change the card dimensions, metadata, status badges, or grid behavior.

### `tauri-app/test/JobsPage.test.tsx`

- Update the long-name card test to assert that the title uses truncation rather than asserting the old overflow behavior.
- Keep the assertion that the complete title text is rendered and keep the batch pie-chart assertion.

## Verification

- Run the focused Jobs page test: `npm test -- --run test/JobsPage.test.tsx` from `tauri-app`.
- Run `npm run typecheck` from `tauri-app` if the script exists.

## Acceptance Criteria

- Long Local Job names no longer overlap Running, Failed, Finished, or Stopped badges.
- Local and Server cards retain the same shared layout and sizing.
- The full job name remains in the DOM and available from the native title tooltip.
- Critical Jobs page tests pass.
