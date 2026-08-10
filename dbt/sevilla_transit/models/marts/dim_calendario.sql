-- dim_calendario: una fila por servicio (patrón semanal de operación),
-- con sus fechas de vigencia. Se mantiene con las 7 columnas booleanas
-- (útil para consultas ad-hoc: "¿qué servicios operan en sábado?"),
-- separada de int_calendar_day_types, que es la versión ya simplificada
-- a laborable/fin_de_semana que usa el mart de frecuencia.
select
    service_id,
    monday,
    tuesday,
    wednesday,
    thursday,
    friday,
    saturday,
    sunday,
    start_date,
    end_date
from {{ ref('stg_calendar') }}