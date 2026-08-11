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
        -- NULLIF convierte el texto vacío ("") a NULL antes de castear.
        -- El feed real de CTAN trae algunas paradas con lat/lon en blanco
        -- (no ausentes del todo, sino cadena vacía) — sin este NULLIF,
        -- el cast a numeric revienta con "invalid input syntax", en vez
        -- de dejarnos tratarlo como el dato ausente que realmente es.
        nullif(stop_lat, '')::numeric as stop_lat,
        nullif(stop_lon, '')::numeric as stop_lon

    from filtered

),

-- Se excluyen las paradas sin coordenadas: no se pueden situar en el mapa
-- de cobertura, que es el objetivo final del proyecto, así que no aportan
-- valor mantenerlas en el modelo analítico. El test not_null de stop_lat/
-- stop_lon (ver _staging.yml) queda como red de seguridad: after este
-- filtro debería pasar siempre — si un día vuelve a fallar, es señal de
-- que este filtro se ha roto, no de que haya coordenadas nuevas sin tratar.
final as (

    select * from typed
    where stop_lat is not null
      and stop_lon is not null

)

select * from final