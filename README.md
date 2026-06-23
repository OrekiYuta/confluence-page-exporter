# Confluence Page Exporter

Export Confluence spaces and page trees into structured YAML files for offline analysis, migration planning, or documentation auditing.

## Prerequisites

- [confluence-cli](https://github.com/pchuri/confluence-cli) (v2.14+) installed and configured
- `jq`

## Quick Start

```bash
# Configure confluence-cli (one-time)
confluence init

# Sync all spaces metadata (fast, no page trees)
./shell/sync-source-states.sh --spaces-only

# Sync a specific space (metadata + page tree)
./shell/sync-source-states.sh --space 0003

# Full sync (all spaces + all page trees, slow)
./shell/sync-source-states.sh
```

## Output

Generated files are written to `source-states/` (gitignored):

```
source-states/
├── spaces.yaml          # All spaces with name, category, page count, URL
└── pages/
    ├── 0003.yaml        # Recursive page tree for each space
    ├── ENG.yaml
    └── ...
```

## Scripts

See [shell/README.md](shell/README.md) for detailed usage of each script.

| Script | Purpose |
|--------|---------|
| `sync-source-states.sh` | Main script — generates YAML state files |
| `list-spaces-with-page-count.sh` | Interactive table of spaces with page counts |
| `list-pages-in-space.sh` | Interactive table of pages in a space |
