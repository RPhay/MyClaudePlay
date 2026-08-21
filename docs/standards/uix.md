# UI Standards: Generic Entity Engine & Dynamic Views

## 0. The one rule

**Every typed page runs the same code.** `generic-entity-tab.ejs` + `genericEntity.js` + `generic-entity-init.js` render Categories, Projects, Goals, Todos, Tasks, Tickets and Ideas, and will render any type a user invents. What differs between them comes from the type's row in `entity_types` and its fields in `entity_type_fields` — never from a branch on its slug.

> **If you are about to write `if (typeSlug === '...')` in the generic engine, stop.** That branch is the bug this architecture exists to prevent: it is what once gave Categories a "+ Folder" button that Todos did not have.

Only **Dailies** (calendar, recurrence, time boxes) and **Templates** (instantiate-to-work-item) still have bespoke tabs. Everything else was converged, Projects most recently — which required migrating `priorities` into `entities` first, because a template swap alone would have rendered an empty list.

### One definition of the system types

`src/database/systemEntityTypes.js` is the only place the system entity types, their fields and their relationship rules are written down. `mysqlSchema.js`, `mssqlSchema.js`, `schemaMigrationService.js`, `scripts/phase0-seed-entity-types.js` and `SYSTEM_TYPE_DEFAULTS` all read from it. There were previously five hand-maintained copies that disagreed on `supports_hierarchy`, icons and labels, so which values an install got depended on which path created it — and `npm run db:init` runs the schema file, never phase 0, so the schema file's stale copy is what fresh installs actually received. **Add a type, rename one, or change a flag in that file and nowhere else.**

The schema seeders insert what is missing and reconcile only the attributes Settings does not expose (`display_order`, `show_in_row`, `is_completion_signal`, plus a forbidden folder-like icon). They deliberately never overwrite a `label`, `field_type` or `field_options`, because those are editable and a rename is a legitimate choice.

### Settings → Entity Types is the control surface

`entity_types.is_visible` decides whether a type gets a dashboard tab; `entity_types.order_index` decides the tab order. Both are **global, single sources of truth** — the Settings list and the dashboard tab bar are two views of the same values, editable from either end. A per-context layer (`context_tab_settings`) used to reorder tabs after render; it was removed, because two mechanisms owning one property disagree the moment either is used.

**UPDATED (Phase 10):** This document describes the unified generic entity rendering system, fully implemented as of Phase 10. All entity types (work items, priorities, todos, tasks, goals, areas, tickets, ideas, templates) now use the same generic engine instead of type-specific implementations.

The architecture relies on:
- **Generic Entity Service** (`src/services/entityService.js`): CRUD for any entity type
- **Generic Entity Routes** (`src/routes/api/entities.js`): polymorphic `/api/entities/:typeSlug` endpoints
- **Type Registry** (`src/services/entityTypeService.js`): dynamic field schemas and relationship rules
- **Generic Renderer** (`src/public/js/genericEntity.js`): reusable tree/row/editor for all types

## 1. Generic Row Rendering (Unified for All Types)

The generic renderer now handles all entity types with a single row template:

- **Generic render function** (`src/public/js/genericEntity.js#renderEntityRow`): takes an entity object and type schema, emits HTML for any type
- **Field rendering strategy map**: `fieldRenderers[fieldType](field, value)` — swap renderers per field type (text, textarea, number, date, select, status, checkbox, recurrence), not per entity type
- **Row identification**: `data-entity-id="${id}"` and `data-entity-type="${typeSlug}"` on the row's outer element — the dual key is necessary to route drag/edit/delete actions to the correct type endpoint
- **Dynamic field display**: fields to show, field labels, and edit control types all come from the type's schema in `entity_types` and `entity_type_fields` tables — no hardcoding in templates or JS

**Migrating from type-specific renderers:**
If you find yourself adding a type-specific render function, stop and add the field to the type's schema instead. The generic engine should handle it.

