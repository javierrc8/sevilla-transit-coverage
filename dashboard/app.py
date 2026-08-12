"""
app.py

Dashboard que responde a la pregunta central del proyecto: qué zonas del
área metropolitana de Sevilla están peor comunicadas por transporte
público, y cómo cambia entre laborable y fin de semana.

Lee directamente de mart_frecuencia_por_parada (la tabla ya calculada por
dbt) — el dashboard no hace ningún cálculo de negocio, solo visualiza.
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

# ---------------------------------------------------------------------------
# Sistema de diseño: paleta, tipografía y componentes reutilizables.
#
# Se aplica vía CSS inyectado (no una librería externa cargada por CDN —
# ya tuvimos un fallo de red con Mapbox/MapLibre, este CSS vive dentro de
# la propia página que Streamlit ya sirve). Las fuentes son pilas de
# sistema (-apple-system, Segoe UI...), no tipografías descargadas: se
# ven bien tanto en Mac como en el Windows del propio autor, sin depender
# de que un CDN externo esté disponible.
# ---------------------------------------------------------------------------

FONT_SANS = (
    "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, "
    "Arial, sans-serif"
)
FONT_MONO = (
    "ui-monospace, 'SF Mono', 'Cascadia Code', 'Roboto Mono', Consolas, "
    "monospace"
)

# Colores semánticos de sistema de Apple (HIG), no un rojo-verde genérico:
# se reutilizan tal cual para la escala de frecuencia del mapa.
COLOR_RED = (255, 59, 48)      # systemRed
COLOR_ORANGE = (255, 149, 0)   # systemOrange
COLOR_GREEN = (52, 199, 89)    # systemGreen

CUSTOM_CSS = f"""
<style>
    /* Oculta el chrome por defecto de Streamlit para una apariencia más seria */
    #MainMenu, footer, header {{ visibility: hidden; }}

    html, body, [class*="css"] {{
        font-family: {FONT_SANS};
    }}

    .block-container {{
        max-width: 1100px;
        padding-top: 3rem;
        padding-bottom: 4rem;
    }}

    /* --- Cabecera --- */
    .eyebrow {{
        font-size: 0.75rem;
        font-weight: 600;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        color: #6E6E73;
        margin-bottom: 0.5rem;
    }}
    h1.page-title {{
        font-size: 2.6rem;
        font-weight: 600;
        letter-spacing: -0.02em;
        color: #1D1D1F;
        margin: 0 0 0.5rem 0;
        line-height: 1.15;
    }}
    p.page-subtitle {{
        font-size: 1.05rem;
        color: #6E6E73;
        max-width: 640px;
        line-height: 1.5;
        margin-bottom: 2.5rem;
    }}

    /* --- Ficha técnica (KPIs) --- */
    .kpi-row {{
        display: flex;
        border-top: 1px solid #D2D2D7;
        border-bottom: 1px solid #D2D2D7;
        padding: 1.75rem 0;
        margin-bottom: 2.5rem;
    }}
    .kpi {{
        flex: 1;
        padding: 0 1.75rem;
        border-left: 1px solid #D2D2D7;
    }}
    .kpi:first-child {{ border-left: none; padding-left: 0; }}
    .kpi-value {{
        font-family: {FONT_MONO};
        font-size: 2.1rem;
        font-weight: 600;
        color: #1D1D1F;
        font-variant-numeric: tabular-nums;
        line-height: 1.1;
    }}
    .kpi-label {{
        font-size: 0.85rem;
        color: #6E6E73;
        margin-top: 0.35rem;
    }}

    /* --- Tarjetas de sección --- */
    div[data-testid="stVerticalBlockBorderWrapper"] {{
        border-radius: 16px !important;
        border-color: #D2D2D7 !important;
        box-shadow: 0 1px 2px rgba(0,0,0,0.03), 0 8px 24px rgba(0,0,0,0.04);
    }}
    div[data-testid="stVerticalBlockBorderWrapper"] > div {{
        padding: 0.5rem 0.25rem;
    }}

    .section-eyebrow {{
        font-size: 0.7rem;
        font-weight: 600;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        color: #6E6E73;
        margin-bottom: 0.15rem;
    }}
    h2.section-title {{
        font-size: 1.35rem;
        font-weight: 600;
        color: #1D1D1F;
        margin: 0 0 0.25rem 0;
        letter-spacing: -0.01em;
    }}
    p.section-caption {{
        font-size: 0.9rem;
        color: #6E6E73;
        margin-bottom: 1.25rem;
        line-height: 1.5;
    }}

    /* --- Métricas nativas (usadas solo en el panel de percentiles) --- */
    [data-testid="stMetricValue"] {{
        font-family: {FONT_MONO};
        font-variant-numeric: tabular-nums;
        color: #1D1D1F;
    }}
    [data-testid="stMetricLabel"] {{
        color: #6E6E73;
    }}

    /* --- Tabla de ranking --- */
    [data-testid="stDataFrame"] {{
        font-family: {FONT_SANS};
    }}
