# Shell Scripts

Scripts for interacting with Confluence via `confluence-cli`.

## Prerequisites

- [confluence-cli](https://github.com/pchuri/confluence-cli) installed and configured (`confluence init`)
- `jq` installed

---

## sync-source-states.sh

Sync Confluence spaces and page trees into `source-states/` as YAML files.

### Usage

```bash
./shell/sync-source-states.sh                  # Full sync (all spaces + page trees)
./shell/sync-source-states.sh --no-personal    # Skip personal spaces (~xxx)
./shell/sync-source-states.sh --spaces-only    # Only generate spaces.yaml (faster)
./shell/sync-source-states.sh --space 0003     # Sync a single space's page tree
```

### Output

```
source-states/
├── spaces.yaml
└── pages/
    ├── 0003.yaml
    ├── 0009.yaml
    └── ...
```

**spaces.yaml**

```yaml
generated_at: "2026-06-23T06:48:36Z"
total: 7703
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
generated_at: "2026-06-23T06:48:36Z"
pages:
  - id: "2630115753985"
    title: "0003 - General Information"
    url: "https://company.atlassian.net/wiki/spaces/0003/pages/2630115753985"
    children: []
  - id: "2632338079827"
    title: "ForServiceCenter"
    url: "https://company.atlassian.net/wiki/spaces/0003/pages/2632338079827"
    children:
      - id: "2632337085724"
        title: "Unable to access"
        url: "https://company.atlassian.net/wiki/spaces/0003/pages/2632337085724"
        children: []
```

### Notes

- Full sync is slow (~2 API calls per space). Use `--spaces-only` for a quick overview, then `--space <key>` for specific spaces.
- Page trees are fetched recursively from each space's homepage.

---

## list-spaces-with-page-count.sh

List all accessible spaces with page count in a table.

### Usage

```bash
./shell/list-spaces-with-page-count.sh                # All spaces (including personal)
./shell/list-spaces-with-page-count.sh --no-personal  # Exclude personal spaces
```

### Output

```
#    | Key             | Name                                          | Category             | Pages
-----+-----------------+-----------------------------------------------+----------------------+-------
1    | 0003            | 0003 - ADD Listing Portal (EADD)              | knowledge-bases      | 77
2    | 0009            | 0009 - Airbus On-Line System                  | knowledge-bases      | 74
```

---

## list-pages-in-space.sh

List all pages in a given space with page ID and title.

### Usage

```bash
./shell/list-pages-in-space.sh <space-key>
./shell/list-pages-in-space.sh 0003
```

### Output

```
#      | Page ID      | Title
-------+--------------+-------------------------------------------------------------
1      | 2630115753985 | 0003 - General Information
2      | 2631969636493 | For End Users
3      | 2632338079827 | ForServiceCenter
...

Total: 77 pages
```
