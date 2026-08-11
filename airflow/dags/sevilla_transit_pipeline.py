"""
sevilla_transit_pipeline.py

DAG que orquesta el pipeline completo, una vez al día:

    extract_gtfs → load_staging → dbt_run → dbt_test

Decisiones de diseño (ver README para el detalle completo):

- catchup=False: si Airflow lleva varios días sin ejecutarse (por ejemplo,
  porque el ordenador estaba apagado), NO intenta recuperar todas las
  ejecuciones perdidas de golpe al arrancar — simplemente retoma desde la
  próxima ejecución programada. Para un pipeline que descarga "el estado
  actual" del feed (no datos históricos), no tiene sentido "recuperar" el
  día de ayer: el feed de ayer ya no existe, solo existe el de hoy. Con
  catchup=True, Airflow lanzaría una ejecución por cada día perdido,
  descargando el mismo feed actual varias veces para fechas de partición
  que ya no representan la realidad.

- retries=2 con retry_delay=5 minutos: la API de CTAN o la red pueden
  fallar puntualmente. Dos reintentos con espera son suficientes para
  fallos transitorios sin generar un bucle agresivo de reintentos.

- Las tareas usan BashOperator invocando los mismos scripts que ya
  ejecutas a mano (extract_gtfs.py, load_staging.py) y los mismos comandos
  de dbt (dbt run, dbt test) — el DAG no reimplementa ninguna lógica,
  solo la orquesta. Si algo falla aquí, se puede reproducir exactamente
  igual ejecutando el comando a mano.
"""

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator

PROJECT_DIR = "/opt/airflow/project"
DBT_DIR = f"{PROJECT_DIR}/dbt/sevilla_transit"
# Entorno virtual aislado (ver airflow/Dockerfile) donde viven las
# dependencias de los scripts del proyecto, separadas de las de Airflow.
VENV_BIN = "/opt/project_venv/bin"

default_args = {
    "owner": "sevilla_transit",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}

with DAG(
    dag_id="sevilla_transit_pipeline",
    description="Extrae, carga y transforma el feed GTFS de CTAN (área de Sevilla).",
    default_args=default_args,
    schedule_interval="0 6 * * *",  # todos los días a las 06:00
    start_date=datetime(2026, 8, 1),
    catchup=False,
    max_active_runs=1,
    tags=["sevilla-transit", "gtfs"],
) as dag:

    extract_gtfs = BashOperator(
        task_id="extract_gtfs",
        bash_command=f"cd {PROJECT_DIR}/extract && {VENV_BIN}/python extract_gtfs.py",
    )

    load_staging = BashOperator(
        task_id="load_staging",
        bash_command=f"cd {PROJECT_DIR}/load && {VENV_BIN}/python load_staging.py",
    )

    dbt_run = BashOperator(
        task_id="dbt_run",
        bash_command=f"cd {DBT_DIR} && DBT_PROFILES_DIR={DBT_DIR} {VENV_BIN}/dbt run",
    )

    dbt_test = BashOperator(
        task_id="dbt_test",
        bash_command=f"cd {DBT_DIR} && DBT_PROFILES_DIR={DBT_DIR} {VENV_BIN}/dbt test",
    )

    extract_gtfs >> load_staging >> dbt_run >> dbt_test