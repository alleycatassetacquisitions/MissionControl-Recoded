(function () {
  const cfg = window.GBN_CYCLE || {};
  const intervalMs = Math.max(5000, Math.min(300000, (cfg.intervalSec || 30) * 1000));
  const base = (cfg.publicBase || "").replace(/\/$/, "");
  const frame = document.getElementById("poster-frame");
  const hud = document.getElementById("hud");
  const hudLabel = document.getElementById("hud-label");
  /** @type {{ id: string, player_id: string, name: string, poster_url: string }[]} */
  let posters = [];
  let index = 0;
  let currentKey = "";

  function posterKey(p) {
    return String(p.player_id || p.id || "");
  }

  function posterUrl(p) {
    if (p.poster_url) return p.poster_url;
    if (p.player_id) {
      return `${base}/poster/player/${encodeURIComponent(p.player_id)}`;
    }
    return `${base}/poster/${encodeURIComponent(p.id)}`;
  }

  function showCurrent() {
    if (!posters.length) {
      frame.src = "about:blank";
      currentKey = "";
      if (hud) hud.hidden = false;
      if (hudLabel) hudLabel.textContent = "NO POSTERS YET";
      return;
    }
    const p = posters[index % posters.length];
    const next = posters[(index + 1) % posters.length];
    currentKey = posterKey(p);
    frame.src = posterUrl(p);
    if (hud) hud.hidden = false;
    if (hudLabel) {
      const label = p.name || currentKey || "?";
      hudLabel.textContent = `${label} · ${index % posters.length + 1}/${posters.length}`;
    }
    if (next && posterKey(next) !== currentKey) {
      const prefetch = document.createElement("link");
      prefetch.rel = "prefetch";
      prefetch.href = posterUrl(next);
      document.head.appendChild(prefetch);
    }
  }

  async function refreshPosters() {
    try {
      const resp = await fetch("/api/posters");
      if (!resp.ok) return;
      const data = await resp.json();
      if (!Array.isArray(data)) return;
      const next = data.map((p) => ({
        id: String(p.id || ""),
        player_id: String(p.player_id || ""),
        name: String(p.name || ""),
        poster_url: String(p.poster_url || ""),
      }));
      posters = next;
      if (!posters.length) {
        index = 0;
        showCurrent();
        return;
      }
      if (currentKey) {
        const found = posters.findIndex((p) => posterKey(p) === currentKey);
        if (found >= 0) index = found;
        else index = index % posters.length;
      } else {
        index = 0;
        showCurrent();
      }
    } catch (_) {
      /* keep current list */
    }
  }

  refreshPosters().then(() => {
    if (posters.length) showCurrent();
    else showCurrent();
  });

  setInterval(() => {
    if (!posters.length) return;
    index = (index + 1) % posters.length;
    showCurrent();
  }, intervalMs);

  setInterval(refreshPosters, 15000);
})();
