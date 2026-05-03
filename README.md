# 🗺️ Tourisme France — Pipeline de données
  
Collecte, stockage et analyse des données météo et hôtelières pour les **35 villes françaises** les plus visitées.

---

## Objectif

Construire un pipeline de données complet permettant d'identifier les **meilleures destinations touristiques françaises** selon la météo et de localiser les **meilleurs hôtels** dans ces destinations.

**Livrable final :**
- Un Data Lake S3 contenant les données brutes
- Un Data Warehouse RDS PostgreSQL contenant les données nettoyées
- Deux visualisations cartographiques interactives (Top 5 destinations + Top 20 hôtels)

---

##  Architecture

```
Sources                  Ingestion              Data Lake         ETL              Data Warehouse
─────────────────────────────────────────────────────────────────────────────────────────────────
OpenWeatherMap API  ──►  Notebook 01  ──────►  S3 raw/       ──► Notebook 03  ──► RDS PostgreSQL
Nominatim API       ──►  (pandas)               cities.csv                         table: cities
                                                                                   table: hotels
Booking.com         ──►  Notebook 02  ──────►  S3 raw/
(Selenium + BS4)         (selenium)              hotels.csv
```

### Justification scalabilité

Pour un passage à l'échelle (10 000+ villes mondiales) :

| Composant | Projet (35 villes) | Version scalable |
|---|---|---|
| Traitement | pandas (RAM unique) | PySpark sur AWS EMR |
| Stockage lake | CSV | Parquet partitionné |
| Data Warehouse | RDS PostgreSQL | AWS Redshift (MPP) |
| Collecte | Scripts séquentiels | concurrent.futures / Spark |

S3 reste le pivot des deux niveaux — seul le moteur de traitement change.

---

## Structure du projet

```
tourisme-france/
│
├── .env                          # Credentials (jamais commité)
├── .env.example                  # Template de configuration
├── .gitignore
├── environment.yml               # Environnement Conda reproductible
├── README.md
│
├── data/
│   ├── raw/                      # Données brutes locales (gitignorées)
│   │   ├── coords_cache.csv      # Coordonnées GPS des 35 villes (cache Nominatim)
│   │   ├── weather_cache_YYYY-MM-DD.csv  # Prévisions météo (cache OWM, par date)
│   │   ├── cities.csv            # Scores météo + ranking
│   │   ├── hotels_cache.csv      # Données hôtels brutes (cache scraping)
│   │   └── hotels.csv            # Données hôtels nettoyées
│   └── processed/                # Données transformées (gitignorées)
│
├── notebooks/
│   ├── 01_weather_collection.ipynb   # Collecte météo
│   ├── 02_booking_scraping.ipynb     # Scraping Booking.com
│   └── 03_etl_s3_to_rds.ipynb       # ETL + visualisations
│
└── src/                          # Modules Python réutilisables
    ├── __init__.py
    ├── nominatim.py              # Coordonnées GPS + cache local
    ├── weather.py                # Collecte OWM + score météo + cache
    ├── scraper.py                # Selenium + BeautifulSoup
    ├── s3_utils.py               # Upload/lecture S3
    └── db_utils.py               # Connexion RDS + création tables + chargement
```

---

## ⚙️ Installation

### Prérequis
- WSL2 / Ubuntu
- Miniforge (conda)
- Google Chrome installé dans WSL2
- Compte AWS (S3 + RDS)
- Clé API OpenWeatherMap (gratuite)
- 

### 1. Cloner le projet

```bash
git clone https://github.com/ton-user/tourisme-france.git
cd tourisme-france
```

### 2. Créer l'environnement Conda

```bash
conda env create -f environment.yml
conda activate tourisme-france
python -m ipykernel install --user --name tourisme-france --display-name "Python 3 (tourisme-france)"
```

### 3. Installer Chrome dans WSL2

