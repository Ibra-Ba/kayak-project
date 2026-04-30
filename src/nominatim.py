"""
nominatim.py — Coordonnées GPS via Nominatim avec cache local

Comportement :
- Si la ville est déjà dans le cache CSV → lecture directe, zéro appel API
- Si la ville est absente → appel Nominatim, résultat ajouté au cache
- Le cache s'enrichit automatiquement à chaque nouvelle ville
"""

import time
import requests
import pandas as pd
from pathlib import Path

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
HEADERS       = {"User-Agent": "TourismeFrance/1.0 (projet-bac4@formation.fr)"}
CACHE_PATH    = Path(__file__).resolve().parent.parent / "data" / "raw" / "coords_cache.csv"


def _load_cache() -> pd.DataFrame:
    """Charge le cache local. Retourne un DataFrame vide si inexistant."""
    if CACHE_PATH.exists():
        return pd.read_csv(CACHE_PATH)
    return pd.DataFrame(columns=["city_id", "city", "lat", "lon"])


def _save_cache(df: pd.DataFrame) -> None:
    """Sauvegarde le cache sur disque."""
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(CACHE_PATH, index=False)


def _call_nominatim(city_name: str) -> dict:
    """Appel API Nominatim pour une ville. Retourne dict {city, lat, lon}."""
    params = {
        "q": f"{city_name}, France",
        "format": "json",
        "limit": 1,
        "countrycodes": "fr"
    }
    response = requests.get(NOMINATIM_URL, params=params, headers=HEADERS)
    response.raise_for_status()
    results = response.json()

    if not results:
        print(f"  [WARN] Aucun résultat pour '{city_name}'")
        return {"city": city_name, "lat": None, "lon": None}

    return {
        "city": city_name,
        "lat":  float(results[0]["lat"]),
        "lon":  float(results[0]["lon"])
    }


def get_all_coordinates(cities: list, delay: float = 1.0) -> pd.DataFrame:
    """
    Retourne un DataFrame avec city_id, city, lat, lon pour toutes les villes.

    - Villes déjà dans le cache → retournées immédiatement
    - Villes manquantes         → appelées via Nominatim, ajoutées au cache

    Paramètres
    ----------
    cities : liste de noms de villes
    delay  : délai entre appels API en secondes (CGU Nominatim = 1s minimum)
    """
    cache = _load_cache()
    cached_cities  = set(cache["city"].tolist())
    missing_cities = [c for c in cities if c not in cached_cities]

    if not missing_cities:
        print(f"  Cache complet ({len(cache)} villes) — aucun appel API nécessaire")
    else:
        print(f"  {len(cached_cities)} villes en cache | {len(missing_cities)} à récupérer via Nominatim")
        new_rows = []
        for city in missing_cities:
            coords = _call_nominatim(city)
            new_rows.append(coords)
            print(f"    API → {city:25s} lat={coords['lat']}, lon={coords['lon']}")
            time.sleep(delay)

        df_new = pd.DataFrame(new_rows)
        cache  = pd.concat([cache, df_new], ignore_index=True)

        # Recalculer les city_id proprement sur l'ensemble du cache
        cache = cache.reset_index(drop=True)
        cache["city_id"] = cache.index + 1

        _save_cache(cache)
        print(f"  Cache mis à jour : {len(cache)} villes → {CACHE_PATH}")

    # Retourner uniquement les villes demandées, dans l'ordre
    df = cache[cache["city"].isin(cities)].copy()
    df = df.reset_index(drop=True)
    return df