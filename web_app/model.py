
from __future__ import annotations

import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

warnings.filterwarnings("ignore")


# Параметры проекта

BASE_DIR = Path(__file__).resolve().parent.parent  # корень проекта
DATA_PATH = BASE_DIR / "СДЕЛКИ_Мос_2023-2026.csv"
INFLATION_DATA_PATH = BASE_DIR / "СДЕЛКИ_Мос_2019-2026.csv"

RANDOM_STATE = 42

# Лучшие параметры модели (определены в блокноте заранее)
KNOWN_BEST_PARAMS = {
    "max_leaf_nodes": 63,
    "max_iter": 150,
    "learning_rate": 0.08,
    "l2_regularization": 1.0,
}

# Словарь соответствия кода материала стен его названию
WALL_MATERIAL_NAMES = {
    '61001001000': 'Каменные',
    '61001001001': 'Кирпичные',
    '61001003000': 'Смешанные',
    '61001006000': 'Бетонные',
    '61001006001': 'Монолитные',
    '61001007000': 'Железобетонные',
    '61001007001': 'Крупнопанельные',
    '61001007004': 'Крупноблочные',
}
# Обратный словарь: название -> код
WALL_MATERIAL_CODES = {name: code for code, name in WALL_MATERIAL_NAMES.items()}

# Параметры инфляции
MIN_DEALS_FOR_INFLATION = 30   # минимум сделок в году для надёжной медианы
MIN_INFLATION_PCT = 7.0        # нижняя граница инфляции, % в год

# Ограничение годового темпа роста рынка
GROWTH_FLOOR, GROWTH_CAP = -0.15, 0.25

# Признаки модели
CATEGORICAL_COLS = ["region", "district", "street", "wall_material_code"]
NUMERIC_COLS = ["year_build", "floor", "area", "period_year", "building_age"]
FEATURE_COLS = CATEGORICAL_COLS + NUMERIC_COLS



# Загрузка и очистка данных

def read_csv_robust(path: Path) -> pd.DataFrame:
    """Чтение CSV с перебором разделителей и кодировок (как в блокноте)."""
    if not path.exists():
        raise FileNotFoundError(f"CSV не найден: {path.resolve()}")
    read_error = None
    for sep in [None, ";", ",", "\t"]:
        for encoding in ["utf-8-sig", "cp1251"]:
            try:
                if sep is None:
                    loaded = pd.read_csv(path, sep=None, engine="python", encoding=encoding)
                else:
                    loaded = pd.read_csv(path, sep=sep, encoding=encoding)
                if loaded.shape[1] >= 5:
                    return loaded
            except Exception as exc:  # noqa: BLE001
                read_error = exc
    raise RuntimeError(f"Не удалось прочитать CSV {path}. Последняя ошибка: {read_error}")


def clean_numeric(series: pd.Series) -> pd.Series:
    """Очистка числовых значений: убирает пробелы, заменяет запятую на точку."""
    s = (series.astype("string")
         .str.replace("\u00a0", "", regex=False)
         .str.replace(" ", "", regex=False)
         .str.replace(",", ".", regex=False))
    return pd.to_numeric(s, errors="coerce")


