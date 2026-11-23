// The opener allows sessionStorage to be copied into this tab, then is no longer needed.
window.opener = null;

(async () => {
  const status = document.getElementById("statblock-status");
  const detail = document.getElementById("statblock-detail");
  try {
    const slug = new URLSearchParams(location.search).get("slug");
    const customId = new URLSearchParams(location.search).get("custom");
    if ((!slug && !customId) || (slug && customId)) throw new Error("Specify one creature.");
    const saved = sessionStorage.getItem("split-chat-session");
    if (!saved) throw new Error("Open this page from a signed-in DM session.");
    const session = JSON.parse(saved);
    const url = new URL(session.backend);
    if (!["http:", "https:"].includes(url.protocol) ||
        (url.protocol === "http:" && !["localhost", "127.0.0.1"].includes(url.hostname)) ||
        url.origin !== session.backend || typeof session.token !== "string" || !session.token) {
      throw new Error("Invalid saved session. Open this page from a signed-in DM session.");
    }
    const path = customId
      ? `/api/custom-creatures/${encodeURIComponent(customId)}`
      : `/api/bestiary/creature?${new URLSearchParams({ slug })}`;
    const response = await fetch(`${url.origin}${path}`, {
      headers: { "Authorization": "Bearer " + session.token, "ngrok-skip-browser-warning": "true" },
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.message || `Request failed (${response.status}).`);
    if (!validStatblockDisplay(data.display)) throw new Error("Invalid stat block response.");
    const rendered = createStatblockFrame(data.display, () => {
      status.textContent = "Could not display the creature stat block.";
    });
    detail.replaceChildren(rendered.frame);
    status.textContent = "";
  } catch (error) {
    console.error("Could not load creature statblock:", error);
    status.textContent = `Could not load creature: ${error.message}`;
  }
})();
