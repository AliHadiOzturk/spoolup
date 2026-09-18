async function refresh() {
  const status = await (await fetch("/api/audio/status")).json();
  const snap = status.snapshot || {};
  document.getElementById("now-playing").textContent =
      "source: " + (snap.source || "off") + "\nvolume: " +
      (snap.volume ?? "-") + "\nconnected: " + (snap.client_connected ?? "-");
  const vol = document.getElementById("volume");
  if (snap.volume !== undefined) vol.value = snap.volume;
  const tracks = await (await fetch("/api/music/tracks")).json();
  const ul = document.getElementById("tracks");
  ul.innerHTML = "";
  tracks.forEach((t) => {
    const li = document.createElement("li");
    li.textContent = t.name + " ";
    const play = document.createElement("button");
    play.textContent = "Play";
    play.onclick = () =>
      fetch("/api/audio/source", {method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({source: "library", track_id: t.id})});
    const del = document.createElement("button");
    del.textContent = "Delete";
    del.onclick = () =>
      fetch("/api/music/tracks/" + t.id, {method: "DELETE"}).then(refresh);
    li.appendChild(play); li.appendChild(del);
    ul.appendChild(li);
  });
}
document.getElementById("volume").onchange = (e) =>
  fetch("/api/audio/volume", {method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({volume: parseFloat(e.target.value)})});
document.getElementById("src-silence").onclick = () =>
  fetch("/api/audio/source", {method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({source: "silence"})});
document.getElementById("src-library").onclick = () =>
  fetch("/api/audio/source", {method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({source: "library"})});
document.getElementById("src-spotify").onclick = () =>
  fetch("/api/audio/source", {method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({source: "spotify"})});
document.getElementById("upload").onchange = async (e) => {
  const f = e.target.files[0];
  if (!f) return;
  const fd = new FormData();
  fd.append("file", f);
  await fetch("/api/music/tracks", {method: "POST", body: fd});
  refresh();
};
refresh();
setInterval(refresh, 4000);
