"""
weather.py — Prévisions météo via OpenWeatherMap One Call API
Documentation : https://openweathermap.org/api/one-call-api

Nécessite une clé API gratuite : https://openweathermap.org/appid
"""

import time
import requests
import pandas as pd
import os



OWM_URL = "https://api.openweathermap.org/data/3.0/onecall"

def get_weather(lat: float, lon: float, api_key: str) -> list:
    """
    Retourne les prévisions daily (7 jours) pour un point GPS.
    """
    # 3. Validation de la clé API pour éviter une erreur obscure plus tard
    if not api_key:
        raise ValueError("La clé API OWM_API_KEY est manquante. Vérifie ton fichier .env")

    params = {
        "lat": lat,
        "lon": lon,
        "exclude": "current,minutely,hourly,alerts",
        "units": "metric",
        "appid": api_key
    }
    response = requests.get(OWM_URL, params=params)
    response.raise_for_status()
    
    return response.json().get("daily", [])


def collect_weather_data(df_cities: pd.DataFrame, api_key: str, delay: float = 0.5) -> pd.DataFrame:
    """
    Collecte les prévisions météo pour toutes les villes du DataFrame.

    Paramètres
    ----------
    df_cities : DataFrame avec colonnes city_id, city, lat, lon
    api_key   : clé OWM
    delay     : délai entre requêtes en secondes

    Retourne
    --------
    DataFrame avec une ligne par ville par jour (7 jours × 35 villes = 245 lignes)
    """
    rows = []
    for _, row in df_cities.iterrows():
        if row["lat"] is None:
            continue

        daily = get_weather(row["lat"], row["lon"], api_key)

        for day in daily:
            rows.append({
                "city_id":       row["city_id"],
                "city":          row["city"],
                "lat":           row["lat"],
                "lon":           row["lon"],
                "date":          pd.to_datetime(day["dt"], unit="s").date(),
                "temp_day":      day["temp"]["day"],
                "temp_min":      day["temp"]["min"],
                "temp_max":      day["temp"]["max"],
                "humidity":      day["humidity"],
                "pop":           day.get("pop", 0),
                "rain_mm":       day.get("rain", 0),
                "weather_main":  day["weather"][0]["main"],
                "weather_desc":  day["weather"][0]["description"]
            })

        time.sleep(delay)

    return pd.DataFrame(rows)


def compute_weather_score(df_weather: pd.DataFrame) -> pd.DataFrame:
    """
    Agrège les 7 jours de prévisions et calcule un score météo par ville.

    Formule (modifiable) :
        score = temp_moy - (pop_moy × 10) - (rain_total × 0.5)

    Plus la température est haute et moins il pleut → score élevé.

    Retourne
    --------
    DataFrame avec une ligne par ville, triée par score décroissant.
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

    df_score = df_score.sort_values("weather_score", ascending=False).reset_index(drop=True)
    df_score["rank"] = df_score.index + 1

    return df_score