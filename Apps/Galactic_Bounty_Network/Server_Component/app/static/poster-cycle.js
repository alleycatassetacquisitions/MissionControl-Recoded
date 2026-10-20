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
  /** @type {string} */
  let emptyReason = "NO POSTERS YET";

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

  function frameIsBlank() {
    const src = frame?.src || "";
    return !src || src === "about:blank" || src === "about:blank#";
  }

  function showEmptyHud(reason) {
    if (hud) hud.hidden = false;
    if (hudLabel) hudLabel.textContent = reason;
  }

  function hideHud() {
    if (hud) hud.hidden = true;
    if (hudLabel) hudLabel.textContent = "";
  }

  function showCurrent() {
    if (!posters.length) {
      frame.src = "about:blank";
      currentKey = "";
      showEmptyHud(emptyReason);
      return;
    }
    const p = posters[index % posters.length];
    const next = posters[(index + 1) % posters.length];
    currentKey = posterKey(p);
    frame.src = posterUrl(p);
    // Kiosk: no event/player/counter chrome over the poster art.
    hideHud();
    if (next && posterKey(next) !== currentKey) {
      const prefetch = document.createElement("link");
      prefetch.rel = "prefetch";
      prefetch.href = posterUrl(next);
      document.head.appendChild(prefetch);
    }
  }

  async function refreshPosters() {
    try {
      // Active-event only — never fall back to legacy global posters.json.
      const activeResp = await fetch("/api/events/active", { cache: "no-store" });
      if (!activeResp.ok) {
        posters = [];
        emptyReason = "EVENT LOOKUP FAILED";
        showCurrent();
        return;
      }
      const active = await activeResp.json();
      const eid = String(active?.active_event_id || "").trim();
      if (!eid) {
        posters = [];
        emptyReason = "NO ACTIVE EVENT";
        showCurrent();
        return;
      }

      const resp = await fetch(
        `/api/posters?event_id=${encodeURIComponent(eid)}`,
        { cache: "no-store" }
      );
      if (!resp.ok) {
        emptyReason = `POSTERS FETCH FAILED (${resp.status})`;
        if (!posters.length) showCurrent();
        return;
      }
      const data = await resp.json();
      if (!Array.isArray(data)) return;
      const wasBlank = frameIsBlank() || !posters.length;
      const next = data.map((p) => ({
        id: String(p.id || ""),
        player_id: String(p.player_id || ""),
        name: String(p.name || ""),
        poster_url: String(p.poster_url || ""),
      }));
      posters = next;
      emptyReason = "NO POSTERS FOR EVENT";
      if (!posters.length) {
        index = 0;
        showCurrent();
        return;
      }
      if (currentKey) {
        const found = posters.findIndex((p) => posterKey(p) === currentKey);
        index = found >= 0 ? found : index % posters.length;
      } else {
        index = 0;
      }
      // Leaving empty → populated must always paint (Pi kiosks used to stay blank
      // until a desktop browser hit the page once and the next refresh had a key).
      if (wasBlank || !currentKey) {
        showCurrent();
      }
      // Already showing a poster — leave the frame alone; no identity HUD.
    } catch (_) {
      /* keep current list */
    }
  }

  refreshPosters().then(() => {
    showCurrent();
  });

  setInterval(() => {
    if (!posters.length) return;
    index = (index + 1) % posters.length;
    showCurrent();
  }, intervalMs);

  setInterval(refreshPosters, 15000);
})();
