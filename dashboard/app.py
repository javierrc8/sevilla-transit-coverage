"""
app.py

Dashboard de Streamlit que responde a la pregunta central del proyecto:
¿qué zonas del área metropolitana de Sevilla están peor comunicadas por
transporte público, y cómo cambia entre laborable y fin de semana?

Lee directamente de mart_frecuencia_por_parada (la tabla ya calculada por
dbt) — el dashboard no hace ningún cálculo de negocio, solo visualiza.
Esa separación es deliberada: si mañana cambia la definición de la
métrica, se cambia en un sitio (el modelo dbt), no en el código del
dashboard.
"""

import os

import altair as alt
import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from sqlalchemy import create_engine

load_dotenv()

st.set_page_config(
    page_title="Cobertura del transporte metropolitano de Sevilla",
    layout="wide",
)


def get_engine():
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "5432")
    user = os.environ.get("POSTGRES_USER", "sevilla")
    password = os.environ.get("POSTGRES_PASSWORD", "sevilla")
    db = os.environ.get("POSTGRES_DB", "sevilla_transit")
    url = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db}"
    return create_engine(url)


@st.cache_data(ttl=600)
def load_mart_data() -> pd.DataFrame:
    # El esquema real es "public_marts": dbt antepone el schema del
    # profile (public) al nombre de carpeta del modelo (marts), según su
    # convención de nombres por defecto (ver dbt_project.yml).
    engine = get_engine()
    return pd.read_sql(
        "SELECT * FROM public_marts.mart_frecuencia_por_parada",
        engine,
    )


DAY_TYPE_LABELS = {
    "laborable": "Laborable",
    "fin_de_semana": "Fin de semana",
}


def scale_marker_size(value: float, vmin: float, vmax: float, min_out: float = 60, max_out: float = 250) -> float:
    """
    Escala total_pasadas a un radio en metros dentro de [min_out, max_out].
    Usa raíz cuadrada (no lineal) para comprimir el efecto de outliers: una
    parada-hub con muchísimos más pasos que el resto (p. ej. una estación
    central de intercambio) no debe generar un círculo que eclipse
    visualmente al resto del mapa — solo debe seguir siendo, de forma
    proporcional pero contenida, la más grande.
    """
    if vmax <= vmin:
        return (min_out + max_out) / 2
    t = (value**0.5 - vmin**0.5) / (vmax**0.5 - vmin**0.5)
    t = max(0.0, min(1.0, t))
    return min_out + t * (max_out - min_out)


def frequency_to_hex_color(value: float, vmax: float, vmin: float = 0.0) -> str:
    """
    Convierte un valor de buses/hora a un color hexadecimal en una escala
    rojo (bajo) -> amarillo -> verde (alto).

    A diferencia de una normalización min-max sobre el propio dataset
    filtrado, vmax aquí es un TECHO FIJO (criterio de negocio: "a partir
    de cuántos buses/hora consideramos que el servicio es bueno"), no el
    valor máximo real de las paradas. Esto evita que una única parada
    con una frecuencia extrema (p. ej. una estación de intercambio como
    Plaza de Armas, con muchos más buses/hora que cualquier parada normal)
    estire toda la escala de color y haga parecer "mal comunicadas" a
    paradas que en realidad tienen un servicio razonable. Valores por
    encima de vmax se recortan (clip) al verde máximo, en vez de seguir
    estirando la escala.
    """
    t = 0.0 if vmax <= vmin else (value - vmin) / (vmax - vmin)
    t = max(0.0, min(1.0, t))  # clip

    if t < 0.5:
        t2 = t / 0.5
        r, g, b = 220, int(50 + (200 - 50) * t2), int(50 + (40 - 50) * t2)
    else:
        t2 = (t - 0.5) / 0.5
        r, g, b = int(230 + (40 - 230) * t2), int(200 + (180 - 200) * t2), int(40 + (90 - 40) * t2)

    return f"#{r:02x}{g:02x}{b:02x}"

st.title("🚌 Cobertura del transporte metropolitano de Sevilla")
st.caption(
    "Frecuencia de autobuses por parada — red interurbana gestionada por "
    "CTAN (agency_id = CTMAS). Datos actualizados diariamente vía Airflow."
)

try:
    df = load_mart_data()
except Exception as exc:
    st.error(
        "No se ha podido conectar con el warehouse. ¿Está Postgres "
        f"arrancado y el pipeline ya ejecutado al menos una vez?\n\n{exc}"
    )
    st.stop()

if df.empty:
    st.warning(
        "El mart de frecuencia está vacío. Ejecuta el pipeline "
        "(extract → load → dbt run) al menos una vez antes de ver el dashboard."
    )
    st.stop()

# Percentiles sobre el conjunto COMPLETO (laborable + fin de semana
# combinados) — se calculan aquí arriba, en silencio, porque el valor por
# defecto del slider de umbral (más abajo) los necesita antes de que el
# usuario haya interactuado con nada.
percentiles = df["buses_por_hora"].quantile([0.5, 0.75, 0.90, 0.95, 0.99]).round(2)
default_threshold = float(percentiles[0.90]) if percentiles[0.90] > 0 else 1.0

# --- Huecos reservados: el mapa y sus métricas se PINTAN aquí arriba, pero
# su CONTENIDO se calcula más abajo, después de leer los controles. Así el
# usuario ve el mapa arriba y los controles que lo modifican justo debajo,
# aunque en el código los controles se definan después (st.empty() permite
# "reservar sitio" y rellenarlo más tarde en la ejecución del script). ---
metrics_placeholder = st.empty()
map_placeholder = st.empty()

