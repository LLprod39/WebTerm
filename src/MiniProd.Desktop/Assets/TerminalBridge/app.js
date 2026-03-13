"use strict";

const state = {
  connected: false,
  serverName: "No server selected",
  serverAddress: "Standalone workspace",
  servers: [],
  aiConfigured: false,
  pendingCommand: "",
  mode: "auto",
  history: [],
  historyIndex: -1,
  aiCollapsed: true,
  aiWidth: 390,
  busyAi: false,
};

const ui = {
  app: document.getElementById("app"),
  sessionTab: document.getElementById("sessionTab"),
  tabName: document.getElementById("tabName"),
  tabSub: document.getElementById("tabSub"),
  serverSelect: document.getElementById("serverSelect"),
  connectButton: document.getElementById("connectButton"),
  disconnectButton: document.getElementById("disconnectButton"),
  toggleAiButton: document.getElementById("toggleAiButton"),
  headerTitle: document.getElementById("headerTitle"),
  headerSub: document.getElementById("headerSub"),
  sessionChip: document.getElementById("sessionChip"),
  connectionChip: document.getElementById("connectionChip"),
  clearButton: document.getElementById("clearButton"),
  interruptButton: document.getElementById("interruptButton"),
  terminal: document.getElementById("terminal"),
  commandInput: document.getElementById("commandInput"),
  sendCommand: document.getElementById("sendCommand"),
  footerStatus: document.getElementById("footerStatus"),
  drawer: document.getElementById("drawer"),
  resizeHandle: document.getElementById("resizeHandle"),
  closeAiButton: document.getElementById("closeAiButton"),
  stopAi: document.getElementById("stopAi"),
  aiState: document.getElementById("aiState"),
  aiMessages: document.getElementById("aiMessages"),
  aiEmpty: document.getElementById("aiEmpty"),
  aiPrompt: document.getElementById("aiPrompt"),
  askAi: document.getElementById("askAi"),
  aiHint: document.getElementById("aiHint"),
  modeButtons: [...document.querySelectorAll(".mode")],
  quickActions: [...document.querySelectorAll(".quick-action")],
};

const post = (message) => window.chrome?.webview?.postMessage(message);

const storage = {
  readNumber(key, fallbackValue) {
    try {
      const parsed = parseInt(localStorage.getItem(key) ?? "", 10);
      return Number.isFinite(parsed) ? parsed : fallbackValue;
    } catch {
      return fallbackValue;
    }
  },
  readBool(key, fallbackValue) {
    try {
      const value = localStorage.getItem(key);
      return value === null ? fallbackValue : value === "1";
    } catch {
      return fallbackValue;
    }
  },
  save(key, value) {
    try {
      localStorage.setItem(key, value);
    } catch {
      // Ignore local storage errors in restricted contexts.
    }
  },
};

state.aiWidth = Math.max(320, Math.min(560, storage.readNumber("ai-width", 390)));
state.aiCollapsed = storage.readBool("ai-collapsed", true);

const timestamp = () => new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

const escapeHtml = (text) =>
  text
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");

const ansiColorByCode = {
  "30": "c-black",
  "31": "c-red",
  "32": "c-green",
  "33": "c-yellow",
  "34": "c-blue",
  "35": "c-magenta",
  "36": "c-cyan",
  "37": "c-white",
  "90": "c-br",
  "91": "c-red",
  "92": "c-green",
  "93": "c-yellow",
  "94": "c-blue",
  "95": "c-magenta",
  "96": "c-cyan",
  "97": "c-white",
};

