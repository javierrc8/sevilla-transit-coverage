-- stg_routes: tipa las columnas de raw.routes y aplica el filtro de scope
-- del proyecto (agency_id = var('sevilla_agency_id'), ver dbt_project.yml).
--
-- Este es el modelo donde vive la decisión de negocio "qué red analizamos"
-- (documentada en el README). Si el scope cambiara en el futuro (por
-- ejemplo, añadir Cádiz), solo se toca la variable en dbt_project.yml,
-- no este SQL.

with source as (

    select * from {{ source('raw', 'routes') }}

),

filtered as (

    select *
    from source
    where agency_id = '{{ var("sevilla_agency_id") }}'

),

typed as (

    select
        route_id,
        agency_id,
        trim(route_short_name) as route_short_name,
        trim(route_long_name)  as route_long_name,
        route_type::integer    as route_type,
        route_color,
        route_text_color

    from filtered

)

select * from typed