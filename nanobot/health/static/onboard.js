const form = document.getElementById("onboard-form");
const cardSteps = [...document.querySelectorAll(".card-step")];
const nextButton = document.getElementById("next");
const backButton = document.getElementById("back");
const submitButton = document.getElementById("submit");
const statusNode = document.getElementById("status");
const completionNode = document.getElementById("completion");
const completionActions = document.getElementById("completion-actions");
const progressLabel = document.getElementById("wizard-progress-label");
const progressHint = document.getElementById("wizard-progress-hint");
const stepDots = document.getElementById("step-dots");
const companionWrap = document.getElementById("onboard-companion-wrap")?.querySelector(".companion-wrap");
const webChatLink = document.getElementById("onboard-web-chat-link");
const focusPreviewTitle = document.getElementById("focus-preview-title");
const focusPreviewBody = document.getElementById("focus-preview-body");
const focusSummary = document.getElementById("focus-summary");
const tonePreviewLine = document.getElementById("tone-preview-line");
const toggleSummary = document.getElementById("toggle-summary");
const timezonePill = document.getElementById("timezone-pill");
const finalSummaryName = document.getElementById("final-summary-name");
const finalSummaryLocation = document.getElementById("final-summary-location");
const finalSummaryTimezone = document.getElementById("final-summary-timezone");
const finalSummaryStyle = document.getElementById("final-summary-style");
const timezoneInput = form?.querySelector('[name="timezone"]');
const telegramConnectBtn = document.getElementById("telegram-connect-btn");
const telegramTokenInput = document.getElementById("telegram-bot-token");
const telegramConnectStatus = document.getElementById("telegram-connect-status");

const SCENES = [
  { label: "Step 1 of 3", hint: "Choose what you want help with.", mood: "happy" },
  { label: "Step 2 of 3", hint: "Pick the tone that fits.", mood: "thinking" },
  { label: "Step 3 of 3", hint: "Make it feel local.", mood: "idle" },
];

const CARE_OPTIONS = {
  meds: {
    goal: "Stay on top of medications",
    reminder: "Medication reminders that feel personal",
    summary: "keep medication support steady and kind",
    previewTitle: "Medication support",
    previewBody: "A soft reminder, then a follow-up if the moment slips past.",
  },
  movement: {
    goal: "Stay consistent with movement",
    reminder: "Interesting nudges to get moving",
    summary: "help movement happen with less friction",
    previewTitle: "Movement support",
    previewBody: "A short nudge when energy drops and the day starts getting stuck.",
  },
  stress: {
    goal: "Feel calmer in stressful moments",
    reminder: "Grounding check-ins during stressful moments",
    summary: "show up with steadier support in stressful moments",
    previewTitle: "Stress support",
    previewBody: "Fewer spirals, more grounded check-ins when the day gets tense.",
  },
  sleep: {
    goal: "Protect sleep and recovery",
    reminder: "Wind-down and sleep protection prompts",
    summary: "protect evenings and recovery time",
    previewTitle: "Sleep support",
    previewBody: "We can keep evenings softer and give the day a calmer landing.",
  },
  routine: {
    goal: "Build a steadier daily rhythm",
    reminder: "Day-shaping check-ins that track how the day is going",
    summary: "keep the shape of your day more predictable",
    previewTitle: "Daily rhythm",
    previewBody: "Small touches across the day so things feel less scattered.",
  },
};

const TONE_OPTIONS = {
  gentle: {
    reminder: "Warm, gentle nudges",
    summary: "show up softly and with encouragement",
    preview: "Morning. Want one small thing to feel easier today?",
  },
  direct: {
    reminder: "Direct, motivating pushes",
    summary: "keep it clear and practical",
    preview: "Quick check: what needs doing first, and what’s getting skipped?",
  },
  calm: {
    reminder: "Calm grounding support",
    summary: "keep the tone steady and grounded",
    preview: "Let’s slow this down. One breath, then the next small step.",
  },
};

let currentCard = 0;
const totalCards = cardSteps.length;
const detectedTimezone = detectTimezone();

function parseLines(value) {
  return (value || "")
    .split("\n")
    .map((item) => item.trim())
    .filter(Boolean);
}

function selectedCareFocuses() {
  return [...form.querySelectorAll('input[name="care_focus"]:checked')].map((input) => input.value);
}

