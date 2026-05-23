# Prism Parity Roadmap (Launcher)

This roadmap focuses on high-impact features that would make GenosLauncher competitive with Prism Launcher for power users.

## Phase 1 - Reliability and Safety (Now)

- Add explicit "remove from launcher" vs "delete files" flows for instances.
- Harden managed-path deletion protections for all destructive actions.
- Improve Java auto-selection to prefer the newest compatible runtime.
- Improve installed-modpack detection across metadata formats.
- Add stronger server input validation and duplicate detection.

## Phase 2 - Instance Management

- Per-instance Java selection override with compatibility hints.
- Full instance settings editor (memory, JVM args, window size, env vars).
- Instance notes, tags, and sortable metadata (last played, playtime, size).
- Built-in duplicate/repair diagnostics with one-click fixes.
- Better import migration from Prism/MultiMC (icons, groups, JVM args, Java settings).

## Phase 3 - Modpack and Mods Workflow

- Update checker for installed modpacks with changelog and safe update flow.
- Side-by-side modpack version channel selection (stable/beta).
- Mod conflict detection and dependency graph viewer.
- CurseForge modpack installation support where policy/format permits.
- Pack lockfile and reproducible export/import flow.

## Phase 4 - Power User Features

- Multiple parallel accounts with per-instance account pinning.
- Launch hooks (pre/post scripts) with permission prompts and logs.
- Per-instance backup schedules + restore points with storage policy controls.
- Better log viewer with filters, error signatures, and "copy launch diagnostics".
- Offline queue: stage installs/downloads and execute when online.

## Phase 5 - UX and Performance

- Virtualized long lists for huge instance/modpack libraries.
- Background metadata refresh jobs with stale-cache indicators.
- Bulk actions across instances (move, group, export, backup, delete).
- Better empty/error states and guided recovery actions.
- Accessibility pass: keyboard traversal, screen reader labels, and contrast checks.
