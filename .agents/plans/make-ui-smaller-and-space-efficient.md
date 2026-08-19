# Plan: Make UI Generally Smaller and More Space-Efficient

## 1. Goal

Make the entire NeuroFlow application interface generally smaller, tighter, and significantly more space-efficient by:
- Reducing global and component padding and margins across all pages, panels, cards, and modal dialogs.
- Decreasing text font sizes across headings, labels, body copy, and metadata displays.
- Downscaling button heights and padding from large desktop touch sizes (~40–44px) to compact desktop workstation sizes (~28–32px).
- Downscaling form input and select control heights from `h-11` (44px) to `h-8` (32px) with proportional font sizes (`text-xs` / 12–13px).
- Reducing top navigation header height (`h-16` → `h-12`) and footer bar height (`h-10` → `h-7.5`).
- Tightening grid gaps in the 2-column pipeline form, tools image cards, and jobs subject cards.

---

## 2. Design System Alignment (`DESIGN.md`)

- **Canvas & Surface**: Maintain warm cream page floor (`#f7f7f4` / `bg-cursor-canvas`) and pure white card surfaces (`#ffffff` / `bg-white`).
- **Hairlines**: Hairline-only depth (`#e6e5e0` / `border-cursor-hairline`, `#efeee8` / `border-cursor-hairline-soft`, `#cfcdc4` / `border-cursor-hairline-strong`).
- **Typography Scale**:
  - Main titles / Section titles: `text-sm font-semibold` / `text-[15px]` (reduced from `text-lg` / `text-[18px]`).
  - Body & Labels: `text-xs` (12px) / `text-[13px]` (reduced from `text-sm` / `text-base` / 14–16px).
  - Secondary / Captions / Badges: `text-[10px]` / `text-[11px]` (reduced from `12px` / `13px`).
  - Code & Paths: JetBrains Mono `text-[11px]` / `text-xs`.
- **Button Tokens**:
  - Primary CTA, Ghost, Danger buttons: `h-8` (32px), `px-3 text-xs font-medium rounded-md` (reduced from `h-10` / `h-11` with `px-4 text-sm`).
  - Small / Icon buttons: `h-6.5` / `h-7` with `px-2 text-[11px]` (reduced from `h-8` / `h-9`).
- **Form Controls**:
  - Input & Select: `h-8` (32px), `px-2.5 text-xs rounded-md` (reduced from `h-11` / 44px with `px-4 text-base`).
  - Labels: `grid gap-1 text-xs font-normal text-cursor-body` (reduced from `gap-3 text-[13px]`).
- **Card & Panel Rounding & Padding**:
  - Panels & Cards: `p-3.5` or `p-4` with `rounded-lg` (reduced from `p-6` / `p-5` with `rounded-xl`).

---

## 3. Files To Modify

### 3.1. Design Tokens & UI Primitives
- **`tauri-app/src/lib/uiTokens.ts`**:
  - `BUTTON.base`: update to `inline-flex h-8 cursor-pointer items-center justify-center gap-1.5 rounded-md border px-3 text-xs font-medium leading-none transition-colors [&_svg]:block`.
  - `inputCls`: update to `h-8 w-full rounded-md border border-cursor-hairline bg-white px-2.5 text-xs font-normal text-cursor-ink outline-none focus:border-cursor-hairline-strong`.
  - `labelCls`: update to `grid gap-1 text-xs font-normal leading-[1.3] text-cursor-body`.
  - `pillBase`: update to `inline-flex w-fit items-center rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.08em]`.
- **`tauri-app/src/components/ui.tsx`**:
  - `Panel`: reduce outer padding to `p-4` (from `p-6`), header margin to `mb-3` (from `mb-5`), title to `text-[15px] font-semibold` (from `text-[18px]`), icon size to `h-4 w-4` (from `h-5 w-5`).
  - `EmptyBox`: reduce padding to `p-3` and font size to `text-xs`.
- **`tauri-app/components/ui/button.tsx`**:
  - Adjust `buttonVariants`: base font size `text-xs` (from `text-sm`), default height `h-8 gap-1.5 px-2.5 text-xs`, `sm` height `h-6.5 gap-1 px-2 text-[11px]`, `xs` height `h-5.5 gap-1 px-1.5 text-[10px]`.
