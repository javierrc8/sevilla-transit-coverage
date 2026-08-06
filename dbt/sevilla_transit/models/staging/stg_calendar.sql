-- stg_calendar: tipa raw.calendar y se filtra a los service_id realmente
-- usados por algún trip de Sevilla (vía stg_trips).
--
-- Las columnas monday..sunday llegan de GTFS como texto '0'/'1'; se
-- castean a boolean explícitamente en vez de dejarlas como texto, porque
-- son la base directa del cálculo laborable-vs-fin-de-semana que pide el
-- mart final — mejor que ese cálculo compare booleanos, no strings.

with source as (

    select * from {{ source('raw', 'calendar') }}

),

sevilla_services as (

    select distinct service_id from {{ ref('stg_trips') }}

),

filtered as (

    select source.*
    from source
    inner join sevilla_services on source.service_id = sevilla_services.service_id

),

typed as (

    select
        service_id,
        (monday = '1')    as monday,
        (tuesday = '1')   as tuesday,
        (wednesday = '1') as wednesday,
        (thursday = '1')  as thursday,
        (friday = '1')    as friday,
        (saturday = '1')  as saturday,
        (sunday = '1')    as sunday,
        to_date(start_date, 'YYYYMMDD') as start_date,
        to_date(end_date, 'YYYYMMDD')   as end_date

    from filtered

)

select * from typed