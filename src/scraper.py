"""
scraper.py — Scraping Booking.com avec Selenium + BeautifulSoup

Pourquoi Selenium ?
- Booking.com bloque les crawlers HTTP classiques (Scrapy, requests)
- Selenium pilote un vrai Chrome → indiscernable d'un utilisateur humain
- BeautifulSoup parse le HTML une fois la page chargée

Cache local :
- Si hotels_cache.csv existe → lecture directe
- Sinon → scraping + sauvegarde

RGPD : uniquement des données publiques (nom, score, coordonnées, description).
Aucune donnée personnelle d'utilisateur collectée.
"""

import json
import os
import random
import re
import time
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By

CACHE_PATH = Path(__file__).resolve().parent.parent / "data" / "raw" / "hotels_cache.csv"


# ──────────────────────────────────────────────
# Cache
# ──────────────────────────────────────────────

def _load_cache() -> pd.DataFrame:
    if CACHE_PATH.exists():
        return pd.read_csv(CACHE_PATH)
    return pd.DataFrame()


def _save_cache(df: pd.DataFrame) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(CACHE_PATH, index=False)


# ──────────────────────────────────────────────
# Driver
# ──────────────────────────────────────────────

def get_driver(headless: bool = True) -> webdriver.Chrome:
    """Crée un driver Chrome configuré pour minimiser la détection."""
    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    )
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    service = Service()
    driver  = webdriver.Chrome(service=service, options=options)
    driver.execute_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    return driver


# ──────────────────────────────────────────────
# Détails d'un hôtel (page individuelle)
# ──────────────────────────────────────────────

def get_hotel_details(driver, url: str) -> dict:
    """
    Visite la page individuelle d'un hôtel pour récupérer
    coordonnées GPS et description.

    Retourne dict : {lat, lon, description}
    """
    result = {"lat": None, "lon": None, "description": None}

    if not url:
        return result

    driver.get(url)
    time.sleep(random.uniform(2, 3))

    soup     = BeautifulSoup(driver.page_source, "lxml")
    html_raw = str(soup)

    # ── Coordonnées GPS depuis le HTML brut ──
    lat_match = re.search(r'"latitude"\s*:\s*([-\d.]+)', html_raw)
    lon_match = re.search(r'"longitude"\s*:\s*([-\d.]+)', html_raw)
    if lat_match and lon_match:
        try:
            result["lat"] = float(lat_match.group(1))
            result["lon"] = float(lon_match.group(1))
        except ValueError:
            pass

    # ── Description depuis JSON-LD ──
    for script in soup.select('script[type="application/ld+json"]'):
        if not script.string:
            continue
        try:
            data = json.loads(script.string)
            if isinstance(data, list):
                data = data[0]
            desc = data.get("description")
            if desc:
                result["description"] = desc[:500]
                break
        except (json.JSONDecodeError, KeyError, IndexError):
            continue

    return result


# ──────────────────────────────────────────────
# Helpers extraction carte hôtel
# ──────────────────────────────────────────────

def _extract_hotel_url(card) -> str | None:
    """Extrait l'URL de la page hôtel depuis une carte de résultats."""
    link = card.select_one('a[data-testid="title-link"]')
    if not link:
        return None
    href = link.get("href", "")
    if not href:
        return None
    if not href.startswith("http"):
        href = "https://www.booking.com" + href
    return href



def _extract_score(card) -> float | None:

    selectors = [
        "p.review_score_value",
        '[data-testid="review-score"]',
        '[data-testid="review-score-right-component"]'
    ]

    for selector in selectors:

        score_el = card.select_one(selector)

        if not score_el:
            continue

        match = re.search(
            r"(\d+[.,]\d+)",
            score_el.get_text(" ", strip=True)
        )

        if match:
            try:
                return float(
                    match.group(1).replace(",", ".")
                )
            except ValueError:
                pass

    return None


def _extract_review_count(card) -> int | None:

    text = card.get_text(" ", strip=True)

    patterns = [
        r'([\d\s\u202f]+)\s+expériences vécues',
        r'([\d\s\u202f]+)\s+avis',
        r'([\d\s\u202f]+)\s+reviews'
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            text,
            re.IGNORECASE
        )

        if match:
            try:
                return int(
                    match.group(1)
                    .replace(" ", "")
                    .replace("\u202f", "")
                )
            except ValueError:
                pass

    return None


def _extract_distance(card, raw_text: str) -> str | None:
    """Extrait la distance au centre depuis une carte."""
    dist_el = card.select_one('[data-testid="distance"]')
    if dist_el:
        return dist_el.get_text(strip=True)
    match = re.search(r"(\d+[.,]?\d*\s?k?m)\s?du centre", raw_text)
    if match:
        return match.group(1)
    return None


def _extract_price(card) -> int | None:
    """Extrait le prix depuis une carte hôtel."""
    for selector in [
        'span.b87c397a13.f2f358d1de',
        '[data-testid="price-and-discounted-price"]'
    ]:
        price_el = card.select_one(selector)
        if not price_el:
            continue
        nums = re.findall(
            r"\d+",
            price_el.get_text(strip=True).replace("\xa0", "").replace(" ", "")
        )
        if nums:
            try:
                return int("".join(nums))
            except ValueError:
                continue
    return None


