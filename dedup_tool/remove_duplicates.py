# -*- coding: utf-8 -*-
"""
Удаление дубликатов из файла СДЕЛКИ_Мос_2019-2026.xlsx.

Скрипт:
1. Читает исходный Excel-файл.
2. Удаляет дубликаты строк по ключевым столбцам: адрес
   (region + district + street) + дата сделки (period_start_date) + цена (price).
   При этом остаётся первое вхождение дубликата (keep="first").
3. Сохраняет результат в новый файл *_dedup.xlsx (исходный файл не изменяется).
4. Печатает статистику: сколько строк было, сколько удалено, сколько осталось.

Запуск из корня проекта:
    python dedup_tool/remove_duplicates.py
"""

import sys
from pathlib import Path

import pandas as pd

# --- Настройки --------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
INPUT_FILE = PROJECT_ROOT / "СДЕЛКИ_Мос_2019-2026.xlsx"
OUTPUT_FILE = PROJECT_ROOT / "СДЕЛКИ_Мос_2019-2026_dedup.xlsx"

# Дубликат = строка с одинаковым адресом (region + district + street),
# одинаковой датой сделки (period_start_date) и одинаковой ценой (price).
SUBSET = ["region", "district", "street", "period_start_date", "price"]

# Пустое значение/None => дубликат = строка, совпадающая по ВСЕМ столбцам.
# SUBSET = None

# -----------------------------------------------------------------------------


def main() -> int:
    if not INPUT_FILE.exists():
        print(f"[ОШИБКА] Файл не найден: {INPUT_FILE}")
        return 1

    print(f"Чтение файла: {INPUT_FILE.name}")
    df = pd.read_excel(INPUT_FILE)
    total_before = len(df)
    print(f"Загружено строк: {total_before}, столбцов: {df.shape[1]}")

    if SUBSET:
        missing = [c for c in SUBSET if c not in df.columns]
        if missing:
            print(f"[ОШИБКА] В файле нет столбцов: {missing}")
            print(f"Доступные столбцы: {list(df.columns)}")
            return 1

    df_dedup = df.drop_duplicates(subset=SUBSET, keep="first").reset_index(drop=True)
    total_after = len(df_dedup)
    removed = total_before - total_after

    print(f"Удалено дубликатов: {removed}")
    print(f"Осталось строк: {total_after}")

    df_dedup.to_excel(OUTPUT_FILE, index=False)
    print(f"Результат сохранён в: {OUTPUT_FILE.name}")

    if removed == 0:
        print("Дубликаты не обнаружены.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
