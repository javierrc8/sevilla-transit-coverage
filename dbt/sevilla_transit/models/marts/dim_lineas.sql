-- dim_lineas: una fila por línea de autobús metropolitana de Sevilla.
select
    route_id,
    route_short_name,
    route_long_name,
    route_color,
    route_text_color
from {{ ref('stg_routes') }}