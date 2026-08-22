# Unify Warning / Alert Components

## Goal

Replace all ad-hoc warning/error banner markup with one shared `Alert` component backed by a proper orange semantic token. Today every "orange" warning renders unstyled because the code references a `cursor-semantic-warn` utility that maps to no CSS variable — only `--cursor-semantic-error` and `--cursor-semantic-success` exist (`tauri-app/src/styles.css:123-124`, mapped at `styles.css:59-60`).

## User-Visible Requirements

- The stats-vector notice shown when Statistics & Atlas mapping is "Not available" (`PipelinePage.tsx:487-491`) must render as an ORANGE warning banner in both light and dark themes (currently it renders as plain unstyled text).
- Backend-unavailable and file-browser errors render as red error banners, visually consistent with the warning banners (same shape/radius/typography, different hue).
- Runtime warnings stop borrowing agent-timeline colors (currently peach `timeline-thinking`, which DESIGN.md reserves for the agent timeline only).
- Job "stopped/warn" dots render as actual orange dots instead of transparent/unstyled.
- Light and dark themes both show readable orange (amber-family) warnings.

## Investigation Summary

All findings re-verified against current code (line numbers current as of commit `d6d31c2`):

- **Missing token confirmed**: `tauri-app/src/styles.css` defines `--cursor-semantic-error` (#cf2d56) and `--cursor-semantic-success` (#1f8a65) in `:root` (lines 123-124) and dark overrides (#f87171 / #34d399) at lines 181-182. No warn/orange variable exists anywhere in `:root` (102-158), `.dark` (160-215), or the `@theme inline` block (lines ~30-100). `DESIGN.md:333-335` ("### Semantic") lists only Success and Error — no Warning entry.
- **Broken usages of the undefined token** (Tailwind generates nothing for unknown utilities, so these silently render unstyled):
  - `tauri-app/src/components/ui.tsx:50` — `bg-cursor-semantic-warn` in shared `StatusDotLarge`.
  - `tauri-app/src/pages/JobsPage.tsx:81` — same in local `statusDotLargeClasses`.
  - `tauri-app/src/pages/JobsPage.tsx:103` — same in local duplicate `StatusDotLarge`.
  - `tauri-app/src/pages/PipelinePage.tsx:488` — border/bg/text all use `cursor-semantic-warn` (the target stats-vector case).
  - `tauri-app/src/components/RuntimeSection.tsx:225` — icon uses `text-cursor-semantic-warn`.
- **Timeline-token misuse**: `RuntimeSection.tsx:217-230` styles warning rows with `border-cursor-timeline-thinking bg-cursor-timeline-thinking/30` — violates DESIGN.md scoping rule ("Thinking … Used inside in-product agent timeline only", `DESIGN.md:327`).
- **Duplicated `StatusDotLarge`**: `tauri-app/src/components/ui.tsx:33-53` and `tauri-app/src/pages/JobsPage.tsx:86-106` are near-identical; JobsPage additionally exports an unused-by-others `statusDotLargeClasses` (JobsPage.tsx:69-84; grep shows no importer besides the page itself). JobsPage renders it at lines 251 and 894.
- **Banner call sites verified**:
  - `PipelinePage.tsx:212-222` — backend unavailable (error): hand-rolled `border-cursor-semantic-error/30 bg-cursor-semantic-error/5` block.
  - `PipelinePage.tsx:487-491` — stats-vector disabled (warning, target case).
  - `PipelinePage.tsx:1065-1067` — file-browser load error: plain red text row inside the browser panel.
  - `RuntimeSection.tsx:218-230` — list of runtime config warnings (timeline-thinking misuse).
  - `DownloadProgress.tsx:63-68` — download failure row (`border-cursor-semantic-error/20 bg-cursor-semantic-error/5`).
- **Shared-component conventions**: variant class strings live in `tauri-app/src/lib/uiTokens.ts` (e.g. `BUTTON` map, `statusPillClasses`); components live in `tauri-app/src/components/ui.tsx`. No shadcn `alert.tsx` exists (`tauri-app/components/ui/`). Design constraints: hairline-weight borders, no shadows, radius md=8px/lg=12px (`styles.css:93-98`, `--radius: 0.5rem` at line 149).
- **Tests**: vitest, run via `npm run test` in `tauri-app/`; existing UI-class assertions live in `tauri-app/test/uiClasses.test.ts`; component tests exist (e.g. `test/AppHeader.test.tsx`) using @testing-library/react.

## Implementation Plan

### 1. Register the orange token in `tauri-app/src/styles.css`

Add a `--cursor-semantic-warn` variable in all three places, mirroring how `semantic-error` is wired:

- In the `@theme inline` block, directly below `--color-cursor-semantic-success` (line 60):

  ```css
  --color-cursor-semantic-warn: var(--cursor-semantic-warn);
  ```

- In `:root`, directly below `--cursor-semantic-success: #1f8a65;` (line 124):

  ```css
  --cursor-semantic-warn: #b45309;
  ```

- In `.dark`, directly below `--cursor-semantic-success: #34d399;` (line 182):

  ```css
  --cursor-semantic-warn: #f59e0b;
  ```

Value justification (amber family, Tailwind amber-500/700):

- **Light theme `#b45309`** (amber-700): dark enough to pass WCAG AA on the cream canvas `#f7f7f4` / white cards when used as small text (~4.9:1); reads unmistakably as "orange", not red or gold.
- **Dark theme `#f59e0b`** (amber-500): follows the codebase convention that semantic colors get *lighter* in dark mode (error goes `#cf2d56` → `#f87171`, success `#1f8a65` → `#34d399`); keeps ~7:1 contrast against `--cursor-canvas` `#0b0f19`.

Naming note: we deliberately keep the short suffix `-warn` rather than `-warning` so that the five existing broken usages (`bg-cursor-semantic-warn` etc.) become valid utilities immediately once the token exists.

### 2. Document the token in `DESIGN.md`

In the `### Semantic` section (`DESIGN.md:333-335`), add a Warning entry between Success and Error:

```md
- **Warning** (`{colors.semantic-warn}` — #b45309, dark-mode #f59e0b): Cautionary notices and degraded-state indicators. Amber family — distinct from Error red.
```

### 3. Add an `ALERT` style map in `tauri-app/src/lib/uiTokens.ts`

Follows the existing `BUTTON` map pattern:

```ts
export const ALERT = {
  base: 'flex items-start gap-1.5 border leading-[1.4]',
  sm: 'rounded-md px-2 py-1 text-2xs gap-1',
  md: 'rounded-lg px-2.5 py-2 text-xs',
  warning: {
    border: 'border-cursor-semantic-warn/40',
    bg: 'bg-cursor-semantic-warn/10',
    text: 'text-cursor-semantic-warn',
  },
  error: {
    border: 'border-cursor-semantic-error/30',
    bg: 'bg-cursor-semantic-error/10',
    text: 'text-cursor-semantic-error',
  },
} as const;
```

Tinted hairline borders + low-opacity tinted background match the existing banner idiom (`PipelinePage.tsx:213`, `DownloadProgress.tsx:64`); no shadows; radii stay within md/lg.

### 4. Add the `Alert` component in `tauri-app/src/components/ui.tsx`

Props API: `{severity, size?, icon?, children, className?}`.

```tsx
import {AlertTriangle, AlertCircle} from 'lucide-react'; // add to existing lucide import if any
import {ALERT} from '../lib/uiTokens';

export type AlertSeverity = 'warning' | 'error';

export interface AlertProps {
  severity: AlertSeverity;
  size?: 'sm' | 'md';
  icon?: boolean | ReactNode;
  children: ReactNode;
  className?: string;
}

const ALERT_ICONS: Record<AlertSeverity, ReactNode> = {
  warning: <AlertTriangle className="h-3.5 w-3.5 flex-none" />,
  error: <AlertCircle className="h-3.5 w-3.5 flex-none" />,
};

export function Alert({severity, size = 'md', icon = true, children, className = ''}: AlertProps) {
  const v = ALERT[severity];
  return (
    <div role="alert" className={`${ALERT.base} ${ALERT[size]} ${v.border} ${v.bg} ${v.text} ${className}`}>
      {icon === false ? null : (
        <span className={`flex h-3.5 w-3.5 flex-none ${v.text}`}>{icon === true ? ALERT_ICONS[severity] : icon}</span>
      )}
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  );
}
```

Semantics: `icon={true}` (default) → severity default glyph; `icon={false}` → no icon; custom node → rendered as-is. Re-export `ALERT` alongside the existing re-exports at `ui.tsx:4`.

### 5. Fix and dedupe `StatusDotLarge` (broken warn dots)

- In `ui.tsx:49-51`, the warn branch already emits `bg-cursor-semantic-warn` — step 1 makes it work with no code change. Optionally extend the matched states list to also accept `'pending'`-style values only if needed; do not change behavior otherwise.
- Delete `statusDotLargeClasses` and the local `StatusDotLarge` from `JobsPage.tsx:69-106`; replace usages at `JobsPage.tsx:251` and `JobsPage.tsx:894` with the shared component imported from `../components/ui`. Verify nothing else imports them first (`grep -rn "statusDotLargeClasses\|StatusDotLarge" tauri-app/src tauri-app/test`); `test/uiClasses.test.ts` already imports the `ui.tsx` version, so removal should be safe. This also satisfies knip (unused export cleanup).

### 6. Migrate the five banner sites

Each site: before → after.

1. **Backend unavailable (error)** — `PipelinePage.tsx:212-222`:

   ```tsx
   {metaError && !metaLoading && (
     <Alert severity="error">
       <p className="m-0 font-medium">Backend unavailable</p>
       <p className="mt-1 text-cursor-muted">
         {/* unchanged inner copy incl. the two <code> chips */}
       </p>
     </Alert>
   )}
   ```

   (Muted secondary line stays muted; only the container/border/icon colorization is centralized.)

2. **Stats-vector warning (target case)** — `PipelinePage.tsx:487-491`:

   ```tsx
   {showUnavailableWarning && (
     <div className="col-span-2 mt-1">
       <Alert severity="warning" size="sm">
         This stats vector has selected atlases, but Statistics &amp; Atlas mapping is set to Not available.
       </Alert>
     </div>
   )}
   ```

   Now renders with real amber border/tint/text/icon in both themes.

3. **File-browser error** — `PipelinePage.tsx:1065-1067`:

   ```tsx
   {!isLoading && isError && statusMsg && (
     <div className="px-4 py-3">
       <Alert severity="error" size="sm">{statusMsg}</Alert>
     </div>
   )}
   ```

4. **RuntimeSection warnings (stop borrowing timeline colors)** — `RuntimeSection.tsx:217-230`:

   ```tsx
   {warnings.length > 0 && (
     <div className="mt-2.5 grid gap-1.5">
       {warnings.map((warning) => (
         <Alert key={warning} severity="warning" size="sm">{warning}</Alert>
       ))}
     </div>
   )}
   ```

   Removes all `cursor-timeline-thinking` usage from this file (also drops its now-unneeded `text-cursor-semantic-warn` icon span at line 225 — the Alert supplies the triangle).

5. **Download failure** — `DownloadProgress.tsx:63-68`:

   ```tsx
   {state.status === 'failed' && state.error && !expanded && (
     <Alert severity="error" size="sm" className="mt-1.5">{state.error}</Alert>
   )}
   ```

Optional cheap wins (do if trivial, otherwise skip and note in executor summary):

- Other plain `text-cursor-semantic-error` one-liners (e.g. inline field errors) may adopt `<Alert severity="error" size="sm" icon={false}>` where they are standalone rows; do NOT refactor error styling embedded inside labels/selects.

### 7. Update imports

- Files touching `Alert`: add it to the existing import from `../components/ui` in `PipelinePage.tsx`, `RuntimeSection.tsx`, `DownloadProgress.tsx` (DownloadProgress already imports `Button` from there).
- Remove unused lucide icon imports left behind (`AlertTriangle` in `RuntimeSection.tsx`, `AlertCircle` in `DownloadProgress.tsx`) to satisfy lint/knip.

## Tests

Run from `tauri-app/`:

```bash
npm run typecheck
npm run lint
npm run test        # vitest run
```

Automated additions:

- New `tauri-app/test/alert.test.tsx`:
  - Renders `<Alert severity="warning">` and asserts the container matches `/border-cursor-semantic-warn\/40/`, `/bg-cursor-semantic-warn\/10/`, `/text-cursor-semantic-warn/`, `role="alert"`.
  - Renders `<Alert severity="error">` and asserts `semantic-error` classes.
  - Asserts `size="sm"` vs default produce different padding/radius classes (`rounded-md` vs `rounded-lg`).
  - Asserts `icon={false}` hides the icon span; custom `icon={<svg/>}` renders it.
- Extend `tauri-app/test/uiClasses.test.ts`: assert `ALERT.warning` and `ALERT.error` differ and reference their respective tokens; extend the `StatusDotLarge` warn case (if present) to lock in `bg-cursor-semantic-warn`.
- Extend `test/JobsPage.test.tsx` expectations if they asserted on the removed local dot markup.

Manual visual checklist (via `npm run dev`, toggle theme):

- [ ] Stats Extraction set to "Not available" while a stats vector has atlases → orange bordered warning with triangle icon, light AND dark mode.
- [ ] Stop backend → red "Backend unavailable" banner, same shape as the warning banner.
- [ ] File browser pointed at an unreadable path → red inline alert row.
- [ ] Trigger a runtime warning (e.g. invalid SSH host) → amber small alerts; no peach/timeline color visible.
- [ ] Download progress failure → red compact alert under the collapsed bar.
- [ ] Jobs list: a stopped job shows an orange dot; running/completed/failed dots unchanged.
- [ ] No shadows introduced anywhere; radii look consistent with other panels.

## Out of Scope

- Native `alert()` calls at `PipelinePage.tsx:1777` and `PipelinePage.tsx:1793` remain untouched.
- No new shadcn `alert.tsx` primitive; the shared component lives in `src/components/ui.tsx` per repo convention.
- Timeline colors (`cursor-timeline-*`) are not changed anywhere else; only RuntimeSection's misuse is removed.
- Modal titles, toast/dialog systems, and `statusPillClasses` state mapping are unchanged (no 'warn' pill state exists today; adding one is future work if a need appears).
- Backend/Python code untouched.
