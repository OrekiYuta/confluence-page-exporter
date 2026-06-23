# Scripts

## sync_source_states.py

Sync Confluence spaces and page trees into `source-states/` as YAML files. Supports parallel execution and resumable runs.

### Usage

```bash
python3 scripts/sync_source_states.py                      # Full sync (all spaces + page trees)
python3 scripts/sync_source_states.py --spaces-only        # Only generate spaces.yaml (no page trees)
python3 scripts/sync_source_states.py --pages-only         # Only generate pages/*.yaml (from existing spaces.yaml)
python3 scripts/sync_source_states.py --space 0003         # Sync a single space
python3 scripts/sync_source_states.py --no-personal        # Skip personal spaces (~xxx)
python3 scripts/sync_source_states.py --concurrency 5      # Set parallel workers (default: 3)
```

### Resume

Already generated `pages/*.yaml` files are skipped automatically. If the script is interrupted, simply re-run the same command to continue from where it left off.

### Output

```
source-states/
├── spaces.yaml
├── pages/
│   ├── 0003.yaml
│   ├── 0009.yaml
│   └── ...
└── logs/
    ├── 0003.log
    └── ...
```

**spaces.yaml**

```yaml
generated_at: "2026-06-24T..."
total: 7701
spaces:
  - key: "0003"
    name: "0003 - ADD Listing Portal (EADD)"
    category: "knowledge-bases"
    pages: 77
    url: "https://company.atlassian.net/wiki/spaces/0003"
```

**pages/\<space-key\>.yaml**

```yaml
space_key: "0003"
space_name: "0003 - ADD Listing Portal (EADD)"
generated_at: "2026-06-24T..."
pages:
  - id: "2630115753985"
    title: "0003 - General Information"
    url: "https://company.atlassian.net/wiki/spaces/0003/pages/2630115753985"
    last_updated: "2025-12-30T01:41:43.376Z"
    children: []
  - id: "2632338079827"
    title: "ForServiceCenter"
    url: "https://company.atlassian.net/wiki/spaces/0003/pages/2632338079827"
    last_updated: "2026-06-15T01:38:47.842Z"
    children:
      - id: "2632337085724"
        title: "Unable to access"
        url: "https://company.atlassian.net/wiki/spaces/0003/pages/2632337085724"
        last_updated: "2026-06-15T01:42:05.906Z"
        children: []
```

### Performance

- `--spaces-only`: ~2 API calls per space (category + page count)
- `--pages-only`: ~3+ API calls per space (homepage + tree + update times batch)
- Default concurrency: 3 parallel workers. Increase to 5 for faster execution, but avoid higher to prevent Confluence rate limiting (429).