st.divider()

# --- Controles del mapa: pegados justo debajo de él ---
st.subheader("Controles del mapa")

day_type = st.radio(
    "Tipo de día",
    options=["laborable", "fin_de_semana"],
    format_func=lambda x: DAY_TYPE_LABELS[x],
    horizontal=True,
)

freq_threshold = st.slider(
    "Umbral de \"buena frecuencia\" (buses/hora) — a partir de aquí, verde máximo",
    min_value=0.5,
    max_value=max(15.0, float(df["buses_por_hora"].max())),
    value=default_threshold,
    step=0.5,
    help=(
        "Por defecto se fija en el percentil 90 de TODAS las paradas "
        "(laborable + fin de semana) — así el 90% de las paradas se "
        "reparte por todo el degradado rojo-verde, en vez de que un hub "
        "extremo (como Plaza de Armas) empuje a casi todo lo demás hacia "
        "el rojo. Se calcula sobre el conjunto completo, no solo la vista "
        "actual, para que el umbral sea el mismo en ambas vistas y los "
        "colores sigan siendo comparables entre ellas."
    ),
)
st.caption(
    f"Rojo = 0 buses/hora. Verde = {freq_threshold:.1f} buses/hora o más "
    f"(≈ percentil {(df['buses_por_hora'] <= freq_threshold).mean() * 100:.0f} del conjunto completo). "
    "Mismo umbral en ambas vistas, así que los colores sí son comparables entre laborable y fin de semana."
)

with st.expander("Ver distribución real de frecuencias (percentiles + histograma)"):
    st.caption(
        "Cómo se reparte realmente buses/hora entre las paradas "
        "(laborable + fin de semana combinados) — sirve para decidir con "
        "criterio dónde poner el umbral de arriba, en vez de a ojo."
    )

    pcol1, pcol2, pcol3, pcol4, pcol5 = st.columns(5)
    pcol1.metric("Mediana (p50)", percentiles[0.50])
    pcol2.metric("p75", percentiles[0.75])
    pcol3.metric("p90", percentiles[0.90])
    pcol4.metric("p95", percentiles[0.95])
    pcol5.metric("Máximo", f"{df['buses_por_hora'].max():.2f}")

    hist_df = pd.DataFrame({
        "buses_por_hora": df["buses_por_hora"].clip(upper=df["buses_por_hora"].quantile(0.99))
    })
    # Altair (integrado en Streamlit, sin dependencias externas cargadas
    # por CDN) en vez de st.bar_chart con value_counts(bins=...): esa
    # combinación generaba etiquetas de eje horribles (la representación
    # en texto de un pandas.Interval, tipo "(0.591, 1.202]"). Altair
    # calcula los bins internamente y decide solo cuántas etiquetas caben
    # sin solaparse.
    chart = (
        alt.Chart(hist_df)
        .mark_bar()
        .encode(
            x=alt.X("buses_por_hora:Q", bin=alt.Bin(maxbins=30), title="Buses/hora"),
            y=alt.Y("count()", title="Nº de paradas"),
        )
    )
    st.altair_chart(chart, use_container_width=True)
    st.caption(
        "El eje X está recortado en el percentil 99 para que el histograma "
        "sea legible (si no, el hub extremo comprimiría todas las demás "
        "barras contra el cero)."
    )

# --- Cálculo real, ya con los valores de los controles leídos ---
filtered = df[df["day_type"] == day_type].copy()

filtered["color"] = filtered["buses_por_hora"].apply(
    lambda v: frequency_to_hex_color(v, vmax=freq_threshold)
)

size_min, size_max = filtered["total_pasadas"].min(), filtered["total_pasadas"].max()
filtered["marker_size"] = filtered["total_pasadas"].apply(
    lambda v: scale_marker_size(v, size_min, size_max)
)

# --- Rellenamos los huecos reservados arriba ---
with metrics_placeholder.container():
    col1, col2, col3 = st.columns(3)
    col1.metric("Paradas analizadas", f"{len(filtered):,}")
    col2.metric("Frecuencia media (buses/hora)", f"{filtered['buses_por_hora'].mean():.2f}")
    peor = filtered.loc[filtered["buses_por_hora"].idxmin()]
    col3.metric("Peor comunicada", peor["stop_name"], f"{peor['buses_por_hora']:.2f} buses/h")

with map_placeholder.container():
    st.subheader("Mapa de frecuencia por parada")
    st.map(
        filtered,
        latitude="stop_lat",
        longitude="stop_lon",
        color="color",
        size="marker_size",
    )

st.divider()

# --- Ranking de peor comunicadas ---
st.subheader("Ranking: paradas peor comunicadas")

n = st.slider("Número de paradas a mostrar", min_value=5, max_value=50, value=15)

ranking = (
    filtered.sort_values("buses_por_hora", ascending=True)
    .head(n)[["stop_name", "buses_por_hora", "total_pasadas", "horas_con_servicio"]]
    .rename(
        columns={
            "stop_name": "Parada",
            "buses_por_hora": "Buses/hora",
            "total_pasadas": "Total pasadas",
            "horas_con_servicio": "Horas con servicio",
        }
    )
)

st.dataframe(ranking, use_container_width=True, hide_index=True)