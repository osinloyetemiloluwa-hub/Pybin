// PyBin - Simple Pastebin JS (no frameworks)

const $ = (id) => document.getElementById(id);
let currentPasteId = null;
let currentPasteData = null;

// ─── Toast ──────────────────────────────────────────────────────────────────
function toast(msg, isError = false) {
  const t = $("toast");
  t.textContent = msg;
  t.className = "toast show" + (isError ? " error" : "");
  setTimeout(() => (t.className = "toast"), 3000);
}

// ─── View switching ─────────────────────────────────────────────────────────
function show(id) {
  ["create-view", "result-view", "view-view", "edit-view", "recent-view"].forEach((v) =>
    $(v).classList.add("hidden")
  );
  $(id).classList.remove("hidden");
  window.scrollTo(0, 0);
}

function showCreate() {
  show("create-view");
  history.pushState({}, "", "/");
}

function showView() {
  show("view-view");
}

function showRecent() {
  show("recent-view");
  loadRecent();
}

// ─── Create paste ───────────────────────────────────────────────────────────
async function createPaste() {
  const content = $("content").value;
  if (!content.trim()) {
    toast("Please enter some content", true);
    return;
  }

  const btn = $("create-btn");
  btn.textContent = "Creating...";
  btn.disabled = true;

  try {
    const res = await fetch("/api/paste", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        content: content,
        syntax: $("syntax").value,
        title: $("title").value,
        expires: $("expires").value,
      }),
    });

    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Failed to create paste");

    // Save token to localStorage
    saveToken(data.id, data.token);

    // Show result
    const fullUrl = window.location.origin + data.url;
    $("paste-url").value = fullUrl;
    $("paste-token").value = data.token;
    $("view-link").href = data.url;
    show("result-view");

    // Reset form
    $("content").value = "";
    $("title").value = "";
    toast("Paste created!");
  } catch (err) {
    toast(err.message, true);
  } finally {
    btn.textContent = "Create Paste";
    btn.disabled = false;
  }
}

// ─── View paste ─────────────────────────────────────────────────────────────
async function loadPaste(id) {
  try {
    const res = await fetch("/api/paste/" + encodeURIComponent(id));
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Paste not found");

    currentPasteId = id;
    currentPasteData = data;

    $("view-title").textContent = data.title || "Untitled";
    $("view-content").textContent = data.content;
    $("raw-link").href = "/raw/" + id;

    const expires = data.expires ? new Date(data.expires).toLocaleString() : "Never";
    $("view-meta").textContent =
      `ID: ${id} | Syntax: ${data.syntax} | Views: ${data.views} | Created: ${new Date(data.created).toLocaleString()} | Expires: ${expires}`;

    show("view-view");
    history.pushState({ paste: id }, "", "/p/" + id);
  } catch (err) {
    toast(err.message, true);
    showCreate();
  }
}

// ─── Edit paste ─────────────────────────────────────────────────────────────
function editCurrentPaste() {
  if (!currentPasteData) return;
  const token = getToken(currentPasteId) || prompt("Enter your edit token:");
  if (!token) return;

  $("edit-token").value = token;
  $("edit-title").value = currentPasteData.title || "";
  $("edit-content").value = currentPasteData.content;
  $("edit-expires").value = "never";
  show("edit-view");
}

async function saveEdit() {
  const token = $("edit-token").value.trim();
  if (!token) {
    toast("Token is required", true);
    return;
  }

  try {
    const res = await fetch("/api/paste/" + encodeURIComponent(currentPasteId), {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
        "X-Token": token,
      },
      body: JSON.stringify({
        content: $("edit-content").value,
        title: $("edit-title").value,
        syntax: currentPasteData.syntax,
        expires: $("edit-expires").value,
      }),
    });

    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Update failed");

    saveToken(currentPasteId, token);
    toast("Paste updated!");
    loadPaste(currentPasteId);
  } catch (err) {
    toast(err.message, true);
  }
}

// ─── Delete paste ───────────────────────────────────────────────────────────
async function deleteCurrentPaste() {
  if (!currentPasteId) return;
  const token = getToken(currentPasteId) || prompt("Enter your delete token:");
  if (!token) return;
  if (!confirm("Delete this paste? This cannot be undone.")) return;

  try {
    const res = await fetch("/api/paste/" + encodeURIComponent(currentPasteId), {
      method: "DELETE",
      headers: { "X-Token": token },
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Delete failed");

    removeToken(currentPasteId);
    toast("Paste deleted");
    showCreate();
  } catch (err) {
    toast(err.message, true);
  }
}

// ─── Recent pastes ──────────────────────────────────────────────────────────
async function loadRecent() {
  try {
    const res = await fetch("/api/recent");
    const data = await res.json();
    const list = $("recent-list");

    if (!data.length) {
      list.innerHTML = '<p style="color:#888;padding:20px;text-align:center;">No pastes yet</p>';
      return;
    }

    list.innerHTML = data
      .map(
        (p) => `
      <div class="recent-item" onclick="loadPaste('${p.id}')">
        <div>
          <div class="recent-title">${escapeHtml(p.title || "Untitled")}</div>
          <div class="recent-meta">${p.syntax} | ${p.views} views | ${p.expires ? "Expires: " + new Date(p.expires).toLocaleDateString() : "Never expires"}</div>
        </div>
        <span style="color:#e74c3c;font-family:monospace;">${p.id}</span>
      </div>`
      )
      .join("");
  } catch (err) {
    toast("Failed to load recent pastes", true);
  }
}

// ─── Token storage (localStorage) ───────────────────────────────────────────
function saveToken(id, token) {
  try {
    const tokens = JSON.parse(localStorage.getItem("pybin_tokens") || "{}");
    tokens[id] = token;
    localStorage.setItem("pybin_tokens", JSON.stringify(tokens));
  } catch {}
}
function getToken(id) {
  try {
    const tokens = JSON.parse(localStorage.getItem("pybin_tokens") || "{}");
    return tokens[id] || "";
  } catch {
    return "";
  }
}
function removeToken(id) {
  try {
    const tokens = JSON.parse(localStorage.getItem("pybin_tokens") || "{}");
    delete tokens[id];
    localStorage.setItem("pybin_tokens", JSON.stringify(tokens));
  } catch {}
}

// ─── Helpers ────────────────────────────────────────────────────────────────
function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

function copyUrl() {
  $("paste-url").select();
  navigator.clipboard.writeText($("paste-url").value).then(() => toast("URL copied!"));
}

function copyToken() {
  $("paste-token").select();
  navigator.clipboard.writeText($("paste-token").value).then(() => toast("Token copied!"));
}

// ─── Init ───────────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  // Check if we're on a paste page (/p/XXXX)
  const match = window.location.pathname.match(/^\/p\/([a-zA-Z0-9]+)$/);
  if (match) {
    loadPaste(match[1]);
  }

  // Ctrl+Enter to create
  $("content").addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") createPaste();
  });
});

// Handle back button
window.addEventListener("popstate", () => {
  const match = window.location.pathname.match(/^\/p\/([a-zA-Z0-9]+)$/);
  if (match) loadPaste(match[1]);
  else showCreate();
});