### Field types are the extension point

A type gains a capability by declaring a **field**, never by growing its own tab, its own editor, or its own table. Adding a capability means adding one entry to `fieldRenderers` in `genericEntity.js`, one value to `validFieldTypes` in `entityTypeService.js`, one `<option>` in `entity-type-editor.js`, and — because MySQL stores `field_type` as an ENUM — one value in **both** schema files.

Current types: `text`, `textarea`, `number`, `date`, `url`, `links`, `select`, `radio`, `checkbox`, `status`, `recurrence`.

- **`url`** — one named link; the field's own label names it, so a type can carry several distinct URL fields ("Repo", "Spec").
- **`links`** — 0-n named links, stored as a JSON array of `{url, title}` in `entity_field_values.value_json`. This replaced four per-type tables (`priority_links`, `task_links`, `ticket_links`, `to_do_links`) that existed only because there was no generic way to express "this type has links". **Do not add a fifth.**

Two traps this surfaced, both worth remembering:

1. **`url` and `radio` were offered by the type editor and accepted by the service, but had no renderer and were missing from the MySQL ENUM.** Saving one failed with `Data truncated for column 'field_type'`, and any that existed rendered as a plain text box. When adding a field type, walk all four layers — renderer, service validation, editor option, schema ENUM — or it half-exists.
2. **mysql2 auto-parses JSON columns.** `attachFieldValues` called `JSON.parse()` unconditionally and threw `Unexpected token 'o', "[object Obj"...` on every JSON-valued field, which silently broke `links` and `recurrence` alike. Parse only when the driver hands back a string (MSSQL's `NVARCHAR` does; MySQL's `JSON` does not).

## 2. Tree Rendering (Hierarchy & Relationships)

**Standard: CSS-only expand/collapse** — applies uniformly to all hierarchical types via the generic renderer.

- **Full DOM upfront**: `genericEntity.js#renderTree()` emits all nodes and their descendants in a single render, organized as:
  ```html
  <div class="entity-node" data-entity-id="${id}">
    <div class="entity-node-header"><!-- title, toggle, actions --></div>
    <div class="entity-node-children"><!-- recursive children --></div>
  </div>
  ```
- **CSS-only state**: toggling `classList.add/remove('expanded')` on `.entity-node` drives child visibility via:
  ```css
  .entity-node-children { display: none; }
  .entity-node.expanded > .entity-node-children { display: block; }
  ```
- **Indentation**: `${depth * 18}px` inline-style spacer span, emitted directly by `genericEntity.js#renderEntityRow()`
- **Event delegation**: toggle click binding via `.closest('[data-action="toggle-expand"]')`, not direct element checks

**Hierarchy is stored in `entity_relationships`, not on the entity.** The `entities` table has no parent column; parent/child links are `relationship_kind = 'hierarchy'` rows fetched in bulk via `GET /api/entities/:typeSlug/relationships?kind=hierarchy` and passed into `renderTree()`. Never add a `parent_entity_id` column or read one.

**Type configuration**: A type's `supports_hierarchy` flag in `entity_types` determines whether the tree render is invoked (true) or flat list (false).

### Folders

**A folder is a row of the page's own type with `entities.is_folder = 1` — never a separate entity type.** A folder on the Todos tab is a `to_do` row; a folder on Categories is an `area` row.

This is what keeps every typed page on one code path:

- **Page-scoped for free** — a Todos folder cannot leak onto Categories, because it *is* a todo.
- **No extra relationship rules** — the type's existing self-nesting rule (`to_do → to_do`) already permits items under items, items under folders, and folders under folders. A separate folder type would need a `folder → X` rule per type, and `entityRelationshipService.js#getRelationshipsForType` joins on `child_e.entity_type_id = parent_e.entity_type_id`, so cross-type folder edges would be silently dropped from the tree.
- **Drag-and-drop, delete-cascade, and reorder need no folder-aware code at all** — every edge is an ordinary same-type hierarchy edge.

