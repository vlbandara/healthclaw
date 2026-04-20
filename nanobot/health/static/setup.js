const form = document.getElementById("setup-form");
const steps = [...document.querySelectorAll(".step")];
const nextButton = document.getElementById("next");
const backButton = document.getElementById("back");
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
const finishSummary = document.getElementById("finish-summary");
const finishTimezone = document.getElementById("finish-timezone");
const connectTelegramButton = document.getElementById("connect-telegram");
const openBotFatherButton = document.getElementById("open-botfather");
const timezoneInput = document.querySelector('[name="timezone"]');
const setupTimezonePill = document.getElementById("setup-timezone-pill");
const usernameSuggestions = document.getElementById("username-suggestions");
const SETUP_TOKEN_KEY = "nanobot-health-setup-token";

const TONE_PREFERENCES = {
  gentle: "Warm, gentle nudges",
  direct: "Direct, motivating pushes",
  calm: "Calm grounding support",
};

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
  if (!spawnOverlay || !spawnLine || !spawnBar) {
    return;
  }
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
  if (companion) {
    companion.setAttribute("data-state", "idle");
  }
  spawnOverlay.classList.add("is-done");
  spawnOverlay.setAttribute("aria-hidden", "true");
}

function typedTimezone() {
  return String(timezoneInput?.value || "").trim() || detectedTimezone;
}

