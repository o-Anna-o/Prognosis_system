
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import re
import sys
import joblib
from sklearn.base import BaseEstimator, RegressorMixin
from sklearn.feature_extraction import DictVectorizer
from sklearn.linear_model import Ridge
from sklearn.utils.validation import check_is_fitted


# Параметры проекта

BASE_DIR = Path(__file__).resolve().parent.parent  # корень проекта
DATA_PATH = BASE_DIR / "СДЕЛКИ_Мос_2023-2026.csv"

RANDOM_STATE = 42

# Лучшие параметры модели (определены в блокноте заранее)


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

# Официальный список районов по округам.
# Именно он показывается в форме и используется ИИ-помощником:
# районы из датасета, которых нет в этом списке, пользователю не предлагаются.
OFFICIAL_DISTRICTS = {
    "ВАО": [
        "Богородское",
        "Вешняки",
        "Восточное Измайлово",
        "Гольяново",
        "Ивановское",
        "Измайлово",
        "Косино-Ухтомский",
        "Метрогородок",
        "Новогиреево",
        "Новокосино",
        "Перово",
        "Преображенское",
        "Северное Измайлово",
        "Соколиная Гора",
        "Сокольники",
    ],
    "ЗАО": [
        "Внуково",
        "Дорогомилово",
        "Крылатское",
        "Кунцево",
        "Можайский",
        "Ново-Переделкино",
        "Очаково-Матвеевское",
        "Проспект Вернадского",
        "Раменки",
        "Солнцево",
        "Тропарево-Никулино",
        "Филевский Парк",
        "Фили-Давыдково",
    ],
    "ЗелАО": [
        "Зеленоград",
        "Крюково",
        "Матушкино",
        "Савелки",
        "Силино",
        "Старое Крюково",
    ],
    "НАО": [
        "Внуково",
        "Внуковское",
        "Коммунарка",
        "Марушкино",
        "Молжаниновский",
        "Московский",
        "Сосенское",
        "Филимонковский",
        "Щербинка",
        "поселение Воскресенское",
        "поселение Десеновское",
        "поселение Кокошкино",
        "поселение Новофедоровское",
        "поселение Первомайское",
        "поселение Рязановское",
    ],
    "САО": [
        "Аэропорт",
        "Беговой",
        "Бескудниковский",
        "Войковский",
        "Восточное Дегунино",
        "Головинский",
        "Дмитровский",
        "Западное Дегунино",
        "Коптево",
        "Левобережный",
        "Молжаниновский",
        "Савеловский",
        "Сокол",
        "Тимирязевский",
        "Ховрино",
        "Хорошевский",
    ],
    "СВАО": [
        "Алексеевский",
        "Алтуфьевский",
        "Бабушкинский",
        "Бибирево",
        "Бутырский",
        "Лианозово",
        "Лосиноостровский",
        "Марфино",
        "Марьина Роща",
        "Останкинский",
        "Отрадное",
        "Ростокино",
        "Свиблово",
        "Северное Медведково",
        "Северный",
        "Южное Медведково",
        "Ярославский",
    ],
    "СЗАО": [
        "Куркино",
        "Митино",
        "Покровское-Стрешнево",
        "Северное Тушино",
        "Строгино",
        "Хорошево-Мневники",
        "Щукино",
        "Южное Тушино",
    ],
    "ТАО": [
        "Бекасово",
        "Краснопахорский",
        "городской округ Троицк",
        "поселение Новофедоровское",
    ],
    "ЦАО": [
        "Арбат",
        "Басманный",
        "Замоскворечье",
        "Красносельский",
        "Мещанский",
        "Пресненский",
        "Таганский",
        "Тверской",
        "Хамовники",
        "Якиманка",
    ],
    "ЮАО": [
        "Бирюлево Восточное",
        "Бирюлево Западное",
        "Братеево",
        "Даниловский",
        "Донской",
        "Зябликово",
        "Москворечье-Сабурово",
        "Нагатино-Садовники",
        "Нагатинский Затон",
        "Нагорный",
        "Орехово-Борисово Северное",
        "Орехово-Борисово Южное",
        "Царицыно",
        "Чертаново Северное",
        "Чертаново Центральное",
        "Чертаново Южное",
    ],
    "ЮВАО": [
        "Выхино-Жулебино",
        "Капотня",
        "Кузьминки",
        "Лефортово",
        "Люблино",
        "Марьино",
        "Некрасовка",
        "Нижегородский",
        "Печатники",
        "Рязанский",
        "Текстильщики",
        "Южнопортовый",
    ],
    "ЮЗАО": [
        "Академический",
        "Гагаринский",
        "Зюзино",
        "Коньково",
        "Котловка",
        "Ломоносовский",
        "Обручевский",
        "Северное Бутово",
        "Теплый Стан",
        "Черемушки",
        "Южное Бутово",
        "Ясенево",
    ],
}