def clean_data(df_raw: pd.DataFrame) -> pd.DataFrame:
    """Полная очистка данных, повторяющая блокнот."""
    df = df_raw.drop_duplicates().copy()

    text_cols = ["region", "district", "street", "wall_material_code"]
    for col in text_cols:
        df[col] = df[col].astype("string").str.strip()
        df[col] = df[col].replace({"": pd.NA, "nan": pd.NA, "None": pd.NA})

    for col in ["year_build", "floor", "area", "price"]:
        df[col] = clean_numeric(df[col])
    df["period_start_date"] = pd.to_datetime(df["period_start_date"], errors="coerce", dayfirst=True)
    df["period_year"] = df["period_start_date"].dt.year

    df = df[(df["area"] > 25) & (df["price"] > 7_000_000)].copy().reset_index(drop=True)
    df = df.dropna(subset=["period_start_date", "price", "area", "year_build", "floor"]).copy()

    current_year = pd.Timestamp.today().year
    valid = (
        (df["price"] > 0) & (df["area"] > 0) & (df["floor"] >= 1) &
        (df["year_build"].between(1800, current_year + 5)) &
        (df["period_year"].between(1900, current_year + 1)) &
        (df["year_build"] <= df["period_year"] + 1)
    )
    df = df.loc[valid].copy()

    df["year_build"] = df["year_build"].round().astype(int)
    df["floor"] = df["floor"].round().astype(int)
    df["period_year"] = df["period_year"].astype(int)
    df["price"] = df["price"].astype(float)
    df["price_per_sqm"] = df["price"] / df["area"]
    df["building_age"] = (df["period_year"] - df["year_build"]).clip(lower=0)
    df = df.replace([np.inf, -np.inf], np.nan).reset_index(drop=True)

    # Удаление выбросов по правилу 3 сигм
    STD_THRESHOLD = 3
    for col in ["price", "price_per_sqm"]:
        mean, std = df[col].mean(), df[col].std()
        lower, upper = mean - STD_THRESHOLD * std, mean + STD_THRESHOLD * std
        df = df[(df[col] >= lower) & (df[col] <= upper)].copy()

    return df.reset_index(drop=True)


def region_price_coef_from(data: pd.DataFrame) -> pd.Series:
    """Коэффициент стоимости по округу: медиана цены за м² в округе / медиана по Москве."""
    market_median = data["price_per_sqm"].median()
    if market_median <= 0:
        return pd.Series(dtype=float)
    coef = data.groupby("region")["price_per_sqm"].median() / market_median
    return coef.fillna(1.0)



# Инфляция

def compute_annual_market(infl_raw: pd.DataFrame) -> pd.DataFrame:
    """Годовая инфляция по медианной цене за м² (price/area)."""
    infl_raw = infl_raw.copy()
    infl_raw["period_start_date"] = pd.to_datetime(infl_raw["period_start_date"], errors="coerce", dayfirst=True)
    infl_raw["period_year"] = infl_raw["period_start_date"].dt.year
    infl_raw["price"] = pd.to_numeric(infl_raw["price"], errors="coerce")
    infl_raw["area"] = pd.to_numeric(infl_raw["area"], errors="coerce")
    infl_raw["price_per_sqm"] = infl_raw["price"] / infl_raw["area"]
    infl_raw = infl_raw[(infl_raw["price"] > 0) & (infl_raw["area"] > 0)].copy()

    # Удаление выбросов (правило 3 сигм)
    for col in ["price", "price_per_sqm"]:
        m, s = infl_raw[col].mean(), infl_raw[col].std()
        infl_raw = infl_raw[(infl_raw[col] >= m - 3 * s) & (infl_raw[col] <= m + 3 * s)]

    annual_market = (infl_raw.groupby("period_year")
                     .agg(median_price_per_sqm=("price_per_sqm", "median"),
                          deals=("price_per_sqm", "size"))
                     .reset_index().sort_values("period_year"))

    annual_market["inflation_pct"] = annual_market["median_price_per_sqm"].pct_change() * 100

    # Годы с малым числом сделок дают ненадёжную медиану — заменяем средним уровнем
    prev_deals = annual_market["deals"].shift(1)
    unreliable = (annual_market["deals"] < MIN_DEALS_FOR_INFLATION) | (prev_deals < MIN_DEALS_FOR_INFLATION)
    reliable_inflation = annual_market.loc[~unreliable, "inflation_pct"].dropna()
    avg_inflation_level = float(reliable_inflation.median()) if len(reliable_inflation) else 0.0

    annual_market.loc[unreliable, "inflation_pct"] = avg_inflation_level
    annual_market.loc[annual_market["period_year"] == annual_market["period_year"].min(), "inflation_pct"] = 0.0

    annual_market["inflation_pct"] = annual_market["inflation_pct"].clip(lower=MIN_INFLATION_PCT)
    annual_market["inflation_pct"] = annual_market["inflation_pct"].round(1)
    return annual_market


