const form = document.getElementById("setup-form");
const steps = [...document.querySelectorAll(".step")];
const nextButton = document.getElementById("next");
const backButton = document.getElementById("back");
const skipButton = document.getElementById("skip-step");
const activateButton = document.getElementById("activate");
const statusNode = document.getElementById("status");
const completionNode = document.getElementById("completion");
const completionActions = document.getElementById("completion-actions");
const completionGreeting = document.getElementById("completion-greeting");
const webChatLink = document.getElementById("web-chat-link");
const spawnOverlay = document.getElementById("spawn-overlay");
const spawnLine = document.getElementById("spawn-line");
const spawnBar = document.getElementById("spawn-bar");
const telegramSummary = document.getElementById("telegram-summary");
const telegramConnectedState = document.getElementById("telegram-connected-state");
const telegramConnectedCopy = document.getElementById("telegram-connected-copy");
const telegramBadge = document.getElementById("telegram-badge");
const telegramTokenInput = document.getElementById("telegram-token-input");
const telegramTokenHint = document.getElementById("telegram-token-hint");
const wearablesBadge = document.getElementById("wearables-badge");
const wearablesProviderSelect = document.getElementById("wearables-provider-select");
const wearablesSummary = document.getElementById("wearables-summary");
const wearablesFreshness = document.getElementById("wearables-freshness");
const wearableSummaryBar = document.getElementById("wearable-summary-bar");
const wearableConnectedChips = document.getElementById("wearable-connected-chips");
const wearableExampleHint = document.getElementById("wearable-example-hint");
const wearableFeaturedGrid = document.getElementById("wearable-featured-grid");
const moreProvidersGrid = document.getElementById("more-providers-grid");
const moreProvidersToggle = document.getElementById("more-providers-toggle");
const finishSummary = document.getElementById("finish-summary");
const finishTimezone = document.getElementById("finish-timezone");
const finishWearables = document.getElementById("finish-wearables");
const connectTelegramButton = document.getElementById("connect-telegram");
const openBotFatherButton = document.getElementById("open-botfather");
const timezoneInput = document.querySelector('[name="timezone"]');
const setupTimezonePill = document.getElementById("setup-timezone-pill");
const usernameSuggestions = document.getElementById("username-suggestions");
const progressItems = [...document.querySelectorAll(".step-progress__item")];
const SETUP_TOKEN_KEY = "nanobot-health-setup-token";

// Provider step elements
const providerOllamaSection = document.getElementById("provider-ollama-section");
const providerApiSection = document.getElementById("provider-api-section");
const providerSummary = document.getElementById("provider-summary");
const providerRadios = form ? [...form.querySelectorAll('[name="provider_type"]')] : [];

// Featured provider slugs — always shown, cross-referenced against available_providers
const FEATURED_SLUGS = ["apple-health", "google-fit", "fitbit"];

const TONE_PREFERENCES = {
  gentle: "Warm, gentle nudges",
  direct: "Direct, motivating pushes",
  calm: "Calm grounding support",
};

// Steps where skip is allowed (wearables=2, vibe=3)
const SKIPPABLE_STEPS = new Set([2]);

let currentStep = 0;
let setupState = null;
const detectedTimezone = detectTimezone();

function detectTimezone() {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  } catch (e) {
    return "UTC";
  }
}

