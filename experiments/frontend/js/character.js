    const characterTextSpecs = [
      ["name", "Character name"], ["race", "Race"], ["gender", "Gender"],
      ["character_description", "Character description (Markdown)"],
      ["background", "Character background"], ["story", "Character story"],
    ];
    const characterNumberSpecs = [
      ["passive_perception", "Passive perception", 0, 10000],
      ["passive_insight", "Passive insight", 0, 10000],
      ["armor_class", "Armor class", 0, 10000], ["max_hp", "Maximum HP", 0, 1000000],
      ["initiative_bonus", "Initiative bonus", -10000, 10000],
      ["strength", "Strength", 0, 1000], ["dexterity", "Dexterity", 0, 1000],
      ["constitution", "Constitution", 0, 1000], ["intelligence", "Intelligence", 0, 1000],
      ["wisdom", "Wisdom", 0, 1000], ["charisma", "Charisma", 0, 1000],
      ["speed_walk", "Walking speed (ft)", 0, 10000], ["speed_fly", "Flying speed (ft)", 0, 10000],
      ["speed_swim", "Swimming speed (ft)", 0, 10000], ["speed_climb", "Climbing speed (ft)", 0, 10000],
      ["speed_burrow", "Burrowing speed (ft)", 0, 10000],
    ];
    const classSpecs = [
      ["class_name", "Class name"], ["class_url", "Class URL"], ["subclass_name", "Subclass"],
      ["subclass_url", "Subclass URL"], ["levels", "Levels"],
    ];
    const characterStatGroups = [
      ["Combat", ["armor_class", "max_hp", "initiative_bonus"]],
      ["Abilities", ["strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma"]],
      ["Senses", ["passive_perception", "passive_insight"]],
      ["Movement", ["speed_walk", "speed_fly", "speed_swim", "speed_climb", "speed_burrow"]],
    ];

    function characterInput(name, label, options = {}) {
      const wrapper = document.createElement("label");
      wrapper.textContent = label;
      const input = document.createElement(options.multiline ? "textarea" : "input");
      input.name = name;
      if (options.multiline) {
        input.rows = 5;
        input.maxLength = 100000;
      } else {
        input.type = options.numeric ? "number" : "text";
        if (options.numeric) {
          input.min = options.min;
          input.max = options.max;
          input.step = "1";
        } else input.maxLength = options.maxLength || 200;
      }
      if (options.required) input.required = true;
      wrapper.append(input);
      return wrapper;
    }

    function characterEditorGroup(title) {
      const section = document.createElement("section");
      section.className = "character-editor-section";
      const heading = document.createElement("h4");
      heading.textContent = title;
      const fields = document.createElement("div");
      fields.className = "character-grid";
      section.append(heading, fields);
      characterFields.append(section);
      return fields;
    }

    const identityFields = characterEditorGroup("Identity");
    for (const [name, label] of characterTextSpecs.slice(0, 3)) {
      identityFields.append(characterInput(name, label, { required: name === "name" }));
    }
    for (const [title, names] of characterStatGroups) {
      const fields = characterEditorGroup(title);
      for (const [name, label, min, max] of characterNumberSpecs.filter(([key]) => names.includes(key))) {
        fields.append(characterInput(name, label, { numeric: true, min, max }));
      }
    }
    for (const [name, label] of characterTextSpecs.slice(3)) {
      characterTextFields.append(characterInput(name, label, { multiline: true }));
    }

    function addCharacterClass(entry = {}) {
      const group = document.createElement("fieldset");
      const legend = document.createElement("legend");
      legend.textContent = "Class";
      group.append(legend);
      for (const [name, label] of classSpecs) {
        const wrapper = characterInput(name, label, name === "levels" ?
          { numeric: true, min: 1, max: 100 } : { maxLength: name.endsWith("_url") ? 2048 : 200 });
        wrapper.querySelector("input").value = entry[name] ?? "";
        group.append(wrapper);
      }
      const remove = document.createElement("button");
      remove.type = "button";
      remove.textContent = "Remove class";
      addButtonIcon(remove, "remove");
      remove.addEventListener("click", () => group.remove());
      group.append(remove);
      characterClasses.append(group);
    }

    function characterDraft() {
      const fields = {};
      for (const [name] of characterTextSpecs) fields[name] = characterForm.elements[name].value;
      for (const [name] of characterNumberSpecs) {
        const value = characterForm.elements[name].value;
        fields[name] = value === "" ? null : Number(value);
      }
      fields.classes = Array.from(characterClasses.querySelectorAll("fieldset"), (group) => {
        const entry = {};
        for (const [name] of classSpecs) {
          const value = group.querySelector(`[name="${name}"]`).value;
          entry[name] = name === "levels" ? (value === "" ? null : Number(value)) : value;
        }
        return entry;
      });
      return fields;
    }

    function characterDirty() {
      return JSON.stringify(characterDraft()) !== characterBaseline ||
        characterPortrait.files.length > 0 || characterRemovePortrait.checked;
    }

    function renderCharacterSheet(characterData, characterDisplay) {
      characterDisplay.replaceChildren();
      if (!characterData.name) {
        characterDisplay.textContent = "No character saved yet.";
        return;
      }
      const sheet = document.createElement("div");
      sheet.className = "character-sheet";
      const hero = document.createElement("div");
      hero.className = "character-hero";
      if (characterData.portrait) {
        const image = document.createElement("img");
        image.src = `data:${characterData.portrait.media_type};base64,${characterData.portrait.data}`;
        image.alt = `Portrait of ${characterData.name}`;
        image.addEventListener("error", () => { characterStatus.textContent = "Could not display portrait."; });
        hero.append(image);
      }
      const identity = document.createElement("div");
      const heading = document.createElement("h4");
      heading.textContent = characterData.name;
      identity.append(heading);
      const traits = characterTextSpecs.slice(1, 3)
        .filter(([name]) => characterData[name])
        .map(([name, label]) => `${label}: ${characterData[name]}`);
      if (traits.length) {
        const p = document.createElement("p");
        p.textContent = traits.join(" · ");
        identity.append(p);
      }
      for (const entry of characterData.classes) {
        const p = document.createElement("p");
        for (const [name, url, label] of [
          ["class_name", "class_url", "Class"], ["subclass_name", "subclass_url", "Subclass"],
        ]) {
          if (!entry[name]) continue;
          const span = entry[url] ? document.createElement("a") : document.createElement("span");
          span.textContent = `${label}: ${entry[name]}`;
          if (entry[url]) {
            span.href = entry[url];
            span.target = "_blank";
            span.rel = "noopener noreferrer";
          }
          p.append(span, document.createTextNode(" "));
        }
        if (entry.levels !== null) p.append(document.createTextNode(`Level ${entry.levels}`));
        identity.append(p);
      }
      hero.append(identity);
      sheet.append(hero);
      for (const [group, names] of characterStatGroups) {
        const section = document.createElement("section");
        section.className = "character-section";
        const title = document.createElement("h4");
        title.textContent = group;
        const stats = document.createElement("div");
        stats.className = "character-stats";
        for (const [name, label] of characterNumberSpecs.filter(([key]) => names.includes(key))) {
          const item = document.createElement("div");
          item.className = "character-stat";
          const caption = document.createElement("span");
          caption.textContent = label;
          const value = document.createElement("strong");
          value.textContent = characterData[name] ?? "Not set";
          item.append(caption, value);
          stats.append(item);
        }
        section.append(title, stats);
        sheet.append(section);
      }
      for (const [name, label] of characterTextSpecs.slice(3)) {
        if (!characterData[name]) continue;
        const section = document.createElement("section");
        section.className = "character-section character-prose";
        const title = document.createElement("h4");
        title.textContent = label;
        const content = document.createElement("div");
        if (name === "character_description") {
          content.className = "markdown-content";
          if (typeof marked === "undefined" || typeof DOMPurify === "undefined") {
            content.textContent = characterData[name];
            characterStatus.textContent = "Markdown renderer unavailable; description shown as text.";
          } else {
            content.innerHTML = DOMPurify.sanitize(marked.parse(characterData[name]), {
              USE_PROFILES: { html: true }, FORBID_TAGS: ["style"], FORBID_ATTR: ["style"],
            });
          }
        } else {
          const p = document.createElement("p");
          p.textContent = characterData[name];
          content.append(p);
        }
        section.append(title, content);
        sheet.append(section);
      }
      characterDisplay.append(sheet);
    }

    function renderCharacter() {
      renderCharacterSheet(characterData, characterDisplay);
    }

    async function loadCharacters() {
      const version = sessionVersion;
      const loadVersion = ++characterLoadVersion;
      characterStatus.textContent = "Loading player characters...";
      try {
        const response = await fetch(`${backendOrigin}/api/characters`, {
          headers: { "Authorization": "Bearer " + token, "ngrok-skip-browser-warning": "true" },
        });
        if (!response.ok) throw new Error(`Loading characters failed (${response.status}).`);
        const result = await response.json();
        if (!Array.isArray(result.characters) || result.characters.some((entry) =>
          !entry || typeof entry.username !== "string" ||
          (entry.character !== null && (!entry.character ||
            typeof entry.character.name !== "string" || !Array.isArray(entry.character.classes) ||
            !Number.isInteger(entry.character.revision))))) {
          throw new Error("Invalid characters response.");
        }
        if (version !== sessionVersion || loadVersion !== characterLoadVersion) return;
        const openPlayers = new Set(Array.from(dmCharacterList.querySelectorAll("details[open]"),
          (element) => element.dataset.username));
        const sheets = result.characters.map(({ username, character }) => {
          const section = document.createElement("details");
          section.className = "board-note";
          section.dataset.username = username;
          section.open = openPlayers.has(username);
          const heading = document.createElement("summary");
          heading.textContent = character?.name ? `${character.name} (${username})` : username;
          const sheet = document.createElement("div");
          sheet.className = "character-display";
          if (character) renderCharacterSheet(character, sheet);
          else sheet.textContent = "No character saved yet.";
          section.append(heading, sheet);
          return section;
        });
        dmCharacterList.replaceChildren(...sheets);
        characterStatus.textContent = sheets.length ? "" : "No player accounts found.";
      } catch (error) {
        if (version !== sessionVersion || loadVersion !== characterLoadVersion) return;
        console.error("Could not load player characters:", error);
        characterStatus.textContent = "Could not load player characters. Check your session and connection, then retry.";
      }
    }

    async function loadCharacter() {
      if (!characterForm.hidden && (characterSaving || characterDirty())) {
        characterStatus.textContent = "Cancel or save your edits before reloading.";
        return;
      }
      const version = sessionVersion;
      const loadVersion = ++characterLoadVersion;
      characterStatus.textContent = "Loading character...";
      try {
        const response = await fetch(`${backendOrigin}/api/character`, {
          headers: { "Authorization": "Bearer " + token, "ngrok-skip-browser-warning": "true" },
        });
        if (!response.ok) throw new Error(`Loading character failed (${response.status}).`);
        const result = await response.json();
        if (!result.character || typeof result.character.name !== "string" ||
            !Array.isArray(result.character.classes) || !Number.isInteger(result.character.revision)) {
          throw new Error("Invalid character response.");
        }
        if (version !== sessionVersion || loadVersion !== characterLoadVersion) return;
        characterData = result.character;
        characterForm.hidden = true;
        characterEditButton.disabled = false;
        characterStatus.textContent = "";
        renderCharacter();
      } catch (error) {
        if (version !== sessionVersion || loadVersion !== characterLoadVersion) return;
        console.error("Could not load character:", error);
        characterStatus.textContent = "Could not load character. Check your session and connection, then retry.";
      }
    }

    characterEditButton.addEventListener("click", () => {
      if (!characterData || characterSaving) return;
      characterLoadVersion++;
      for (const [name] of [...characterTextSpecs, ...characterNumberSpecs]) {
        characterForm.elements[name].value = characterData[name] ?? "";
      }
      characterClasses.replaceChildren();
      characterData.classes.forEach(addCharacterClass);
      characterPortrait.value = "";
      characterRemovePortrait.checked = false;
      characterBaseline = JSON.stringify(characterDraft());
      characterForm.hidden = false;
      characterStatus.textContent = "Editing character.";
    });
    document.getElementById("character-add-class").addEventListener("click", () => {
      if (characterClasses.children.length >= 20) {
        characterStatus.textContent = "At most 20 classes are supported.";
        return;
      }
      addCharacterClass();
    });
    document.getElementById("character-cancel").addEventListener("click", () => {
      if (characterSaving || characterDirty() && !confirm("Discard unsaved character changes?")) return;
      characterForm.hidden = true;
      characterStatus.textContent = "";
    });
    characterReloadButton.addEventListener("click", () => {
      if (currentRole === "player") loadCharacter();
      else loadCharacters();
    });
    characterForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (characterSaving || !characterData) return;
      const draft = characterDraft();
      if (!draft.name.trim()) {
        characterStatus.textContent = "Enter a character name.";
        return;
      }
      const version = sessionVersion;
      characterSaving = true;
      characterReloadButton.disabled = true;
      characterEditButton.disabled = true;
      for (const control of characterForm.elements) control.disabled = true;
      characterStatus.textContent = "Saving character...";
      try {
        let portrait = characterRemovePortrait.checked ? null : characterData.portrait;
        if (characterPortrait.files.length) {
          portrait = await readBoardImage(characterPortrait.files[0]);
          if (portrait.media_type === "image/gif") throw new Error("Portrait must be PNG, JPEG or WebP.");
        }
        if (version !== sessionVersion) return;
        const response = await fetch(`${backendOrigin}/api/character`, {
          method: "PUT",
          headers: {
            "Authorization": "Bearer " + token, "Content-Type": "application/json",
            "ngrok-skip-browser-warning": "true",
          },
          body: JSON.stringify({ ...draft, portrait, revision: characterData.revision }),
        });
        const result = await response.json();
        if (!response.ok || result.status !== "success") {
          throw new Error(result.message || `Saving character failed (${response.status}).`);
        }
        if (version !== sessionVersion) return;
        characterData = result.character;
        characterForm.hidden = true;
        characterStatus.textContent = "Character saved.";
        renderCharacter();
      } catch (error) {
        if (version !== sessionVersion) return;
        console.error("Could not save character:", error);
        characterStatus.textContent = `${error.message} Your edits are retained; save may have succeeded.`;
      } finally {
        if (version === sessionVersion) {
          characterSaving = false;
          characterReloadButton.disabled = false;
          characterEditButton.disabled = false;
          for (const control of characterForm.elements) control.disabled = false;
        }
      }
    });
