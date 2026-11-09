interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

interface AssistantChatResponse {
  answer?: unknown;
  error?: unknown;
  conversation_id?: unknown;
}

interface EdaCharts {
  wall_material?: string;
  districts?: string;
  area?: string;
  floor?: string;
}

let chartLibrariesPromise: Promise<void> | null = null;

function loadScript(src: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = src;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error(`Не удалось загрузить ${src}`));
    document.body.appendChild(script);
  });
}

function loadChartLibraries(): Promise<void> {
  chartLibrariesPromise ??= (async () => {
    try {
      await loadScript("https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js");
      await loadScript("https://cdn.jsdelivr.net/npm/chartjs-plugin-datalabels@2.2.0/dist/chartjs-plugin-datalabels.min.js");
      const chart = (window as Window & { Chart?: { register: (plugin: unknown) => void }; ChartDataLabels?: unknown }).Chart;
      const plugin = (window as Window & { ChartDataLabels?: unknown }).ChartDataLabels;
      if (chart && plugin) chart.register(plugin);
    } catch (error) {
      console.error("Не удалось загрузить библиотеки графиков:", error);
    }
  })();
  return chartLibrariesPromise;
}

function startStatusPolling(): () => void {
  const dot = document.querySelector<HTMLElement>(".status-dot");
  const text = document.getElementById("status-text");
  if (!dot || !text) return () => undefined;

  let stopped = false;
  let timer = 0;
  const check = async () => {
    try {
      const response = await fetch("/api/status");
      const status: { ready?: boolean; error?: string | null } = await response.json();
      if (stopped) return;
      if (response.ok && status.ready) {
        dot.classList.add("hidden");
        text.textContent = "Модель HistGradientBoosting";
      } else if (status.error) {
        dot.className = "status-dot error";
        text.textContent = "Ошибка загрузки модели";
        console.error(status.error);
      } else {
        dot.className = "status-dot loading";
        text.textContent = "Модель HistGradientBoosting загружается…";
        timer = window.setTimeout(() => void check(), 3000);
      }
    } catch (error) {
      if (stopped) return;
      dot.className = "status-dot error";
      text.textContent = "Сервер недоступен. Переподключение…";
      console.error(error);
      timer = window.setTimeout(() => void check(), 3000);
    }
  };
  void check();
  return () => { stopped = true; window.clearTimeout(timer); };
}

function initializeSectionTabs(): () => void {
  const buttons = Array.from(document.querySelectorAll<HTMLButtonElement>(".tab-btn"));
  const panels = Array.from(document.querySelectorAll<HTMLElement>(".tab-panel"));
  const closeButton = document.getElementById("assistant-close");
  let activeTab = "forecast";
  let edaRequested = false;
  let stopped = false;
  let edaTimer = 0;

  const updateButtons = (active: string) => {
    buttons.forEach((button) => button.classList.toggle("active", button.dataset.tab === active));
  };
  const loadEda = async (attempt = 0): Promise<void> => {
    if (stopped) return;
    if (attempt === 0 && edaRequested) return;
    edaRequested = true;
    try {
      const response = await fetch("/api/eda");
      if (!response.ok) throw new Error(`EDA API вернул HTTP ${response.status}`);
      const data: EdaCharts = await response.json();
      if (stopped) return;
      const images: Record<keyof EdaCharts, HTMLElement | null> = {
        wall_material: document.getElementById("eda-wall-chart"),
        districts: document.getElementById("eda-district-chart"),
        area: document.getElementById("eda-area-chart"),
        floor: document.getElementById("eda-floor-chart"),
      };
      (Object.keys(images) as (keyof EdaCharts)[]).forEach((key) => {
        const image = images[key];
        if (image && data[key]) image.setAttribute("src", data[key]!);
      });
    } catch (error) {
      console.error("Ошибка загрузки EDA-графиков:", error);
      const delay = Math.min(3000 * 1.5 ** attempt, 30000);
      edaTimer = window.setTimeout(() => void loadEda(attempt + 1), delay);
    }
  };

  const buttonHandlers = new Map<HTMLButtonElement, EventListener>();
  buttons.forEach((button) => {
    const handler: EventListener = () => {
      const tab = button.dataset.tab;
      if (!tab) return;
      if (tab === "assistant") {
        const isOpen = document.body.classList.toggle("assistant-open");
        updateButtons(isOpen ? "assistant" : activeTab);
        return;
      }
      activeTab = tab;
      document.body.classList.remove("assistant-open");
      if (tab === "eda") void loadEda();
      updateButtons(tab);
      panels.forEach((panel) => panel.classList.toggle("active", panel.id === `tab-${tab}`));
    };
    button.addEventListener("click", handler);
    buttonHandlers.set(button, handler);
  });
  const closeHandler: EventListener = () => {
    document.body.classList.remove("assistant-open");
    updateButtons(activeTab);
  };
  const showForecastHandler: EventListener = () => {
    activeTab = "forecast";
    document.body.classList.remove("assistant-open");
    updateButtons(activeTab);
    panels.forEach((panel) => panel.classList.toggle("active", panel.id === "tab-forecast"));
  };
  closeButton?.addEventListener("click", closeHandler);
  window.addEventListener("prognosis:show-forecast", showForecastHandler);

  return () => {
    stopped = true;
    window.clearTimeout(edaTimer);
    buttonHandlers.forEach((handler, button) => button.removeEventListener("click", handler));
    closeButton?.removeEventListener("click", closeHandler);
    window.removeEventListener("prognosis:show-forecast", showForecastHandler);
  };
}