function detectLanguage() {
  try {
    const lang = (navigator.language || "en").trim();
    return lang || "en";
  } catch (e) {
    return "en";
  }
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function runSpawnSequence() {
  if (!spawnOverlay || !spawnLine || !spawnBar) return;
  const lines = [
    "Setting up your private space.",
    "Saving your name and local timing…",
    "Almost there. Getting your companion ready…",
  ];
  let pct = 0;
  for (let i = 0; i < lines.length; i += 1) {
    spawnLine.textContent = lines[i];
    const target = Math.round(((i + 1) / lines.length) * 92);
    while (pct < target) {
      pct += 3;
      spawnBar.style.width = `${Math.min(pct, target)}%`;
      await sleep(40);
    }
    await sleep(320);
  }
  spawnBar.style.width = "100%";
  spawnLine.textContent = "Ready when you are.";
  await sleep(500);
  const companion = spawnOverlay.querySelector(".companion-wrap");
  if (companion) companion.setAttribute("data-state", "idle");
  spawnOverlay.classList.add("is-done");
  spawnOverlay.setAttribute("aria-hidden", "true");
}

function typedTimezone() {
  return String(timezoneInput?.value || "").trim() || detectedTimezone;
}

function seedTimezoneField(value = "") {
  if (!timezoneInput) return;
  const nextValue = String(value || "").trim() || detectedTimezone;
  if (!String(timezoneInput.value || "").trim() || value) {
    timezoneInput.value = nextValue;
  }
  if (setupTimezonePill) {
    setupTimezonePill.textContent = typedTimezone() === detectedTimezone
      ? `Detected here: ${detectedTimezone}`
      : `Detected here: ${detectedTimezone}. Using: ${typedTimezone()}`;
  }
}

function slugifyBase(value) {
  return String(value || "").toLowerCase().replace(/[^a-z0-9]+/g, "").slice(0, 12);
}

function randomDigits(length = 4) {
  let value = "";
  for (let index = 0; index < length; index += 1) {
    value += Math.floor(Math.random() * 10);
  }
  return value;
}

function renderUsernameSuggestions() {
  if (!usernameSuggestions) return;
  const base = slugifyBase(form?.dataset.displayName || "");
  const stems = [
    `${base || "my"}health`,
    `${base || "daily"}check`,
    `${base || "steady"}care`,
    "calmcheck",
    "resetcoach",
    "dailyanchor",
  ];
  const suggestions = [];
  for (const stem of stems) {
    const candidate = `${stem}${randomDigits(stem.length > 11 ? 3 : 5)}_bot`;
    if (!suggestions.includes(candidate)) suggestions.push(candidate);
    if (suggestions.length === 3) break;
  }
  usernameSuggestions.innerHTML = "";
  suggestions.forEach((candidate) => {
    const chip = document.createElement("code");
    chip.className = "username-suggestion";
    chip.textContent = candidate;
    usernameSuggestions.appendChild(chip);
  });
}

function selectedPrimaryChannel() {
  return field("preferred_channel")?.value || "telegram";
}

function setupIsActive() {
  return setupState?.state === "active";
}

function setPrimaryChannel() {
  const hidden = field("preferred_channel");
  if (hidden) hidden.value = "telegram";
  updateFinishSummary();
}

if (telegramBadge) {
  telegramBadge.textContent = "Primary";
  telegramBadge.classList.remove("channel-badge--secondary");
}

// ── Step progress indicator ────────────────────────────────────────────────

function updateStepProgress(active) {
  progressItems.forEach((item, index) => {
    item.classList.toggle("is-active", index === active);
    item.classList.toggle("is-done", index < active);
  });
}

// ── Finish summary ─────────────────────────────────────────────────────────

function updateFinishSummary() {
  if (!finishSummary) return;
  const tone = form.querySelector('input[name="tone_style"]:checked')?.value || "gentle";
  const toneLabel = { gentle: "warm and light", direct: "clear and a bit sharper", calm: "steady and grounding" }[tone] || "warm and light";
  const channelState = (setupState?.channels || {}).telegram || {};
  finishSummary.textContent = channelState.connected
    ? setupIsActive()
      ? `Telegram is live. The starting tone is ${toneLabel}.`
      : "Telegram is linked. Finish setup and wake your companion before replies start."
    : "Connect Telegram first, then we can continue.";
  if (finishTimezone) {
    finishTimezone.textContent = `Timezone: ${typedTimezone()}. You can change it later in chat if your schedule shifts.`;
  }
  if (finishWearables) {
    const connected = Array.isArray(setupState?.wearables?.connected_providers)
      ? setupState.wearables.connected_providers
      : [];
    finishWearables.textContent = connected.length
      ? `Wearables connected: ${connected.join(", ")}.`
      : "No wearables connected — that's fine, you can add them later from chat.";
  }
}

// ── Telegram token inline hint ─────────────────────────────────────────────

function updateTelegramTokenHint(value) {
  if (!telegramTokenHint) return;
  const token = String(value || "").trim().replace(/\s+/g, "");
  if (!token) { telegramTokenHint.textContent = ""; return; }
  const looksRight = /^\d{5,}:[A-Za-z0-9_-]{20,}$/.test(token);
  if (looksRight) {
    telegramTokenHint.textContent = "Token format looks good.";
    telegramTokenHint.style.color = "var(--color-success, #15803d)";
  } else if (token.length > 8) {
    telegramTokenHint.textContent = "Should look like: 123456:ABC-DEF… (numbers, colon, letters)";
    telegramTokenHint.style.color = "var(--color-muted, #94a3b8)";
  } else {
    telegramTokenHint.textContent = "";
  }
}

if (telegramTokenInput) {
  telegramTokenInput.addEventListener("input", () => updateTelegramTokenHint(telegramTokenInput.value));
}

// ── Wearable tile renderer ─────────────────────────────────────────────────

/**
 * Build a single wearable provider tile element.
 * state: "connect" | "connected" | "soon" | "error"
 */
function buildWearableTile(provider, state) {
  const tile = document.createElement("div");
  tile.className = `wearable-tile${state === "connected" ? " is-connected" : ""}`;
  tile.dataset.provider = provider.provider;

  const header = document.createElement("div");
  header.className = "wearable-tile__header";

  const logoWrap = document.createElement("div");
  logoWrap.className = "wearable-tile__logo";
  const img = document.createElement("img");
  img.src = provider.logo || `/static/wearables/${provider.provider}.svg`;
  img.alt = provider.name;
  img.width = 32;
  img.height = 32;
  logoWrap.appendChild(img);

  const nameEl = document.createElement("div");
  nameEl.className = "wearable-tile__name";
  nameEl.textContent = provider.name;

  header.appendChild(logoWrap);
  header.appendChild(nameEl);

  const blurb = document.createElement("div");
  blurb.className = "wearable-tile__blurb";
  blurb.textContent = provider.blurb || "";

  const actions = document.createElement("div");
  actions.className = "wearable-tile__actions";

  if (state === "connected") {
    const chip = document.createElement("span");
    chip.className = "wearable-tile__chip wearable-tile__chip--connected";
    chip.textContent = "✓ Connected";
    actions.appendChild(chip);

    const syncBtn = document.createElement("button");
    syncBtn.type = "button";
    syncBtn.className = "wearable-tile__sync-btn";
    syncBtn.textContent = "Sync now";
    syncBtn.addEventListener("click", () => handleTileSync(provider.provider, syncBtn));
    actions.appendChild(syncBtn);
  } else if (state === "connect") {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "wearable-tile__chip wearable-tile__chip--connect";
    chip.textContent = "Connect";
    chip.addEventListener("click", () => handleTileConnect(provider.provider));
    actions.appendChild(chip);
  } else if (state === "error") {
    const chip = document.createElement("span");
    chip.className = "wearable-tile__chip wearable-tile__chip--error";
    chip.textContent = "Sync failing";
    actions.appendChild(chip);

    const retryBtn = document.createElement("button");
    retryBtn.type = "button";
    retryBtn.className = "wearable-tile__sync-btn";
    retryBtn.textContent = "Retry";
    retryBtn.addEventListener("click", () => handleTileSync(provider.provider, retryBtn));
    actions.appendChild(retryBtn);
  } else {
    // "soon"
    const chip = document.createElement("span");
    chip.className = "wearable-tile__chip wearable-tile__chip--soon";
    chip.title = "This Healthclaw host hasn't enabled wearables yet.";
    chip.textContent = "Coming soon";
    actions.appendChild(chip);
  }

  tile.appendChild(header);
  tile.appendChild(blurb);
  tile.appendChild(actions);
  return tile;
}

/**
 * Derive tile state from wearables payload for a given provider slug.
 */
function tileState(slug, wearables) {
  if (!wearables.configured) return "soon";
  const available = Array.isArray(wearables.available_providers) ? wearables.available_providers : [];
  const availableSlugs = new Set(available.map((p) => String(p.provider || "").toLowerCase()));
  const connected = Array.isArray(wearables.connected_providers)
    ? new Set(wearables.connected_providers.map((s) => String(s).toLowerCase()))
    : new Set();

  if (connected.has(slug)) return "connected";
  if (availableSlugs.has(slug)) return "connect";
  return "soon";
}

function renderWearablesState(wearables) {
  const featured = Array.isArray(wearables?.featured_providers) ? wearables.featured_providers : [];
  const available = Array.isArray(wearables?.available_providers) ? wearables.available_providers : [];
  const connected = Array.isArray(wearables?.connected_providers) ? wearables.connected_providers : [];

  // Merge: use featured list for the header tiles, then add remaining available providers
  const featuredSlugs = new Set(featured.map((p) => p.provider));
  const extended = available.filter((p) => !featuredSlugs.has(p.provider));

  // Render featured grid
  if (wearableFeaturedGrid) {
    wearableFeaturedGrid.innerHTML = "";
    const toRender = featured.length
      ? featured
      : [
          { provider: "apple-health", name: "Apple Health", logo: "/static/wearables/apple-health.svg", blurb: "Sleep, steps, heart rate" },
          { provider: "google-fit", name: "Google Fit / Health Connect", logo: "/static/wearables/google-fit.svg", blurb: "Steps, workouts, heart rate" },
          { provider: "fitbit", name: "Fitbit", logo: "/static/wearables/fitbit.svg", blurb: "Sleep score, steps, resting HR" },
        ];
    toRender.forEach((provider) => {
      wearableFeaturedGrid.appendChild(buildWearableTile(provider, tileState(provider.provider, wearables)));
    });
  }

  // Render extended grid
  if (moreProvidersGrid) {
    moreProvidersGrid.innerHTML = "";
    extended.forEach((provider) => {
      moreProvidersGrid.appendChild(buildWearableTile(provider, tileState(provider.provider, wearables)));
    });
    // Auto-expand if none of the featured three are connectable
    const featuredConnectable = featured.some((p) => tileState(p.provider, wearables) !== "soon");
    if (!featuredConnectable && extended.length > 0) {
      moreProvidersGrid.classList.add("is-open");
      if (moreProvidersToggle) moreProvidersToggle.classList.add("is-open");
    }
    if (moreProvidersToggle) {
      moreProvidersToggle.style.display = extended.length ? "" : "none";
    }
  }

  // Sync hidden select for any legacy paths
  if (wearablesProviderSelect) {
    const currentValue = wearablesProviderSelect.value;
    wearablesProviderSelect.innerHTML = '<option value="">Choose a provider…</option>';
    available.forEach((provider) => {
      const option = document.createElement("option");
      option.value = provider.provider;
      option.textContent = provider.name || provider.provider;
      wearablesProviderSelect.appendChild(option);
    });
    if (currentValue && available.some((p) => p.provider === currentValue)) {
      wearablesProviderSelect.value = currentValue;
    }
  }

  // Connected summary bar
  if (wearableConnectedChips) {
    wearableConnectedChips.innerHTML = "";
    connected.forEach((slug) => {
      const chip = document.createElement("span");
      chip.className = "wearable-connected-chip";
      chip.textContent = slug;
      wearableConnectedChips.appendChild(chip);
    });
  }

  if (wearablesFreshness) {
    const freshness = wearables?.snapshot?.freshness_note || wearables?.snapshot?.freshness || "";
    wearablesFreshness.textContent = freshness ? `Data freshness: ${freshness}.` : "No wearable snapshot yet.";
  }

  if (wearableExampleHint) {
    const sleepScore = wearables?.snapshot?.summaries?.sleep?.score;
    if (sleepScore != null) {
      wearableExampleHint.textContent = `e.g. last night's sleep score: ${sleepScore}`;
      wearableExampleHint.style.display = "";
    } else {
      wearableExampleHint.style.display = "none";
    }
  }

  if (wearablesSummary) {
    if (!wearables?.configured) {
      setInlineStatus(wearablesSummary, "Wearables aren't enabled on this host yet — you can skip this step.");
    } else if (wearables?.last_error) {
      setInlineStatus(wearablesSummary, wearables.last_error, true);
    } else if (connected.length) {
      const lastSync = wearables?.last_sync_at || "not synced yet";
      setInlineStatus(wearablesSummary, `Connected to ${connected.join(", ")}. Last sync: ${lastSync}.`);
    } else {
      setInlineStatus(wearablesSummary, "You can skip this and add wearables later from chat.");
    }
  }
}

// ── Tile connect / sync handlers ───────────────────────────────────────────

async function handleTileConnect(providerSlug) {
  const token = form.dataset.setupToken;
  setInlineStatus(wearablesSummary, `Connecting to ${providerSlug}…`);
  try {
    const data = await fetchJson(`/api/setup/${token}/wearables/connect`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ provider: providerSlug }),
    });
    await refreshStatus();
    const authUrl = data.authorizationUrl || "";
    if (!authUrl) throw new Error("Open Wearables did not return an authorization URL.");
    window.location.href = authUrl;
  } catch (err) {
    setInlineStatus(wearablesSummary, err.message || "Unable to start wearable connection.", true);
  }
}

