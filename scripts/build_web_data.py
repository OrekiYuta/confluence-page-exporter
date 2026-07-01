#!/usr/bin/env python3
"""
Convert source-states/*.yaml into web/data/*.json for the static web viewer.

The web viewer (web/index.html) fetches these JSON files at runtime, so after
updating source-states you only need to re-run this script and refresh the page.

Usage:
    python3 scripts/build_web_data.py                 # build all data
    python3 scripts/build_web_data.py --space TNTEF   # rebuild a single space tree

Output:
    web/data/spaces.json          # space index (key, name, category, pages, url, has_tree)
    web/data/pages/<KEY>.json     # nested page tree for each space that has one
    web/data/manifest.json        # build metadata (generated_at, counts)

No third-party dependencies: a minimal YAML reader tailored to the known
source-states schema is used instead of PyYAML.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
SOURCE_DIR = PROJECT_DIR / "source-states"
PAGES_SRC_DIR = SOURCE_DIR / "pages"
WEB_DIR = PROJECT_DIR / "web"
DATA_DIR = WEB_DIR / "data"
PAGES_OUT_DIR = DATA_DIR / "pages"


def _unquote(value):
    """Strip surrounding double quotes and unescape YAML-escaped chars."""
    value = value.strip()
    if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        value = value[1:-1]
        value = value.replace('\\"', '"').replace("\\\\", "\\")
    return value


def parse_spaces_yaml(path):
    """Parse source-states/spaces.yaml -> list[dict]."""
    spaces = []
    current = None
    with path.open(encoding="utf-8") as fh:
        for raw in fh:
            line = raw.rstrip("\n")
            stripped = line.strip()
            if stripped.startswith("- key:"):
                if current:
                    spaces.append(current)
                current = {"key": _unquote(stripped[len("- key:"):])}
            elif current is None:
                continue
            elif stripped.startswith("name:"):
                current["name"] = _unquote(stripped[len("name:"):])
            elif stripped.startswith("category:"):
                current["category"] = _unquote(stripped[len("category:"):])
            elif stripped.startswith("pages:"):
                try:
                    current["pages"] = int(stripped[len("pages:"):].strip())
                except ValueError:
                    current["pages"] = 0
            elif stripped.startswith("url:"):
                current["url"] = _unquote(stripped[len("url:"):])
    if current:
        spaces.append(current)
    return spaces


def parse_pages_yaml(path):
    """
    Parse a source-states/pages/<KEY>.yaml file into a nested tree.

    Schema (indentation is significant, 2 spaces per level):
        space_key: "..."
        space_name: "..."
        generated_at: "..."
        pages:
          - id: "..."
            title: "..."
            url: "..."
            last_updated: "..."
            children: []            # or nested "children:" block
    """
    meta = {"space_key": "", "space_name": "", "generated_at": ""}
    lines = path.read_text(encoding="utf-8").split("\n")

    # Header (before "pages:")
    idx = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("space_key:"):
            meta["space_key"] = _unquote(stripped[len("space_key:"):])
        elif stripped.startswith("space_name:"):
            meta["space_name"] = _unquote(stripped[len("space_name:"):])
        elif stripped.startswith("generated_at:"):
            meta["generated_at"] = _unquote(stripped[len("generated_at:"):])
        elif stripped == "pages:":
            idx = i + 1
            break

    body = lines[idx:]

    # Build a flat list of (indent, key, value) tokens, then reconstruct tree
    # by indentation. Each page node starts with a "- id:" line.
    root = []
    # Stack of (indent_of_dash, node_list). A node's children live in a list
    # that is attached when a deeper "- " appears.
    stack = [(-1, root)]
    current_node = None

    for raw in body:
        if not raw.strip():
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        content = raw.strip()

        if content.startswith("- id:"):
            # New page node at this indent level.
            # Pop stack entries whose indent >= this dash indent.
            while stack and stack[-1][0] >= indent:
                stack.pop()
            parent_list = stack[-1][1]
            current_node = {
                "id": _unquote(content[len("- id:"):]),
                "title": "",
                "url": "",
                "last_updated": "",
                "children": [],
            }
            parent_list.append(current_node)
            # This node's own list becomes a potential parent for deeper dashes.
            stack.append((indent, current_node["children"]))
        elif current_node is not None and content.startswith("title:"):
            current_node["title"] = _unquote(content[len("title:"):])
        elif current_node is not None and content.startswith("url:"):
            current_node["url"] = _unquote(content[len("url:"):])
        elif current_node is not None and content.startswith("last_updated:"):
            current_node["last_updated"] = _unquote(content[len("last_updated:"):])
        elif content.startswith("children:"):
            # "children: []" -> nothing to do. A block form is handled by the
            # indentation of the following "- id:" lines.
            continue

    return meta, root


def count_tree_nodes(nodes):
    total = 0
    for node in nodes:
        total += 1
        total += count_tree_nodes(node.get("children", []))
    return total


def build_single_space(key):
    src = PAGES_SRC_DIR / f"{key}.yaml"
    if not src.exists():
        print(f"Error: {src} not found", file=sys.stderr)
        return None
    meta, tree = parse_pages_yaml(src)
    out = PAGES_OUT_DIR / f"{key}.json"
    payload = {
        "space_key": meta["space_key"] or key,
        "space_name": meta["space_name"],
        "generated_at": meta["generated_at"],
        "page_count": count_tree_nodes(tree),
        "pages": tree,
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def main():
    parser = argparse.ArgumentParser(description="Build web/data JSON from source-states YAML")
    parser.add_argument("--space", type=str, help="Rebuild only a single space page tree")
    args = parser.parse_args()

    if not SOURCE_DIR.exists():
        print(f"Error: {SOURCE_DIR} not found. Run scripts/sync_source_states.py first.", file=sys.stderr)
        sys.exit(1)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PAGES_OUT_DIR.mkdir(parents=True, exist_ok=True)

    # --- Single space mode ---
    if args.space:
        payload = build_single_space(args.space)
        if payload is None:
            sys.exit(1)
        print(f"Built web/data/pages/{args.space}.json ({payload['page_count']} pages)")
        # Refresh has_tree flag in spaces.json if it exists
        spaces_json = DATA_DIR / "spaces.json"
        if spaces_json.exists():
            data = json.loads(spaces_json.read_text(encoding="utf-8"))
            for s in data.get("spaces", []):
                if s["key"] == args.space:
                    s["has_tree"] = True
            spaces_json.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return

    # --- Full build ---
    spaces_yaml = SOURCE_DIR / "spaces.yaml"
    if not spaces_yaml.exists():
        print(f"Error: {spaces_yaml} not found. Run scripts/sync_source_states.py --spaces-only first.", file=sys.stderr)
        sys.exit(1)

    print("Parsing spaces.yaml...")
    spaces = parse_spaces_yaml(spaces_yaml)

    # Which spaces have a page tree yaml available?
    available_trees = {p.stem for p in PAGES_SRC_DIR.glob("*.yaml")} if PAGES_SRC_DIR.exists() else set()

    print(f"Building page tree JSON ({len(available_trees)} available)...")
    built_trees = 0
    for key in sorted(available_trees):
        payload = build_single_space(key)
        if payload is not None:
            built_trees += 1

    # Space index
    index = []
    for s in spaces:
        key = s["key"]
        index.append({
            "key": key,
            "name": s.get("name", key),
            "category": s.get("category", ""),
            "pages": s.get("pages", 0),
            "url": s.get("url", ""),
            "has_tree": key in available_trees,
        })

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    spaces_payload = {
        "generated_at": timestamp,
        "total": len(index),
        "with_tree": built_trees,
        "spaces": index,
    }
    (DATA_DIR / "spaces.json").write_text(
        json.dumps(spaces_payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    manifest = {
        "generated_at": timestamp,
        "total_spaces": len(index),
        "spaces_with_tree": built_trees,
    }
    (DATA_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"\nDone.")
    print(f"  web/data/spaces.json  ({len(index)} spaces)")
    print(f"  web/data/pages/*.json ({built_trees} trees)")
    print(f"  web/data/manifest.json")


if __name__ == "__main__":
    main()
