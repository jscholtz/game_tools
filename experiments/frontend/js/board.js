    function imageSource(image) {
      return image.url || `data:${image.media_type};base64,${image.data}`;
    }

    function boardDirty() {
      return boardHeader.value !== boardBaseline.header || boardInput.value !== boardBaseline.content ||
        boardVisible.checked !== boardBaseline.visible || boardImages.files.length > 0 ||
        boardExistingImages.querySelector("input:checked") !== null;
    }

    function hasUnsavedChanges() {
      return (notesLoaded && (notesSaving || notesDirty())) ||
        (!customForm.hidden && (customSaving || customDirty())) ||
        (!boardEditor.hidden && (boardSaving || boardDirty())) ||
        (!characterForm.hidden && (characterSaving || characterDirty())) ||
        (!initiativeDm.hidden && (initiativeSaving || initiativeDirty ||
          document.getElementById("initiative-name").value.trim() !== "" ||
          document.getElementById("initiative-encounter-name").value.trim() !== ""));
    }

    function resetBoardEditor(note = null) {
      boardEdit = note ? { id: note.id, revision: note.revision } : null;
      boardBaseline = {
        header: note ? note.header : "",
        content: note ? note.content : "",
        visible: note ? note.visible : false,
      };
      boardHeader.value = boardBaseline.header;
      boardInput.value = boardBaseline.content;
      boardVisible.checked = boardBaseline.visible;
      boardAttachments = note ? note.images.slice() : [];
      boardImages.value = "";
      boardExistingImages.replaceChildren();
      boardAttachments.forEach((image, index) => {
        const label = document.createElement("label");
        const preview = document.createElement("img");
        preview.src = imageSource(image);
        preview.alt = image.name;
        preview.addEventListener("error", () => {
          boardStatus.textContent = `Could not display image: ${image.name}.`;
        });
        const checkbox = document.createElement("input");
        checkbox.type = "checkbox";
        checkbox.value = String(index);
        label.append(preview, checkbox, document.createTextNode(` Remove ${image.name}`));
        boardExistingImages.append(label);
      });
      boardInput.disabled = false;
      boardHeader.disabled = false;
      boardImages.disabled = false;
      boardVisible.disabled = false;
      boardSave.disabled = false;
      boardCancel.disabled = false;
      setButtonLabel(boardCancel, note ? "Cancel editing" : "Clear editor", "cancel");
    }

    async function loadBoard() {
      const version = sessionVersion;
      const loadVersion = ++boardLoadVersion;
      try {
        const response = await fetch(`${backendOrigin}/api/board`, {
          headers: { "Authorization": "Bearer " + token, "ngrok-skip-browser-warning": "true" },
        });
        if (!response.ok) throw new Error(`Loading board failed (${response.status}).`);
        const data = await response.json();
        if (!Array.isArray(data.notes) || data.notes.some((note) =>
          !validNote(note) || typeof note.visible !== "boolean" || !Array.isArray(note.images) ||
          note.images.some((image) => !image || typeof image.name !== "string" ||
            !["image/png", "image/jpeg", "image/gif", "image/webp"].includes(image.media_type) ||
            !(typeof image.url === "string" || typeof image.data === "string")))) {
          throw new Error("Invalid board response.");
        }
        if (typeof marked === "undefined" || typeof DOMPurify === "undefined") {
          throw new Error("Markdown rendering libraries failed to load.");
        }
        if (version !== sessionVersion || loadVersion !== boardLoadVersion) return;
        const openNotes = new Set(Array.from(boardList.querySelectorAll("details[open]"), (el) => el.dataset.id));
        const entries = data.notes.map((note) => {
          const article = renderNote(note, openNotes.has(note.id));
          for (const image of note.images) {
            const figure = document.createElement("figure");
            const element = document.createElement("img");
            element.src = imageSource(image);
            element.alt = image.name;
            element.loading = "lazy";
            element.addEventListener("error", () => {
              boardStatus.textContent = `Could not display image: ${image.name}.`;
            });
            const caption = document.createElement("figcaption");
            caption.textContent = image.name;
            figure.append(element, caption);
            article.append(figure);
          }
          if (!boardEditor.hidden) {
            const visibility = document.createElement("p");
            visibility.textContent = note.visible ? "Visible to players" : "Hidden from players";
            article.append(visibility);
          }
          if (!boardEditor.hidden) {
            const edit = document.createElement("button");
            edit.type = "button";
            edit.textContent = "Edit";
            addButtonIcon(edit, "edit");
            edit.addEventListener("click", () => {
              if (boardSaving) return;
              if (boardDirty() && !confirm("Discard unsaved board edits?")) return;
              resetBoardEditor(note);
              boardStatus.textContent = "Editing board note.";
              boardInput.focus();
            });
            article.append(edit);
          }
          appendNoteDate(article, note);
          return article;
        });
        boardList.replaceChildren(...entries);
        boardStatus.textContent = entries.length ? "" : "No board notes to display.";
      } catch (error) {
        if (version !== sessionVersion || loadVersion !== boardLoadVersion) return;
        console.error("Could not load board:", error);
        boardStatus.textContent = "Could not load the board or Markdown renderer. Check your connection and refresh.";
      }
    }

    document.getElementById("board-refresh").addEventListener("click", loadBoard);
    boardCancel.addEventListener("click", () => {
      if (boardDirty() && !confirm("Discard unsaved board edits?")) return;
      resetBoardEditor();
      boardStatus.textContent = "";
    });
    async function readBoardImage(file) {
      if (file.size === 0 || file.size > 2 * 1024 * 1024) {
        throw new Error(`${file.name}: image must be between 1 byte and 2 MiB.`);
      }
      if (file.name.length > 255) throw new Error("Image filename exceeds 255 characters.");
      const signature = new Uint8Array(await file.slice(0, 12).arrayBuffer());
      let mediaType;
      if (signature.length >= 8 && [137, 80, 78, 71, 13, 10, 26, 10].every((v, i) => signature[i] === v)) {
        mediaType = "image/png";
      } else if (signature.length >= 3 && signature[0] === 255 && signature[1] === 216 && signature[2] === 255) {
        mediaType = "image/jpeg";
      } else if (signature.length >= 6 && ["GIF87a", "GIF89a"].includes(String.fromCharCode(...signature.slice(0, 6)))) {
        mediaType = "image/gif";
      } else if (signature.length >= 12 && String.fromCharCode(...signature.slice(0, 4)) === "RIFF" &&
                 String.fromCharCode(...signature.slice(8, 12)) === "WEBP") {
        mediaType = "image/webp";
      } else {
        throw new Error(`${file.name}: unsupported image format.`);
      }
      const data = await new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onerror = () => reject(new Error(`Could not read ${file.name}.`));
        reader.onabort = () => reject(new Error(`Reading ${file.name} was interrupted.`));
        reader.onload = () => resolve(reader.result.split(",", 2)[1]);
        reader.readAsDataURL(file);
      });
      return { name: file.name, media_type: mediaType, data };
    }

    document.getElementById("board-form").addEventListener("submit", async (event) => {
      event.preventDefault();
      if (boardSaving) return;
      if (!boardInput.value.trim()) {
        boardStatus.textContent = "Board note must not be blank.";
        return;
      }
      const version = sessionVersion;
      const editing = boardEdit;
      const payload = { header: boardHeader.value, content: boardInput.value, visible: boardVisible.checked };
      if (editing) payload.revision = editing.revision;
      boardSaving = true;
      boardInput.disabled = true;
      boardHeader.disabled = true;
      boardImages.disabled = true;
      for (const checkbox of boardExistingImages.querySelectorAll("input")) checkbox.disabled = true;
      boardVisible.disabled = true;
      boardSave.disabled = true;
      boardCancel.disabled = true;
      boardStatus.textContent = "Saving board note...";
      try {
        const removed = new Set(Array.from(boardExistingImages.querySelectorAll("input:checked"),
          (checkbox) => Number(checkbox.value)));
        const kept = boardAttachments.filter((_, index) => !removed.has(index));
        const files = Array.from(boardImages.files);
        if (kept.length + files.length > 5) throw new Error("A note can have at most 5 images.");
        payload.images = [...kept, ...await Promise.all(files.map(readBoardImage))];
        if (version !== sessionVersion) return;
        const response = await fetch(`${backendOrigin}/api/board${editing ? `/${encodeURIComponent(editing.id)}` : ""}`, {
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
          throw new Error(result.message || `Saving board note failed (${response.status}).`);
        }
        if (version !== sessionVersion) return;
        resetBoardEditor();
        await loadBoard();
      } catch (error) {
        if (version !== sessionVersion) return;
        console.error("Could not save board note:", error);
        boardStatus.textContent = `${error.message} Save may have succeeded. Your edits are retained; refresh the board before retrying.`;
      } finally {
        if (version === sessionVersion) {
          boardSaving = false;
          boardInput.disabled = false;
          boardHeader.disabled = false;
          boardImages.disabled = false;
          for (const checkbox of boardExistingImages.querySelectorAll("input")) checkbox.disabled = false;
          boardVisible.disabled = false;
          boardSave.disabled = false;
          boardCancel.disabled = false;
        }
      }
    });
