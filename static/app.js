const $ = id => document.getElementById(id);
const api = path => fetch(path).then(r => r.ok ? r.json() : Promise.reject());

async function create() {
  const content = $("content").value;
  if (!content.trim()) return alert("Enter some content");
  const fd = new FormData();
  fd.append("content", content);
  fd.append("language", $("lang").value);

  const res = await fetch("/api/pastes", { method: "POST", body: fd });
  const data = await res.json();

  const url = `${location.origin}/p/${data.id}`;
  $("link").href = url;
  $("link").textContent = url;
  $("toast").classList.remove("hidden");
  $("content").value = "";
  loadRecent();
}

function copyLink() {
  navigator.clipboard.writeText($("link").href);
}

async function loadRecent() {
  const list = await api("/api/pastes?limit=10");
  $("list").innerHTML = list.length
    ? list.map(p => `
      <div class="item" onclick="openPaste('${p.id}')">
        <div><strong>${p.id}</strong> <span style="color:var(--accent)">[${p.language}]</span></div>
        <small>${new Date(p.created_at).toLocaleString()}</small>
      </div>`).join("")
    : `<p style="color:#8b949e">No pastes yet.</p>`;
}

async function openPaste(id) {
  const p = await api(`/api/pastes/${id}`);
  $("m-id").textContent = p.id;
  $("m-lang").textContent = p.language;
  $("m-code").textContent = p.content;
  $("modal").classList.remove("hidden");
  history.replaceState(null, "", `/p/${id}`);
}

function closeModal(e) {
  if (e && e.target !== $("modal") && e.target.closest("button") === null) return;
  $("modal").classList.add("hidden");
  history.replaceState(null, "", "/");
}

// Open paste if URL is /p/xxx
const m = location.pathname.match(/\/p\/(.+)/);
if (m) openPaste(m[1]);
loadRecent();
