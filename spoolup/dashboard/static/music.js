/* Music page: audio status + library rendering. */
const AUDIO_API = "/api/";

function el(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined && text !== null) n.textContent = text;
  return n;
}

function renderBanners(list) {
  const box = document.getElementById("music-banners");
  if (!box) return;
  box.textContent = "";
  (list || []).slice(-5).forEach((text) => {
    box.appendChild(el("div", "banner", text));
  });
}

function renderSpotifyPanel(spotify, snap) {
  const panel = document.getElementById("spotify-panel");
  if (!panel) return;
  panel.textContent = "";
  if (!spotify) {
    panel.textContent = "Spotify status unavailable.";
    return;
  }
  const title = el("div", null, spotify.ready
    ? "Spotify ready (librespot found)"
    : "Spotify not ready");
  title.style.fontWeight = "600";
  title.style.color = spotify.ready ? "var(--ok)" : "var(--danger)";
  panel.appendChild(title);

  const lines = [];
  if (spotify.librespot_path) {
    lines.push("binary: " + spotify.librespot_path);
  }
  lines.push("device name: " + (spotify.device_name || "SpoolUp"));
  if (snap && snap.source === "spotify") {
    if (snap.source_alive === false) {
      lines.push("receiver: dead — " + (snap.source_error || "exited"));
    } else {
      lines.push("receiver: running — pick SpoolUp in Spotify and play");
    }
  }
  if (spotify.hint) lines.push(spotify.hint);
  lines.forEach((t) => panel.appendChild(el("div", null, t)));
}

async function setSource(source, extra) {
  const body = Object.assign({source: source}, extra || {});
  const r = await fetch("/api/audio/source", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(body),
  });
  const data = await r.json().catch(() => ({ok: false}));
  if (!data.ok) {
    renderBanners(["Could not queue audio change — try again in a second."]);
  }
  // Action worker drains ~1s; poll a few times so status catches up.
  for (let i = 0; i < 4; i++) {
    await new Promise((res) => setTimeout(res, 400));
    await refresh();
  }
}

async function refresh() {
  try {
    const status = await (await fetch("/api/audio/status")).json();
    const snap = status.snapshot || {};
    renderBanners(status.banners || []);
    renderSpotifyPanel(status.spotify, snap);

    const np = document.getElementById("now-playing");
    np.classList.remove("skeleton");
    np.textContent = "";
    const build = (k, v) => {
      const r = document.createElement("div");
      r.className = "row";
      const kk = document.createElement("span");
      kk.className = "k";
      kk.textContent = k;
      const vv = document.createElement("span");
      vv.className = "v np-value";
      vv.textContent = v;
      r.appendChild(kk);
      r.appendChild(vv);
      np.appendChild(r);
    };
    build("source", snap.source || "off");
    build("volume", snap.volume !== undefined ? Math.round(snap.volume * 100) + "%" : "—");
    build("connected", snap.client_connected ? "yes (in broadcast)" : "standby / not streaming");
    if (snap.source === "spotify") {
      build("spotify", snap.source_alive === false
        ? ("dead: " + (snap.source_error || "exited"))
        : "waiting for Connect / playing");
    }
    const vol = document.getElementById("volume");
    if (snap.volume !== undefined) vol.value = snap.volume;

    const btnSpotify = document.getElementById("src-spotify");
    if (btnSpotify && status.spotify) {
      btnSpotify.title = status.spotify.hint || "";
      btnSpotify.disabled = false;
    }

    const tracks = await (await fetch("/api/music/tracks")).json();
    const box = document.getElementById("tracks");
    box.textContent = "";
    if (!tracks.length) {
      const e = document.createElement("div");
      e.className = "empty";
      e.textContent = "No tracks yet — upload an mp3 to get started.";
      box.appendChild(e);
      return;
    }
    tracks.forEach((t) => {
      const item = document.createElement("div");
      item.className = "list-item";
      const name = document.createElement("span");
      name.className = "grow";
      name.textContent = t.name;
      item.appendChild(name);
      const size = document.createElement("span");
      size.className = "meta";
      size.textContent = Math.round(t.size / 1024) + " KB";
      item.appendChild(size);
      const play = document.createElement("button");
      play.className = "ghost";
      play.textContent = "Play";
      play.onclick = () => setSource("library", {track_id: t.id});
      const del = document.createElement("button");
      del.className = "ghost";
      del.textContent = "×";
      del.title = "Delete";
      del.onclick = () =>
        fetch("/api/music/tracks/" + t.id, {method: "DELETE"}).then(refresh);
      item.appendChild(play);
      item.appendChild(del);
      box.appendChild(item);
    });
  } catch (e) { /* transient */ }
}

document.getElementById("volume").addEventListener("change", (e) =>
  fetch("/api/audio/volume", {method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({volume: parseFloat(e.target.value)})}));

document.getElementById("src-silence").addEventListener("click", () => {
  const b = document.getElementById("src-silence");
  b.disabled = true;
  setSource("silence").finally(() => { b.disabled = false; });
});
document.getElementById("src-library").addEventListener("click", () => {
  const b = document.getElementById("src-library");
  b.disabled = true;
  setSource("library").finally(() => { b.disabled = false; });
});
document.getElementById("src-spotify").addEventListener("click", () => {
  const b = document.getElementById("src-spotify");
  b.disabled = true;
  setSource("spotify").finally(() => { b.disabled = false; });
});
document.getElementById("upload").addEventListener("change", async (e) => {
  const f = e.target.files[0];
  if (!f) return;
  const fd = new FormData();
  fd.append("file", f);
  await fetch("/api/music/tracks", {method: "POST", body: fd});
  refresh();
});

document.addEventListener("DOMContentLoaded", refresh);
setInterval(refresh, 4000);
