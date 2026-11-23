    const bestiaryStatus = document.getElementById("bestiary-status");
    const bestiaryDetailStatus = document.getElementById("bestiary-detail-status");
    const bestiaryCount = document.getElementById("bestiary-count");
    const bestiaryDetail = document.getElementById("bestiary-detail");
    const bestiaryResults = document.getElementById("bestiary-results");
    const bestiaryName = document.getElementById("bestiary-name");
    const bestiaryAdd = document.getElementById("bestiary-add");
    const bestiaryCombatantName = document.getElementById("bestiary-combatant-name");
    const bestiaryInitiative = document.getElementById("bestiary-initiative");
    const bestiaryInitiativeRoll = document.getElementById("bestiary-initiative-roll");
    const bestiaryReroll = document.getElementById("bestiary-reroll");
    const bestiaryAddSubmit = document.getElementById("bestiary-add-submit");
    const bestiaryHitPoints = document.getElementById("bestiary-hit-points");
    const bestiaryAddStatus = document.getElementById("bestiary-add-status");
    const bestiaryCopy = document.getElementById("bestiary-copy");
    const bestiaryFilters = {
      type: document.getElementById("bestiary-type"),
      challenge_rating: document.getElementById("bestiary-rating"),
      size: document.getElementById("bestiary-size"),
      document__title: document.getElementById("bestiary-source"),
    };
    let bestiaryEntries = [];
    let bestiaryLoaded = false;
    let bestiaryLoadVersion = 0;
    let bestiaryDetailVersion = 0;
    let bestiaryFrame = null;
    let bestiarySelectedSlug = null;
    let bestiaryAdding = false;
    let bestiaryInitiativeBonus = null;
    let bestiaryInitiativeBonusSource = null;
    let bestiaryCopyData = null;

    function clearBestiaryAdd() {
      bestiaryAdd.hidden = true;
      bestiaryCopy.hidden = true;
      bestiaryCopyData = null;
      bestiaryAdd.reset();
      bestiaryInitiativeBonus = null;
      bestiaryInitiativeBonusSource = null;
      bestiaryInitiative.value = "";
      bestiaryInitiative.disabled = true;
      bestiaryReroll.disabled = true;
      bestiaryAddSubmit.disabled = true;
      bestiaryInitiativeRoll.textContent = "";
      bestiaryHitPoints.textContent = "";
      bestiaryAddStatus.textContent = "";
    }

    function clearBestiaryDetail() {
      if (bestiaryFrame) bestiaryFrame.disconnect();
      bestiaryFrame = null;
      bestiaryDetail.replaceChildren();
    }

    function resetBestiary() {
      bestiaryLoadVersion++;
      bestiaryDetailVersion++;
      bestiaryEntries = [];
      bestiaryLoaded = false;
      bestiarySelectedSlug = null;
      bestiaryAdding = false;
      clearBestiaryAdd();
      bestiaryName.value = "";
      for (const select of Object.values(bestiaryFilters)) select.replaceChildren(new Option("All", ""));
      bestiaryResults.replaceChildren();
      bestiaryCount.textContent = "";
      bestiaryStatus.textContent = "";
      bestiaryDetailStatus.textContent = "Select a creature to see its statblock.";
      clearBestiaryDetail();
      clearBestiaryAdd();
    }

    function abbreviateBestiarySource(source) {
      const words = source.match(/[\p{L}\p{N}]+/gu) || [];
      if (words.length <= 1) return source;
      return words.map((word) => /^\p{N}/u.test(word) ? word : Array.from(word)[0]).join("");
    }

    function filterBestiary() {
      const name = bestiaryName.value.trim().toLocaleLowerCase();
      const matches = bestiaryEntries.filter((entry) =>
        entry.name.toLocaleLowerCase().includes(name) &&
        Object.entries(bestiaryFilters).every(([key, select]) => !select.value || select.value === entry[key])
      );
      bestiaryCount.textContent = `${matches.length} creatures found.`;
      if (bestiarySelectedSlug && !matches.some((entry) => entry.slug === bestiarySelectedSlug)) {
        bestiarySelectedSlug = null;
        clearBestiaryAdd();
        bestiaryDetailVersion++;
        clearBestiaryDetail();
        bestiaryDetailStatus.textContent = "Select a creature to see its statblock.";
      }
      const rows = document.createDocumentFragment();
      for (const entry of matches) {
        const row = document.createElement("tr");
        const nameCell = document.createElement("td");
        const button = document.createElement("button");
        button.type = "button";
        button.dataset.slug = entry.slug;
        button.textContent = entry.name;
        button.setAttribute("aria-pressed", String(entry.slug === bestiarySelectedSlug));
        row.classList.toggle("is-selected", entry.slug === bestiarySelectedSlug);
        nameCell.append(button);
        row.append(nameCell);
        for (const value of [entry.challenge_rating, entry.type, entry.size]) {
          const cell = document.createElement("td");
          cell.textContent = value;
          row.append(cell);
        }
        const sourceCell = document.createElement("td");
        const source = document.createElement("abbr");
        source.textContent = abbreviateBestiarySource(entry.document__title);
        source.title = entry.document__title;
        source.setAttribute("aria-label", entry.document__title);
        sourceCell.append(source);
        row.append(sourceCell);
        rows.append(row);
      }
      bestiaryResults.replaceChildren(rows);
      bestiaryResults.parentElement.scrollTop = 0;
    }

    async function bestiaryRequest(path) {
      const response = await fetch(`${backendOrigin}${path}`, {
        headers: { "Authorization": `Bearer ${token}`, "ngrok-skip-browser-warning": "true" },
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.message || `Request failed (${response.status}).`);
      return data;
    }

    async function loadBestiary() {
      const version = sessionVersion;
      const loadVersion = ++bestiaryLoadVersion;
      bestiaryDetailVersion++;
      bestiaryLoaded = false;
      bestiaryEntries = [];
      bestiarySelectedSlug = null;
      clearBestiaryAdd();
      bestiaryCount.textContent = "";
      bestiaryResults.replaceChildren();
      clearBestiaryDetail();
      bestiaryDetailStatus.textContent = "Select a creature to see its statblock.";
      bestiaryStatus.textContent = "Loading bestiary...";
      try {
        const data = await bestiaryRequest("/api/bestiary");
        if (version !== sessionVersion || loadVersion !== bestiaryLoadVersion) return;
        if (!Array.isArray(data.creatures) || data.creatures.some((entry) =>
          !entry || !["slug", "name", "type", "challenge_rating", "size", "document__title"]
            .every((key) => typeof entry[key] === "string") ||
          typeof entry.cr !== "number" || !Number.isFinite(entry.cr))) {
          throw new Error("Invalid bestiary response.");
        }
        bestiaryEntries = data.creatures;
        for (const [key, select] of Object.entries(bestiaryFilters)) {
          const previous = select.value;
          const values = [...new Set(bestiaryEntries.map((entry) => entry[key]))];
          const ratings = new Map(bestiaryEntries.map((entry) => [entry.challenge_rating, entry.cr]));
          values.sort(key === "challenge_rating"
            ? (a, b) => ratings.get(a) - ratings.get(b) || a.localeCompare(b)
            : (a, b) => a.localeCompare(b));
          select.replaceChildren(new Option("All", ""));
          for (const value of values) select.add(new Option(value, value));
          if (values.includes(previous)) select.value = previous;
        }
        bestiaryLoaded = true;
        bestiaryStatus.textContent = bestiaryEntries.length ? "" : "The bestiary is empty.";
        filterBestiary();
      } catch (error) {
        if (version !== sessionVersion || loadVersion !== bestiaryLoadVersion) return;
        console.error("Could not load bestiary:", error);
        bestiaryStatus.textContent = `Could not load bestiary: ${error.message}`;
        bestiaryCount.textContent = "";
      }
    }

    function renderBestiaryCreature(display) {
      bestiaryFrame = createStatblockFrame(display, () => {
        bestiaryDetailStatus.textContent = "Could not display the creature stat block.";
      });
      bestiaryDetail.replaceChildren(bestiaryFrame.frame);
    }

    async function loadBestiaryCreature(slug) {
      bestiarySelectedSlug = slug;
      clearBestiaryAdd();
      const entry = bestiaryEntries.find((candidate) => candidate.slug === slug);
      if (entry) {
        bestiaryAdd.hidden = false;
        bestiaryCombatantName.value = entry.name;
        bestiaryHitPoints.textContent = Number.isInteger(entry.hit_points) && entry.hit_points >= 1 && entry.hit_points <= 1000000
          ? `Starting hit points: ${entry.hit_points}`
          : "This creature has no valid starting hit points for initiative.";
      }
      for (const button of bestiaryResults.querySelectorAll("button[data-slug]")) {
        const selected = button.dataset.slug === slug;
        button.setAttribute("aria-pressed", String(selected));
        button.closest("tr").classList.toggle("is-selected", selected);
      }
      const version = sessionVersion;
      const detailVersion = ++bestiaryDetailVersion;
      clearBestiaryDetail();
      bestiaryDetailStatus.textContent = "Loading creature...";
      try {
        const query = new URLSearchParams({ slug });
        const data = await bestiaryRequest(`/api/bestiary/creature?${query}`);
        if (version !== sessionVersion || detailVersion !== bestiaryDetailVersion) return;
        if (!validStatblockDisplay(data.display) || !Number.isSafeInteger(data.initiative_bonus) ||
            !["initiative", "dexterity"].includes(data.initiative_bonus_source)) {
          throw new Error("Invalid stat block response.");
        }
        renderBestiaryCreature(data.display);
        if (data.creature && typeof data.creature === "object" && !Array.isArray(data.creature) &&
            (data.stored_initiative_bonus === null || Number.isSafeInteger(data.stored_initiative_bonus))) {
          bestiaryCopyData = { ...data.creature, initiative_bonus: data.stored_initiative_bonus };
          bestiaryCopy.hidden = false;
          bestiaryDetailStatus.textContent = "";
        } else {
          bestiaryDetailStatus.textContent =
            "Copy to custom creatures is unavailable: the backend response is missing creature data. Restart the updated backend.";
        }
        bestiaryInitiativeBonus = data.initiative_bonus;
        bestiaryInitiativeBonusSource = data.initiative_bonus_source;
        bestiaryInitiative.disabled = false;
        bestiaryReroll.disabled = false;
        rollBestiaryInitiative();
        bestiaryAddSubmit.disabled = bestiaryAdding || !entry || !Number.isInteger(entry.hit_points) ||
          entry.hit_points < 1 || entry.hit_points > 1000000;
      } catch (error) {
        if (version !== sessionVersion || detailVersion !== bestiaryDetailVersion) return;
        console.error("Could not load creature:", error);
        bestiaryDetailStatus.textContent = `Could not load creature: ${error.message}`;
      }
    }

    function rollBestiaryInitiative() {
      if (bestiaryInitiativeBonus === null) return;
      const roll = Math.floor(Math.random() * 20) + 1;
      const bonus = bestiaryInitiativeBonus;
      bestiaryInitiative.value = String(roll + bonus);
      bestiaryInitiativeRoll.textContent = `Rolled ${roll} ${bonus < 0 ? "-" : "+"} ${Math.abs(bonus)} ` +
        `(${bestiaryInitiativeBonusSource === "initiative" ? "initiative bonus" : "Dexterity modifier"}).`;
    }

    async function openBestiaryCreature(slug) {
      const version = sessionVersion;
      if (!bestiaryLoaded) await loadBestiary();
      if (version !== sessionVersion) return;
      if (!bestiaryLoaded) {
        selectTab(bestiaryTab);
        return;
      }
      bestiaryName.value = "";
      for (const select of Object.values(bestiaryFilters)) select.value = "";
      filterBestiary();
      selectTab(bestiaryTab);
      if (!bestiaryEntries.some((entry) => entry.slug === slug)) {
        bestiaryDetailStatus.textContent = "This creature is no longer in the bestiary.";
        return;
      }
      loadBestiaryCreature(slug);
    }

    bestiaryAdd.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (bestiaryAdding || loggingOut || initiativeSaving) {
        bestiaryAddStatus.textContent = "Wait for the current operation to finish.";
        return;
      }
      if (initiativeDirty) {
        bestiaryAddStatus.textContent = "Save or reload unsaved initiative changes first.";
        return;
      }
      const entry = bestiaryEntries.find((candidate) => candidate.slug === bestiarySelectedSlug);
      const name = bestiaryCombatantName.value.trim();
      const initiative = Number(bestiaryInitiative.value);
      if (bestiaryInitiativeBonus === null || !entry || !name || !bestiaryInitiative.value ||
          !Number.isInteger(initiative) || initiative < -10000 || initiative > 10000 ||
          !Number.isInteger(entry.hit_points) || entry.hit_points < 1 || entry.hit_points > 1000000) {
        bestiaryAddStatus.textContent = "Enter a valid name and initiative; the creature needs valid hit points.";
        return;
      }
      const version = sessionVersion;
      const selectionVersion = bestiaryDetailVersion;
      bestiaryAdding = true;
      bestiaryAddSubmit.disabled = true;
      bestiaryReroll.disabled = true;
      bestiaryAddStatus.textContent = "Adding to initiative...";
      try {
        if (!await loadInitiative()) {
          if (version === sessionVersion && selectionVersion === bestiaryDetailVersion) {
            bestiaryAddStatus.textContent = "Could not load initiative. Save or reload changes and try again.";
          }
          return;
        }
        if (version !== sessionVersion || selectionVersion !== bestiaryDetailVersion) return;
        if (loggingOut || initiativeDirty || initiativeSaving) {
          bestiaryAddStatus.textContent = "Initiative is busy or has unsaved changes. Try again after saving.";
          return;
        }
        if (initiativeData.tracker.combatants.length >= 100) {
          bestiaryAddStatus.textContent = "The current fight already has 100 combatants.";
          return;
        }
        const next = structuredClone(initiativeData);
        next.tracker.combatants.push({
          id: crypto.randomUUID(), name, initiative, current_hp: entry.hit_points,
          max_hp: entry.hit_points, visible: true, dead: false, bestiary_slug: entry.slug,
        });
        const saved = await saveInitiative(next);
        if (version !== sessionVersion || selectionVersion !== bestiaryDetailVersion) return;
        bestiaryAddStatus.textContent = saved
          ? `${name} added to initiative.`
          : `Could not add creature: ${initiativeStatus.textContent}`;
        if (saved) rollBestiaryInitiative();
      } catch (error) {
        if (version === sessionVersion && selectionVersion === bestiaryDetailVersion) {
          console.error("Could not add creature to initiative:", error);
          bestiaryAddStatus.textContent = "Could not add creature to initiative. Check the browser console.";
        }
      } finally {
        if (version === sessionVersion) {
          bestiaryAdding = false;
          const current = bestiaryEntries.find((candidate) => candidate.slug === bestiarySelectedSlug);
          bestiaryAddSubmit.disabled = bestiaryInitiativeBonus === null || !current ||
            !Number.isInteger(current.hit_points) || current.hit_points < 1 || current.hit_points > 1000000;
          bestiaryReroll.disabled = bestiaryInitiativeBonus === null;
        }
      }
    });

    bestiaryName.addEventListener("input", filterBestiary);
    bestiaryCopy.addEventListener("click", () => {
      if (bestiaryCopyData) startCustomDraft(bestiaryCopyData);
    });
    bestiaryInitiative.addEventListener("input", () => { bestiaryInitiativeRoll.textContent = "Initiative entered manually."; });
    bestiaryReroll.addEventListener("click", rollBestiaryInitiative);
    for (const select of Object.values(bestiaryFilters)) select.addEventListener("change", filterBestiary);
    bestiaryResults.addEventListener("click", (event) => {
      const row = event.target.closest("tr");
      const button = row && row.querySelector("button[data-slug]");
      if (button) loadBestiaryCreature(button.dataset.slug);
    });
    document.getElementById("bestiary-refresh").addEventListener("click", loadBestiary);