def forecast_inflation_pct(annual_market: pd.DataFrame, n_years: int,
                           floor_pct: float = 7.0, cap_pct: float = 15.0,
                           convergence: float = 0.15, min_step_pp: float = 0.2):
    """Прогноз инфляции на n_years лет.

    Последняя известная инфляция плавно сходится к целевому уровню —
    медиане последних 3 надёжных лет. Результат ограничен [floor_pct; cap_pct].
    """
    hist = annual_market.dropna(subset=["inflation_pct"]).copy()
    if len(hist) < 1:
        return [], []
    last_year = int(hist["period_year"].iloc[-1])
    last_inflation = float(hist["inflation_pct"].iloc[-1])
    target = float(hist["inflation_pct"].tail(3).median())

    years = list(range(last_year + 1, last_year + int(n_years) + 1))
    inflations = []
    current = last_inflation
    for _ in years:
        step = (current - target) * convergence
        if current > target and step < min_step_pp:
            step = min_step_pp
        current = current - step
        current = float(np.clip(current, floor_pct, cap_pct))
        inflations.append(current)
    return years, inflations



# Обучение модели

class PrognosisModel:
    """Обученная модель прогнозирования стоимости квартир."""

    def __init__(self, model, preprocessor, region_price_coef: pd.Series,
                 annual_market: pd.DataFrame, model_df: pd.DataFrame,
                 avg_inflation_level: float):
        self.model = model
        self.preprocessor = preprocessor
        self.region_price_coef = region_price_coef
        self.annual_market = annual_market
        self.model_df = model_df
        self.avg_inflation_level = avg_inflation_level
        self.base_year = int(model_df["period_year"].max())

    def predict_base_price(self, apartment: dict) -> float:
        """Базовая оценка квартиры моделью с учётом коэффициента округа."""
        year_build = int(apartment["year_build"])
        row = {
            "region": str(apartment["region"]),
            "district": str(apartment["district"]),
            "street": str(apartment["street"]),
            "wall_material_code": str(apartment["wall_material_code"]),
            "year_build": year_build,
            "floor": int(apartment["floor"]),
            "area": float(apartment["area"]),
            "period_year": self.base_year,
            "building_age": max(0, self.base_year - year_build),
        }
        X_new = pd.DataFrame([row])[FEATURE_COLS]
        base_price = float(np.maximum(0.0, np.expm1(self.model.predict(X_new)))[0])
        coef_region = float(self.region_price_coef.get(str(apartment["region"]), 1.0))
        return base_price * coef_region, coef_region

    def forecast(self, apartment: dict, n_years: int) -> dict:
        """Прогноз цены квартиры на n_years лет.

        Возвращает словарь с таблицей прогноза и служебной информацией.
        """
        base_price, coef_region = self.predict_base_price(apartment)

        infl_years, infl_values = forecast_inflation_pct(self.annual_market, n_years)

        years = [self.base_year] + list(infl_years)
        prices = [base_price]
        for inf in infl_values:
            prices.append(prices[-1] * (1.0 + inf / 100.0))

        forecast_df = pd.DataFrame({
            "Год": years,
            "Прогноз цены, млн руб.": [round(p / 1e6, 2) for p in prices],
            "Инфляция, %": pd.Series([0.0] + [round(i, 1) for i in infl_values]),
        })

        return {
            "forecast": forecast_df,
            "base_price": base_price,
            "coef_region": coef_region,
            "base_year": self.base_year,
            "avg_inflation_level": self.avg_inflation_level,
            "infl_first": infl_values[0] if infl_values else None,
            "infl_last": infl_values[-1] if infl_values else None,
        }


