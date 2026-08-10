-- dim_paradas: una fila por parada física de la red de Sevilla.
select
    stop_id,
    stop_name,
    stop_lat,
    stop_lon
from {{ ref('stg_stops') }}