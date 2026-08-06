"""
load_staging.py

Descarga el feed GTFS (ya extraído a S3/MinIO por extract_gtfs.py) y carga
cada fichero .txt tal cual a una tabla del esquema `raw` en Postgres, usando
pandas + SQLAlchemy.

Patrón ELT: este script es solo "EL" (Extract del raw layer + Load a
Postgres). NO filtra por agencia ni tipa las columnas — todo eso es
transformación (la "T"), y se hace de forma declarativa y testeable en dbt
(Fase 3). Cargar todo como texto (dtype=str) mantiene el esquema `raw` fiel
a la fuente: si dbt necesita un INT y llega un valor inesperado, falla un
test de dbt de forma visible, en vez de que pandas silenciosamente
convierta o trunque algo durante la carga.

Decisiones de diseño (ver README para el detalle completo):
- Selección de partición: por defecto coge la última fecha (dt=) disponible
  en S3; se puede fijar una fecha concreta con --date para reprocesar un
  día histórico.
- Full refresh: cada ejecución reemplaza el contenido de las tablas `raw.*`
  (if_exists='replace'). El histórico real vive en S3 (particionado por
  fecha); Postgres `raw` es solo la copia de trabajo más reciente para
  transformar. Si en el futuro se necesita histórico también en el
  warehouse, se añadiría vía snapshots de dbt, no aquí.
- Columnas de linaje (_source_file, _extraction_date, _loaded_at) para
  poder trazar de dónde viene cada fila sin salir de Postgres.
"""

from __future__ import annotations

import argparse
import io
import logging
import os
import sys
import zipfile
from datetime import date, datetime, timezone

import boto3
import pandas as pd
from botocore.client import Config
from botocore.exceptions import ClientError
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
)
logger = logging.getLogger("load_staging")

RAW_SCHEMA = "raw"


def load_config() -> dict:
    load_dotenv()
    config = {
        "s3_endpoint_url": os.environ.get("S3_ENDPOINT_URL"),
        "s3_bucket": os.environ.get("S3_BUCKET_NAME", "sevilla-transit-raw"),
        "s3_prefix": os.environ.get("S3_RAW_PREFIX", "raw/gtfs"),
        "aws_access_key_id": os.environ.get("AWS_ACCESS_KEY_ID"),
        "aws_secret_access_key": os.environ.get("AWS_SECRET_ACCESS_KEY"),
        "aws_region": os.environ.get("AWS_REGION", "eu-west-1"),
        "pg_user": os.environ.get("POSTGRES_USER", "sevilla"),
        "pg_password": os.environ.get("POSTGRES_PASSWORD", "sevilla"),
        "pg_db": os.environ.get("POSTGRES_DB", "sevilla_transit"),
        "pg_host": os.environ.get("POSTGRES_HOST", "localhost"),
        "pg_port": os.environ.get("POSTGRES_PORT", "5432"),
    }

    missing = [
        k
        for k in ("aws_access_key_id", "aws_secret_access_key")
        if not config[k]
    ]
    if missing:
        logger.error("Faltan variables de entorno: %s", ", ".join(missing))
        sys.exit(1)

    return config


def get_s3_client(config: dict):
    return boto3.client(
        "s3",
        endpoint_url=config["s3_endpoint_url"],
        aws_access_key_id=config["aws_access_key_id"],
        aws_secret_access_key=config["aws_secret_access_key"],
        config=Config(signature_version="s3v4"),
        region_name=config["aws_region"],
    )


def resolve_extraction_date(s3_client, config: dict, requested_date: date | None) -> date:
    """
    Si se pide una fecha concreta, la valida. Si no, busca la partición
    dt=YYYY-MM-DD más reciente disponible en S3 listando el prefijo.
    """
    prefix = f"{config['s3_prefix']}/"

    if requested_date is not None:
        key = f"{config['s3_prefix']}/dt={requested_date.isoformat()}/gtfs.zip"
        try:
            s3_client.head_object(Bucket=config["s3_bucket"], Key=key)
        except ClientError as exc:
            raise FileNotFoundError(
                f"No existe extracción para {requested_date} en s3://{config['s3_bucket']}/{key}"
            ) from exc
        return requested_date

    paginator = s3_client.get_paginator("list_objects_v2")
    dates_found = []
    for page in paginator.paginate(Bucket=config["s3_bucket"], Prefix=prefix, Delimiter="/"):
        for common_prefix in page.get("CommonPrefixes", []):
            # common_prefix['Prefix'] tiene forma "raw/gtfs/dt=2026-08-06/"
            part = common_prefix["Prefix"].rstrip("/").split("dt=")[-1]
            try:
                dates_found.append(datetime.strptime(part, "%Y-%m-%d").date())
            except ValueError:
                continue

    if not dates_found:
        raise FileNotFoundError(
            f"No se encontró ninguna partición dt= bajo s3://{config['s3_bucket']}/{prefix}. "
            "¿Has ejecutado extract_gtfs.py primero?"
        )

    latest = max(dates_found)
    logger.info("Partición más reciente encontrada en S3: dt=%s", latest.isoformat())
    return latest