async function handleTileSync(providerSlug, btn) {
  const token = form.dataset.setupToken;
  if (btn) btn.textContent = "Syncing…";
  setInlineStatus(wearablesSummary, `Syncing ${providerSlug}…`);
  try {
    await fetchJson(`/api/setup/${token}/wearables/sync`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ provider: providerSlug }),
    });
    await refreshStatus();
    setInlineStatus(wearablesSummary, "Wearable data synced.");
  } catch (err) {
    setInlineStatus(wearablesSummary, err.message || "Unable to sync wearables.", true);
  } finally {
    if (btn) btn.textContent = "Sync now";
  }
}

// More providers toggle
if (moreProvidersToggle) {
  moreProvidersToggle.addEventListener("click", () => {
    const isOpen = moreProvidersGrid.classList.toggle("is-open");
    moreProvidersToggle.classList.toggle("is-open", isOpen);
  });
}

// ── Provider state ─────────────────────────────────────────────────────────

function renderProviderState(provider) {
  if (!providerSummary) return;
  const name = (provider?.provider || "").toLowerCase();
  const label = name === "ollama" ? "Ollama (local)" : name === "openrouter" ? "OpenRouter" : name === "minimax" ? "MiniMax" : name;
  if (provider?.validated_at || provider?.has_api_key) {
    providerSummary.textContent = label ? `${label} connected.` : "Provider connected.";
  }
}

