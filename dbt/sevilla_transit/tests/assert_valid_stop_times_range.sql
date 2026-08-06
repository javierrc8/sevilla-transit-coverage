-- Test de "rangos horarios válidos" (requisito mínimo definido en el
-- alcance del proyecto). Un test dbt falla si esta query devuelve alguna
-- fila, así que aquí seleccionamos las filas QUE INCUMPLEN la regla.
--
-- Formato esperado: HH:MM:SS, con minutos y segundos entre 00-59.
-- La hora puede superar 24 (GTFS lo permite para viajes nocturnos que
-- terminan después de medianoche), pero ponemos un techo razonable (47,
-- es decir hasta las 23:59:59 del día siguiente) para detectar valores
-- claramente corruptos sin invalidar servicios nocturnos legítimos.

select
    trip_id,
    stop_id,
    arrival_time,
    departure_time
from {{ ref('stg_stop_times') }}
where
    arrival_time !~ '^[0-9]{1,2}:[0-5][0-9]:[0-5][0-9]$'
    or departure_time !~ '^[0-9]{1,2}:[0-5][0-9]:[0-5][0-9]$'
    or split_part(arrival_time, ':', 1)::integer > 47
    or split_part(departure_time, ':', 1)::integer > 47