function initializeAssistant(): () => void {
  const form = document.getElementById("assistant-form");
  const input = document.getElementById("assistant-input");
  const messages = document.getElementById("assistant-messages");
  const send = document.getElementById("assistant-send");
  const clear = document.getElementById("assistant-clear");
  const error = document.getElementById("assistant-error");
  if (!(form instanceof HTMLFormElement) || !(input instanceof HTMLTextAreaElement)
    || !(messages instanceof HTMLElement) || !(send instanceof HTMLButtonElement)
    || !(clear instanceof HTMLButtonElement) || !(error instanceof HTMLElement)) return () => undefined;

  const assistantInput = input;
  const assistantMessages = messages;
  const assistantSend = send;
  const assistantError = error;
  const conversationStorageKey = "prognosis-assistant-conversation-id";
  const createConversationId = () => crypto.randomUUID();
  let conversationId = sessionStorage.getItem(conversationStorageKey) || createConversationId();
  sessionStorage.setItem(conversationStorageKey, conversationId);
  let history: ChatMessage[] = [];
  let controller: AbortController | null = null;

  const addMessage = (role: ChatMessage["role"], content: string) => {
    const message = document.createElement("div");
    message.className = role === "user" ? "assistant-message assistant-message-user" : "assistant-message assistant-message-bot";
    if (role === "user") {
      const label = document.createElement("div");
      label.className = "assistant-message-label";
      label.textContent = "Вы";
      message.appendChild(label);
    }
    const text = document.createElement("div");
    text.className = "assistant-message-text";
    text.textContent = content;
    message.appendChild(text);
    assistantMessages.appendChild(message);
    assistantMessages.scrollTop = assistantMessages.scrollHeight;
  };
  const showError = (message: string) => {
    assistantError.textContent = message;
    assistantError.classList.remove("hidden");
  };
  const hideError = () => {
    assistantError.textContent = "";
    assistantError.classList.add("hidden");
  };
  const errorEventHandler: EventListener = (event) => {
    const detail = (event as CustomEvent<unknown>).detail;
    showError(typeof detail === "string" ? detail : "Не удалось заполнить параметры квартиры.");
  };
  const submitHandler: EventListener = async (event) => {
    event.preventDefault();
    const message = assistantInput.value.trim();
    if (!message) { showError("Введите сообщение."); return; }
    if (message.length > 4000) { showError("Сообщение слишком длинное."); return; }
    hideError();
    const historyForRequest = history.slice(-20);
    addMessage("user", message);
    history.push({ role: "user", content: message });
    assistantInput.value = "";
    assistantSend.disabled = true;
    assistantInput.disabled = true;
    assistantSend.textContent = "Ожидание…";
    controller = new AbortController();
    try {
      const response = await fetch("/api/agent/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message,
          history: historyForRequest,
          conversation_id: conversationId,
          prediction_context: sessionStorage.getItem("prognosis-assistant-result-context"),
        }),
        signal: controller.signal,
      });
      const responseText = await response.text();
      let data: AssistantChatResponse;
      try {
        data = JSON.parse(responseText) as AssistantChatResponse;
      } catch {
        console.error("Сервер вернул не JSON:", responseText.slice(0, 1000));
        throw new Error(`Сервер вернул некорректный ответ (HTTP ${response.status}). Проверьте терминал backend.`);
      }
      if (!response.ok) throw new Error(typeof data.error === "string" ? data.error : `Ошибка HTTP ${response.status}`);
      if (typeof data.conversation_id === "string") {
        conversationId = data.conversation_id;
        sessionStorage.setItem(conversationStorageKey, conversationId);
      }
      const answer = data.answer;
      if (typeof answer !== "string" || !answer.trim()) throw new Error("ИИ-агент вернул пустой ответ.");

      let visibleAnswer = answer;
      const commandMatch = visibleAnswer.match(/\[\[CALCULATE_JSON\]\]([\s\S]*?)\[\[\/CALCULATE_JSON\]\]/);
      if (commandMatch) {
        let calculationPayload: unknown;
        try {
          calculationPayload = JSON.parse(commandMatch[1]!);
        } catch {
          throw new Error("Агент сформировал некорректные параметры. Попросите его уточнить данные.");
        }
        visibleAnswer = visibleAnswer.replace(commandMatch[0], "").trim();
        window.dispatchEvent(new CustomEvent("prognosis:assistant-calculation", { detail: calculationPayload }));
      }
      visibleAnswer = visibleAnswer.replace(/\[\[APARTMENTS_STATE_JSON\]\][\s\S]*?\[\[\/APARTMENTS_STATE_JSON\]\]/g, "").trim();
      if (visibleAnswer) {
        addMessage("assistant", visibleAnswer);
        history.push({ role: "assistant", content: visibleAnswer });
      }
      history = history.slice(-20);
    } catch (caught) {
      if (caught instanceof DOMException && caught.name === "AbortError") return;
      showError(caught instanceof Error ? caught.message : "Ошибка соединения с ИИ-агентом.");
    } finally {
      controller = null;
      assistantSend.disabled = false;
      assistantInput.disabled = false;
      assistantSend.textContent = "Отправить";
      if (document.body.classList.contains("assistant-open")) assistantInput.focus();
    }
  };
  const keyHandler: EventListener = (event) => {
    const keyboardEvent = event as KeyboardEvent;
    if (keyboardEvent.key === "Enter" && !keyboardEvent.shiftKey) {
      keyboardEvent.preventDefault();
      form.requestSubmit();
    }
  };
  const clearHandler: EventListener = () => {
    conversationId = createConversationId();
    sessionStorage.setItem(conversationStorageKey, conversationId);
    history = [];
    assistantMessages.replaceChildren();
    hideError();
    addMessage("assistant", "Приветствую! Я — ИИ-агент. Задайте вопрос о прогнозировании или укажите параметры квартиры для расчёта.");
  };

  form.addEventListener("submit", submitHandler);
  assistantInput.addEventListener("keydown", keyHandler);
  clear.addEventListener("click", clearHandler);
  window.addEventListener("prognosis:assistant-error", errorEventHandler);
  return () => {
    controller?.abort();
    form.removeEventListener("submit", submitHandler);
    assistantInput.removeEventListener("keydown", keyHandler);
    clear.removeEventListener("click", clearHandler);
    window.removeEventListener("prognosis:assistant-error", errorEventHandler);
  };
}

export function initializeBrowserUi(): () => void {
  void loadChartLibraries();
  const cleanups = [startStatusPolling(), initializeSectionTabs(), initializeAssistant()];
  return () => cleanups.forEach((cleanup) => cleanup());
}
