"""
diagnostico_sanmartin.py — script de UN SOLO USO para averiguar por qué San
Martín sale con barras casi invisibles en fig_cobertura_bandas_departamento.

Uso:
    python -m src.diagnostico_sanmartin
"""
from src.config_loader import load_config
from src.export import _cargar_demanda_acceso

cfg = load_config()
col_dep = cfg.sigmed_col_departamento
col_pob = cfg.poblacion_col_total

demanda_acceso = _cargar_demanda_acceso(cfg)

print("Valores únicos en la columna de departamento:")
print(demanda_acceso[col_dep].unique())
print()

for dep in demanda_acceso[col_dep].dropna().unique():
    sub = demanda_acceso[demanda_acceso[col_dep] == dep]
    print(f"--- {dep!r} ---")
    print(f"  Filas totales: {len(sub)}")
    print(f"  Filas con t_min no nulo: {sub['t_min'].notna().sum()}")
    print(f"  Filas con población no nula: {sub[col_pob].notna().sum()}")
    print(f"  Suma de población (con NaN excluidos): {sub[col_pob].sum()}")
    print(f"  Tipo de dato de la columna población: {sub[col_pob].dtype}")
    print()
