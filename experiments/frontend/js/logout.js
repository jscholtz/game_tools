    document.getElementById("logout-button").addEventListener("click", async () => {
      if (notesSaving || boardSaving || characterSaving || initiativeSaving || customSaving || customAdding) {
        notesStatus.textContent = "Wait for the current save to finish before logging out.";
        boardStatus.textContent = "Wait for the current save to finish before logging out.";
        characterStatus.textContent = "Wait for the current save to finish before logging out.";
        initiativeStatus.textContent = "Wait for the current save to finish before logging out.";
        customStatus.textContent = "Wait for the current save to finish before logging out.";
        return;
      }
      if (hasUnsavedChanges() && !confirm("Discard unsaved changes and log out?")) return;
      const logoutButton = document.getElementById("logout-button");
      loggingOut = true;
      updateInitiativeControls();
      logoutButton.disabled = true;
      notesInput.disabled = true;
      notesHeader.disabled = true;
      notesSave.disabled = true;
      notesCancel.disabled = true;
      boardInput.disabled = true;
      boardHeader.disabled = true;
      boardImages.disabled = true;
      for (const checkbox of boardExistingImages.querySelectorAll("input")) checkbox.disabled = true;
      boardVisible.disabled = true;
      boardSave.disabled = true;
      boardCancel.disabled = true;
      for (const control of characterForm.elements) control.disabled = true;
      characterEditButton.disabled = true;
      characterReloadButton.disabled = true;
      try {
        const response = await fetch(`${backendOrigin}/api/logout`, {
          method: "POST",
          headers: {
            "Authorization": `Bearer ${token}`,
            "ngrok-skip-browser-warning": "true",
          },
        });
        if (!response.ok && response.status !== 401 && response.status !== 422) {
          throw new Error(`Logout failed (${response.status}).`);
        }
        showLogin("Logged out.", true);
      } catch (error) {
        console.error("Logout failed:", error);
        messageError.textContent = "Logout failed. Check the backend and try again.";
        if (notesLoaded) {
          notesInput.disabled = false;
          notesHeader.disabled = false;
          notesSave.disabled = false;
          notesCancel.disabled = false;
          notesStatus.textContent = "Logout failed. Check the backend and try again.";
        }
        boardInput.disabled = false;
        boardHeader.disabled = false;
        boardImages.disabled = false;
        for (const checkbox of boardExistingImages.querySelectorAll("input")) checkbox.disabled = false;
        boardVisible.disabled = false;
        boardSave.disabled = false;
        boardCancel.disabled = false;
        boardStatus.textContent = "Logout failed. Check the backend and try again.";
        for (const control of characterForm.elements) control.disabled = false;
        characterEditButton.disabled = !characterData;
        characterReloadButton.disabled = false;
        characterStatus.textContent = "Logout failed. Check the backend and try again.";
      } finally {
        loggingOut = false;
        updateInitiativeControls();
        logoutButton.disabled = false;
      }
    });
