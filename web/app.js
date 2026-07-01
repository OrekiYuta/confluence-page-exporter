"use strict";

/* ---------------------------------------------------------------------------
 * Confluence Page Explorer — front-end
 *
 * Reads web/data/*.json (produced by scripts/build_web_data.py) at runtime.
 * After updating source-states and rebuilding, just refresh the browser.
 * ------------------------------------------------------------------------- */

const DATA_BASE = "data";

const state = {
  spaces: [],            // space index from spaces.json
  currentSpaceKey: null,
  tree: [],              // nested page tree of the current space
  pageIndex: new Map(),  // id -> { node, parentId }
  activePageId: null,
};

/* ---------- DOM refs ---------- */
const el = {
  sidebar: document.getElementById("sidebar"),
  sidebarToggle: document.getElementById("sidebar-toggle"),
  spaceSearch: document.getElementById("space-search"),
  spaceResults: document.getElementById("space-results"),
  spaceBadge: document.getElementById("space-badge"),
  sidebarSpaceName: document.getElementById("sidebar-space-name"),
  sidebarSpaceMeta: document.getElementById("sidebar-space-meta"),
  treeFilter: document.getElementById("tree-filter"),
  tree: document.getElementById("tree"),
  welcome: document.getElementById("welcome"),
  stats: document.getElementById("stats"),
  content: document.getElementById("content"),
  pageView: document.getElementById("page-view"),
  breadcrumb: document.getElementById("breadcrumb"),
  pageTitle: document.getElementById("page-title"),
  pageMeta: document.getElementById("page-meta"),
  pageSourceLink: document.getElementById("page-source-link"),
  childList: document.getElementById("child-list"),
};

/* ---------- Utilities ---------- */
function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function highlight(text, query) {
  if (!query) return escapeHtml(text);
  const idx = text.toLowerCase().indexOf(query.toLowerCase());
  if (idx === -1) return escapeHtml(text);
  return (
    escapeHtml(text.slice(0, idx)) +
    "<mark>" +
    escapeHtml(text.slice(idx, idx + query.length)) +
    "</mark>" +
    escapeHtml(text.slice(idx + query.length))
  );
}

