(() => {
  const storageKey = "split-chat-theme";
  const themes = new Set(["parchment", "dark"]);
  let storageError = false;

  function applyTheme(theme) {
    document.documentElement.dataset.theme = themes.has(theme) ? theme : "parchment";
  }

  try {
    applyTheme(localStorage.getItem(storageKey));
  } catch (error) {
    storageError = true;
    console.warn("Could not read the saved theme:", error);
  }

  document.addEventListener("DOMContentLoaded", () => {
    const select = document.getElementById("theme-select");
    const status = document.getElementById("theme-status");
    select.value = document.documentElement.dataset.theme;
    if (storageError) status.textContent = "Theme preference could not be loaded from browser storage.";

    select.addEventListener("change", () => {
      applyTheme(select.value);
      try {
        localStorage.setItem(storageKey, document.documentElement.dataset.theme);
        status.textContent = "";
      } catch (error) {
        console.warn("Could not save the theme:", error);
        status.textContent = "Theme changed, but could not be saved in browser storage.";
      }
    });

    window.addEventListener("storage", (event) => {
      if (event.key !== storageKey && event.key !== null) return;
      applyTheme(event.newValue);
      select.value = document.documentElement.dataset.theme;
    });
  });
})();
