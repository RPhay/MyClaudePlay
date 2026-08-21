# Feature Documentation Structure

This standard defines how to organize and maintain documentation for each feature in the project.

## Directory Structure

Each feature gets its own folder under `./docs/features/` using kebab-case naming:

```
./docs/features/
├── entity-rendering/
│   ├── feature.md
│   ├── context.md
│   ├── decisions.md
│   ├── plan-phases.md
│   ├── plan-current.md
│   ├── requirements.md
│   ├── resources-feature.md
│   ├── resources-shared.md
│   ├── bugs/
│   │   ├── 001-rendering-crash.md
│   │   ├── 002-tree-scroll-lag.md
│   │   └── archive/
│   │       └── (closed bugs)
│   └── enhancements/
│       ├── 001-bulk-edit.md
│       ├── 002-keyboard-shortcuts.md
│       └── archive/
│           └── (completed enhancements)
├── auth-system/
│   └── (same structure)
└── ...
```

## File Purposes

### feature.md

**Purpose:** High-level summary of the feature. What is it? Why does it exist?

**Scope:** 1-2 pages max. Should be readable in 2 minutes.

**Update:** Rarely. Only if feature scope changes fundamentally.

**Template:**
```markdown
# Feature Name

## Status
- **Current Status**: [planning|in-progress|complete|blocked]
- **Created**: [date]
- **Owner**: [optional]

## Overview
[1-2 paragraph summary of what this feature does]

## Rationale
[Why does this feature exist? What problem does it solve?]

## Scope
[What's included. What's explicitly excluded.]

## Key Definitions
[Any domain-specific terms relevant to this feature]

## Documentation Guide

Use this to know what to read based on what you're doing:

### Quick Status Check (2-3 min)
→ feature.md (this file) + plan-current.md

### Working on Current Phase (5-10 min)
→ plan-current.md + context.md + resources-feature.md

### Deep Dive / Implementation (15+ min)
→ context.md + resources-feature.md + resources-shared.md + requirements.md

### Investigating a Bug (5-15 min)
→ bugs/[specific-bug].md + context.md

### Planning an Enhancement (10-20 min)
→ enhancements/[specific-enhancement].md + requirements.md + plan-phases.md

### Understanding Architecture
→ decisions.md + context.md
```

---

### context.md

**Purpose:** Everything you need to know to work on this feature in the current session. Zero prior context assumed.

**Scope:** Terse and focused. Omit anything you could discover in one file read.

**Update:** As you learn. Add gotchas, conventions, file references as you discover them.

**Contents:**

- **Directory purposes** — What each relevant folder does, in one line each
- **Entry points** — Where to start reading (file paths, line numbers if relevant)
- **Module boundaries** — What code belongs to this feature, what's external
- **Conventions** — Non-obvious patterns or naming schemes specific to this feature
- **Gotchas** — Pitfalls, surprises, things that break easily
- **Relevant files** — Files that matter for current work and why (one-liners)
- **Dependencies** — Other features or systems this depends on

**Links, don't duplicate** — Reference `resources-feature.md` and `resources-integration.md` rather than listing files again.

**Template:**
```markdown
# Context: Entity Rendering

## Directory Purposes
- `src/services/entityService.js` — CRUD operations for any entity type
- `src/public/js/genericEntity.js` — Unified rendering engine (tree, rows, editor)
- `src/routes/api/entities.js` — Polymorphic API endpoints

## Entry Points
- Start: `src/public/js/genericEntity.js#renderTree()` — Tree rendering logic
- Then: `src/database/systemEntityTypes.js` — Type definitions and fields

## Module Boundaries
- **Belongs to this feature**: Anything dealing with entity rendering, trees, rows
- **Does NOT**: Authentication, deployment, user preferences
- **Shared with**: Auth (session checks), UI (CSS classes, click handling)

## Conventions
- Entity types are defined once in `systemEntityTypes.js`, never hardcoded elsewhere
- Folders are entities with `is_folder = 1`, never a separate type
- All API routes return `{ success: bool, data: ?, message?: string }`

## Gotchas
- **Trap 1**: mysql2 auto-parses JSON columns. Don't call `JSON.parse()` unconditionally or it throws on already-parsed objects.
- **Trap 2**: `renderTree()` emits all descendants at once. Watch memory with large trees.

## Relevant Files & Why
- `genericEntity.js` — Core renderer. Any visual change goes here.
- `systemEntityTypes.js` — Type definitions. Adding a field type requires changes here.
- `main.css` — Entity styling. All `.entity-*` classes live here.

## Dependencies
- [[uix|UIX Standards]] — Reference for tree/row/editor architecture
- [[tech-stack|Tech Stack]] — Node.js/Express version requirements
```

---

### decisions.md

**Purpose:** Record why architectural decisions were made. Rationale, trade-offs, alternatives considered.

**Scope:** One decision per section.

**Update:** When you make a significant decision about this feature.

**Template:**
```markdown
# Decisions: Entity Rendering

## Decision: Generic Renderer for All Types

