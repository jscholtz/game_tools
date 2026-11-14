    async function loadNotes() {
      const version = sessionVersion;
      const loadVersion = ++notesLoadVersion;
      notesStatus.textContent = "Loading notes...";
      try {
        const response = await fetch(`${backendOrigin}/api/notes`, {
          headers: { "Authorization": "Bearer " + token, "ngrok-skip-browser-warning": "true" },
        });
        if (!response.ok) throw new Error(`Loading notes failed (${response.status}).`);
        const data = await response.json();
        if (!Array.isArray(data.notes) || data.notes.some((note) => !validNote(note))) {
          throw new Error("Invalid notes response.");
        }
        if (typeof marked === "undefined" || typeof DOMPurify === "undefined") {
          throw new Error("Markdown rendering libraries failed to load.");
        }
        if (version !== sessionVersion || loadVersion !== notesLoadVersion) return;
        const openNotes = new Set(Array.from(notesList.querySelectorAll("details[open]"), (el) => el.dataset.id));
        const entries = data.notes.map((note) => {
          const article = renderNote(note, openNotes.has(note.id));
          const edit = document.createElement("button");
          edit.type = "button";
          edit.textContent = "Edit";
          addButtonIcon(edit, "edit");
          edit.addEventListener("click", () => {
            if (notesSaving) return;
            if (notesDirty() && !confirm("Discard unsaved personal note edits?")) return;
            resetNotesEditor(note);
            notesStatus.textContent = "Editing personal note.";
            notesHeader.focus();
          });
          article.append(edit);
          appendNoteDate(article, note);
          return article;
        });
        notesList.replaceChildren(...entries);
        notesLoaded = true;
        if (!notesSaving && !loggingOut) {
          notesHeader.disabled = false;
          notesInput.disabled = false;
          notesSave.disabled = false;
          notesCancel.disabled = false;
        }
        notesStatus.textContent = entries.length ? "" : "No personal notes to display.";
      } catch (error) {
        if (version !== sessionVersion || loadVersion !== notesLoadVersion) return;
        console.error("Could not load notes:", error);
        notesStatus.textContent = "Could not load notes. Check your session and connection, then retry.";
      }
    }

    notesRetry.addEventListener("click", loadNotes);
    notesCancel.addEventListener("click", () => {
      if (notesDirty() && !confirm("Discard unsaved personal note edits?")) return;
      resetNotesEditor();
      notesStatus.textContent = "";
    });
    document.getElementById("notes-form").addEventListener("submit", async (event) => {
      event.preventDefault();
      if (!notesLoaded || notesSaving) return;
      const version = sessionVersion;
      const editing = notesEdit;
      const payload = { header: notesHeader.value, content: notesInput.value };
      if (editing) payload.revision = editing.revision;
      notesSaving = true;
      notesSave.disabled = true;
      notesInput.disabled = true;
      notesHeader.disabled = true;
      notesCancel.disabled = true;
      notesStatus.textContent = "Saving...";
      try {
        const response = await fetch(`${backendOrigin}/api/notes${editing ? `/${encodeURIComponent(editing.id)}` : ""}`, {
          method: editing ? "PUT" : "POST",
          headers: {
            "Authorization": "Bearer " + token,
            "Content-Type": "application/json",
            "ngrok-skip-browser-warning": "true",
          },
          body: JSON.stringify(payload),
        });
        const result = await response.json();
        if (!response.ok || result.status !== "success") {
          throw new Error(result.message || `Saving notes failed (${response.status}).`);
        }
        if (version !== sessionVersion) return;
        resetNotesEditor();
        await loadNotes();
      } catch (error) {
        if (version !== sessionVersion) return;
        console.error("Could not save notes:", error);
        notesStatus.textContent = `${error.message} Save may have succeeded. Your edits are retained; refresh notes before retrying.`;
      } finally {
        if (version === sessionVersion) {
          notesSaving = false;
          notesSave.disabled = false;
          notesInput.disabled = false;
          notesHeader.disabled = false;
          notesCancel.disabled = false;
        }
      }
    });
    window.addEventListener("beforeunload", (event) => {
      if (hasUnsavedChanges()) event.preventDefault();
    });

