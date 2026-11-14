    async function verifySession() {
      const response = await fetch(`${backendOrigin}/api/verify`, {
        headers: {
          "Authorization": `Bearer ${token}`,
          "ngrok-skip-browser-warning": "true",
        },
      });
      if (response.status === 401 || response.status === 422) {
        showLogin("Session expired or invalid. Log in again.");
        return null;
      }
      if (!response.ok) throw new Error(`Session verification failed (${response.status}).`);
      return response.json();
    }

    async function restoreSession() {
      const saved = sessionStorage.getItem(storageKey);
      if (!saved) return;
      try {
        const session = JSON.parse(saved);
        const url = new URL(session.backend);
        if (!["http:", "https:"].includes(url.protocol) ||
            (url.protocol === "http:" && !["localhost", "127.0.0.1"].includes(url.hostname)) ||
            url.origin !== session.backend ||
            typeof session.token !== "string" || !session.token) {
          throw new Error("Invalid saved session.");
        }
        backendOrigin = session.backend;
        token = session.token;
        document.getElementById("backend-url").value = backendOrigin;
        const data = await verifySession();
        if (data) {
          if (typeof io !== "function") throw new Error("Socket.IO client failed to load.");
          enterChat(data.username, data.role);
        }
      } catch (reason) {
        console.error("Could not restore session:", reason);
        document.getElementById("login-error").textContent =
          "Could not restore session. Check the backend and refresh to retry, or log in again.";
      }
    }

