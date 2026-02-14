(function () {
  const MAX_DESTINATIONS = 5;
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

  const form = document.getElementById("alert-form");
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

  const originError = document.getElementById("origin-error");
  const destinationError = document.getElementById("destination-error");
  const travelersError = document.getElementById("travelers-error");
  const maxPriceError = document.getElementById("max-price-error");
  const availableDaysError = document.getElementById("available-days-error");
  const minDaysError = document.getElementById("min-days-error");
  const frequencyError = document.getElementById("frequency-error");

  let originSelection = null;
  let destinationSelections = [];
  let availableDays = [];
  let destinationLimitMessage = "";
  let submitAttempted = false;
  const touched = {
    origin: false,
    destinations: false,
    travelers: false,
    max_price_per_traveler: false,
    available_departure_days: false,
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

  function formatAirportReadable(airport) {
    return `${airport.city} (${airport.code})`;
  }

  function formatSuggestionLabel(airport) {
    return `${airport.city} (${airport.code}) — ${airport.name}`;
  }

  function renderDropdown(menuEl, items, onPick) {
    if (!items || items.length === 0) {
      menuEl.classList.add("hidden");
      menuEl.innerHTML = "";
      return;
    }

    menuEl.innerHTML = items
      .map(
        (airport) => `
          <button
            type="button"
            class="dropdown-item"
            data-code="${escapeHtml(airport.code)}"
            data-name="${escapeHtml(airport.name)}"
            data-city="${escapeHtml(airport.city)}"
            data-country="${escapeHtml(airport.country)}"
          >
            <span>${escapeHtml(formatSuggestionLabel(airport))}</span>
          </button>
        `
      )
      .join("");

    menuEl.classList.remove("hidden");

    Array.from(menuEl.querySelectorAll(".dropdown-item")).forEach((btn) => {
      btn.addEventListener("click", () => {
        const airport = {
          code: btn.dataset.code,
          name: btn.dataset.name,
          city: btn.dataset.city,
          country: btn.dataset.country,
        };
        onPick(airport);
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

  async function fetchAirportSuggestions(query) {
    const url = `/api/airports/search?q=${encodeURIComponent(query)}`;
    const response = await fetch(url);
    const payload = await response.json();
    if (!response.ok) return [];
    return payload.items || [];
  }

  function syncDestinationCodesHidden() {
    const destinationCodes = destinationSelections.map((item) => item.code);
    destinationCodesHidden.value = JSON.stringify(destinationCodes);
  }

  function syncAvailableDaysHidden() {
    availableDaysInput.value = JSON.stringify(availableDays);
  }

  function clearOriginSelection() {
    originSelection = null;
    originCodeHidden.value = "";
    renderOriginChip();
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

    // For immediate notifications we always treat this as true on the backend.
    if (!isDailyDigest) {
      onlyMatchingInput.checked = true;
    }
  }

  function syncMinDaysLimit() {
    const parsed = parseIntegerInput(minDaysInput.value);
    if (parsed !== null && parsed < 1) {
      minDaysInput.value = "1";
    }
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
      errors.max_price_per_traveler = "Enter a valid price (e.g., 300).";
    } else if (maxPrice <= 0) {
      errors.max_price_per_traveler = "Price must be at least 1.";
    }

    const minDays = parseIntegerInput(minDaysInput.value);
    if (minDays === null) {
      errors.min_days = "Enter a valid number of days.";
    } else if (minDays < 1) {
      errors.min_days = "Minimum days must be at least 1.";
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
    const showAvailableDays = submitAttempted || touched.available_departure_days;
    const showMinDays = submitAttempted || touched.min_days;
    const showFrequency = submitAttempted || touched.frequency;

    const destinationMessage = destinationLimitMessage || errors.destinations || "";

    setFieldError(originError, errors.origin, showOrigin);
    setFieldError(destinationError, destinationMessage, showDestinations || Boolean(destinationLimitMessage));
    setFieldError(travelersError, errors.travelers, showTravelers);
    setFieldError(maxPriceError, errors.max_price_per_traveler, showMaxPrice);
    setFieldError(availableDaysError, errors.available_departure_days, showAvailableDays);
    setFieldError(minDaysError, errors.min_days, showMinDays);
    setFieldError(frequencyError, errors.frequency, showFrequency);

    setInvalidClass(originShell, showOrigin && Boolean(errors.origin));
    setInvalidClass(destinationShell, showDestinations && Boolean(errors.destinations));
    setInvalidClass(travelersInput, showTravelers && Boolean(errors.travelers));
    setInvalidClass(maxPriceInput, showMaxPrice && Boolean(errors.max_price_per_traveler));
    setInvalidClass(availableDaysField, showAvailableDays && Boolean(errors.available_departure_days));
    setInvalidClass(minDaysInput, showMinDays && Boolean(errors.min_days));
    setInvalidClass(frequencyField, showFrequency && Boolean(errors.frequency));

    const isValid = Object.keys(errors).length === 0;
    submitButton.disabled = !isValid;
    ctaHint.classList.toggle("hidden", isValid);

    return { isValid, errors };
  }

  function updateSubmitState() {
    renderValidationState();
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
              data-code="${escapeHtml(selection.code)}"
              aria-label="Remove ${escapeHtml(selection.city)} (${escapeHtml(selection.code)})"
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
        const code = button.dataset.code;
        destinationSelections = destinationSelections.filter((item) => item.code !== code);
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
    if (typeof alert.max_price_per_traveler !== "undefined") {
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
  }

  function renderAvailableDays() {
    availableDayButtons.forEach((button) => {
      const isSelected = availableDays.includes(button.dataset.day);
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

    const items = await fetchAirportSuggestions(q);
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

    const items = await fetchAirportSuggestions(q);
    renderDropdown(destinationMenu, items, (airport) => {
      if (destinationSelections.length >= MAX_DESTINATIONS) {
        destinationLimitMessage = "You can add up to 5 destinations.";
        destinationInput.value = "";
        closeDropdown(destinationMenu);
        updateSubmitState();
        return;
      }

      const alreadySelected = destinationSelections.some((item) => item.code === airport.code);
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
      markTouched("available_departure_days");
      markTouched("min_days");
      const day = button.dataset.day;
      if (availableDays.includes(day)) {
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
      if (input === travelersInput) markTouched("travelers");
      if (input === maxPriceInput) markTouched("max_price_per_traveler");
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

  document.addEventListener("click", (event) => {
    const target = event.target;
    if (!originAnchor.contains(target)) {
      closeDropdown(originMenu);
    }

    if (!destinationAnchor.contains(target)) {
      closeDropdown(destinationMenu);
    }
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    submitAttempted = true;
    formError.classList.add("hidden");

    const validation = renderValidationState();
    if (!validation.isValid) {
      return;
    }

    const formData = new FormData(form);
    const response = await fetch(form.action, { method: "POST", body: formData });
    const payload = await response.json();

    if (!response.ok) {
      formError.textContent = payload.error || "Failed to create alert.";
      formError.classList.remove("hidden");
      return;
    }

    window.location.assign(payload.redirect_url || "/alert-created");
  });

  applyInitialAlert(initialAlertData);
  syncDestinationCodesHidden();
  syncAvailableDaysHidden();
  syncMinDaysLimit();
  renderOriginChip();
  setOnlyMatchingVisibility();
  renderDestinationChips();
  renderAvailableDays();
  renderValidationState();
})();
