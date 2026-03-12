# AutoFlow UX Enhancement Prompt

I have a workflow automation dashboard called **AutoFlow** built with vanilla HTML, CSS, and JS (no framework). It has 3 files: `index.html`, `index.css`, and `app.js`. This is a **desktop-only internal tool** — do not add any mobile/responsive/touch optimizations. I need you to implement the following UX enhancements across every section. Preserve the existing dark glassmorphism aesthetic, accent gradient (#7c5cfc → #c084fc), and Inter font. Do NOT change the API contract or endpoints — only improve the frontend UX.

---

## 1. LOADING & SKELETON STATES — Critical (Currently Missing)

There are zero loading indicators anywhere. When the app boots or data is being fetched, the user sees "0" in stat cards and empty lists with no feedback.

- Add **skeleton loader placeholders** (pulsing gray rounded rectangles) for: stat cards, workflow list, and logs list. Show them on initial load and during any refetch.
- Add a **small spinner** inside buttons that trigger async actions: "Save Workflow", "Run now" (play icon button), "Clear All" logs. Disable the button while loading to prevent double-clicks.
- The "New Workflow" button should NOT show a spinner (it's instant navigation, not async).
- After the API call resolves, fade the skeleton out and fade the real content in.

---

## 2. WORKFLOW LIST — Search, Filter, Sort

Currently there's no way to find a workflow if the list grows. Add:

- A **search bar** above the workflow list (below the stats grid). Styled consistently with `.form-input`. It should filter workflows in real-time (client-side) by name or description. Include a clear "✕" button inside the input when text is present.
- A **filter row** next to search with small pill/toggle buttons to filter by: All, Active, Inactive, and by trigger type (Manual, Cron, Interval, Login). The active filter pill should use the accent gradient background.
- A **sort dropdown** (use the existing `.custom-select` pattern) with options: Name A→Z, Name Z→A, Newest first, Oldest first.

---

## 3. DELETE CONFIRMATION — Replace Browser `confirm()`

The current `confirm()` for deleting workflows and clearing logs is jarring and breaks the UI's premium feel.

- Create a **custom confirmation modal** using the existing `.modal` styling pattern already in the CSS.
- It should show: a warning icon, the workflow name being deleted, "Cancel" (ghost button) and "Delete" (red/danger styled button).
- Add a brief fade+scale animation on open/close (the CSS already has `.modal` animations — reuse them).
- For "Clear All Logs", use the same modal but with appropriate copy: "This will permanently delete all execution logs."

---

## 4. EDITOR — Form Validation & UX Improvements

### 4a. Inline Validation
- Mark required fields with a subtle red asterisk (*) next to the label.
- Show inline error messages below inputs (red text, 0.733rem) when the user tries to save with: empty workflow name, invalid cron expression (basic regex check), missing required step params.
- Add a red border (`border-color: var(--error)`) to invalid inputs.
- Currently only the name is validated with a toast — replace that with inline validation.

### 4b. Unsaved Changes Warning
- Track whether the form is "dirty" (any field changed from initial state).
- If the user clicks "Cancel" or a nav item while the form is dirty, show a confirmation modal: "You have unsaved changes. Discard?" with "Keep Editing" and "Discard" buttons.

### 4c. Step Reordering
- Add **drag handles** (a grip/drag icon ⠿) to the left of each step's number circle.
- Implement drag-and-drop reordering of steps using native HTML5 drag & drop (no library needed). Update the step numbers after reorder.
- As a fallback, also add small "Move Up" / "Move Down" arrow buttons next to the remove button.

### 4d. Duplicate Step
- Add a "Duplicate" icon button (copy icon) next to each step's remove button. Clicking it inserts a clone of that step immediately below.

### 4e. Cron Expression Helper
- When "Cron Schedule" trigger is selected and the cron input is focused, show a small **helper tooltip/popover** below the input with common examples:
  - `0 9 * * *` → Every day at 9 AM
  - `0 9 * * 1-5` → Weekdays at 9 AM
  - `*/30 * * * *` → Every 30 minutes
  - `0 0 * * 0` → Every Sunday midnight
- Make each example clickable — clicking one fills the cron input.

### 4f. Trigger Config Transition
- The trigger config field currently pops in/out with `display:none`. Replace with a smooth **slide-down/collapse animation** (max-height transition or similar).

---

## 5. LOGS SECTION — Filtering, Search & Pagination

### 5a. Log Filters
- Add **status filter pills** at the top: All, Success (green), Failed (red), Running (amber). Clicking one filters the log list. Show a count badge on each pill.
- Add a **date range filter** — a simple dropdown: "Today", "Last 7 days", "Last 30 days", "All time".

### 5b. Log Search
- Add a search input that filters logs by workflow name.

### 5c. Pagination
- If there are more than 50 logs, show a "Load More" button at the bottom (styled as `btn-ghost`) instead of rendering all at once.

### 5d. Auto-Refresh Indicator
- The logs auto-refresh every 15 seconds. Show a subtle indicator — a thin progress bar at the top of the logs section that fills over 15 seconds, or a small text like "Auto-refreshing in 12s" near the Refresh button.

### 5e. Log Detail Improvement
- When a log card is expanded, animate the detail section open (max-height transition instead of instant `display:block`).
- Add a "Re-run" button inside the expanded log detail that re-triggers the same workflow.

---

## 6. SETTINGS SECTION — Completeness

The settings section feels empty and unfinished.

- **Google Calendar card**: Replace "See README for setup" with a "Connect Google Calendar" button (even if it just shows a toast saying "Configure in server settings" for now). Show connection status with a green/red dot.
- **Autostart card**: Replace the plain button with a styled **CSS-only toggle switch**. The label should dynamically switch between "Enabled" / "Disabled" based on current state.
- **Add new settings cards**:
  - **Notifications**: A toggle for "Show desktop notifications on workflow completion/failure".
  - **Theme**: "Dark" (current) / "System" preference toggle (placeholder — can be non-functional but UI should exist).
  - **Data Management**: "Export all workflows as JSON" button and "Import workflows from JSON" file upload button.
  - **Danger Zone**: A card at the bottom with a red-tinted border containing "Delete all workflows" with appropriate confirmation.

---

## 7. ACCESSIBILITY — A11y Pass

### 7a. ARIA Attributes
- All `.custom-select` elements: add `role="listbox"` on dropdown, `role="option"` on each option, `aria-expanded` on trigger, `aria-selected` on selected option, `aria-haspopup="listbox"`.
- All `.btn-icon` elements: add descriptive `aria-label` ("Run workflow", "Toggle workflow", "Delete workflow").
- `.log-card`: add `role="button"` and `tabindex="0"`, handle Enter/Space keypress for expand/collapse.
- Toast container: add `role="alert"` and `aria-live="polite"` so screen readers announce toasts.

### 7b. Focus Management
- When a modal opens, trap focus inside it (Tab should cycle through modal elements only). On close, return focus to the element that triggered the modal.
- When switching sections, move focus to the new section's heading (`#page-title`).
- Add a visible **focus ring** (outline using the accent color) for all interactive elements. Currently some elements have `outline: none` with no replacement focus indicator — that's an accessibility failure, fix it.

### 7c. Color Contrast
- `--text-muted: #4a4a58` on `--bg-primary: #08080c` fails WCAG AA. Bump `--text-muted` to at least `#6a6a78` or similar to hit 4.5:1 contrast ratio.
- `--text-secondary: #7c7c8a` — verify it passes AA against card backgrounds. If not, lighten slightly.

---

## 8. MICRO-INTERACTIONS & POLISH

### 8a. Section Transitions
- When switching sections, add a subtle **crossfade**. The current `fade-slide-in` animation is fine for incoming, but the outgoing section disappears instantly — add a brief fade-out (150ms opacity transition).

### 8b. Stat Card Number Animation
- When stat numbers update (e.g., from 0 to 5), animate the number counting up (a simple requestAnimationFrame counter over 400ms).

### 8c. Empty State Enhancement
- The workflow empty state could be more engaging. Add a slightly larger or animated SVG illustration.
- Add a **"Start from Template"** secondary button in the empty state that opens a small modal with 3-4 pre-built workflow templates (Morning Routine, Dev Setup, Backup Script, System Health Check). Clicking one pre-fills the editor with that template's steps.

### 8d. Workflow Card Active Indicator
- The small green dot for active workflows is subtle. Additionally add a **3px left border** with `var(--success)` color on active workflow cards for stronger visual signal.

### 8e. Toast Improvements
- Add a thin **progress bar** at the bottom of each toast that shrinks over the 4-second display duration.
- Allow clicking a toast to dismiss it immediately.
- Stack toasts with slight vertical offset when multiple appear simultaneously.

---

## 9. KEYBOARD SHORTCUTS

Add global keyboard shortcuts (only fire when focus is NOT inside an input/textarea):

- `N` — New workflow
- `1` / `2` / `3` / `4` — Switch to Workflows / Editor / Logs / Settings
- `Escape` — Close any open modal or dropdown (partially done already)
- `?` — Show keyboard shortcuts help modal
- `/` — Focus the search input (when on Workflows or Logs section)

Add a small `?` icon button in the sidebar footer (near the server status) that opens the shortcuts modal.

---

## 10. PERFORMANCE & RESILIENCE

- **Debounce search inputs** — filter after 250ms of no typing, not on every keystroke.
- **Throttle health check on disconnect** — if the server is disconnected, increase polling interval to 60s instead of 30s to avoid flooding. Reset to 30s on reconnect.
- **Optimistic UI for toggle** — when toggling a workflow's enabled state, immediately update the card UI (flip the dot color) and revert only if the API call fails. Don't wait for full `loadWorkflows()` re-render.
- **GPU-optimize ambient blobs** — add `will-change: transform` to `.blob` elements and use `transform: translate3d()` to ensure the background animation runs on the compositor thread without causing layout jank.
- **Batch DOM updates** — in `renderWorkflows()` and `renderLogs()`, build the full HTML string before assigning to `.innerHTML` once (this is already done, just ensure no regressions).

---

## Summary of Expected Changes Per File

- **index.html**: ARIA attributes, keyboard shortcut modal markup, search/filter bar markup, custom confirmation modal structure, template picker modal, toast `aria-live`, shortcuts help button in sidebar footer.
- **index.css**: Skeleton pulse keyframe animation, focus ring styles, contrast variable fixes, toggle switch component, toast progress bar, search/filter pill styles, log expand animation (max-height), section crossfade, stat counter transition, cron helper popover styles, drag handle styles, danger zone card border.
- **app.js**: Skeleton rendering + fade logic, search/filter/sort state management with debounce, custom confirm modal open/close/callback logic, drag-and-drop step reordering, form dirty tracking + unsaved changes guard, cron helper popover toggle, log pagination + "Load More", auto-refresh countdown timer, number count-up animation (requestAnimationFrame), keyboard shortcut listener, focus trap utility for modals, optimistic toggle update, adaptive health check throttle, workflow templates data + pre-fill logic.

**Keep all 3 files separate (HTML, CSS, JS). Do not introduce any framework, bundler, or library. Do not change API routes or request/response shapes.**