function selectedTone() {
  return form.querySelector('input[name="tone_style"]:checked')?.value || "gentle";
}

function typedName() {
  return form.querySelector('[name="full_name"]')?.value.trim() || "";
}

function typedLocation() {
  return form.querySelector('[name="location"]')?.value.trim() || "";
}

function typedTimezone() {
  return timezoneInput?.value.trim() || detectedTimezone;
}

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

function seedTimezoneField() {
  if (!timezoneInput || String(timezoneInput.value || "").trim()) {
    return;
  }
  timezoneInput.value = detectedTimezone;
}

function updateStepDots() {
  if (!stepDots) {
    return;
  }
  const dots = [...stepDots.querySelectorAll(".step-dot")];
  dots.forEach((dot, idx) => {
    dot.classList.toggle("is-done", idx < currentCard);
    dot.classList.toggle("is-active", idx === currentCard);
  });
}

function updateProgressCopy() {
  const scene = SCENES[currentCard];
  if (!scene) {
    return;
  }
  if (progressLabel) {
    progressLabel.textContent = scene.label;
  }
  if (progressHint) {
    progressHint.textContent = scene.hint;
  }
}

function updateCompanionMood() {
  if (!companionWrap) {
    return;
  }
  let mood = SCENES[currentCard]?.mood || "idle";
  const tone = selectedTone();
  if (currentCard === 1 && tone === "calm") {
    mood = "concerned";
  } else if (currentCard === 2) {
    mood = "celebrating";
  }
  companionWrap.setAttribute("data-state", mood);
}

function formatFocusLabel(key) {
  return CARE_OPTIONS[key]?.previewTitle?.toLowerCase() || "support";
}

function joinList(items) {
  if (!items.length) {
    return "";
  }
  if (items.length === 1) {
    return items[0];
  }
  if (items.length === 2) {
    return `${items[0]} and ${items[1]}`;
  }
  return `${items.slice(0, -1).join(", ")}, and ${items[items.length - 1]}`;
}

function updateFocusPreview() {
  const focuses = selectedCareFocuses();
  const primary = focuses[0] || "sleep";
  const meta = CARE_OPTIONS[primary] || CARE_OPTIONS.sleep;
  if (focusPreviewTitle) {
    focusPreviewTitle.textContent = meta.previewTitle;
  }
  if (focusPreviewBody) {
    focusPreviewBody.textContent = meta.previewBody;
  }
  if (focusSummary) {
    if (!focuses.length) {
      focusSummary.textContent = "Start with one thing that matters. We’ll refine the rest as we go.";
    } else {
      const labels = focuses.map((key) => formatFocusLabel(key));
      focusSummary.textContent = `We’ll begin around ${joinList(labels)} and keep the rest lightweight for now.`;
    }
  }
}

function updateTonePreview() {
  const tone = selectedTone();
  if (tonePreviewLine) {
    tonePreviewLine.textContent = TONE_OPTIONS[tone]?.preview || TONE_OPTIONS.gentle.preview;
  }
  if (toggleSummary) {
    const active = [];
    if (form.querySelector('[name="morning_check_in"]')?.checked) {
      active.push("morning hello");
    }
    if (form.querySelector('[name="weekly_summary"]')?.checked) {
      active.push("weekly reset");
    }
    toggleSummary.textContent = active.length
      ? `${joinList(active)} ${active.length === 1 ? "is" : "are"} on.`
      : "No recurring check-ins yet. You can still chat whenever you want.";
  }
}

function updateLocationPreview() {
  seedTimezoneField();
  const timezone = typedTimezone();
  const location = typedLocation();
  const name = typedName();
  const tone = selectedTone();
  const focuses = selectedCareFocuses();

  if (timezonePill) {
    timezonePill.textContent = timezone === detectedTimezone
      ? `Detected here: ${detectedTimezone}`
      : `Detected here: ${detectedTimezone}. Using: ${timezone}`;
  }
  if (finalSummaryName) {
    finalSummaryName.textContent = name
      ? `I’ll call you ${name}.`
      : "You’ll be greeted by name.";
  }
  if (finalSummaryLocation) {
    finalSummaryLocation.textContent = location
      ? `${location} is your anchor, and reminders will land in the right part of the day.`
      : "Timing will follow the day you set here.";
  }
  if (finalSummaryTimezone) {
    finalSummaryTimezone.textContent = `Timezone: ${timezone}. You can change it later if your schedule moves.`;
  }
  if (finalSummaryStyle) {
    const focusLabels = focuses.map((key) => formatFocusLabel(key));
    const focusLine = focusLabels.length
      ? `starting with ${joinList(focusLabels)}`
      : "starting with the basics";
    finalSummaryStyle.textContent = `I’ll show up ${TONE_OPTIONS[tone]?.summary || TONE_OPTIONS.gentle.summary}, ${focusLine}.`;
  }
}