def download_gtfs_zip(s3_client, config: dict, extraction_date: date) -> bytes:
    key = f"{config['s3_prefix']}/dt={extraction_date.isoformat()}/gtfs.zip"
    logger.info("Descargando s3://%s/%s", config["s3_bucket"], key)
    obj = s3_client.get_object(Bucket=config["s3_bucket"], Key=key)
    return obj["Body"].read()


def get_pg_engine(config: dict):
    url = (
        f"postgresql+psycopg2://{config['pg_user']}:{config['pg_password']}"
        f"@{config['pg_host']}:{config['pg_port']}/{config['pg_db']}"
    )
    return create_engine(url)


def ensure_schema_exists(engine, schema: str) -> None:
    with engine.begin() as conn:
        conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema}"))


def load_gtfs_files_to_postgres(
    zip_content: bytes, engine, extraction_date: date
) -> dict[str, int]:
    """
    Carga cada .txt del ZIP a raw.<nombre_fichero> (sin extensión).
    Todo como texto (dtype=str) — el tipado es responsabilidad de dbt.
    Devuelve un dict {tabla: nº de filas cargadas} para el resumen final.
    """
    loaded_at = datetime.now(timezone.utc)
    rows_by_table: dict[str, int] = {}

    with zipfile.ZipFile(io.BytesIO(zip_content)) as zf:
        txt_files = [n for n in zf.namelist() if n.endswith(".txt")]
        logger.info("Ficheros encontrados en el ZIP: %s", txt_files)

        for filename in txt_files:
            table_name = filename.removesuffix(".txt")

            with zf.open(filename) as f:
                # dtype=str + keep_default_na=False: mantenemos el raw
                # fiel a la fuente. Sin esto, pandas podría inferir tipos
                # numéricos y perder ceros a la izquierda en IDs, o
                # convertir campos vacíos en NaN de forma inconsistente
                # entre ficheros.
                df = pd.read_csv(
                    f,
                    dtype=str,
                    keep_default_na=False,
                    skipinitialspace=True,  # el CSV real de CTAN trae espacios tras algunas comas
                    encoding="utf-8-sig",   # tolera BOM si el fichero lo trae
                )

            df.columns = df.columns.str.strip()

            # Columnas de linaje: permiten trazar cada fila hasta su origen
            # sin salir de Postgres (útil para debugging y auditoría).
            df["_source_file"] = filename
            df["_extraction_date"] = extraction_date.isoformat()
            df["_loaded_at"] = loaded_at.isoformat()

            df.to_sql(
                name=table_name,
                schema=RAW_SCHEMA,
                con=engine,
                if_exists="replace",
                index=False,
                chunksize=5000,
            )

            rows_by_table[table_name] = len(df)
            logger.info("raw.%s: %d filas cargadas", table_name, len(df))

    return rows_by_table


def run(requested_date: date | None) -> dict[str, int]:
    config = load_config()

    s3_client = get_s3_client(config)
    extraction_date = resolve_extraction_date(s3_client, config, requested_date)
    zip_content = download_gtfs_zip(s3_client, config, extraction_date)

    engine = get_pg_engine(config)
    ensure_schema_exists(engine, RAW_SCHEMA)

    return load_gtfs_files_to_postgres(zip_content, engine, extraction_date)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Carga el feed GTFS desde S3/MinIO al esquema raw de Postgres."
    )
    parser.add_argument(
        "--date",
        type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(),
        default=None,
        help="Partición dt=YYYY-MM-DD a cargar. Por defecto: la más reciente disponible en S3.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    try:
        summary = run(requested_date=args.date)
        total_rows = sum(summary.values())
        logger.info(
            "Carga finalizada: %d tablas, %d filas en total.", len(summary), total_rows
        )
    except Exception:
        logger.exception("La carga a staging ha fallado")
        sys.exit(1)