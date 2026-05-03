"""
db_utils.py — Connexion et chargement vers AWS RDS PostgreSQL

Schéma en étoile :
- cities (dimension) : coordonnées, score météo, ranking
- hotels (fait)      : hôtels scrapés, reliés à cities via city_id FK
"""

import os
import pandas as pd
from sqlalchemy import create_engine, text


def get_engine():
    """
    Crée un engine SQLAlchemy vers RDS PostgreSQL
    depuis les variables d'environnement.
    """
    host     = os.getenv("RDS_HOST")
    port     = os.getenv("RDS_PORT", "5432")
    db       = os.getenv("RDS_DB")
    user     = os.getenv("RDS_USER")
    password = os.getenv("RDS_PASSWORD")

    url = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db}"
    return create_engine(url)


def create_tables(engine) -> None:
    """
    Crée les tables cities et hotels dans RDS si elles n'existent pas.

    Schéma en étoile :
    - cities  : table de dimension (1 ligne par ville)
    - hotels  : table de faits (N lignes par ville via city_id FK)
    """
    sql = """
        CREATE TABLE IF NOT EXISTS cities (
            city_id       INTEGER PRIMARY KEY,
            city          VARCHAR(100) NOT NULL,
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

        CREATE TABLE IF NOT EXISTS hotels (
            id            SERIAL PRIMARY KEY,
            city_id       INTEGER REFERENCES cities(city_id),
            city          VARCHAR(100),
            hotel_name    VARCHAR(255),
            url           TEXT,
            score         FLOAT,
            distance      VARCHAR(50),
            price_eur     INTEGER,
            lat           FLOAT,
            lon           FLOAT,
            description   TEXT
        );
    """
    with engine.connect() as conn:
        conn.execute(text(sql))
        conn.commit()
    print("  Tables créées (ou déjà existantes)")


def load_df_to_table(df: pd.DataFrame, table: str, engine) -> None:
    """
    Vide et recharge une table sans jamais la supprimer.
    TRUNCATE CASCADE + INSERT via SQLAlchemy Core.

    Paramètres
    ----------
    df     : DataFrame à charger
    table  : nom de la table cible
    engine : engine SQLAlchemy
    """
    with engine.connect() as conn:
        conn.execute(text(f"TRUNCATE TABLE {table} CASCADE"))

        rows = df.to_dict(orient="records")
        if rows:
            cols   = ", ".join(rows[0].keys())
            vals   = ", ".join([f":{k}" for k in rows[0].keys()])
            insert = text(f"INSERT INTO {table} ({cols}) VALUES ({vals})")
            conn.execute(insert, rows)

        conn.commit()
    print(f"  Chargé → table '{table}' ({len(df)} lignes)")


def run_query(query: str, engine) -> pd.DataFrame:
    """
    Exécute une requête SQL et retourne un DataFrame.

    Paramètres
    ----------
    query  : requête SQL en string
    engine : engine SQLAlchemy
    """
    with engine.connect() as conn:
        return pd.read_sql(text(query), conn)