# Confluence Page Exporter

Export Confluence spaces and page trees into structured YAML files for offline analysis, migration planning, or documentation auditing.

## Prerequisites

- [confluence-cli](https://github.com/pchuri/confluence-cli) (v2.14+) installed and configured
- `jq`
- Python 3.9+

## Quick Start

```bash
# Configure confluence-cli (one-time)
confluence init

# Sync all spaces metadata (fast, no page trees)
python3 scripts/sync_source_states.py --spaces-only

# Sync a specific space (metadata + page tree)
python3 scripts/sync_source_states.py --space 0003

# Generate page trees for all spaces (3 concurrent, resumable)
python3 scripts/sync_source_states.py --pages-only

# Full sync (all spaces + all page trees)
python3 scripts/sync_source_states.py
```

## Output

Generated files are written to `source-states/` (gitignored):

```
source-states/
├── spaces.yaml          # All spaces with name, category, page count, URL
├── pages/
│   ├── 0003.yaml        # Recursive page tree for each space
│   ├── ENG.yaml
│   └── ...
└── logs/                # Per-space sync logs
```

## Scripts

| Script | Purpose |
|--------|---------|
| `scripts/sync_source_states.py` | Main script — generates YAML state files (parallel, resumable) |
| `shell/list-spaces-with-page-count.sh` | Interactive table of spaces with page counts |
| `shell/list-pages-in-space.sh` | Interactive table of pages in a space |

See [shell/README.md](shell/README.md) for shell script usage details.
