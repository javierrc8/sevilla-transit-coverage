"""
extract_gtfs.py

Descarga el feed GTFS unificado de la Red de Consorcios de Transporte de
Andalucía (CTAN) y lo sube, sin transformar, a la capa raw de almacenamiento
(S3 o MinIO en local), particionado por fecha de extracción.

Decisiones de diseño (explicadas en detalle en el README):
- El feed de CTAN es UNIFICADO (los 9 consorcios andaluces en un solo ZIP).
  No filtramos aquí a TUSSAM/Sevilla: el raw layer debe ser fiel a la fuente.
  El filtrado por operador ocurre en la capa de staging (Fase 2).
- Particionado por fecha (dt=YYYY-MM-DD) para poder llevar histórico y
  reprocesar un día concreto sin pisar los demás.
- Idempotente: si ya existe una extracción para la fecha dada, no la repite
  salvo que se use --force. Esto hace seguro reintentar el DAG de Airflow
  sin duplicar datos.
"""

from __future__ import annotations

import argparse
import io
import logging
import os
import sys
import zipfile
from datetime import date, datetime

import boto3
import requests
from botocore.client import Config
from botocore.exceptions import ClientError
from dotenv import load_dotenv

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
)
logger = logging.getLogger("extract_gtfs")

# Ficheros que un feed GTFS válido debe contener como mínimo para este proyecto.
REQUIRED_GTFS_FILES = {
    "agency.txt",
    "stops.txt",
    "routes.txt",
    "trips.txt",
    "stop_times.txt",
    "calendar.txt",
}


def load_config() -> dict:
    """Carga configuración desde variables de entorno (.env en local)."""
    load_dotenv()

    config = {
        "gtfs_url": os.environ.get(
            "CTAN_GTFS_URL", "https://api.ctan.es/v1/datos/UNIFICADO/gtfs.zip"
        ),
        "s3_endpoint_url": os.environ.get("S3_ENDPOINT_URL"),  # None => AWS real
        "s3_bucket": os.environ.get("S3_BUCKET_NAME", "sevilla-transit-raw"),
        "s3_prefix": os.environ.get("S3_RAW_PREFIX", "raw/gtfs"),
        "aws_access_key_id": os.environ.get("AWS_ACCESS_KEY_ID"),
        "aws_secret_access_key": os.environ.get("AWS_SECRET_ACCESS_KEY"),
    }

    missing = [
        k
        for k in ("aws_access_key_id", "aws_secret_access_key")
        if not config[k]
    ]
    if missing:
        logger.error(
            "Faltan variables de entorno obligatorias: %s. "
            "Copia .env.example a .env y rellénalas.",
            ", ".join(missing),
        )
        sys.exit(1)

    return config


def download_gtfs_feed(url: str) -> bytes:
    """Descarga el ZIP del feed GTFS y devuelve su contenido en bytes."""
    logger.info("Descargando feed GTFS desde %s", url)
    response = requests.get(url, timeout=60)
    response.raise_for_status()
    logger.info(
        "Descarga completada: %.2f MB", len(response.content) / (1024 * 1024)
    )
    return response.content


def validate_gtfs_zip(content: bytes) -> None:
    """
    Valida que el contenido descargado es un ZIP válido y contiene los
    ficheros GTFS mínimos esperados. Lanza ValueError si algo falla.

    Esta validación es deliberadamente barata (solo estructura, no contenido
    fila a fila) porque su objetivo es detectar fallos de la fuente
    (API caída, ZIP corrupto, cambio de formato) ANTES de subir nada a S3.
    La validación de calidad de datos (nulls, integridad referencial, rangos)
    se hace con tests de dbt en la Fase 3, no aquí.
    """
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            bad_file = zf.testzip()
            if bad_file is not None:
                raise ValueError(f"ZIP corrupto: fallo en {bad_file}")

            names = set(zf.namelist())
            missing = REQUIRED_GTFS_FILES - names
            if missing:
                raise ValueError(
                    f"Faltan ficheros GTFS obligatorios en el feed: {missing}"
                )
    except zipfile.BadZipFile as exc:
        raise ValueError(f"El contenido descargado no es un ZIP válido: {exc}") from exc

    logger.info("Validación del feed GTFS: OK (%d ficheros)", len(names))


