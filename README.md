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
- [x] Fase 4 — Orquestación con Airflow
- [x] Fase 5 — Dashboard con Streamlit
- [x] Ejecución diaria automática vía GitHub Actions

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
pip install dbt-core==1.8.2 dbt-postgres==1.8.2
export DBT_PROFILES_DIR=$(pwd)   # en Windows (PowerShell): $env:DBT_PROFILES_DIR = (Get-Location)

dbt debug     # comprueba la conexión a Postgres
dbt run       # construye los modelos
dbt test      # ejecuta los tests
```

> **Nota**: se fijan las dos versiones (`dbt-core` y `dbt-postgres`) explícitamente, no solo `dbt-postgres`. dbt Labs publicó un nuevo motor ("dbt Fusion", en Rust) bajo el mismo paquete `dbt-core` en versiones 2.x, que todavía no soporta el adaptador de Postgres — sin fijar también `dbt-core`, `pip install dbt-postgres` puede arrastrar esa versión nueva incompatible. Ver el detalle en Decisiones técnicas, Fase 4.

## Cómo ejecutar Airflow

```bash
docker-compose up -d --build airflow-init      # una sola vez: prepara la BD de metadatos
docker-compose up -d airflow-webserver airflow-scheduler
```

Abre http://localhost:8080 (usuario `admin`, contraseña `admin`), activa el DAG `sevilla_transit_pipeline` y dispáralo manualmente con el botón ▶ para probarlo, o espera a su ejecución programada diaria (06:00).

## Cómo ejecutar el dashboard

```bash
docker-compose up -d --build streamlit
```

Abre http://localhost:8501. Necesita que el pipeline se haya ejecutado al menos una vez (para que `mart_frecuencia_por_parada` tenga datos) — si no, el dashboard lo indica con un aviso claro en vez de fallar en silencio.

## Ejecución automática diaria (sin depender de tu portátil)

Airflow (Fase 4) solo dispara sus tareas programadas si su `scheduler` está corriendo en ese momento — si tu ordenador está apagado, esa ejecución simplemente no ocurre. Para que el pipeline se ejecute de verdad todos los días sin depender de que tu máquina esté encendida, `.github/workflows/daily_pipeline.yml` reutiliza exactamente la misma secuencia de comandos (`extract → load → dbt run → dbt test`) disparada por un cron en GitHub Actions, sobre infraestructura efímera y gratuita (no sustituye a Airflow, lo complementa).

Se activa solo con hacer push del repo a GitHub — no requiere configuración adicional. También puedes lanzarlo manualmente desde la pestaña **Actions** del repositorio, botón "Run workflow", sin esperar al cron.

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
Cada ejecución de `load_staging.py` reemplaza el contenido de las tablas `raw.*`. Postgres `raw` es solo la copia de trabajo más reciente para transformar — el histórico día a día ya está garantizado por el particionado de S3 (Fase 1). Si en el futuro se necesitara histórico también dentro del warehouse (por ejemplo, para detectar cuándo cambió el horario de una línea), se añadiría con snapshots de dbt, que es la herramienta pensada para eso, no repitiendo la lógica en Python.

**`DROP ... CASCADE` explícito, no `if_exists='replace'` de pandas.**
Una vez que dbt crea sus vistas de staging (`staging.stg_stops`, etc.) sobre las tablas `raw.*`, un `replace` simple de pandas falla: Postgres se niega a hacer `DROP TABLE raw.stops` mientras exista una vista que dependa de ella (error `DependentObjectsStillExist`). La solución es un `DROP TABLE ... CASCADE` explícito antes de recrear la tabla — arrastra también las vistas dependientes (incluso en cadena, hasta los modelos intermedios). Esto es coherente con el pipeline tal y como está diseñado: el siguiente paso del DAG de Airflow, justo después de `load_staging`, es `dbt run`, que reconstruye esas vistas desde cero de todas formas. Es la misma filosofía de "full refresh" aplicada de forma consistente: si `raw` cambia, todo lo que depende de `raw` se recalcula entero, nunca se actualiza a medias.

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

**Coordenadas vacías en el feed real: `NULLIF` antes de castear, y exclusión explícita.**
Los datos sintéticos no cubrían un caso que sí apareció en el feed real de CTAN: algunas paradas traen `stop_lat`/`stop_lon` como cadena de texto vacía (`""`), no ausente del todo. Como la Fase 2 carga todo como texto sin convertir vacíos a nulo (a propósito, para no perder información en la carga), el cast directo a `numeric` en `stg_stops` reventaba con un error de sintaxis antes de que el test `not_null` llegara a evaluarlo. La solución: `NULLIF(stop_lat, '')::numeric` convierte el vacío en `NULL` de verdad antes de castear, y el modelo excluye explícitamente las paradas sin coordenadas — no pueden situarse en el mapa de cobertura, que es el objetivo final del proyecto. El test `not_null` se mantiene como red de seguridad: tras el filtro debería pasar siempre, y si un día vuelve a fallar, es la señal de que el filtro se ha roto, no de que hayan aparecido coordenadas nuevas sin tratar.

### Fase 4 — Airflow

**Base de datos de metadatos de Airflow separada del warehouse.**
`airflow-postgres` es una instancia de Postgres distinta a la que usa el proyecto como warehouse (`postgres`). Airflow necesita guardar su propio estado interno (qué DAGs existen, qué ejecuciones ha habido, logs...) — mezclarlo con los esquemas `raw`/`staging`/`marts` del proyecto acoplaría dos cosas que no tienen relación conceptual entre sí, y complicaría un backup o una migración del warehouse el día de mañana.

**`catchup=False`: no se recuperan ejecuciones perdidas.**
Esto conecta directamente con una limitación real de ejecutar Airflow en un portátil que no está siempre encendido: si el scheduler lleva 3 días parado, `catchup=True` haría que, al arrancar, Airflow lanzara 3 ejecuciones seguidas (una por cada día "perdido"). Para este pipeline no tiene sentido: cada ejecución descarga *el estado actual* del feed de CTAN, no un dato histórico de un día concreto — "recuperar" el día de ayer significaría simplemente descargar el feed de hoy con la fecha de ayer en la partición de S3, lo cual sería incorrecto. Con `catchup=False`, Airflow simplemente retoma desde la próxima ejecución programada.

**Las tareas del DAG no reimplementan lógica, solo orquestan.**
Cada tarea (`extract_gtfs`, `load_staging`, `dbt_run`, `dbt_test`) es un `BashOperator` que ejecuta exactamente el mismo comando que ya usas a mano. Esto es deliberado: si una tarea falla en Airflow, se puede reproducir el fallo ejecutando el mismo comando manualmente, sin tener que entender ninguna capa de abstracción extra de Airflow — el DAG es solo el "pegamento" que decide el orden y qué hacer si algo falla.

**Overrides de red explícitos para el contexto Docker.**
El `.env` compartido usa `POSTGRES_HOST=localhost` y `POSTGRES_PORT=5433` porque está pensado para ejecutar los scripts desde tu Windows, fuera de Docker. Dentro de la red de contenedores, los servicios se alcanzan por su nombre (`postgres`, `minio`) **y por su puerto interno real** (`5432` para Postgres, no el `5433` republicado hacia el host — ese mapeo de puerto solo existe de cara a Windows, la red interna de Docker nunca lo ve). En vez de mantener un `.env` duplicado, `docker-compose.yml` sobrescribe explícitamente `POSTGRES_HOST`, `POSTGRES_PORT` y `S3_ENDPOINT_URL` a nivel de servicio (`environment:`), y reutiliza el resto de la configuración (contraseñas, nombres de bucket) del mismo `.env` de siempre vía `env_file:`. Una única fuente de verdad para los secretos, con overrides explícitos solo donde el contexto de ejecución realmente cambia.

**Imagen Docker propia para Airflow, en vez de instalar dependencias en cada ejecución.**
`airflow/Dockerfile` parte de la imagen oficial de Airflow y le instala de una vez las dependencias de `extract_gtfs.py`, `load_staging.py` y `dbt-postgres`. La alternativa (instalar con `pip` dentro del propio `BashOperator`, en cada ejecución) funcionaría pero sería mucho más lento y menos reproducible — cada ejecución del DAG dependería de que PyPI esté disponible en ese momento.

**Las dependencias del proyecto viven en un entorno virtual aislado, no en el Python de Airflow.**
Al instalar `boto3`, `pandas` y `dbt-postgres` directamente en el mismo Python que usa Airflow, apareció un conflicto real: nuestro `load/requirements.txt` fija `SQLAlchemy==2.0.32`, pero Airflow 2.9 necesita internamente `SQLAlchemy <2.0` — la versión más nueva rompía el arranque del propio `webserver` y `scheduler` (error `ArgumentError` en los modelos ORM internos de Airflow). La solución: crear un entorno virtual aparte (`/opt/project_venv`) dentro de la misma imagen, con las dependencias del proyecto completamente aisladas de las de Airflow. Las tareas del DAG invocan explícitamente `/opt/project_venv/bin/python` y `/opt/project_venv/bin/dbt`, no el `python`/`dbt` que estaría en el `PATH` por defecto. Esto también es más robusto a futuro: actualizar `dbt` o `pandas` en el proyecto ya no puede volver a romper Airflow, porque nunca comparten el mismo entorno.

**`dbt-core` fijado explícitamente, no solo `dbt-postgres`.**
`pip install dbt-postgres==1.8.2` por sí solo instaló, inesperadamente, `dbt-core 2.0.0-alpha` — la primera versión pública de **dbt Fusion**, un motor nuevo de dbt Labs reescrito en Rust, que en esta versión alpha todavía no soporta el adaptador de Postgres (error `InvalidConfig`, "adapter is not yet supported by dbt Fusion"). La causa: la versión `dbt-postgres==1.8.2` no fija un límite superior para su dependencia de `dbt-core`, así que `pip` resuelve a la versión más reciente disponible — que hoy es la 2.0 alpha, no la línea clásica 1.x. La solución es fijar **ambos** paquetes (`dbt-core==1.8.2` y `dbt-postgres==1.8.2`) a la misma versión clásica explícitamente, tanto en la imagen Docker de Airflow como en las instrucciones de instalación local. Es un buen recordatorio de por qué fijar versiones exactas en un proyecto reproducible importa incluso para dependencias "de segundo grado" que uno no instala directamente.

### Fase 5 — Dashboard

**El dashboard no calcula nada, solo visualiza.**
`app.py` lee directamente de `mart_frecuencia_por_parada` — la tabla que dbt ya deja calculada — y no reimplementa ningún filtro ni agregación de negocio. Es la misma separación de responsabilidades que ya aplicamos entre Python y dbt en la Fase 2: la lógica de negocio vive en un único sitio (los modelos dbt), no se duplica en la capa de presentación. Si mañana cambia la definición de "peor comunicada", se cambia el modelo SQL, no el dashboard.

**Mapa con `open-street-map`, sin token de Mapbox.**
Plotly permite mapas interactivos sin necesidad de una cuenta de Mapbox (que requeriría gestionar otra clave de API más). Es la misma filosofía que MinIO/Postgres: todo el proyecto debe poder clonarse y ejecutarse sin depender de ninguna cuenta externa que pueda caducar o requerir configuración adicional.

**`scatter_mapbox`, no `scatter_map`, a pesar del aviso de "deprecated".**
Plotly introdujo `scatter_map` (basado en MapLibre) como reemplazo moderno de `scatter_mapbox` (basado en Mapbox GL). En pruebas locales, `scatter_map` compilaba sin errores en Python — pero al renderizarse en el navegador dentro de Streamlit, el mapa aparecía en blanco (solo ejes numéricos genéricos, sin el mapa de fondo). Se probó `scatter_mapbox` como alternativa, pero mostró exactamente el mismo fallo — señal de que el problema no era la traza concreta, sino que el navegador no cargaba correctamente la librería externa de mapas (Mapbox GL / MapLibre) que Plotly necesita, probablemente por un bloqueo de red hacia su CDN.

**Se sustituyó Plotly por `st.map` (el componente de mapa nativo de Streamlit, basado en pydeck/deck.gl) para el mapa de cobertura.**
En vez de seguir depurando una librería externa cargada por CDN, se optó por el componente de mapa integrado en el propio Streamlit, que usa teselas de Carto (gratuitas, sin API key para uso básico) y no depende de cargar Mapbox GL/MapLibre por separado en el navegador — mucho menos propenso a este tipo de fallo silencioso. Como `st.map` no ofrece una escala de color continua incorporada (solo acepta una columna con colores ya calculados en hexadecimal), se añadió una función propia (`frequency_to_hex_color`) que genera el color rojo→amarillo→verde manualmente. Se pierde el tooltip interactivo con detalles al pasar el ratón (limitación de `st.map` frente a Plotly), compensado con la tabla de ranking justo debajo, que ya muestra esos datos en detalle.

**El techo de la escala de color es un umbral fijo y ajustable, no el máximo del propio dataset.**
La primera versión normalizaba el color entre el mínimo y el máximo de `buses_por_hora` dentro del conjunto filtrado. Esto tenía un problema real, detectado al ver el mapa: la estación de intercambio de Plaza de Armas (un hub con muchísima más frecuencia que cualquier parada normal) actuaba como el extremo "verde" de la escala, lo que empujaba a prácticamente todas las demás paradas hacia el rojo *por comparación*, aunque tuvieran una frecuencia perfectamente razonable en términos absolutos. Además, como el mínimo y máximo se recalculaban por separado en cada vista, los colores de "laborable" y "fin de semana" ni siquiera eran comparables entre sí. La solución: un umbral fijo, controlable con un slider en el propio dashboard, y con recorte (*clip*) de cualquier valor por encima de ese umbral al verde máximo — así un outlier extremo no puede volver a estirar la escala.

**El umbral por defecto se calcula con el percentil 90 real de los datos, no con un número inventado.**
Tras ver el mapa con un umbral fijo puesto a ojo, seguía viéndose "casi todo rojo" — la elección inicial había sido una suposición razonable pero sin verificar contra los datos reales. Se añadió una sección de "Distribución de frecuencias" (percentiles + histograma) para inspeccionar la forma real de los datos antes de fijar el umbral, y el valor por defecto del slider pasó a calcularse dinámicamente como el percentil 90 de `buses_por_hora` sobre el conjunto completo (laborable + fin de semana combinados, para no romper la comparabilidad entre vistas). Con un umbral basado en percentiles, el 90% de las paradas se reparte por todo el degradado rojo-verde en vez de agruparse en el extremo rojo por comparación con un único hub extremo.

**`app.py` montado como volumen en Docker, no copiado en el build.**
La primera versión de `dashboard/Dockerfile` usaba `COPY app.py .`, que "hornea" el código dentro de la imagen en el momento de construirla. Esto causó un problema real durante el desarrollo: cambios en `app.py` no se reflejaban al recrear el contenedor (`docker-compose up -d streamlit`), porque seguía usando la imagen vieja con el código viejo — hacía falta reconstruir la imagen entera (`--build`) para cada cambio, incluso los más pequeños. Se corrigió montando `app.py` como volumen (`./dashboard/app.py:/app/app.py`), igual que ya se hacía con el proyecto completo en Airflow — así los cambios de código se reflejan de inmediato sin reconstruir nada, y Streamlit incluso recarga en caliente al detectar el cambio.

**Streamlit dockerizado, coherente con el resto del stack.**
Aunque Streamlit se puede lanzar directamente con `streamlit run app.py` sin Docker, se dockerizó igual que el resto de servicios para mantener la promesa central del proyecto: todo el pipeline (extracción, carga, transformación, orquestación y visualización) se levanta con un único `docker-compose up`, sin pasos manuales adicionales fuera de Docker.

### GitHub Actions — ejecución diaria sin depender de un ordenador encendido

**Complementa a Airflow, no lo sustituye.**
Airflow demuestra la habilidad de orquestar (dependencias entre tareas, reintentos, configuración de scheduling) — eso no cambia. Pero su `scheduler` necesita estar corriendo en el instante exacto de cada ejecución programada, y un portátil que se apaga por la noche no lo garantiza. GitHub Actions aporta un runner gratuito y siempre disponible como disparador real, reutilizando literalmente los mismos comandos que ya ejecuta el DAG — el workflow no reimplementa ninguna lógica nueva, solo la dispara desde otro sitio.

**MinIO no se declara como `services:` de GitHub Actions — se lanza manualmente con `docker run`.**
La sintaxis `services:` de GitHub Actions permite fijar la imagen y las variables de entorno de un contenedor auxiliar, pero no pasarle un comando de arranque personalizado. La imagen oficial de Postgres arranca sola sin argumentos extra, así que sí funciona como `service` — pero la de MinIO necesita explícitamente `server /data` como argumento, o solo imprime la ayuda y no levanta el servidor. La solución: lanzar MinIO como un contenedor Docker normal en un paso del job, con control total del comando, y esperar activamente a que su endpoint de salud responda antes de continuar.

**Sin secretos de GitHub Actions.**
Las credenciales usadas (`minioadmin`/`minioadmin`, contraseña de Postgres) son de infraestructura efímera que nace y muere dentro de la propia ejecución del workflow — nunca queda expuesta a nada externo. Es coherente con la filosofía de todo el proyecto: cero cuentas ni credenciales externas necesarias para ejecutarlo, ni siquiera en CI.

**Limitación asumida: sin persistencia entre ejecuciones.**
Cada ejecución del workflow levanta Postgres y MinIO efímeros desde cero — los datos no se acumulan de un día a otro dentro de GitHub Actions. El objetivo de este workflow es demostrar que la automatización diaria funciona de verdad, no sustituir a un warehouse persistente en la nube (eso exigiría una cuenta cloud real, justo lo que el proyecto evita a propósito). En un entorno de producción real, este mismo workflow apuntaría a infraestructura persistente (RDS, S3 real) en vez de contenedores efímeros.

## Autor

Javier Rodríguez Cordero — Ingeniero de Software · Máster en Inteligencia Artificial