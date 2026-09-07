"""
run_phase1.py — Orquesta la Fase 1 completa: carga, filtra a los 3 departamentos,
valida, y exporta.

Uso:
    python -m src.run_phase1

Salidas:
    data/processed/renipress_clean.parquet   (GeoDataFrame con geometry de puntos)
    data/processed/sigmed_clean.parquet      (GeoDataFrame con geometry de puntos)
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

    # NOTA: check_outside_declared_district requiere polígonos distritales (no
    # descargados aún en esta fase). Se deja pendiente — ver TODO en config.md
    # (fuente_limites_administrativos) y en el README.
    log.warning(
        "check_outside_declared_district PENDIENTE: falta la fuente de polígonos "
        "administrativos (declarar en config.md -> fuente_limites_administrativos)."
    )

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

    print(
        "\nPENDIENTE antes de Fase 2:\n"
        "  1. Población por centro poblado (SIGMED no la trae) — ver config.md.\n"
        "  2. Polígonos distritales para check_outside_declared_district — ver config.md.\n"
    )


if __name__ == "__main__":
    run()