def train_model() -> PrognosisModel:
    """Полное обучение модели на всех доступных данных (как в блокноте)."""
    # 1. Основной датасет
    df_raw = read_csv_robust(DATA_PATH)
    df_raw.columns = df_raw.columns.astype(str).str.strip().str.lower()
    expected_cols = ["region", "district", "street", "wall_material_code",
                     "year_build", "floor", "area", "period_start_date", "price"]
    missing = [c for c in expected_cols if c not in df_raw.columns]
    if missing:
        raise ValueError(f"Не найдены колонки {missing}. В файле есть: {df_raw.columns.tolist()}")

    df = clean_data(df_raw)
    model_source = df.copy()

    # 2. Коэффициент стоимости по округу (по данным < 2026)
    region_price_coef = region_price_coef_from(model_source[model_source["period_year"] < 2026])

    # 3. Подготовка признаков
    model_df = model_source.copy()
    for col in CATEGORICAL_COLS:
        model_df[col] = model_df[col].astype("string").fillna("Неизвестно").astype(str)
    model_df = model_df.dropna(subset=["price", "period_year", "area"]).sort_values("period_start_date").reset_index(drop=True)

    try:
        onehot = OneHotEncoder(handle_unknown="ignore", min_frequency=2, sparse_output=False)
    except TypeError:
        onehot = OneHotEncoder(handle_unknown="ignore", min_frequency=2, sparse=False)

    preprocessor = ColumnTransformer([
        ("cat", Pipeline([("imputer", SimpleImputer(strategy="most_frequent")),
                          ("onehot", onehot)]), CATEGORICAL_COLS),
        ("num", Pipeline([("imputer", SimpleImputer(strategy="median"))]), NUMERIC_COLS)
    ], remainder="drop")

    # 4. Финальное обучение на всех строках (log1p цены)
    X = model_df[FEATURE_COLS]
    y = np.log1p(model_df["price"].astype(float))
    model = Pipeline([
        ("prep", preprocessor),
        ("model", HistGradientBoostingRegressor(
            max_leaf_nodes=KNOWN_BEST_PARAMS["max_leaf_nodes"],
            max_iter=KNOWN_BEST_PARAMS["max_iter"],
            learning_rate=KNOWN_BEST_PARAMS["learning_rate"],
            l2_regularization=KNOWN_BEST_PARAMS["l2_regularization"],
            random_state=RANDOM_STATE,
        )),
    ])
    model.fit(X, y)

    # 5. Инфляция по полному датасету 2019-2026
    infl_raw = read_csv_robust(INFLATION_DATA_PATH)
    annual_market = compute_annual_market(infl_raw)

    # Средний уровень инфляции по надёжным годам (после нижней границы)
    prev_deals = annual_market["deals"].shift(1)
    unreliable = (annual_market["deals"] < MIN_DEALS_FOR_INFLATION) | (prev_deals < MIN_DEALS_FOR_INFLATION)
    avg_inflation_level = float(annual_market.loc[~unreliable, "inflation_pct"].median())

    return PrognosisModel(
        model=model,
        preprocessor=preprocessor,
        region_price_coef=region_price_coef,
        annual_market=annual_market,
        model_df=model_df,
        avg_inflation_level=avg_inflation_level,
    )



# Справочные данные для формы

def load_reference_data() -> dict:
    """Списки округов, районов и улиц для выпадающих списков/подсказок."""
    df_raw = read_csv_robust(DATA_PATH)
    regions = sorted(df_raw["region"].dropna().astype(str).unique().tolist())
    districts = sorted(df_raw["district"].dropna().astype(str).unique().tolist())
    streets = sorted(df_raw["street"].dropna().astype(str).unique().tolist())
    return {
        "regions": regions,
        "districts": districts,
        "streets": streets,
        "wall_materials": list(WALL_MATERIAL_NAMES.values()),
    }



# EDA-графики для вкладки «Закономерности цен»

def _fig_to_base64(fig) -> str:
    """Сохранение matplotlib-фигуры в base64-строку data URI."""
    import base64
    import io

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100, bbox_inches="tight")
    buf.seek(0)
    return "data:image/png;base64," + base64.b64encode(buf.read()).decode("ascii")


