import streamlit as st
import pandas as pd
import geopandas as gpd
import plotly.express as px

st.set_page_config(page_title="Golden Hour Dashboard", layout="wide")

@st.cache_data
def load_app_data():
    gdf_demand = gpd.read_parquet("data/processed/demand_points_clean.parquet")
    gdf_facilities = gpd.read_parquet("data/processed/facilities_clean.parquet")
    df_matrix = pd.read_parquet("data/processed/travel_time_matrix.parquet")
    df_quality = pd.read_csv("data/outputs/phase1_quality_report.csv")
    return gdf_demand, gdf_facilities, df_matrix, df_quality

gdf_demand, gdf_facilities, df_matrix, df_quality = load_app_data()

st.title("🏥 Dashboard: Proyecto Golden Hour")

st.sidebar.header("Filtro Departamental")
dept_names = {"14": "Lambayeque", "05": "Ayacucho", "22": "San Martín"}
available_deps = gdf_facilities['codigo_dep'].unique()

selected_deps = st.sidebar.multiselect(
    "Selecciona Departamentos:",
    options=available_deps,
    default=available_deps,
    format_func=lambda x: f"{x} - {dept_names.get(x, 'Otro')}"
)

fac_filtered = gdf_facilities[gdf_facilities['codigo_dep'].isin(selected_deps)]
matrix_filtered = df_matrix.loc[:, df_matrix.columns.isin(fac_filtered['codigo_unica'])]
t_min_series = matrix_filtered.min(axis=1)

col1, col2, col3 = st.columns(3)
total_pop = gdf_demand['poblacion'].sum()
pop_critical = gdf_demand[t_min_series > 60]['poblacion'].sum()

col1.metric("Población Evaluada", f"{total_pop:,.0f}")
col2.metric("Población a > 60 min", f"{pop_critical:,.0f}", f"{(pop_critical/total_pop)*100:.1f}%")
col3.metric("Mediana Tiempo de Traslado", f"{t_min_series.median():.1f} min")

st.subheader("Tiempo de Viaje a Centros Resolutivos")
fig = px.histogram(x=t_min_series, nbins=30, labels={'x': 'Tiempo de Traslado (Minutos)'})
st.plotly_chart(fig, use_container_width=True)

with st.expander("Calidad de Datos (Fase 1)"):
    st.dataframe(df_quality, use_container_width=True)

