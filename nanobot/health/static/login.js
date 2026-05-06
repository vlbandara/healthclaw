"use strict";

const form = document.getElementById("login-form");
const emailInput = document.getElementById("email");
const passwordInput = document.getElementById("password");
const submitBtn = document.getElementById("submit-btn");
const statusEl = document.getElementById("status");
const pwToggle = document.getElementById("pw-toggle");
const pwIconShow = document.getElementById("pw-icon-show");
const pwIconHide = document.getElementById("pw-icon-hide");

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
  const email = emailInput.value.trim();
  const password = passwordInput.value;

  if (!email || !password) {
    setStatus("Please enter your email and password.", "error");
    return;
  }

  submitBtn.disabled = true;
  setStatus("Signing in…");

  try {
    const res = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });

    const data = await res.json().catch(() => ({}));

    if (!res.ok) {
      setStatus(data.detail || "Invalid email or password.", "error");
      submitBtn.disabled = false;
      return;
    }

    setStatus("Signed in! Redirecting…", "success");
    // Redirect to account page (or wherever ?next points)
    const params = new URLSearchParams(window.location.search);
    window.location.href = params.get("next") || "/account";
  } catch (err) {
    setStatus("Network error. Please try again.", "error");
    submitBtn.disabled = false;
  }
});
