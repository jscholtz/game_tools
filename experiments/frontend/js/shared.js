    const loginForm = document.getElementById("login-form");
    const conversations = document.getElementById("conversations");
    const connectionStatus = document.getElementById("connection-status");
    const messageError = document.getElementById("message-error");
    const playerTabs = document.getElementById("player-tabs");
    const chatTab = document.getElementById("chat-tab");
    const chatUnread = document.getElementById("chat-unread");
    const notesTab = document.getElementById("notes-tab");
    const chatPanel = document.getElementById("chat-panel");
    const notesPanel = document.getElementById("notes-panel");
    const notesInput = document.getElementById("notes-input");
    const notesHeader = document.getElementById("notes-header");
    const notesCancel = document.getElementById("notes-cancel");
    const notesList = document.getElementById("notes-list");
    const notesSave = document.getElementById("notes-save");
    const notesRetry = document.getElementById("notes-retry");
    const notesStatus = document.getElementById("notes-status");
    const characterTab = document.getElementById("character-tab");
    const characterPanel = document.getElementById("character-panel");
    const characterForm = document.getElementById("character-form");
    const characterDisplay = document.getElementById("character-display");
    const dmCharacterList = document.getElementById("dm-character-list");
    const characterStatus = document.getElementById("character-status");
    const characterEditButton = document.getElementById("character-edit");
    const characterReloadButton = document.getElementById("character-reload");
    const characterFields = document.getElementById("character-fields");
    const characterTextFields = document.getElementById("character-text-fields");
    const characterClasses = document.getElementById("character-classes");
    const characterPortrait = document.getElementById("character-portrait");
    const characterRemovePortrait = document.getElementById("character-remove-portrait");
    const boardTab = document.getElementById("board-tab");
    const boardPanel = document.getElementById("board-panel");
    const boardEditor = document.getElementById("board-editor");
    const boardInput = document.getElementById("board-input");
    const boardHeader = document.getElementById("board-header");
    const boardImages = document.getElementById("board-images");
    const boardExistingImages = document.getElementById("board-existing-images");
    const boardVisible = document.getElementById("board-visible");
    const boardSave = document.getElementById("board-save");
    const boardCancel = document.getElementById("board-cancel");
    const boardStatus = document.getElementById("board-status");
    const boardList = document.getElementById("board-list");
    const initiativeTab = document.getElementById("initiative-tab");
    const initiativePanel = document.getElementById("initiative-panel");
    const initiativeDm = document.getElementById("initiative-dm");
    const initiativeStatus = document.getElementById("initiative-status");
    const initiativeFields = document.getElementById("initiative-fields");
    const initiativeEditList = document.getElementById("initiative-edit-list");
    const initiativePlayerList = document.getElementById("initiative-player-list");
    const initiativeEncounters = document.getElementById("initiative-encounters");
    const initiativeAdd = document.getElementById("initiative-add");
    const initiativeEdit = document.getElementById("initiative-edit");
    const initiativeEncounterForm = document.getElementById("initiative-encounter-form");
    if (location.protocol === "https:") {
      document.getElementById("backend-url").value = location.origin;
    }
    let socket;
    let token;
    let backendOrigin;
    let currentUser;
    let currentRole;
    let chatHistoryReady = false;
    let latestChatReceived = -1;
    let chatReadAck = -1;
    let chatReadInFlight = false;
    let sessionVersion = 0;
    let notesEdit = null;
    let notesBaseline = { header: "", content: "" };
    let notesLoadVersion = 0;
    let notesLoaded = false;
    let notesSaving = false;
    let characterData = null;
    let characterBaseline = "";
    let characterSaving = false;
    let characterLoadVersion = 0;
    let boardSaving = false;
    let loggingOut = false;
    let boardEdit = null;
    let boardAttachments = [];
    let boardBaseline = { header: "", content: "", visible: false };
    let boardLoadVersion = 0;
    let initiativeData = null;
    let initiativeDirty = false;
    let initiativeSaving = false;
    let initiativeLoadVersion = 0;
    let initiativeRefreshPending = false;
    const panes = new Map();
    const storageKey = "split-chat-session";

    const iconPaths = {
      chat: "M4 4h16v12H9l-5 4V4z",
      notes: "M5 3h14v18H5z M8 3v18 M11 7h5 M11 11h5 M11 15h5",
      character: "M5 3h14v18H5z M9 8a3 3 0 1 0 6 0 3 3 0 0 0-6 0 M8 18c0-2 2-3 4-3s4 1 4 3",
      board: "M4 5h16v14H4z M8 9h8 M8 13h8 M8 17h4 M12 2v3",
      initiative: "M6 3h12l3 9-9 9-9-9z M6 3l6 9 6-9 M3 12h18 M12 12v9",
      login: "M13 3h7v18h-7 M4 12h12 M12 8l4 4-4 4",
      logout: "M11 3H4v18h7 M20 12H8 M16 8l4 4-4 4",
      send: "M3 4l18 8-18 8 3-8-3-8z M6 12h15",
      save: "M4 3h13l3 3v15H4z M7 3v6h9V3 M7 21v-8h10v8",
      edit: "M4 20l4-1L19 8l-3-3L5 16z M14 7l3 3",
      cancel: "M6 6l12 12 M18 6L6 18",
      reload: "M20 7v5h-5 M4 17v-5h5 M5 10a7 7 0 0 1 12-4l3 3 M19 14a7 7 0 0 1-12 4l-3-3",
      add: "M12 4v16 M4 12h16",
      remove: "M4 7h16 M9 7V4h6v3 M7 7l1 13h8l1-13 M10 10v7 M14 10v7",
      next: "M4 5l10 7-10 7z M18 5v14",
      sort: "M4 5h11 M4 9h8 M4 13h5 M4 17h3 M18 5v14 M15 16l3 3 3-3",
      load: "M3 6h7l2 2h9l-2 11H3z M3 6v13",
      overwrite: "M4 8a8 8 0 0 1 14-2l2 2 M20 4v4h-4 M20 16a8 8 0 0 1-14 2l-2-2 M4 20v-4h4",
    };

    function addButtonIcon(button, name) {
      const icon = document.createElementNS("http://www.w3.org/2000/svg", "svg");
      icon.setAttribute("viewBox", "0 0 24 24");
      icon.setAttribute("fill", "none");
      icon.setAttribute("stroke", "currentColor");
      icon.setAttribute("stroke-width", "1.8");
      icon.setAttribute("stroke-linecap", "round");
      icon.setAttribute("stroke-linejoin", "round");
      icon.setAttribute("aria-hidden", "true");
      icon.setAttribute("focusable", "false");
      icon.classList.add("button-icon");
      const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
      path.setAttribute("d", iconPaths[name]);
      icon.append(path);
      button.prepend(icon);
    }

    function setButtonLabel(button, label, icon) {
      button.textContent = label;
      addButtonIcon(button, icon);
    }

    for (const [selector, icon] of [
      ["#login-form button[type=submit]", "login"], ["#chat-tab", "chat"], ["#notes-tab", "notes"],
      ["#character-tab", "character"], ["#board-tab", "board"], ["#initiative-tab", "initiative"],
      ["#logout-button", "logout"], ["#notes-save", "save"], ["#notes-cancel", "cancel"],
      ["#notes-retry", "reload"], ["#character-edit", "edit"], ["#character-reload", "reload"],
      ["#character-add-class", "add"], ["#character-save", "save"], ["#character-cancel", "cancel"],
      ["#board-save", "save"], ["#board-cancel", "cancel"], ["#board-refresh", "reload"],
      ["#initiative-refresh", "reload"], ["#initiative-add button", "add"], ["#initiative-next", "next"],
      ["#initiative-sort", "sort"], ["#initiative-save", "save"], ["#initiative-encounter-form button", "save"],
    ]) {
      addButtonIcon(document.querySelector(selector), icon);
    }

