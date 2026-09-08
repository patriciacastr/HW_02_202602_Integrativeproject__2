"""
app.py — Fase 4: Dashboard Streamlit del proyecto Golden Hour.

Uso:
    streamlit run app/app.py

Principio de diseño (igual que metrics.py): este archivo NO inventa fórmulas
de métricas propias. Cuando hace falta recalcular algo por un filtro del
usuario, llama a funciones de src/metrics.py. Los datos pesados (matrices de
ruteo, geometrías) se leen precomputados de Fase 1-3 -- este dashboard nunca
llama a un motor de ruteo ni reconstruye un grafo.
"""
from __future__ import annotations

import sys
from pathlib import Path

# app.py vive en app/, pero necesita importar src/ desde la raíz del repo.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import geopandas as gpd
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src.config_loader import load_config
from src.metrics import brecha_critica, promedio_ponderado_por_nivel, resumen_kpis

st.set_page_config(page_title="Golden Hour Dashboard", layout="wide", page_icon="🏥")

cfg = load_config()

ID_DEMANDA = cfg.sigmed_col_codigo_cp
ID_FACILIDAD = cfg.renipress_col_codigo
COL_POBLACION = cfg.poblacion_col_total
# IMPORTANTE: la columna "UBIGEO" original de SIGMED/RENIPRESS quedó renombrada
# a "UBIGEO_punto" en Fase 1, porque colisionaba de nombre con el "UBIGEO" del
# polígono durante la validación de distrito declarado (ver poligonos.py).
COL_UBIGEO_DEMANDA = "UBIGEO_punto"
COL_UBIGEO_POLIGONO = cfg.poligonos_campo_ubigeo_distrito


# ---------------------------------------------------------------------------
# Carga de datos (todo precomputado en Fases 1-3; nada se calcula aquí salvo
# agregaciones ligeras sobre el subconjunto ya filtrado por el usuario)
# ---------------------------------------------------------------------------

@st.cache_data
def cargar_datos():
    demanda = gpd.read_parquet(Path(cfg.processed_dir) / "sigmed_clean.parquet")
    facilidades = gpd.read_parquet(Path(cfg.processed_dir) / "renipress_clean.parquet")
    acceso = pd.read_csv(Path(cfg.outputs_dir) / "acceso_tiempo_por_punto.csv")
    distritos = gpd.read_file(cfg.path_poligonos_gpkg_salida, layer="distrito")

    calidad_renipress = pd.read_csv(Path(cfg.outputs_dir) / "data_quality_report_renipress.csv")
    calidad_sigmed = pd.read_csv(Path(cfg.outputs_dir) / "data_quality_report_sigmed.csv")

    # Une cada punto de demanda con su tiempo de acceso ya calculado (Fase 3).
    # Puntos sin resultado de ruteo (fuera de la muestra, o sin establecimiento
    # resolutivo alcanzable) quedan fuera -- es la misma limitación de Fase 2/3.
    demanda[ID_DEMANDA] = demanda[ID_DEMANDA].astype(str)
    acceso[ID_DEMANDA] = acceso[ID_DEMANDA].astype(str)
    facilidades[ID_FACILIDAD] = facilidades[ID_FACILIDAD].astype(str)
    demanda_acceso = demanda.merge(acceso, on=ID_DEMANDA, how="inner")

    return demanda_acceso, facilidades, distritos, calidad_renipress, calidad_sigmed


@st.cache_data
def cargar_matriz_completa():
    """La matriz completa (demanda x TODOS los establecimientos) solo se usa
    para el simulador de escenarios -- es pesada, se cachea aparte."""
    matriz = pd.read_parquet(Path(cfg.path_routing_cache_dir) / "matrix_car_full.parquet")
    matriz[ID_DEMANDA] = matriz[ID_DEMANDA].astype(str)
    matriz[ID_FACILIDAD] = matriz[ID_FACILIDAD].astype(str)
    return matriz


demanda_acceso, facilidades, distritos, calidad_renipress, calidad_sigmed = cargar_datos()

DEPTO_COL = cfg.sigmed_col_departamento
PROV_COL = cfg.sigmed_col_provincia
DIST_COL = cfg.sigmed_col_distrito


# ---------------------------------------------------------------------------
# Sidebar -- filtros (departamento, provincia, categoría, institución, umbral)
# ---------------------------------------------------------------------------

st.sidebar.header("Filtros")

deptos_disponibles = sorted(demanda_acceso[DEPTO_COL].dropna().unique())
deptos_sel = st.sidebar.multiselect("Departamento", deptos_disponibles, default=deptos_disponibles)

demanda_tmp = demanda_acceso[demanda_acceso[DEPTO_COL].isin(deptos_sel)]
provincias_disponibles = sorted(demanda_tmp[PROV_COL].dropna().unique())
provincias_sel = st.sidebar.multiselect("Provincia", provincias_disponibles, default=provincias_disponibles)