function updatePreviews() {
  updateFocusPreview();
  updateTonePreview();
  updateLocationPreview();
}

function updateStep() {
  cardSteps.forEach((step, index) => {
    step.classList.toggle("active", index === currentCard);
  });
  backButton.style.visibility = currentCard === 0 ? "hidden" : "visible";
  const last = currentCard === totalCards - 1;
  nextButton.hidden = last;
  submitButton.hidden = !last;
  updateStepDots();
  updateProgressCopy();
  updateCompanionMood();
}

function availableChannelLinks() {
  return {
    telegram: form.dataset.telegramUrl || "",
    whatsapp: form.dataset.whatsappUrl || "",
  };
}

function channelLabel(name) {
  return name === "telegram" ? "Telegram" : "WhatsApp";
}

function renderCompletion(preferredChannel, links, userToken) {
  completionActions.innerHTML = "";
  const boundChannel = form.dataset.boundChannel || "";
  const ordered = [];
  const primaryChannel = boundChannel || preferredChannel;

  if (primaryChannel && links[primaryChannel]) {
    ordered.push(primaryChannel);
  }
  Object.keys(links).forEach((name) => {
    if (links[name] && !ordered.includes(name) && name === preferredChannel) {
      ordered.push(name);
    }
  });

  ordered.forEach((name) => {
    const anchor = document.createElement("a");
    anchor.href = links[name];
    anchor.target = "_blank";
    anchor.rel = "noopener";
    anchor.className = `channel-link${name === "whatsapp" ? " secondary-link" : ""}`;
    anchor.textContent = primaryChannel === name ? `Back to ${channelLabel(name)}` : `Also available in ${channelLabel(name)}`;
    completionActions.appendChild(anchor);
  });

  if (webChatLink && userToken) {
    webChatLink.href = `/chat/${encodeURIComponent(userToken)}`;
    webChatLink.hidden = false;
  }

  form.hidden = true;
  completionNode.hidden = false;
}

function collectPhase1Payload() {
  const boundChannel = (form.dataset.boundChannel || "").trim();
  const preferredChannel = boundChannel || "telegram";
  return {
    full_name: form.querySelector('[name="full_name"]')?.value.trim() || "",
    location: typedLocation(),
    email: "",
    phone: "",
    timezone: typedTimezone(),
    language: detectLanguage(),
    preferred_channel: preferredChannel,
    age_range: "not set",
    sex: "unknown",
    gender: "not set",
    height_cm: null,
    weight_kg: null,
    known_conditions: [],
    medications: [],
    allergies: [],
    wake_time: "",
    sleep_time: "",
    consents: ["privacy", "emergency", "coaching"],
  };
}

function collectPhase2Payload() {
  const focuses = selectedCareFocuses();
  const reminderPreferences = focuses
    .map((key) => CARE_OPTIONS[key]?.reminder)
    .filter(Boolean);
  reminderPreferences.push(TONE_OPTIONS[selectedTone()]?.reminder || TONE_OPTIONS.gentle.reminder);

  return {
    mood_interest: 0,
    mood_down: 0,
    activity_level: "not set",
    nutrition_quality: "not set",
    sleep_quality: "not set",
    stress_level: "not set",
    goals: focuses.map((key) => CARE_OPTIONS[key]?.goal).filter(Boolean),
    current_concerns: typedLocation()
      ? `Based in ${typedLocation()}. Wants support around ${joinList(focuses.map((key) => CARE_OPTIONS[key]?.previewTitle?.toLowerCase() || key)) || "general wellbeing"} with a ${selectedTone()} tone.`
      : `Wants support around ${joinList(focuses.map((key) => CARE_OPTIONS[key]?.previewTitle?.toLowerCase() || key)) || "general wellbeing"} with a ${selectedTone()} tone.`,
    reminder_preferences: reminderPreferences,
    medication_reminder_windows: [],
    morning_check_in: Boolean(form.querySelector('[name="morning_check_in"]')?.checked),
    weekly_summary: Boolean(form.querySelector('[name="weekly_summary"]')?.checked),
  };
}