function seedTimezoneField(value = "") {
  if (!timezoneInput) {
    return;
  }
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
  return String(value || "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "")
    .slice(0, 12);
}

function randomDigits(length = 4) {
  let value = "";
  for (let index = 0; index < length; index += 1) {
    value += Math.floor(Math.random() * 10);
  }
  return value;
}

function renderUsernameSuggestions() {
  if (!usernameSuggestions) {
    return;
  }
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
    if (!suggestions.includes(candidate)) {
      suggestions.push(candidate);
    }
    if (suggestions.length === 3) {
      break;
    }
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

function primaryChannelLabel() {
  return "Telegram";
}

function setupIsActive() {
  return setupState?.state === "active";
}

function setPrimaryChannel() {
  const hidden = field("preferred_channel");
  if (hidden) {
    hidden.value = "telegram";
  }
  updateFinishSummary();
}

if (telegramBadge) {
  telegramBadge.textContent = "Primary";
  telegramBadge.classList.remove("channel-badge--secondary");
}

function updateFinishSummary() {
  if (!finishSummary) {
    return;
  }
  const tone = form.querySelector('input[name="tone_style"]:checked')?.value || "gentle";
  const toneLabel = {
    gentle: "warm and light",
    direct: "clear and a bit sharper",
    calm: "steady and grounding",
  }[tone] || "warm and light";
  const channelState = (setupState?.channels || {}).telegram || {};
  finishSummary.textContent = channelState.connected
    ? setupIsActive()
      ? `Telegram is live. The starting tone is ${toneLabel}.`
      : "Telegram is linked. Finish setup and wake your companion before replies start."
    : "Connect Telegram first, then we can continue.";
  if (finishTimezone) {
    finishTimezone.textContent = `Timezone: ${typedTimezone()}. You can change it later in chat if your schedule shifts.`;
  }
}

function normalizeTelegramBotToken(value) {
  return String(value || "")
    .trim()
    .replace(/\s+/g, "");
}

function validateTelegramBotTokenFormat(value) {
  const token = normalizeTelegramBotToken(value);
  if (!token) {
    throw new Error("Paste your Telegram bot token first.");
  }
  const looksRight = /^\d{5,}:[A-Za-z0-9_-]{20,}$/.test(token);
  if (!looksRight) {
    throw new Error(
      "That token doesn’t look right. It should look like “123456:ABC-DEF...” (numbers, colon, then letters).",
    );
  }
  return token;
}

function updateStep() {
  steps.forEach((step, index) => {
    step.classList.toggle("active", index === currentStep);
  });
  backButton.style.visibility = currentStep === 0 ? "hidden" : "visible";
  nextButton.style.display = currentStep === steps.length - 1 ? "none" : "inline-flex";
  activateButton.style.display = currentStep === steps.length - 1 ? "inline-flex" : "none";
}

function setStatus(message, isError = false) {
  statusNode.textContent = message;
  statusNode.classList.toggle("status-error", isError);
}

function setInlineStatus(node, message, isError = false) {
  if (!node) {
    return;
  }
  node.textContent = message;
  node.classList.toggle("status-error", isError);
}

function field(name) {
  return form.querySelector(`[name="${name}"]`);
}

function setFieldValue(name, value) {
  const element = field(name);
  if (!element) {
    return;
  }
  if (element.type === "checkbox") {
    element.checked = Boolean(value);
    return;
  }
  if (Array.isArray(value)) {
    element.value = value.join("\n");
    return;
  }
  element.value = value ?? "";
}

function fillProfile(profile) {
  if (!profile) {
    seedTimezoneField();
    return;
  }
  const phase1 = profile.phase1 || {};
  const phase2 = profile.phase2 || {};
  if (phase1.timezone) {
    seedTimezoneField(phase1.timezone);
  } else {
    seedTimezoneField();
  }
  setPrimaryChannel();
  if (typeof phase2.morning_check_in === "boolean") {
    setFieldValue("morning_check_in", phase2.morning_check_in);
  }
  if (typeof phase2.weekly_summary === "boolean") {
    setFieldValue("weekly_summary", phase2.weekly_summary);
  }
}

function orderChannelLinks(primaryChannel, links) {
  const ordered = [];
  if (primaryChannel && links[primaryChannel]) {
    ordered.push(primaryChannel);
  }
  Object.keys(links || {}).forEach((name) => {
    if (links[name] && !ordered.includes(name)) {
      ordered.push(name);
    }
  });
  return ordered;
}

function renderCompletion(preferredChannel, links) {
  try {
    window.localStorage.removeItem(SETUP_TOKEN_KEY);
  } catch (e) {
    // Ignore storage failures.
  }
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
  const toneLabel = {
    gentle: "warmly",
    direct: "with a push",
    calm: "with calm energy",
  }[tone] || "warmly";
  if (completionGreeting) {
    const who = displayName || "there";
    completionGreeting.textContent = `Hey ${who}. I’m awake and I’ll show up in Telegram ${toneLabel}.`;
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

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const ref = data.errorId || data.requestId || response.headers.get("X-Request-ID") || "";
    const detail = data.detail;
    if (Array.isArray(detail)) {
      const message = detail
        .map((item) => {
          const path = Array.isArray(item.loc) ? item.loc.join(".") : "";
          const msg = item.msg || "Invalid value";
          return path ? `${path}: ${msg}` : msg;
        })
        .join("; ");
      const fullMessage = message || "Request failed.";
      throw new Error(ref ? `${fullMessage} Ref: ${ref}` : fullMessage);
    }
    const baseMessage = detail || "Request failed.";
    throw new Error(ref ? `${baseMessage} Ref: ${ref}` : baseMessage);
  }
  return data;
}

function renderTelegramState(telegram) {
  const connected = Boolean(telegram.connected);
  telegramConnectedState.hidden = !connected;
  if (connected) {
    telegramConnectedCopy.textContent = telegram.bot_username
      ? setupIsActive()
        ? `Live as @${telegram.bot_username}.`
        : `Linked as @${telegram.bot_username}. Finish setup to start replies.`
      : setupIsActive()
        ? "Your Telegram bot is live."
        : "Your Telegram bot is linked. Finish setup to start replies.";
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

async function refreshStatus() {
  const token = form.dataset.setupToken;
  setupState = await fetchJson(`/api/setup/${token}/status`);
  const channels = setupState.channels || {};
  const telegram = channels.telegram || {};

  fillProfile(setupState.profile);
  renderTelegramState(telegram);

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
      if (toneField) {
        toneField.checked = true;
      }
    }
  }
  updateFinishSummary();

  if (setupState.state === "active") {
    const preferred = setupState.profile?.phase1?.preferred_channel || selectedPrimaryChannel();
    renderCompletion(preferred, setupState.channelLinks || {});
  }
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
  const data = await fetchJson(`/api/setup/${token}/activate`, {
    method: "POST",
  });
  setStatus("Your companion is ready.");
  renderCompletion(
    data.preferredChannel || selectedPrimaryChannel(),
    data.channelLinks || setupState?.channelLinks || {},
  );
}

async function handleNext() {
  try {
    if (currentStep === 0) {
      const hasTelegramToken = field("telegram_bot_token").value.trim();
      if (hasTelegramToken && !((setupState?.channels || {}).telegram || {}).connected) {
        await saveTelegram();
      }
      const telegramMeta = ((setupState?.channels || {}).telegram) || {};
      if (!telegramMeta.connected) {
        throw new Error("Connect Telegram before you continue.");
      }
      currentStep += 1;
      updateStep();
      return;
    }
    if (currentStep === 1) {
      await saveProfile();
      currentStep += 1;
      updateStep();
    }
  } catch (error) {
    setStatus(error.message || "Something went wrong.", true);
  }
}

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

nextButton.addEventListener("click", handleNext);
backButton.addEventListener("click", () => {
  currentStep = Math.max(currentStep - 1, 0);
  updateStep();
});
form.addEventListener("change", () => {
  seedTimezoneField();
  updateFinishSummary();
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

renderUsernameSuggestions();
seedTimezoneField();
setPrimaryChannel();
updateStep();
refreshStatus().catch(() => {});
runSpawnSequence().catch(() => {
  if (spawnOverlay) {
    spawnOverlay.classList.add("is-done");
  }
});
