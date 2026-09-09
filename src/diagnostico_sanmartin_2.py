"""
diagnostico_sanmartin_2.py — revisa la fuente CRUDA de población (antes del
cruce espacial) para saber si los ceros en San Martín vienen del dato
original o de un bug en el cruce.

Uso:
    python -m src.diagnostico_sanmartin_2
"""
import geopandas as gpd
from src.config_loader import load_config

cfg = load_config()

poblacion = gpd.read_file(cfg.path_poblacion_raw)
print("Columnas disponibles:", poblacion.columns.tolist())
print()

print("Valores únicos en la columna de departamento (fuente de población):")
print(poblacion[cfg.poblacion_col_departamento].unique())
print()

for dep in cfg.departamentos:
    sub = poblacion[poblacion[cfg.poblacion_col_departamento] == dep]
    print(f"--- {dep!r} en la fuente CRUDA de población ---")
    print(f"  Centros poblados encontrados: {len(sub)}")
    if len(sub) > 0:
        print(f"  Población total (cruda, antes de cualquier cruce): {sub[cfg.poblacion_col_total].sum()}")
        print(f"  Población promedio por centro poblado: {sub[cfg.poblacion_col_total].mean():.1f}")
        print(f"  Cuántos tienen población = 0: {(sub[cfg.poblacion_col_total] == 0).sum()} de {len(sub)}")
    print()
