/* Music page: audio status + library rendering. */
const AUDIO_API = "/api/";

async function refresh() {
  try {
    const status = await (await fetch("/api/audio/status")).json();
    const snap = status.snapshot || {};
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
    build("connected", snap.client_connected ? "yes" : "not streaming");
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
      play.onclick = () =>
        fetch("/api/audio/source", {method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({source: "library", track_id: t.id})});
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
  fetch("/api/audio/source", {method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({source: "silence"})}).finally(() => { b.disabled = false; });
});
document.getElementById("src-library").addEventListener("click", () => {
  const b = document.getElementById("src-library");
  b.disabled = true;
  fetch("/api/audio/source", {method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({source: "library"})}).finally(() => { b.disabled = false; });
});
document.getElementById("src-spotify").addEventListener("click", () => {
  const b = document.getElementById("src-spotify");
  b.disabled = true;
  fetch("/api/audio/source", {method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({source: "spotify"})}).finally(() => { b.disabled = false; });
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