function toAnsiHtml(text) {
  let html = "";
  let activeClass = "";
  let bold = false;
  const parts = text.split(/\x1b\[([0-9;]*)m/);

  for (let index = 0; index < parts.length; index += 1) {
    if (index % 2 === 0) {
      const escaped = escapeHtml(parts[index]);
      if (!escaped) {
        continue;
      }

      if (activeClass || bold) {
        const className = [activeClass, bold ? "bold" : ""].filter(Boolean).join(" ");
        html += `<span class="${className}">${escaped}</span>`;
      } else {
        html += escaped;
      }

      continue;
    }

    const codes = parts[index].split(";");
    for (const code of codes) {
      if (!code || code === "0") {
        activeClass = "";
        bold = false;
      } else if (code === "1") {
        bold = true;
      } else if (ansiColorByCode[code]) {
        activeClass = ansiColorByCode[code];
      }
    }
  }

  return html;
}

function appendTerminal(text) {
  ui.terminal.insertAdjacentHTML("beforeend", toAnsiHtml(text));
  ui.terminal.scrollTop = ui.terminal.scrollHeight;
}

function clearTerminal() {
  ui.terminal.innerHTML = "";
}

function setTheme(themeName) {
  document.body.classList.toggle("light", (themeName ?? "").toLowerCase() === "light");
}

function syncConnectionButtons() {
  const hasServers = state.servers.length > 0;
  ui.connectButton.disabled = state.connected;
  ui.disconnectButton.disabled = !state.connected;
  ui.serverSelect.disabled = !hasServers;
}

function applyDrawerState() {
  ui.app.classList.toggle("drawer-open", !state.aiCollapsed);
  document.documentElement.style.setProperty("--drawer-width", `${state.aiWidth}px`);
  ui.toggleAiButton.textContent = state.aiCollapsed ? "AI" : "Hide AI";
}

function setConnected(connected, labelText) {
  state.connected = connected;
  ui.sessionTab.classList.toggle("connected", connected);
  ui.connectionChip.classList.toggle("is-success", connected);
  ui.connectionChip.textContent = labelText || (connected ? "connected" : "disconnected");
  ui.footerStatus.textContent = connected ? "Connected" : "Disconnected";
  syncConnectionButtons();
}

function setMode(mode) {
  state.mode = mode;
  for (const button of ui.modeButtons) {
    button.classList.toggle("active", button.dataset.mode === mode);
  }
}

function setAiBusy(busy) {
  state.busyAi = busy;
  ui.askAi.disabled = busy || !state.aiConfigured;
  ui.stopAi.disabled = !busy;
  ui.aiState.textContent = busy
    ? "Analyzing terminal transcript..."
    : state.aiConfigured
      ? "Ready"
      : "Configure AI provider in settings";
}

function syncAiPromptHeight() {
  ui.aiPrompt.style.height = "70px";
  ui.aiPrompt.style.height = `${Math.min(ui.aiPrompt.scrollHeight, 190)}px`;
}

function hideEmptyAiState() {
  ui.aiEmpty.classList.add("hidden");
}

function removeThinkingMessage() {
  document.getElementById("thinkingMessage")?.remove();
}

function addUserMessage(text) {
  hideEmptyAiState();
  const message = document.createElement("div");
  message.className = "message";
  message.innerHTML =
    `<div class="message-row">
       <span class="avatar user">U</span>
       <span>You</span>
       <span class="stamp">${timestamp()}</span>
     </div>
     <div class="bubble user">${escapeHtml(text)}</div>`;
  ui.aiMessages.appendChild(message);
  ui.aiMessages.scrollTop = ui.aiMessages.scrollHeight;
}

function showThinkingMessage() {
  hideEmptyAiState();
  removeThinkingMessage();
  const message = document.createElement("div");
  message.id = "thinkingMessage";
  message.className = "message";
  message.innerHTML =
    `<div class="message-row">
       <span class="avatar ai">AI</span>
       <span>Assistant</span>
     </div>
     <div class="bubble">
       <div class="thinking"><span></span><span></span><span></span></div>
     </div>`;
  ui.aiMessages.appendChild(message);
  ui.aiMessages.scrollTop = ui.aiMessages.scrollHeight;
}

function bindAssistantActionButtons(container, suggestedCommand) {
  container.querySelector("[data-run]")?.addEventListener("click", () => {
    if (state.pendingCommand) {
      post({ type: "run-ai-command", command: state.pendingCommand });
    }
  });

  container.querySelector("[data-copy]")?.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(suggestedCommand);
    } catch {
      // Clipboard can be blocked in some WebView contexts.
    }
  });
}

function addAssistantMessage(answer, suggestedCommand, risk) {
  removeThinkingMessage();
  hideEmptyAiState();
  state.pendingCommand = suggestedCommand || "";

  const commandSection = suggestedCommand
    ? `<div class="assistant-section">
         <div class="assistant-label">Suggested command</div>
         <div class="assistant-command">${escapeHtml(suggestedCommand)}</div>
         ${risk ? `<div class="assistant-risk">${escapeHtml(risk)}</div>` : ""}
         <div class="inline-actions">
           <button class="button button-primary" data-run type="button">Run</button>
           <button class="button" data-copy type="button">Copy</button>
         </div>
       </div>`
    : "";

  const message = document.createElement("div");
  message.className = "message";
  message.innerHTML =
    `<div class="message-row">
       <span class="avatar ai">AI</span>
       <span>Assistant</span>
       <span class="stamp">${timestamp()}</span>
     </div>
     <div class="bubble">${escapeHtml(answer)}${commandSection}</div>`;
  ui.aiMessages.appendChild(message);

  if (suggestedCommand) {
    bindAssistantActionButtons(message, suggestedCommand);
  }

  ui.aiMessages.scrollTop = ui.aiMessages.scrollHeight;
}

