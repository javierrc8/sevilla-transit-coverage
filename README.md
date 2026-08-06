# Sevilla Transit Coverage

Pipeline de datos end-to-end que analiza la cobertura y frecuencia del transporte público urbano de Sevilla (TUSSAM), para responder a la pregunta:

> **¿Qué zonas de la ciudad están peor comunicadas por transporte público, y cómo cambia el servicio entre semana y fin de semana?**

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

> Nota de diseño: para que el proyecto sea ejecutable de forma indefinida (portfolio público, sin depender de trials de cloud que caducan), el pipeline corre localmente con Docker usando Postgres como data warehouse. El código de staging está pensado para ser portable a Snowflake en un entorno de producción real — se detalla en la sección de [Decisiones técnicas](#decisiones-técnicas).

## Alcance

Este proyecto cubre únicamente la red urbana de autobuses de Sevilla capital (**TUSSAM**), excluyendo metro, tranvía, cercanías y líneas interurbanas. Fue una decisión deliberada para priorizar un pipeline completo y funcionando end-to-end frente a cobertura exhaustiva de todos los operadores del Consorcio de Transporte de Sevilla.

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

- [ ] Fase 0 — Estructura del repo y entorno Docker
- [ ] Fase 1 — Extracción del feed GTFS (CTAN API → S3)
- [ ] Fase 2 — Carga a staging
- [ ] Fase 3 — Modelado dbt (staging → marts)
- [ ] Fase 4 — Orquestación con Airflow
- [ ] Fase 5 — Dashboard con Streamlit

## Decisiones técnicas

_(Se irá documentando el "por qué" de cada decisión a medida que avanza el proyecto)_

## Autor

[Javier Rodríguez Cordero] — Ingeniero de Software · Máster en Inteligencia Artificial