// ── Telegram state ─────────────────────────────────────────────────────────

function renderTelegramState(telegram) {
  const connected = Boolean(telegram?.connected);
  if (telegramConnectedState) telegramConnectedState.hidden = !connected;
  if (connected) {
    if (telegramConnectedCopy) {
      telegramConnectedCopy.textContent = telegram.bot_username
        ? setupIsActive()
          ? `Live as @${telegram.bot_username}.`
          : `Linked as @${telegram.bot_username}. Finish setup to start replies.`
        : setupIsActive()
          ? "Your Telegram bot is live."
          : "Your Telegram bot is linked. Finish setup to start replies.";
    }
    setInlineStatus(
      telegramSummary,
      telegram.bot_username
        ? setupIsActive()
          ? `Live as @${telegram.bot_username}.`
          : `Linked as @${telegram.bot_username}. Activate the companion to start replies.`
        : setupIsActive()
          ? "Telegram is live."
          : "Telegram is linked. Activate the companion to start replies.",
    );
  } else {
    setInlineStatus(telegramSummary, "Paste a BotFather token to connect Telegram.");
  }
}

// ── Step visibility + buttons ──────────────────────────────────────────────

function updateStep() {
  steps.forEach((step, index) => {
    step.classList.toggle("active", index === currentStep);
  });
  backButton.style.visibility = currentStep === 0 ? "hidden" : "visible";
  const isLast = currentStep === steps.length - 1;
  nextButton.style.display = isLast ? "none" : "inline-flex";
  activateButton.style.display = isLast ? "inline-flex" : "none";

  // Show skip only on skippable steps
  if (skipButton) {
    skipButton.style.display = SKIPPABLE_STEPS.has(currentStep) ? "inline-flex" : "none";
  }

  updateStepProgress(currentStep);
}

