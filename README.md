# Sevilla Transit Coverage

Pipeline de datos end-to-end que analiza la cobertura y frecuencia de la **red interurbana metropolitana de Sevilla** (líneas gestionadas por el Consorcio de Transporte Metropolitano del Área de Sevilla — CTAN, `agency_id = CTMAS`), para responder a la pregunta:

> **¿Qué municipios y zonas del área metropolitana de Sevilla están peor comunicados con la capital por transporte público, y cómo cambia el servicio entre semana y fin de semana?**

## Estado del proyecto

🚧 En construcción — ver [progreso por fases](#roadmap) más abajo.

## Por qué este proyecto

- Usa datos en formato **GTFS**, el estándar internacional de transporte público (el mismo que usan Google Maps o Citymapper).
- Modelado dimensional real: esquema en estrella con **dbt** (dimensiones de paradas/líneas/calendario + tabla de hechos de viajes), no solo mover datos de un sitio a otro.
- Stack con alta demanda en el mercado de Data Engineering: Python, SQL, dbt, Airflow, data warehouse en la nube.

## Arquitectura

```
Python (extract del ZIP GTFS vía API de CTAN)
  → S3 (raw, sin transformar)
  → Data Warehouse (staging)
  → dbt (staging → intermediate → marts, esquema en estrella)
  → Airflow (orquesta el pipeline diario, con reintentos)
  → Streamlit (dashboard final: mapa de frecuencia por parada)
```

> Nota de diseño: para que el proyecto sea ejecutable de forma indefinida (portfolio público, sin depender de trials de cloud que caducan), el pipeline corre localmente con Docker usando Postgres como data warehouse y MinIO como almacenamiento S3-compatible. El código está pensado para ser portable a Snowflake/S3 real en un entorno de producción — se detalla en la sección de [Decisiones técnicas](#decisiones-técnicas).

## Alcance

Este proyecto cubre la **red interurbana metropolitana de Sevilla**: las líneas gestionadas bajo `agency_id = CTMAS` en el feed GTFS de CTAN (112 líneas que conectan Sevilla capital con municipios como Dos Hermanas, Alcalá de Guadaíra, Mairena del Aljarafe, Bormujos, Camas, Carmona, etc.).

> **Nota de scope (decisión documentada):** la idea inicial era analizar solo la red urbana de TUSSAM (autobuses dentro de Sevilla capital). Se descartó tras comprobar que TUSSAM no publica su feed GTFS por ningún canal oficial y estable — ver el detalle en [Decisiones técnicas](#decisiones-técnicas). El feed de CTAN, en cambio, es una fuente pública, documentada y con actualización diaria garantizada, por lo que el análisis se centra en la red metropolitana interurbana en su lugar. La pregunta de negocio sigue siendo válida y de hecho gana un ángulo real de movilidad: qué municipios del área metropolitana quedan peor conectados con la capital.

## Modelo de datos (dbt)

- **Staging**: `stg_stops`, `stg_routes`, `stg_trips`, `stg_stop_times`, `stg_calendar`
- **Dimensiones**: `dim_paradas`, `dim_lineas`, `dim_calendario`
- **Hechos**: `fct_paradas_por_viaje`
- **Mart final**: `mart_frecuencia_por_parada` (buses/hora por parada, laborable vs. fin de semana)

## Cómo ejecutarlo en local

_(Se documentará en cada fase a medida que se construya)_

```bash
docker-compose up -d
```

## Roadmap

- [x] Fase 0 — Estructura del repo y entorno Docker
- [x] Fase 1 — Extracción del feed GTFS (CTAN API → S3/MinIO)
- [ ] Fase 2 — Carga a staging
- [ ] Fase 3 — Modelado dbt (staging → marts)
- [ ] Fase 4 — Orquestación con Airflow
- [ ] Fase 5 — Dashboard con Streamlit

## Cómo ejecutar la extracción

```bash
docker-compose up -d minio
cd extract
pip install -r requirements.txt
cp ../.env.example ../.env   # si no lo has hecho ya
python extract_gtfs.py                      # extrae para la fecha de hoy
python extract_gtfs.py --date 2026-08-01     # backfill de una fecha concreta
python extract_gtfs.py --force               # sobrescribe si ya existe
```

Puedes ver el fichero subido en la consola web de MinIO: http://localhost:9001 (usuario/contraseña definidos en `.env`).

## Decisiones técnicas

### Fase 1 — Extracción

**Pivote de scope: de TUSSAM urbano a red metropolitana interurbana (CTAN).**
El plan inicial era analizar solo TUSSAM (autobuses urbanos de Sevilla capital). Al inspeccionar el feed real de CTAN se comprobó que: (1) el feed es unificado para los 9 consorcios de Andalucía, y (2) dentro del consorcio de Sevilla (`agency_id = CTMAS`), las 112 líneas presentes siguen todas el patrón `M-xxx`, es decir, son líneas **interurbanas metropolitanas** — TUSSAM no aparece en este feed en absoluto. Investigando el ecosistema de datos abiertos de Sevilla se confirmó que TUSSAM no publica su feed GTFS por ningún canal oficial (fuente: TFG de la Universidad de Sevilla sobre datos abiertos de transporte, que documenta explícitamente esta carencia). Ante esto, se decidió pivotar el scope del proyecto a la red metropolitana interurbana de CTAN: es una fuente pública, documentada y con garantía de actualización diaria, y la pregunta de negocio ("¿qué zonas están peor comunicadas?") sigue siendo válida aplicada a los municipios del área metropolitana en vez de a los barrios de la capital. Esta decisión se tomó **antes** de construir el modelo dbt, precisamente para evitar rehacer el modelado dimensional a mitad de proyecto.

**El feed de CTAN es unificado, no filtramos en la extracción.**
La API de CTAN (`https://api.ctan.es/v1/datos/UNIFICADO/gtfs.zip`) sirve un único ZIP con los 9 consorcios de transporte de Andalucía, no uno específico de Sevilla. Se decidió **no filtrar por operador (TUSSAM) en esta fase**, sino subir el ZIP completo tal cual a la capa raw. El filtrado a TUSSAM ocurre en la Fase 2 (carga a staging). Motivo: el raw layer debe ser una copia fiel de la fuente en el momento de la extracción — cualquier decisión de negocio (qué operador nos interesa) puede cambiar con el tiempo, y si está "cocinada" dentro del raw, perdemos la capacidad de reprocesar sin volver a golpear la API.

**Particionado por fecha de extracción (`dt=YYYY-MM-DD`).**
Cada ejecución escribe en una key distinta de S3 (`raw/gtfs/dt=2026-08-06/gtfs.zip`), nunca sobrescribe un día anterior. Esto permite: (a) llevar histórico para detectar cambios en el feed día a día, (b) reprocesar un día concreto sin afectar a los demás, y (c) que el pipeline sea idempotente — condición necesaria para que Airflow pueda reintentar una tarea fallida sin duplicar datos.

**MinIO en vez de S3 real para desarrollo local.**
Mismo razonamiento que Postgres frente a Snowflake: un portfolio público tiene que poder clonarse y ejecutarse sin depender de una cuenta AWS activa. MinIO expone una API compatible con S3, así que el código de `extract_gtfs.py` usa `boto3` de forma idéntica en ambos casos — solo cambia la variable de entorno `S3_ENDPOINT_URL`. En producción real, bastaría con vaciar esa variable para que boto3 apunte a AWS.

**Validación "barata" en la extracción, no de calidad de datos.**
El script valida que el ZIP no esté corrupto y que contenga los ficheros GTFS mínimos esperados (`stops.txt`, `routes.txt`, etc.) — es una validación estructural para detectar fallos de la fuente (API caída, cambio de formato) antes de subir nada. La validación de calidad de datos real (nulls, integridad referencial `trip_id`, rangos horarios válidos) se hace con tests de dbt en la Fase 3, no aquí — cada capa valida lo que le corresponde.

## Autor

[Javier Rodríguez Cordero] — Ingeniero de Software · Máster en Inteligencia Artificial