- **`tauri-app/components/ui/card.tsx`**:
  - `Card`: `p-3.5 rounded-lg` (from `p-5 rounded-xl`).
  - `CardHeader`: `pb-2.5 gap-1` (from `pb-4 gap-1.5`).
  - `CardTitle`: `text-sm font-semibold` (from `text-lg font-medium`).
  - `CardDescription`: `text-[11px]` (from `text-xs`).
  - `CardFooter`: `pt-2.5` (from `pt-4`).
- **`tauri-app/components/ui/input.tsx`**:
  - Base input height `h-8 px-2.5 py-1 text-xs rounded-md` (from `text-sm`).
- **`tauri-app/components/ui/badge.tsx`**:
  - Padding `px-2 py-0.25 text-[10px]` (from `px-2.5 py-0.5 text-[10px]`).

### 3.2. Global Navigation & Layout Shell
- **`tauri-app/src/components/AppHeader.tsx`**:
  - Top header container: height `h-12` (48px, down from `h-16` / 64px), padding `px-4` (down from `px-6`).
  - Brand identity: logo container `h-7 w-7 rounded-md` (down from `h-9 w-9`), icon `h-4 w-4` (down from `h-5 w-5`), title `text-sm font-semibold` (down from `text-base`), subtitle `text-[10px]` (down from `text-[11px]`).
  - Action buttons: compact button group with `gap-1.5`.
  - Navigation tab bar: height `py-2` (down from `py-3`), tab font `text-xs font-medium` (down from `text-sm`), tab spacing `gap-6` (down from `gap-8`), padding `px-4` (down from `px-6`).
- **`tauri-app/src/components/AppFooter.tsx`**:
  - Footer height: `h-7.5` (30px, down from `h-10`), padding `px-4`, font `text-[11px]` (down from `text-xs`).

### 3.3. Pipeline Configuration Page
- **`tauri-app/src/pages/PipelinePage.tsx`**:
  - Page scroll wrapper padding: `pl-4 pt-3 pb-3 pr-2` (left pane) and `pl-2 pt-3 pb-3 pr-4` (right pane), content gap `gap-3.5` (down from `gap-6`).
  - `PipelineStepsSection`:
    - Header preset selector row: `mb-2.5 gap-2` (down from `mb-4 gap-3`).
    - Stage table rows: `px-3 py-1.5` (down from `px-4 py-2.5`), `min-h-8` (down from `min-h-11`), stage label `text-xs` (down from `text-[13.5px]`).
    - License upload row: `mt-2.5 gap-2`.
  - `StatsAtlasSection`:
    - Stat group rows: padding `py-2.5` (down from `py-4.5`), title `text-xs font-semibold` (down from `text-[14px]`).
    - Add Atlas button: `h-7 px-2.5 text-[11px]`.
    - Atlas chip pills: `py-0.5 pl-2.5 pr-1.5 text-xs` (down from `py-1.5 pl-3.5 pr-2 text-sm`), remove icon `h-3.5 w-3.5` in `h-4 w-4` button.
    - Atlas Picker modal: overlay padding `p-4`, search bar `h-8 text-xs px-2.5`, atlas list items `px-3 py-2 text-xs`, done button `h-7.5 px-4 text-xs`.
  - `AdvancedSettingsSection`:
    - Spacing `gap-2.5` (down from `gap-4`), checkbox title `text-xs font-medium` (down from `text-base`).
  - `InputOutputSection`:
    - Section grid gap `gap-3.5` (down from `gap-6`).
    - RadioGroup items: padding `px-2.5 py-1.5` (down from `px-3.5 py-2.5`), title `text-xs` (down from `text-[13px]`), hint `text-[11px]` (down from `text-[12px]`).
    - Path fields: Browse buttons `h-8 px-2.5 text-xs` (down from `h-11 px-3`).
    - ServerBrowserModal & BatchConfigModal: padding `px-4 py-2.5`, table header `py-1.5 text-[10px]`, item rows `px-4 py-1.5 text-xs`.
