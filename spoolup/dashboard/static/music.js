/* Music page: audio status + library rendering. */

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

function setActiveSourceButton(source) {
  ["silence", "library", "spotify"].forEach((name) => {
    const b = document.getElementById("src-" + name);
    if (!b) return;
    const on = source === name || (name === "library" && source && source.indexOf("file:") === 0);
    b.classList.toggle("primary", on);
    b.classList.toggle("ghost", !on);
  });
}

function renderSpotifyCallout(spotify, snap, streaming) {
  const box = document.getElementById("spotify-callout");
  if (!box) return;
  if (!spotify || !spotify.active) {
    box.hidden = true;
    box.textContent = "";
    return;
  }
  box.hidden = false;
  box.textContent = "";
  if (spotify.receiver_alive === false) {
    box.appendChild(el("div", null,
      "Spotify receiver died. " + (spotify.next_step || "")));
    return;
  }
  const device = spotify.device_name || "SpoolUp";
  const port = spotify.zeroconf_port || 24879;
  box.appendChild(el("div", null,
    streaming
      ? ("Spotify receiver is up as \"" + device + "\" (port " + port +
         "). Cast from the Spotify app → Devices → " + device +
         ". Audio goes to YouTube/Kick, not PC speakers.")
      : ("Spotify receiver is up as \"" + device + "\" (port " + port +
         "), but Spotify only finds it on the LAN. Same Wi‑Fi, no VPN, then " +
         "Devices → " + device + ". No PC speaker playback — livestream only.")));

  const tips = spotify.discovery_tips || [];
  if (tips.length) {
    const ul = document.createElement("ul");
    ul.style.margin = "8px 0 0";
    ul.style.paddingLeft = "18px";
    tips.forEach((t) => {
      const li = document.createElement("li");
      li.textContent = t;
      ul.appendChild(li);
    });
    box.appendChild(ul);
  }
  if (spotify.firewall_cmd) {
    box.appendChild(el("div", null,
      "Admin PowerShell (one time) to allow discovery:"));
    const code = document.createElement("code");
    code.style.display = "block";
    code.style.marginTop = "6px";
    code.style.whiteSpace = "pre-wrap";
    code.style.wordBreak = "break-all";
    code.textContent = spotify.firewall_cmd;
    box.appendChild(code);
  }
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
    ? (spotify.active
        ? (spotify.receiver_alive === false
            ? "Spotify selected — receiver dead"
            : "Spotify selected — receiver running")
        : "librespot found — press Spotify to start")
    : "Spotify not ready");
  title.style.fontWeight = "600";
  title.style.color = (!spotify.ready || spotify.receiver_alive === false)
    ? "var(--danger)"
    : "var(--ok)";
  panel.appendChild(title);

  const lines = [];
  if (spotify.librespot_path) {
    lines.push("binary: " + spotify.librespot_path);
  }
  lines.push("device name: " + (spotify.device_name || "SpoolUp"));
  if (spotify.zeroconf_port) {
    lines.push("Connect port: " + spotify.zeroconf_port);
  }
  lines.push("PC speakers: no (broadcast mix only)");
  if (spotify.next_step) lines.push("next: " + spotify.next_step);
  lines.forEach((t) => panel.appendChild(el("div", null, t)));
}

async function setSource(source, extra) {
  const body = Object.assign({source: source}, extra || {});
  if (source === "spotify") {
    renderBanners(["Starting Spotify Connect receiver…"]);
    const callout = document.getElementById("spotify-callout");
    if (callout) {
      callout.hidden = false;
      callout.textContent =
        "Starting receiver… then cast from the Spotify app to \"SpoolUp\". " +
        "Audio is for the livestream only.";
    }
  }
  const r = await fetch("/api/audio/source", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(body),
  });
  const data = await r.json().catch(() => ({ok: false}));
  if (!data.ok) {
    renderBanners(["Could not queue audio change — try again in a second."]);
    return;
  }
  for (let i = 0; i < 8; i++) {
    await new Promise((res) => setTimeout(res, 400));
    await refresh();
  }
}

async function refresh() {
  try {
    const status = await (await fetch("/api/audio/status")).json();
    const snap = status.snapshot || {};
    const spotify = status.spotify || null;
    renderBanners(status.banners || []);
    renderSpotifyCallout(spotify, snap, !!status.streaming);
    renderSpotifyPanel(spotify, snap);
    setActiveSourceButton(snap.source || "silence");

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
    build("livestream", status.streaming
      ? (snap.client_connected ? "encoding (audio linked)" : "encoding")
      : "not streaming — Spotify won't be audible yet");
    if (snap.source === "spotify") {
      let spotifyState = "receiver up — cast from Spotify app";
      if (snap.source_alive === false) {
        spotifyState = "dead: " + (snap.source_error || "exited");
      } else if (snap.receiving_pcm) {
        spotifyState = "receiving audio from Spotify";
      }
      build("spotify", spotifyState);
    }
    const vol = document.getElementById("volume");
    if (snap.volume !== undefined) vol.value = snap.volume;

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
