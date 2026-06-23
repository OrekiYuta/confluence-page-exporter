# Shell Scripts

Interactive CLI tools for quick Confluence queries. For bulk sync, use `scripts/sync_source_states.py` instead.

## Prerequisites

- [confluence-cli](https://github.com/pchuri/confluence-cli) installed and configured (`confluence init`)
- `jq`

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
