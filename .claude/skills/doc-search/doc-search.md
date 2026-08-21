# Doc Search

Discover, load, and manage project documentation efficiently.

## Modes

### Load Mode (default)
Load specific documentation based on skill needs.

```bash
/doc-search --load feature-structure,tech-stack
```

### Generate Mode
Analyze a skill and auto-generate its `doc-search.md` file.

```bash
/doc-search --analyze my-skill --overwrite
```

### Update Mode
Scan entire repository for documentation and update this manifest.

```bash
/doc-search --update
```

---

# Manifest

## Baseline (loads on SessionStart)
- feature-structure.md
- tech-stack.md
- uix.md

## All Available Docs

### Standards
- docs/standards/feature-structure.md
- docs/standards/tech-stack.md
- docs/standards/uix.md

### Features

### Other Documentation
