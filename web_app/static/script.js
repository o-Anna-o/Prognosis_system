"use strict";

const form = document.getElementById("forecast-form");
const submitBtn = document.getElementById("submit-btn");
const resultSection = document.getElementById("result-section");
const errorSection = document.getElementById("error-section");
const errorText = document.getElementById("error-text");
const statusDot = document.querySelector(".status-dot");
const statusText = document.getElementById("status-text");

let chart = null;

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
        statusDot.className = "status-dot error";
        statusText.textContent = "Сервер недоступен";
        console.error(err);
    }
}

async function loadReference() {
    const res = await fetch("/api/reference");
    if (!res.ok) {
        setTimeout(loadReference, 3000);
        return;
    }
    const data = await res.json();

    const regionSelect = document.getElementById("region");
    data.regions.forEach((r) => {
        const opt = document.createElement("option");
        opt.value = r;
        opt.textContent = r;
        regionSelect.appendChild(opt);
    });

    const districtList = document.getElementById("district-list");
    data.districts.forEach((d) => {
        const opt = document.createElement("option");
        opt.value = d;
        districtList.appendChild(opt);
    });

    const streetList = document.getElementById("street-list");
    data.streets.forEach((s) => {
        const opt = document.createElement("option");
        opt.value = s;
        streetList.appendChild(opt);
    });

    const wallSelect = document.getElementById("wall_material");
    data.wall_materials.forEach((w) => {
        const opt = document.createElement("option");
        opt.value = w;
        opt.textContent = w;
        wallSelect.appendChild(opt);
    });
}

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
            plugins: {
                legend: { labels: { color: "#0f172a", font: { size: 13 } } },
                tooltip: {
                    callbacks: {
                        label: (item) => ` ${item.parsed.y.toLocaleString("ru-RU", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} млн руб.`,
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
document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
        const tab = btn.dataset.tab;
        document.querySelectorAll(".tab-btn").forEach((b) => {
            b.classList.toggle("active", b === btn);
        });
        document.querySelectorAll(".tab-panel").forEach((panel) => {
            panel.classList.toggle("active", panel.id === `tab-${tab}`);
        });
    });
});

// EDA-графики Закономерности цен
async function loadEda() {
    const imgs = {
        wall_material: document.getElementById("eda-wall-chart"),
        districts: document.getElementById("eda-district-chart"),
        area: document.getElementById("eda-area-chart"),
        floor: document.getElementById("eda-floor-chart"),
    };
    try {
        const res = await fetch("/api/eda");
        if (!res.ok) {
            setTimeout(loadEda, 3000);
            return;
        }
        const data = await res.json();
        Object.entries(imgs).forEach(([key, img]) => {
            if (data[key]) {
                img.src = data[key];
            }
        });
    } catch (err) {
        console.error("Ошибка загрузки EDA-графиков:", err);
        setTimeout(loadEda, 5000);
    }
}

// Инициализация 
form.addEventListener("submit", submitForecast);
form.addEventListener("reset", () => {
    clearErrors();
    resultSection.classList.add("hidden");
    errorSection.classList.add("hidden");
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
