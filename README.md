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
- [x] Fase 2 — Carga a staging (raw layer en Postgres)
- [x] Fase 3 — Modelado dbt (staging → marts)
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

## Cómo ejecutar la carga a staging

```bash
docker-compose up -d postgres
cd load
pip install -r requirements.txt
python load_staging.py                      # coge la partición más reciente de S3
python load_staging.py --date 2026-08-01     # carga una fecha concreta
```

Puedes inspeccionar el resultado conectando a Postgres (`localhost:5432`, credenciales en `.env`) y listando las tablas del esquema `raw`:

```sql
SELECT table_name FROM information_schema.tables WHERE table_schema = 'raw';
SELECT agency_id, agency_name FROM raw.agency;
```

## Cómo ejecutar dbt

```bash
cd dbt/sevilla_transit
pip install dbt-postgres
export DBT_PROFILES_DIR=$(pwd)   # en Windows (PowerShell): $env:DBT_PROFILES_DIR = (Get-Location)

dbt debug     # comprueba la conexión a Postgres
dbt run       # construye los modelos
dbt test      # ejecuta los tests
```

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

### Fase 2 — Carga a staging

**Patrón ELT: Python solo carga, dbt transforma.**
`load_staging.py` copia cada `.txt` del GTFS a una tabla `raw.<nombre>` en Postgres **sin filtrar por agencia ni tipar las columnas** — todo se carga como texto (`dtype=str`). El filtro a `agency_id = CTMAS` (Sevilla) y el tipado real de columnas (fechas, floats de lat/long, etc.) se hacen en dbt (Fase 3). Se decidió así porque el filtro a Sevilla no es una operación de una sola tabla: `routes.txt` tiene `agency_id`, pero `stops.txt` y `calendar.txt` no — para filtrarlos hay que atravesar `routes → trips → stop_times → stops`, y ese tipo de lógica declarativa, con dependencias entre modelos y tests automáticos, es exactamente para lo que existe dbt. Meterla en un script Python de carga habría duplicado lógica de negocio en dos sitios distintos del pipeline.

**`dtype=str` en la carga, no inferencia automática de tipos.**
pandas podría inferir tipos automáticamente (`route_short_name` como int, por ejemplo), pero eso es peligroso con datos GTFS: algunos códigos de línea tienen ceros a la izquierda o mezclan letras y números (`"P.LO"`, `"0110-V"`), y una inferencia de tipo incorrecta en la carga sería un error silencioso. Cargar todo como texto mantiene el esquema `raw` fiel a la fuente byte a byte; si dbt necesita castear algo a `INTEGER` o `FLOAT` y falla, el fallo es visible y explícito, no un dato corrompido sin avisar.

**Selección automática de la partición más reciente en S3.**
Por defecto, `load_staging.py` lista las particiones `dt=` disponibles en S3 y coge la más reciente, sin necesidad de pasarle una fecha. Esto es importante para la Fase 4: cuando Airflow orqueste `extract → load`, el DAG no necesita coordinar explícitamente qué fecha acaba de extraer el paso anterior — `load_staging.py` simplemente coge "lo último que haya", lo cual simplifica el grafo de dependencias. La opción `--date` se mantiene para reprocesar un día histórico concreto sin tocar el resto.

**Full refresh en `raw`, histórico real vive en S3.**
Cada ejecución de `load_staging.py` reemplaza el contenido de las tablas `raw.*` (`if_exists='replace'`). Postgres `raw` es solo la copia de trabajo más reciente para transformar — el histórico día a día ya está garantizado por el particionado de S3 (Fase 1). Si en el futuro se necesitara histórico también dentro del warehouse (por ejemplo, para detectar cuándo cambió el horario de una línea), se añadiría con snapshots de dbt, que es la herramienta pensada para eso, no repitiendo la lógica en Python.

### Fase 3 — dbt (en curso)

**`profiles.yml` versionado en el repo, sin credenciales.**
Normalmente `profiles.yml` vive fuera del repo (`~/.dbt/profiles.yml`) porque suele contener contraseñas. Aquí usa `env_var()` de Jinja para leer las mismas variables de entorno que ya usan `extract_gtfs.py` y `load_staging.py` — no hay ningún secreto en el fichero, así que se puede versionar sin riesgo, y todo el proyecto comparte una única fuente de configuración (`.env`). Se activa apuntando `DBT_PROFILES_DIR` a la carpeta del proyecto dbt en vez de duplicarlo en el home del usuario.

