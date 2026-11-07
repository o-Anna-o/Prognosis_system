import { useEffect } from "react";
import { ApartmentWorkspace } from "../features/apartments/ApartmentWorkspace";

let legacyUiPromise: Promise<void> | undefined;

function loadScript(src: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = src;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error(`Не удалось загрузить ${src}`));
    document.body.appendChild(script);
  });
}

function loadExistingUi(): Promise<void> {
  if (!legacyUiPromise) {
    legacyUiPromise = (async () => {
      try {
        await loadScript("https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js");
        await loadScript(
          "https://cdn.jsdelivr.net/npm/chartjs-plugin-datalabels@2.2.0/dist/chartjs-plugin-datalabels.min.js",
        );
      } catch (error) {
        console.error("Не удалось загрузить библиотеки графиков:", error);
      }
      await loadScript("/static/script.js");
    })();
  }

  return legacyUiPromise;
}

export function App() {
  useEffect(() => {
    void loadExistingUi().catch((error: unknown) => {
      console.error("Не удалось подключить существующие сценарии интерфейса:", error);
    });
  }, []);

  return (
    <>
      <header className="site-header">
        <div className="container header-inner">
          <div className="logo">
            <div>
              <h1>Прогнозирование стоимости квартиры в Москве</h1>
            </div>
          </div>
          <div id="model-status" className="model-status">
            <span className="status-dot" />
            <span id="status-text">Проверка модели…</span>
          </div>
        </div>
      </header>

      <nav className="tabs container" aria-label="Разделы сайта">
        <button type="button" className="tab-btn active" data-tab="forecast">
          Прогноз
        </button>
        <button type="button" className="tab-btn" data-tab="eda">
          Закономерности цен
        </button>
        <button type="button" className="tab-btn" data-tab="assistant">
          ИИ-помощник
        </button>
      </nav>

      <main className="container">
        <div className="main-layout">
          <aside id="tab-assistant" className="assistant-panel" aria-label="Чат с ИИ-помощником">
            <section className="card assistant-card">
              <div className="assistant-heading">
                <h2 className="card-title">ИИ-помощник</h2>
                <div className="assistant-heading-actions">
                  <button type="button" id="assistant-clear" className="btn btn-secondary">
                    Очистить чат
                  </button>
                  <button
                    type="button"
                    id="assistant-close"
                    className="assistant-close-btn"
                    aria-label="Закрыть чат"
                    title="Закрыть чат"
                  >
                    ✕
                  </button>
                </div>
              </div>

              <div
                id="assistant-messages"
                className="assistant-messages"
                role="log"
                aria-live="polite"
                aria-label="Переписка с ИИ-помощником"
              >
                <div className="assistant-message assistant-message-bot">
                  <div className="assistant-message-text">
                    Здравствуйте! Я помогу разобраться с формой прогноза и рассчитать стоимость
                    квартиры. Для расчёта понадобятся округ, район, улица, материал стен, год
                    постройки, этаж и площадь. Горизонт прогноза можно не указывать — по умолчанию
                    возьму 5 лет.
                  </div>
                </div>
              </div>

              <div id="assistant-error" className="assistant-error hidden" role="alert" />

              <form id="assistant-form" className="assistant-form">
                <label htmlFor="assistant-input">Ваше сообщение</label>
                <div className="assistant-input-row">
                  <textarea
                    id="assistant-input"
                    className="btn-send"
                    name="message"
                    rows={2}
                    maxLength={4000}
                    placeholder="Например: как рассчитывается прогноз цены?"
                    required
                  />
                  <button type="submit" id="assistant-send" className="btn btn-primary btn-send">
                    Отправить
                  </button>
                </div>
                <p className="assistant-hint">
                  Ответ формируется локальной моделью. Проверяйте введённые параметры квартиры
                  перед расчётом.
                </p>
              </form>
            </section>
          </aside>

          <div className="main-content">
            <section id="tab-forecast" className="tab-panel active">
              <ApartmentWorkspace />
            </section>

            <section id="tab-eda" className="tab-panel">
              <div className="card">
                <h2 className="card-title">Закономерности цен на квартиры</h2>
                <p className="eda-intro">
                  Анализ сделок с квартирами в Москве (2023–2026 гг.): как цена зависит от
                  материала стен, района, площади и этажа.
                </p>
                <div className="eda-block">
                  <h3>Цена квартиры по материалу стен</h3>
                  <div className="eda-chart-wrap">
                    <img id="eda-wall-chart" className="eda-chart" alt="Цена квартир по материалу стен" />
                  </div>
                </div>
                <div className="eda-block">
                  <h3>Медианная цена квартиры по районам (топ-20)</h3>
                  <div className="eda-chart-wrap">
                    <img
                      id="eda-district-chart"
                      className="eda-chart"
                      alt="Медианная цена квартир по районам"
                    />
                  </div>
                </div>
                <div className="eda-block">
                  <h3>Цена квартиры в зависимости от площади (группы по 10 м²)</h3>
                  <div className="eda-chart-wrap">
                    <img
                      id="eda-area-chart"
                      className="eda-chart"
                      alt="Цена квартиры в зависимости от площади"
                    />
                  </div>
                </div>
                <div className="eda-block">
                  <h3>Медианная цена квартиры по группе этажности</h3>
                  <div className="eda-chart-wrap">
                    <img
                      id="eda-floor-chart"
                      className="eda-chart"
                      alt="Медианная цена квартир по группе этажности"
                    />
                  </div>
                </div>
              </div>
            </section>
          </div>
        </div>
      </main>

      <footer className="site-footer">
        <div className="container">
          <p>подготовила Агапова Анна, 2026 г</p>
        </div>
      </footer>
    </>
  );
}
