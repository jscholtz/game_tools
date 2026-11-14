    function validNote(note) {
      return note && typeof note.id === "string" && typeof note.header === "string" &&
        typeof note.content === "string" && Number.isInteger(note.revision) &&
        (note.updated_at === null ||
          (typeof note.updated_at === "string" && !Number.isNaN(Date.parse(note.updated_at))));
    }

    function renderNote(note, open = false) {
      const details = document.createElement("details");
      details.className = "board-note";
      details.dataset.id = note.id;
      details.open = open;
      const summary = document.createElement("summary");
      summary.textContent = note.header;
      const content = document.createElement("div");
      content.className = "markdown-content";
      content.innerHTML = DOMPurify.sanitize(marked.parse(note.content), {
        USE_PROFILES: { html: true }, FORBID_TAGS: ["style"], FORBID_ATTR: ["style"],
      });
      details.append(summary, content);
      return details;
    }

    function appendNoteDate(details, note) {
      const time = document.createElement("p");
      time.className = "note-date";
      if (note.updated_at === null) {
        time.textContent = "Last saved: unknown";
      } else {
        const date = new Date(note.updated_at);
        const pad = (value) => String(value).padStart(2, "0");
        time.textContent = `Last saved: ${pad(date.getFullYear() % 100)}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
      }
      details.append(time);
    }

    function notesDirty() {
      return notesHeader.value !== notesBaseline.header || notesInput.value !== notesBaseline.content;
    }

    function resetNotesEditor(note = null) {
      notesEdit = note ? { id: note.id, revision: note.revision } : null;
      notesBaseline = { header: note ? note.header : "", content: note ? note.content : "" };
      notesHeader.value = notesBaseline.header;
      notesInput.value = notesBaseline.content;
      setButtonLabel(notesCancel, note ? "Cancel editing" : "Clear editor", "cancel");
    }
