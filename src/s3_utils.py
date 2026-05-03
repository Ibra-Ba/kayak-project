"""
s3_utils.py — Upload et lecture de fichiers CSV vers/depuis Amazon S3
"""

import boto3
import pandas as pd
from pathlib import Path
from io import StringIO
import os


def get_s3_client():
    """Crée un client S3 depuis les variables d'environnement."""
    return boto3.client(
        "s3",
        aws_access_key_id     = os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key = os.getenv("AWS_SECRET_ACCESS_KEY"),
        region_name           = os.getenv("AWS_REGION", "eu-west-3")
    )


def upload_df_to_s3(df: pd.DataFrame, bucket: str, key: str) -> None:
    """
    Upload un DataFrame pandas vers S3 au format CSV.

    Paramètres
    ----------
    df     : DataFrame à uploader
    bucket : nom du bucket S3
    key    : chemin dans le bucket (ex. "raw/cities.csv")
    """
    client = get_s3_client()
    buffer = StringIO()
    df.to_csv(buffer, index=False)
    client.put_object(Bucket=bucket, Key=key, Body=buffer.getvalue())
    print(f"  Uploadé → s3://{bucket}/{key} ({len(df)} lignes)")


def read_df_from_s3(bucket: str, key: str) -> pd.DataFrame:
    """
    Lit un fichier CSV depuis S3 et retourne un DataFrame.

    Paramètres
    ----------
    bucket : nom du bucket S3
    key    : chemin dans le bucket (ex. "raw/cities.csv")
    """
    client   = get_s3_client()
    response = client.get_object(Bucket=bucket, Key=key)
    content  = response["Body"].read().decode("utf-8")
    df       = pd.read_csv(StringIO(content))
    print(f"  Lu depuis s3://{bucket}/{key} → {df.shape}")
    return df


def list_s3_files(bucket: str, prefix: str = "") -> list:
    """Liste les fichiers d'un bucket S3 sous un préfixe donné."""
    client   = get_s3_client()
    response = client.list_objects_v2(Bucket=bucket, Prefix=prefix)
    files    = [obj["Key"] for obj in response.get("Contents", [])]
    return files