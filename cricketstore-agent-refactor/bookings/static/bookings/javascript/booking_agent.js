(function () {
  const chatForm = document.getElementById("chatForm");
  const chatInput = document.getElementById("chatInput");
  const chatMessages = document.getElementById("chatMessages");
  const quickReplies = document.getElementById("quickReplies");
  const agentContent = document.getElementById("agentContent");
  const modeLabel = document.getElementById("modeLabel");
  const sendBtn = document.getElementById("sendBtn");
  const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content || "";

  let currentMode = null;
  let pendingRequiredFields = [];
  let lastQuery = "";
  let redirecting = false;

  function addUserMessage(text) {
    const msg = document.createElement("div");
    msg.className = "message user";
    msg.textContent = text;
    chatMessages.appendChild(msg);
    chatMessages.scrollTop = chatMessages.scrollHeight;
  }

  function addBotMessage(text) {
    const msg = document.createElement("div");
    msg.className = "message bot";
    msg.textContent = text;
    chatMessages.appendChild(msg);
    chatMessages.scrollTop = chatMessages.scrollHeight;
  }

  function clearQuickReplies() {
    quickReplies.innerHTML = "";
  }

  function showQuickReplies(options = []) {
    clearQuickReplies();

    options.forEach((option) => {
      const btn = document.createElement("button");
      btn.className = "quick-reply";
      btn.textContent = option.text;

      btn.onclick = () => {
        if (option.modeSelection) {
          handleModeSelection(option.text);
          return;
        }
        if (option.action) {
          addUserMessage(option.text);
          sendQuery("", { action: option.action });
          return;
        }

        sendQuery(option.text || "", option.id ? { booking_id: option.id } : {});
      };

      quickReplies.appendChild(btn);
    });
  }

  function enableChat() {
    chatInput.disabled = false;
    sendBtn.disabled = false;
    chatInput.focus();
  }

  function showModeSelection() {
    addBotMessage("What would you like to do today?");

    showQuickReplies([
      { text: "Normal Booking", modeSelection: true },
      { text: "Tournament Booking", modeSelection: true },
      { text: "Cancel Booking", modeSelection: true },
      { text: "Reschedule Booking", modeSelection: true },
    ]);
  }

  function handleModeSelection(text) {
    const modeMap = {
      "Normal Booking": "normal_booking",
      "Tournament Booking": "tournament",
      "Cancel Booking": "cancellation",
      "Reschedule Booking": "reschedule",
    };

    currentMode = modeMap[text];

    addUserMessage(text);
    clearQuickReplies();

    modeLabel.textContent = `Mode: ${text}`;
    addBotMessage(`${text} selected.`);
    addBotMessage("Tell me your requirement.");

    enableChat();
  }

  async function sendQuery(query = "", extraPayload = {}) {
    if (!currentMode) return;

    if (query) {
      lastQuery = query;
      addUserMessage(query);
      chatInput.value = "";
    }

    try {
      const response = await fetch(CHATBOT_URL, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Requested-With": "XMLHttpRequest",
          "X-CSRFToken": csrfToken,
        },
        body: JSON.stringify({
          mode: currentMode,
          query: query,
          required_fields: pendingRequiredFields,
          ...extraPayload,
        }),
      });

      const data = await response.json();

      if (data.html) {
        agentContent.innerHTML = data.html;
      }

      if (data.redirect_url) {
        if (redirecting) return;

        redirecting = true;
        addBotMessage("Redirecting to checkout page...");
        chatInput.disabled = true;
        sendBtn.disabled = true;
        clearQuickReplies();

        window.location.replace(data.redirect_url);
        return;
      }

      if (data.message) {
        addBotMessage(data.message);
      }

      if (data.show_confirm_button) {
        pendingRequiredFields = [];

        showQuickReplies(data.options || [
          { text: "Yes", action: "confirm_booking" },
          { text: "No", action: "cancel_confirm_booking" },
        ]);

        enableChat();
        return;
      }

      if (Array.isArray(data.required_fields)) {
        pendingRequiredFields = data.required_fields;
      } else {
        pendingRequiredFields = [];
      }

      if (data.options) {
        showQuickReplies(data.options);
      } else {
        clearQuickReplies();
        enableChat();
      }
    } catch (err) {
      console.error(err);
      addBotMessage("Something went wrong. Please try again.");
    }
  }

  window.resendLastQuery = function () {
    sendQuery("");
  };

  chatForm.addEventListener("submit", (e) => {
    e.preventDefault();
    sendQuery(chatInput.value.trim());
  });

  chatInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      chatForm.dispatchEvent(new Event("submit"));
    }
  });

  addBotMessage("Hi! I'm your Booking Agent 🤖");
  showModeSelection();
})();