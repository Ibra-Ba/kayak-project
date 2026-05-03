"""
weather.py — Prévisions météo via OpenWeatherMap One Call API 3.0
avec cache local par date de collecte.

Comportement :
- Si un cache du jour existe → lecture directe, zéro appel API
- Sinon → appel OWM pour toutes les villes, cache sauvegardé
"""

import time
import requests
import pandas as pd
from pathlib import Path
from datetime import date

OWM_URL    = OWM_URL = "https://api.openweathermap.org/data/3.0/onecall"
CACHE_DIR  = Path(__file__).resolve().parent.parent / "data" / "raw"


def _cache_path() -> Path:
    """
    Chemin du cache météo du jour.
    Ex : data/raw/weather_cache_2025-04-30.csv
    Chaque jour de collecte génère son propre fichier.
    """
    return CACHE_DIR / f"weather_cache_{date.today()}.csv"


def _call_owm(lat: float, lon: float, api_key: str) -> list:
    """Appel API OWM pour un point GPS. Retourne la liste des jours (daily)."""
    params = {
        "lat":     lat,
        "lon":     lon,
        "exclude": "current,minutely,hourly,alerts",
        "units":   "metric",
        "appid":   api_key
    }
    response = requests.get(OWM_URL, params=params)
    response.raise_for_status()
    return response.json().get("daily", [])


def collect_weather_data(df_cities: pd.DataFrame, api_key: str, delay: float = 0.5) -> pd.DataFrame:
    """
    Collecte les prévisions météo 7 jours pour toutes les villes.

    - Si le cache du jour existe → retourné directement
    - Sinon → appels OWM + sauvegarde cache

    Paramètres
    ----------
    df_cities : DataFrame avec colonnes city_id, city, lat, lon
    api_key   : clé OWM
    delay     : délai entre requêtes en secondes

    Retourne
    --------
    DataFrame avec une ligne par ville par jour (35 villes × 7 jours = 245 lignes)
    """
    cache_file = _cache_path()

    if cache_file.exists():
        print(f"  Cache météo du jour trouvé → {cache_file.name}")
        return pd.read_csv(cache_file)

    print(f"  Pas de cache — appel OWM pour {len(df_cities)} villes...")
    rows = []

    for _, row in df_cities.iterrows():
        if row["lat"] is None:
            continue

        daily = _call_owm(row["lat"], row["lon"], api_key)

        for day in daily:
            rows.append({
                "city_id":      row["city_id"],
                "city":         row["city"],
                "lat":          row["lat"],
                "lon":          row["lon"],
                "date":         pd.to_datetime(day["dt"], unit="s").date(),
                "temp_day":     day["temp"]["day"],
                "temp_min":     day["temp"]["min"],
                "temp_max":     day["temp"]["max"],
                "humidity":     day["humidity"],
                "pop":          day.get("pop", 0),
                "rain_mm":      day.get("rain", 0),
                "weather_main": day["weather"][0]["main"],
                "weather_desc": day["weather"][0]["description"]
            })

        print(f"    OK {row['city']}")
        time.sleep(delay)

    df = pd.DataFrame(rows)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(cache_file, index=False)
    print(f"  Cache sauvegardé : {cache_file.name} ({len(df)} lignes)")
    return df


def compute_weather_score(df_weather: pd.DataFrame) -> pd.DataFrame:
    """
    Agrège les 7 jours et calcule un score météo par ville.

    Formule : score = temp_moy - (pop_moy × 10) - (rain_total × 0.5)
    Modifiable selon  critères choisis dans ce fichier.

    Retourne
    --------
    DataFrame une ligne par ville, triée par score décroissant.
    """
    df_score = (
        df_weather
        .groupby(["city_id", "city", "lat", "lon"])
        .agg(
            temp_moy   =("temp_day", "mean"),
            temp_max   =("temp_max", "max"),
            pop_moy    =("pop",      "mean"),
            rain_total =("rain_mm",  "sum"),
            humidity   =("humidity", "mean")
        )
        .reset_index()
    )

    df_score["weather_score"] = (
        df_score["temp_moy"]
        - df_score["pop_moy"] * 10
        - df_score["rain_total"] * 0.5
    ).round(2)

    df_score = (
        df_score
        .sort_values("weather_score", ascending=False)
        .reset_index(drop=True)
    )
    df_score["rank"] = df_score.index + 1

    return df_score