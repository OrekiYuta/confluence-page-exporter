#!/bin/bash
# Sync Confluence spaces and page trees into source-states/ as YAML files
#
# Usage:
#   ./shell/sync-source-states.sh                  # full sync (all spaces + page trees)
#   ./shell/sync-source-states.sh --no-personal    # skip personal spaces
#   ./shell/sync-source-states.sh --spaces-only    # only generate spaces.yaml (no page trees)
#   ./shell/sync-source-states.sh --space 0003     # sync single space (updates spaces.yaml + generates pages/0003.yaml)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
OUTPUT_DIR="${PROJECT_DIR}/source-states"
PAGES_DIR="${OUTPUT_DIR}/pages"

SKIP_PERSONAL=false
SPACES_ONLY=false
SINGLE_SPACE=""

while [ $# -gt 0 ]; do
    case "$1" in
        --no-personal) SKIP_PERSONAL=true; shift ;;
        --spaces-only) SPACES_ONLY=true; shift ;;
        --space) SINGLE_SPACE="$2"; shift 2 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

mkdir -p "$PAGES_DIR"

# Get Confluence domain from config
CONFLUENCE_DOMAIN=$(jq -r '.profiles[.activeProfile].domain' ~/.confluence-cli/config.json 2>/dev/null)
if [ -z "$CONFLUENCE_DOMAIN" ] || [ "$CONFLUENCE_DOMAIN" = "null" ]; then
    CONFLUENCE_DOMAIN="unknown.atlassian.net"
fi
BASE_URL="https://${CONFLUENCE_DOMAIN}/wiki/spaces"

TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

# --- Helper: get page count for a space ---
get_page_count() {
    local key="$1"
    local result
    result=$(NO_COLOR=1 confluence search --cql "type=page AND space=\"${key}\"" --limit 10000 2>&1 | head -1)
    local count
    count=$(echo "$result" | sed -n 's/^Found \([0-9]*\) result.*/\1/p')
    if [ -z "$count" ]; then
        echo "0"
    else
        echo "$count"
    fi
}

# --- Helper: get space category ---
get_category() {
    local key="$1"
    local cat
    cat=$(confluence api "space/${key}?expand=metadata.labels" --jq '[.metadata.labels.results[].name] | join(", ")' 2>/dev/null | tr -d '"')
    if [ -z "$cat" ] || [ "$cat" = "null" ]; then
        echo ""
    else
        echo "$cat"
    fi
}

