const $ = id => document.getElementById(id);
let currentToken = "";
let currentContent = "";
let currentId = "";

const api = path => fetch(path).then(r => r.ok ? r.json() : Promise.reject());

async function create() {
  const content = $("content").value;
  if (!content.trim()) return alert("Enter some content");
  const body = JSON.stringify({
    content: content,
    language: $("lang").value
  });

  const res = await fetch("/api/pastes", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body
  });
  const json = await res.json();
  const data = json.data;

  $("link").href = data.url;
  $("link").textContent = data.url;
  $("token").textContent = data.delete_token;
  currentToken = data.delete_token;
  $("toast").classList.remove("hidden");
  $("content").value = "";
  loadRecent();
}

function copyLink() {
  navigator.clipboard.writeText($("link").href);
}

function copyToken() {
  navigator.clipboard.writeText(currentToken);
}

function copyContent() {
  navigator.clipboard.writeText(currentContent);
}

async function loadRecent() {
  const json = await api("/api/pastes?limit=10");
  const list = json.data;
  $("list").innerHTML = list.length
    ? list.map(p => `
      <div class="item" onclick="openPaste('${p.id}')">
        <div><strong>${p.id}</strong> <span style="color:var(--accent)">[${p.language}]</span></div>
        <small>${p.views} views &middot; ${new Date(p.created_at).toLocaleString()}</small>
      </div>`).join("")
    : `<p style="color:#8b949e">No pastes yet.</p>`;
}

async function openPaste(id) {
  const json = await api(`/api/pastes/${id}`);
  const p = json.data;
  currentId = p.id;
  $("m-id").textContent = p.id;
  $("m-lang").textContent = p.language;
  $("m-views").textContent = `&middot; ${p.views} views`;
  $("m-code").textContent = p.content;
  $("m-code").className = `language-${p.language}`;
  $("m-download").href = `/download/${p.id}`;
  currentContent = p.content;
  $("modal").classList.remove("hidden");
  history.replaceState(null, "", `/p/${id}`);
  hljs.highlightElement($("m-code"));
}

function closeModal(e) {
  if (e && e.target !== $("modal") && e.target.closest("button") === null && e.target.closest("a") === null) return;
  $("modal").classList.add("hidden");
  history.replaceState(null, "", "/");
}

const m = location.pathname.match(/\/p\/(.+)/);
if (m) openPaste(m[1]);
loadRecent();
