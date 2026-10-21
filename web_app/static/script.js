"use strict";

const form = document.getElementById("forecast-form");
const submitBtn = document.getElementById("submit-btn");
const resultSection = document.getElementById("result-section");
const errorSection = document.getElementById("error-section");
const errorText = document.getElementById("error-text");
const statusDot = document.querySelector(".status-dot");
const statusText = document.getElementById("status-text");

let chart = null;
let referenceData = null;

// Регистрация плагина подписей данных (если CDN-скрипт плагина загрузился)
if (window.ChartDataLabels) {
    Chart.register(ChartDataLabels);
}

// Экспоненциальная задержка повторов, чтобы не забивать сервер запросами, пока модель обучается.
function retryDelay(attempt) {
    return Math.min(3000 * Math.pow(1.5, attempt), 30000);
}

async function checkStatus() {
    try {
        const res = await fetch("/api/status");
        const data = await res.json();
        if (data.ready) {
            statusDot.classList.add("hidden");
            statusText.textContent = "Модель HistGradientBoosting";
        } else if (data.error) {
            statusDot.className = "status-dot error";
            statusText.textContent = "Ошибка обучения модели";
            console.error(data.error);
        } else {
            statusDot.className = "status-dot loading";
            statusText.textContent = "Модель обучается…";
            setTimeout(checkStatus, 3000);
        }
    } catch (err) {
        // Сервер недоступен — продолжаем опрашивать, чтобы страница сама восстановилась, когда сервер снова поднимется.
        statusDot.className = "status-dot error";
        statusText.textContent = "Сервер недоступен. Переподключение…";
        console.error(err);
        setTimeout(checkStatus, 3000);
    }
}

async function loadReference(attempt = 0) {
    let res;
    try {
        res = await fetch("/api/reference");
    } catch (err) {
        setTimeout(() => loadReference(attempt + 1), retryDelay(attempt));
        return;
    }
    if (!res.ok) {
        setTimeout(() => loadReference(attempt + 1), retryDelay(attempt));
        return;
    }
    const data = await res.json();
    referenceData = data;

    data.regions.forEach((r) => {
        const opt = document.createElement("option");
        opt.value = r;
        opt.textContent = r;
        regionSelect.appendChild(opt);
    });

    const wallSelect = document.getElementById("wall_material");
    data.wall_materials.forEach((w) => {
        const opt = document.createElement("option");
        opt.value = w;
        opt.textContent = w;
        wallSelect.appendChild(opt);
    });
}

// Каскадная фильтрация: округ → район → улица
const regionSelect = document.getElementById("region");
const districtInput = document.getElementById("district");
const streetInput = document.getElementById("street");
const districtList = document.getElementById("district-list");
const streetList = document.getElementById("street-list");

function fillDistrictList(region) {
    districtList.innerHTML = "";
    if (!region || !referenceData) return;
    const districts = (referenceData.region_districts || {})[region] || [];
    districts.forEach((d) => {
        const opt = document.createElement("option");
        opt.value = d;
        districtList.appendChild(opt);
    });
}

function fillStreetList(district) {
    streetList.innerHTML = "";
    if (!district || !referenceData) return;
    const streets = (referenceData.district_streets || {})[district] || [];
    streets.forEach((s) => {
        const opt = document.createElement("option");
        opt.value = s;
        streetList.appendChild(opt);
    });
}

regionSelect.addEventListener("change", () => {
    districtInput.value = "";
    streetInput.value = "";
    lastDistrict = "";
    fillDistrictList(regionSelect.value);
    fillStreetList("");
});

let lastDistrict = "";
districtInput.addEventListener("input", () => {
    const district = districtInput.value.trim();
    if (district !== lastDistrict) {
        lastDistrict = district;
        streetInput.value = "";
        fillStreetList(district);
    }
});

// Валидация 
function setError(fieldName, message) {
    const field = document.getElementById(fieldName);
    const msg = document.querySelector(`.error-msg[data-for="${fieldName}"]`);
    if (field) field.classList.toggle("invalid", Boolean(message));
    if (msg) msg.textContent = message || "";
}

function clearErrors() {
    document.querySelectorAll(".error-msg").forEach((el) => (el.textContent = ""));
    document.querySelectorAll(".invalid").forEach((el) => el.classList.remove("invalid"));
}

