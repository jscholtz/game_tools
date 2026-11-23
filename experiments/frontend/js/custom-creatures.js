    const customForm = document.getElementById("custom-form");
    const customStatus = document.getElementById("custom-status");
    const customList = document.getElementById("custom-list");
    const customListStatus = document.getElementById("custom-list-status");
    const customSearch = document.getElementById("custom-search");
    const customSavedActions = document.getElementById("custom-saved-actions");
    const customPreview = document.getElementById("custom-preview");
    const customAdd = document.getElementById("custom-add");
    const customAddStatus = document.getElementById("custom-add-status");
    const customName = document.getElementById("custom-combatant-name");
    const customInitiative = document.getElementById("custom-initiative");
    const customRoll = document.getElementById("custom-roll");
    const customGroups = [
      ["Identity", [
        ["name", "Name", "text", ""], ["size", "Size", "text", "Medium"],
        ["type", "Type", "text", "humanoid"], ["alignment", "Alignment", "text", ""],
        ["challenge_rating", "Challenge rating", "text", "0"],
      ]],
      ["Combat", [
        ["armor_class", "Armor class", "text", "10"], ["hit_points", "Hit points", "number", 1],
        ["hit_dice", "Hit dice", "text", ""], ["speed", "Speed", "text", "30 ft."],
        ["initiative_bonus", "Initiative bonus (optional)", "number", null],
      ]],
      ["Ability scores", [
        ["strength", "Strength", "number", 10], ["dexterity", "Dexterity", "number", 10],
        ["constitution", "Constitution", "number", 10], ["intelligence", "Intelligence", "number", 10],
        ["wisdom", "Wisdom", "number", 10], ["charisma", "Charisma", "number", 10],
      ]],
      ["Defenses and senses", [
        ["saving_throws", "Saving throws", "text", ""], ["skills", "Skills", "text", ""],
        ["damage_vulnerabilities", "Damage vulnerabilities", "text", ""],
        ["damage_resistances", "Damage resistances", "text", ""],
        ["damage_immunities", "Damage immunities", "text", ""],
        ["condition_immunities", "Condition immunities", "text", ""],
        ["senses", "Senses", "text", ""], ["languages", "Languages", "text", ""],
      ]],
      ["Abilities and actions", [
        ["traits", "Traits", "textarea", ""], ["actions", "Actions", "textarea", ""],
        ["bonus_actions", "Bonus actions", "textarea", ""], ["reactions", "Reactions", "textarea", ""],
        ["legendary_actions", "Legendary actions", "textarea", ""],
        ["lair_actions", "Lair actions", "textarea", ""], ["notes", "Notes", "textarea", ""],
      ]],
    ];
    const customDefinitions = customGroups.flatMap(([, fields]) => fields);
    const customDefaults = Object.fromEntries(customDefinitions.map(([key, , , value]) => [key, value]));
    let customEntries = [];
    let customListLoaded = false;
    let customListVersion = 0;
    let customDetailVersion = 0;
    let customSaving = false;
    let customAdding = false;
    let customCurrent = null;
    let customBaseline = "";
    let customDraft = false;
    let customFrame = null;

    for (const [heading, fields] of customGroups) {
      const fieldset = document.createElement("fieldset");
      fieldset.className = "custom-field-group";
      const legend = document.createElement("legend");
      legend.textContent = heading;
      const grid = document.createElement("div");
      grid.className = "custom-field-grid";
      if (heading === "Abilities and actions") {
        const help = document.createElement("p");
        help.className = "custom-field-help custom-wide";
        help.textContent = "Separate entries with blank lines. Start each with a name and a period to emphasize it.";
        grid.append(help);
      }
      for (const [key, title, type] of fields) {
        const label = document.createElement("label");
        label.textContent = title;
        if (type === "textarea") label.className = "custom-wide";
        const input = document.createElement(type === "textarea" ? "textarea" : "input");
        input.name = key;
        if (type !== "textarea") input.type = type;
        if (type === "number") {
          input.step = "1";
          input.min = key === "initiative_bonus" ? "-10000" : "1";
          input.max = key === "initiative_bonus" ? "10000" : key === "hit_points" ? "1000000" : "1000";
          input.required = key !== "initiative_bonus";
        } else {
          input.maxLength = key === "name" ? 200 : 10000;
          input.required = ["name", "size", "type", "challenge_rating", "armor_class", "speed"].includes(key);
        }
        label.append(input);
        grid.append(label);
      }
      fieldset.append(legend, grid);
      document.getElementById("custom-fields").append(fieldset);
    }

    function customValues() {
      return Object.fromEntries(customDefinitions.map(([key, , type]) => {
        const value = customForm.elements.namedItem(key).value;
        return [key, type === "number" ? (value === "" ? null : Number(value)) : value];
      }));
    }

    function customDirty() {
      return customDraft || JSON.stringify(customValues()) !== customBaseline;
    }

    function confirmCustomDiscard() {
      if (customSaving || customAdding) {
        customStatus.textContent = "Wait for the current operation to finish.";
        return false;
      }
      return customForm.hidden || !customDirty() || confirm("Discard unsaved creature changes?");
    }

    function clearCustomPreview() {
      if (customFrame) customFrame.disconnect();
      customFrame = null;
      customPreview.replaceChildren();
      customSavedActions.hidden = true;
    }

    function resetCustomCreatures() {
      customListVersion++;
      customDetailVersion++;
      customEntries = [];
      customListLoaded = false;
      customSaving = false;
      customAdding = false;
      customCurrent = null;
      customBaseline = "";
      customDraft = false;
      customForm.hidden = true;
      for (const control of customForm.elements) control.disabled = false;
      customForm.reset();
      customSearch.value = "";
      customList.replaceChildren();
      customListStatus.textContent = "";
      customStatus.textContent = "Select a creature or create a new one.";
      clearCustomPreview();
    }

    async function customRequest(path, options = {}) {
      const response = await fetch(`${backendOrigin}${path}`, {
        ...options,
        headers: {
          "Authorization": "Bearer " + token, "ngrok-skip-browser-warning": "true",
          ...(options.body ? { "Content-Type": "application/json" } : {}),
        },
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.message || `Request failed (${response.status}).`);
      return data;
    }

    function renderCustomList() {
      const query = customSearch.value.trim().toLocaleLowerCase();
      const matches = customEntries.filter((entry) => entry.name.toLocaleLowerCase().includes(query));
      customList.replaceChildren();
      for (const entry of matches) {
        const button = document.createElement("button");
        button.type = "button";
        const name = document.createElement("strong");
        name.textContent = entry.name;
        const metadata = document.createElement("span");
        metadata.textContent = `CR ${entry.challenge_rating} · ${entry.type}`;
        button.append(name, metadata);
        button.setAttribute("aria-pressed", String(entry.id === customCurrent?.id));
        button.addEventListener("click", () => openCustomCreature(entry.id));
        customList.append(button);
      }
      customListStatus.textContent = matches.length ? `${matches.length} creatures` : "No creatures found.";
    }

    async function loadCustomList() {
      const version = sessionVersion;
      const loadVersion = ++customListVersion;
      customListStatus.textContent = "Loading creatures...";
      try {
        const data = await customRequest("/api/custom-creatures");
        if (version !== sessionVersion || loadVersion !== customListVersion) return;
        if (!Array.isArray(data.creatures) || data.creatures.some((entry) =>
          !entry || !["id", "name", "type", "challenge_rating"].every((key) => typeof entry[key] === "string"))) {
          throw new Error("Invalid creature list.");
        }
        customEntries = data.creatures;
        customListLoaded = true;
        renderCustomList();
      } catch (error) {
        if (version !== sessionVersion || loadVersion !== customListVersion) return;
        console.error("Could not load custom creatures:", error);
        customListStatus.textContent = `Could not load creatures: ${error.message}`;
      }
    }

    function fillCustomForm(values) {
      for (const [key] of customDefinitions) {
        customForm.elements.namedItem(key).value = values[key] ?? "";
      }
    }

    function startCustomDraft(values = customDefaults) {
      if (!confirmCustomDiscard()) return;
      customDetailVersion++;
      customCurrent = null;
      customDraft = true;
      fillCustomForm(values);
      customBaseline = JSON.stringify(customValues());
      customForm.hidden = false;
      document.getElementById("custom-editor-heading").textContent = "New creature";
      customStatus.textContent = "New draft. Save to add it to your creatures.";
      clearCustomPreview();
      renderCustomList();
      selectTab(customCreaturesTab);
    }

    function rollCustomInitiative() {
      if (!customCurrent) return;
      const creature = customCurrent.creature;
      const bonus = creature.initiative_bonus ?? Math.floor((creature.dexterity - 10) / 2);
      const die = Math.floor(Math.random() * 20) + 1;
      customInitiative.value = String(die + bonus);
      customRoll.textContent = `Rolled ${die} ${bonus < 0 ? "-" : "+"} ${Math.abs(bonus)} ` +
        `(${creature.initiative_bonus === null ? "Dexterity modifier" : "initiative bonus"}).`;
    }

    function showCustomCreature(data) {
      if (!data.creature || !validStatblockDisplay(data.display)) throw new Error("Invalid creature response.");
      customCurrent = { id: data.id, creature: data.creature };
      fillCustomForm(data.creature);
      customBaseline = JSON.stringify(customValues());
      customDraft = false;
      customForm.hidden = true;
      document.getElementById("custom-editor-heading").textContent = "Edit creature";
      clearCustomPreview();
      customFrame = createStatblockFrame(data.display, () => {
        customStatus.textContent = "Could not display the creature statblock.";
      });
      customPreview.append(customFrame.frame);
      customSavedActions.hidden = false;
      customName.value = data.creature.name;
      customAddStatus.textContent = "";
      rollCustomInitiative();
      renderCustomList();
    }

    async function openCustomCreature(id) {
      if (!confirmCustomDiscard()) return;
      selectTab(customCreaturesTab);
      const version = sessionVersion;
      const detailVersion = ++customDetailVersion;
      const previousValues = JSON.stringify(customValues());
      customStatus.textContent = "Loading creature...";
      try {
        const data = await customRequest(`/api/custom-creatures/${encodeURIComponent(id)}`);
        if (version !== sessionVersion || detailVersion !== customDetailVersion) return;
        if (previousValues !== JSON.stringify(customValues())) {
          customStatus.textContent = "Creature not opened because the current draft changed while loading.";
          return;
        }
        showCustomCreature(data);
        customStatus.textContent = "";
      } catch (error) {
        if (version !== sessionVersion || detailVersion !== customDetailVersion) return;
        console.error("Could not load custom creature:", error);
        customStatus.textContent = `Could not load creature: ${error.message}`;
      }
    }

    customForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (customSaving || customAdding || loggingOut) return;
      const version = sessionVersion;
      const id = customCurrent?.id;
      const values = customValues();
      if (id) values.revision = customCurrent.creature.revision;
      customDetailVersion++;
      customSaving = true;
      for (const control of customForm.elements) control.disabled = true;
      customStatus.textContent = "Saving creature...";
      try {
        const path = id ? `/api/custom-creatures/${encodeURIComponent(id)}` : "/api/custom-creatures";
        const data = await customRequest(path, { method: id ? "PUT" : "POST", body: JSON.stringify(values) });
        if (version !== sessionVersion) return;
        showCustomCreature(data);
        customStatus.textContent = "Creature saved.";
        loadCustomList();
      } catch (error) {
        if (version !== sessionVersion) return;
        console.error("Could not save custom creature:", error);
        customStatus.textContent = `Could not save creature: ${error.message}`;
      } finally {
        if (version === sessionVersion) {
          customSaving = false;
          for (const control of customForm.elements) control.disabled = false;
        }
      }
    });

    customAdd.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (!customCurrent || customSaving || customAdding || loggingOut) return;
      if (customDirty()) {
        customAddStatus.textContent = "Save your creature changes before adding it.";
        return;
      }
      if (initiativeDirty || initiativeSaving) {
        customAddStatus.textContent = "Save or reload unsaved initiative changes first.";
        return;
      }
      const name = customName.value.trim();
      const initiative = Number(customInitiative.value);
      if (!name || !customInitiative.value || !Number.isInteger(initiative) || initiative < -10000 || initiative > 10000) {
        customAddStatus.textContent = "Enter a valid name and initiative.";
        return;
      }
      const version = sessionVersion;
      const creature = customCurrent;
      customAdding = true;
      customAddStatus.textContent = "Adding to initiative...";
      try {
        if (!await loadInitiative()) throw new Error("Could not load initiative. Save or reload changes and try again.");
        if (version !== sessionVersion) return;
        if (loggingOut || initiativeDirty || initiativeSaving) throw new Error("Initiative is busy or has unsaved changes.");
        if (initiativeData.tracker.combatants.length >= 100) throw new Error("The current fight already has 100 combatants.");
        const next = structuredClone(initiativeData);
        const hp = creature.creature.hit_points;
        next.tracker.combatants.push({
          id: crypto.randomUUID(), name, initiative, current_hp: hp, max_hp: hp,
          visible: true, dead: false, custom_creature_id: creature.id,
        });
        if (!await saveInitiative(next)) throw new Error(initiativeStatus.textContent || "Could not save initiative.");
        if (version !== sessionVersion) return;
        customAddStatus.textContent = `${name} added to initiative.`;
        rollCustomInitiative();
      } catch (error) {
        if (version !== sessionVersion) return;
        console.error("Could not add custom creature:", error);
        customAddStatus.textContent = error.message;
      } finally {
        if (version === sessionVersion) customAdding = false;
      }
    });

    customSearch.addEventListener("input", renderCustomList);
    document.getElementById("custom-refresh").addEventListener("click", loadCustomList);
    document.getElementById("custom-new").addEventListener("click", () => startCustomDraft());
    document.getElementById("custom-edit").addEventListener("click", () => {
      if (!customCurrent || customSaving || customAdding || loggingOut) return;
      customForm.hidden = false;
      customSavedActions.hidden = true;
      customStatus.textContent = "Editing creature.";
      customForm.elements.namedItem("name").focus();
    });
    document.getElementById("custom-cancel").addEventListener("click", () => {
      if (!confirmCustomDiscard()) return;
      customDetailVersion++;
      customForm.hidden = true;
      customDraft = false;
      if (customCurrent) {
        fillCustomForm(customCurrent.creature);
        customSavedActions.hidden = false;
        customStatus.textContent = "";
      } else {
        clearCustomPreview();
        customStatus.textContent = "Select a creature or create a new one.";
      }
      renderCustomList();
    });
    document.getElementById("custom-reroll").addEventListener("click", rollCustomInitiative);
    customInitiative.addEventListener("input", () => { customRoll.textContent = "Initiative entered manually."; });