**El filtro de scope (`agency_id = CTMAS`) vive en una variable de dbt, no hardcodeado en SQL.**
`dbt_project.yml` define `vars: sevilla_agency_id: 'CTMAS'`, y `stg_routes.sql` lo referencia con `{{ var("sevilla_agency_id") }}`. Si el scope del proyecto cambiara (por ejemplo, añadir Cádiz más adelante), es un cambio de una línea en la configuración, no una reescritura de modelos — y queda documentado en un único sitio.

**El test `accepted_values` sobre `agency_id` no es redundante con el `WHERE` del modelo.**
Puede parecer que testear que `agency_id = 'CTMAS'` es innecesario si el propio modelo ya filtra por eso — pero el test no verifica el filtro en sí, verifica que **nadie rompa el filtro sin darse cuenta** en un cambio futuro (por ejemplo, si alguien edita `stg_routes.sql` y se equivoca en el `WHERE`). Es la diferencia entre "confiar en que el código hace lo que crees" y "tener una alarma automática si deja de hacerlo".

**Las horas GTFS se castean directamente a `INTERVAL`, sin parsear a mano.**
Postgres interpreta correctamente el formato `HH:MM:SS` de GTFS incluso por encima de 24h (`'25:30:00'::interval` da 25.5 horas, sin error) — se comprobó explícitamente antes de construir `fct_paradas_por_viaje`. Esto evita una trampa común: intentar castear a `TIME` (que sí falla con >24h) o parsear manualmente con funciones de texto cuando no hace falta.

**Esquema en estrella: 3 dimensiones + 1 tabla de hechos.**
`dim_paradas`, `dim_lineas` y `dim_calendario` son las "entidades" sobre las que se pregunta (quién, qué, cuándo). `fct_paradas_por_viaje` es la tabla de hechos: una fila por cada paso real de un autobús por una parada, con solo IDs apuntando a las dimensiones y las horas ya en `INTERVAL`. Mantenerla "delgada" (sin repetir nombres ni colores) es el propósito central de este patrón: evita duplicar el nombre de una parada en cientos de miles de filas.

**El filtro a Sevilla se propaga en cascada por JOINs, no se repite en cada modelo.**
`stops.txt` y `calendar.txt` no tienen `agency_id` directamente — no hay forma de filtrarlos "a pelo". En su lugar, cada modelo de staging se une (`INNER JOIN`) al modelo anterior ya filtrado: `stg_trips` se une a `stg_routes`, `stg_stop_times` a `stg_trips`, `stg_stops` a `stg_stop_times`, `stg_calendar` a `stg_trips`. Si un registro no pertenece a la cadena de Sevilla, el JOIN lo descarta solo, sin necesidad de repetir `WHERE agency_id = 'CTMAS'` en cada sitio.

**Definición de la métrica: buses/hora sobre horas con servicio activo, no sobre las 24h del día.**
`mart_frecuencia_por_parada` calcula `total_pasadas / horas_con_servicio_activo`, contando solo las horas en las que efectivamente pasó al menos un bus. Dividir entre las 24 horas del día habría diluido el dato con la franja de madrugada (donde ninguna parada tiene servicio), ocultando las diferencias reales entre paradas bien y mal comunicadas durante su horario de servicio.

**`laborable` / `fin_de_semana` se calcula desnormalizando el calendario, no asumiendo un día fijo.**
Un `service_id` de GTFS puede operar varios días de la semana a la vez (p. ej. "Lunes a Viernes"). `int_calendar_day_types` convierte las 7 columnas booleanas de `stg_calendar` en pares `(service_id, day_type)`, permitiendo que un mismo servicio cuente como `laborable` y/o `fin_de_semana` según corresponda — sin necesidad de asumir de antemano qué días concretos tiene cada patrón.

**Validación end-to-end con datos sintéticos antes de ejecutarlo contra datos reales.**
Antes de dar por bueno el modelo, se construyó una base de datos Postgres efímera con un puñado de filas sintéticas que cubrían deliberadamente los casos límite: una hora por encima de 24h, una parada sin ningún paso de autobús (para comprobar que desaparece del resultado), y una línea de otra provincia (para comprobar que el filtro a `CTMAS` la excluye en toda la cadena). Los 11 modelos y 50 tests se ejecutaron correctamente contra esos datos antes de aplicarlo al feed real — una práctica de ingeniería de software (probar con casos límite conocidos) aplicada a un pipeline de datos.

## Autor

[Javier Rodríguez Cordero] — Ingeniero de Software · Máster en Inteligencia Artificial