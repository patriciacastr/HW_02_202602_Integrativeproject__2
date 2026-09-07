"""
obtener_bboxes.py — Script auxiliar de UN SOLO USO (no es parte del pipeline
de Fases 1-5). Calcula el bounding box de cada departamento a partir de
data/processed/poligonos.gpkg (ya generado en Fase 1), con un margen de
0.3 grados (~30km) para no perder carreteras que crucen justo la frontera
departamental.

Uso:
    python -m src.obtener_bboxes

Imprime, para cada departamento, la línea lista para copiar/pegar en el
comando de osmium extract (formato: min_lon,min_lat,max_lon,max_lat).
"""
from __future__ import annotations

import geopandas as gpd

from src.config_loader import load_config

MARGEN_GRADOS = 0.3  # ~30km de buffer; documentar como supuesto en el reporte


def main() -> None:
    cfg = load_config()
    gdf = gpd.read_file(cfg.get("path_poligonos_gpkg_salida"), layer="departamento")

    campo_depto = cfg.get("poligonos_campo_departamento", "DEPARTAMEN")

    print(f"{'Departamento':15s} {'bbox (min_lon,min_lat,max_lon,max_lat)'}")
    print("-" * 70)
    for _, fila in gdf.iterrows():
        nombre = fila[campo_depto]
        minx, miny, maxx, maxy = fila.geometry.bounds
        bbox = (
            f"{minx - MARGEN_GRADOS:.4f},{miny - MARGEN_GRADOS:.4f},"
            f"{maxx + MARGEN_GRADOS:.4f},{maxy + MARGEN_GRADOS:.4f}"
        )
        print(f"{nombre:15s} {bbox}")


if __name__ == "__main__":
    main()