// ── Form helpers ───────────────────────────────────────────────────────────

function selectedProviderType() {
  return form ? (form.querySelector('[name="provider_type"]:checked')?.value || "ollama") : "ollama";
}

function updateProviderSections() {
  const isOllama = selectedProviderType() === "ollama";
  if (providerOllamaSection) providerOllamaSection.style.display = isOllama ? "" : "none";
  if (providerApiSection) providerApiSection.style.display = isOllama ? "none" : "";
}

function setStatus(message, isError = false) {
  statusNode.textContent = message;
  statusNode.classList.toggle("status-error", isError);
}

function setInlineStatus(node, message, isError = false) {
  if (!node) return;
  node.textContent = message;
  node.classList.toggle("status-error", isError);
}

function field(name) {
  return form.querySelector(`[name="${name}"]`);
}

function setFieldValue(name, value) {
  const element = field(name);
  if (!element) return;
  if (element.type === "checkbox") { element.checked = Boolean(value); return; }
  if (Array.isArray(value)) { element.value = value.join("\n"); return; }
  element.value = value ?? "";
}

function fillProfile(profile) {
  if (!profile) { seedTimezoneField(); return; }
  const phase1 = profile.phase1 || {};
  const phase2 = profile.phase2 || {};
  if (phase1.timezone) seedTimezoneField(phase1.timezone);
  else seedTimezoneField();
  setPrimaryChannel();
  if (typeof phase2.morning_check_in === "boolean") setFieldValue("morning_check_in", phase2.morning_check_in);
  if (typeof phase2.weekly_summary === "boolean") setFieldValue("weekly_summary", phase2.weekly_summary);
}

