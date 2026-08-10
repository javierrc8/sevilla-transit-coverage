-- int_calendar_day_types: convierte las 7 columnas booleanas de
-- stg_calendar (monday...sunday) en filas (service_id, day_type), donde
-- day_type es 'laborable' o 'fin_de_semana'.
--
-- Por qué: un service_id de GTFS puede aplicar a varios días de la semana
-- a la vez (ej. "Lunes a Viernes"). Para poder agrupar más adelante por
-- "laborable vs fin de semana" necesitamos esa clasificación como un
-- valor, no como 5 columnas booleanas sueltas. Un service_id que opere
-- tanto en fin de semana como en algún día laborable (poco común, pero
-- posible) aparecerá en las dos categorías — es el comportamiento
-- correcto: sus viajes son reales en ambos tipos de día.

with calendar as (

    select * from {{ ref('stg_calendar') }}

),

laborable as (

    select service_id, 'laborable' as day_type
    from calendar
    where monday or tuesday or wednesday or thursday or friday

),

fin_de_semana as (

    select service_id, 'fin_de_semana' as day_type
    from calendar
    where saturday or sunday

)

select * from laborable
union all
select * from fin_de_semana