def compute_eda_charts(model_df: pd.DataFrame) -> dict:
    """Генерирует EDA-графики закономерностей цен (как в Prognosis_system.ipynb).

    Возвращает словарь с base64-изображениями PNG:
    - wall_material — boxplot цены по материалу стен;
    - districts     — медианная цена по районам (топ-20);
    - area          — медианная цена по группам площади (по 10 м²);
    - floor         — медианная цена по группе этажности.
    Корреляционная матрица намеренно не включена.
    """
    import matplotlib
    matplotlib.use("Agg")  # headless-бэкенд для генерации без окна
    import matplotlib.pyplot as plt
    import seaborn as sns

    df = model_df.copy()
    df["price_mln"] = df["price"] / 1_000_000
    charts: dict = {}

    # 1. Цена квартиры по материалу стен (boxplot)
    wall = df.dropna(subset=["wall_material_code", "price_mln"]).copy()
    wall["wall_material"] = wall["wall_material_code"].map(WALL_MATERIAL_NAMES).fillna("Прочие")
    median_prices = wall.groupby("wall_material")["price_mln"].median().sort_values()
    if not median_prices.empty:
        fig, ax = plt.subplots(figsize=(11, max(5, 0.35 * len(median_prices))))
        sns.boxplot(data=wall, y="wall_material", x="price_mln",
                    color="skyblue", showfliers=False, ax=ax)
        ax.set_title("Цена квартир по материалу стен", fontsize=14)
        ax.set_xlabel("Цена квартиры, млн руб.")
        ax.set_ylabel("Материал стен")
        ax.set_xlim(0, 60)  # шкала цены — до 60 млн руб.
        ax.grid(axis="x", alpha=0.3)
        fig.tight_layout()
        charts["wall_material"] = _fig_to_base64(fig)
        plt.close(fig)

    # 2. Медианная цена по районам (топ-20)
    dist = (df.dropna(subset=["district", "price_mln"])
              .groupby("district")["price_mln"]
              .agg(["median", "count"])
              .sort_values("median", ascending=False)
              .head(20))
    if not dist.empty:
        fig, ax = plt.subplots(figsize=(11, max(5, 0.35 * len(dist))))
        sns.barplot(x=dist["median"].values, y=dist.index.astype(str),
                    color="steelblue", ax=ax)
        ax.set_title("Медианная цена квартиры по районам (топ-20)", fontsize=14)
        ax.set_xlabel("Медианная цена, млн руб.")
        ax.set_ylabel("Район")
        ax.grid(axis="x", alpha=0.3)
        fig.tight_layout()
        charts["districts"] = _fig_to_base64(fig)
        plt.close(fig)

    # 3. Цена в зависимости от площади (группы по 10 м²)
    area_df = df.dropna(subset=["area", "price_mln"]).copy()
    if area_df["area"].nunique() >= 2:
        bins = list(range(0, 301, 10))
        area_df["area_category"] = pd.cut(area_df["area"], bins=bins)
        stats = area_df.groupby("area_category", observed=True)["price_mln"].median().dropna()
        x_labels = [f"{int(iv.left)}–{int(iv.right)}" for iv in stats.index]

        fig, ax = plt.subplots(figsize=(14, 6))
        sns.barplot(x=x_labels, y=stats.values, color="steelblue", ax=ax)
        ax.set_title("Цена квартиры в зависимости от площади (группы по 10 м²)")
        ax.set_xlabel("Площадь, м²")
        ax.set_ylabel("Медианная цена, млн руб.")
        ax.tick_params(axis="x", rotation=45, labelsize=8)
        ax.grid(axis="y", alpha=0.3)
        for i, value in enumerate(stats.values):
            ax.text(i, value, f"{value:,.1f}", ha="center", va="bottom", fontsize=8)
        fig.tight_layout()
        charts["area"] = _fig_to_base64(fig)
        plt.close(fig)

    # 4. Медианная цена по группе этажности
    floor_df = df.dropna(subset=["floor", "price_mln"]).copy()
    floor_df["floor_group"] = pd.cut(
        floor_df["floor"], bins=[0, 1, 5, 10, 20, np.inf],
        labels=["1-й этаж", "2–5 этаж", "6–10 этаж", "11–20 этаж", "Выше 20-го"],
        include_lowest=True,
    )
    fstats = floor_df.groupby("floor_group", observed=True)["price_mln"].median().dropna()
    if not fstats.empty:
        fig, ax = plt.subplots(figsize=(9, 6))
        sns.barplot(x=fstats.index.astype(str), y=fstats.values, color="steelblue", ax=ax)
        ax.set_title("Медианная цена квартиры по группе этажности")
        ax.set_xlabel("Группа этажа")
        ax.set_ylabel("Медианная цена, млн руб.")
        ax.tick_params(axis="x", rotation=20)
        ax.grid(axis="y", alpha=0.3)
        for i, value in enumerate(fstats.values):
            ax.text(i, value, f"{value:,.1f}", ha="center", va="bottom")
        fig.tight_layout()
        charts["floor"] = _fig_to_base64(fig)
        plt.close(fig)

    return charts