function isNumber(value) {
    if (typeof value !== "string" || value.trim() === "") return false;
    return !Number.isNaN(Number(value.replace(",", ".").trim()));
}

function validateForm() {
    let valid = true;

    const region = document.getElementById("region").value;
    const district = document.getElementById("district").value.trim();
    const street = document.getElementById("street").value.trim();
    const wallMaterial = document.getElementById("wall_material").value;
    const area = document.getElementById("area").value;
    const yearBuild = document.getElementById("year_build").value;
    const floor = document.getElementById("floor").value;
    const nYears = document.getElementById("n_years").value;

    if (!region) { setError("region", "Выберите административный округ."); valid = false; }
    if (!district) { setError("district", "Укажите район."); valid = false; }
    if (!street) { setError("street", "Укажите улицу."); valid = false; }
    if (!wallMaterial) { setError("wall_material", "Выберите материал стен."); valid = false; }

    if (!isNumber(area)) {
        setError("area", "Площадь должна быть числом.");
        valid = false;
    } else if (Number(area.replace(",", ".")) <= 0) {
        setError("area", "Площадь должна быть больше нуля.");
        valid = false;
    }

    if (!isNumber(yearBuild)) {
        setError("year_build", "Год постройки должен быть числом.");
        valid = false;
    } else {
        const y = Number(yearBuild);
        if (y < 1800 || y > new Date().getFullYear() + 5) {
            setError("year_build", "Укажите корректный год постройки.");
            valid = false;
        }
    }

    if (!isNumber(floor)) {
        setError("floor", "Этаж должен быть числом.");
        valid = false;
    } else if (Number(floor) < 1) {
        setError("floor", "Цокольный этаж выбрать нельзя");
        valid = false;
    }

    if (!isNumber(nYears)) {
        setError("n_years", "Горизонт должен быть числом.");
        valid = false;
    } else {
        const n = Number(nYears);
        if (n < 1 || n > 20) {
            setError("n_years", "Горизонт — от 1 до 20 лет.");
            valid = false;
        }
    }

    return valid;
}

// Отправка прогноза 
async function submitForecast(event) {
    event.preventDefault();
    clearErrors();

    if (!validateForm()) return;

    const payload = {
        region: document.getElementById("region").value,
        district: document.getElementById("district").value.trim(),
        street: document.getElementById("street").value.trim(),
        wall_material: document.getElementById("wall_material").value,
        area: document.getElementById("area").value.replace(",", "."),
        year_build: document.getElementById("year_build").value,
        floor: document.getElementById("floor").value,
        n_years: document.getElementById("n_years").value,
    };

    submitBtn.disabled = true;
    submitBtn.textContent = "Расчёт…";
    errorSection.classList.add("hidden");

    try {
        const res = await fetch("/api/predict", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });
        const data = await res.json();

        if (!res.ok) {
            showError(data.error || "Не удалось выполнить прогноз.");
            return;
        }
        renderResult(data);
    } catch (err) {
        showError("Ошибка соединения с сервером.");
        console.error(err);
    } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = "Рассчитать прогноз";
    }
}

// Отрисовка результата 
function renderResult(data) {
    const apt = data.apartment;

    const summary = document.getElementById("result-summary");
    summary.innerHTML = `
        <div class="summary-item">
            <div class="label">Базовая оценка (${data.base_year} г.)</div>
            <div class="value">${formatMln(data.base_price)} <small>млн руб.</small></div>
        </div>
        <div class="summary-item">
            <div class="label">Коэффициент округа ${apt.region}</div>
            <div class="value">${data.coef_region.toFixed(3)}</div>
        </div>
        <div class="summary-item">
            <div class="label">Прогноз инфляции</div>
            <div class="value">${data.infl_first.toFixed(1)}% → ${data.infl_last.toFixed(1)}%</div>
        </div>
        <div class="summary-item">
            <div class="label">Квартира</div>
            <div class="value" style="font-size:14px; line-height:1.35;">
                ${apt.district}, ${apt.street}<br>
                ${apt.area} м² · ${apt.floor} эт. · ${apt.year_build} г. · ${apt.wall_material}
            </div>
        </div>
    `;

    const tbody = document.querySelector("#forecast-table tbody");
    tbody.innerHTML = "";
    data.forecast.forEach((row) => {
        const tr = document.createElement("tr");
        tr.innerHTML = `
            <td>${row["Год"]}</td>
            <td>${row["Прогноз цены, млн руб."].toLocaleString("ru-RU", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
            <td>${row["Инфляция, %"].toLocaleString("ru-RU", { minimumFractionDigits: 1, maximumFractionDigits: 1 })}</td>
        `;
        tbody.appendChild(tr);
    });

    renderChart(data.forecast);
    resultSection.classList.remove("hidden");
    resultSection.scrollIntoView({ behavior: "smooth", block: "start" });
}

