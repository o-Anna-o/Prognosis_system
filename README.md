# Система прогнозирования стоимости недвижимости

## 1. Настроить backend

Откройте PowerShell в корневой папке проекта и создайте виртуальное окружение:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r .\backend\requirements.txt
```

Создайте `.env` в корне проекта. Замените имя пользователя, пароль и базу на свои данные:

```dotenv
DATABASE_URL=postgresql://prognosis_user:your_password@127.0.0.1:5432/prognosis_db
DJANGO_SECRET_KEY=replace-this-with-a-long-random-secret
DJANGO_DEBUG=true
DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost
```

Файл `.env` содержит локальные настройки и не должен публиковаться в репозитории. Для локального запуска `DJANGO_DEBUG=true` удобно; не используйте этот режим для публикации приложения в интернете.

Примените миграции базы данных:

```powershell
.\.venv\Scripts\python.exe .\backend\manage.py migrate
```

## 2. Запустить backend

Из корневой папки проекта:

```powershell
.\.venv\Scripts\python.exe .\backend\manage.py runserver 127.0.0.1:8000
```

Или запустите файл `start_django.bat` в корневой папке. Backend будет доступен по адресу `http://127.0.0.1:8000`.

При первом запросе прогнозной модели backend загружает и подготавливает данные, поэтому первый ответ может занять больше времени.

## 4. Запустить frontend

Откройте второе окно PowerShell:

```powershell
cd frontend
npm install
npm run dev
```

Откройте адрес, который покажет Vite (обычно `http://127.0.0.1:5173`). Оставьте оба окна терминала открытыми, пока пользуетесь приложением.

## ИИ-агент

Для функций ИИ-агента дополнительно установите и запустите [Ollama](https://ollama.com/), затем скачайте используемую по умолчанию модель:

```powershell
ollama pull qwen3:8b
```

Убедитесь, что Ollama запущена и доступна по адресу `http://127.0.0.1:11434`. Модель и адрес при необходимости можно переопределить в `.env`:

```dotenv
OLLAMA_MODEL=qwen3:8b
OLLAMA_BASE_URL=http://127.0.0.1:11434
```

Основной запуск прогноза не требует Ollama.

## Важные файлы данных

В корне проекта должны находиться:

- `СДЕЛКИ_Мос_2023-2026.csv` — исходные данные.
- `Prognosis_HistGradientBoosting.joblib` — сохранённая модель HistGradientBoosting из ноутбука `Prognosis_HistGradientBoosting.ipynb`.

Они используются backend при расчёте прогноза. Не перемещайте их из корня проекта. Поправка на инфляцию рассчитывается backend отдельно от модели и применяется после прогноза базовой цены.
