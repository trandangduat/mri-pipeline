# Sidebar, Layout, and Window Polish Plan

## Goal

Implement the requested GUI polish without changing app behavior:

- Make the sidebar background match the card background.
- Fix collapsed sidebar icon alignment so icons stay centered inside the 3rem sidebar.
- Balance the main content horizontal spacing around the floating sidebar toggle button.
- Make the active sidebar item visually clearer.
- Launch the Tauri GUI maximized by default.

## Current Code Context

- Main layout lives in `tauri-app/src/router/AppRouter.tsx`.
- App sidebar composition lives in `tauri-app/src/AppSidebar.tsx`.
- Shared sidebar primitives and active/collapsed styles live in `tauri-app/components/ui/sidebar.tsx`.
- Theme tokens live in `tauri-app/src/styles.css`.
- Tauri window config lives in `tauri-app/src-tauri/tauri.conf.json`.
- Design tokens in `DESIGN.md` define card surface as `surface-card` / `#ffffff`, canvas as `#f7f7f4`, primary blue as `#0077b6`, and hairline-only depth.

## Implementation Steps

1. Update sidebar background tokens/classes.
   - In `tauri-app/src/styles.css`, change light sidebar token values from canvas to card surface:
     - `--color-sidebar-background`, `--color-sidebar`, and `--sidebar` should use `#ffffff`.
     - Keep `--sidebar-border` / hairline tokens unchanged.
   - In `tauri-app/src/AppSidebar.tsx`, replace explicit `bg-cursor-canvas` on the `Sidebar` with `bg-cursor-surface-card` or rely on `bg-sidebar` after token update.
   - Keep the app page background as `bg-cursor-canvas` so the white sidebar matches cards and still contrasts against the page floor.

2. Fix collapsed sidebar icon alignment.
   - Inspect the collapsed width relationship between `AppRouter.tsx` (`--active-sidebar-width: 3rem`), `components/ui/sidebar.tsx` (`SIDEBAR_WIDTH_ICON = '3rem'`), and `AppSidebar.tsx` content padding.
   - In `AppSidebar.tsx`, adjust collapsed-only classes on the sidebar content/menu/header so the icon-only layout uses the full 3rem rail cleanly:
     - Remove or reduce horizontal padding in collapsed mode, for example `group-data-[collapsible=icon]:px-0` on `SidebarContent`.
     - Center header logo in collapsed mode with a collapsed-only justify/width class.
     - Ensure `SidebarMenuButton` collapsed state remains `size-8` and centered, not shifted by parent padding.
   - If necessary, refine the shared button class in `components/ui/sidebar.tsx` to include collapsed-only `justify-center` for `SidebarMenuButton`, while preserving expanded label alignment.
   - Confirm the job submenu remains hidden in collapsed mode; do not render cramped job details inside the icon rail.

3. Balance main content spacing around the floating toggle button.
   - In `tauri-app/src/router/AppRouter.tsx`, replace repeated route wrappers using only `pl-16` with symmetric desktop horizontal spacing.
   - Preferred minimal approach: use `px-16 max-[760px]:px-0` for each page wrapper instead of `pl-16 max-[760px]:pl-0`.
   - Keep the outer content section `px-6 py-4` unless visual testing shows double right padding is too large; the key acceptance criterion is that the right side gets the same extra 4rem space currently used on the left for the toggle.
   - Preserve mobile behavior: below `760px`, no left sidebar margin and no extra horizontal route-wrapper padding.

4. Make active sidebar item clearer.
   - Update `SidebarMenuButton` active styling in `tauri-app/components/ui/sidebar.tsx` to be more visible than the current very subtle `bg-sidebar-accent`.
   - Use design-safe treatment based on existing tokens:
     - Active background: `bg-cursor-primary` or a clearly visible blue-tinted style if available.
     - Active text/icon: `text-cursor-on-primary` for blue active background.
     - Keep hover/focus readable.
   - Add or use an active indicator if full blue fill feels too strong, for example a small left border/bar using existing primary color. Prefer the simplest robust class-only treatment first.
   - Update active job submenu item styling in `AppSidebar.tsx` as well, currently `data-active:bg-white`, so selected job rows are also clearly identifiable.
   - Ensure collapsed active icons are clear without labels.

5. Launch maximized by default.
   - In `tauri-app/src-tauri/tauri.conf.json`, add `"maximized": true` to the main window object.
   - Keep existing `width`, `height`, `minWidth`, and `minHeight` as fallback/default constraints.
   - Avoid fullscreen; the request is maximize, not fullscreen.

## Tests and Verification

Run from `tauri-app/`:

1. `npm run typecheck`
2. `npm run test`
3. `npm run build`

Manual visual checks:

1. Start the app with `npm run tauri:dev` if environment allows.
2. Confirm the window opens maximized.
3. Confirm expanded sidebar background matches white cards.
4. Collapse sidebar and confirm all nav icons and the logo are centered inside the rail with no overflow.
5. Switch between Pipeline, Tools, and Jobs and confirm the active sidebar item is obvious in expanded and collapsed states.
6. Confirm main content has matching extra left/right spacing on desktop and still fits on narrow/mobile widths.

## Acceptance Criteria

- Sidebar uses card surface color, not canvas cream.
- Collapsed sidebar icons do not overflow and are horizontally centered.
- Main content has symmetric desktop spacing around the toggle button area.
- Active tab is visually clear at a glance.
- Tauri GUI launches maximized by default.
- Typecheck, tests, and build pass.
