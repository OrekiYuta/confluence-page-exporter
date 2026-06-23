#!/usr/bin/env python3
"""
Sync Confluence spaces and page trees into source-states/ as YAML files.

Usage:
    python3 scripts/sync_source_states.py                      # full sync
    python3 scripts/sync_source_states.py --spaces-only        # only spaces.yaml
    python3 scripts/sync_source_states.py --pages-only         # only pages/*.yaml
    python3 scripts/sync_source_states.py --space 0003         # single space
    python3 scripts/sync_source_states.py --no-personal        # skip personal spaces
    python3 scripts/sync_source_states.py --concurrency 5      # parallel workers (default: 3)

Resume: already generated pages/*.yaml files are skipped automatically.
"""

import argparse
import json
import logging
import os
import re
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_DIR / "source-states"
PAGES_DIR = OUTPUT_DIR / "pages"
LOG_DIR = OUTPUT_DIR / "logs"

counter_lock = threading.Lock()
counter_value = 0


def get_confluence_domain():
    config_path = Path.home() / ".confluence-cli" / "config.json"
    try:
        config = json.loads(config_path.read_text())
        profile = config.get("activeProfile", "default")
        return config["profiles"][profile]["domain"]
    except (FileNotFoundError, KeyError, json.JSONDecodeError):
        return "unknown.atlassian.net"


def run_confluence(*args, env_override=None):
    env = os.environ.copy()
    env["NO_COLOR"] = "1"
    if env_override:
        env.update(env_override)
    result = subprocess.run(
        ["confluence", *args],
        capture_output=True, text=True, env=env
    )
    return result.stdout.strip()


def run_confluence_api_json(endpoint):
    raw = run_confluence("api", endpoint, "--jq", ".")
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def fetch_all_spaces(skip_personal=False):
    raw = run_confluence("spaces", "--all", "--json")
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []

    spaces = data.get("spaces", [])
    if skip_personal:
        spaces = [s for s in spaces if not s["key"].startswith("~")]
    return spaces


def fetch_space_category(key):
    data = run_confluence_api_json(f"space/{key}?expand=metadata.labels")
    if not data:
        return ""
    try:
        labels = data["metadata"]["labels"]["results"]
        return ", ".join(l["name"] for l in labels)
    except (KeyError, TypeError):
        return ""


def fetch_page_count(key):
    output = run_confluence("search", "--cql", f'type=page AND space="{key}"', "--limit", "10000")
    if not output:
        return 0
    match = re.match(r"Found (\d+) result", output)
    return int(match.group(1)) if match else 0


def fetch_homepage_id(key):
    data = run_confluence_api_json(f"space/{key}?expand=homepage")
    if not data:
        return None
    try:
        hid = data["homepage"]["id"]
        return str(hid) if hid else None
    except (KeyError, TypeError):
        return None


def fetch_page_tree(homepage_id):
    return run_confluence(
        "children", homepage_id,
        "--recursive", "--format", "tree", "--show-id", "--show-url"
    )


def parse_page_tree(tree_output):
    if not tree_output:
        return []

    lines = tree_output.split("\n")
    if len(lines) < 2:
        return []

    ansi_re = re.compile(r"\033\[[0-9;]*m")
    id_re = re.compile(r"\(ID:\s*(\d+)\)$")

    pages = []
    pending = None

    for line in lines[1:]:
        clean = ansi_re.sub("", line)

        if "https://" in clean:
            url = re.sub(r"^[│├└─── ]*", "", clean).strip()
            if pending:
                pending["url"] = url
                pages.append(pending)
                pending = None
            continue

        if pending:
            pages.append(pending)
            pending = None

        leading_spaces = len(clean) - len(clean.lstrip())
        content = re.sub(r"^[├└│─── ]+", "", clean.strip())
        content = re.sub(r"^[│ ]+", "", content)
        content = re.sub(r"^[├└─ ]+", "", content)
        content = re.sub(r"^── ", "", content)
        content = content.replace("📄 ", "").replace("📁 ", "")

        if not content or content.startswith("Total: "):
            continue

        id_match = id_re.search(content)
        if id_match:
            page_id = id_match.group(1)
            title = content[:id_match.start()].strip()
        else:
            page_id = ""
            title = content.strip()

        if not title:
            continue

        depth = leading_spaces // 2
        pending = {"id": page_id, "title": title, "url": "", "depth": depth}

    if pending:
        pages.append(pending)

    return pages


def fetch_update_times(space_key):
    times = {}
    start = 0
    limit = 100
    while True:
        raw = run_confluence(
            "api",
            f"content/search?cql=type%3Dpage+AND+space%3D{space_key}&expand=version&limit={limit}&start={start}",
            "--jq", "."
        )
        if not raw:
            break
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            break

        results = data.get("results", [])
        if not results:
            break

        for r in results:
            pid = str(r.get("id", ""))
            when = r.get("version", {}).get("when", "")
            if pid:
                times[pid] = when

        if len(results) < limit:
            break
        start += limit

    return times