function orderChannelLinks(primaryChannel, links) {
  const ordered = [];
  if (primaryChannel && links[primaryChannel]) ordered.push(primaryChannel);
  Object.keys(links || {}).forEach((name) => {
    if (links[name] && !ordered.includes(name)) ordered.push(name);
  });
  return ordered;
}

function renderCompletion(preferredChannel, links) {
  try { window.localStorage.removeItem(SETUP_TOKEN_KEY); } catch (e) {}
  completionActions.innerHTML = "";
  orderChannelLinks("telegram", { telegram: (links || {}).telegram || "" }).forEach((name) => {
    const anchor = document.createElement("a");
    anchor.href = links[name];
    anchor.target = "_blank";
    anchor.rel = "noopener";
    anchor.className = "channel-link";
    anchor.textContent = "Open Telegram";
    completionActions.appendChild(anchor);
  });
  const token = form?.dataset.setupToken || "";
  const displayName = (form?.dataset.displayName || "").trim();
  const tone = form.querySelector('input[name="tone_style"]:checked')?.value || "gentle";
  const toneLabel = { gentle: "warmly", direct: "with a push", calm: "with calm energy" }[tone] || "warmly";
  if (completionGreeting) {
    const who = displayName || "there";
    completionGreeting.textContent = `Hey ${who}. I'm awake and I'll show up in Telegram ${toneLabel}.`;
  }
  if (webChatLink && token) {
    webChatLink.href = `/chat/${encodeURIComponent(token)}`;
    webChatLink.hidden = false;
  }
  form.hidden = true;
  completionNode.hidden = false;
}

function profilePayload() {
  const tone = form.querySelector('input[name="tone_style"]:checked')?.value || "gentle";
  return {
    phase1: {
      full_name: (form?.dataset.displayName || "").trim(),
      location: "",
      timezone: typedTimezone(),
      language: detectLanguage(),
      preferred_channel: selectedPrimaryChannel(),
      wake_time: "",
      sleep_time: "",
      consents: ["privacy", "emergency", "coaching"],
    },
    phase2: {
      goals: [],
      reminder_preferences: [TONE_PREFERENCES[tone] || TONE_PREFERENCES.gentle],
      morning_check_in: Boolean(field("morning_check_in")?.checked),
      weekly_summary: Boolean(field("weekly_summary")?.checked),
    },
  };
}

