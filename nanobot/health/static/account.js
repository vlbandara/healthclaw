"use strict";

const HC = window.__HC || {};

// ── Logout ─────────────────────────────────────────────────────────────────
document.getElementById("logout-btn")?.addEventListener("click", async (e) => {
  e.preventDefault();
  await fetch("/api/auth/logout", { method: "POST" });
  window.location.href = "/login";
});

// ═══════════════════════════════════════════════════════════════════════════
// TELEGRAM LINKING  —  one-time deep link, no bot token entry needed
// ═══════════════════════════════════════════════════════════════════════════

const tgLinkBtn    = document.getElementById("tg-link-btn");
const tgLinkStatus = document.getElementById("tg-link-status");
const tgLinkResult = document.getElementById("tg-link-result");

let linkExpiryTimer = null;

function setTgStatus(msg, type = "") {
  if (!tgLinkStatus) return;
  tgLinkStatus.textContent = msg;
  tgLinkStatus.className = "section-status" + (type ? ` section-status--${type}` : "");
}

function showLinkResult(deepLink, botUsername, expiresInSeconds) {
  if (!tgLinkResult) return;

  clearInterval(linkExpiryTimer);
  let remaining = expiresInSeconds;

  tgLinkResult.hidden = false;
  tgLinkResult.innerHTML = `
    <div class="tg-ready-card" style="margin-top:var(--nh-space-md);">
      <div class="tg-ready-card__icon">🔗</div>
      <div class="tg-ready-card__body">
        <strong>Your link is ready</strong>
        <p>Click it to open Telegram. The bot will confirm once your account is linked.</p>
        <a class="tg-open-btn" href="${deepLink}" target="_blank" rel="noopener">
          Open @${botUsername} and link →
        </a>
        <p class="pairing-expires" id="link-expires-label" style="margin-top:8px;">
          Link expires in 15:00
        </p>
      </div>
    </div>`;

  const label = document.getElementById("link-expires-label");
  function tick() {
    if (!label) return;
    const m = Math.floor(remaining / 60);
    const s = remaining % 60;
    label.textContent = remaining > 0
      ? `Link expires in ${m}:${String(s).padStart(2, "0")}`
      : "Link expired — generate a new one.";
    if (remaining <= 0) clearInterval(linkExpiryTimer);
    remaining--;
  }
  tick();
  linkExpiryTimer = setInterval(tick, 1000);
}

tgLinkBtn?.addEventListener("click", async () => {
  tgLinkBtn.disabled = true;
  setTgStatus("Generating link…");

  try {
    const res  = await fetch("/api/account/telegram/generate-link", { method: "POST" });
    const data = await res.json().catch(() => ({}));

    if (!res.ok) {
      setTgStatus(data.detail || "Couldn't generate link.", "error");
      tgLinkBtn.disabled = false;
      return;
    }

    setTgStatus("");
    tgLinkBtn.textContent = "↻ Generate new link";
    tgLinkBtn.disabled = false;
    showLinkResult(data.deep_link, data.bot_username, data.expires_in_seconds);

  } catch {
    setTgStatus("Network error. Please try again.", "error");
    tgLinkBtn.disabled = false;
  }
});

// ═══════════════════════════════════════════════════════════════════════════
// PREFERENCES WIZARD  (mirrors onboard.js)
// ═══════════════════════════════════════════════════════════════════════════

const prefsForm       = document.getElementById("prefs-form");
const cardSteps       = prefsForm ? [...prefsForm.querySelectorAll(".card-step")] : [];
const nextButton      = document.getElementById("next");
const backButton      = document.getElementById("back");
const submitPrefsBtn  = document.getElementById("submit-prefs");
const prefsStatus     = document.getElementById("prefs-status");
const prefsCompletion = document.getElementById("prefs-completion");
const progressLabel   = document.getElementById("wizard-progress-label");
const progressHint    = document.getElementById("wizard-progress-hint");
const stepDots        = document.getElementById("step-dots");
const companionWrap   = document.getElementById("onboard-companion-wrap")?.querySelector(".companion-wrap");

const SCENES = [
  { label: "Step 1 of 3", hint: "Choose what you want help with.", mood: "happy" },
  { label: "Step 2 of 3", hint: "Pick the tone that fits.",        mood: "thinking" },
  { label: "Step 3 of 3", hint: "Make it feel local.",            mood: "idle" },
];

