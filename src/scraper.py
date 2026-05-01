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

import time
import random
import re
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import os
import time


CACHE_PATH = Path(__file__).resolve().parent.parent / "data" / "raw" / "hotels_cache.csv"



# Cache

def _load_cache() -> pd.DataFrame:
    if CACHE_PATH.exists():
        return pd.read_csv(CACHE_PATH)
    return pd.DataFrame()


def _save_cache(df: pd.DataFrame) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(CACHE_PATH, index=False)



# Driver

def get_driver(headless: bool = True) -> webdriver.Chrome:
    options = Options()
    if headless:
        options.add_argument("--headless=new")
    
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    
    try:
        service = Service() 
        driver = webdriver.Chrome(service=service, options=options)
    except Exception as e:
        print(f"Erreur au lancement du driver : {e}")
        # Si ça échoue encore, on tente de forcer le chemin (si tu as installé chromedriver manuellement)
        # service = Service("/usr/bin/chromedriver") 
        # driver = webdriver.Chrome(service=service, options=options)
        raise e

    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    return driver

# URL

# Dans scraper.py
def build_booking_url(city: str) -> str:
    # URL ultra-simple : juste la ville et la langue
    return f"https://www.booking.com/searchresults.fr.html?ss={city.replace(' ', '+')}&lang=fr"



def _scrape_city(driver, city: str, city_id: int, max_hotels: int) -> list:
    # Paramètres de recherche fixés selon tes critères
    adults, children, rooms = 1, 0, 1
    checkin, checkout = "2026-07-10", "2026-07-12"
    
    url = (
        f"https://www.booking.com/searchresults.fr.html?ss={city}"
        f"&checkin={checkin}&checkout={checkout}"
        f"&group_adults={adults}&no_rooms={rooms}&group_children={children}"
        f"&lang=fr"
    )
    
    driver.get(url)
    time.sleep(5) 

    # Fermeture du pop-up si présent
    try:
        driver.find_element(By.CSS_SELECTOR, 'button[aria-label="Ignorer les informations de connexion"]').click()
    except:
        pass

    cards = driver.find_elements(By.CSS_SELECTOR, '[data-testid="property-card"]')
    hotels = []

    for card in cards[:max_hotels]:
        try:
            raw_text = card.text
            name = raw_text.split('\n')[0]

            # Score
            score = None
            score_match = re.search(r"(\d[.,]\d)", raw_text)
            if score_match:
                score = float(score_match.group(1).replace(",", "."))

            # Distance
            distance = None
            try:
                distance = card.find_element(By.CSS_SELECTOR, '[data-testid="distance"]').text
            except:
                dist_match = re.search(r"(\d+[.,]?\d*\s?k?m)\s?du centre", raw_text)
                if dist_match: distance = dist_match.group(1)

            # Prix (Sélecteurs robustes)
            price = None
            price_text = ""
            for selector in ['span.b87c397a13.f2f358d1de', '[data-testid="price-and-discounted-price"]']:
                try:
                    el = card.find_element(By.CSS_SELECTOR, selector)
                    if el.is_displayed():
                        price_text = el.text
                        break
                except:
                    continue

            if price_text:
                nums = re.findall(r"\d+", price_text.replace("\xa0", "").replace(" ", ""))
                if nums: price = int("".join(nums))

            hotels.append({
                "city_id": city_id,
                "city": city,
                "hotel_name": name,
                "score": score,
                "distance": distance,
                "price_eur": price
            })
        except:
            continue
            
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
    
    cache_path = "data/raw/hotels_cache.csv"
    
    # Gestion du cache
    if not force_refresh and os.path.exists(cache_path):
        print("Chargement des données depuis le cache...")
        return pd.read_csv(cache_path)

    driver = get_driver(headless=headless)
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
            
            # Pause aléatoire pour éviter le ban
            time.sleep(random.uniform(*delay_range))

    finally:
        driver.quit()

    df_result = pd.DataFrame(all_hotels)
    
    # Sauvegarde
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    df_result.to_csv(cache_path, index=False)
    print(f"\nTerminé ! {len(df_result)} hôtels sauvegardés dans {cache_path}")
    
    return df_result