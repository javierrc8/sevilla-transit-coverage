# Imagen de Airflow para este proyecto: parte de la imagen oficial y le
# añade las dependencias de extract_gtfs.py, load_staging.py y dbt.
#
# Decisión importante: estas dependencias NO se instalan en el Python de
# Airflow (con `pip install` directo), sino en un entorno virtual aparte
# (/opt/project_venv). Motivo: nuestros scripts fijan versiones concretas
# (p.ej. SQLAlchemy 2.x) que entran en conflicto con las que Airflow
# necesita internamente (SQLAlchemy <2.0). Mezclar ambos en el mismo
# entorno rompe el propio arranque de Airflow. Aislarlas en su propio
# venv evita ese conflicto por completo, y además hace que actualizar
# las dependencias del proyecto en el futuro nunca pueda volver a romper
# Airflow.
FROM apache/airflow:2.9.3-python3.10

USER root

RUN python3 -m venv /opt/project_venv

COPY extract/requirements.txt /tmp/extract-requirements.txt
COPY load/requirements.txt /tmp/load-requirements.txt

# dbt-core y dbt-postgres se fijan EXPLÍCITAMENTE los dos, a la misma
# versión clásica (1.8.2). Motivo: dbt Labs publicó un nuevo motor
# ("dbt Fusion", escrito en Rust) bajo el mismo nombre de paquete
# dbt-core, en versiones 2.x. dbt-postgres==1.8.2 no fija un límite
# superior para su dependencia de dbt-core, así que sin este pin
# explícito, pip resuelve a la versión más reciente de dbt-core
# disponible (la 2.0 alpha de Fusion) — que todavía no soporta el
# adaptador de Postgres. Fijar ambos paquetes a la misma versión clásica
# evita este problema de raíz.
RUN /opt/project_venv/bin/pip install --no-cache-dir --upgrade pip && \
    /opt/project_venv/bin/pip install --no-cache-dir \
        -r /tmp/extract-requirements.txt \
        -r /tmp/load-requirements.txt \
        dbt-core==1.8.2 \
        dbt-postgres==1.8.2

USER airflow