```bash
wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | sudo apt-key add -
echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" | sudo tee /etc/apt/sources.list.d/google-chrome.list
sudo apt update && sudo apt install -y google-chrome-stable
```

### 4. Configurer les credentials

```bash
cp .env.example .env
# Remplir .env avec vos clés API et credentials AWS
```

### 5. Ouvrir dans VSCode

```bash
code .
```

Sélectionner le kernel **"Python 3 (tourisme-france)"** dans chaque notebook.

---

## 🚀 Exécution

Lancer les notebooks dans l'ordre :

### Notebook 01 — Collecte météo
```
Input  : liste des 35 villes (hardcodée)
Output : data/raw/cities.csv
Durée  : ~35s (cache Nominatim) + ~20s (OWM)
```
- Récupère les coordonnées GPS via **Nominatim** (cache local)
- Collecte les prévisions 7 jours via **OpenWeatherMap** (cache par date)
- Calcule un score météo : `temp_moy - (pop_moy × 10) - (rain_total × 0.5)`
- Génère la carte Top 5 destinations

### Notebook 02 — Scraping Booking.com
```
Input  : data/raw/cities.csv
Output : data/raw/hotels.csv
Durée  : ~30-45 minutes (visite page individuelle par hôtel)
```
- Scrape Booking.com avec **Selenium** (Chrome headless) + **BeautifulSoup**
- Collecte : nom, URL, score, distance, prix, coordonnées GPS, description
- Cache local pour éviter de re-scraper à chaque exécution

### Notebook 03 — ETL + Visualisations
```
Input  : data/raw/cities.csv + data/raw/hotels.csv
Output : S3 bucket + RDS PostgreSQL
Durée  : ~2 minutes
```
- **Extract** : lecture des CSV locaux
- **Transform** : nettoyage, typage, imputation des valeurs manquantes
- **Load** : upload S3 (Data Lake) + chargement RDS (Data Warehouse)
- Génère les cartes Plotly finales

---

## 🗄️ Schéma de la base de données

```sql
-- Dimension : une ligne par ville
CREATE TABLE cities (
    city_id       INTEGER PRIMARY KEY,
    city          VARCHAR(100),
    lat           FLOAT,
    lon           FLOAT,
    temp_moy      FLOAT,
    temp_max      FLOAT,
    pop_moy       FLOAT,
    rain_total    FLOAT,
    humidity      FLOAT,
    weather_score FLOAT,
    rank          INTEGER
);

-- Faits : N hôtels par ville
CREATE TABLE hotels (
    id          SERIAL PRIMARY KEY,
    city_id     INTEGER REFERENCES cities(city_id),
    city        VARCHAR(100),
    hotel_name  VARCHAR(255),
    url         TEXT,
    score       FLOAT,
    distance    VARCHAR(50),
    price_eur   INTEGER,
    lat         FLOAT,
    lon         FLOAT,
    description TEXT
);
```

---

## 🔒 RGPD & Éthique

- **Données publiques uniquement** : nom, score, coordonnées et description affichés publiquement sur Booking.com
- **Aucune donnée personnelle** d'utilisateur collectée ou stockée
- **Robots.txt respecté** : délais aléatoires entre requêtes (2-4s)
- **Nominatim CGU** : User-Agent identifiant l'application + délai 1s entre requêtes
- **Credentials** jamais commités (`.env` dans `.gitignore`)

---

## 📦 Dépendances principales

| Librairie | Usage |
|---|---|
| requests | Appels API Nominatim + OWM |
| pandas | Manipulation des DataFrames |
| selenium | Scraping Booking.com (Chrome headless) |
| beautifulsoup4 | Parsing HTML |
| boto3 | Upload/lecture S3 |
| sqlalchemy | Connexion RDS PostgreSQL |
| psycopg2-binary | Driver PostgreSQL |
| plotly | Visualisations cartographiques |
| python-dotenv | Chargement variables d'environnement |
| psql | connection à la db et query sur terminal