- **`tauri-app/src/components/RuntimeSection.tsx`**:
  - Hardware fields grid: `gap-2.5` (down from `gap-3.5`).
  - Warnings alert box: `px-2.5 py-1.5 text-[11px]` (down from `px-3 py-2 text-xs`).
  - SSH Server box: padding `p-3` (down from `p-4`), header `mb-2 pb-2`, field grid `gap-2`, action row `mt-2.5 gap-2`.

### 3.4. Tools Configuration Page
- **`tauri-app/src/pages/ToolsPage.tsx`**:
  - Page wrapper padding: `p-4` (down from `p-6`), section gap `gap-4.5` (down from `gap-7`).
  - Section headers: `mb-2` (down from `mb-3.5`), title `text-sm font-semibold` (down from `text-base`).
  - Environment summary cards: padding `p-3` (down from `p-4`), icon `h-8 w-8` (down from `h-10 w-10`), label `text-[10px]` (down from `text-[11px]`), value `text-xs` (down from `text-sm`).
  - Image cards grid: column min-width `minmax(18rem, 1fr)` (down from `minmax(22rem, 1fr)`), grid gap `gap-3` (down from `gap-4.5`).
- **`tauri-app/src/components/ImageCard.tsx`**:
  - Card container: `p-3 min-h-[160px] rounded-lg` (down from `p-4.5 min-h-[220px] rounded-xl`).
  - Header: `mb-1.5 gap-2`, icon container `h-7 w-7 rounded-md` (down from `h-9 w-9`), repo text `text-xs font-semibold` (down from `text-sm`), tag `text-[10px]` (down from `text-[11px]`).
  - Meta row: `mb-1.5 gap-x-2 gap-y-0.5 text-[11px]` (down from `mb-2.5 gap-x-3 text-xs`).
  - Tool chips: `mb-2 gap-1`, chips `px-1.5 py-0.5 text-[10px]` (down from `px-2 py-0.5 text-[11px]`).
  - Footer button: `pt-2`, button height `h-7.5 text-xs` (down from full-size button).
- **`tauri-app/src/components/DownloadProgress.tsx`**:
  - Padding `p-2.5` (down from `p-3`), text `text-[11px]`.

### 3.5. Jobs Monitor Page & Dialogs
- **`tauri-app/src/pages/JobsPage.tsx`**:
  - Page wrapper padding: `p-3.5` (down from `p-6`), layout gap `gap-2.5` (down from `gap-4`).
  - Back button bar: button `h-7.5 px-2.5 text-xs` (down from `h-9 px-3.5`).
  - Job List View: section gap `gap-4`, job card `p-3 rounded-lg` (down from `p-4 rounded-xl`), title `text-xs` (down from `text-sm`).
  - Top Job Detail Card: padding `p-3.5` (down from `p-5`), header `pb-2.5`, icon `h-7 w-7` (down from `h-10 w-10`), title/select `text-base` (down from `text-xl`), metadata table `text-xs` with `py-1 px-2.5` cells and `8rem` label column (down from `text-[14px]`, `py-2 px-3`, `10rem`).
  - Top Batch Summary Card: padding `p-3.5` (down from `p-5`), stacked bar `h-4.5` (down from `h-6`), legend `gap-1.5 text-[11px] mb-2.5` (down from `gap-2 text-xs mb-4`), action buttons `h-8 text-xs` (down from `h-11 text-sm`).
  - Bottom Batch Subjects Card: header `px-4 py-2` (down from `px-5 py-3`), search toolbar `mb-2.5 gap-2`, search input `h-7.5 text-xs px-2.5` (down from `h-10 text-sm`), filter buttons `px-2 py-0.5 text-[10px]` (down from `px-2.5 py-1 text-[12px]`).
  - Subject Grid items: `p-2.5 rounded-lg` (down from `p-4 rounded-xl`), icon `h-7 w-7` (down from `h-9 w-9`), subject ID `text-xs font-semibold` (down from `text-[14px]`), details footer `mt-1.5 pt-1.5 text-[11px]` (down from `mt-3 pt-3 text-[13px]`).
  - Subject List items: `px-2.5 py-1.5 text-xs` (down from `px-4 py-3 text-sm`).
  - Subject Detail Modal: overlay padding `p-3`, header `px-4 py-3` with `text-base font-semibold` title (down from `px-6 py-5` with `text-[22px]`), body grid `p-3 gap-3.5`, timeline rows `p-2 text-xs`, sparklines `h-22` (down from `h-28`), log pre `min-h-[14rem] text-[11px]` (down from `min-h-[18rem] text-[12px]`).