**Date**: [date]  
**Status**: Accepted

**Problem**
We had 8+ type-specific renderers (TaskRow, GoalRow, etc.), leading to code duplication and inconsistent behavior.

**Decision**
Build one `genericEntity.js` renderer that handles all types via field schema from `entity_types` table.

**Rationale**
- Single code path for all types
- New types work without code changes
- Bugs fixed once, everywhere

**Trade-offs**
- More complex schema system (initial setup cost)
- Runtime field resolution (tiny perf hit)

**Alternatives Considered**
- Keep type-specific renderers (rejected: maintenance nightmare)
- Use a framework like React (rejected: overkill, team expertise)

**Outcome**
Successful. All entity types now use the generic renderer.
```

---

### plan-phases.md

**Purpose:** High-level implementation roadmap from start to completion.

**Scope:** Phases, not tasks. Each phase should be 1-2 weeks of work.

**Update:** Rarely. Only if overall strategy changes.

**Template:**
```markdown
# Implementation Phases: Entity Rendering

## Phase 1: Schema & Data Layer
- Define entity_types and entity_type_fields tables
- Create systemEntityTypes.js as single source of truth
- Seed system types into database

**Estimated**: 3-5 days

## Phase 2: Generic Row Renderer
- Build genericEntity.js#renderRow() to handle any type
- Implement field renderer strategy map
- Replace first type-specific renderer (Projects)

**Estimated**: 5-7 days

## Phase 3: Tree & Hierarchy
- Implement renderTree() for hierarchical types
- Handle folder logic (is_folder flag)
- CSS expand/collapse

**Estimated**: 3-5 days

## Phase 4: Generic Editor
- Build EntityEditor that renders form from schema
- Unified change tracking
- Save/revert logic

**Estimated**: 5-7 days

## Phase 5: Remaining Types
- Migrate all other entity types to use generic renderer
- Remove legacy type-specific code
- Test and bug fixes

**Estimated**: 7-10 days

## Phase 6: Polish & Testing
- Performance optimization
- E2E tests for all types
- User testing

**Estimated**: 5-7 days
```

---

### plan-current.md

**Purpose:** Current work for a specific phase. Updated frequently as work progresses.

**Scope:** Single phase from plan-phases.md. Contains plan, implementation details, status, what's left, bugs.

**Update:** Daily or per work session. This is your active notebook.

**Template:**
```markdown
# Current Work: Phase 4 - Generic Editor

**Phase**: Phase 4 (Generic Editor)  
**Status**: In Progress  
**Last Updated**: 2026-08-20

## Phase Plan
See plan-phases.md for overall roadmap.

This phase builds a unified EntityEditor that generates forms from entity schema instead of hardcoded forms per type.

## Implementation Details

### What's Been Done
- ✅ EntityEditor module skeleton created (`src/public/js/entityEditor.js`)
- ✅ Form generation from schema (buildForm method)
- ✅ Change tracking factory integrated

### Currently Working On
- 🔄 Field value population (fillForm method)
- 🔄 Save/revert button behavior

### What's Left
- [ ] Test with all field types (text, date, select, etc.)
- [ ] Persist changes to database
- [ ] Handle error responses from API
- [ ] Keyboard shortcuts (Cmd+S to save)
- [ ] Close on save (vs. stay open for new items)

## Bugs & Issues

**Bug #1**: Checkbox fields not rendering in form
- File: `genericEntity.js#fieldRenderers.checkbox`
- Issue: Missing CSS class, doesn't appear visually
- Status: Investigating

**Bug #2**: Date picker not initialized
- File: `entityEditor.js#applyFieldValue`
- Issue: Date picker library not being called for date fields
- Status: Needs research (which date lib do we use?)

## Blockers
None currently.

## Questions
- Should save close the editor for edits? (Yes, per uix.md) For new items? (No, stay open)
- Which date picker library are we using? (Check tech-stack.md)

## Next Steps
1. Fix checkbox rendering
2. Research date picker
3. Test all field types
4. Begin database integration
```

---

### requirements.md

**Purpose:** Complete requirements document for the feature.

**Scope:** Functional requirements, constraints, acceptance criteria. Not implementation details.

**Update:** Early in feature development. Reference when you need to confirm scope.

**Template:**
```markdown
# Requirements: Entity Rendering

## Functional Requirements

### FR1: Render Trees
- All hierarchical entity types render as trees
- Expand/collapse supported via CSS
- Folders (is_folder=1) display with folder icon and no child count

### FR2: Render Rows in List View
- Non-hierarchical types render as lists
- One row per entity
- Fields defined in entity_type_fields table display in configured order

### FR3: Unified Editor
- Single editor form works for all entity types
- Form fields generated from type's schema
- Save/revert/close buttons behave consistently

## Non-Functional Requirements

### Performance
- Tree rendering: sub-100ms for <1000 nodes
- Row rendering: sub-50ms per page load

### Compatibility
- Works in Chrome, Firefox, Safari (latest versions)
- Works on desktop and tablet (responsive design)

