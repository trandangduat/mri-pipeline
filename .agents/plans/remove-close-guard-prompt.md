# Implementation Plan: Remove Close Guard Prompt on App Exit

## 1. Overview & Objective

The user requested to completely remove the exit confirmation dialog ("Cancel running job? A pipeline job is currently running...") when closing the application.

Currently, `useCloseGuard` in `tauri-app/src/hooks/useCloseGuard.ts` attaches an `onCloseRequested` listener to the Tauri window. We will remove this hook and its usage from `tauri-app/src/App.tsx`.

---

## 2. Changes

### File Changes

1. **[MODIFY] `tauri-app/src/App.tsx`**:
   - Remove `import {useCloseGuard} from './hooks/useCloseGuard';`
   - Remove `useCloseGuard(true);` call inside `App()`.

2. **[DELETE] `tauri-app/src/hooks/useCloseGuard.ts`**:
   - Delete `tauri-app/src/hooks/useCloseGuard.ts`.

---

## 3. Verification Plan

1. **Type Check & Lint**:
   - Run `npm run typecheck` inside `tauri-app` to ensure no dangling references or type errors exist.
2. **Unit Tests**:
   - Run `npm test` inside `tauri-app` to ensure all existing frontend tests pass.
3. **Manual Check**:
   - Verify that closing the window no longer triggers any confirmation modal and closes directly as handled by standard Tauri window lifecycle.
