const API = "/api/";

document.querySelectorAll(".actions button[data-action]").forEach((button) => {
  button.addEventListener("click", async () => {
    await fetch(API + button.dataset.action, {"method": "POST"});
    poll();
  });
});

async function poll() {
  const snap = await (await fetch(API + "status")).json();
  const bn = document.getElementById("banners");
  if (bn) bn.textContent = (snap.banners || []).join("\n");
  const pc = document.getElementById("print-card");
  const sc = document.getElementById("stream-card");
  const sess = document.getElementById("sessions-card");
  if (pc) pc.textContent = fmt(snap.print);
  if (sc) sc.textContent = "live: " + fmt(snap.stream);
  if (sess) sess.textContent = fmtSessions(snap.sessions || []);
  if (updatesEl) renderUpdates(snap);
}

const updatesEl = document.getElementById("updates-card");
if (updatesEl) {
  const chk = document.getElementById("btn-check");
  const upd = document.getElementById("btn-update");
  if (chk) chk.onclick = async () => {
    const r = await (await fetch("/api/update/check", {method: "POST"})).json();
    renderUpdates({last_check: r});
    poll();
  };
  if (upd) upd.onclick = async () => {
    await fetch("/api/update/apply", {method: "POST"});
    poll();
  };
}

async function renderUpdates(state) {
  const u = state.update || state.last_check || {};
  const lc = state.update ? state.update.last_check : null;
  const cur = lc && lc.current ? lc.current.slice(0, 7) : "?";
  let text = "version: " + cur;
  if (lc && lc.ahead_by) text += "\n" + lc.ahead_by + " new commit(s)";
  if (lc && lc.commits && lc.commits.length)
    text += "\n" + lc.commits.slice(0, 10).map((c) => "• " + c.subject).join("\n");
  if (state.update && state.update.pending_restart)
    text += "\nRESTART PENDING — applies when the stream ends";
  updatesEl.textContent = text;
}

function fmtSessions(list) {
  if (!list.length) return "no sessions yet";
  return list.map((s) =>
    (s.filename || "?") + " — " + (s.outcome || "running") +
    (s.upload ? " | upload: " + (s.upload.ok ? "ok" : "failed") : "")
  ).join("\n");
}

function fmt(obj) {
  if (!obj || Object.keys(obj).length === 0) return "no data";
  return Object.entries(obj).map(([k, v]) => k + ": " + v).join("\n");
}

poll();
setInterval(poll, 2000);