const CARE = {
  meds:     { goal: "Stay on top of medications",        reminder: "Medication reminders that feel personal",         previewTitle: "Medication support", previewBody: "A soft reminder, then a follow-up if the moment slips past." },
  movement: { goal: "Stay consistent with movement",     reminder: "Nudges to get moving",                            previewTitle: "Movement support",   previewBody: "A short nudge when energy drops and the day starts getting stuck." },
  stress:   { goal: "Feel calmer in stressful moments",  reminder: "Grounding check-ins during stressful moments",    previewTitle: "Stress support",     previewBody: "Fewer spirals, more grounded check-ins when the day gets tense." },
  sleep:    { goal: "Protect sleep and recovery",        reminder: "Wind-down and sleep protection prompts",           previewTitle: "Sleep support",      previewBody: "We can keep evenings softer and give the day a calmer landing." },
  routine:  { goal: "Build a steadier daily rhythm",     reminder: "Day-shaping check-ins",                           previewTitle: "Daily rhythm",       previewBody: "Small touches across the day so things feel less scattered." },
};

const TONE = {
  gentle: { reminder: "Warm, gentle nudges",      summary: "show up softly and with encouragement", preview: "Morning. Want one small thing to feel easier today?" },
  direct: { reminder: "Direct, motivating pushes", summary: "keep it clear and practical",           preview: "Quick check: what needs doing first, and what's getting skipped?" },
  calm:   { reminder: "Calm grounding support",   summary: "keep the tone steady and grounded",      preview: "Let's slow this down. One breath, then the next small step." },
};

let currentCard  = 0;
const totalCards = cardSteps.length;