categorias_disponibles = sorted(facilidades[cfg.renipress_col_categoria].dropna().unique())
categorias_sel = st.sidebar.multiselect("Categoría de establecimiento", categorias_disponibles, default=categorias_disponibles)

instituciones_disponibles = sorted(facilidades[cfg.renipress_col_institucion].dropna().unique())
instituciones_sel = st.sidebar.multiselect("Institución", instituciones_disponibles, default=instituciones_disponibles)

umbral_min = st.sidebar.slider("Umbral de tiempo crítico (min)", min_value=15, max_value=180, value=60, step=15)

solo_resolutivos_mapa = st.sidebar.checkbox("Mostrar solo establecimientos RESOLUTIVOS en el mapa", value=False)

# --- Aplicar filtros ---
demanda_f = demanda_acceso[
    demanda_acceso[DEPTO_COL].isin(deptos_sel) & demanda_acceso[PROV_COL].isin(provincias_sel)
].copy()

facilidades_f = facilidades[
    facilidades[cfg.renipress_col_departamento].isin(deptos_sel)
    & facilidades[cfg.renipress_col_categoria].isin(categorias_sel)
    & facilidades[cfg.renipress_col_institucion].isin(instituciones_sel)
].copy()
if solo_resolutivos_mapa:
    facilidades_f = facilidades_f[facilidades_f["es_resolutivo"]]

if demanda_f.empty:
    st.warning("No hay puntos de demanda para los filtros seleccionados. Ajusta los filtros en la barra lateral.")
    st.stop()


# ---------------------------------------------------------------------------
# Título + KPI header
# ---------------------------------------------------------------------------

st.title("🏥 Golden Hour — Acceso a salud resolutiva")
st.caption("Lambayeque (costa) · Ayacucho (andino) · San Martín (amazónico)")

kpis = resumen_kpis(demanda_f, COL_POBLACION, umbral_min).iloc[0]

col1, col2, col3, col4 = st.columns(4)
col1.metric("Población evaluada", f"{kpis['poblacion_total']:,.0f}")
col2.metric(
    f"Población a más de {umbral_min} min",
    f"{kpis['poblacion_sobre_umbral']:,.0f}",
    f"{kpis['pct_sobre_umbral']:.1f}%",
    delta_color="inverse",
)
col3.metric("Tiempo promedio ponderado", f"{kpis['t_min_promedio_ponderado']:.1f} min")
col4.metric("Tiempo mediana", f"{kpis['t_min_mediana']:.1f} min")


# ---------------------------------------------------------------------------
# Mapa coroplético -- tiempo de acceso promedio ponderado por distrito
# ---------------------------------------------------------------------------

st.subheader("Tiempo de acceso por distrito")

prom_distrito = promedio_ponderado_por_nivel(demanda_f, COL_UBIGEO_DEMANDA, COL_POBLACION)
prom_distrito = prom_distrito.rename(columns={COL_UBIGEO_DEMANDA: COL_UBIGEO_POLIGONO})

distritos_mapa = distritos.merge(prom_distrito, on=COL_UBIGEO_POLIGONO, how="inner")

if distritos_mapa.empty:
    st.info("Ningún distrito con datos para los filtros actuales.")
else:
    fig_mapa = px.choropleth_map(
        distritos_mapa,
        geojson=distritos_mapa.set_index(COL_UBIGEO_POLIGONO).geometry,
        locations=COL_UBIGEO_POLIGONO,
        color="t_min_promedio_ponderado",
        hover_name="DISTRITO",
        hover_data={"poblacion_total": True, "n_puntos": True, COL_UBIGEO_POLIGONO: False},
        color_continuous_scale="RdYlGn_r",
        map_style="open-street-map",
        center={"lat": distritos_mapa.geometry.centroid.y.mean(), "lon": distritos_mapa.geometry.centroid.x.mean()},
        zoom=5.5,
        opacity=0.75,
        labels={"t_min_promedio_ponderado": "Min. promedio"},
    )
    fig_mapa.update_layout(margin={"r": 0, "t": 0, "l": 0, "b": 0}, height=500)
    st.plotly_chart(fig_mapa, use_container_width=True)


# ---------------------------------------------------------------------------
# Capa de establecimientos
# ---------------------------------------------------------------------------

st.subheader("Establecimientos de salud")

if facilidades_f.empty:
    st.info("Ningún establecimiento para los filtros actuales.")
else:
    fig_facilidades = px.scatter_map(
        facilidades_f,
        lat=facilidades_f.geometry.y,
        lon=facilidades_f.geometry.x,
        color="es_resolutivo",
        hover_name=cfg.renipress_col_institucion,
        hover_data={cfg.renipress_col_categoria: True, cfg.renipress_col_estado: True},
        color_discrete_map={True: "#2ca02c", False: "#7f7f7f"},
        labels={"es_resolutivo": "Resolutivo"},
        map_style="open-street-map",
        zoom=5.5,
        height=450,
    )
    fig_facilidades.update_layout(margin={"r": 0, "t": 0, "l": 0, "b": 0})
    st.plotly_chart(fig_facilidades, use_container_width=True)