Exactly two places in the renderer are folder-aware, both driven by `is_folder` and never by type slug:

1. `renderEntityRow()` swaps the type's icon for 📁.
2. `buildForm()` emits a title-only form (folders hold no field values).

The "+ Folder" button is rendered for every type by `generic-entity-tab.ejs` and removed at init time for types where `supports_hierarchy` is false. It opens the standard editor pane — **no `prompt()`, no modal**. Creating and renaming a folder use the same editor and the same save path as any other item.

**If you are about to write `if (typeSlug === '...')` in the generic engine, stop.** That branch is the bug this architecture exists to prevent — it is what previously gave Categories a folder button that Todos did not have. Drive the difference from `entity_types` / `entity_type_fields` instead.

## 3. Generic Editor (Unified for All Types)

**Single generic editor** (`src/public/js/genericEntity.js#EntityEditor`) replaces all type-specific editor modules:

```js
const EntityEditor = (() => {
  let splitPane, currentEntityId, currentTypeSlug, typeSchema, hasChanges;
  const trackFormChanges = createChangeTracker(formElement, saveButton); // via changeTracker factory
  const fillForm = (entity, fields) => fields.forEach(f => applyFieldValue(form, f, entity.fields[f.field_key]));
  const save = () => fetch(`/api/entities/${typeSlug}/${entityId}`, { ... });
  return { init, populate, save, close };
})();
```

**Key differences from per-type editors:**
- **Dynamic form generation**: `EntityEditor#buildForm(typeSchema)` generates form fields from `entity_type_fields` at runtime, not hardcoded in HTML
- **Field rendering strategy**: each form field is rendered via `fieldRenderers[field.field_type](field)` to emit the appropriate control (text input, textarea, date picker, select, etc.)
- **Single change-tracker instance**: shared `createChangeTracker()` factory (`src/public/js/changeTracker.js`) replaces 8+ copy-pasted implementations
- **Pane visibility**: `splitPane.showRightPane()` / `hideRightPane()` only called by the editor, just as before
- **Automatic field mapping**: no `fillForm()`/`save()` branching — the type schema tells the editor which fields exist and what type each is

**No type-specific editors exist anymore.** If you need custom editing logic for a type, add it as a custom field renderer in `fieldRenderers`, not a new editor module.

## 4. Dynamic Field Mapping (From Type Schema)

**No hardcoded type-specific field maps exist.** Field mapping is data-driven:

- **Source of truth**: `entity_type_fields` table — defines which fields belong to which type, their display order, label, and control type
- **At render time**: `genericEntity.js#buildForm(typeSchema)` queries the type's fields and generates form controls dynamically
- **At save time**: `genericEntity.js#collectFormValues(typeSchema, isFolder)` reads all fields defined for that type and returns `{ title, is_folder, fields: { ... } }`. **Field values must be nested under `fields`** — that is the shape `entityService.js#createEntity`/`updateEntity` read. Returning them flat alongside `title` makes the service silently ignore every one of them, which is exactly how `entity_field_values` stayed empty while saves reported success.
- **Future custom types**: when a user creates a new type in Settings with custom fields, the generic editor automatically handles them — no code changes

**Consistency guaranteed by single source of truth:** Because all types use the same generic editor + dynamic schema, there's no risk of two "interpretations" of which fields a type has (the problem that spawned the `ff2b943` fix). The schema is consulted once at render time and is authoritative.

## 4b. Rows are a table: columns, header, cells

Every typed page renders its rows as a CSS grid whose template is published once
on `.entity-list`, so the header and every row share one definition and cannot
drift apart. What that buys, and the rules that come with it:

- **Columns are the type's fields with `show_in_row`**, in `display_order`, plus
  Title. Title carries the indent, expand arrow, icon and child count, and can be
  dragged anywhere among them - its position is `entity_types.title_order`.
