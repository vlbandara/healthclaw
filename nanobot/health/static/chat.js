const app = document.getElementById("chat-app");
const token = app?.dataset.token || "";
const thread = document.getElementById("chat-thread");
const input = document.getElementById("chat-input");
const sendBtn = document.getElementById("chat-send");
const typing = document.getElementById("chat-typing");
const companionSlot = document.getElementById("chat-companion-slot");
const stageLabel = document.getElementById("chat-stage-label");
const insightToggle = document.getElementById("insight-toggle");
const insightPanel = document.getElementById("insight-panel");
const insightScore = document.getElementById("insight-score");
const insightStage = document.getElementById("insight-stage");
const insightTopics = document.getElementById("insight-topics");

const stageLabels = {
  onboarding: "Learning the basics",
  early: "Early days together",
  settling: "Finding our rhythm",
  established: "We know each other",
  deep: "Deep groove",
};

function setCompanionState(state) {
  const el = companionSlot?.querySelector(".companion-wrap");
  if (el) {
    el.setAttribute("data-state", state);
  }
}

function appendBubble(role, text) {
  const wrap = document.createElement("div");
  wrap.className = `chat-bubble chat-bubble--${role}`;
  if (role === "assistant") {
    const inner = document.createElement("div");
    inner.className = "chat-bubble__text";
    inner.textContent = text;
    wrap.appendChild(inner);
  } else {
    wrap.textContent = text;
  }
  thread.appendChild(wrap);
  thread.scrollTop = thread.scrollHeight;
}

async function loadStatus() {
  try {
    const res = await fetch(`/api/chat/${encodeURIComponent(token)}/companion-status`);
    if (!res.ok) {
      return;
    }
    const data = await res.json();
    const st = data.companionState || "idle";
    setCompanionState(st);
    const slug = (data.stage || "early").toLowerCase();
    if (stageLabel) {
      stageLabel.textContent = stageLabels[slug] || "Getting to know you";
    }
    if (insightScore) {
      insightScore.textContent = `${data.knowledgeScore ?? 0}%`;
    }
    if (insightStage) {
      insightStage.textContent = slug;
    }
    if (insightTopics && Array.isArray(data.topicsLearned)) {
      insightTopics.textContent =
        data.topicsLearned.length > 0
          ? `Topics: ${data.topicsLearned.join(", ")}.`
          : "Still collecting patterns worth naming.";
    }
  } catch {
    /* ignore */
  }
}

async function sendMessage() {
  const text = (input?.value || "").trim();
  if (!text || !token) {
    return;
  }
  input.value = "";
  appendBubble("user", text);
  sendBtn.disabled = true;
  setCompanionState("thinking");
  typing.hidden = false;

  const assistantEl = document.createElement("div");
  assistantEl.className = "chat-bubble chat-bubble--assistant";
  const inner = document.createElement("div");
  inner.className = "chat-bubble__text";
  assistantEl.appendChild(inner);
  thread.appendChild(assistantEl);

  let assembled = "";

  try {
    const res = await fetch(`/api/chat/${encodeURIComponent(token)}/message`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text }),
    });
    if (!res.ok || !res.body) {
      inner.textContent = "Couldn’t reach your companion. Try Telegram or try again.";
      return;
    }
    const reader = res.body.getReader();
    const dec = new TextDecoder();
    let buffer = "";
    for (;;) {
      const { done, value } = await reader.read();
      if (done) {
        break;
      }
      buffer += dec.decode(value, { stream: true });
      const parts = buffer.split("\n\n");
      buffer = parts.pop() || "";
      for (const block of parts) {
        if (!block.startsWith("data: ")) {
          continue;
        }
        let payload;
        try {
          payload = JSON.parse(block.slice(6));
        } catch {
          continue;
        }
        if (payload.type === "token" && payload.text) {
          assembled += payload.text;
          inner.textContent = assembled;
          thread.scrollTop = thread.scrollHeight;
        } else if (payload.type === "complete") {
          assembled = payload.text || assembled;
          inner.textContent = assembled;
        } else if (payload.type === "error") {
          inner.textContent = payload.message || "Something went wrong.";
        }
      }
    }
  } catch {
    inner.textContent = "Network error.";
  } finally {
    typing.hidden = true;
    sendBtn.disabled = false;
    setCompanionState("idle");
    thread.scrollTop = thread.scrollHeight;
    loadStatus();
  }
}

if (insightToggle && insightPanel) {
  insightToggle.addEventListener("click", () => {
    const open = insightPanel.hidden;
    insightPanel.hidden = !open;
    insightToggle.setAttribute("aria-expanded", open ? "true" : "false");
  });
}

sendBtn?.addEventListener("click", sendMessage);
input?.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});

loadStatus();