// ── Network ────────────────────────────────────────────────────────────────

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const ref = data.errorId || data.requestId || response.headers.get("X-Request-ID") || "";
    const detail = data.detail;
    if (Array.isArray(detail)) {
      const message = detail.map((item) => {
        const path = Array.isArray(item.loc) ? item.loc.join(".") : "";
        const msg = item.msg || "Invalid value";
        return path ? `${path}: ${msg}` : msg;
      }).join("; ");
      const fullMessage = message || "Request failed.";
      throw new Error(ref ? `${fullMessage} Ref: ${ref}` : fullMessage);
    }
    const baseMessage = detail || "Request failed.";
    throw new Error(ref ? `${baseMessage} Ref: ${ref}` : baseMessage);
  }
  return data;
}

// ── Status refresh ─────────────────────────────────────────────────────────

async function refreshStatus() {
  const token = form.dataset.setupToken;
  setupState = await fetchJson(`/api/setup/${token}/status`);
  const channels = setupState.channels || {};
  const telegram = channels.telegram || {};
  let wearables = setupState.wearables || {};

  if (wearables.configured && (!Array.isArray(wearables.available_providers) || wearables.available_providers.length === 0)) {
    try {
      const data = await fetchJson(`/api/setup/${token}/wearables/providers`);
      wearables = data.wearables || wearables;
      setupState.wearables = wearables;
    } catch (e) {}
  }

  fillProfile(setupState.profile);
  renderProviderState(setupState.provider || {});
  renderTelegramState(telegram);
  renderWearablesState(wearables);
  updateProviderSections();

  const reminderPreferences = (setupState.profile?.phase2 || {}).reminder_preferences || [];
  if (Array.isArray(reminderPreferences) && reminderPreferences.length) {
    const reminder = reminderPreferences[0];
    const toneInput = {
      [TONE_PREFERENCES.gentle]: "gentle",
      [TONE_PREFERENCES.direct]: "direct",
      [TONE_PREFERENCES.calm]: "calm",
    }[reminder];
    if (toneInput) {
      const toneField = form.querySelector(`input[name="tone_style"][value="${toneInput}"]`);
      if (toneField) toneField.checked = true;
    }
  }
  updateFinishSummary();

  if (setupState.state === "active") {
    const preferred = setupState.profile?.phase1?.preferred_channel || selectedPrimaryChannel();
    renderCompletion(preferred, setupState.channelLinks || {});
  }
}

// ── Actions ────────────────────────────────────────────────────────────────

async function saveProvider() {
  const token = form.dataset.setupToken;
  const providerType = selectedProviderType();
  if (providerType === "ollama") {
    if (providerSummary) providerSummary.textContent = "Checking Ollama connection…";
    try {
      await fetchJson(`/api/setup/${token}/provider`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ provider: "ollama", api_key: "" }),
      });
    } catch (err) {
      if (providerSummary) providerSummary.textContent = "";
      throw err;
    }
    if (providerSummary) providerSummary.textContent = "Ollama connected. Running locally.";
  } else {
    const providerName = (form.querySelector('[name="provider_name"]')?.value || "").trim() || "openrouter";
    const apiKey = (form.querySelector('[name="provider_api_key"]')?.value || "").trim();
    if (!apiKey) throw new Error("Paste your API key before continuing.");
    if (providerSummary) providerSummary.textContent = "Validating API key…";
    try {
      await fetchJson(`/api/setup/${token}/provider`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ provider: providerName, api_key: apiKey }),
      });
    } catch (err) {
      if (providerSummary) providerSummary.textContent = "";
      throw err;
    }
    if (providerSummary) providerSummary.textContent = "Provider connected.";
  }
}

function normalizeTelegramBotToken(value) {
  return String(value || "").trim().replace(/\s+/g, "");
}

function validateTelegramBotTokenFormat(value) {
  const token = normalizeTelegramBotToken(value);
  if (!token) throw new Error("Paste your Telegram bot token first.");
  const looksRight = /^\d{5,}:[A-Za-z0-9_-]{20,}$/.test(token);
  if (!looksRight) throw new Error('That token doesn\'t look right. It should look like "123456:ABC-DEF…" (numbers, colon, then letters).');
  return token;
}

