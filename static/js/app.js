(function () {
  const originInput = document.getElementById("origin-input");
  const originCodeHidden = document.getElementById("origin-airport-code");
  const originMenu = document.getElementById("origin-menu");

  const destinationInput = document.getElementById("destination-input");
  const destinationMenu = document.getElementById("destination-menu");
  const destinationCodesHidden = document.getElementById("destination-airport-codes");
  const destinationChips = document.getElementById("destination-chips");

  const form = document.getElementById("alert-form");
  const formError = document.getElementById("form-error");
  const result = document.getElementById("result");

  let destinationCodes = [];

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
            <strong>${escapeHtml(airport.code)}</strong>
            <span>${escapeHtml(airport.city)} - ${escapeHtml(airport.name)} (${escapeHtml(airport.country)})</span>
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
  }

  async function fetchAirportSuggestions(query) {
    const url = `/api/airports/search?q=${encodeURIComponent(query)}`;
    const response = await fetch(url);
    const payload = await response.json();
    if (!response.ok) return [];
    return payload.items || [];
  }

  function syncDestinationCodesHidden() {
    destinationCodesHidden.value = JSON.stringify(destinationCodes);
  }

  function renderDestinationChips() {
    destinationChips.innerHTML = destinationCodes
      .map(
        (code) => `
          <div class="chip">
            <span>${escapeHtml(code)}</span>
            <button type="button" class="chip-remove" data-code="${escapeHtml(code)}" aria-label="Remove ${escapeHtml(code)}">x</button>
          </div>
        `
      )
      .join("");

    Array.from(destinationChips.querySelectorAll(".chip-remove")).forEach((button) => {
      button.addEventListener("click", () => {
        const code = button.dataset.code;
        destinationCodes = destinationCodes.filter((item) => item !== code);
        syncDestinationCodesHidden();
        renderDestinationChips();
      });
    });
  }

  const debouncedOriginSearch = debounce(async () => {
    const q = originInput.value.trim();
    originCodeHidden.value = "";
    if (q.length < 2) {
      originMenu.classList.add("hidden");
      originMenu.innerHTML = "";
      return;
    }
    const items = await fetchAirportSuggestions(q);
    renderDropdown(originMenu, items, (airport) => {
      originInput.value = `${airport.code} - ${airport.city} (${airport.name})`;
      originCodeHidden.value = airport.code;
      originMenu.classList.add("hidden");
      originMenu.innerHTML = "";
    });
  }, 300);

  const debouncedDestinationSearch = debounce(async () => {
    const q = destinationInput.value.trim();
    if (q.length < 2) {
      destinationMenu.classList.add("hidden");
      destinationMenu.innerHTML = "";
      return;
    }
    const items = await fetchAirportSuggestions(q);
    renderDropdown(destinationMenu, items, (airport) => {
      if (!destinationCodes.includes(airport.code)) {
        destinationCodes.push(airport.code);
        syncDestinationCodesHidden();
        renderDestinationChips();
      }
      destinationInput.value = "";
      destinationMenu.classList.add("hidden");
      destinationMenu.innerHTML = "";
    });
  }, 300);

  originInput.addEventListener("input", debouncedOriginSearch);
  destinationInput.addEventListener("input", debouncedDestinationSearch);

  document.addEventListener("click", (event) => {
    const target = event.target;
    if (!originMenu.contains(target) && target !== originInput) {
      originMenu.classList.add("hidden");
    }
    if (!destinationMenu.contains(target) && target !== destinationInput) {
      destinationMenu.classList.add("hidden");
    }
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    formError.classList.add("hidden");
    result.classList.add("hidden");

    if (!originCodeHidden.value) {
      formError.textContent = "Please select a departure airport from suggestions.";
      formError.classList.remove("hidden");
      return;
    }
    if (destinationCodes.length < 1) {
      formError.textContent = "Please add at least one destination airport.";
      formError.classList.remove("hidden");
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

    result.textContent = JSON.stringify(payload, null, 2);
    result.classList.remove("hidden");
  });
})();