- **Never scrolls horizontally, never truncates.** Tracks are fractional and long
  values wrap, so a row grows taller rather than being cut off or pushing the
  grid wider. Title keeps a pixel floor: with no floor it collapses to nothing on
  a narrow pane and the row loses its name.
- **Columns are only as wide as their content needs.** Status, select and radio
  are measured from a real control rendered offscreen; checkbox, emoji, number
  and date get fixed widths; open-ended text shares what is left.
- **Cells are controls, not text.** Status cycles, dropdown/radio are selects,
  checkbox toggles, dates open a picker, emoji opens a picker or cycles a set.
  A cell control never opens or closes the editor - it only redirects an editor
  that is already open, because opening one re-flows the tab and moves the cell
  out from under the pointer.
- **Folders show roll-ups.** A folder has no field values; a column declaring
  `rollup` shows what its descendants add up to, derived at render time and never
  stored. That badge is not clickable.
- **One value, many views.** `show_in_row`, `show_column_label` and
  `display_order` are each editable from the column chooser, the row editor and
  Settings. They all write the same field record - never add a per-view store.

## 5. CSS & Class Naming (Generic System)

- **kebab-case with entity-prefix**: `entity-node`, `entity-node-header`, `entity-node-children`, `entity-row`, `entity-toggle` — consistency across all types
- **Shared generic rules**: `src/public/css/main.css` now contains all entity rendering styles (tree, rows, editors, drag indicators) — no per-type stylesheets
- **State classes**: `.expanded`, `.selected`, `.editing` on the outer element, driving descendant visibility via CSS combinators:
  ```css
  .entity-node-children { display: none; }
  .entity-node.expanded > .entity-node-children { display: block; }
  ```
- **Dynamic theming**: field-type-specific styling (e.g. `.field-status { ... }`, `.field-date { ... }`) lets the generic renderer match visual conventions per control type, not per entity type

## 5b. Context menus

Right-clicking a row (or empty space) in a typed page opens a menu built from the type definition, in `generic-entity-init.js`:

- `supports_hierarchy` gates every "New … inside" entry and folders;
- the type's `hierarchy` rules in `entity_type_relationships` decide which types may be children.

"New … inside" records the row, opens the standard editor, and writes the nesting edge once the child exists. Cross-type children are deliberately **not** offered — a tab only has an editor for its own type, so creating a Goal inside a Project would have nowhere to render; that is an association, not a creation.

The menu carries `entity-context-menu` alongside the shared `.context-menu` class, because the hand-written Dailies menu is always in the DOM under the latter.

## 5c. Editor behaviour

- **Creating** an item or a folder leaves the editor open on the new record, with its row marked `.selected`, so you can keep working. Editing an existing item closes on save.
- **Save starts disabled** and enables on the first change. `populate()` must reset `disabled = true`; it previously only reset `hasChanges`, so once any edit enabled the button it stayed enabled for every item opened afterwards.
- **Saving never closes an editor**, and neither does **Revert** - which reloads
  the stored record rather than discarding the editor. Both buttons are disabled
  until something changes. An editor is closed by clicking its row again.
