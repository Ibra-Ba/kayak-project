"""
db_utils.py — Connexion et chargement vers AWS RDS PostgreSQL
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
    engine = create_engine(url)
    return engine


def create_tables(engine) -> None:
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
    TRUNCATE CASCADE + INSERT ligne par ligne via SQLAlchemy Core.
    """
    with engine.connect() as conn:
        # Vide la table (CASCADE propage aux tables dépendantes)
        conn.execute(text(f"TRUNCATE TABLE {table} CASCADE"))

        # Insert toutes les lignes
        rows = df.to_dict(orient="records")
        if rows:
            cols    = ", ".join(rows[0].keys())
            vals    = ", ".join([f":{k}" for k in rows[0].keys()])
            insert  = text(f"INSERT INTO {table} ({cols}) VALUES ({vals})")
            conn.execute(insert, rows)

        conn.commit()

    print(f"  Chargé → table '{table}' ({len(df)} lignes)")