# --- Helper: parse tree output into structured data (DEPTH|ID|TITLE|URL) ---
parse_tree_to_yaml() {
    local tree_output="$1"
    local indent_unit=2

    local pending_depth=""
    local pending_id=""
    local pending_title=""

    echo "$tree_output" | tail -n +2 | while IFS= read -r line; do
        # Strip ANSI codes
        clean=$(echo "$line" | sed 's/\x1b\[[0-9;]*m//g')

        # Check if this line is a URL (contains https://)
        if echo "$clean" | grep -q "https://"; then
            url=$(echo "$clean" | sed 's/^[│ ├└─── ]*//;s/^ *//')
            if [ -n "$pending_title" ]; then
                echo "${pending_depth}|${pending_id}|${pending_title}|${url}"
                pending_title=""
            fi
            continue
        fi

        # Flush previous item without URL if we hit a new page line
        if [ -n "$pending_title" ]; then
            echo "${pending_depth}|${pending_id}|${pending_title}|"
        fi

        # Count leading spaces to determine depth
        stripped="${clean#"${clean%%[! ]*}"}"
        spaces=$(( ${#clean} - ${#stripped} ))

        # Remove tree characters
        content=$(echo "$stripped" | sed 's/^[├└│─── ]*//;s/^[│ ]*//;s/^[├└─ ]*//;s/^── //')
        # Remove emoji prefix
        content=$(echo "$content" | sed 's/^📄 //;s/^📁 //')

        # Extract ID and title
        if echo "$content" | grep -q "(ID: "; then
            title=$(echo "$content" | sed 's/ (ID: [0-9]*)$//')
            id=$(echo "$content" | sed -n 's/.*(ID: \([0-9]*\))$/\1/p')
        else
            title="$content"
            id=""
        fi

        # Skip empty lines and summary lines
        if [ -z "$title" ] || echo "$title" | grep -q "^Total: "; then
            pending_title=""
            continue
        fi

        depth=$((spaces / indent_unit))
        pending_depth="$depth"
        pending_id="$id"
        pending_title="$title"
    done

    # Flush last pending item
    if [ -n "$pending_title" ]; then
        echo "${pending_depth}|${pending_id}|${pending_title}|"
    fi
}

# --- Helper: convert depth-based list to nested YAML ---
generate_pages_yaml() {
    local space_key="$1"
    local space_name="$2"
    local parsed_data="$3"

    cat <<EOF
space_key: "${space_key}"
space_name: "${space_name}"
generated_at: "${TIMESTAMP}"
pages:
EOF

    if [ -z "$parsed_data" ]; then
        echo "  []"
        return
    fi

    echo "$parsed_data" | awk -F'|' '
    BEGIN { lines_count = 0 }
    {
        lines_count++
        depths[lines_count] = $1
        ids[lines_count] = $2
        titles[lines_count] = $3
        urls[lines_count] = $4
        gsub(/"/, "\\\"", titles[lines_count])
    }
    END {
        for (i = 1; i <= lines_count; i++) {
            depth = depths[i]
            id = ids[i]
            title = titles[i]
            url = urls[i]

            has_children = 0
            if (i < lines_count && depths[i+1] > depth) {
                has_children = 1
            }

            indent = "  "
            for (d = 0; d < depth; d++) {
                indent = indent "    "
            }

            printf "%s- id: \"%s\"\n", indent, id
            printf "%s  title: \"%s\"\n", indent, title
            printf "%s  url: \"%s\"\n", indent, url
            if (has_children) {
                printf "%s  children:\n", indent
            } else {
                printf "%s  children: []\n", indent
            }
        }
    }'
}

# --- Sync a single space's page tree ---
sync_space_pages() {
    local key="$1"
    local name="$2"
    local output_file="${PAGES_DIR}/${key}.yaml"

    local homepage_id
    homepage_id=$(confluence api "space/${key}?expand=homepage" --jq ".homepage.id" 2>/dev/null | tr -d '"')

    if [ -z "$homepage_id" ] || [ "$homepage_id" = "null" ]; then
        echo "    [!] No homepage found, skipping page tree"
        return
    fi

    local tree_output
    tree_output=$(NO_COLOR=1 confluence children "$homepage_id" --recursive --format tree --show-id --show-url 2>&1)

    if echo "$tree_output" | grep -q "Error\|error"; then
        echo "    [!] Failed to fetch page tree"
        return
    fi

    local parsed
    parsed=$(parse_tree_to_yaml "$tree_output")

    generate_pages_yaml "$key" "$name" "$parsed" > "$output_file"
    echo "    -> pages/${key}.yaml"
}

# --- Update or insert a space entry in spaces.yaml ---
upsert_space_in_yaml() {
    local key="$1"
    local name="$2"
    local category="$3"
    local pages="$4"
    local url="$5"
    local spaces_file="${OUTPUT_DIR}/spaces.yaml"

    local safe_name
    safe_name=$(echo "$name" | sed 's/"/\\"/g')

    local entry
    entry=$(cat <<EOF
  - key: "${key}"
    name: "${safe_name}"
    category: "${category}"
    pages: ${pages}
    url: "${url}"
EOF
)

    if [ ! -f "$spaces_file" ]; then
        # Create new spaces.yaml
        cat > "$spaces_file" <<EOF
generated_at: "${TIMESTAMP}"
total: 1
spaces:
${entry}
EOF
        return
    fi

    # Check if space already exists in the file
    if grep -q "key: \"${key}\"" "$spaces_file"; then
        # Remove existing entry block: "  - key: ..." line and all following indented lines (4 spaces+)
        local tmp_file="${spaces_file}.tmp"
        awk -v key="\"${key}\"" '
        BEGIN { skip = 0 }
        {
            if ($0 ~ /^  - key: / && index($0, key) > 0) {
                skip = 1
                next
            }
            if (skip && /^    /) {
                next
            }
            skip = 0
            print
        }
        ' "$spaces_file" > "$tmp_file"
        mv "$tmp_file" "$spaces_file"
    fi

    # Append entry
    echo "$entry" >> "$spaces_file"

    # Update total count
    local count
    count=$(grep -c "^  - key:" "$spaces_file" || echo "0")
    sed -i '' "s/^total: .*/total: ${count}/" "$spaces_file"

    # Update timestamp
    sed -i '' "s/^generated_at: .*/generated_at: \"${TIMESTAMP}\"/" "$spaces_file"
}

# ============================================================
# MAIN
# ============================================================

# --- Mode: single space ---
if [ -n "$SINGLE_SPACE" ]; then
    echo "Syncing space [${SINGLE_SPACE}]..."

    # Fetch space info
    space_name=$(confluence api "space/${SINGLE_SPACE}" --jq ".name" 2>/dev/null | tr -d '"')
    if [ -z "$space_name" ] || [ "$space_name" = "null" ]; then
        echo "Error: Space '${SINGLE_SPACE}' not found"
        exit 1
    fi

    # Get metadata
    category=$(get_category "$SINGLE_SPACE")
    pages=$(get_page_count "$SINGLE_SPACE")
    url="${BASE_URL}/${SINGLE_SPACE}"

    echo "  Space: ${space_name}"
    echo "  Category: ${category:-"-"}"
    echo "  Pages: ${pages}"

    # Update spaces.yaml
    upsert_space_in_yaml "$SINGLE_SPACE" "$space_name" "$category" "$pages" "$url"
    echo "  -> spaces.yaml (updated)"

    # Sync page tree
    if [ "$pages" -gt 0 ] 2>/dev/null; then
        sync_space_pages "$SINGLE_SPACE" "$space_name"
    else
        echo "    [!] No pages, skipping page tree"
    fi

    echo "Done."
    exit 0
fi

# --- Mode: full sync ---
echo "Fetching all spaces..."
spaces_json=$(confluence spaces --all --json 2>&1)

if [ $? -ne 0 ]; then
    echo "Error: Failed to fetch spaces"
    echo "$spaces_json"
    exit 1
fi

total=$(echo "$spaces_json" | jq '.spaceCount')
echo "Found $total spaces."

# Generate spaces.yaml
echo "Generating spaces.yaml..."

cat > "${OUTPUT_DIR}/spaces.yaml" <<EOF
generated_at: "${TIMESTAMP}"
total: ${total}
spaces:
EOF

i=0
echo "$spaces_json" | jq -r '.spaces[] | "\(.key)\t\(.name)\t\(.type)"' | while IFS=$'\t' read -r key name type; do
    if [ "$SKIP_PERSONAL" = "true" ]; then
        case "$key" in
            ~*) continue ;;
        esac
    fi

    i=$((i + 1))

    category=$(get_category "$key")
    pages=$(get_page_count "$key")
    url="${BASE_URL}/${key}"

    safe_name=$(echo "$name" | sed 's/"/\\"/g')

    cat >> "${OUTPUT_DIR}/spaces.yaml" <<EOF
  - key: "${key}"
    name: "${safe_name}"
    category: "${category}"
    pages: ${pages}
    url: "${url}"
EOF

    echo "  [${i}] ${key} - ${pages} pages"

    # Sync page tree (unless --spaces-only)
    if [ "$SPACES_ONLY" = "false" ] && [ "$pages" -gt 0 ] 2>/dev/null; then
        sync_space_pages "$key" "$name"
    fi
done

echo ""
echo "Done. Output: ${OUTPUT_DIR}/"
echo "  - spaces.yaml"
if [ "$SPACES_ONLY" = "false" ]; then
    echo "  - pages/*.yaml"
fi
