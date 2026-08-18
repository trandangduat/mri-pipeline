# Redesign Application UI: Horizontal Tab Navigation & Sidebar Removal

## 1. Goal

Completely redesign the user interface of NeuroFlow by:
- Removing the left vertical sidebar entirely (`AppSidebar`, sidebar toggle button, collapsible sidebar layout).
- Introducing a top-level horizontal navigation and action layout matching the mock UI layout (`mock_ui.png`):
  1. **Top Header Bar**: Brand logo + title ("NeuroFlow MRI Pipeline") on the left, and primary workspace/pipeline actions ("Save Workspace", "Load Workspace", "Start Pipeline", "Stop Pipeline") on the right.
  2. **Horizontal Navigation Tab Bar**: Tabs for "Pipeline Configuration", "Tools Configuration", and "Jobs Monitor" (with dynamic job count badge) with Sea Blue active indicators and icons.
  3. **Full-width Responsive Main Viewport**: Clean layout container without sidebar margin offsets, giving the 2-column pipeline forms and tools/jobs dashboards maximum breathing room.
  4. **Bottom Status Footer Bar**: Fixed/sticky footer displaying copyright info, live system readiness status with green indicator dot ("● System ready" / environment state), version label (`v1.0.0`), and reference documentation links.

---

## 2. Design System Alignment (`DESIGN.md`)

- **Canvas & Surface**: Warm cream floor (`#f7f7f4` / `bg-cursor-canvas`), pure white card surfaces (`#ffffff` / `bg-white`).
- **Hairlines**: 1px dividers and borders (`#e6e5e0` / `border-cursor-hairline`, strong: `#cfcdc4` / `border-cursor-hairline-strong`).
- **Typography**: CursorGothic / Geist Sans (`text-cursor-ink` for titles/emphasis, `text-cursor-body` for running text, `text-cursor-muted` for labels).
- **Brand Voltage**: Sea Blue (`#0077b6` / `bg-cursor-primary`, active: `#005f8f` / `bg-cursor-primary-active`) reserved for primary CTAs and active tab underlines.
- **Danger / Semantic Error**: Semantic red (`#cf2d56` / `bg-cursor-semantic-error` or `bg-[#cf2d56]`) for "Stop Pipeline" button.
- **Success Semantic**: Green indicator (`#1f8a65` / `text-cursor-semantic-success`, `bg-cursor-semantic-success`).
- **Pill / Badge Tokens**: Uppercase badges with rounded pills (`rounded-full bg-cursor-surface-strong px-2 py-0.5 text-xs font-semibold text-cursor-ink`).
- **Depth**: Hairline-only depth, no heavy box shadows.

---

## 3. Files To Change & Create

### 3.1. Create: `tauri-app/src/components/AppHeader.tsx`
Encapsulates the top branding bar, global workspace/pipeline action buttons, and horizontal tab navigation:
- **Brand Header Section (Top Row)**:
  - Left: BrainCircuit icon in Sea Blue rounded square (`bg-cursor-primary text-white rounded-lg p-1.5 h-8 w-8`), bold title "NeuroFlow" (`text-base font-semibold text-cursor-ink`), subtitle "MRI Pipeline" (`text-xs font-normal text-cursor-muted font-mono`).
  - Right:
    - **Save Workspace**: Button with `Save` icon (`variant="ghost"`, opens modal/prompt to save workspace JSON).
    - **Load Workspace**: Button with `FolderOpen` icon (`variant="ghost"`, triggers hidden JSON file input).
    - **Start Pipeline**: Button with `Play` icon (or spinner `Loader2` when starting, Sea Blue `variant="primary"`), with proper disabled states (when starting, when server runtime is not connected, or when required license is missing).
    - **Stop Pipeline**: Danger button with `Square` icon (`variant="danger"` / red background `#cf2d56`).
- **Horizontal Tabs Section (Bottom Row)**:
  - Border bottom divider (`border-b border-cursor-hairline bg-white px-8`).
  - Three navigation tab buttons:
    1. `Pipeline Configuration` (icon: `SlidersHorizontal` or `Workflow`, route: `/pipeline`)
    2. `Tools Configuration` (icon: `Container`, route: `/tools`)
    3. `Jobs Monitor` (icon: `Activity`, route: `/jobs`, badge pill showing `{jobs.length}`)
  - Active tab styling: Sea Blue text (`text-cursor-primary font-semibold`), active bottom border line (`border-b-2 border-cursor-primary -mb-px pb-3.5 pt-3.5`).
  - Inactive tab styling: `text-cursor-body hover:text-cursor-ink font-medium pb-3.5 pt-3.5 transition-colors`.

### 3.2. Create: `tauri-app/src/components/AppFooter.tsx`
Renders the bottom application status bar:
- Height ~40px (`h-10 border-t border-cursor-hairline bg-cursor-canvas px-8 flex items-center justify-between text-xs text-cursor-body`).
- **Left**: `NeuroFlow MRI Pipeline © {new Date().getFullYear()}`.
- **Center**: System readiness status with green status dot:
  - If Python, Docker, and (optional) SSH are ready: `● System ready` (with `text-cursor-semantic-success` green dot).
  - Also display tooltip or secondary text with individual subsystem status (`python: ready · docker: ready · ssh: ready`).
