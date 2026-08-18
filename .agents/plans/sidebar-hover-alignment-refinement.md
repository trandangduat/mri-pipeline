# Sidebar Hover and Alignment Refinement Plan

## Goal

Refine the sidebar after the first polish pass:

- Collapsed sidebar nav items below the logo must be horizontally centered in the rail.
- Hovering an active sidebar item must not turn it white or visually override the active state.
- Normal hover needs a stronger shade so it is easier to see.
- Sidebar top-level items need more vertical spacing.
- Selected job rows should use a less bold active background than full primary blue.

## Current Findings

- `tauri-app/src/AppSidebar.tsx` sets `SidebarContent` collapsed padding to `px-0`, but top-level `SidebarMenuButton` instances do not get `mx-auto` in collapsed mode. Because the button becomes `size-8` but remains left-positioned, icon-only buttons can look off-center.
- `tauri-app/components/ui/sidebar.tsx` has generic `hover:bg-sidebar-accent` and active `data-active:bg-sidebar-primary` in the shared button classes. The `default` variant also adds hover classes, so active hover can visually regress to the normal hover/white-ish style.
- `SidebarMenu` uses `gap-0`, making top-level items too close.
- Job row active class in `AppSidebar.tsx` currently uses `data-active:bg-cursor-primary`, which is too strong for a nested/secondary selected row.
- `--sidebar-accent` is currently `#fafaf7`, which is too subtle against the white sidebar.

## Implementation Steps

1. Center collapsed top-level sidebar buttons.
   - In `tauri-app/components/ui/sidebar.tsx`, update `sidebarMenuButtonVariants` base classes so collapsed icon buttons center themselves inside the rail:
     - Add `group-data-[collapsible=icon]:mx-auto` near the existing `group-data-[collapsible=icon]:size-8!` classes.
     - Keep `group-data-[collapsible=icon]:justify-center` and `group-data-[collapsible=icon]:p-2!`.
   - Do not add manual margins to individual menu buttons unless the shared primitive is insufficient.
   - Confirm the logo/header remains centered separately; the reported issue is the nav items below it.

2. Make normal hover visibly shaded.
   - Prefer token-level change in `tauri-app/src/styles.css`:
     - Change light `--color-sidebar-accent` and `--sidebar-accent` from `#fafaf7` to a stronger but still design-safe hairline shade, such as `#efeee8`.
   - Keep text color as `#26251e`.
   - This makes all normal sidebar hover states more visible without adding one-off hover classes everywhere.

3. Preserve active styling on hover.
   - In `tauri-app/components/ui/sidebar.tsx`, add explicit active-hover classes after generic hover behavior in `sidebarMenuButtonVariants`:
     - Use `data-active:hover:bg-sidebar-primary` to keep the active fill stable, or `data-active:hover:bg-cursor-primary-active` if using cursor token classes is accepted in this shared component.
     - Use `data-active:hover:text-sidebar-primary-foreground` so text/icon stays readable.
   - If class ordering still lets the default variant override active hover, remove duplicate hover classes from the `default` variant or replace the variant with non-conflicting classes. Keep the minimal change that fixes ordering.
   - Verify active top-level items stay blue or slightly darker blue when hovered, never white/off-white.

4. Increase spacing between top-level sidebar items.
   - In `tauri-app/components/ui/sidebar.tsx`, change `SidebarMenu` default gap from `gap-0` to `gap-2`.
   - If this affects nested menus unexpectedly, only apply `gap-2` from `AppSidebar.tsx` to the top-level `SidebarMenu` via `className="gap-2"` and leave the primitive default alone.
   - Preferred minimal/safer implementation: add `className="gap-2"` to the top-level `SidebarMenu` in `AppSidebar.tsx`.

5. Soften selected job row active background.
   - In `tauri-app/src/AppSidebar.tsx`, replace the nested job row active classes on `SidebarMenuSubButton`:
     - Remove `data-active:bg-cursor-primary` and `data-active:text-cursor-on-primary`.
     - Use a lighter active treatment, for example `data-active:bg-cursor-hairline-soft data-active:border-cursor-primary data-active:text-cursor-ink`.
     - Keep a clear selected marker via border and/or a subtle left accent if needed.
   - Ensure inner job title/subtitle colors do not fight the selected state. Since title/subtitle currently set explicit `text-cursor-ink` and `text-cursor-muted`, the lighter active row should remain readable.
   - Keep the top-level Jobs Monitor active item strong; only soften individual selected job rows.

## Verification

Run from `tauri-app/`:

1. `npm run typecheck`
2. `npm run test`
3. `npm run build`

Manual visual checks:

1. Collapse the sidebar and confirm Pipeline, Tools, and Jobs icons are all centered under the logo.
2. Hover inactive top-level sidebar items and confirm the shade is easy to see.
3. Hover the active top-level item and confirm it stays active-colored, not white/off-white.
4. Confirm top-level items have more breathing room than before.
5. In Jobs, select a job and confirm the nested selected row is visible but less bold than the top-level active blue.

## Acceptance Criteria

- Collapsed nav buttons are centered in the 3rem sidebar rail.
- Active top-level item remains active-colored on hover.
- Inactive hover state is visibly shaded.
- Top-level sidebar items are less cramped.
- Selected job item uses a subtle active style, not full primary-blue fill.
- Typecheck, tests, and build pass.
