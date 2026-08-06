-- stg_stops: tipa raw.stops y se filtra a las paradas que efectivamente
-- reciben algún paso de una línea de Sevilla (vía stg_stop_times, ya
-- filtrado en cascada). stops.txt no tiene agency_id ni route_id: es la
-- última tabla de la cadena de filtrado, por eso el semi-join es contra
-- stop_times en vez de contra routes directamente.

with source as (

    select * from {{ source('raw', 'stops') }}

),

sevilla_stop_ids as (

    select distinct stop_id from {{ ref('stg_stop_times') }}

),

filtered as (

    select source.*
    from source
    inner join sevilla_stop_ids on source.stop_id = sevilla_stop_ids.stop_id

),

typed as (

    select
        stop_id,
        trim(stop_name) as stop_name,
        stop_lat::numeric as stop_lat,
        stop_lon::numeric as stop_lon

    from filtered

)

select * from typed