function formatDate(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

async function fetchJson(path) {
  const res = await fetch(path, { cache: "no-store" });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} — ${path}`);
  return res.json();
}

/* ---------- Boot ---------- */
async function boot() {
  try {
    const data = await fetchJson(`${DATA_BASE}/spaces.json`);
    state.spaces = data.spaces || [];
    renderStats(data);
  } catch (err) {
    el.stats.innerHTML =
      `<div class="stat-card"><div class="num">!</div>` +
      `<div class="label">Failed to load data.<br>Run the build script and serve over http.</div></div>`;
    console.error(err);
    return;
  }

  const hash = parseHash();
  if (hash.space) {
    await selectSpace(hash.space, { silent: true });
    if (hash.page) showPage(hash.page);
  }
}

function renderStats(data) {
  const withTree = data.with_tree ?? state.spaces.filter((s) => s.has_tree).length;
  el.stats.innerHTML = `
    <div class="stat-card"><div class="num">${data.total ?? state.spaces.length}</div><div class="label">Total spaces</div></div>
    <div class="stat-card"><div class="num">${withTree}</div><div class="label">Spaces with page tree</div></div>
  `;
}

/* ---------- Space search / picker ---------- */
let highlightedIdx = -1;

function renderSpaceResults(query) {
  const q = query.trim().toLowerCase();
  let matches;
  if (!q) {
    matches = state.spaces.slice(0, 50);
  } else {
    matches = state.spaces.filter(
      (s) =>
        s.key.toLowerCase().includes(q) ||
        s.name.toLowerCase().includes(q) ||
        (s.category || "").toLowerCase().includes(q)
    );
    // Spaces with a tree first, then by name.
    matches.sort((a, b) => (b.has_tree - a.has_tree));
    matches = matches.slice(0, 50);
  }

  if (matches.length === 0) {
    el.spaceResults.innerHTML = `<li class="sr-empty">No matching spaces</li>`;
    el.spaceResults.hidden = false;
    return;
  }

  el.spaceResults.innerHTML = matches
    .map((s, i) => {
      const treeTag = s.has_tree
        ? `<span>page tree ✓</span>`
        : `<span class="sr-no-tree">no tree yet</span>`;
      return `
      <li data-key="${escapeHtml(s.key)}" data-idx="${i}">
        <span class="sr-name">${highlight(s.name, q)}</span>
        <span class="sr-meta">
          <span class="sr-key">${highlight(s.key, q)}</span>
          <span>${s.pages} pages</span>
          ${treeTag}
        </span>
      </li>`;
    })
    .join("");
  el.spaceResults.hidden = false;
  highlightedIdx = -1;
}

el.spaceSearch.addEventListener("input", (e) => renderSpaceResults(e.target.value));
el.spaceSearch.addEventListener("focus", (e) => renderSpaceResults(e.target.value));

el.spaceSearch.addEventListener("keydown", (e) => {
  const items = Array.from(el.spaceResults.querySelectorAll("li[data-key]"));
  if (e.key === "ArrowDown") {
    e.preventDefault();
    highlightedIdx = Math.min(highlightedIdx + 1, items.length - 1);
  } else if (e.key === "ArrowUp") {
    e.preventDefault();
    highlightedIdx = Math.max(highlightedIdx - 1, 0);
  } else if (e.key === "Enter") {
    e.preventDefault();
    const target = highlightedIdx >= 0 ? items[highlightedIdx] : items[0];
    if (target) selectSpace(target.dataset.key);
    return;
  } else if (e.key === "Escape") {
    el.spaceResults.hidden = true;
    return;
  } else {
    return;
  }
  items.forEach((it, i) => it.classList.toggle("highlighted", i === highlightedIdx));
  if (items[highlightedIdx]) items[highlightedIdx].scrollIntoView({ block: "nearest" });
});

el.spaceResults.addEventListener("click", (e) => {
  const li = e.target.closest("li[data-key]");
  if (li) selectSpace(li.dataset.key);
});

document.addEventListener("click", (e) => {
  if (!e.target.closest(".space-picker")) el.spaceResults.hidden = true;
});

/* ---------- Load a space ---------- */
async function selectSpace(key, opts = {}) {
  const meta = state.spaces.find((s) => s.key === key);
  if (!meta) return;

  el.spaceResults.hidden = true;
  el.spaceSearch.value = "";
  el.spaceBadge.hidden = false;
  el.spaceBadge.textContent = `${key} · ${meta.pages} pages`;
  el.sidebarSpaceName.textContent = meta.name;
  el.sidebarSpaceMeta.textContent =
    [meta.category, `${meta.pages} pages`].filter(Boolean).join(" · ");

  state.currentSpaceKey = key;
  state.activePageId = null;

  if (!meta.has_tree) {
    state.tree = [];
    state.pageIndex = new Map();
    el.treeFilter.hidden = true;
    el.tree.innerHTML =
      `<div class="tree-empty">No page tree data for this space yet.<br><br>` +
      `Generate it with:<br><code>python3 scripts/sync_source_states.py --space ${escapeHtml(key)}</code><br>` +
      `then<br><code>python3 scripts/build_web_data.py --space ${escapeHtml(key)}</code></div>`;
    showWelcomeForSpace(meta);
    if (!opts.silent) updateHash();
    return;
  }

  el.tree.innerHTML = `<div class="tree-empty">Loading page tree&hellip;</div>`;
  try {
    const data = await fetchJson(`${DATA_BASE}/pages/${encodeURIComponent(key)}.json`);
    state.tree = data.pages || [];
  } catch (err) {
    el.tree.innerHTML = `<div class="tree-empty">Failed to load page tree.</div>`;
    console.error(err);
    return;
  }

  buildPageIndex();
  el.treeFilter.hidden = false;
  el.treeFilter.value = "";
  renderTree();
  showWelcomeForSpace(meta);

  if (!opts.silent) updateHash();

  // Auto-open the first top-level page for convenience.
  if (state.tree.length > 0) showPage(state.tree[0].id);
}

function showWelcomeForSpace(meta) {
  // Keep welcome hidden once a space is loaded; page view takes over.
  el.welcome.hidden = true;
  el.pageView.hidden = false;
}

/* ---------- Page index (id -> node, parent) ---------- */
function buildPageIndex() {
  const index = new Map();
  function walk(nodes, parentId) {
    for (const node of nodes) {
      index.set(node.id, { node, parentId });
      if (node.children && node.children.length) walk(node.children, node.id);
    }
  }
  walk(state.tree, null);
  state.pageIndex = index;
}

/* ---------- Tree rendering ---------- */
function renderTree(filterText) {
  const filter = (filterText || "").trim().toLowerCase();

  if (state.tree.length === 0) {
    el.tree.innerHTML = `<div class="tree-empty">This space has no pages.</div>`;
    return;
  }

  const rootUl = document.createElement("ul");
  const anyMatch = renderNodes(state.tree, rootUl, filter);

  el.tree.innerHTML = "";
  if (filter && !anyMatch) {
    el.tree.innerHTML = `<div class="tree-empty">No pages match "${escapeHtml(filterText)}".</div>`;
    return;
  }
  el.tree.appendChild(rootUl);

  if (state.activePageId) markActive(state.activePageId);
}

/**
 * Returns true if this subtree contains a node matching the filter (so parents
 * can auto-expand). When no filter, always renders and returns false.
 */
function renderNodes(nodes, parentUl, filter) {
  let subtreeMatched = false;

  for (const node of nodes) {
    const hasChildren = node.children && node.children.length > 0;
    const selfMatch = filter && node.title.toLowerCase().includes(filter);

    // Recurse first to know whether descendants match.
    const childUl = document.createElement("ul");
    childUl.className = "children";
    const childMatched = hasChildren ? renderNodes(node.children, childUl, filter) : false;

    if (filter && !selfMatch && !childMatched) {
      continue; // prune non-matching branch
    }

    subtreeMatched = subtreeMatched || selfMatch || childMatched;

    const li = document.createElement("li");
    li.dataset.id = node.id;

    const row = document.createElement("div");
    row.className = "node-row";
    row.dataset.id = node.id;

    const toggle = document.createElement("span");
    toggle.className = "toggle" + (hasChildren ? "" : " empty");
    toggle.textContent = "▶";

    const icon = document.createElement("span");
    icon.className = "node-icon";
    icon.textContent = hasChildren ? "📁" : "📄";

    const title = document.createElement("span");
    title.className = "node-title";
    title.innerHTML = filter ? highlight(node.title, filter) : escapeHtml(node.title);
    title.title = node.title;

    row.appendChild(toggle);
    row.appendChild(icon);
    row.appendChild(title);
    li.appendChild(row);

    if (hasChildren) {
      li.appendChild(childUl);
      // Auto-expand when filtering (to reveal matches).
      if (filter && childMatched) {
        li.classList.add("open");
        row.classList.add("expanded");
      }
      toggle.addEventListener("click", (e) => {
        e.stopPropagation();
        toggleNode(li, row);
      });
    }

    row.addEventListener("click", () => {
      showPage(node.id);
      if (hasChildren && !li.classList.contains("open")) toggleNode(li, row);
    });

    parentUl.appendChild(li);
  }

  return subtreeMatched;
}

function toggleNode(li, row) {
  const open = li.classList.toggle("open");
  row.classList.toggle("expanded", open);
}

el.treeFilter.addEventListener("input", (e) => renderTree(e.target.value));

/* ---------- Show a page ---------- */
function showPage(pageId) {
  const entry = state.pageIndex.get(pageId);
  if (!entry) return;
  const { node } = entry;

  state.activePageId = pageId;
  el.welcome.hidden = true;
  el.pageView.hidden = false;

  // Breadcrumb
  const path = [];
  let cur = pageId;
  while (cur != null) {
    const e = state.pageIndex.get(cur);
    if (!e) break;
    path.unshift(e.node);
    cur = e.parentId;
  }
  el.breadcrumb.innerHTML = path
    .map((n, i) => {
      const isCurrent = i === path.length - 1;
      const crumb = `<span class="crumb ${isCurrent ? "current" : ""}" data-id="${escapeHtml(
        n.id
      )}">${escapeHtml(n.title)}</span>`;
      return isCurrent ? crumb : crumb + `<span class="sep">/</span>`;
    })
    .join("");

  el.pageTitle.textContent = node.title;

  const childCount = node.children ? node.children.length : 0;
  el.pageMeta.innerHTML = `
    <span class="meta-item"><strong>ID:</strong> ${escapeHtml(node.id)}</span>
    <span class="meta-item"><strong>Last updated:</strong> ${formatDate(node.last_updated)}</span>
    <span class="meta-item"><strong>Child pages:</strong> ${childCount}</span>
  `;

  el.pageSourceLink.href = node.url || "#";
  if (!node.url) el.pageSourceLink.style.display = "none";
  else el.pageSourceLink.style.display = "inline-block";

  // Child list
  if (childCount > 0) {
    el.childList.innerHTML =
      `<h2>Child pages (${childCount})</h2><ul>` +
      node.children
        .map((c) => {
          const cc = c.children ? c.children.length : 0;
          return `<li data-id="${escapeHtml(c.id)}">📄 ${escapeHtml(c.title)}${
            cc ? ` <span class="child-count">(${cc})</span>` : ""
          }</li>`;
        })
        .join("") +
      `</ul>`;
  } else {
    el.childList.innerHTML = "";
  }

  markActive(pageId);
  expandToPage(pageId);
  updateHash();
  el.content.scrollTop = 0;
}

