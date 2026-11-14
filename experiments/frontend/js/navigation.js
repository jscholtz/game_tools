    function updateControls() {
      for (const pane of panes.values()) {
        const disabled = !socket || !socket.connected || pane.sending;
        pane.input.disabled = disabled;
        pane.button.disabled = disabled;
      }
    }

    loginForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      const error = document.getElementById("login-error");
      error.textContent = "";
      if (typeof io !== "function") {
        error.textContent = "Socket.IO client failed to load. Check your internet connection.";
        return;
      }

      let backend;
      try {
        backend = new URL(document.getElementById("backend-url").value);
        if (!["http:", "https:"].includes(backend.protocol) ||
            (backend.protocol === "http:" && !["localhost", "127.0.0.1"].includes(backend.hostname)) ||
            backend.username || backend.password || backend.pathname !== "/" ||
            backend.search || backend.hash) {
          throw new Error("Backend URL must be an HTTP(S) origin.");
        }
      } catch {
        error.textContent = "Enter an HTTPS backend origin, or an HTTP localhost origin.";
        return;
      }

      const button = loginForm.querySelector("button");
      button.disabled = true;
      try {
        const response = await fetch(`${backend.origin}/api/login`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "ngrok-skip-browser-warning": "true",
          },
          body: JSON.stringify({
            username: document.getElementById("username").value,
            password: document.getElementById("password").value,
          }),
        });
        const data = await response.json();
        if (!response.ok || data.status !== "success") {
          error.textContent = data.message || `Login failed (${response.status}).`;
          return;
        }
        token = data.token;
        backendOrigin = backend.origin;
        sessionStorage.setItem(storageKey, JSON.stringify({ token, backend: backendOrigin }));
        document.getElementById("password").value = "";
        enterChat(data.username, data.role);
      } catch (reason) {
        console.error("Login failed:", reason);
        error.textContent = "Cannot complete login. Check the backend URL, origin settings, and server.";
      } finally {
        button.disabled = false;
      }
    });

    function enterChat(username, role) {
      sessionVersion++;
      currentUser = username;
      currentRole = role;
      conversations.classList.toggle("dm-conversations", role === "dm" && username === "dm");
      playerTabs.hidden = false;
      notesTab.hidden = role !== "player";
      characterTab.hidden = role !== "player" && !(role === "dm" && username === "dm");
      setButtonLabel(characterTab, role === "dm" ? "Characters" : "Character", "character");
      characterEditButton.hidden = role !== "player";
      characterDisplay.hidden = role !== "player";
      dmCharacterList.hidden = role !== "dm";
      boardEditor.hidden = username !== "dm" || role !== "dm";
      initiativeTab.hidden = role !== "player" && !(role === "dm" && username === "dm");
      initiativeDm.hidden = username !== "dm" || role !== "dm";
      chatPanel.setAttribute("role", "tabpanel");
      chatPanel.setAttribute("aria-labelledby", "chat-tab");
      chatPanel.removeAttribute("aria-label");
      selectTab(chatTab);
      document.getElementById("current-user").textContent = username;
      document.getElementById("login-view").hidden = true;
      document.getElementById("chat-view").hidden = false;
      connectChat();
      if (role === "player") {
        loadNotes();
        loadCharacter();
      }
      loadBoard();
    }

    function showLogin(message, discardNotes = false) {
      if (!discardNotes && hasUnsavedChanges() &&
          !confirm(`${message}\nDiscard unsaved changes and return to login?`)) {
        notesStatus.textContent = "Session ended. Copy unsaved notes before logging in again.";
        boardStatus.textContent = "Session ended. Copy unsaved board edits before logging in again.";
        characterStatus.textContent = "Session ended. Copy unsaved character edits before logging in again.";
        initiativeStatus.textContent = "Session ended. Copy unsaved initiative edits before logging in again.";
        return;
      }
      sessionVersion++;
      if (socket) socket.disconnect();
      socket = null;
      token = null;
      sessionStorage.removeItem(storageKey);
      conversations.replaceChildren();
      conversations.classList.remove("dm-conversations");
      panes.clear();
      chatHistoryReady = false;
      latestChatReceived = -1;
      chatReadAck = -1;
      chatReadInFlight = false;
      updateUnreadCount(0);
      notesInput.value = "";
      notesHeader.value = "";
      notesEdit = null;
      notesBaseline = { header: "", content: "" };
      notesLoadVersion++;
      notesList.replaceChildren();
      notesLoaded = false;
      notesSaving = false;
      notesInput.disabled = true;
      notesHeader.disabled = true;
      notesSave.disabled = true;
      notesCancel.disabled = true;
      notesStatus.textContent = "";
      characterLoadVersion++;
      characterData = null;
      characterSaving = false;
      characterBaseline = "";
      characterForm.hidden = true;
      characterForm.reset();
      for (const control of characterForm.elements) control.disabled = false;
      characterReloadButton.disabled = false;
      characterClasses.replaceChildren();
      characterDisplay.replaceChildren();
      dmCharacterList.replaceChildren();
      characterEditButton.disabled = true;
      characterStatus.textContent = "";
      boardLoadVersion++;
      boardSaving = false;
      boardList.replaceChildren();
      boardStatus.textContent = "";
      resetBoardEditor();
      initiativeLoadVersion++;
      initiativeData = null;
      initiativeDirty = false;
      initiativeSaving = false;
      initiativeRefreshPending = false;
      initiativeAdd.reset();
      initiativeEncounterForm.reset();
      initiativeEditList.replaceChildren();
      initiativePlayerList.replaceChildren();
      initiativeEncounters.replaceChildren();
      initiativeStatus.textContent = "";
      document.getElementById("chat-view").hidden = true;
      document.getElementById("login-view").hidden = false;
      document.getElementById("login-error").textContent = message;
      updateControls();
    }

    function selectTab(selected) {
      for (const tab of [chatTab, notesTab, characterTab, boardTab, initiativeTab]) {
        const active = tab === selected;
        tab.setAttribute("aria-selected", String(active));
        tab.tabIndex = active ? 0 : -1;
      }
      chatPanel.hidden = selected !== chatTab;
      notesPanel.hidden = selected !== notesTab;
      characterPanel.hidden = selected !== characterTab;
      boardPanel.hidden = selected !== boardTab;
      initiativePanel.hidden = selected !== initiativeTab;
      if (selected === characterTab && currentRole === "dm" && currentUser === "dm") loadCharacters();
      if (selected === initiativeTab && !initiativeDirty) loadInitiative();
      if (selected === chatTab) markVisibleChatRead();
    }

    playerTabs.addEventListener("click", (event) => {
      const tab = event.target.closest('[role="tab"]');
      if ([chatTab, notesTab, characterTab, boardTab, initiativeTab].includes(tab)) selectTab(tab);
    });
    playerTabs.addEventListener("keydown", (event) => {
      if (!["ArrowUp", "ArrowDown", "Home", "End"].includes(event.key)) return;
      event.preventDefault();
      const tabs = [chatTab, notesTab, characterTab, boardTab, initiativeTab].filter((tab) => !tab.hidden);
      const index = tabs.indexOf(document.activeElement);
      const selected = event.key === "Home" ? tabs[0] : event.key === "End" ? tabs[tabs.length - 1] :
        tabs[(index + (event.key === "ArrowDown" ? 1 : -1) + tabs.length) % tabs.length];
      selectTab(selected);
      selected.focus();
    });