def get_s3_client(config: dict):
    """
    Crea un cliente S3 compatible tanto con AWS real como con MinIO local.

    Si S3_ENDPOINT_URL está definido (caso MinIO en docker-compose), se usa
    ese endpoint. Si no, boto3 apunta a AWS real por defecto. El resto del
    código no necesita saber cuál de los dos está usando.
    """
    return boto3.client(
        "s3",
        endpoint_url=config["s3_endpoint_url"],
        aws_access_key_id=config["aws_access_key_id"],
        aws_secret_access_key=config["aws_secret_access_key"],
        config=Config(signature_version="s3v4"),
        region_name=os.environ.get("AWS_REGION", "eu-west-1"),
    )


def ensure_bucket_exists(s3_client, bucket_name: str) -> None:
    """Crea el bucket si no existe (solo relevante en local con MinIO)."""
    try:
        s3_client.head_bucket(Bucket=bucket_name)
    except ClientError:
        logger.info("Bucket '%s' no existe, creándolo...", bucket_name)
        s3_client.create_bucket(Bucket=bucket_name)


def build_s3_key(prefix: str, extraction_date: date) -> str:
    """
    Construye la key de S3 particionada por fecha de extracción, siguiendo
    el patrón Hive-style (dt=YYYY-MM-DD) para que sea directamente legible
    por motores de consulta particionados (Athena, Snowflake external
    tables, etc.) si el proyecto escala más allá de este alcance inicial.
    """
    return f"{prefix}/dt={extraction_date.isoformat()}/gtfs.zip"


def object_already_exists(s3_client, bucket: str, key: str) -> bool:
    try:
        s3_client.head_object(Bucket=bucket, Key=key)
        return True
    except ClientError:
        return False


def upload_to_s3(s3_client, content: bytes, bucket: str, key: str) -> None:
    logger.info("Subiendo a s3://%s/%s (%.2f MB)", bucket, key, len(content) / (1024 * 1024))
    s3_client.put_object(
        Bucket=bucket,
        Key=key,
        Body=content,
        ContentType="application/zip",
        Metadata={
            "source": "api.ctan.es",
            "extracted_at_utc": datetime.utcnow().isoformat(),
        },
    )
    logger.info("Subida completada.")


def run(extraction_date: date, force: bool = False) -> str:
    """Ejecuta el flujo completo de extracción. Devuelve la S3 key usada."""
    config = load_config()

    s3_client = get_s3_client(config)
    ensure_bucket_exists(s3_client, config["s3_bucket"])

    key = build_s3_key(config["s3_prefix"], extraction_date)

    if not force and object_already_exists(s3_client, config["s3_bucket"], key):
        logger.info(
            "Ya existe una extracción para %s en s3://%s/%s — nada que hacer "
            "(usa --force para sobrescribir).",
            extraction_date,
            config["s3_bucket"],
            key,
        )
        return key

    content = download_gtfs_feed(config["gtfs_url"])
    validate_gtfs_zip(content)
    upload_to_s3(s3_client, content, config["s3_bucket"], key)

    return key


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extrae el feed GTFS de CTAN y lo sube a S3/MinIO (raw layer)."
    )
    parser.add_argument(
        "--date",
        type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(),
        default=date.today(),
        help="Fecha de partición a usar (YYYY-MM-DD). Por defecto: hoy. "
        "Útil para backfills o pruebas.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Sobrescribe la extracción aunque ya exista para esa fecha.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    try:
        s3_key = run(extraction_date=args.date, force=args.force)
        logger.info("Extracción finalizada correctamente: %s", s3_key)
    except Exception:
        logger.exception("La extracción ha fallado")
        sys.exit(1)