    function updateUnreadCount(count) {
      chatUnread.textContent = String(count);
      chatUnread.hidden = count === 0;
      chatTab.setAttribute("aria-label", count ? `Chat, ${count} unread messages` : "Chat");
    }

    function markVisibleChatRead() {
      if (!socket?.connected || !chatHistoryReady || chatPanel.hidden || document.hidden ||
          latestChatReceived <= chatReadAck || chatReadInFlight) return;
      const version = sessionVersion;
      const messageId = latestChatReceived;
      chatReadInFlight = true;
      socket.timeout(5000).emit("mark_chat_read", { message_id: messageId }, (error, result) => {
        if (version !== sessionVersion) return;
        chatReadInFlight = false;
        if (error || !result || result.status !== "success") {
          messageError.textContent = result?.message || "Could not mark chat as read. Reconnect or reopen chat to retry.";
          return;
        }
        chatReadAck = Math.max(chatReadAck, messageId);
        markVisibleChatRead();
      });
    }

    document.addEventListener("visibilitychange", () => {
      if (!document.hidden) markVisibleChatRead();
    });

    function connectChat() {
      socket = io(backendOrigin, { transports: ["websocket"], auth: { token } });
      socket.on("connect", () => {
        connectionStatus.textContent = "Connected.";
        updateControls();
        loadBoard();
        if (initiativeData) initiativeChanged();
        socket.timeout(5000).emit("get_history", (error, result) => {
          if (error || !result || result.status !== "success") {
            messageError.textContent = result?.message || "Could not load chat history.";
          }
        });
      });
      socket.on("board_changed", loadBoard);
      socket.on("initiative_changed", initiativeChanged);
      socket.on("disconnect", async (reason) => {
        chatHistoryReady = false;
        if (reason === "io client disconnect") return;
        connectionStatus.textContent = "Disconnected. Reconnecting...";
        updateControls();
        if (reason === "io server disconnect" && !loggingOut) {
          try {
            const data = await verifySession();
            if (data && socket) socket.connect();
          } catch (error) {
            console.error("Session verification failed:", error);
            connectionStatus.textContent = "Cannot verify session. Refresh to retry.";
          }
        }
      });
      socket.on("connect_error", async (reason) => {
        console.error("Chat connection failed:", reason);
        connectionStatus.textContent = "Connection failed. Check the backend, origin settings, and WebSocket support.";
        updateControls();
        if (reason.message.startsWith("Connection rejected")) {
          try {
            await verifySession();
          } catch (error) {
            console.error("Session verification failed:", error);
          }
        }
      });
      function appendMessage(data) {
        if (!data || typeof data.sender !== "string" || typeof data.recipient !== "string" ||
            typeof data.text !== "string" || !Number.isSafeInteger(data.id) || data.id < 0) {
          console.error("Invalid message received:", data);
          messageError.textContent = "Invalid chat message received. Reconnect to reload.";
          return false;
        }
        const player = currentRole === "dm"
          ? (data.sender === "dm" ? data.recipient : data.sender)
          : currentUser;
        const pane = panes.get(player);
        if (!pane) {
          messageError.textContent = "Received a message for an unknown conversation. Refresh to reload.";
          return false;
        }
        const box = pane.box;
        const row = document.createElement("div");
        const sender = document.createElement("strong");
        sender.textContent = `${data.sender}: `;
        row.append(sender, document.createTextNode(data.text));
        box.append(row);
        box.scrollTop = box.scrollHeight;
        if (data.recipient === currentUser) latestChatReceived = Math.max(latestChatReceived, data.id);
        return true;
      }
      socket.on("chat_history", (history) => {
        if (!history || typeof history !== "object" || Array.isArray(history)) {
          messageError.textContent = "Invalid chat history received.";
          return;
        }
        if (Object.values(history).some((messages) => !Array.isArray(messages))) {
          messageError.textContent = "Invalid chat history received.";
          return;
        }
        messageError.textContent = "";
        for (const [player, pane] of panes) {
          if (!Object.hasOwn(history, player)) {
            pane.section.remove();
            panes.delete(player);
          }
        }
        let validHistory = true;
        for (const [player, messages] of Object.entries(history)) {
          if (!panes.has(player)) createPane(player);
          panes.get(player).box.replaceChildren();
          for (const message of messages) {
            if (!appendMessage(message)) validHistory = false;
          }
        }
        if (currentRole === "dm" && Object.keys(history).length === 0) {
          messageError.textContent = "No player accounts found.";
        }
        chatHistoryReady = validHistory;
        if (validHistory) markVisibleChatRead();
        updateControls();
      });
      socket.on("receive_message", (message) => {
        if (appendMessage(message)) markVisibleChatRead();
      });
      socket.on("chat_unread", (data) => {
        if (!data || !Number.isSafeInteger(data.count) || data.count < 0) {
          messageError.textContent = "Invalid unread count received.";
          return;
        }
        updateUnreadCount(data.count);
      });
    }

    function createPane(player) {
      const section = document.createElement("section");
      const heading = document.createElement("h3");
      heading.textContent = currentRole === "dm" ? player : "Dungeon Master";
      const box = document.createElement("div");
      box.className = "chat-box";
      box.setAttribute("role", "log");
      box.setAttribute("aria-label", `Messages with ${heading.textContent}`);
      box.setAttribute("aria-live", "polite");
      const form = document.createElement("form");
      const label = document.createElement("label");
      label.textContent = "Message";
      const input = document.createElement("input");
      input.maxLength = 1000;
      input.required = true;
      label.append(input);
      const button = document.createElement("button");
      button.type = "submit";
      button.textContent = "Send";
      addButtonIcon(button, "send");
      form.append(label, button);
      section.append(heading, box, form);
      conversations.append(section);
      const pane = { section, box, input, button, sending: false };
      panes.set(player, pane);
      form.addEventListener("submit", (event) => {
        event.preventDefault();
        const text = input.value.trim();
        if (!text || !socket || !socket.connected || pane.sending) return;
        messageError.textContent = "";
        pane.sending = true;
        updateControls();
        socket.timeout(5000).emit("send_message", {
          text, recipient: currentRole === "dm" ? player : "dm",
        }, (error, result) => {
          pane.sending = false;
          updateControls();
          if (error) {
            messageError.textContent = "Delivery unconfirmed. Check the chat before retrying.";
          } else if (!result || result.status !== "success") {
            messageError.textContent = result?.message || "Message was not accepted.";
          } else {
            input.value = "";
          }
        });
      });
    }

