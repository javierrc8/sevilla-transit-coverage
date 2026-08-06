-- stg_stop_times: tipa raw.stop_times y propaga el filtro de scope
-- uniéndose a stg_trips (ya filtrado a Sevilla).
--
-- Decisión: arrival_time/departure_time se mantienen como texto (VARCHAR),
-- NO se castean a TIME. El estándar GTFS permite horas por encima de
-- 24:00:00 (p.ej. "25:30:00") para representar un viaje nocturno que
-- termina después de medianoche sin cambiar de día de servicio. El tipo
-- TIME de Postgres no admite eso — castear aquí perdería esos viajes o
-- lanzaría un error. El cálculo de frecuencias en el mart final (Fase 3,
-- más adelante) convertirá estas horas a INTERVAL, que sí soporta ese
-- rango, con una lógica explícita en el modelo intermedio.

with source as (

    select * from {{ source('raw', 'stop_times') }}

),

sevilla_trips as (

    select trip_id from {{ ref('stg_trips') }}

),

filtered as (

    select source.*
    from source
    inner join sevilla_trips on source.trip_id = sevilla_trips.trip_id

),

typed as (

    select
        trip_id,
        stop_id,
        arrival_time,
        departure_time,
        stop_sequence::integer as stop_sequence

    from filtered

)

select * from typed