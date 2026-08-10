-- fct_paradas_por_viaje: la tabla de hechos del esquema en estrella. Una
-- fila por cada paso real de un autobús por una parada (trip_id + stop_id
-- + día tipo). Es intencionadamente "delgada": solo IDs que apuntan a las
-- dimensiones (dim_paradas, dim_lineas) + la hora ya convertida a
-- INTERVAL (no texto) para poder operar con ella en el mart siguiente.
--
-- Nota técnica: arrival_time se castea directamente a ::interval. Se
-- comprobó que Postgres interpreta correctamente el formato "HH:MM:SS" de
-- GTFS incluso por encima de 24h (ej. "25:30:00" → interval de 25.5h),
-- así que no hace falta parsear manualmente con split_part.

with stop_times as (

    select * from {{ ref('stg_stop_times') }}

),

trips as (

    select * from {{ ref('stg_trips') }}

),

day_types as (

    select * from {{ ref('int_calendar_day_types') }}

),

joined as (

    select
        stop_times.stop_id,
        stop_times.trip_id,
        trips.route_id,
        day_types.day_type,
        stop_times.arrival_time::interval   as arrival_interval,
        stop_times.departure_time::interval as departure_interval,
        stop_times.stop_sequence

    from stop_times
    inner join trips      on stop_times.trip_id  = trips.trip_id
    inner join day_types  on trips.service_id    = day_types.service_id

)

select * from joined