# ──────────────────────────────────────────────
# Scraping d'une ville
# ──────────────────────────────────────────────

def _scrape_city(driver, city: str, city_id: int, max_hotels: int = None) -> list:
    """
    POC :
    Scrape uniquement les informations visibles sur la page résultats Booking.
    Aucun appel aux pages individuelles.
    """

    checkin, checkout = "2026-08-25", "2026-08-26"

    url = (
        f"https://www.booking.com/searchresults.fr.html?ss={city}"
        f"&checkin={checkin}&checkout={checkout}"
        f"&group_adults=1&no_rooms=1&group_children=0"
        f"&lang=fr"
    )

    print(f"\nScraping {city}")
    driver.get(url)
    time.sleep(5)

    try:
        btn = driver.find_element(
            By.CSS_SELECTOR,
            'button[aria-label="Ignorer les informations de connexion"]'
        )
        btn.click()
        time.sleep(1)
    except Exception:
        pass

    last_height = driver.execute_script(
    "return document.body.scrollHeight"
    )

    for i in range(15):

        driver.execute_script(
            "window.scrollTo(0, document.body.scrollHeight);"
        )

        time.sleep(3)

        new_height = driver.execute_script(
            "return document.body.scrollHeight"
        )

        print(
            f"Scroll {i+1} - hauteur={new_height}"
        )

        if new_height == last_height:
            print("Fin du chargement")
            break

        last_height = new_height

    soup = BeautifulSoup(driver.page_source, "lxml")

    cards = soup.select('[data-testid="property-card"]')

    print(f"Cartes trouvées : {len(cards)}")

    if max_hotels:
        cards = cards[:max_hotels]

    hotels = []

    for i, card in enumerate(cards, start=1):

        raw_text = card.get_text(separator="\n", strip=True)

        name = raw_text.split("\n")[0] if raw_text else None

        if not name:
            continue

        hotel_url = _extract_hotel_url(card)
        score = _extract_score(card)
        if score is None:
            continue
        review_count = _extract_review_count(card)
        distance = _extract_distance(card, raw_text)
        price_eur = _extract_price(card)

        hotels.append({
            "city_id": city_id,
            "city": city,
            "hotel_name": name,
            "url": hotel_url,
            "score": score,
            "review_count": review_count,
            "distance": distance,
            "price_eur": price_eur
        })

    df_debug = pd.DataFrame(hotels)

    print("\n=== APERCU ===")
    print(
        df_debug[
            [
                "hotel_name",
                "score",
                "review_count",
                "distance",
                "price_eur"
            ]
        ].head(20)
    )

    print("\n=== VALEURS MANQUANTES ===")
    print(df_debug.isna().sum())

    return hotels

# ──────────────────────────────────────────────
# Point d'entrée principal
# ──────────────────────────────────────────────

def scrape_all_cities(
    df_cities: pd.DataFrame,
    max_hotels_per_city: int = 20,
    headless: bool = True,
    delay_range: tuple = (2, 5),
    force_refresh: bool = False
) -> pd.DataFrame:
    """
    Scrape les hôtels de toutes les villes avec cache local.

    Paramètres
    ----------
    df_cities           : DataFrame city_id, city
    max_hotels_per_city : limite par ville
    headless            : False = Chrome visible (debug)
    delay_range         : délai aléatoire entre villes (anti-détection)
    force_refresh       : True = ignore le cache et re-scrape tout
    """
    if not force_refresh and CACHE_PATH.exists():
        print("Cache trouvé — chargement direct")
        return pd.read_csv(CACHE_PATH)

    driver     = get_driver(headless=headless)
    all_hotels = []

    try:
        for _, row in df_cities.iterrows():
            print(f"Scraping : {row['city']}...", end=" ", flush=True)
            city_hotels = _scrape_city(
                driver,
                city=row["city"],
                city_id=row["city_id"],
                max_hotels=max_hotels_per_city
            )
            all_hotels.extend(city_hotels)
            print(f"OK ({len(city_hotels)} hôtels)")
            time.sleep(random.uniform(*delay_range))
    finally:
        driver.quit()

    df_result = pd.DataFrame(all_hotels)
    _save_cache(df_result)
    print(f"\nTerminé : {len(df_result)} hôtels sauvegardés")
    return df_result


def enrich_hotels_details(
    df_hotels: pd.DataFrame,
    headless: bool = True
) -> pd.DataFrame:
    """
    Enrichit un DataFrame d'hôtels avec :
    lat, lon, description

    à partir de l'URL Booking.
    """

    driver = get_driver(headless=headless)

    try:

        details_list = []

        total = len(df_hotels)

        for i, (_, row) in enumerate(df_hotels.iterrows(), start=1):

            print(
                f"[{i}/{total}] {row['hotel_name']}",
                flush=True
            )

            details = get_hotel_details(
                driver,
                row["url"]
            )

            details_list.append(details)

            time.sleep(
                random.uniform(1, 2)
            )

    finally:
        driver.quit()

    df_details = pd.DataFrame(details_list)

    return pd.concat(
        [
            df_hotels.reset_index(drop=True),
            df_details.reset_index(drop=True)
        ],
        axis=1
    )