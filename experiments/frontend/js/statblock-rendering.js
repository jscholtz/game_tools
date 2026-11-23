function validStatblockDisplay(display) {
  return display && typeof display.inline === "string" &&
    display.inline.includes("<head>") && Array.isArray(display.sizes) &&
    display.sizes.length === 2 &&
    display.sizes.every((size) => Number.isFinite(size) && size > 0);
}

function createStatblockFrame(display, onError) {
  const frame = document.createElement("iframe");
  frame.className = "bestiary-statblock-frame";
  frame.title = "Creature stat block";
  frame.setAttribute("sandbox", "allow-same-origin");
  frame.style.height = `${display.sizes[0] + 50}px`;
  frame.style.maxWidth = `${display.sizes[1] + 40}px`;
  let observer = null;
  frame.addEventListener("load", () => {
    if (!frame.isConnected) return;
    const block = frame.contentDocument?.querySelector("stat-block");
    if (!block) {
      onError();
      return;
    }
    const resize = () => {
      if (!frame.isConnected) return;
      const height = block.getBoundingClientRect().bottom + 20;
      if (height > 20) frame.style.height = `${Math.ceil(height)}px`;
    };
    observer = new ResizeObserver(resize);
    observer.observe(block);
    resize();
  });
  const policy = "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'";
  frame.srcdoc = display.inline.replace("<head>", `<head><meta http-equiv="Content-Security-Policy" content="${policy}">`);
  return { frame, disconnect: () => observer?.disconnect() };
}