# Официальное написание района -> другие написания в датасете.
# Нужны, чтобы модель использовала знакомую ей категорию, а пользователь
# видел одно официальное название района.
DISTRICT_DATASET_ALIASES = {
    "Соколиная Гора": ["Соколиная гора"],
    "Филевский Парк": ["Филевский парк"],
    "Внуковское": ["поселение Внуковское"],
    "Марушкино": ["поселение Марушкинское"],
    "Московский": ["поселение Московский"],
    "Сосенское": ["поселение Сосенское"],
    "Филимонковский": ["поселение Филимонковское"],
    "Щербинка": ["городской округ Щербинка"],
    "Марьина Роща": ["Марьина роща"],
    "Нагатинский Затон": ["Нагатинский затон"],
}

# Полные названия округов и их сокращения.
REGION_NAMES = {
    "ВАО": "Восточный административный округ",
    "ЗАО": "Западный административный округ",
    "ЗелАО": "Зеленоградский административный округ",
    "НАО": "Новомосковский административный округ",
    "САО": "Северный административный округ",
    "СВАО": "Северо-Восточный административный округ",
    "СЗАО": "Северо-Западный административный округ",
    "ТАО": "Троицкий административный округ",
    "ЦАО": "Центральный административный округ",
    "ЮАО": "Южный административный округ",
    "ЮВАО": "Юго-Восточный административный округ",
    "ЮЗАО": "Юго-Западный административный округ",
}

REGION_ALIASES = {}
for _code, _name in REGION_NAMES.items():
    REGION_ALIASES[_code.lower()] = _code
    REGION_ALIASES[_name.lower()] = _code
    REGION_ALIASES[_name.lower().replace(" административный округ", "")] = _code

# Разговорные названия материалов стен -> официальное название.
WALL_MATERIAL_ALIASES = {
    "крупнопанель": "Крупнопанельные",
    "панель": "Крупнопанельные",
    "панельные": "Крупнопанельные",
    "крупноблоч": "Крупноблочные",
    "кирпич": "Кирпичные",
    "монолит": "Монолитные",
    "железобетон": "Железобетонные",
    "бетон": "Бетонные",
    "смешан": "Смешанные",
    "камен": "Каменные",
}

# Минимум сделок для надёжного годового индикатора роста.

