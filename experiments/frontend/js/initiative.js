    function updateInitiativeControls() {
      for (const button of initiativePanel.querySelectorAll("[data-initiative-action]")) {
        button.disabled = !initiativeData || initiativeSaving || initiativeDirty || loggingOut;
      }
      for (const input of initiativeAdd.querySelectorAll("input")) input.disabled = initiativeSaving || loggingOut;
      for (const input of initiativeEncounterForm.querySelectorAll("input")) input.disabled = initiativeSaving || loggingOut;
      initiativeFields.disabled = !initiativeData || initiativeSaving || loggingOut;
      document.getElementById("initiative-save").disabled = !initiativeData || initiativeSaving || !initiativeDirty || loggingOut;
      document.getElementById("initiative-refresh").disabled = initiativeSaving || loggingOut;
    }

    function initiativeChanged() {
      if (initiativeSaving) {
        initiativeRefreshPending = true;
      } else if (initiativeDirty) {
        initiativeStatus.textContent = "Initiative changed elsewhere. Copy your edits, then reload before saving.";
      } else if (initiativeData) {
        loadInitiative();
      }
    }

    async function loadInitiative() {
      if (initiativeSaving || initiativeDirty) return;
      const version = sessionVersion;
      const loadVersion = ++initiativeLoadVersion;
      try {
        const response = await fetch(`${backendOrigin}/api/initiative`, {
          headers: { "Authorization": "Bearer " + token, "ngrok-skip-browser-warning": "true" },
        });
        if (!response.ok) throw new Error(`Loading initiative failed (${response.status}).`);
        const data = await response.json();
        if (version !== sessionVersion || loadVersion !== initiativeLoadVersion || initiativeDirty || initiativeSaving) return;
        initiativeData = data.initiative;
        renderInitiative();
        initiativeStatus.textContent = "";
      } catch (error) {
        if (version !== sessionVersion || loadVersion !== initiativeLoadVersion) return;
        console.error("Could not load initiative:", error);
        initiativeStatus.textContent = "Could not load initiative. Use Reload initiative to retry.";
      }
    }

    async function saveInitiative(next) {
      if (initiativeSaving || !initiativeData) return false;
      const version = sessionVersion;
      initiativeLoadVersion++;
      initiativeSaving = true;
      updateInitiativeControls();
      let saved = false;
      try {
        const response = await fetch(`${backendOrigin}/api/initiative`, {
          method: "PUT",
          headers: {
            "Authorization": "Bearer " + token, "Content-Type": "application/json",
            "ngrok-skip-browser-warning": "true",
          },
          body: JSON.stringify(next),
        });
        const data = await response.json();
        if (version !== sessionVersion) return false;
        if (!response.ok) throw new Error(data.message || `Saving initiative failed (${response.status}).`);
        initiativeData = data.initiative;
        initiativeDirty = false;
        renderInitiative();
        initiativeStatus.textContent = "Initiative saved.";
        saved = true;
      } catch (error) {
        if (version !== sessionVersion) return false;
        console.error("Could not save initiative:", error);
        initiativeStatus.textContent = error.message || "Could not save initiative.";
      } finally {
        if (version === sessionVersion) {
          initiativeSaving = false;
          updateInitiativeControls();
          if (initiativeRefreshPending) {
            initiativeRefreshPending = false;
            if (saved) loadInitiative();
          }
        }
      }
      return saved;
    }

    function initiativeButton(label, action, icon) {
      const button = document.createElement("button");
      button.type = "button";
      setButtonLabel(button, label, icon);
      button.dataset.initiativeAction = "";
      button.addEventListener("click", action);
      return button;
    }

    function renderInitiative() {
      initiativeEditList.replaceChildren();
      initiativePlayerList.replaceChildren();
      initiativeEncounters.replaceChildren();
      const tracker = initiativeData.tracker;
      if (initiativeDm.hidden) {
        if (!tracker.combatants.length) initiativePlayerList.textContent = "No visible combatants.";
        for (const actor of tracker.combatants) {
          const item = document.createElement("p");
          item.textContent = `${actor.name} — initiative ${actor.initiative}${actor.dead ? " — defeated" : ""}` +
            (actor.id === tracker.current_turn_id ? " — current turn" : "");
          if (actor.id === tracker.current_turn_id) item.className = "initiative-current";
          initiativePlayerList.append(item);
        }
      } else {
        if (!tracker.combatants.length) initiativeEditList.textContent = "No combatants yet.";
        for (const [index, actor] of tracker.combatants.entries()) {
          const group = document.createElement("fieldset");
          group.className = "initiative-combatant";
          const legend = document.createElement("legend");
          legend.textContent = `${actor.name}${actor.id === tracker.current_turn_id ? " — current turn" : ""}`;
          group.append(legend);
          const fields = document.createElement("div");
          fields.className = "initiative-combatant-fields";
          group.append(fields);
          if (actor.id === tracker.current_turn_id) group.classList.add("initiative-current");
          for (const [key, title, type, min, max] of [
            ["name", "Name", "text", null, 200],
            ["initiative", "Initiative", "number", -10000, 10000],
            ["current_hp", "Current HP", "number", 0, 1000000],
            ["max_hp", "Max HP", "number", 1, 1000000],
            ["visible", "Visible", "checkbox", null, null],
            ["dead", "Defeated", "checkbox", null, null],
          ]) {
            const label = document.createElement("label");
            if (key === "name") label.className = "initiative-name";
            if (type === "checkbox") label.className = "initiative-toggle";
            const input = document.createElement("input");
            input.type = type;
            input.dataset.index = String(index);
            input.dataset.field = key;
            if (type === "checkbox") {
              input.checked = actor[key];
              label.append(input, document.createTextNode(` ${title}`));
            } else {
              input.value = actor[key];
              input.required = true;
              if (type === "text") input.maxLength = max;
              else { input.min = String(min); input.max = String(max); input.step = "1"; }
              label.append(document.createTextNode(title), input);
            }
            fields.append(label);
          }
          fields.append(initiativeButton("Remove combatant", () => {
            if (!confirm(`Remove ${actor.name} from the live tracker?`)) return;
            const next = structuredClone(initiativeData);
            next.tracker.combatants.splice(index, 1);
            if (next.tracker.current_turn_id === actor.id) next.tracker.current_turn_id = null;
            saveInitiative(next);
          }, "remove"));
          initiativeEditList.append(group);
        }
        for (const encounter of initiativeData.encounters) {
          const item = document.createElement("div");
          item.className = "initiative-encounter";
          const label = document.createElement("strong");
          label.textContent = encounter.name;
          item.append(label);
          item.append(initiativeButton("Load", () => {
            if (!confirm(`Replace the live tracker with ${encounter.name}?`)) return;
            const next = structuredClone(initiativeData);
            next.tracker = structuredClone(encounter.tracker);
            saveInitiative(next);
          }, "load"));
          item.append(initiativeButton("Overwrite", () => {
            if (!confirm(`Overwrite ${encounter.name} with the live tracker?`)) return;
            const next = structuredClone(initiativeData);
            next.encounters.find((entry) => entry.id === encounter.id).tracker = structuredClone(next.tracker);
            saveInitiative(next);
          }, "overwrite"));
          item.append(initiativeButton("Delete", () => {
            if (!confirm(`Delete saved encounter ${encounter.name}?`)) return;
            const next = structuredClone(initiativeData);
            next.encounters = next.encounters.filter((entry) => entry.id !== encounter.id);
            saveInitiative(next);
          }, "remove"));
          initiativeEncounters.append(item);
        }
        if (!initiativeData.encounters.length) initiativeEncounters.textContent = "No saved encounters.";
      }
      updateInitiativeControls();
    }

    initiativeEdit.addEventListener("input", () => {
      initiativeDirty = true;
      updateInitiativeControls();
    });
    initiativeEdit.addEventListener("submit", (event) => {
      event.preventDefault();
      if (!initiativeData || initiativeSaving || !initiativeDirty) return;
      const next = structuredClone(initiativeData);
      for (const input of initiativeEditList.querySelectorAll("input")) {
        const value = input.type === "checkbox" ? input.checked :
          input.type === "number" ? Number(input.value) : input.value.trim();
        next.tracker.combatants[Number(input.dataset.index)][input.dataset.field] = value;
      }
      if (next.tracker.combatants.some((actor) => !actor.name || actor.current_hp > actor.max_hp)) {
        initiativeStatus.textContent = "Enter names and ensure current hit points do not exceed maximum hit points.";
        return;
      }
      if (next.tracker.combatants.some((actor) => actor.id === next.tracker.current_turn_id && actor.dead)) {
        next.tracker.current_turn_id = null;
      }
      saveInitiative(next);
    });
    initiativeAdd.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (!initiativeData || initiativeDirty || initiativeSaving) return;
      const name = document.getElementById("initiative-name").value.trim();
      if (!name) { initiativeStatus.textContent = "Enter a combatant name."; return; }
      const next = structuredClone(initiativeData);
      const hp = Number(document.getElementById("initiative-hp").value);
      next.tracker.combatants.push({
        id: crypto.randomUUID(), name, initiative: Number(document.getElementById("initiative-value").value),
        current_hp: hp, max_hp: hp, visible: true, dead: false,
      });
      if (await saveInitiative(next)) initiativeAdd.reset();
    });
    document.getElementById("initiative-next").addEventListener("click", () => {
      if (!initiativeData || initiativeDirty || initiativeSaving) return;
      const next = structuredClone(initiativeData);
      const living = next.tracker.combatants.filter((actor) => !actor.dead);
      if (!living.length) { initiativeStatus.textContent = "No living combatants."; return; }
      const index = living.findIndex((actor) => actor.id === next.tracker.current_turn_id);
      next.tracker.current_turn_id = living[(index + 1) % living.length].id;
      saveInitiative(next);
    });
    document.getElementById("initiative-sort").addEventListener("click", () => {
      if (!initiativeData || initiativeDirty || initiativeSaving) return;
      const next = structuredClone(initiativeData);
      next.tracker.combatants.sort((a, b) => b.initiative - a.initiative);
      saveInitiative(next);
    });
    initiativeEncounterForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (!initiativeData || initiativeDirty || initiativeSaving) return;
      const name = document.getElementById("initiative-encounter-name").value.trim();
      if (!name) { initiativeStatus.textContent = "Enter an encounter name."; return; }
      const next = structuredClone(initiativeData);
      next.encounters.push({ id: crypto.randomUUID(), name, tracker: structuredClone(next.tracker) });
      if (await saveInitiative(next)) initiativeEncounterForm.reset();
    });
    document.getElementById("initiative-refresh").addEventListener("click", () => {
      if (initiativeDirty && !confirm("Discard unsaved combatant changes and reload initiative?")) return;
      initiativeDirty = false;
      loadInitiative();
    });