const detectedTZ = (() => { try { return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC"; } catch { return "UTC"; } })();

const q  = (sel) => prefsForm?.querySelector(sel);
const focuses = () => [...(prefsForm?.querySelectorAll('input[name="care_focus"]:checked') || [])].map(i => i.value);
const tone    = () => q('input[name="tone_style"]:checked')?.value || "gentle";
const name_   = () => q('[name="full_name"]')?.value.trim() || "";
const loc     = () => q('[name="location"]')?.value.trim()  || "";
const tz      = () => q('[name="timezone"]')?.value.trim()  || detectedTZ;

function joinList(items) {
  if (!items.length) return "";
  if (items.length === 1) return items[0];
  if (items.length === 2) return `${items[0]} and ${items[1]}`;
  return `${items.slice(0, -1).join(", ")}, and ${items[items.length - 1]}`;
}

function setPrefsStatus(msg, type = "") {
  if (!prefsStatus) return;
  prefsStatus.textContent = msg;
  prefsStatus.className   = "status" + (type ? ` status--${type}` : "");
}

function updateDots() {
  [...(stepDots?.querySelectorAll(".step-dot") || [])].forEach((d, i) => {
    d.classList.toggle("is-done",   i < currentCard);
    d.classList.toggle("is-active", i === currentCard);
  });
}

function updatePreviews() {
  const fs  = focuses();
  const pri = fs[0] || "sleep";
  const cm  = CARE[pri] || CARE.sleep;
  const el  = (id) => document.getElementById(id);

  el("focus-preview-title")?.textContent !== undefined && (el("focus-preview-title").textContent = cm.previewTitle);
  el("focus-preview-body") && (el("focus-preview-body").textContent = cm.previewBody);
  el("focus-summary") && (el("focus-summary").textContent = fs.length
    ? `We'll start with ${joinList(fs.map(k => (CARE[k]?.previewTitle || k).toLowerCase()))} and keep the rest lightweight.`
    : "Start with one thing that matters.");

  el("tone-preview-line") && (el("tone-preview-line").textContent = TONE[tone()]?.preview || TONE.gentle.preview);

  const active = [];
  if (q('[name="morning_check_in"]')?.checked) active.push("morning hello");
  if (q('[name="weekly_summary"]')?.checked)   active.push("weekly reset");
  el("toggle-summary") && (el("toggle-summary").textContent = active.length
    ? `${joinList(active)} ${active.length === 1 ? "is" : "are"} on.`
    : "No recurring check-ins yet.");

  const curTZ = tz();
  el("timezone-pill") && (el("timezone-pill").textContent = curTZ === detectedTZ
    ? `Detected here: ${detectedTZ}`
    : `Detected: ${detectedTZ} · Using: ${curTZ}`);
  el("final-summary-name")     && (el("final-summary-name").textContent     = name_() ? `I'll call you ${name_()}.` : "You'll be greeted by name.");
  el("final-summary-location") && (el("final-summary-location").textContent = loc()   ? `${loc()} is your anchor.` : "Timing follows your local day.");
  el("final-summary-timezone") && (el("final-summary-timezone").textContent = `Timezone: ${curTZ}.`);
  el("final-summary-style")    && (el("final-summary-style").textContent    =
    `I'll ${TONE[tone()]?.summary || "show up softly"}, starting with ${joinList(focuses().map(k => (CARE[k]?.previewTitle || k).toLowerCase())) || "the basics"}.`);
}

function updateStep() {
  cardSteps.forEach((s, i) => s.classList.toggle("active", i === currentCard));
  if (backButton) backButton.style.visibility = currentCard === 0 ? "hidden" : "visible";
  const last = currentCard === totalCards - 1;
  if (nextButton)     nextButton.hidden = last;
  if (submitPrefsBtn) submitPrefsBtn.hidden = !last;

  const scene = SCENES[currentCard];
  if (progressLabel) progressLabel.textContent = scene?.label || "";
  if (progressHint)  progressHint.textContent  = scene?.hint  || "";
  if (companionWrap) {
    let mood = scene?.mood || "idle";
    if (currentCard === 1 && tone() === "calm") mood = "concerned";
    if (currentCard === 2) mood = "celebrating";
    companionWrap.setAttribute("data-state", mood);
  }
  updateDots();
  updatePreviews();
}

function validateCard() {
  if (currentCard === 0 && !focuses().length) {
    setPrefsStatus("Pick at least one area where your companion should help.");
    return false;
  }
  return true;
}

nextButton?.addEventListener("click", () => {
  if (!validateCard()) return;
  setPrefsStatus("");
  currentCard = Math.min(currentCard + 1, totalCards - 1);
  updateStep();
});

backButton?.addEventListener("click", () => {
  currentCard = Math.max(currentCard - 1, 0);
  updateStep();
  setPrefsStatus("");
});

prefsForm?.addEventListener("change", updateStep);
prefsForm?.addEventListener("input",  updatePreviews);

prefsForm?.addEventListener("submit", async (e) => {
  e.preventDefault();
  if (!validateCard()) { setPrefsStatus("Please complete all fields first."); return; }

  if (submitPrefsBtn) submitPrefsBtn.disabled = true;
  setPrefsStatus("Saving…");

  const fs = focuses();
  const t  = tone();
  const payload = {
    phase1: {
      full_name: name_(), location: loc(), timezone: tz(),
      language: (navigator.language || "en").split("-")[0],
      preferred_channel: "telegram",
      consents: ["privacy", "emergency", "coaching"],
    },
    phase2: {
      goals:                fs.map(k => CARE[k]?.goal).filter(Boolean),
      reminder_preferences: [...fs.map(k => CARE[k]?.reminder).filter(Boolean), TONE[t]?.reminder || TONE.gentle.reminder],
      morning_check_in:     Boolean(q('[name="morning_check_in"]')?.checked),
      weekly_summary:       Boolean(q('[name="weekly_summary"]')?.checked),
      current_concerns:     fs.length
        ? `Wants help with ${joinList(fs.map(k => (CARE[k]?.previewTitle || k).toLowerCase()))} in a ${t} tone.`
        : "",
    },
  };

  try {
    const res  = await fetch("/api/account/profile", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) { setPrefsStatus(data.detail || "Couldn't save. Try again.", "error"); if (submitPrefsBtn) submitPrefsBtn.disabled = false; return; }
    setPrefsStatus("");
    if (prefsForm) prefsForm.hidden = true;
    if (prefsCompletion) prefsCompletion.hidden = false;
  } catch {
    setPrefsStatus("Network error. Please try again.", "error");
    if (submitPrefsBtn) submitPrefsBtn.disabled = false;
  }
});

// Seed timezone field on load
const tzField = q('[name="timezone"]');
if (tzField && !tzField.value) tzField.value = detectedTZ;

updateStep();