- **Right**:
  - `v1.0.0` version label.
  - `Documentation ↗` link.
  - `GitHub ↗` link.

### 3.3. Modify: `tauri-app/src/router/AppRouter.tsx`
- Remove all sidebar imports, states, and CSS variables (`sidebarOpen`, `sidebarWidth`, `setSidebarOpen`, `setSidebarWidth`, `AppSidebar`, `#sidebarRoot`, `style={{'--active-sidebar-width': ...}}`).
- Replace layout with a clean vertical flex container:
  ```tsx
  <main className="min-h-screen flex flex-col bg-cursor-canvas text-cursor-ink">
    <AppHeader
      activeTab={activeTab}
      onSelectTab={(tab) => navigate('/' + tab)}
      jobsCount={latestJobs.length}
    />
    <div className="flex-1 min-h-0 overflow-y-auto w-full max-w-[1680px] mx-auto px-8 py-6 max-[760px]:px-4">
      <Routes>
        <Route path="/" element={<Navigate to="/pipeline" replace />} />
        <Route path="/pipeline" element={<PipelinePage />} />
        <Route path="/tools" element={<ToolsPage />} />
        <Route path="/jobs" element={<JobsPage />} />
        <Route path="/jobs/:jobId" element={<JobsPage />} />
      </Routes>
    </div>
    <AppFooter envText={envParts.join(' · ')} isEnvReady={isEnvReady} />
  </main>
  ```

### 3.4. Modify: `tauri-app/src/pages/PipelinePage.tsx`
- Remove the redundant inline workspace and start/stop buttons from the top of `PipelinePage` (lines 1700-1796), since they are now seamlessly hosted in `AppHeader`.
- Ensure `PipelinePage` mounts the 2-column `SplitPaneForm` as the top-level view without unnecessary top padding.
- Keep `StartPipelineDialog` accessible or wire it with the pipeline trigger.

### 3.5. Modify: `tauri-app/src/stores/uiStore.ts`
- Clean up unused sidebar states while maintaining backward-compatible interfaces if needed.

### 3.6. Modify/Create Tests: `tauri-app/test/AppHeader.test.tsx`
- Remove or update `tauri-app/test/AppSidebar.test.tsx` to avoid testing removed sidebar components.
- Add unit tests in `tauri-app/test/AppHeader.test.tsx` to verify:
  1. Header renders logo, title, and subtitle.
  2. Tab navigation renders all 3 tabs ("Pipeline Configuration", "Tools Configuration", "Jobs Monitor").
  3. Jobs count badge reflects the total jobs prop correctly.
  4. Active tab highlights correctly with active styles.
  5. Action buttons (Save Workspace, Load Workspace, Start Pipeline, Stop Pipeline) render and respond to user clicks.

---

## 4. Step-by-Step Execution Plan

1. **Implement `AppFooter.tsx`**:
   - Create component with left copyright, center system status indicator with green dot, and right version + doc links.

2. **Implement `AppHeader.tsx`**:
   - Top bar: Branding (BrainCircuit icon + NeuroFlow title + subtitle) + Workspace action buttons + Pipeline start/stop buttons + hidden workspace file input.
   - Tab navigation bar: 3 horizontal tabs with active bottom border indicator, icons, and jobs count badge.
   - Connect handlers for Save/Load Workspace and Start/Stop Pipeline.

3. **Refactor `AppRouter.tsx`**:
   - Wire `AppHeader` and `AppFooter` into `AppLayout`.
   - Remove `AppSidebar` and all sidebar-related state, CSS variables, and layout margin hacks (`ml-[var(--active-sidebar-width)]`).
   - Standardize page wrappers with responsive container width and padding.

4. **Refactor `PipelinePage.tsx`**:
   - Clean up top redundant buttons so `SplitPaneForm` directly renders at the top of the page.

5. **Clean up & Update Unit Tests**:
   - Replace `AppSidebar.test.tsx` with `AppHeader.test.tsx`.
   - Ensure all tests pass with `npm test`.
   - Ensure TypeScript passes cleanly with `npm run typecheck`.

---

## 5. Verification & Testing

1. **TypeScript Type Check**:
   ```bash
   cd tauri-app && npm run typecheck
   ```
2. **Unit Test Suite**:
   ```bash
   cd tauri-app && npm test
   ```
3. **Visual & Interaction Verification**:
   - Verify sidebar is completely gone.
   - Verify top header displays logo, NeuroFlow MRI Pipeline title, and top action buttons.
   - Verify horizontal tab bar switches seamlessly between `/pipeline`, `/tools`, and `/jobs`.
   - Verify Jobs Monitor tab displays badge count of jobs.
   - Verify footer displays copyright, system readiness indicator, version, and documentation links.
   - Verify Start Pipeline, Stop Pipeline, Save Workspace, and Load Workspace trigger accurately.
