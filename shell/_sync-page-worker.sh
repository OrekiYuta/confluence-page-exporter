#!/bin/bash
# Worker script: sync a single space's page tree
# Called by sync-source-states.sh via xargs
# Usage: _sync-page-worker.sh <space-key> <pages-dir> <timestamp> <names-file> <log-dir>

key="$1"
PAGES_DIR="$2"
TIMESTAMP="$3"
NAMES_FILE="$4"
LOG_DIR="$5"

output_file="${PAGES_DIR}/${key}.yaml"
LOG_FILE="${LOG_DIR}/${key}.log"

# Skip if already exists
if [ -f "$output_file" ]; then
    exit 0
fi

# Look up space name from names file
name=$(grep "^${key}	" "$NAMES_FILE" 2>/dev/null | cut -f2-)
if [ -z "$name" ]; then
    name=$(confluence api "space/${key}" --jq ".name" 2>/dev/null | tr -d '"')
fi
if [ -z "$name" ] || [ "$name" = "null" ]; then
    name="$key"
fi

# Get homepage ID
homepage_id=$(confluence api "space/${key}?expand=homepage" --jq ".homepage.id" 2>/dev/null | tr -d '"')
if [ -z "$homepage_id" ] || [ "$homepage_id" = "null" ]; then
    echo "[$(date -u +%H:%M:%S)] SKIP no_homepage key=${key}" >> "$LOG_FILE"
    echo "  [!] ${key} - No homepage found, skipping"
    exit 0
fi

# Fetch recursive page tree
tree_output=$(NO_COLOR=1 confluence children "$homepage_id" --recursive --format tree --show-id --show-url 2>&1)
if echo "$tree_output" | grep -q "Error\|error"; then
    echo "[$(date -u +%H:%M:%S)] FAIL fetch_tree key=${key} homepage=${homepage_id}" >> "$LOG_FILE"
    echo "$tree_output" >> "$LOG_FILE"
    echo "  [!] ${key} - Failed to fetch page tree"
    exit 0
fi

# Parse tree into DEPTH|ID|TITLE|URL lines
# Strip ANSI codes and emoji before awk to avoid multibyte issues
parsed=$(echo "$tree_output" | tail -n +2 \
    | sed 's/\x1b\[[0-9;]*m//g' \
    | sed 's/📄 //g; s/📁 //g' \
    | awk '
BEGIN { pd=""; pi=""; pt="" }
{
    if ($0 ~ /https:\/\//) {
        url = $0; gsub(/^[│ ├└───]*/, "", url); gsub(/^ */, "", url)
        if (pt != "") { print pd "|" pi "|" pt "|" url; pt = "" }
        next
    }
    if (pt != "") { print pd "|" pi "|" pt "|" }
    line = $0; gsub(/^[[:space:]]+/, "", $0)
    spaces = length(line) - length($0)
    content = $0
    gsub(/^[├└│─── ]*/, "", content); gsub(/^[│ ]*/, "", content)
    gsub(/^[├└─ ]*/, "", content); gsub(/^── /, "", content)
    if (match(content, /\(ID: [0-9]+\)$/)) {
        id = content; gsub(/.* \(ID: /, "", id); gsub(/\)$/, "", id)
        title = content; gsub(/ \(ID: [0-9]+\)$/, "", title)
    } else { title = content; id = "" }
    if (title == "" || title ~ /^Total: /) { pt = ""; next }
    pd = int(spaces / 2); pi = id; pt = title
}
END { if (pt != "") print pd "|" pi "|" pt "|" }
')

# Generate YAML output
{
    echo "space_key: \"${key}\""
    echo "space_name: \"${name}\""
    echo "generated_at: \"${TIMESTAMP}\""
    echo "pages:"
    if [ -z "$parsed" ]; then
        echo "  []"
    else
        echo "$parsed" | awk -F'|' '
        {
            depth = $1; id = $2; title = $3; url = $4
            gsub(/"/, "\\\"", title)
            indent = "  "
            for (d = 0; d < depth; d++) indent = indent "    "
            printf "%s- id: \"%s\"\n", indent, id
            printf "%s  title: \"%s\"\n", indent, title
            printf "%s  url: \"%s\"\n", indent, url
            printf "%s  children: []\n", indent
        }'
    fi
} > "$output_file"

echo "[$(date -u +%H:%M:%S)] OK key=${key} pages_file=${output_file}" >> "$LOG_FILE"
echo "  [ok] ${key} -> pages/${key}.yaml"