function validateCurrentCard() {
  const step = cardSteps[currentCard];
  if (!step) {
    return true;
  }
  if (currentCard === 0) {
    if (!selectedCareFocuses().length) {
      statusNode.textContent = "Pick at least one area where your companion should help.";
      return false;
    }
  }
  const requiredInputs = step.querySelectorAll("[required]");
  for (const input of requiredInputs) {
    if (input.type === "checkbox") {
      continue;
    }
    if (!String(input.value || "").trim()) {
      input.focus();
      return false;
    }
  }
  return true;
}

function syncPreferredChannelWithInvite() {
  const boundChannel = form.dataset.boundChannel || "";
  if (!boundChannel) {
    return;
  }
  // Preferred channel is derived from invite context; no UI selection.
}

nextButton.addEventListener("click", () => {
  if (!validateCurrentCard()) {
    if (!statusNode.textContent) {
      statusNode.textContent = "Finish this step before continuing.";
    }
    return;
  }
  statusNode.textContent = "";
  currentCard = Math.min(currentCard + 1, totalCards - 1);
  updateStep();
});

backButton.addEventListener("click", () => {
  currentCard = Math.max(currentCard - 1, 0);
  updateStep();
  statusNode.textContent = "";
});

form.addEventListener("change", () => {
  updateCompanionMood();
  updatePreviews();
});

form.addEventListener("input", () => {
  updatePreviews();
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!validateCurrentCard()) {
    statusNode.textContent = "Please complete the final step first.";
    return;
  }
  statusNode.textContent = "Saving your setup…";
  const invite = form.dataset.invite;
  const payload = {
    phase1: collectPhase1Payload(),
    phase2: collectPhase2Payload(),
  };
  const response = await fetch(`/api/onboard/${invite}/submit`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Unable to submit onboarding." }));
    statusNode.textContent = error.detail || "Something went wrong. Please try again.";
    return;
  }
  const data = await response.json();
  const links = { ...availableChannelLinks(), ...(data.channelLinks || {}) };
  statusNode.textContent = "Your companion is ready.";
  renderCompletion(payload.phase1.preferred_channel, links, data.userToken || "");
});

async function connectTelegram() {
  if (!telegramConnectBtn || !telegramTokenInput) {
    return;
  }
  const invite = form?.dataset?.invite || "";
  const botToken = String(telegramTokenInput.value || "").trim();
  if (!invite) {
    if (telegramConnectStatus) telegramConnectStatus.textContent = "Missing invite token.";
    return;
  }
  if (!botToken) {
    if (telegramConnectStatus) telegramConnectStatus.textContent = "Paste your Telegram bot token first.";
    return;
  }
  if (telegramConnectStatus) telegramConnectStatus.textContent = "Validating Telegram token…";
  telegramConnectBtn.disabled = true;
  try {
    const response = await fetch(`/api/onboard/${encodeURIComponent(invite)}/channels/telegram`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ botToken }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = data.detail || "Unable to connect Telegram.";
      if (telegramConnectStatus) telegramConnectStatus.textContent = detail;
      telegramConnectBtn.disabled = false;
      return;
    }
    const link = (data.channelLinks || {}).telegram || "";
    if (link) {
      form.dataset.telegramUrl = link;
    }
    if (telegramConnectStatus) {
      const username = (data.telegram || {}).bot_username || "";
      telegramConnectStatus.textContent = username
        ? `Connected @${username}. The Telegram link is ready below.`
        : "Connected. The Telegram link is ready below.";
    }
  } catch (e) {
    if (telegramConnectStatus) telegramConnectStatus.textContent = e?.message || "Unable to connect Telegram.";
    telegramConnectBtn.disabled = false;
  }
}

if (telegramConnectBtn) {
  telegramConnectBtn.addEventListener("click", connectTelegram);
}

syncPreferredChannelWithInvite();
seedTimezoneField();
updateStep();
updatePreviews();