def build_nested_tree(flat_pages, update_times):
    if not flat_pages:
        return []

    def build_children(pages, start_idx, parent_depth):
        children = []
        i = start_idx
        while i < len(pages):
            page = pages[i]
            if page["depth"] <= parent_depth:
                break
            if page["depth"] == parent_depth + 1:
                node = {
                    "id": page["id"],
                    "title": page["title"],
                    "url": page["url"],
                    "last_updated": update_times.get(page["id"], ""),
                    "children": [],
                }
                sub_children, i = build_children(pages, i + 1, page["depth"])
                node["children"] = sub_children
                children.append(node)
            else:
                i += 1
        return children, i

    result = []
    i = 0
    while i < len(flat_pages):
        page = flat_pages[i]
        node = {
            "id": page["id"],
            "title": page["title"],
            "url": page["url"],
            "last_updated": update_times.get(page["id"], ""),
            "children": [],
        }
        sub_children, i = build_children(flat_pages, i + 1, page["depth"])
        node["children"] = sub_children
        result.append(node)
    return result


def yaml_escape(s):
    return s.replace("\\", "\\\\").replace('"', '\\"')


def write_spaces_yaml(spaces_data, total, output_path):
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = [
        f'generated_at: "{timestamp}"',
        f"total: {total}",
        "spaces:",
    ]
    for s in spaces_data:
        lines.append(f'  - key: "{s["key"]}"')
        lines.append(f'    name: "{yaml_escape(s["name"])}"')
        lines.append(f'    category: "{yaml_escape(s.get("category", ""))}"')
        lines.append(f'    pages: {s.get("pages", 0)}')
        lines.append(f'    url: "{s.get("url", "")}"')

    output_path.write_text("\n".join(lines) + "\n")


def write_pages_yaml(space_key, space_name, pages_tree, output_path):
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = [
        f'space_key: "{space_key}"',
        f'space_name: "{yaml_escape(space_name)}"',
        f'generated_at: "{timestamp}"',
        "pages:",
    ]

    if not pages_tree:
        lines.append("  []")
    else:
        def render_nodes(nodes, indent_level=1):
            indent = "  " * indent_level
            for node in nodes:
                lines.append(f'{indent}- id: "{node["id"]}"')
                lines.append(f'{indent}  title: "{yaml_escape(node["title"])}"')
                lines.append(f'{indent}  url: "{node["url"]}"')
                lines.append(f'{indent}  last_updated: "{node["last_updated"]}"')
                if node["children"]:
                    lines.append(f"{indent}  children:")
                    render_nodes(node["children"], indent_level + 2)
                else:
                    lines.append(f"{indent}  children: []")

        render_nodes(pages_tree)

    output_path.write_text("\n".join(lines) + "\n")


def sync_single_space(key, name, pages_dir, log_dir, total_remaining):
    global counter_value

    output_file = pages_dir / f"{key}.yaml"
    log_file = log_dir / f"{key}.log"

    if output_file.exists():
        return "skip"

    logger = logging.getLogger(key)
    handler = logging.FileHandler(log_file, mode="w")
    handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

    homepage_id = fetch_homepage_id(key)
    if not homepage_id:
        with counter_lock:
            counter_value += 1
            n = counter_value
        logger.info(f"SKIP no_homepage key={key}")
        print(f"  [{n}/{total_remaining}] [!] {key} - No homepage found, skipping")
        return "skip"

    tree_output = fetch_page_tree(homepage_id)
    if not tree_output or "error" in tree_output.lower()[:100]:
        with counter_lock:
            counter_value += 1
            n = counter_value
        logger.info(f"FAIL fetch_tree key={key} homepage={homepage_id}")
        logger.info(tree_output[:500] if tree_output else "empty output")
        print(f"  [{n}/{total_remaining}] [!] {key} - Failed to fetch page tree")
        return "fail"

    flat_pages = parse_page_tree(tree_output)
    update_times = fetch_update_times(key)
    pages_tree = build_nested_tree(flat_pages, update_times)

    write_pages_yaml(key, name, pages_tree, output_file)

    with counter_lock:
        counter_value += 1
        n = counter_value
    logger.info(f"OK key={key} pages={len(flat_pages)}")
    print(f"  [{n}/{total_remaining}] {key} -> pages/{key}.yaml ({len(flat_pages)} pages)")
    return "ok"


def read_spaces_from_yaml(spaces_file):
    content = spaces_file.read_text()
    spaces = []
    current = {}

    for line in content.split("\n"):
        if line.strip().startswith("- key:"):
            if current:
                spaces.append(current)
            key = line.split('"')[1] if '"' in line else ""
            current = {"key": key}
        elif "name:" in line and current:
            current["name"] = line.split('"')[1] if '"' in line else ""
        elif "pages:" in line and current and "category" in current:
            val = line.strip().split()[-1]
            try:
                current["pages"] = int(val)
            except ValueError:
                current["pages"] = 0
        elif "category:" in line and current:
            current["category"] = line.split('"')[1] if '"' in line else ""
        elif "url:" in line and current:
            current["url"] = line.split('"')[1] if '"' in line else ""

    if current:
        spaces.append(current)

    return spaces


