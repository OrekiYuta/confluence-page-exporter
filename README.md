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

The web viewer data is generated separately into `web/data/` (also gitignored):

```
web/data/
├── spaces.json          # Space index (key, name, category, pages, url, has_tree)
├── pages/
│   └── <KEY>.json       # Nested page tree per space
└── manifest.json        # Build metadata
```

## Web Viewer

A static, dependency-free web viewer renders the synced data into a
Confluence-like interface: top space picker, left collapsible page-tree
navigation, and a right content area (placeholder + page metadata).

The page reads `web/data/*.json` **live** at runtime, so after updating
`source-states/` you only need to rebuild the data and refresh the browser —
no need to regenerate the HTML.

```bash
# 1. Build web/data JSON from source-states YAML
python3 scripts/build_web_data.py

# 2. Serve the web/ folder (fetch requires http://, not file://)
python3 -m http.server 8000 --directory web

# 3. Open http://localhost:8000 in your browser
```

Rebuild a single space after re-syncing it:

```bash
python3 scripts/sync_source_states.py --space 0003   # refresh source data
python3 scripts/build_web_data.py --space 0003       # refresh web/data
# then just refresh the browser
```

Deep links are supported: `http://localhost:8000/#<SPACE_KEY>/<PAGE_ID>`.

## Scripts

| Script | Purpose |
|--------|---------|
| `scripts/sync_source_states.py` | Main script — generates YAML state files (parallel, resumable) |
| `scripts/build_web_data.py` | Converts `source-states/*.yaml` into `web/data/*.json` for the web viewer |
| `shell/list-spaces-with-page-count.sh` | Interactive table of spaces with page counts |
| `shell/list-pages-in-space.sh` | Interactive table of pages in a space |

See [shell/README.md](shell/README.md) for shell script usage details.
