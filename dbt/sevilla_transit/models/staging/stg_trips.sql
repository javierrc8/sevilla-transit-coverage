-- stg_trips: tipa raw.trips y propaga el filtro de scope en cascada.
--
-- No repetimos el filtro por agency_id aquí (trips no tiene esa columna
-- directamente). En su lugar, hacemos INNER JOIN con stg_routes, que ya
-- está filtrado: si un trip no pertenece a una ruta de Sevilla, el JOIN
-- simplemente lo descarta. Este es el patrón que se repite en cascada
-- hasta stops y calendar.

with source as (

    select * from {{ source('raw', 'trips') }}

),

sevilla_routes as (

    select route_id from {{ ref('stg_routes') }}

),

filtered as (

    select source.*
    from source
    inner join sevilla_routes on source.route_id = sevilla_routes.route_id

),

typed as (

    select
        trip_id,
        route_id,
        service_id,
        trim(trip_headsign) as trip_headsign,
        direction_id::integer as direction_id,
        shape_id

    from filtered

)

select * from typed