- **No browser dialogs.** Use `app.confirm(message, title)` / `app.prompt(message, {title, defaultValue, placeholder})` (`main.js`) and the editor pane — never `confirm()`/`prompt()`/`alert()`; for `alert()` use `app.notify(message, 'danger'|'warning')`. Both dialogs are one modal built on demand by `app._dialog`, so they behave identically on the dashboard and on Settings — the `#confirmModal` markup they used to need lived only in `dashboard.ejs`, which meant `app.confirm` silently fell back to `window.confirm` on Settings, which is why Settings code called the browser dialog directly.
- **Cmd+S / Ctrl+S saves the open editor**, on every surface — `src/public/js/save-shortcut.js`. It resolves the button by walking up from the focused element to the tightest enclosing scope (`.modal.show`, `.draggable-modal`, `.split-pane-right`, `.tab-content-pane.active`, `form`) that holds a visible, enabled Save button, so it needs to know nothing about any particular editor. A new editor is covered for free provided its Save button id is `save…` or `…SaveBtn`, or it carries `data-action="save"` — if you name one something else, the shortcut silently skips it.
- **The selected row carries `.selected`**, styled once in `main.css` for every list in the app. Set it with `app.selectRow(rows, groupSelector)` (`main.js`) when the editor opens and when it closes, and re-apply after any re-render — these lists are rebuilt with `innerHTML`, which drops the class. Add a new row type to the shared selector list in `main.css` rather than restyling selection per page; note the deliberate `.selected.selected` there, which outranks the per-tab `:hover` rules that would otherwise erase the indicator under the pointer.

## 6. Generic API Calls

**Single pattern** used by all entity operations:

```js
// All entity CRUD routes return { success: bool, data: entity, message?: string }
const response = await app.fetch(`/api/entities/${typeSlug}`, { 
  method: 'POST', 
  body: JSON.stringify({ title, ...fields }) 
});
if (response.success) { app.notify('Created', 'success'); }
```

**Centralized via app.fetch()** (`src/public/js/main.js`). Three entry points,
and no call site should write a CSRF header by hand — a forgotten one is not a
visible error, the write just silently fails:

- **`app.fetch(url, options)`** — injects the CSRF header, parses the body
  *even on a 4xx* (the API answers failures with `{ success: false, message }`
  and that message is the useful part), and throws an `Error` carrying
  `.status` and `.body` with the **server's** message. It deliberately does
  **not** show a toast: callers already do, and two notifications for one
  failure is worse than none.
- **`app.fetchData(url, options)`** — the same, unwrapped to `data`. What a
  caller usually wants.
- **`app.fetchRaw(url, options)`** — the raw `Response` with the header
  attached, for call sites that need `.ok`, a blob, or a stream.

This was aspirational for a long time: there were 173 raw `fetch(` calls and
126 places writing the header by hand. 128 call sites are now migrated and the
hand-rolled count is zero. `forms.js` also patches `window.fetch` globally as a
safety net — that is belt-and-braces, not the mechanism, and it is action at a
distance. Use these.

**Generic entity routes** (`/api/entities/:typeSlug`) handle all types identically — no per-type endpoints. The `typeSlug` URL parameter routes to the right type service.

## Phase 10 Completion Checklist

The generic entity engine is now the sole architecture for all entity types. Completed:

- ✅ **Generic renderer** (`src/public/js/genericEntity.js`) handles trees, rows, and editors for all types
- ✅ **Dynamic schema system**: field definitions come from `entity_type_fields` table, not hardcoded
- ✅ **Polymorphic API routes** (`/api/entities/:typeSlug/*`) replace 8+ type-specific endpoints
- ✅ **Unified change tracking** via `createChangeTracker()` factory
- ✅ **Field renderer strategy map** for extensible, type-agnostic control rendering
- ✅ **Type-aware CSS** with generic `.entity-*` class names
- ✅ **Centralized fetch pattern** via `app.fetch()` for all API calls

**Legacy type-specific code has been removed:**
- ❌ `src/public/js/editors/*` — replaced by generic editor
- ❌ Per-tab render functions (`renderTaskRow`, `renderAreaRow`, etc.) — replaced by `genericEntity.renderRow()`
- ❌ Per-tab tree renders (`renderTasksList`, `renderAreaTree`, etc.) — replaced by `genericEntity.renderTree()`
- ❌ Type-specific field mapping (`TaskEditor.fillForm()`, `AreaEditor.save()`, etc.) — replaced by schema-driven field mapping

**Custom types now work automatically:** Users can define new types in Settings with custom fields. The generic editor, renderer, and API routes automatically support them — no code changes needed.