### Maintainability
- No type-specific renderers or editors in codebase
- All types use generic engine

## Constraints

- No breaking changes to existing API
- Database schema changes require migration script
- All entity types must migrate by end of Phase 5

## Acceptance Criteria

- [ ] All 8 entity types render correctly (visually identical to before)
- [ ] Tree expand/collapse works for hierarchical types
- [ ] Editor saves and loads all field types
- [ ] No console errors
- [ ] Performance benchmarks met
- [ ] E2E tests pass for all types
```

---

### resources-feature.md

**Purpose:** All files and folders directly associated with this feature.

**Scope:** Only files that exist because of this feature. Not shared infrastructure.

**Update:** When feature adds/removes files.

**Template:**
```markdown
# Feature Resources: Entity Rendering

## Source Code
- `src/services/entityService.js` — CRUD service
- `src/services/entityTypeService.js` — Type registry and schema
- `src/routes/api/entities.js` — API endpoints
- `src/public/js/genericEntity.js` — Renderer (tree, rows, editor)
- `src/public/css/entity-rendering.css` — Styling

## Database
- `src/database/systemEntityTypes.js` — Type definitions
- Schema tables: `entity_types`, `entity_type_fields`, `entity_relationships`

## Tests
- `tests/unit/genericEntity.test.js`
- `tests/e2e/entity-rendering.spec.js`

## Configuration
- None (types come from database)

## Documentation
- See this feature folder
```

---

### resources-shared.md

**Purpose:** Files and folders shared with other features but used by this one.

**Scope:** Only files in other features' domains that this feature depends on.

**Update:** When discovering new dependencies.

**Template:**
```markdown
# Resources: Shared - Entity Rendering

## Authentication & Sessions
- `src/middleware/sessionAuth.js` — Session checks before allowing edits
- Used by: Entity save endpoint

## CSS & Styling
- `src/public/css/main.css` — Base styles, button/input standards
- Used by: Form styling, button appearance

## UI Components (Shared)
- `src/public/js/app.js#app.fetch()` — CSRF-protected fetch wrapper
- `src/public/js/app.js#app.notify()` — Toast notifications
- `src/public/js/changeTracker.js` — Change tracking factory (shared)
- Used by: All API calls, form state tracking

## Error Handling
- `src/utils/errorHandler.js` — Consistent error responses
- Used by: API error responses

## Utilities
- `src/utils/validators.js` — Input validation
- Used by: Form field validation before save

## Database Connection
- `src/database/connection.js` — Connection pool
- Used by: All queries
```

---

### bugs/

**Purpose:** Track bugs discovered during or after feature development.

**Structure:**
```
bugs/
├── 001-rendering-crash.md
├── 002-tree-scroll-lag.md
└── archive/
    ├── 001-rendering-crash.md (closed)
```

**File Template:**
```markdown
# Bug: [Title]

**Status**: [open|in-progress|closed]
**Severity**: [low|medium|high|critical]
**Reported**: [date]
**Fixed**: [date, if closed]

## Description
[What is the bug? How to reproduce?]

## Impact
[What breaks? Who is affected?]

## Root Cause
[Why does it happen? Where in code?]

## Solution
[How was/will it be fixed?]

## Notes
[Additional context, workarounds, etc.]
```

**Archive:** When a bug is closed, move it to `bugs/archive/` with status changed to "closed".

---

### enhancements/

**Purpose:** Track feature enhancements and new requests discovered post-launch.

**Structure:**
```
enhancements/
├── 001-bulk-edit.md
├── 002-keyboard-shortcuts.md
└── archive/
    ├── 001-bulk-edit.md (completed)
```

**File Template:**
```markdown
# Enhancement: [Title]

**Status**: [proposed|approved|in-progress|completed]
**Requested**: [date]
**Completed**: [date, if done]
**Priority**: [low|medium|high]

## Description
[What is the enhancement? Why is it needed?]

## Use Case
[Who wants this? What problem does it solve?]

## Implementation Notes
[How would this work? What needs to change?]

## Effort Estimate
[How much work? Rough T-shirt size: S/M/L/XL]

## Dependencies
[Other features or work this depends on?]

## Notes
[Additional context, considerations, related discussions]
```

**Archive:** When an enhancement is completed, move it to `enhancements/archive/` with status changed to "completed".

---

## Workflow

**Starting a feature:**
1. Create feature folder with all 8 scaffold files + `bugs/` and `enhancements/` folders
2. Create `bugs/archive/` and `enhancements/archive/` folders (empty initially)
3. Fill in `feature.md` and `requirements.md` first
4. Reference `plan-phases.md` for phases
5. As you work, update `context.md`, `decisions.md`, `plan-current.md`

**Switching to a feature:**
1. Read `feature.md` (1-2 min) — understand what it is
2. Read `plan-current.md` (2-3 min) — see current status
3. If you need context, read `context.md` (3-5 min)
4. Read linked resources as needed

**Asking for status:**
- `feature.md` status field gives overall progress
- `plan-current.md` gives active work details
- No need to read everything unless digging deeper
