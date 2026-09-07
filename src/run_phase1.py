"""
run_phase1.py — Orquesta la Fase 1 completa: carga, filtra a los 3 departamentos,
valida (incluyendo polígonos distritales), y exporta.

Uso:
    python -m src.run_phase1

Salidas:
    data/processed/renipress_clean.parquet   (GeoDataFrame con geometry de puntos)
    data/processed/sigmed_clean.parquet      (GeoDataFrame con geometry de puntos)
    data/processed/poligonos.gpkg            (capas: distrito, provincia, departamento)
    data/outputs/data_quality_report_renipress.csv
    data/outputs/data_quality_report_sigmed.csv
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

from src.config_loader import Config, load_config
from src.poligonos import (
    cargar_poligonos,
    guardar_poligonos_geopackage,
    validar_punto_en_distrito,
)
from src.validation import (
    build_quality_report,
    check_bbox,
    check_duplicate_codes,
    check_encoding_issues,
    check_missing_coords,
    check_swapped_coords,
)

Path("logs").mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(Path("logs") / "run_phase1.log", encoding="utf-8"),
    ],
)
log = logging.getLogger("run_phase1")


def _read_csv_flexible(path: Path) -> pd.DataFrame:
    """Detecta encoding y separador automáticamente (mismo enfoque que inspect_raw_data.py)."""
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            df = pd.read_csv(path, encoding=enc, sep=None, engine="python")
            if df.shape[1] > 1:
                log.info("RENIPRESS leído con encoding='%s' — %d filas, %d columnas", enc, len(
                    df), len(df.columns))
                return df
        except (UnicodeDecodeError, pd.errors.ParserError):
            continue
    raise RuntimeError(
        f"No se pudo leer {path} con ningún encoding/separador probado.")


def load_renipress(cfg: Config) -> gpd.GeoDataFrame:
    path = Path(cfg.path_renipress_raw)
    df = _read_csv_flexible(path)

    # normalizar nombres de columna (por si vienen con BOM, ya cubierto por utf-8-sig)
    df.columns = [c.strip() for c in df.columns]

    df = df[df[cfg.renipress_col_departamento].isin(cfg.departamentos)].copy()
    log.info("RENIPRESS filtrado a %s departamentos: %d filas",
             cfg.departamentos, len(df))

    # Normalizar categoría: valores en categorias_invalidas -> NaN
    df[cfg.renipress_col_categoria] = df[cfg.renipress_col_categoria].replace(
        {v: pd.NA for v in cfg.categorias_invalidas}
    )

    # Convertir a GeoDataFrame usando NORTE=lat, ESTE=lon
    lat = df[cfg.renipress_col_lat]
    lon = df[cfg.renipress_col_lon]
    geometry = [
        Point(lo, la) if pd.notna(lo) and pd.notna(la) else None for lo, la in zip(lon, lat)
    ]
    gdf = gpd.GeoDataFrame(df, geometry=geometry, crs="EPSG:4326")
    return gdf


def load_sigmed(cfg: Config) -> gpd.GeoDataFrame:
    path = Path(cfg.path_sigmed_raw)
    gdf = gpd.read_file(path)
    if gdf.crs is None or str(gdf.crs) != "EPSG:4326":
        log.warning("SIGMED CRS es %s, reproyectando a EPSG:4326", gdf.crs)
        gdf = gdf.to_crs("EPSG:4326")

    gdf = gdf[gdf[cfg.sigmed_col_departamento].isin(cfg.departamentos)].copy()
    log.info("SIGMED filtrado a %s departamentos: %d filas",
             cfg.departamentos, len(gdf))
    return gdf


def load_poblacion(cfg: Config) -> gpd.GeoDataFrame | None:
    path = Path(cfg.path_poblacion_raw)
    if not path.exists():
        log.warning(
            "No se encontró %s — ver config.md para la fuente de población (GeoPerú/INEI, "
            "descarga manual). Se continúa SIN datos de población por ahora.",
            path,
        )
        return None
    gdf = gpd.read_file(path)
    if gdf.crs is None or str(gdf.crs) != "EPSG:4326":
        gdf = gdf.to_crs("EPSG:4326")
    gdf = gdf[gdf[cfg.poblacion_col_departamento].isin(
        cfg.departamentos)].copy()
    log.info("Población (GeoPerú/INEI) leída: %d centros poblados", len(gdf))
    cols = [cfg.poblacion_col_total,
            cfg.poblacion_col_departamento, "geometry"]
    return gpd.GeoDataFrame(gdf[cols], geometry="geometry", crs="EPSG:4326")


def cruzar_poblacion(sigmed: gpd.GeoDataFrame, poblacion: gpd.GeoDataFrame | None, cfg: Config) -> gpd.GeoDataFrame:
    """Cruza SIGMED con la población por PROXIMIDAD ESPACIAL (no por código —
    los esquemas de codificación de SIGMED y GeoPerú/INEI no son compatibles,
    ver config.md). Usa vecino más cercano dentro de un radio máximo en metros."""
    if poblacion is None:
        return sigmed.assign(**{cfg.poblacion_col_total: pd.NA})

    antes = len(sigmed)
    max_dist = cfg.get("poblacion_max_distancia_metros", 500)

    # Reproyectar a Web Mercator (metros) solo para calcular distancias; el
    # resultado final se guarda en las coordenadas originales de sigmed (EPSG:4326).
    sigmed_m = sigmed.to_crs("EPSG:3857")
    poblacion_m = poblacion.to_crs("EPSG:3857")

    cruce = gpd.sjoin_nearest(
        sigmed_m,
        poblacion_m[[cfg.poblacion_col_total, "geometry"]],
        how="left",
        max_distance=max_dist,
        distance_col="_dist_poblacion_m",
    )
    # sjoin_nearest puede duplicar filas si hay empates a la misma distancia;
    # nos quedamos con el primer match por fila original.
    cruce = cruce[~cruce.index.duplicated(keep="first")]

    resultado = sigmed.copy()
    resultado[cfg.poblacion_col_total] = cruce[cfg.poblacion_col_total].values

    n_con_poblacion = resultado[cfg.poblacion_col_total].notna().sum()
    tasa = round(n_con_poblacion / antes * 100, 2) if antes else 0.0
    log.info(
        "Cruce espacial de población (radio %sm): %d/%d centros poblados con población asignada (%.2f%%)",
        max_dist,
        n_con_poblacion,
        antes,
        tasa,
    )
    if tasa < 80:
        log.warning(
            "Tasa de cruce de población baja (%.2f%%) — considera aumentar "
            "poblacion_max_distancia_metros en config.md si muchos SIGMED no tienen "
            "un centro poblado GeoPerú cercano, y documentar esto como limitación en Fase 5.",
            tasa,
        )
    return resultado


def validar_renipress(gdf: gpd.GeoDataFrame, cfg: Config) -> tuple[gpd.GeoDataFrame, pd.DataFrame]:
    resumenes = []
    df = gdf

    df, r = check_missing_coords(
        df, lat_col=cfg.renipress_col_lat, lon_col=cfg.renipress_col_lon)
    resumenes.append(r)

    df, r = check_bbox(df, cfg, lat_col=cfg.renipress_col_lat,
                       lon_col=cfg.renipress_col_lon)
    resumenes.append(r)

    df, r = check_swapped_coords(
        df, cfg, lat_col=cfg.renipress_col_lat, lon_col=cfg.renipress_col_lon)
    resumenes.append(r)

    df, r = check_duplicate_codes(df, code_col=cfg.renipress_col_codigo)
    resumenes.append(r)

    df, r = check_encoding_issues(
        df, text_cols=[cfg.renipress_col_institucion,
                       "NOMBRE", cfg.renipress_col_distrito]
    )
    resumenes.append(r)

    reporte = build_quality_report(resumenes, n_total=len(df))
    return df, reporte


def validar_sigmed(gdf: gpd.GeoDataFrame, cfg: Config) -> tuple[gpd.GeoDataFrame, pd.DataFrame]:
    resumenes = []
    df = gdf

    df, r = check_duplicate_codes(df, code_col=cfg.sigmed_col_codigo_cp)
    resumenes.append(r)

    df, r = check_encoding_issues(
        df, text_cols=[cfg.sigmed_col_nombre_cp, cfg.sigmed_col_distrito])
    resumenes.append(r)

    reporte = build_quality_report(resumenes, n_total=len(df))
    return df, reporte


def normalizar_resolutivo(gdf: gpd.GeoDataFrame, cfg: Config) -> gpd.GeoDataFrame:
    """Agrega la columna booleana `es_resolutivo` según categoría + estado operativo."""
    categoria = gdf[cfg.renipress_col_categoria]
    estado = gdf[cfg.renipress_col_estado]
    es_resolutivo = categoria.isin(cfg.categorias_resolutivas) & estado.isin(
        cfg.estado_operativo_valido)
    return gdf.assign(es_resolutivo=es_resolutivo)


def run() -> None:
    cfg = load_config()
    Path(cfg.processed_dir).mkdir(parents=True, exist_ok=True)
    Path(cfg.outputs_dir).mkdir(parents=True, exist_ok=True)

    log.info("=== Cargando RENIPRESS ===")
    renipress = load_renipress(cfg)
    renipress, reporte_renipress = validar_renipress(renipress, cfg)
    renipress = normalizar_resolutivo(renipress, cfg)

    n_resolutivos = int(renipress["es_resolutivo"].sum())
    log.info(
        "RENIPRESS: %d establecimientos totales, %d resolutivos y activos",
        len(renipress),
        n_resolutivos,
    )

    log.info("=== Cargando SIGMED ===")
    sigmed = load_sigmed(cfg)
    sigmed, reporte_sigmed = validar_sigmed(sigmed, cfg)

    log.info("=== Cruzando población ===")
    poblacion = load_poblacion(cfg)
    sigmed = cruzar_poblacion(sigmed, poblacion, cfg)

    log.info("=== Cargando polígonos administrativos ===")
    distrito = cargar_poligonos("distrito", cfg)
    provincia = cargar_poligonos("provincia", cfg)
    departamento = cargar_poligonos("departamento", cfg)

    guardar_poligonos_geopackage(
        {"distrito": distrito, "provincia": provincia, "departamento": departamento},
        cfg,
    )

    log.info("=== Validando puntos vs. distrito declarado ===")
    renipress = validar_punto_en_distrito(
        renipress, distrito, campo_ubigeo_punto=cfg.renipress_col_ubigeo, cfg=cfg
    )
    sigmed = validar_punto_en_distrito(
        sigmed, distrito, campo_ubigeo_punto=cfg.sigmed_col_ubigeo, cfg=cfg
    )

    # Exportar
    renipress_out = Path(cfg.processed_dir) / "renipress_clean.parquet"
    sigmed_out = Path(cfg.processed_dir) / "sigmed_clean.parquet"
    renipress.to_parquet(renipress_out)
    sigmed.to_parquet(sigmed_out)
    log.info("Guardado %s (%d filas)", renipress_out, len(renipress))
    log.info("Guardado %s (%d filas)", sigmed_out, len(sigmed))

    reporte_renipress_path = Path(
        cfg.outputs_dir) / "data_quality_report_renipress.csv"
    reporte_sigmed_path = Path(cfg.outputs_dir) / \
        "data_quality_report_sigmed.csv"
    reporte_renipress.to_csv(reporte_renipress_path, index=False)
    reporte_sigmed.to_csv(reporte_sigmed_path, index=False)

    print("\n" + "=" * 70)
    print("REPORTE DE CALIDAD — RENIPRESS")
    print("=" * 70)
    print(reporte_renipress.to_string(index=False))

    print("\n" + "=" * 70)
    print("REPORTE DE CALIDAD — SIGMED")
    print("=" * 70)
    print(reporte_sigmed.to_string(index=False))

    print("\n" + "=" * 70)
    print("VERIFICACIÓN — desglose de resolutivos por departamento")
    print("=" * 70)
    print(
        renipress.groupby(cfg.renipress_col_departamento)["es_resolutivo"]
        .agg(["sum", "count"])
        .rename(columns={"sum": "resolutivos", "count": "total"})
    )

    print("\nValores únicos de CATEGORIA (revisa que no haya espacios/variantes raras):")
    print(renipress[cfg.renipress_col_categoria].value_counts(dropna=False))

    print("\nValores únicos de ESTADO (revisa que 'ACTIVO' calce exacto):")
    print(renipress[cfg.renipress_col_estado].value_counts(dropna=False))


if __name__ == "__main__":
    run()
