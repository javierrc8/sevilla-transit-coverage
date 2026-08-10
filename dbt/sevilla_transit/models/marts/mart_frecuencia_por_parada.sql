-- mart_frecuencia_por_parada: la tabla que responde directamente a la
-- pregunta del proyecto. Una fila por (parada, tipo de día), con la
-- frecuencia media de buses/hora.
--
-- Definición de la métrica (decisión documentada en el README): se
-- calcula como pasadas_totales / horas_con_servicio_activo, NO dividiendo
-- entre las 24h del día. Motivo: dividir entre 24h diluiría el dato con
-- horas de madrugada donde no pasa ningún bus en ninguna parada,
-- ocultando diferencias reales entre paradas bien y mal comunicadas
-- durante su franja de servicio real.
--
-- Se denormaliza el nombre y las coordenadas de la parada directamente
-- aquí (en vez de dejarlas solo en dim_paradas): los marts son la capa de
-- consumo final, pensada para que el dashboard (Fase 5) pueda consultar
-- esta única tabla sin tener que hacer JOIN con dim_paradas cada vez.

with fct as (

    select * from {{ ref('fct_paradas_por_viaje') }}

),

por_parada_y_dia as (

    select
        stop_id,
        day_type,
        count(*) as total_pasadas,
        count(distinct floor(extract(epoch from arrival_interval) / 3600)) as horas_con_servicio,
        min(arrival_interval) as primera_pasada,
        max(arrival_interval) as ultima_pasada

    from fct
    group by stop_id, day_type

),

con_metrica as (

    select
        por_parada_y_dia.*,
        round(
            total_pasadas::numeric / nullif(horas_con_servicio, 0),
            2
        ) as buses_por_hora

    from por_parada_y_dia

)

select
    con_metrica.stop_id,
    dim_paradas.stop_name,
    dim_paradas.stop_lat,
    dim_paradas.stop_lon,
    con_metrica.day_type,
    con_metrica.total_pasadas,
    con_metrica.horas_con_servicio,
    con_metrica.buses_por_hora,
    con_metrica.primera_pasada,
    con_metrica.ultima_pasada

from con_metrica
inner join {{ ref('dim_paradas') }} as dim_paradas
    on con_metrica.stop_id = dim_paradas.stop_id