function renderServers(selectedServerId) {
  ui.serverSelect.innerHTML = "";
  if (!state.servers.length) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "No saved servers";
    ui.serverSelect.appendChild(option);
    syncConnectionButtons();
    return;
  }

  for (const server of state.servers) {
    const option = document.createElement("option");
    option.value = String(server.id);
    option.textContent = `${server.name} · ${server.address}`;
    if (server.id === selectedServerId) {
      option.selected = true;
    }
    ui.serverSelect.appendChild(option);
  }

  if (!ui.serverSelect.value) {
    ui.serverSelect.value = String(selectedServerId || state.servers[0].id);
  }

  syncConnectionButtons();
}

function pushHistory(command) {
  if (!command) {
    return;
  }

  const last = state.history[state.history.length - 1];
  if (last !== command) {
    state.history.push(command);
  }
  state.historyIndex = state.history.length;
}

function moveHistory(step) {
  if (state.history.length === 0) {
    return;
  }

  state.historyIndex = Math.max(0, Math.min(state.history.length, state.historyIndex + step));
  if (state.historyIndex === state.history.length) {
    ui.commandInput.value = "";
    return;
  }

  ui.commandInput.value = state.history[state.historyIndex] || "";
  ui.commandInput.setSelectionRange(ui.commandInput.value.length, ui.commandInput.value.length);
}

function sendCommand() {
  const text = ui.commandInput.value.trim();
  if (!text) {
    return;
  }

  pushHistory(text);
  post({ type: "send-input", text });
  ui.commandInput.value = "";
}

function sendAiRequest() {
  const prompt = ui.aiPrompt.value.trim();
  if (!prompt) {
    return;
  }

  if (!state.aiConfigured) {
    addAssistantMessage("Configure AI provider in settings before using the assistant.", "", "");
    return;
  }

  if (state.aiCollapsed) {
    state.aiCollapsed = false;
    storage.save("ai-collapsed", "0");
    applyDrawerState();
  }

  addUserMessage(prompt);
  showThinkingMessage();
  setAiBusy(true);
  post({ type: "ask-ai", prompt, mode: state.mode });
  ui.aiPrompt.value = "";
  syncAiPromptHeight();
}

function updateFromBootstrap(data) {
  state.serverName = data.serverName || "No server selected";
  state.serverAddress = data.serverAddress || "Standalone workspace";
  state.servers = Array.isArray(data.servers) ? data.servers : [];
  state.aiConfigured = !!data.aiConfigured;

  renderServers(data.serverId || 0);
  ui.tabName.textContent = state.serverName;
  ui.tabSub.textContent = state.serverAddress;
  ui.headerTitle.textContent = state.serverName || "MiniProd Terminal";
  ui.headerSub.textContent = state.serverAddress;
  ui.sessionChip.textContent = data.serverId ? `#${data.serverId}` : "bridge";
  ui.aiHint.textContent = state.aiConfigured ? "Ctrl+Enter to send" : "Configure AI in settings";

  setConnected(data.sessionState === "connected", data.sessionState || "disconnected");
  setTheme(data.theme || "Dark");
  setAiBusy(false);
}

function setupDrawerResizing() {
  let dragging = false;
  let startX = 0;
  let startWidth = 0;

  ui.resizeHandle.addEventListener("mousedown", (event) => {
    if (state.aiCollapsed) {
      return;
    }

    dragging = true;
    startX = event.clientX;
    startWidth = state.aiWidth;
    ui.resizeHandle.classList.add("dragging");
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  });

  document.addEventListener("mousemove", (event) => {
    if (!dragging) {
      return;
    }

    const delta = startX - event.clientX;
    state.aiWidth = Math.max(320, Math.min(Math.floor(window.innerWidth * 0.52), startWidth + delta));
    applyDrawerState();
  });

  document.addEventListener("mouseup", () => {
    if (!dragging) {
      return;
    }

    dragging = false;
    storage.save("ai-width", String(Math.round(state.aiWidth)));
    ui.resizeHandle.classList.remove("dragging");
    document.body.style.cursor = "";
    document.body.style.userSelect = "";
  });
}

