"use strict";

const form = document.getElementById("signup-form");
const nameInput = document.getElementById("name");
const emailInput = document.getElementById("email");
const passwordInput = document.getElementById("password");
const timezoneInput = document.getElementById("timezone");
const submitBtn = document.getElementById("submit-btn");
const statusEl = document.getElementById("status");
const pwToggle = document.getElementById("pw-toggle");
const pwIconShow = document.getElementById("pw-icon-show");
const pwIconHide = document.getElementById("pw-icon-hide");

// Seed timezone from browser
function detectTimezone() {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  } catch (_) {
    return "UTC";
  }
}

if (timezoneInput && !timezoneInput.value) {
  timezoneInput.value = detectTimezone();
}

function setStatus(msg, type = "") {
  statusEl.textContent = msg;
  statusEl.className = "auth-status" + (type ? ` auth-status--${type}` : "");
}

pwToggle?.addEventListener("click", () => {
  const isPassword = passwordInput.type === "password";
  passwordInput.type = isPassword ? "text" : "password";
  pwIconShow.hidden = isPassword;
  pwIconHide.hidden = !isPassword;
  pwToggle.setAttribute("aria-label", isPassword ? "Hide password" : "Show password");
});

form.addEventListener("submit", async (e) => {
  e.preventDefault();

  const name = nameInput.value.trim();
  const email = emailInput.value.trim();
  const password = passwordInput.value;
  const timezone = timezoneInput.value.trim() || "UTC";

  if (!name) { setStatus("Please enter your name.", "error"); return; }
  if (!email) { setStatus("Please enter your email.", "error"); return; }
  if (password.length < 8) { setStatus("Password must be at least 8 characters.", "error"); return; }

  submitBtn.disabled = true;
  setStatus("Creating your account…");

  try {
    const res = await fetch("/api/auth/signup", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, email, password, timezone }),
    });

    const data = await res.json().catch(() => ({}));

    if (!res.ok) {
      const msg = data.detail || "Something went wrong.";
      setStatus(msg === "Email already registered" ? "That email is already registered. Try signing in." : msg, "error");
      submitBtn.disabled = false;
      return;
    }

    setStatus("Account created! Setting up your companion…", "success");
    window.location.href = "/account";
  } catch (err) {
    setStatus("Network error. Please try again.", "error");
    submitBtn.disabled = false;
  }
});
