/* SpoolUp dashboard: status polling + structured renderers. */
const API = "/api/";

/* ---------- small helpers ---------- */

function el(tag, cls, text) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== undefined) node.textContent = text;
  return node;
}

function rows(pairs) {
  const wrap = el("div", "rows");
  pairs.forEach(([k, v]) => {
    if (v === null || v === undefined || v === "") return;
    const r = el("div", "row");
    r.appendChild(el("span", "k", k));
    r.appendChild(el("span", "v", String(v)));
    wrap.appendChild(r);
  });
  return wrap;
}

function chip(label, state) {
  // state: live | idle | warn | bad
  return el("span", "chip " + state, label);
}

function rowPair(k, value, chipState) {
  const r = el("div", "row");
  r.appendChild(el("span", "k", k));
  const v = el("span", "v");
  if (chipState) v.appendChild(chip(String(value), chipState));
  else if (value !== null && value !== undefined) v.textContent = String(value);
  else v.textContent = "—";
  r.appendChild(v);
  return r;
}

function clearSkeleton(card) {
  const skel = card.querySelector(".skeleton");
  if (skel) skel.remove();
  const old = card.querySelector(".card-body");
  if (old) old.remove();
}

/* ---------- print card ---------- */

function renderPrint(card, p) {
  clearSkeleton(card);
  const head = el("div", "card-body rows");
  head.appendChild(rows([
    ["job", p.filename && p.filename !== "Unknown" ? p.filename : null],
    ["state", p.state],
    ["progress", p.progress !== undefined
        ? (p.progress * 100).toFixed(1) + "%" : null],
    ["layer", (p.current_layer !== undefined && p.total_layers)
        ? p.current_layer + " / " + p.total_layers : null],
    ["nozzle", p.extruder_temp_str],
    ["bed", p.bed_temp_str],
    ["eta", p.estimate],
  ]));
  if (head.textContent.trim() === "") {
    head.appendChild(el("div", "empty",
        "No print data — connect Moonraker in Settings."));
  }
  card.appendChild(head);
}

/* ---------- stream card ---------- */

function chipRow(k, value, chipState) {
  const r = el("div", "row");
  r.appendChild(el("span", "k", k));
  const v = el("span", "v");
  v.appendChild(chip(String(value), chipState));
  r.appendChild(v);
  return r;
}

function renderStream(card, s) {
  clearSkeleton(card);
  const head = el("div");
  head.style.cssText =
      "display:flex;align-items:center;gap:10px;margin-bottom:12px;";
  head.appendChild(el("h2", null, s.is_streaming ? "Live" : "Standby"));
  head.appendChild(chip(s.is_streaming ? "LIVE" : "IDLE",
      s.is_streaming ? "live" : "idle"));

  const body = el("div", "card-body");
  if (s.watch_url) {
    const r = el("div", "row");
    r.appendChild(el("span", "k", "watch"));
    const v = el("span", "v");
    const a = el("a", null, "open broadcast");
    a.href = s.watch_url;
    a.target = "_blank";
    a.rel = "noopener";
    v.appendChild(a);
    r.appendChild(v);
    body.appendChild(r);
  }
  const sinks = s.sinks || {};
  const yt = sinks.youtube || null;
  if (yt) {
    body.appendChild(rowPair("youtube",
        yt.up ? (yt.health || "up") : "down",
        yt.up ? "ok" : "bad"));
  }
  const kick = sinks.kick || null;
  if (kick) {
    const label = kick.up ? "receiving"
        : kick.configured ? "idle" : "not configured";
    body.appendChild(rowPair("kick", label, kick.up ? "ok" : "idle"));
  }
  if (s.pump && s.pump.read_rate !== null && s.pump.read_rate !== undefined) {
    body.appendChild(rowPair("webcam feed",
        s.pump.read_rate.toFixed(1) + " fps", null));
  }
  body.prepend(head);
  card.appendChild(body);
}

/* ---------- sessions card ---------- */

function renderSessions(card, list) {
  clearSkeleton(card);
  if (!list.length) {
    card.appendChild(el("div", "card-body empty",
        "No prints yet — sessions appear here while you're away."));
    return;
  }
  const box = el("div", "list card-body");
  list.slice(0, 8).forEach((s) => {
    const item = el("div", "list-item");
    item.appendChild(el("span", "grow", s.filename || "?"));
    const outcome = s.outcome || "running";
    item.appendChild(chip(outcome,
        outcome === "complete" ? "live"
        : outcome === "cancelled" ? "bad" : "warn"));
    if (s.upload) {
      item.appendChild(chip(s.upload.ok ? "upload ok" : "upload failed",
          s.upload.ok ? "live" : "bad"));
    }
    box.appendChild(item);
  });
  card.appendChild(box);
}

/* ---------- updates card ---------- */

const updatesEl = document.getElementById("updates-card");

function renderUpdates(state) {
  clearSkeleton(updatesEl);
  const lc = state.update ? state.update.last_check : state.last_check;
  const body = el("div", "card-body rows");

  body.appendChild(rowPair("running version",
      lc && lc.current ? lc.current.slice(0, 7) : "unknown", null));

  if (lc && lc.ahead_by) {
    body.appendChild(chipRow("available now", lc.ahead_by + " new", "warn"));
    (lc.commits || []).slice(0, 6).forEach((c) => {
      body.appendChild(rowPair(c.hash,
          c.subject.length > 44 ? c.subject.slice(0, 42) + "…" : c.subject, null));
    });
  } else {
    body.appendChild(el("div", "empty", "Up to date."));
  }
  if (state.update && state.update.pending_restart) {
    body.appendChild(el("div", "banner",
        "Restart pending — applies when the stream ends."));
  }
  updatesEl.appendChild(body);
}

const btnCheck = document.getElementById("btn-check");
const btnUpdate = document.getElementById("btn-update");
if (btnCheck) btnCheck.addEventListener("click", async () => {
  btnCheck.disabled = true;
  try {
    await fetch("/api/update/check", {"method": "POST"});
    await poll();
  } finally {
    btnCheck.disabled = false;
  }
});
if (btnUpdate) btnUpdate.addEventListener("click", async () => {
  btnUpdate.disabled = true;
  try {
    await fetch("/api/update/apply", {"method": "POST"});
    await poll();
  } finally {
    btnUpdate.disabled = false;
  }
});

/* ---------- banners ---------- */

function renderBanners(list) {
  const bn = document.getElementById("banners");
  if (!bn) return;
  bn.innerHTML = "";
  (list || []).forEach((text) => bn.appendChild(el("div", "banner", text)));
}

/* ---------- polling ---------- */

async function poll() {
  let snap;
  try {
    const resp = await fetch(API + "status");
    if (!resp.ok) return;
    snap = await resp.json();
  } catch (e) {
    return;  // transient; the next tick retries and skeletons remain
  }
  renderBanners(snap.banners || []);
  const pc = document.getElementById("print-card");
  const sc = document.getElementById("stream-card");
  const sess = document.getElementById("sessions-card");
  if (pc) renderPrint(pc, snap.print || {});
  if (sc) renderStream(sc, snap.stream || {});
  if (sess) renderSessions(sess, snap.sessions || []);
  if (updatesEl) renderUpdates(snap);
}

poll();
setInterval(poll, 2000);