function renderChart(forecast) {
    const ctx = document.getElementById("forecast-chart").getContext("2d");
    const years = forecast.map((r) => r["Год"]);
    const prices = forecast.map((r) => r["Прогноз цены, млн руб."]);

    if (chart) chart.destroy();

    chart = new Chart(ctx, {
        type: "line",
        data: {
            labels: years,
            datasets: [{
                label: "Прогноз цены, млн руб.",
                data: prices,
                borderColor: "#2563eb",
                backgroundColor: "rgba(37, 99, 235, 0.12)",
                fill: true,
                tension: 0.25,
                pointBackgroundColor: "#1a4fa0",
                pointRadius: 5,
                pointHoverRadius: 7,
                borderWidth: 2.5,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            layout: {
                padding: { top: 30 },
            },
            interaction: {
                mode: "nearest",
                intersect: false,
            },
            plugins: {
                legend: { labels: { color: "#0f172a", font: { size: 13 } } },
                tooltip: {
                    callbacks: {
                        label: (item) => ` ${item.parsed.y.toLocaleString("ru-RU", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} млн руб.`,
                    },
                },
                datalabels: {
                    color: "#1a4fa0",
                    anchor: "end",
                    align: "top",
                    offset: 6,
                    font: { size: 12, weight: "bold" },
                    formatter: (value) => value.toLocaleString("ru-RU", { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
                    hover: {
                        color: "#0f172a",
                        font: { size: 18, weight: "bold" }, 
                    },
                },
            },
            scales: {
                x: {
                    ticks: { color: "#334155" },
                    grid: { color: "rgba(203, 213, 225, 0.4)" },
                },
                y: {
                    ticks: { color: "#334155" },
                    grid: { color: "rgba(203, 213, 225, 0.4)" },
                    title: { display: true, text: "млн руб.", color: "#334155" },
                },
            },
        },
    });
}

function formatMln(value) {
    return value.toLocaleString("ru-RU", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function showError(message) {
    errorText.textContent = message;
    errorSection.classList.remove("hidden");
    errorSection.scrollIntoView({ behavior: "smooth", block: "center" });
}

// Вкладки 

/* Вкладки и боковая панель ИИ-помощника */

let activeContentTab = "forecast";

document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
        const tab = btn.dataset.tab;

        if (tab === "assistant") {
            const isOpen = document.body.classList.toggle(
                "assistant-drawer-open"
            );

            document.querySelectorAll(".tab-btn").forEach((b) => {
                b.classList.toggle(
                    "active",
                    b.dataset.tab === (isOpen ? "assistant" : activeContentTab)
                );
            });

            document.querySelectorAll(".tab-panel").forEach((panel) => {
                panel.classList.toggle(
                    "active",
                    panel.id === `tab-${activeContentTab}`
                );
            });

            return;
        }

        activeContentTab = tab;
        document.body.classList.remove("assistant-drawer-open");

        document.querySelectorAll(".tab-btn").forEach((b) => {
            b.classList.toggle("active", b.dataset.tab === tab);
        });

        document.querySelectorAll(".tab-panel").forEach((panel) => {
            panel.classList.toggle("active", panel.id === `tab-${tab}`);
        });
    });
});


// EDA-графики Закономерности цен
async function loadEda(attempt = 0) {
    const imgs = {
        wall_material: document.getElementById("eda-wall-chart"),
        districts: document.getElementById("eda-district-chart"),
        area: document.getElementById("eda-area-chart"),
        floor: document.getElementById("eda-floor-chart"),
    };
    let res;
    try {
        res = await fetch("/api/eda");
    } catch (err) {
        console.error("Ошибка загрузки EDA-графиков:", err);
        setTimeout(() => loadEda(attempt + 1), retryDelay(attempt));
        return;
    }
    if (!res.ok) {
        setTimeout(() => loadEda(attempt + 1), retryDelay(attempt));
        return;
    }
    const data = await res.json();
    Object.entries(imgs).forEach(([key, img]) => {
        if (data[key]) {
            img.src = data[key];
        }
    });
}

// Инициализация 
form.addEventListener("submit", submitForecast);
form.addEventListener("reset", () => {
    clearErrors();
    resultSection.classList.add("hidden");
    errorSection.classList.add("hidden");
    lastDistrict = "";
    fillDistrictList("");
    fillStreetList("");
});

// Очистка ошибки поля при вводе
document.querySelectorAll("input, select").forEach((el) => {
    el.addEventListener("input", () => {
        const msg = document.querySelector(`.error-msg[data-for="${el.id}"]`);
        if (msg && msg.textContent) {
            el.classList.remove("invalid");
            msg.textContent = "";
        }
    });
});

checkStatus();
loadReference();
loadEda();


/* Заполнение формы данными, собранными ИИ-помощником */

function fillForecastFromAssistant(data) {
    if (!referenceData) {
        throw new Error("Справочник ещё загружается. Попробуйте повторить запрос.");
    }

    const required = [
        "region", "district", "street", "wall_material",
        "year_build", "floor", "area", "n_years"
    ];

    for (const key of required) {
        if (
            data[key] === undefined ||
            data[key] === null ||
            String(data[key]).trim() === ""
        ) {
            throw new Error(`Агент не передал обязательный параметр: ${key}.`);
        }
    }

    const regions = referenceData.regions || [];
    const districts =
        (referenceData.region_districts || {})[data.region] || [];
    const streets =
        (referenceData.district_streets || {})[data.district] || [];
    const materials = referenceData.wall_materials || [];

    if (!regions.includes(data.region)) {
        throw new Error("Округ не найден в справочнике. Уточните округ.");
    }
    if (!districts.includes(data.district)) {
        throw new Error("Район не относится к выбранному округу.");
    }
    if (!streets.includes(data.street)) {
        throw new Error("Улица не найдена в справочнике выбранного района.");
    }
    if (!materials.includes(data.wall_material)) {
        throw new Error("Материал стен отсутствует в справочнике.");
    }

    const year = Number(data.year_build);
    const floorNumber = Number(data.floor);
    const area = Number(String(data.area).replace(",", "."));
    const years = Number(data.n_years);

    if (
        !Number.isInteger(year) ||
        year < 1800 ||
        year > new Date().getFullYear() + 5
    ) {
        throw new Error("Проверьте год постройки.");
    }
    if (!Number.isInteger(floorNumber) || floorNumber < 1) {
        throw new Error("Этаж должен быть целым числом не меньше 1.");
    }
    if (!Number.isFinite(area) || area <= 0) {
        throw new Error("Площадь должна быть положительным числом.");
    }
    if (!Number.isInteger(years) || years < 1 || years > 20) {
        throw new Error("Горизонт прогноза должен составлять от 1 до 20 лет.");
    }

    regionSelect.value = data.region;
    fillDistrictList(data.region);

    districtInput.value = data.district;
    lastDistrict = data.district;
    fillStreetList(data.district);
    streetInput.value = data.street;

    document.getElementById("wall_material").value = data.wall_material;
    document.getElementById("year_build").value = String(year);
    document.getElementById("floor").value = String(floorNumber);
    document.getElementById("area").value = String(area);
    document.getElementById("n_years").value = String(years);

    clearErrors();

    // Переключаемся на вкладку прогноза.
    activeContentTab = "forecast";
    document.body.classList.remove("assistant-drawer-open");

    document.querySelectorAll(".tab-btn").forEach((btn) => {
        btn.classList.toggle("active", btn.dataset.tab === "forecast");
    });

    document.querySelectorAll(".tab-panel").forEach((panel) => {
        panel.classList.toggle("active", panel.id === "tab-forecast");
    });

    // Запускаем существующий обработчик формы.
    form.requestSubmit();
}

/* ИИ-помощник: отдельный чат */

const assistantForm = document.getElementById("assistant-form");
const assistantInput = document.getElementById("assistant-input");
const assistantMessages = document.getElementById("assistant-messages");
const assistantSend = document.getElementById("assistant-send");
const assistantClear = document.getElementById("assistant-clear");
const assistantError = document.getElementById("assistant-error");

// История хранится только в памяти открытой страницы.
// Она не записывается в localStorage или на диск.
let assistantHistory = [];

function addAssistantMessage(role, content) {
    const message = document.createElement("div");
    message.className = role === "user"
        ? "assistant-message assistant-message-user"
        : "assistant-message assistant-message-bot";

    const label = document.createElement("div");
    label.className = "assistant-message-label";
    label.textContent = role === "user" ? "Вы" : "ИИ-помощник";

    const text = document.createElement("div");
    text.className = "assistant-message-text";
    // Используем textContent, чтобы ответ не интерпретировался как HTML.
    text.textContent = content;

    message.append(label, text);
    assistantMessages.appendChild(message);
    assistantMessages.scrollTop = assistantMessages.scrollHeight;

    return message;
}

function showAssistantError(message) {
    assistantError.textContent = message;
    assistantError.classList.remove("hidden");
}

function hideAssistantError() {
    assistantError.textContent = "";
    assistantError.classList.add("hidden");
}

assistantForm.addEventListener("submit", async (event) => {
    event.preventDefault();

    const message = assistantInput.value.trim();

    if (!message) {
        showAssistantError("Введите сообщение.");
        return;
    }

    if (message.length > 4000) {
        showAssistantError("Сообщение слишком длинное.");
        return;
    }

    hideAssistantError();

    // Отправляем историю предыдущих сообщений.
    const historyForRequest = assistantHistory.slice(-20);

    addAssistantMessage("user", message);
    assistantHistory.push({ role: "user", content: message });

    assistantInput.value = "";
    assistantSend.disabled = true;
    assistantInput.disabled = true;
    assistantSend.textContent = "Ожидание…";

    try {
        const response = await fetch("/api/agent/chat", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({
                message,
                history: historyForRequest,
            }),
        });

        const responseText = await response.text();

        let data;
        try {
            data = JSON.parse(responseText);
        } catch {
            console.error("Сервер вернул не JSON:", responseText.slice(0, 1000));
            throw new Error(
                `Сервер вернул некорректный ответ (HTTP ${response.status}). ` +
                "Проверьте терминал Flask."
            );
        }

        if (!response.ok) {
            throw new Error(data.error || `Ошибка HTTP ${response.status}`);
        }


        if (typeof data.answer !== "string" || !data.answer.trim()) {
            throw new Error("ИИ-помощник вернул пустой ответ.");
        }

        
        let visibleAnswer = data.answer;
        const commandMatch = visibleAnswer.match(
            /\[\[CALCULATE_JSON\]\]([\s\S]*?)\[\[\/CALCULATE_JSON\]\]/
        );

        let calculationPayload = null;

        if (commandMatch) {
            try {
                calculationPayload = JSON.parse(commandMatch[1]);
            } catch {
                throw new Error(
                    "Агент сформировал некорректные параметры. Попросите его уточнить данные."
                );
            }

            visibleAnswer = visibleAnswer.replace(commandMatch[0], "").trim();
        }

        if (visibleAnswer) {
            addAssistantMessage("assistant", visibleAnswer);
            assistantHistory.push({
                role: "assistant",
                content: visibleAnswer,
            });
        }

        if (calculationPayload) {
            fillForecastFromAssistant(calculationPayload);
        }


        // Ограничиваем историю, передаваемую при следующих запросах.
        assistantHistory = assistantHistory.slice(-20);
    } catch (error) {
        showAssistantError(
            error.message || "Ошибка соединения с ИИ-помощником."
        );
    } finally {
        assistantSend.disabled = false;
        assistantInput.disabled = false;
        assistantSend.textContent = "Отправить";
        assistantInput.focus();
    }
});

// Enter отправляет сообщение, Shift+Enter добавляет новую строку.
assistantInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        assistantForm.requestSubmit();
    }
});

// Очистка чата удаляет сообщения только из текущей страницы.
assistantClear.addEventListener("click", () => {
    assistantHistory = [];
    assistantMessages.replaceChildren();
    hideAssistantError();

    addAssistantMessage(
        "assistant",
        "Приветствую! Я — ИИ-помощник. Задайте вопрос о прогнозировании или укажите параметры квартиры для расчёта."
    );
});