function setupEvents() {
  ui.serverSelect.addEventListener("change", () => {
    const serverId = parseInt(ui.serverSelect.value || "", 10);
    if (Number.isFinite(serverId)) {
      post({ type: "select-server", serverId });
    }
  });

  ui.connectButton.addEventListener("click", () => post({ type: "connect" }));
  ui.disconnectButton.addEventListener("click", () => post({ type: "disconnect" }));

  ui.toggleAiButton.addEventListener("click", () => {
    state.aiCollapsed = !state.aiCollapsed;
    storage.save("ai-collapsed", state.aiCollapsed ? "1" : "0");
    applyDrawerState();
  });

  ui.closeAiButton.addEventListener("click", () => {
    state.aiCollapsed = true;
    storage.save("ai-collapsed", "1");
    applyDrawerState();
  });

  ui.clearButton.addEventListener("click", () => {
    clearTerminal();
    appendTerminal("Terminal cleared.\n");
  });

  ui.interruptButton.addEventListener("click", () => post({ type: "interrupt" }));

  ui.sendCommand.addEventListener("click", sendCommand);
  ui.commandInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      sendCommand();
      return;
    }

    if (event.key === "ArrowUp") {
      event.preventDefault();
      moveHistory(-1);
      return;
    }

    if (event.key === "ArrowDown") {
      event.preventDefault();
      moveHistory(1);
    }
  });

  ui.askAi.addEventListener("click", sendAiRequest);
  ui.aiPrompt.addEventListener("input", syncAiPromptHeight);
  ui.aiPrompt.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && event.ctrlKey) {
      event.preventDefault();
      sendAiRequest();
    }
  });

  ui.stopAi.addEventListener("click", () => {
    removeThinkingMessage();
    setAiBusy(false);
  });

  for (const button of ui.modeButtons) {
    button.addEventListener("click", () => setMode(button.dataset.mode || "auto"));
  }

  for (const action of ui.quickActions) {
    action.addEventListener("click", () => {
      ui.aiPrompt.value = action.dataset.p || "";
      syncAiPromptHeight();
      sendAiRequest();
    });
  }

  document.addEventListener("keydown", (event) => {
    if (event.ctrlKey && event.key.toLowerCase() === "j") {
      event.preventDefault();
      state.aiCollapsed = !state.aiCollapsed;
      storage.save("ai-collapsed", state.aiCollapsed ? "1" : "0");
      applyDrawerState();
      return;
    }

    if (event.ctrlKey && event.key.toLowerCase() === "k") {
      event.preventDefault();
      ui.commandInput.focus();
      return;
    }

    if (event.ctrlKey && event.key.toLowerCase() === "l") {
      event.preventDefault();
      clearTerminal();
      appendTerminal("Terminal cleared.\n");
    }
  });

  window.chrome?.webview?.addEventListener("message", ({ data }) => {
    if (!data) {
      return;
    }

    switch (data.type) {
      case "bootstrap":
        updateFromBootstrap(data);
        break;
      case "terminal-output":
        appendTerminal(data.text || "");
        break;
      case "terminal-reset":
        clearTerminal();
        break;
      case "status":
        setConnected(!!data.connected, data.text || "status");
        ui.footerStatus.textContent = data.text || "status";
        appendTerminal(`\n[${data.text || "status"}]\n`);
        break;
      case "error":
        appendTerminal(`\n[error] ${data.text || "Unknown error"}\n`);
        break;
      case "ai-response":
        setAiBusy(false);
        addAssistantMessage(data.answer || "No response.", data.command || "", data.risk || "");
        break;
      case "ai-error":
        removeThinkingMessage();
        setAiBusy(false);
        addAssistantMessage(data.text || "AI request failed.", "", "");
        break;
      default:
        break;
    }
  });
}

setupDrawerResizing();
setupEvents();
setMode("auto");
setAiBusy(false);
syncAiPromptHeight();
applyDrawerState();
syncConnectionButtons();
appendTerminal("Desktop terminal bridge ready. Select a server and connect.\n");
post({ type: "host-ready" });