async function saveTelegram() {
  const botToken = validateTelegramBotTokenFormat(field("telegram_bot_token").value);
  setFieldValue("telegram_bot_token", botToken);
  const token = form.dataset.setupToken;
  setInlineStatus(telegramSummary, "Checking your Telegram bot token…");
  await fetchJson(`/api/setup/${token}/channels/telegram`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ bot_token: botToken }),
  });
  await refreshStatus();
  setInlineStatus(telegramSummary, "Telegram is connected.");
}

async function saveProfile() {
  const token = form.dataset.setupToken;
  setStatus("Saving…");
  await fetchJson(`/api/setup/${token}/profile`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(profilePayload()),
  });
  await refreshStatus();
  setStatus("Saved.");
}

async function activateSetup() {
  const token = form.dataset.setupToken;
  setStatus("Starting your companion…");
  const data = await fetchJson(`/api/setup/${token}/activate`, { method: "POST" });
  if (setupState) {
    setupState.state = data.state || "active";
    if (data.channelLinks) setupState.channelLinks = data.channelLinks;
  }
  setStatus("Your companion is ready.");
  renderCompletion(
    data.preferredChannel || selectedPrimaryChannel(),
    data.channelLinks || setupState?.channelLinks || {},
  );
}

// ── Step navigation ────────────────────────────────────────────────────────

async function handleNext() {
  try {
    if (currentStep === 0) {
      await saveProvider();
      currentStep += 1;
      updateStep();
      return;
    }
    if (currentStep === 1) {
      const hasTelegramToken = field("telegram_bot_token").value.trim();
      if (hasTelegramToken && !((setupState?.channels || {}).telegram || {}).connected) {
        await saveTelegram();
      }
      const telegramMeta = ((setupState?.channels || {}).telegram) || {};
      if (!telegramMeta.connected) throw new Error("Connect Telegram before you continue.");
      currentStep += 1;
      updateStep();
      return;
    }
    if (currentStep === 2) {
      // Wearables — optional, Continue just advances
      currentStep += 1;
      updateStep();
      return;
    }
    if (currentStep === 3) {
      await saveProfile();
      currentStep += 1;
      updateStep();
    }
  } catch (error) {
    setStatus(error.message || "Something went wrong.", true);
  }
}

function handleSkip() {
  if (SKIPPABLE_STEPS.has(currentStep)) {
    currentStep += 1;
    updateStep();
    setStatus("");
  }
}

// ── Event listeners ────────────────────────────────────────────────────────

connectTelegramButton.addEventListener("click", async () => {
  try {
    await saveTelegram();
  } catch (error) {
    setInlineStatus(telegramSummary, error.message || "Unable to connect Telegram.", true);
  }
});

if (openBotFatherButton) {
  openBotFatherButton.addEventListener("click", () => {
    window.open("https://t.me/BotFather", "_blank", "noopener");
  });
}

if (skipButton) skipButton.addEventListener("click", handleSkip);
nextButton.addEventListener("click", handleNext);
backButton.addEventListener("click", () => {
  currentStep = Math.max(currentStep - 1, 0);
  updateStep();
});
form.addEventListener("change", (e) => {
  seedTimezoneField();
  updateFinishSummary();
  if (e.target && e.target.name === "provider_type") updateProviderSections();
});
form.addEventListener("input", () => {
  seedTimezoneField();
  updateFinishSummary();
});
activateButton.addEventListener("click", async () => {
  try {
    await activateSetup();
  } catch (error) {
    setStatus(error.message || "Unable to activate your assistant.", true);
  }
});

// ── Init ───────────────────────────────────────────────────────────────────

updateProviderSections();
renderUsernameSuggestions();
seedTimezoneField();
setPrimaryChannel();
updateStep();
refreshStatus().catch(() => {});
runSpawnSequence().catch(() => {
  if (spawnOverlay) spawnOverlay.classList.add("is-done");
});
