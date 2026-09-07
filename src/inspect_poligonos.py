import geopandas as gpd

for nivel, ruta in [
    ("distrito", "data/raw/limites_geogpsperu/distrito/DISTRITOS.shp"),
    ("provincia", "data/raw/limites_geogpsperu/provincia/PROVINCIAS.shp"),
    ("departamento", "data/raw/limites_geogpsperu/departamento/DEPARTAMENTOS.shp"),
]:
    gdf = gpd.read_file(ruta)
    print(f"\n=== {nivel} ===")
    print("CRS:", gdf.crs)
    print("Columnas:", gdf.columns.tolist())
    print(gdf.head(2))