</style>
"""

st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


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
    # profile (public) al nombre de carpeta del modelo (marts).
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
    Usa raíz cuadrada para comprimir el efecto de outliers: una parada-hub
    con muchísimos más pasos que el resto no debe generar un círculo que
    eclipse visualmente al resto del mapa.
    """
    if vmax <= vmin:
        return (min_out + max_out) / 2
    t = (value**0.5 - vmin**0.5) / (vmax**0.5 - vmin**0.5)
    t = max(0.0, min(1.0, t))
    return min_out + t * (max_out - min_out)


def _mix(c1: tuple, c2: tuple, t: float) -> tuple:
    return tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))


def frequency_to_hex_color(value: float, vmax: float, vmin: float = 0.0) -> str:
    """
    Convierte un valor de buses/hora a un color hexadecimal, interpolando
    a través de los tres colores semánticos de sistema de Apple (rojo ->
    naranja -> verde), no un degradado genérico.

    vmax es un TECHO FIJO (criterio de negocio, ajustable desde la propia
    interfaz), no el máximo real del dataset — evita que una única parada
    con frecuencia extrema (un hub de intercambio) estire toda la escala y
    haga parecer "mal comunicadas" a paradas con servicio razonable.
    Valores por encima de vmax se recortan al verde.
    """
    t = 0.0 if vmax <= vmin else (value - vmin) / (vmax - vmin)
    t = max(0.0, min(1.0, t))

    if t < 0.5:
        r, g, b = _mix(COLOR_RED, COLOR_ORANGE, t / 0.5)
    else:
        r, g, b = _mix(COLOR_ORANGE, COLOR_GREEN, (t - 0.5) / 0.5)

    return f"#{r:02x}{g:02x}{b:02x}"


