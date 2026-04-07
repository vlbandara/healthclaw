const form = document.getElementById("setup-form");
const steps = [...document.querySelectorAll(".step")];
const nextButton = document.getElementById("next");
const backButton = document.getElementById("back");
const activateButton = document.getElementById("activate");
const statusNode = document.getElementById("status");
const completionNode = document.getElementById("completion");
const completionActions = document.getElementById("completion-actions");
const telegramSummary = document.getElementById("telegram-summary");
const finishSummary = document.getElementById("finish-summary");
const connectTelegramButton = document.getElementById("connect-telegram");

let currentStep = 0;
let setupState = null;

function parseLines(value) {
  return (value || "")
    .split("\n")
    .map((item) => item.trim())
    .filter(Boolean);
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
  if (!profile || !profile.phase1) {
    return;
  }
  Object.entries(profile.phase1).forEach(([name, value]) => {
    if (name === "consents") {
      form.querySelectorAll('input[name="consents"]').forEach((checkbox) => {
        checkbox.checked = (value || []).includes(checkbox.value);
      });
      return;
    }
    setFieldValue(name, value);
  });
  Object.entries(profile.phase2 || {}).forEach(([name, value]) => {
    if (name === "morning_check_in" || name === "weekly_summary") {
      const checkbox = field(name);
      if (checkbox) {
        checkbox.checked = Boolean(value);
      }
      return;
    }
    setFieldValue(name, value);
  });
}

function renderCompletion(links) {
  completionActions.innerHTML = "";
  Object.entries(links || {}).forEach(([name, url]) => {
    if (!url) {
      return;
    }
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.target = "_blank";
    anchor.rel = "noopener";
    anchor.className = `channel-link${name === "whatsapp" ? " secondary-link" : ""}`;
    anchor.textContent = name === "telegram" ? "Open Telegram" : "Open WhatsApp";
    completionActions.appendChild(anchor);
  });
  form.hidden = true;
  completionNode.hidden = false;
}

function profilePayload() {
  const checkboxGroups = new Map();
  form.querySelectorAll("[name]").forEach((element) => {
    if (element.type !== "checkbox") {
      return;
    }
    if (!checkboxGroups.has(element.name)) {
      checkboxGroups.set(element.name, []);
    }
    if (element.checked) {
      checkboxGroups.get(element.name).push(element.value);
    }
  });

  return {
    phase1: {
      full_name: field("full_name").value,
      email: field("email").value,
      phone: field("phone").value,
      timezone: field("timezone").value,
      language: field("language").value,
      preferred_channel: field("preferred_channel").value,
      age_range: field("age_range").value,
      sex: field("sex").value,
      gender: field("gender").value,
      height_cm: field("height_cm").value ? Number(field("height_cm").value) : null,
      weight_kg: field("weight_kg").value ? Number(field("weight_kg").value) : null,
      known_conditions: parseLines(field("known_conditions").value),
      medications: parseLines(field("medications").value),
      allergies: parseLines(field("allergies").value),
      wake_time: field("wake_time").value,
      sleep_time: field("sleep_time").value,
      consents: checkboxGroups.get("consents") || [],
    },
    phase2: {
      mood_interest: Number(field("mood_interest").value || 0),
      mood_down: Number(field("mood_down").value || 0),
      activity_level: field("activity_level").value,
      nutrition_quality: field("nutrition_quality").value,
      sleep_quality: field("sleep_quality").value,
      stress_level: field("stress_level").value,
      goals: parseLines(field("goals").value),
      current_concerns: field("current_concerns").value,
      reminder_preferences: parseLines(field("reminder_preferences").value),
      medication_reminder_windows: parseLines(field("medication_reminder_windows").value),
      morning_check_in: field("morning_check_in").checked,
      weekly_summary: field("weekly_summary").checked,
    },
  };
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.detail || "Request failed.");
  }
  return data;
}

async function refreshStatus() {
  const token = form.dataset.setupToken;
  setupState = await fetchJson(`/api/setup/${token}/status`);

  const telegram = (setupState.channels || {}).telegram || {};
  telegramSummary.textContent = telegram.connected
    ? `Connected as @${telegram.bot_username || "your_bot"}.`
    : "Telegram is not connected yet.";
  if (telegram.connected && telegram.bot_username) {
    setFieldValue("preferred_channel", "telegram");
  }

  fillProfile(setupState.profile);
  finishSummary.textContent = setupState.activationReady
    ? "Everything looks ready. Turn on your assistant when you’re ready."
    : "You can activate once Telegram is connected and your profile is saved.";

  if (setupState.state === "active") {
    renderCompletion(setupState.channelLinks || {});
  }
}

async function saveTelegram() {
  const botToken = field("telegram_bot_token").value.trim();
  if (!botToken) {
    throw new Error("Paste your Telegram bot token first.");
  }
  const token = form.dataset.setupToken;
  setStatus("Checking your Telegram bot token…");
  await fetchJson(`/api/setup/${token}/channels/telegram`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ bot_token: botToken }),
  });
  await refreshStatus();
  setStatus("Telegram is connected.");
}

async function saveProfile() {
  const token = form.dataset.setupToken;
  setStatus("Saving your profile…");
  await fetchJson(`/api/setup/${token}/profile`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(profilePayload()),
  });
  await refreshStatus();
  setStatus("Your profile is saved.");
}

async function activateSetup() {
  const token = form.dataset.setupToken;
  setStatus("Spinning up your coach…");
  const data = await fetchJson(`/api/setup/${token}/activate`, {
    method: "POST",
  });
  setStatus("Your assistant is ready.");
  renderCompletion(data.channelLinks || {});
}

async function handleNext() {
  try {
    if (currentStep === 0) {
      currentStep += 1;
      updateStep();
      return;
    }
    if (currentStep === 1) {
      const hasTelegramToken = field("telegram_bot_token").value.trim();
      if (hasTelegramToken && !((setupState?.channels || {}).telegram || {}).connected) {
        await saveTelegram();
      }
      const channels = setupState?.channels || {};
      const hasConnectedChannel = Object.values(channels).some((channel) => channel && channel.connected);
      if (!hasConnectedChannel) {
        throw new Error("Connect Telegram before you continue.");
      }
      currentStep += 1;
      updateStep();
      return;
    }
    if (currentStep === 2) {
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
    setStatus(error.message || "Unable to connect Telegram.", true);
  }
});

nextButton.addEventListener("click", handleNext);
backButton.addEventListener("click", () => {
  currentStep = Math.max(currentStep - 1, 0);
  updateStep();
});
activateButton.addEventListener("click", async () => {
  try {
    await activateSetup();
  } catch (error) {
    setStatus(error.message || "Unable to activate your assistant.", true);
  }
});

updateStep();
refreshStatus().catch(() => {});