# ---------------------------------------------------------------------------
# Distribución del tiempo de acceso
# ---------------------------------------------------------------------------

st.subheader("Distribución del tiempo de acceso")
fig_hist = px.histogram(
    demanda_f, x="t_min", nbins=40, color=DEPTO_COL,
    labels={"t_min": "Tiempo de acceso (min)"}, barmode="overlay", opacity=0.7,
)
st.plotly_chart(fig_hist, use_container_width=True)


# ---------------------------------------------------------------------------
# Ranking de brecha crítica + descarga
# ---------------------------------------------------------------------------

st.subheader("Distritos con peor acceso (dentro de los filtros actuales)")
top_n = st.slider("Cantidad de distritos a mostrar", 5, 30, cfg.get("top_n_brecha_critica", 15))
brecha = brecha_critica(prom_distrito.rename(columns={COL_UBIGEO_POLIGONO: COL_UBIGEO_DEMANDA}), COL_UBIGEO_DEMANDA, top_n)
brecha = brecha.merge(
    distritos[[COL_UBIGEO_POLIGONO, "DISTRITO", "PROVINCIA"]],
    left_on=COL_UBIGEO_DEMANDA, right_on=COL_UBIGEO_POLIGONO, how="left",
)
tabla_mostrar = brecha[["ranking", "DISTRITO", "PROVINCIA", "t_min_promedio_ponderado", "poblacion_total", "n_puntos"]]
st.dataframe(tabla_mostrar, use_container_width=True, hide_index=True)
st.download_button(
    "Descargar tabla como CSV", tabla_mostrar.to_csv(index=False).encode("utf-8"),
    file_name="brecha_critica_filtrada.csv", mime="text/csv",
)


# ---------------------------------------------------------------------------
# Simulador de escenarios: "¿qué pasa si convierto este I-3/I-4 en resolutivo?"
# ---------------------------------------------------------------------------

st.subheader("🔧 Simulador: convertir un establecimiento en resolutivo")

no_resolutivos = facilidades[
    (~facilidades["es_resolutivo"]) & facilidades[cfg.renipress_col_departamento].isin(deptos_sel)
].copy()
no_resolutivos["etiqueta"] = (
    no_resolutivos[cfg.renipress_col_institucion].astype(str) + " — "
    + no_resolutivos[cfg.renipress_col_distrito].astype(str)
    + " (" + no_resolutivos[cfg.renipress_col_categoria].astype(str) + ")"
)

if no_resolutivos.empty:
    st.info("No hay establecimientos no-resolutivos en los departamentos seleccionados.")
else:
    seleccion = st.selectbox("Elige un establecimiento a 'upgradear'", no_resolutivos["etiqueta"])
    fid_seleccionado = no_resolutivos.loc[no_resolutivos["etiqueta"] == seleccion, ID_FACILIDAD].iloc[0]

    if st.button("Simular"):
        matriz_completa = cargar_matriz_completa()
        candidato = matriz_completa[
            (matriz_completa[ID_FACILIDAD] == fid_seleccionado) & matriz_completa["routable"]
        ][[ID_DEMANDA, "duracion_min"]].rename(columns={"duracion_min": "t_min_candidato"})

        simulado = demanda_f.merge(candidato, on=ID_DEMANDA, how="left")
        simulado["t_min_nuevo"] = simulado[["t_min", "t_min_candidato"]].min(axis=1, skipna=True)

        antes = resumen_kpis(demanda_f, COL_POBLACION, umbral_min).iloc[0]
        despues_df = simulado.copy()
        despues_df["t_min"] = despues_df["t_min_nuevo"]
        despues = resumen_kpis(despues_df, COL_POBLACION, umbral_min).iloc[0]

        ganancia_poblacion = antes["poblacion_sobre_umbral"] - despues["poblacion_sobre_umbral"]

        c1, c2, c3 = st.columns(3)
        c1.metric(f"Población sobre {umbral_min} min -- ANTES", f"{antes['poblacion_sobre_umbral']:,.0f}")
        c2.metric(f"Población sobre {umbral_min} min -- DESPUÉS", f"{despues['poblacion_sobre_umbral']:,.0f}")
        c3.metric("Población que GANA acceso", f"{ganancia_poblacion:,.0f}")


# ---------------------------------------------------------------------------
# Panel de calidad de datos (Fase 1)
# ---------------------------------------------------------------------------

with st.expander("📋 Calidad de datos (Fase 1)"):
    st.markdown("**RENIPRESS**")
    st.dataframe(calidad_renipress, use_container_width=True, hide_index=True)
    st.markdown("**SIGMED**")
    st.dataframe(calidad_sigmed, use_container_width=True, hide_index=True)