def main():
    parser = argparse.ArgumentParser(description="Sync Confluence spaces and page trees to YAML")
    parser.add_argument("--spaces-only", action="store_true", help="Only generate spaces.yaml")
    parser.add_argument("--pages-only", action="store_true", help="Only generate pages/*.yaml from existing spaces.yaml")
    parser.add_argument("--space", type=str, help="Sync a single space by key")
    parser.add_argument("--no-personal", action="store_true", help="Skip personal spaces")
    parser.add_argument("--concurrency", type=int, default=3, help="Number of parallel workers (default: 3)")
    args = parser.parse_args()

    PAGES_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    domain = get_confluence_domain()
    base_url = f"https://{domain}/wiki/spaces"

    global counter_value
    counter_value = 0

    # --- Mode: single space ---
    if args.space:
        key = args.space
        print(f"Syncing space [{key}]...")

        data = run_confluence_api_json(f"space/{key}")
        if not data:
            print(f"Error: Space '{key}' not found")
            sys.exit(1)

        name = data.get("name", key)
        category = fetch_space_category(key)
        pages = fetch_page_count(key)
        url = f"{base_url}/{key}"

        print(f"  Space: {name}")
        print(f"  Category: {category or '-'}")
        print(f"  Pages: {pages}")

        space_entry = {"key": key, "name": name, "category": category, "pages": pages, "url": url}

        spaces_file = OUTPUT_DIR / "spaces.yaml"
        if spaces_file.exists():
            existing = read_spaces_from_yaml(spaces_file)
            existing = [s for s in existing if s["key"] != key]
            existing.append(space_entry)
            write_spaces_yaml(existing, len(existing), spaces_file)
        else:
            write_spaces_yaml([space_entry], 1, spaces_file)
        print("  -> spaces.yaml (updated)")

        if pages > 0:
            output_file = PAGES_DIR / f"{key}.yaml"
            if output_file.exists():
                output_file.unlink()
            sync_single_space(key, name, PAGES_DIR, LOG_DIR, 1)

        print("Done.")
        return

    # --- Mode: pages only ---
    if args.pages_only:
        spaces_file = OUTPUT_DIR / "spaces.yaml"
        if not spaces_file.exists():
            print("Error: spaces.yaml not found. Run --spaces-only first.")
            sys.exit(1)

        print("Reading spaces from existing spaces.yaml...")
        spaces = read_spaces_from_yaml(spaces_file)
        work_list = [s for s in spaces if s.get("pages", 0) > 0]
        pending = [s for s in work_list if not (PAGES_DIR / f"{s['key']}.yaml").exists()]

        print(f"Total spaces with pages: {len(work_list)}")
        print(f"Already generated: {len(work_list) - len(pending)}")
        print(f"Remaining: {len(pending)}")
        print(f"Concurrency: {args.concurrency}")
        print()

        if not pending:
            print("All page trees already generated. Nothing to do.")
            return

        total_remaining = len(pending)
        with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
            futures = {
                executor.submit(sync_single_space, s["key"], s["name"], PAGES_DIR, LOG_DIR, total_remaining): s
                for s in pending
            }
            for future in as_completed(futures):
                future.result()

        final_count = len(list(PAGES_DIR.glob("*.yaml")))
        print(f"\nDone. Generated: {final_count} page tree files in {PAGES_DIR}/")
        print(f"Logs: {LOG_DIR}/")
        return

    # --- Mode: full sync ---
    print("Fetching all spaces...")
    spaces = fetch_all_spaces(skip_personal=args.no_personal)
    if not spaces:
        print("Error: Failed to fetch spaces")
        sys.exit(1)

    total = len(spaces)
    print(f"Found {total} spaces.")

    # Generate spaces.yaml
    print("Generating spaces.yaml...")
    spaces_data = []
    for i, s in enumerate(spaces, 1):
        key = s["key"]
        name = s["name"]
        category = fetch_space_category(key)
        pages = fetch_page_count(key)
        url = f"{base_url}/{key}"
        spaces_data.append({"key": key, "name": name, "category": category, "pages": pages, "url": url})
        print(f"  [{i}/{total}] {key} - {pages} pages")

    write_spaces_yaml(spaces_data, total, OUTPUT_DIR / "spaces.yaml")
    print(f"  -> spaces.yaml ({total} spaces)")

    if args.spaces_only:
        print("\nDone.")
        return

    # Sync page trees
    print(f"\nGenerating page trees (concurrency: {args.concurrency})...")
    work_list = [s for s in spaces_data if s["pages"] > 0]
    pending = [s for s in work_list if not (PAGES_DIR / f"{s['key']}.yaml").exists()]

    if not pending:
        print("All page trees already generated.")
    else:
        total_remaining = len(pending)
        with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
            futures = {
                executor.submit(sync_single_space, s["key"], s["name"], PAGES_DIR, LOG_DIR, total_remaining): s
                for s in pending
            }
            for future in as_completed(futures):
                future.result()

    print(f"\nDone. Output: {OUTPUT_DIR}/")
    print("  - spaces.yaml")
    print("  - pages/*.yaml")


if __name__ == "__main__":
    main()
