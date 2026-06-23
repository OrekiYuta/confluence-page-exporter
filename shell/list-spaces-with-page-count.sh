#!/bin/bash
# List all accessible Confluence spaces with page count (table format)
# Includes personal spaces by default; use --no-personal to exclude them
# Note: Queries each space individually, may be slow with many spaces

SKIP_PERSONAL=false
if [ "$1" = "--no-personal" ]; then
    SKIP_PERSONAL=true
fi

echo "Fetching all spaces..."
spaces_json=$(confluence spaces --all --json 2>&1)

if [ $? -ne 0 ]; then
    echo "Error: Failed to fetch spaces"
    echo "$spaces_json"
    exit 1
fi

total=$(echo "$spaces_json" | jq '.spaceCount')

if [ "$SKIP_PERSONAL" = "true" ]; then
    space_count=$(echo "$spaces_json" | jq '[.spaces[] | select(.key | startswith("~") | not)] | length')
    echo "Found $total spaces ($space_count non-personal). Counting pages per space..."
else
    echo "Found $total spaces. Counting pages per space..."
fi

echo ""
printf "%-4s | %-15s | %-45s | %-20s | %s\n" "#" "Key" "Name" "Category" "Pages"
printf "%-4s-+-%-15s-+-%-45s-+-%-20s-+-%s\n" "----" "---------------" "---------------------------------------------" "--------------------" "------"

i=0
echo "$spaces_json" | jq -r '.spaces[] | "\(.key)\t\(.name)\t\(.type)"' | while IFS=$'\t' read -r key name type; do
    if [ "$SKIP_PERSONAL" = "true" ]; then
        case "$key" in
            ~*) continue ;;
        esac
    fi

    i=$((i + 1))

    # Fetch space categories (labels)
    category=$(confluence api "space/${key}?expand=metadata.labels" --jq '[.metadata.labels.results[].name] | join(", ")' 2>/dev/null | tr -d '"')
    if [ -z "$category" ] || [ "$category" = "null" ]; then
        category="-"
    fi

    # Count pages using CQL search
    result=$(NO_COLOR=1 confluence search --cql "type=page AND space=\"${key}\"" --limit 10000 2>&1 | head -1)
    count=$(echo "$result" | sed -n 's/^Found \([0-9]*\) result.*/\1/p')

    if [ -z "$count" ]; then
        if echo "$result" | grep -q "No results"; then
            count="0"
        else
            count="N/A"
        fi
    fi

    printf "%-4s | %-15s | %-45s | %-20s | %s\n" "$i" "$key" "${name:0:45}" "${category:0:20}" "$count"
done

echo ""
echo "Done. (Use --no-personal to exclude personal spaces)"