# Признаки модели
CATEGORICAL_COLS = ["region", "district", "street", "wall_material_code"]
NUMERIC_COLS = ["year_build", "floor", "area"]
FEATURE_COLS = CATEGORICAL_COLS + NUMERIC_COLS + ["period_year"]
MIN_DEALS_FOR_INFLATION = 30
MIN_INFLATION_PCT = 7.0
MAX_INFLATION_PCT = 15.0
INFLATION_CONVERGENCE = 0.15
MIN_INFLATION_STEP_PP = 0.2



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

    valid = (
        (df["price"] > 0) & (df["area"] > 0) & (df["floor"] >= 1) &
        (df["year_build"] >= 1800) &
        (df["period_year"] >= 1900) &
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

    return df.reset_index(drop=True)


def region_price_coef_from(data: pd.DataFrame) -> pd.Series:
    """K АО = среднее арифметическое price/area в АО / среднее по Москве."""
    valid = data.loc[
        data["price"].gt(0) & data["area"].gt(0), ["region", "price", "area"]
    ].copy()
    if valid.empty:
        return pd.Series(dtype=float)
    valid["price_per_sqm"] = valid["price"] / valid["area"]
    market_mean = float(valid["price_per_sqm"].mean())
    if not np.isfinite(market_mean) or market_mean <= 0:
        return pd.Series(dtype=float)
    coef = valid.groupby("region")["price_per_sqm"].mean() / market_mean
    return coef.fillna(1.0)



# Инфляция

def compute_annual_market(infl_raw: pd.DataFrame) -> pd.DataFrame:
    """Estimate annual price inflation from robust median price per square metre."""
    data = infl_raw.copy()
    data["period_start_date"] = pd.to_datetime(
        data["period_start_date"], errors="coerce", dayfirst=True
    )
    data["period_year"] = data["period_start_date"].dt.year
    data["price"] = clean_numeric(data["price"])
    data["area"] = clean_numeric(data["area"])
    data = data.loc[
        data["price"].gt(0) & data["area"].gt(0)
    ].copy()
    data["price_per_sqm"] = data["price"] / data["area"]
    data = data.replace([np.inf, -np.inf], np.nan).dropna(
        subset=["period_year", "price", "price_per_sqm"]
    )

    # Apply the same sequential 3-sigma filter used for the model training data.
    for column in ["price", "price_per_sqm"]:
        mean = data[column].mean()
        std = data[column].std()
        if pd.notna(std) and std > 0:
            data = data.loc[
                data[column].between(mean - 3 * std, mean + 3 * std)
            ].copy()

    annual_market = (
        data.groupby("period_year")
        .agg(
            median_price_per_sqm=("price_per_sqm", "median"),
            deals=("price_per_sqm", "size"),
        )
        .reset_index()
        .sort_values("period_year")
        .reset_index(drop=True)
    )
    if annual_market.empty:
        raise ValueError("Для расчёта инфляции не осталось корректных сделок.")

    annual_market["inflation_pct"] = annual_market["median_price_per_sqm"].pct_change() * 100
    previous_deals = annual_market["deals"].shift(1)
    unreliable = (
        annual_market["deals"].lt(MIN_DEALS_FOR_INFLATION)
        | previous_deals.lt(MIN_DEALS_FOR_INFLATION)
    )
    reliable = annual_market.loc[~unreliable, "inflation_pct"].dropna()
    average_inflation = float(reliable.median()) if not reliable.empty else MIN_INFLATION_PCT

    annual_market.loc[unreliable, "inflation_pct"] = average_inflation
    # The first year has no preceding comparison year, so keep it at zero after clipping.
    annual_market["inflation_pct"] = annual_market["inflation_pct"].clip(
        lower=MIN_INFLATION_PCT
    )
    annual_market.loc[annual_market.index[0], "inflation_pct"] = 0.0
    annual_market["inflation_pct"] = annual_market["inflation_pct"].round(1)
    annual_market.attrs["avg_inflation_level"] = max(
        MIN_INFLATION_PCT, average_inflation
    )
    return annual_market


TIME_CENTER = 2024.5
MIN_STREET_TOTAL, MIN_STREET_PER_YEAR = 20, 5
MIN_DISTRICT_TOTAL, MIN_DISTRICT_PER_YEAR = 15, 3


def normalize_text(value) -> str:
    if pd.isna(value) or not str(value).strip():
        return "_неизвестно_"
    return re.sub(r"\s+", " ", str(value).strip().lower().replace("ё", "е"))


def district_key(row) -> str:
    return f"{row['region']} | {row['district']}"


def street_key(row) -> str:
    return f"{row['region']} | {row['district']} | {row['street']}"


def supported_keys(frame: pd.DataFrame, key_func, minimum_total: int, minimum_year: int) -> set[str]:
    keys = [key_func(row) for row in frame[CATEGORICAL_COLS].to_dict("records")]
    counts = pd.crosstab(pd.Series(keys, index=frame.index), frame["period_year"])
    keep = (counts.sum(axis=1) >= minimum_total) & ((counts >= minimum_year).sum(axis=1) >= 2)
    return set(counts.index[keep])


def make_support(frame: pd.DataFrame) -> dict[str, set[str]]:
    return {
        "district_trends": supported_keys(frame, district_key, MIN_DISTRICT_TOTAL, MIN_DISTRICT_PER_YEAR),
        "street_trends": supported_keys(frame, street_key, MIN_STREET_TOTAL, MIN_STREET_PER_YEAR),
    }


def record_features(row, support, with_time: bool = True, trend_scale: float = 1.0) -> dict[str, float]:
    region = str(row["region"])
    wall = str(row["wall_material_code"])
    district = district_key(row)
    street = street_key(row)
    log_area = np.log(float(row["area"]) / 50.0)
    floor = (float(row["floor"]) - 7) / 12.0
    build = (float(row["year_build"]) - 1985) / 40.0
    numeric = {
        "log_area": log_area, "log_area_sq": log_area ** 2,
        "floor": floor, "floor_sq": floor ** 2,
        "build": build, "build_sq": build ** 2,
    }
    level = {
        "region=" + region: 1.0, "district=" + district: 1.0,
        "street=" + street: 1.0, "wall=" + wall: 1.0, **numeric,
    }
    features = {"L:" + key: value for key, value in level.items()}
    if with_time:
        slope = {"global": 1.0, "region=" + region: 1.0, "wall=" + wall: 1.0, **numeric}
        if district in support["district_trends"]:
            slope["district=" + district] = 1.0
        if street in support["street_trends"]:
            slope["street=" + street] = 1.0
        time_value = (float(row["period_year"]) - TIME_CENTER) * float(trend_scale)
        features.update({"T:" + key: time_value * value for key, value in slope.items()})
    return features


class ApartmentEstimator(RegressorMixin, BaseEstimator):
    """Sklearn estimator interface for the persisted price models."""

    def __init__(self, kind="ridge_time", alpha=100.0, trend_scale=1.0,
                 max_iter=180, max_leaf_nodes=31, min_samples_leaf=40,
                 learning_rate=0.07, l2_regularization=0.0,
                 iterations=240, depth=6, l2_leaf_reg=5.0,
                 random_strength=1.0, cat_feature_mode="native",
                 year_weighting="none", random_state=42, thread_count=3):
        self.kind = kind
        self.alpha = alpha
        self.trend_scale = trend_scale
        self.max_iter = max_iter
        self.max_leaf_nodes = max_leaf_nodes
        self.min_samples_leaf = min_samples_leaf
        self.learning_rate = learning_rate
        self.l2_regularization = l2_regularization
        self.iterations = iterations
        self.depth = depth
        self.l2_leaf_reg = l2_leaf_reg
        self.random_strength = random_strength
        self.cat_feature_mode = cat_feature_mode
        self.year_weighting = year_weighting
        self.random_state = random_state
        self.thread_count = thread_count

    def fit(self, X, y):
        raise NotImplementedError("Сохранённая модель уже обучена; переобучение в приложении отключено.")

    def predict(self, X):
        check_is_fitted(self, "is_fitted_")
        X = X.copy().reset_index(drop=True)
        records = [record_features(row, self.support_, self.with_time_, self.trend_scale)
                   for row in X[FEATURE_COLS].to_dict("records")]
        log_price_per_sqm = self.model_.predict(self.vectorizer_.transform(records))
        prices = np.exp(log_price_per_sqm) * X["area"].to_numpy(dtype=float)
        if not np.isfinite(prices).all():
            raise ValueError("Модель вернула некорректную цену квартиры.")
        return prices


# The serialized estimator identifies this class as __main__.ApartmentEstimator.
# Register it before loading the model bundle.
setattr(sys.modules["__main__"], "ApartmentEstimator", ApartmentEstimator)

MODEL_BUNDLE_PATH = BASE_DIR / "Prognosis_model.joblib"


def _prepare_model_data(df: pd.DataFrame) -> pd.DataFrame:
    model_source = df.copy()
    model_source["price_per_sqm"] = model_source["price"] / model_source["area"]
    for col in ["price", "price_per_sqm"]:
        mean, std = model_source[col].mean(), model_source[col].std()
        model_source = model_source[(model_source[col] >= mean - 3 * std) & (model_source[col] <= mean + 3 * std)].copy()
    model_df = model_source.copy()
    model_df["_source_id"] = model_df.index.astype(int)
    for col in CATEGORICAL_COLS:
        model_df[col] = model_df[col].map(normalize_text)
    model_df["wall_material_code"] = model_df["wall_material_code"].str.replace(r"\.0+$", "", regex=True)
    for col in NUMERIC_COLS + ["price"]:
        model_df[col] = pd.to_numeric(model_df[col], errors="coerce")
    model_df = model_df.dropna(subset=NUMERIC_COLS + ["price", "period_year"]).copy()
    model_df = model_df[
        model_df["period_year"].between(2023, 2026)
        & model_df["year_build"].between(1800, 2027)
        & (model_df["year_build"] <= model_df["period_year"] + 1)
        & model_df["floor"].between(1, 100)
        & model_df["area"].between(25, 400)
        & model_df["price"].between(7_000_000, 1_000_000_000)
    ].copy()
    model_df["price_per_sqm"] = model_df["price"] / model_df["area"]
    model_df = model_df[model_df["price_per_sqm"].between(50_000, 15_000_000)].copy()
    model_df["period_year"] = model_df["period_year"].astype(int)
    return model_df.sort_values("period_start_date").reset_index(drop=True)


class PrognosisModel:
    """Adapter from the trained model bundle to the forecasting API."""

    def __init__(self, bundle: dict, model_df: pd.DataFrame, annual_market: pd.DataFrame):
        required = {"price_model", "trend_model", "base_year"}
        missing = required.difference(bundle)
        if missing:
            raise ValueError(f"В файле модели отсутствуют обязательные поля: {sorted(missing)}")
        self.bundle = bundle
        self.price_model = bundle["price_model"]
        self.trend_model = bundle["trend_model"]
        self.selected_model = bundle.get("selected_model", "CatBoost")
        self.model_df = model_df
        self.annual_market = annual_market
        self.base_year = int(bundle["base_year"])
        self.region_price_coef = region_price_coef_from(model_df)
        self.avg_inflation_level = float(
            annual_market.attrs.get("avg_inflation_level", MIN_INFLATION_PCT)
        )

    def _apartment_row(self, apartment: dict, year: int) -> pd.DataFrame:
        row = {col: normalize_text(apartment[col]) for col in CATEGORICAL_COLS}
        row["wall_material_code"] = re.sub(r"\.0+$", "", row["wall_material_code"])
        row.update({col: float(apartment[col]) for col in NUMERIC_COLS})
        row["period_year"] = int(year)
        if not (25 <= row["area"] <= 400 and 1 <= row["floor"] <= 100
                and 1800 <= row["year_build"] <= year + 1):
            raise ValueError("Параметры квартиры выходят за границы обучающей выборки модели.")
        return pd.DataFrame([row])[FEATURE_COLS]

    def forecast(self, apartment: dict, n_years: int) -> dict:
        years = list(range(self.base_year, self.base_year + int(n_years) + 1))
        model_prices = [
            float(self.trend_model.predict(self._apartment_row(apartment, year))[0])
            for year in years[:2]
        ]
        if not np.isfinite(model_prices).all() or any(price <= 0 for price in model_prices):
            raise ValueError("Модель вернула некорректную последовательность цен.")
        prices = [model_prices[0], model_prices[1]]
        first_growth = (model_prices[1] / model_prices[0] - 1) * 100
        annual_growth = [0.0, first_growth]

        # Preserve the apartment-specific first-year growth, then converge future
        # yearly rates toward the observed market inflation level.
        target_growth = float(
            np.clip(self.avg_inflation_level, MIN_INFLATION_PCT, MAX_INFLATION_PCT)
        )
        current_growth = first_growth
        for _year in years[2:]:
            difference = current_growth - target_growth
            if abs(difference) <= 1e-12:
                current_growth = target_growth
            else:
                step = min(
                    max(abs(difference) * INFLATION_CONVERGENCE, MIN_INFLATION_STEP_PP),
                    abs(difference),
                )
                current_growth -= np.copysign(step, difference)
            annual_growth.append(float(current_growth))
            prices.append(prices[-1] * (1 + current_growth / 100.0))
        forecast_df = pd.DataFrame({
            "Год": years,
            "Прогноз цены, млн руб.": [round(price / 1_000_000, 2) for price in prices],
            "Инфляция, %": [round(value, 1) for value in annual_growth],
        })
        return {
            "forecast": forecast_df,
            "forecast_exact": [
                {"year": year, "price_mln": price / 1_000_000, "inflation_pct": growth}
                for year, price, growth in zip(years, prices, annual_growth)
            ],
            "base_price": prices[0],
            "coef_region": float(self.region_price_coef.get(normalize_text(apartment["region"]), 1.0)),
            "growth_source": "динамическая Ridge-модель",
            "base_year": self.base_year,
            "avg_inflation_level": self.avg_inflation_level,
            "infl_first": annual_growth[1] if len(annual_growth) > 1 else None,
            "infl_last": annual_growth[-1] if len(annual_growth) > 1 else None,
        }


def train_model() -> PrognosisModel:
    """Load the trained CatBoost and dynamic Ridge models from the saved bundle."""
    if not MODEL_BUNDLE_PATH.exists():
        raise FileNotFoundError(f"Файл обученной модели не найден: {MODEL_BUNDLE_PATH}")
    df_raw = read_csv_robust(DATA_PATH)
    df_raw.columns = df_raw.columns.astype(str).str.strip().str.lower()
    model_df = _prepare_model_data(clean_data(df_raw))
    if model_df.empty or model_df["period_year"].max() < 2026:
        raise ValueError("Для модели нужны очищенные сделки за 2026 год.")
    bundle = joblib.load(MODEL_BUNDLE_PATH)
    annual_market = compute_annual_market(df_raw)
    return PrognosisModel(bundle, model_df, annual_market)



def train_model_cached() -> PrognosisModel:
    """Загружает сохранённую обученную модель без переобучения на старой схеме."""
    return train_model()

def _official_district_streets(df_raw: pd.DataFrame, region: str,
                               district: str) -> list[str]:
    """Улицы официального района из строк датасета с учётом вариантов написания."""
    aliases = [district] + DISTRICT_DATASET_ALIASES.get(district, [])
    mask = (
        (df_raw["region"].astype(str) == region)
        & (df_raw["district"].astype(str).isin(aliases))
    )
    streets = df_raw.loc[mask, "street"].dropna().astype(str).str.strip()
    return sorted({street for street in streets if street})


def load_reference_data() -> dict:
    """Списки округов, районов и улиц для выпадающих списков/подсказок.

    Дополнительно возвращает иерархию «округ → районы» и «район → улицы»,
    чтобы форма могла показывать в поле «Район» только районы выбранного
    округа, а в поле «Улица» — только улицы выбранного района.

    Районы берутся из OFFICIAL_DISTRICTS — это единственный источник
    значений для формы и ИИ-помощника. Районы датасета, которых нет в
    официальном списке, пользователю не показываются.
    """
    df_raw = read_csv_robust(DATA_PATH)
    df_raw.columns = df_raw.columns.astype(str).str.strip().str.lower()

    regions = sorted(
        set(df_raw["region"].dropna().astype(str).unique().tolist())
        | set(OFFICIAL_DISTRICTS)
    )
    streets = sorted(df_raw["street"].dropna().astype(str).unique().tolist())

    # Официальные районы — единственный источник для выпадающего списка.
    region_districts: dict[str, list[str]] = {
        region: list(districts)
        for region, districts in OFFICIAL_DISTRICTS.items()
    }

    # Иерархия из датасета: район -> улицы
    district_streets: dict[str, list[str]] = {}
    for district, group in df_raw.groupby("district"):
        district_streets[str(district)] = sorted(
            group["street"].dropna().astype(str).unique().tolist()
        )

    # Для официальных районов собираем улицы из всех вариантов написания.
    for region, official_districts in OFFICIAL_DISTRICTS.items():
        for district in official_districts:
            district_streets[district] = _official_district_streets(
                df_raw, region, district
            )

    districts = sorted(
        {district for items in OFFICIAL_DISTRICTS.values() for district in items}
    )

    return {
        "regions": regions,
        "districts": districts,
        "streets": streets,
        "region_districts": region_districts,
        "district_streets": district_streets,
        "wall_materials": list(WALL_MATERIAL_NAMES.values()),
        "region_names": REGION_NAMES,
        "region_aliases": REGION_ALIASES,
        "district_aliases": DISTRICT_DATASET_ALIASES,
        "wall_material_aliases": WALL_MATERIAL_ALIASES,
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
