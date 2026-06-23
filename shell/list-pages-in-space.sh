#!/bin/bash
# List all pages in a given Confluence space (title and ID)

if [ -z "$1" ]; then
    echo "Usage: $0 <space-key>"
    echo "Example: $0 0003"
    exit 1
fi

SPACE_KEY="$1"
LIMIT=100
START=0
TOTAL_COUNT=0

echo "Fetching all pages in space [$SPACE_KEY]..."
echo ""
printf "%-6s | %-12s | %s\n" "#" "Page ID" "Title"
printf "%-6s-+-%-12s-+-%s\n" "------" "------------" "------------------------------------------------------------"

while true; do
    response=$(confluence api "space/${SPACE_KEY}/content/page?limit=${LIMIT}&start=${START}" --jq "." 2>/dev/null)

    if [ -z "$response" ] || [ "$response" = "null" ]; then
        if [ $START -eq 0 ]; then
            echo "Error: Failed to fetch pages for space [$SPACE_KEY]. Check if the space key is correct."
            exit 1
        fi
        break
    fi

    size=$(echo "$response" | jq -r '.size' 2>/dev/null)
    if [ -z "$size" ] || [ "$size" = "0" ] || [ "$size" = "null" ]; then
        if [ $START -eq 0 ]; then
            echo "No pages found in this space."
        fi
        break
    fi

    while IFS=$'\t' read -r id title; do
        TOTAL_COUNT=$((TOTAL_COUNT + 1))
        printf "%-6s | %-12s | %s\n" "$TOTAL_COUNT" "$id" "$title"
    done < <(echo "$response" | jq -r '.results[] | "\(.id)\t\(.title)"')

    START=$((START + size))

    if [ "$size" -lt "$LIMIT" ]; then
        break
    fi
done

echo ""
echo "Total: $TOTAL_COUNT pages"