- **`tauri-app/src/components/StartPipelineDialog.tsx`**:
  - Modal container `p-4 max-w-[24rem]` (down from `p-6 max-w-[28rem]`), title `text-sm font-semibold` (down from `text-[16px]`), step text `text-xs` (down from `text-[13px]`), close button `px-3 py-1.5 text-xs`.
- **`tauri-app/src/components/DownloadOutputsDialog.tsx`**:
  - Modal container `p-4 max-w-[28rem]` (down from `p-6 max-w-[32rem]`), title `text-sm font-semibold`, input fields `h-8 text-xs` (down from `h-10 text-[13px]`), buttons `px-3 py-1.5 text-xs`.

---

## 4. Step-by-Step Execution Plan

1. **Update Shared Design Tokens (`uiTokens.ts`, `ui.tsx`, and component primitives)**:
   - Refactor `BUTTON.base`, `inputCls`, `labelCls`, `pillBase`.
   - Update `Panel`, `EmptyBox` in `src/components/ui.tsx`.
   - Update `components/ui/button.tsx`, `components/ui/card.tsx`, `components/ui/input.tsx`, `components/ui/badge.tsx`.

2. **Update App Header & Footer (`AppHeader.tsx`, `AppFooter.tsx`)**:
   - Reduce top header height to `h-12`, logo to `h-7 w-7`, tabs padding to `py-2` with `text-xs` font.
   - Reduce footer height to `h-7.5` with `text-[11px]` font.

3. **Update Pipeline Page & Runtime Sections (`PipelinePage.tsx`, `RuntimeSection.tsx`)**:
   - Compact pane container padding and gaps.
   - Compact `PipelineStepsSection` stage table rows and font size.
   - Compact `StatsAtlasSection` rows, chips, and Atlas Picker modal.
   - Compact `InputOutputSection` radio groups, path fields, and directory browser modals.
   - Compact `RuntimeSection` hardware grid and SSH configuration card.

4. **Update Tools Page & Components (`ToolsPage.tsx`, `ImageCard.tsx`, `DownloadProgress.tsx`)**:
   - Compact environment overview cards.
   - Compact `InstalledImageCard` and `MissingImageCard` heights, chips, padding, and buttons.
   - Adjust image card grid min-width from `22rem` to `18rem`.

5. **Update Jobs Page & Modal Dialogs (`JobsPage.tsx`, `StartPipelineDialog.tsx`, `DownloadOutputsDialog.tsx`)**:
   - Compact Job Details metadata table, Batch Summary progress bar, and action buttons.
   - Compact Batch Subjects search toolbar, grid cards, and list rows.
   - Compact Subject Detail modal timeline, telemetry sparklines, and operator console log.
   - Compact Start Pipeline stream dialog and Download Outputs dialog.

6. **Verification & Testing**:
   - Run `npm run typecheck` in `tauri-app/`.
   - Run `npm test` in `tauri-app/` to ensure all 11 test suites pass with zero regressions.
   - Run `npm run build` in `tauri-app/` to verify bundling succeeds.

---

## 5. Acceptance Criteria

- All buttons across the application are compact (`h-7.5` / `h-8` with `text-xs` or `text-[11px]`).
- Form inputs and dropdown selects are space-efficient (`h-8` with `text-xs`).
- Text typography scale is refined downwards throughout headers, body text, tables, chips, and metadata.
- Page, card, panel, and modal paddings are reduced by 25–40% to eliminate wasted whitespace.
- Application layout feels dense, readable, and space-efficient on both standard and high-density screens.
- All TypeScript checks and unit tests pass cleanly.
