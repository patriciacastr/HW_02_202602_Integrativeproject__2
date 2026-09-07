"""
inspect_raw_data.py — Fase 1 (previo): inspecciona los archivos crudos ya
descargados para descubrir nombres reales de columnas, valores de categoría/
estado operativo, y sistema de coordenadas — ANTES de escribir el pipeline
de validación real.

No modifica nada. Solo imprime en pantalla.

Uso:
    python -m src.inspect_raw_data
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from src.config_loader import load_config


def _print_header(title: str) -> None:
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def inspect_renipress(path: str | Path) -> None:
    path = Path(path)
    if not path.exists():
        print(f"\n[AVISO] No se encontró {path} — descárgalo primero (ver README).")
        return

    _print_header(f"RENIPRESS — {path}")
    # RENIPRESS suele venir en latin-1 o utf-8, y separado por ',' o ';'
    # (exportes de Excel en configuración regional español usan ';'). Probamos
    # combinaciones hasta que una funcione razonablemente.
    df = None
    intentos = []
    for enc in ("utf-8", "latin-1"):
        try:
            candidato = pd.read_csv(path, encoding=enc, sep=None, engine="python")
            if candidato.shape[1] > 1:  # si solo detectó 1 columna, algo salió mal igual
                df = candidato
                print(f"Leído con encoding='{enc}', separador autodetectado")
                break
            intentos.append(f"{enc}: autodetectado dio 1 sola columna")
        except (UnicodeDecodeError, pd.errors.ParserError) as exc:
            intentos.append(f"{enc}: {exc}")
            continue

    if df is None:
        print("[ERROR] No se pudo leer el CSV automáticamente. Intentos:")
        for i in intentos:
            print(f"  - {i}")
        print(
            "Abre el archivo en un editor de texto (no Excel) y revisa manualmente "
            "el separador real (',' ';' o tab) y el encoding, luego ajusta este script."
        )
        return

    print(f"{len(df)} filas, {len(df.columns)} columnas")

    print("\nColumnas:")
    print(list(df.columns))

    print("\nPrimeras 3 filas:")
    print(df.head(3).to_string())

    # Búsqueda heurística de columnas de interés por nombre parecido
    candidatas_categoria = [c for c in df.columns if "categ" in c.lower()]
    candidatas_estado = [c for c in df.columns if "estado" in c.lower() or "condic" in c.lower()]
    candidatas_lat = [c for c in df.columns if "lat" in c.lower() or "norte" in c.lower()]
    candidatas_lon = [c for c in df.columns if "lon" in c.lower() or "este" in c.lower()]
    candidatas_codigo = [c for c in df.columns if "codigo" in c.lower() or "cod_" in c.lower()]

    for etiqueta, candidatas in [
        ("categoría", candidatas_categoria),
        ("estado operativo", candidatas_estado),
        ("latitud", candidatas_lat),
        ("longitud", candidatas_lon),
        ("código único", candidatas_codigo),
    ]:
        print(f"\nPosibles columnas de {etiqueta}: {candidatas}")
        for c in candidatas:
            valores = df[c].dropna().unique()[:15]
            print(f"  {c!r} — {len(df[c].unique())} valores únicos, muestra: {list(valores)}")


def inspect_shapefile(path: str | Path, titulo: str) -> None:
    path = Path(path)
    if not path.exists():
        print(f"\n[AVISO] No se encontró {path} — descárgalo primero (ver README).")
        return

    _print_header(f"{titulo} — {path}")
    try:
        import geopandas as gpd
    except ImportError:
        print("[ERROR] Falta geopandas. Instala con: pip install geopandas")
        return

    gdf = gpd.read_file(path)
    print(f"{len(gdf)} filas, {len(gdf.columns)} columnas")
    print(f"CRS (sistema de coordenadas): {gdf.crs}")

    print("\nColumnas:")
    print(list(gdf.columns))

    print("\nPrimeras 3 filas (sin geometría completa):")
    cols_sin_geom = [c for c in gdf.columns if c != "geometry"]
    print(gdf[cols_sin_geom].head(3).to_string())

    print("\nTipo de geometría:", gdf.geometry.geom_type.unique())
    print("Bounding box de los datos:", gdf.total_bounds)

    candidatas_pob = [c for c in gdf.columns if "pob" in c.lower()]
    candidatas_dist = [c for c in gdf.columns if "dist" in c.lower()]
    candidatas_ubigeo = [c for c in gdf.columns if "ubigeo" in c.lower()]
    candidatas_codigo_cp = [c for c in gdf.columns if "cod" in c.lower() and "cp" in c.lower()]
    candidatas_departamento = [c for c in gdf.columns if "dep" in c.lower()]

    for etiqueta, candidatas in [
        ("población", candidatas_pob),
        ("distrito", candidatas_dist),
        ("ubigeo", candidatas_ubigeo),
        ("código de centro poblado", candidatas_codigo_cp),
        ("departamento", candidatas_departamento),
    ]:
        print(f"\nPosibles columnas de {etiqueta}: {candidatas}")
        for c in candidatas:
            valores = gdf[c].dropna().unique()[:10]
            print(f"  {c!r} — muestra: {list(valores)}")


def main() -> None:
    cfg = load_config()
    inspect_renipress(cfg.get("path_renipress_raw", "data/raw/renipress.csv"))
    inspect_shapefile(cfg.get("path_sigmed_raw", "data/raw/sigmed/CP_P.shp"), "SIGMED (shapefile)")

    # Población: puede ser el .geojson de SIGRID (si la descarga automática funcionó)
    # o el shapefile manual de GeoPerú (fuente de respaldo, ver config.md)
    path_poblacion = Path(cfg.get("path_poblacion_raw", "data/raw/poblacion_centros_poblados.geojson"))
    path_poblacion_geoperu = Path("data/raw/poblacion_centros_poblados_geoperu")
    if path_poblacion.exists():
        inspect_shapefile(path_poblacion, "Población (SIGRID)")
    elif path_poblacion_geoperu.exists():
        shp_files = list(path_poblacion_geoperu.glob("*.shp"))
        if shp_files:
            inspect_shapefile(shp_files[0], "Población (GeoPerú/INEI, respaldo manual)")
        else:
            print(f"\n[AVISO] {path_poblacion_geoperu} existe pero no tiene ningún .shp adentro.")
    else:
        print(
            f"\n[AVISO] No se encontró población ni en {path_poblacion} ni en "
            f"{path_poblacion_geoperu}/ — ver config.md para las dos fuentes posibles."
        )

    print("\n" + "=" * 70)
    print(
        "Siguiente paso: con los nombres reales de columnas de arriba, actualiza "
        "config.md (estado_operativo_valido, categorias_resolutivas, y si usaste "
        "GeoPerú también poblacion_col_codigo_cp/poblacion_col_total) y ajusta "
        "run_phase1.py si el nombre de archivo de población cambió."
    )


if __name__ == "__main__":
    sys.exit(main())