def render_section_header(eyebrow: str, title: str, caption: str) -> None:
    st.markdown(f'<div class="section-eyebrow">{eyebrow}</div>', unsafe_allow_html=True)
    st.markdown(f'<h2 class="section-title">{title}</h2>', unsafe_allow_html=True)
    st.markdown(f'<p class="section-caption">{caption}</p>', unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Cabecera
# ---------------------------------------------------------------------------

st.markdown('<div class="eyebrow">Transporte metropolitano · Sevilla</div>', unsafe_allow_html=True)
st.markdown('<h1 class="page-title">Cobertura de la red interurbana</h1>', unsafe_allow_html=True)
st.markdown(
    '<p class="page-subtitle">Frecuencia de autobuses por parada en la red gestionada '
    "por el Consorcio de Transporte de Sevilla (CTAN). Los datos se extraen y "
    "recalculan a diario de forma automática.</p>",
    unsafe_allow_html=True,
)

try:
    df = load_mart_data()
except Exception as exc:
    st.error(
        "No ha sido posible conectar con el almacén de datos. Comprueba que "
        f"Postgres está en marcha y que el pipeline se ha ejecutado al menos una vez.\n\n{exc}"
    )
    st.stop()

if df.empty:
    st.warning(
        "El mart de frecuencia no contiene datos todavía. Ejecuta el pipeline "
        "(extracción, carga y transformación) antes de abrir este panel."
    )
    st.stop()

# Percentiles sobre el conjunto completo (laborable + fin de semana
# combinados): el valor por defecto del umbral de color los necesita antes
# de que la persona usuaria haya interactuado con nada.
percentiles = df["buses_por_hora"].quantile([0.5, 0.75, 0.90, 0.95, 0.99]).round(2)
default_threshold = float(percentiles[0.90]) if percentiles[0.90] > 0 else 1.0

# Huecos reservados: la ficha técnica y el mapa se pintan aquí arriba, pero
# su contenido se calcula más abajo, una vez leídos los controles.
kpi_placeholder = st.empty()
map_placeholder = st.empty()

# ---------------------------------------------------------------------------
# Controles
# ---------------------------------------------------------------------------

with st.container(border=True):
    render_section_header(
        "Filtros",
        "Ajustar la vista",
        "Estos controles determinan qué se muestra en el mapa y en la ficha técnica de arriba.",
    )

    day_type = st.radio(
        "Tipo de día",
        options=["laborable", "fin_de_semana"],
        format_func=lambda x: DAY_TYPE_LABELS[x],
        horizontal=True,
        label_visibility="collapsed",
    )

    freq_threshold = st.slider(
        "Umbral de buen servicio (buses por hora)",
        min_value=0.5,
        max_value=max(15.0, float(df["buses_por_hora"].max())),
        value=default_threshold,
        step=0.5,
        help=(
            "A partir de este valor, una parada se muestra en verde. Por "
            "defecto corresponde al percentil 90 del conjunto completo, "
            "para que una parada con frecuencia excepcional no distorsione "
            "la lectura del resto de la red."
        ),
    )
    st.caption(
        f"En rojo, 0 buses por hora. En verde, {freq_threshold:.1f} buses por hora o más "
        f"— aproximadamente el percentil {(df['buses_por_hora'] <= freq_threshold).mean() * 100:.0f} "
        "del conjunto completo. El umbral es el mismo en ambas vistas, así que los colores son comparables entre ellas."
    )

    with st.expander("Ver distribución real de frecuencias"):
        st.caption(
            "Reparto de buses por hora entre las paradas (laborable y fin de "
            "semana combinados), como referencia para elegir el umbral."
        )

        pcol1, pcol2, pcol3, pcol4, pcol5 = st.columns(5)
        pcol1.metric("Mediana", percentiles[0.50])
        pcol2.metric("P75", percentiles[0.75])
        pcol3.metric("P90", percentiles[0.90])
        pcol4.metric("P95", percentiles[0.95])
        pcol5.metric("Máximo", f"{df['buses_por_hora'].max():.2f}")

        hist_df = pd.DataFrame({
            "buses_por_hora": df["buses_por_hora"].clip(upper=df["buses_por_hora"].quantile(0.99))
        })
        chart = (
            alt.Chart(hist_df)
            .mark_bar(color="#0071E3")
            .encode(
                x=alt.X("buses_por_hora:Q", bin=alt.Bin(maxbins=30), title="Buses por hora"),
                y=alt.Y("count()", title="Número de paradas"),
            )
            .configure_axis(labelFont=FONT_SANS, titleFont=FONT_SANS, gridColor="#EDEDF0")
            .configure_view(strokeWidth=0)
        )
        st.altair_chart(chart, use_container_width=True)
        st.caption(
            "El eje horizontal se recorta en el percentil 99 para mantener "
            "el histograma legible."
        )

# ---------------------------------------------------------------------------
# Cálculo, ya con los valores de los controles
# ---------------------------------------------------------------------------

filtered = df[df["day_type"] == day_type].copy()

filtered["color"] = filtered["buses_por_hora"].apply(
    lambda v: frequency_to_hex_color(v, vmax=freq_threshold)
)

size_min, size_max = filtered["total_pasadas"].min(), filtered["total_pasadas"].max()
filtered["marker_size"] = filtered["total_pasadas"].apply(
    lambda v: scale_marker_size(v, size_min, size_max)
)

peor = filtered.loc[filtered["buses_por_hora"].idxmin()]

with kpi_placeholder.container():
    st.markdown(
        f"""
        <div class="kpi-row">
            <div class="kpi">
                <div class="kpi-value">{len(filtered):,}</div>
                <div class="kpi-label">Paradas analizadas</div>
            </div>
            <div class="kpi">
                <div class="kpi-value">{filtered['buses_por_hora'].mean():.2f}</div>
                <div class="kpi-label">Frecuencia media (buses/hora)</div>
            </div>
            <div class="kpi">
                <div class="kpi-value">{peor['buses_por_hora']:.2f}</div>
                <div class="kpi-label">Frecuencia mínima — {peor['stop_name']}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with map_placeholder.container(border=True):
    render_section_header(
        "Cobertura por parada",
        "Mapa de frecuencia",
        "El tamaño de cada punto refleja el volumen de paradas de autobús; el color, la frecuencia de servicio.",
    )
    st.map(
        filtered,
        latitude="stop_lat",
        longitude="stop_lon",
        color="color",
        size="marker_size",
    )

# ---------------------------------------------------------------------------
# Ranking
# ---------------------------------------------------------------------------

st.write("")

with st.container(border=True):
    render_section_header(
        "Detalle",
        "Paradas con menor frecuencia",
        "Ordenadas de peor a mejor comunicada, según el filtro activo.",
    )

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