el.breadcrumb.addEventListener("click", (e) => {
  const c = e.target.closest(".crumb[data-id]");
  if (c && !c.classList.contains("current")) showPage(c.dataset.id);
});

el.childList.addEventListener("click", (e) => {
  const li = e.target.closest("li[data-id]");
  if (li) showPage(li.dataset.id);
});

function markActive(pageId) {
  el.tree.querySelectorAll(".node-row.active").forEach((r) => r.classList.remove("active"));
  const row = el.tree.querySelector(`.node-row[data-id="${cssEscape(pageId)}"]`);
  if (row) {
    row.classList.add("active");
    row.scrollIntoView({ block: "nearest" });
  }
}

function expandToPage(pageId) {
  // Walk up the parent chain and open each ancestor <li>.
  let cur = pageId;
  const chain = [];
  while (cur != null) {
    const e = state.pageIndex.get(cur);
    if (!e) break;
    chain.push(cur);
    cur = e.parentId;
  }
  for (const id of chain) {
    const li = el.tree.querySelector(`li[data-id="${cssEscape(id)}"]`);
    if (li && li.querySelector(":scope > ul.children")) {
      li.classList.add("open");
      const row = li.querySelector(":scope > .node-row");
      if (row) row.classList.add("expanded");
    }
  }
}

function cssEscape(s) {
  if (window.CSS && CSS.escape) return CSS.escape(s);
  return String(s).replace(/[^a-zA-Z0-9_-]/g, "\\$&");
}

/* ---------- Sidebar toggle ---------- */
el.sidebarToggle.addEventListener("click", () => {
  el.sidebar.classList.toggle("collapsed");
});

/* ---------- Deep-link via hash (#space/PAGEID) ---------- */
function updateHash() {
  let h = "";
  if (state.currentSpaceKey) {
    h = "#" + encodeURIComponent(state.currentSpaceKey);
    if (state.activePageId) h += "/" + encodeURIComponent(state.activePageId);
  }
  if (location.hash !== h) history.replaceState(null, "", h || location.pathname);
}

function parseHash() {
  const raw = location.hash.replace(/^#/, "");
  if (!raw) return {};
  const [space, page] = raw.split("/");
  return {
    space: space ? decodeURIComponent(space) : null,
    page: page ? decodeURIComponent(page) : null,
  };
}

boot();
