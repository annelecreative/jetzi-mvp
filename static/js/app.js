(function () {
  const form = document.getElementById("alert-form");
  const maxDestinationsFromData = Number(form?.dataset.allowedDestinations || "");
  const MAX_DESTINATIONS =
    Number.isFinite(maxDestinationsFromData) && maxDestinationsFromData > 0
      ? maxDestinationsFromData
      : Number(window.__DESTINATION_LIMIT__ || 3);
  const initialAlertData = window.__INITIAL_ALERT__ || null;

  const originAnchor = document.getElementById("origin-autocomplete-anchor");
  const originShell = document.getElementById("origin-input-shell");
  const originInput = document.getElementById("origin-input");
  const originCodeHidden = document.getElementById("origin-airport-code");
  const originChip = document.getElementById("origin-chip");
  const originMenu = document.getElementById("origin-menu");

  const destinationAnchor = document.getElementById("destination-autocomplete-anchor");
  const destinationShell = document.getElementById("destination-input-shell");
  const destinationInput = document.getElementById("destination-input");
  const destinationMenu = document.getElementById("destination-menu");
  const destinationCodesHidden = document.getElementById("destination-airport-codes");
  const destinationChips = document.getElementById("destination-chips");
  const clearDestinationsButton = document.getElementById("clear-destinations");

  const formError = document.getElementById("form-error");
  const submitButton = form.querySelector('button[type="submit"]');
  const ctaHint = document.getElementById("cta-hint");

  const availableDayButtons = Array.from(document.querySelectorAll(".day-button"));
  const availableDaysField = document.getElementById("available-days");
  const availableDaysInput = document.getElementById("available-days-input");
  const travelersInput = document.getElementById("travelers-input");
  const maxPriceInput = document.getElementById("max-price-input");
  const minDaysInput = document.getElementById("min-days-input");
  const frequencyInputs = Array.from(document.querySelectorAll('input[name="frequency"]'));
  const frequencyField = document.getElementById("frequency-field");
  const onlyMatchingField = document.getElementById("only-matching-field");
  const onlyMatchingInput = document.getElementById("only-matching-input");

  const budgetContext = document.getElementById("budget-context");
  const budgetGuideTitle = document.getElementById("budget-guide-title");
  const budgetGuideCopy = document.getElementById("budget-guide-copy");
  const budgetSuggestionButton = document.getElementById("budget-suggestion-button");
  const lowPriceWarning = document.getElementById("low-price-warning");

  const originError = document.getElementById("origin-error");
  const destinationError = document.getElementById("destination-error");
  const travelersError = document.getElementById("travelers-error");
  const maxPriceError = document.getElementById("max-price-error");
  const availableDaysError = document.getElementById("available-days-error");
  const minDaysError = document.getElementById("min-days-error");
  const frequencyError = document.getElementById("frequency-error");

  const tripTypeInputs = Array.from(document.querySelectorAll('input[name="trip_type"]'));
  const minDaysField = minDaysInput.closest(".field");
  const MAX_MIN_DAYS = 14;

  let originSelection = null;
  let destinationSelections = [];
  let availableDays = [];
  let destinationLimitMessage = "";
  let submitAttempted = false;
  let currentBudgetSuggestion = null;

  const touched = {
    origin: false,
    destinations: false,
    travelers: false,
    max_price_per_traveler: false,
    trip_days: false,
    min_days: false,
    frequency: false,
  };

  function debounce(fn, delayMs) {
    let timer = null;
    return function (...args) {
      clearTimeout(timer);
      timer = setTimeout(() => fn.apply(this, args), delayMs);
    };
  }

  function escapeHtml(value) {
    return String(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function markTouched(fieldName) {
    if (Object.prototype.hasOwnProperty.call(touched, fieldName)) {
      touched[fieldName] = true;
    }
  }

  function formatAirportReadable(item) {
  if (item.type === "country") {
    return item.label || item.country || item.name;
  }

  if (item.type === "city") {
    return item.label || `${item.city}, ${item.country}`;
  }

  return `${item.city} (${item.code})`;
  }

  function formatSuggestionLabel(item) {
    if (item.label) {
      return item.label;
    }

    if (item.type === "country") {
      return item.country || item.name;
    }

    if (item.type === "city") {
      return `${item.city}, ${item.country}`;
    }

    return `${item.city} (${item.code}) — ${item.name}`;
  }

  function formatSuggestionSubtitle(item) {
    if (item.subtitle) {
      return item.subtitle;
    }

    if (item.type === "country") {
      return "Country";
    }

    if (item.type === "city") {
      return "All airports";
    }

    return item.name || "";
  }

  function renderDropdown(menuEl, items, onPick) {
    if (!items || items.length === 0) {
      menuEl.classList.add("hidden");
      menuEl.innerHTML = "";
      return;
    }

    menuEl.innerHTML = items
      .map(
        (item) => `
          <button
            type="button"
            class="dropdown-item"
            data-type="${escapeHtml(item.type || "airport")}"
            data-code="${escapeHtml(item.code || "")}"
            data-codes="${escapeHtml(JSON.stringify(item.codes || []))}"
            data-name="${escapeHtml(item.name || "")}"
            data-city="${escapeHtml(item.city || "")}"
            data-country="${escapeHtml(item.country || "")}"
            data-label="${escapeHtml(item.label || "")}"
            data-subtitle="${escapeHtml(item.subtitle || "")}"
          >
            <span>${escapeHtml(formatSuggestionLabel(item))}</span>
            <small class="dropdown-item-subtitle">${escapeHtml(formatSuggestionSubtitle(item))}</small>
          </button>
        `
      )
      .join("");

    menuEl.classList.remove("hidden");

    Array.from(menuEl.querySelectorAll(".dropdown-item")).forEach((btn) => {
      btn.addEventListener("click", () => {
        const item = {
          type: btn.dataset.type || "airport",
          code: btn.dataset.code,
          codes: JSON.parse(btn.dataset.codes || "[]"),
          name: btn.dataset.name,
          city: btn.dataset.city,
          country: btn.dataset.country,
          label: btn.dataset.label,
          subtitle: btn.dataset.subtitle,
        };

        onPick(item);
      });
    });

    setDropdownActiveIndex(menuEl, 0);
  }

  function getDropdownItems(menuEl) {
    return Array.from(menuEl.querySelectorAll(".dropdown-item"));
  }

  function getDropdownActiveIndex(menuEl) {
    const items = getDropdownItems(menuEl);
    return items.findIndex((item) => item.classList.contains("active"));
  }

  function setDropdownActiveIndex(menuEl, index) {
    const items = getDropdownItems(menuEl);
    if (items.length === 0) return;

    const boundedIndex = Math.min(Math.max(index, 0), items.length - 1);
    items.forEach((item) => item.classList.remove("active"));
    items[boundedIndex].classList.add("active");
  }

  function moveDropdownActiveIndex(menuEl, delta) {
    const items = getDropdownItems(menuEl);
    if (items.length === 0) return;

    const currentIndex = getDropdownActiveIndex(menuEl);
    const startIndex = currentIndex < 0 ? 0 : currentIndex;
    const nextIndex = Math.min(Math.max(startIndex + delta, 0), items.length - 1);
    setDropdownActiveIndex(menuEl, nextIndex);
  }

  function closeDropdown(menuEl) {
    menuEl.classList.add("hidden");
    menuEl.innerHTML = "";
  }

  function handleAutocompleteKeydown(event, menuEl) {
    const isOpen = !menuEl.classList.contains("hidden");
    if (!isOpen) return;

    if (event.key === "ArrowDown") {
      event.preventDefault();
      moveDropdownActiveIndex(menuEl, 1);
      return;
    }

    if (event.key === "ArrowUp") {
      event.preventDefault();
      moveDropdownActiveIndex(menuEl, -1);
      return;
    }

    if (event.key === "Enter") {
      const items = getDropdownItems(menuEl);
      const activeIndex = getDropdownActiveIndex(menuEl);
      if (items.length > 0 && activeIndex >= 0) {
        event.preventDefault();
        items[activeIndex].click();
      }
      return;
    }

    if (event.key === "Escape") {
      event.preventDefault();
      closeDropdown(menuEl);
    }
  }

  async function fetchAirportSuggestions(query, mode = "destination") {
    const url = `/api/airports/search?q=${encodeURIComponent(query)}&mode=${encodeURIComponent(mode)}`;
    const response = await fetch(url);
    const payload = await response.json();
    if (!response.ok) return [];
    return payload.items || [];
  }

  function syncDestinationCodesHidden() {
    const destinationCodes = destinationSelections.flatMap((item) => {
      if (Array.isArray(item.codes) && item.codes.length > 0) {
        return item.codes;
      }

      if (item.code) {
        return [item.code];
      }

      return [];
    });

    destinationCodesHidden.value = JSON.stringify([...new Set(destinationCodes)]);
  }

  function syncAvailableDaysHidden() {
    availableDaysInput.value = JSON.stringify(availableDays);
  }

  function clearOriginSelection() {
    originSelection = null;
    originCodeHidden.value = "";
    renderOriginChip();
    updateBudgetGuidance();
    updateLowPriceWarning();
  }

  function renderOriginChip() {
    if (!originSelection) {
      originChip.innerHTML = "";
      return;
    }

    originChip.innerHTML = `
      <div class="chip">
        <span>${escapeHtml(formatAirportReadable(originSelection))}</span>
        <button
          type="button"
          class="chip-remove"
          id="origin-chip-remove"
          aria-label="Remove ${escapeHtml(formatAirportReadable(originSelection))}"
        >
          x
        </button>
      </div>
    `;

    const removeButton = document.getElementById("origin-chip-remove");
    removeButton.addEventListener("click", () => {
      markTouched("origin");
      clearOriginSelection();
      originInput.focus();
      formError.classList.add("hidden");
      updateSubmitState();
    });
  }

  function getSelectedFrequency() {
    return frequencyInputs.find((input) => input.checked)?.value || "";
  }

  function setOnlyMatchingVisibility() {
    const isDailyDigest = getSelectedFrequency() === "daily";
    onlyMatchingField.classList.toggle("hidden", !isDailyDigest);
    onlyMatchingInput.disabled = !isDailyDigest;

    if (!isDailyDigest) {
      onlyMatchingInput.checked = true;
    }
  }

  function getSelectedTripType() {
    return tripTypeInputs.find((input) => input.checked)?.value || "round_trip";
  }

  function setMinDaysVisibility() {
    const isOneWay = getSelectedTripType() === "one_way";
    minDaysField.classList.toggle("hidden", isOneWay);

    if (isOneWay) {
      minDaysInput.value = "1";
    }
  }

  function syncMinDaysLimit() {
    const selectedDayCount = availableDays.length;
    const maxAllowedDays = selectedDayCount > 0 ? Math.min(selectedDayCount, MAX_MIN_DAYS) : MAX_MIN_DAYS;

    minDaysInput.max = String(maxAllowedDays);
  }

  function parseIntegerInput(rawValue) {
    const trimmed = String(rawValue || "").trim();
    if (!trimmed) return null;
    if (!/^\d+$/.test(trimmed)) return null;
    return Number(trimmed);
  }

  function parsePositiveNumberInput(rawValue) {
    const trimmed = String(rawValue || "").trim();
    if (!trimmed) return null;
    const value = Number(trimmed);
    if (!Number.isFinite(value)) return null;
    return value;
  }

  function getBudgetGuidanceState() {
    const destinationCount = destinationSelections.length;

    if (!originSelection || destinationCount === 0) {
      return {
        title: "Not sure what to enter?",
        copy:
          "Start with a price that would make you feel good booking. You can always adjust it later.",
        context: "",
        suggestion: null,
        buttonLabel: "",
      };
    }

    const sameCountryDestinations = destinationSelections.filter(
      (destination) => destination.country && originSelection.country && destination.country === originSelection.country
    );
    const allSameCountry =
      destinationSelections.length > 0 && sameCountryDestinations.length === destinationSelections.length;
    const hasMixedCountries =
      destinationSelections.some(
        (destination) =>
          originSelection.country && destination.country && destination.country !== originSelection.country
      );

    if (destinationCount > 1 && hasMixedCountries) {
      return {
        title: "Not sure what to enter?",
        copy:
          "Use one broad starter target for now. Jetzi will apply it across all selected destinations, and you can fine-tune later.",
        context: "If you track multiple destinations, this budget applies to all of them for now.",
        suggestion: 400,
        buttonLabel: "Use $400 starter target",
      };
    }

    if (destinationCount > 1 && allSameCountry) {
      return {
        title: "Not sure what to enter?",
        copy:
          "Pick one price that would feel like a strong deal across all of your selected destinations.",
        context: "If you track multiple destinations, this budget applies to all of them for now.",
        suggestion: 225,
        buttonLabel: "Use $225 starter target",
      };
    }

    if (destinationCount === 1 && allSameCountry) {
      return {
        title: "Not sure what to enter?",
        copy:
          "For a shorter domestic-style trip, many people start with a target around $150–$250 per traveler to catch good deals consistently (lower targets can catch rare deals, but you may miss many good ones).",
        context: "",
        suggestion: 200,
        buttonLabel: "Use $200 starter target",
      };
    }

    return {
      title: "Not sure what to enter?",
      copy:
        "For an international-style trip, many people start with a target around $350–$600 per traveler to catch good deals consistently (lower targets can catch rare deals, but you may miss many good ones).",
      context: "",
      suggestion: 450,
      buttonLabel: "Use $450 starter target",
    };
  }

  function updateBudgetGuidance() {
    if (!budgetGuideTitle || !budgetGuideCopy || !budgetContext || !budgetSuggestionButton) {
      return;
    }

    const state = getBudgetGuidanceState();
    currentBudgetSuggestion = state.suggestion;

    budgetGuideTitle.textContent = state.title;
    budgetGuideCopy.textContent = state.copy;
    budgetContext.textContent = state.context || "";
    budgetContext.classList.toggle("hidden", !state.context);

    if (typeof state.suggestion === "number" && state.suggestion > 0) {
      budgetSuggestionButton.textContent = state.buttonLabel;
      budgetSuggestionButton.classList.remove("hidden");
    } else {
      budgetSuggestionButton.textContent = "";
      budgetSuggestionButton.classList.add("hidden");
    }
  }

  function updateLowPriceWarning() {
    if (!lowPriceWarning || !maxPriceInput) return;

    const maxPrice = parsePositiveNumberInput(maxPriceInput.value);

    if (maxPrice !== null && maxPrice > 0 && maxPrice < 50) {
      lowPriceWarning.textContent =
        "This price is very low for most trips. You may miss good deals if your target is too strict.";
      lowPriceWarning.classList.remove("hidden");
      return;
    }

    lowPriceWarning.textContent = "";
    lowPriceWarning.classList.add("hidden");
  }

  function getValidationErrors() {
    const errors = {};

    if (!originCodeHidden.value) {
      errors.origin = "Select a departure airport from the list.";
    }

    if (destinationSelections.length < 1) {
      errors.destinations = "Select at least 1 destination.";
    }

    const travelers = parseIntegerInput(travelersInput.value);
    if (travelers === null) {
      errors.travelers = "Enter a number from 1 to 4.";
    } else if (travelers > 4) {
      errors.travelers = "Maximum 4 adults.";
    } else if (travelers < 1) {
      errors.travelers = "Minimum is 1.";
    }

    const maxPrice = parsePositiveNumberInput(maxPriceInput.value);
    if (maxPrice === null) {
      errors.max_price_per_traveler = "Enter a valid price (e.g. 300).";
    } else if (maxPrice <= 0) {
      errors.max_price_per_traveler = "Price must be at least 1.";
    }

    const minDays = parseIntegerInput(minDaysInput.value);
    const maxAllowedDays =
      availableDays.length > 0 ? Math.min(availableDays.length, MAX_MIN_DAYS) : MAX_MIN_DAYS;

    if (minDays === null) {
      errors.min_days = "Enter a valid number of days.";
    } else if (minDays < 1) {
      errors.min_days = "Minimum trip length must be at least 1 day.";
    } else if (minDays > maxAllowedDays) {
      if (availableDays.length > 0) {
        errors.min_days = `With your selected days, the shortest trip can’t be more than ${availableDays.length} days.`;
      } else {
        errors.min_days = `Shortest trip length can’t be more than ${MAX_MIN_DAYS} days.`;
      }
    }

    
    if (!getSelectedFrequency()) {
      errors.frequency = "Choose when you’d like to be notified.";
    }

    return errors;
  }

  function setFieldError(el, message, shouldShow) {
    if (!el) return;
    if (shouldShow && message) {
      el.textContent = message;
      el.classList.remove("hidden");
    } else {
      el.textContent = "";
      el.classList.add("hidden");
    }
  }

  function setInvalidClass(el, isInvalid) {
    if (!el) return;
    el.classList.toggle("is-invalid", Boolean(isInvalid));
  }

  function renderValidationState() {
    const errors = getValidationErrors();
    const isOriginTyping = document.activeElement === originInput && originInput.value.trim().length > 0;
    const isDestinationTyping =
      document.activeElement === destinationInput && destinationInput.value.trim().length > 0;

    const showOrigin = submitAttempted || (touched.origin && !isOriginTyping);
    const showDestinations = submitAttempted || (touched.destinations && !isDestinationTyping);
    const showTravelers = submitAttempted || touched.travelers;
    const showMaxPrice = submitAttempted || touched.max_price_per_traveler;
    const showAvailableDays = submitAttempted || touched.trip_days;
    const showMinDays = submitAttempted || touched.min_days;
    const showFrequency = submitAttempted || touched.frequency;

    const destinationMessage = destinationLimitMessage || errors.destinations || "";

    setFieldError(originError, errors.origin, showOrigin);
    setFieldError(destinationError, destinationMessage, showDestinations || Boolean(destinationLimitMessage));
    setFieldError(travelersError, errors.travelers, showTravelers);
    setFieldError(maxPriceError, errors.max_price_per_traveler, showMaxPrice);
    setFieldError(availableDaysError, errors.trip_days, showAvailableDays);
    setFieldError(minDaysError, errors.min_days, showMinDays);
    setFieldError(frequencyError, errors.frequency, showFrequency);

    setInvalidClass(originShell, showOrigin && Boolean(errors.origin));
    setInvalidClass(destinationShell, showDestinations && Boolean(errors.destinations));
    setInvalidClass(travelersInput, showTravelers && Boolean(errors.travelers));
    setInvalidClass(maxPriceInput, showMaxPrice && Boolean(errors.max_price_per_traveler));
    setInvalidClass(availableDaysField, showAvailableDays && Boolean(errors.trip_days));
    setInvalidClass(minDaysInput, showMinDays && Boolean(errors.min_days));
    setInvalidClass(frequencyField, showFrequency && Boolean(errors.frequency));

    const isValid = Object.keys(errors).length === 0;
    if (ctaHint) {
      ctaHint.classList.toggle("hidden", isValid);
    }

    return { isValid, errors };
  }

  function updateSubmitState() {
    renderValidationState();
    updateBudgetGuidance();
    updateLowPriceWarning();
  }

  function renderDestinationChips() {
    destinationChips.innerHTML = destinationSelections
      .map(
        (selection) => `
          <div class="chip">
            <span>${escapeHtml(formatAirportReadable(selection))}</span>
            <button
              type="button"
              class="chip-remove"
              data-key="${escapeHtml(selection.code || selection.label || selection.city || selection.country)}"
              aria-label="Remove ${escapeHtml(formatAirportReadable(selection))}"
            >
              x
            </button>
          </div>
        `
      )
      .join("");

    Array.from(destinationChips.querySelectorAll(".chip-remove")).forEach((button) => {
      button.addEventListener("click", () => {
        markTouched("destinations");
        const key = button.dataset.key;
        destinationSelections = destinationSelections.filter(
          (item) => (item.code || item.label || item.city || item.country) !== key
        );
        if (destinationSelections.length < MAX_DESTINATIONS) {
          destinationLimitMessage = "";
        }
        syncDestinationCodesHidden();
        renderDestinationChips();
        formError.classList.add("hidden");
        updateSubmitState();
      });
    });

    clearDestinationsButton.classList.toggle("hidden", destinationSelections.length === 0);
    updateBudgetGuidance();
  }

  function setRadioValue(name, value) {
    const radios = Array.from(document.querySelectorAll(`input[name="${name}"]`));
    radios.forEach((radio) => {
      radio.checked = radio.value === value;
    });
  }

  function applyInitialAlert(alert) {
    if (!alert || typeof alert !== "object") return;

    if (alert.origin_airport_code) {
      const originAirport = alert.origin_airport || {};
      originSelection = {
        code: alert.origin_airport_code,
        city: originAirport.city || alert.origin_airport_code,
        name: originAirport.name || "",
        country: originAirport.country || "",
      };
      originCodeHidden.value = alert.origin_airport_code;
      renderOriginChip();
    }

    const destinationAirports = Array.isArray(alert.destination_airports)
      ? alert.destination_airports
      : [];
    if (destinationAirports.length > 0) {
      destinationSelections = destinationAirports.map((airport) => ({
        code: airport.code,
        city: airport.city || airport.code,
        name: airport.name || "",
        country: airport.country || "",
      }));
    } else if (Array.isArray(alert.destination_airport_codes)) {
      destinationSelections = alert.destination_airport_codes.map((code) => ({
        code,
        city: code,
        name: "",
        country: "",
      }));
    }
    syncDestinationCodesHidden();
    renderDestinationChips();

    if (alert.trip_type) {
      setRadioValue("trip_type", alert.trip_type);
    }
    if (typeof alert.adults !== "undefined") {
      travelersInput.value = String(alert.adults);
    }
    if (typeof alert.max_price_per_traveler !== "undefined" && alert.max_price_per_traveler !== null) {
      maxPriceInput.value = String(alert.max_price_per_traveler);
    }
    if (Array.isArray(alert.available_departure_days)) {
      availableDays = alert.available_departure_days;
      syncAvailableDaysHidden();
      renderAvailableDays();
    }
    if (typeof alert.min_days !== "undefined") {
      minDaysInput.value = String(alert.min_days);
    }
    syncMinDaysLimit();

    if (alert.frequency) {
      setRadioValue("frequency", alert.frequency);
    }
    if (typeof alert.only_send_matching_deals !== "undefined") {
      onlyMatchingInput.checked = Boolean(alert.only_send_matching_deals);
    }
    setOnlyMatchingVisibility();
    updateBudgetGuidance();
    updateLowPriceWarning();
  }

  function renderAvailableDays() {
    availableDayButtons.forEach((button) => {
      const day = button.dataset.day;
      const isSelected = day === "any" ? availableDays.length === 0 : availableDays.includes(day);

      button.classList.toggle("selected", isSelected);
      button.setAttribute("aria-pressed", isSelected ? "true" : "false");
    });
  }

  const debouncedOriginSearch = debounce(async () => {
    const q = originInput.value.trim();
    if (originSelection) {
      clearOriginSelection();
    }
    updateSubmitState();

    if (q.length < 2) {
      closeDropdown(originMenu);
      return;
    }

    const items = await fetchAirportSuggestions(q, "origin");
    renderDropdown(originMenu, items, (airport) => {
      originSelection = airport;
      originInput.value = "";
      originCodeHidden.value = airport.code;
      renderOriginChip();
      closeDropdown(originMenu);
      formError.classList.add("hidden");
      updateSubmitState();
    });
  }, 300);

  const debouncedDestinationSearch = debounce(async () => {
    const q = destinationInput.value.trim();
    destinationLimitMessage = "";

    if (q.length < 2) {
      closeDropdown(destinationMenu);
      updateSubmitState();
      return;
    }

    const items = await fetchAirportSuggestions(q, "destination");
    renderDropdown(destinationMenu, items, (airport) => {
      if (destinationSelections.length >= MAX_DESTINATIONS) {
        destinationLimitMessage = `You can add up to ${MAX_DESTINATIONS} destinations.`;
        destinationInput.value = "";
        closeDropdown(destinationMenu);
        updateSubmitState();
        return;
      }

      const pickedKey = airport.code || airport.label || airport.city || airport.country;

      const alreadySelected = destinationSelections.some((item) => {
        const existingKey = item.code || item.label || item.city || item.country;
        return existingKey === pickedKey;
      });

      if (!alreadySelected) {
        destinationSelections.push(airport);
        syncDestinationCodesHidden();
        renderDestinationChips();
      }

      destinationLimitMessage = "";
      destinationInput.value = "";
      closeDropdown(destinationMenu);
      formError.classList.add("hidden");
      updateSubmitState();
    });
  }, 300);

  originInput.addEventListener("input", debouncedOriginSearch);
  originInput.addEventListener("keydown", (event) => handleAutocompleteKeydown(event, originMenu));
  originInput.addEventListener("blur", () => {
    markTouched("origin");
    updateSubmitState();
  });

  destinationInput.addEventListener("input", debouncedDestinationSearch);
  destinationInput.addEventListener("keydown", (event) => handleAutocompleteKeydown(event, destinationMenu));
  destinationInput.addEventListener("input", () => {
    destinationLimitMessage = "";
    formError.classList.add("hidden");
    updateSubmitState();
  });
  destinationInput.addEventListener("blur", () => {
    window.setTimeout(() => {
      markTouched("destinations");
      updateSubmitState();
    }, 0);
  });

  originShell.addEventListener("click", () => originInput.focus());
  destinationShell.addEventListener("click", () => destinationInput.focus());

  clearDestinationsButton.addEventListener("click", () => {
    markTouched("destinations");
    destinationSelections = [];
    destinationLimitMessage = "";
    syncDestinationCodesHidden();
    renderDestinationChips();
    formError.classList.add("hidden");
    updateSubmitState();
    destinationInput.focus();
  });

  availableDayButtons.forEach((button) => {
    button.addEventListener("click", () => {
      markTouched("trip_days");
      markTouched("min_days");

      const day = button.dataset.day;

      if (day === "any") {
        availableDays = [];
      } else if (availableDays.includes(day)) {
        availableDays = availableDays.filter((item) => item !== day);
      } else {
        availableDays.push(day);
      }

      syncAvailableDaysHidden();
      renderAvailableDays();
      syncMinDaysLimit();
      formError.classList.add("hidden");
      updateSubmitState();
    });
  });

  [travelersInput, maxPriceInput, minDaysInput].forEach((input) => {
    input.addEventListener("input", () => {
      if (input === travelersInput) {
        markTouched("travelers");
      }

      if (input === maxPriceInput) {
        markTouched("max_price_per_traveler");
        updateLowPriceWarning();
      }

      if (input === minDaysInput) {
        markTouched("min_days");
        syncMinDaysLimit();
      }

      formError.classList.add("hidden");
      updateSubmitState();
    });
  });

  frequencyInputs.forEach((input) => {
    input.addEventListener("change", () => {
      markTouched("frequency");
      setOnlyMatchingVisibility();
      formError.classList.add("hidden");
      updateSubmitState();
    });
  });

  tripTypeInputs.forEach((input) => {
    input.addEventListener("change", () => {
      setMinDaysVisibility();
      formError.classList.add("hidden");
      updateSubmitState();
    });
  });

  if (budgetSuggestionButton) {
    budgetSuggestionButton.addEventListener("click", () => {
      if (typeof currentBudgetSuggestion === "number" && currentBudgetSuggestion > 0) {
        maxPriceInput.value = String(currentBudgetSuggestion);
        markTouched("max_price_per_traveler");
        formError.classList.add("hidden");
        updateSubmitState();
        maxPriceInput.focus();
      }
    });
  }

  document.addEventListener("click", (event) => {
    const target = event.target;
    if (!originAnchor.contains(target)) {
      closeDropdown(originMenu);
    }

    if (!destinationAnchor.contains(target)) {
      closeDropdown(destinationMenu);
    }
  });

  form.addEventListener("submit", (event) => {
    submitAttempted = true;
    formError.classList.add("hidden");

    const validation = renderValidationState();
    if (!validation.isValid) {
      event.preventDefault();
      formError.textContent = "Please fix the highlighted errors before creating your alert.";
      formError.classList.remove("hidden");
      return;
    }

    submitButton.disabled = true;
  });

  applyInitialAlert(initialAlertData);
  syncDestinationCodesHidden();
  syncAvailableDaysHidden();
  syncMinDaysLimit();
  renderOriginChip();
  setOnlyMatchingVisibility();
  renderDestinationChips();
  renderAvailableDays();
  updateBudgetGuidance();
  updateLowPriceWarning();
  setMinDaysVisibility();
  renderValidationState();
})();