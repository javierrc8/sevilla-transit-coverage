-- Verifica que el mart final tiene, como mucho, una fila por combinación
-- de (stop_id, day_type). Si el GROUP BY de mart_frecuencia_por_parada
-- estuviera mal (por ejemplo, olvidando agrupar por day_type), esta
-- combinación dejaría de ser única y este test lo detectaría.

select
    stop_id,
    day_type,
    count(*) as filas
from {{ ref('mart_frecuencia_por_parada') }}
group by stop_id, day_type
having count(*) > 1