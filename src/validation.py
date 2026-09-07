"""
validation.py — Fase 1: capa de validación y reporte de calidad de datos.

Cada función `check_*` recibe un DataFrame y devuelve:
    (dataframe_anotado, resumen_dict)
donde dataframe_anotado añade una columna booleana `flag_<regla>` y
resumen_dict trae {"regla": ..., "n_flagged": ..., "accion": ..., "detalle": ...}.

No se elimina ninguna fila dentro de estas funciones: solo se marca.
La decisión de qué hacer con lo marcado (corregir, descartar, mantener con
advertencia) se toma explícitamente en `build_quality_report` / en el
pipeline que llama a este módulo, y debe quedar documentada en el reporte.
"""
from __future__ import annotations

from typing import Callable

import pandas as pd

from src.config_loader import Config


def check_missing_coords(df: pd.DataFrame, lat_col="latitud", lon_col="longitud"):
    flag = df[lat_col].isna() | df[lon_col].isna() | (df[lat_col] == 0) | (df[lon_col] == 0)
    df = df.assign(flag_missing_coords=flag)
    resumen = {
        "regla": "coordenadas_faltantes_o_cero",
        "n_flagged": int(flag.sum()),
        "accion": "descartar_de_computo_geoespacial (mantener fila, excluir de ruteo)",
    }
    return df, resumen


def check_bbox(df: pd.DataFrame, cfg: Config, lat_col="latitud", lon_col="longitud"):
    dentro = df[lon_col].between(cfg.lon_min, cfg.lon_max) & df[lat_col].between(
        cfg.lat_min, cfg.lat_max
    )
    flag = ~dentro & df[lat_col].notna() & df[lon_col].notna()
    df = df.assign(flag_fuera_bbox=flag)
    resumen = {
        "regla": "coordenadas_fuera_de_peru",
        "n_flagged": int(flag.sum()),
        "accion": "candidato_a_swap_lat_lon (ver check_swapped_coords) o descartar si no aplica",
    }
    return df, resumen


def check_swapped_coords(df: pd.DataFrame, cfg: Config, lat_col="latitud", lon_col="longitud"):
    """Si intercambiar lat/lon cae dentro del bbox de Perú, es candidato a swap."""
    swapped_dentro = df[lat_col].between(cfg.lon_min, cfg.lon_max) & df[lon_col].between(
        cfg.lat_min, cfg.lat_max
    )
    original_fuera = ~(
        df[lon_col].between(cfg.lon_min, cfg.lon_max) & df[lat_col].between(cfg.lat_min, cfg.lat_max)
    )
    flag = swapped_dentro & original_fuera
    df = df.assign(flag_lat_lon_invertidos=flag)
    resumen = {
        "regla": "lat_lon_invertidos",
        "n_flagged": int(flag.sum()),
        "accion": "corregir_automaticamente (swap) y registrar tasa de recuperación",
    }
    return df, resumen


def check_outside_declared_district(
    df: pd.DataFrame, point_in_polygon_fn: Callable[[pd.Series], bool]
):
    """point_in_polygon_fn recibe una fila y devuelve True si el punto cae dentro
    del polígono del distrito que la propia fila declara. Se inyecta como función
    para no acoplar este módulo a una librería geoespacial específica."""
    flag = ~df.apply(point_in_polygon_fn, axis=1)
    df = df.assign(flag_fuera_de_distrito_declarado=flag)
    resumen = {
        "regla": "punto_fuera_de_distrito_declarado",
        "n_flagged": int(flag.sum()),
        "accion": "mantener_con_advertencia (usar distrito por point-in-polygon real, no el declarado)",
    }
    return df, resumen


def check_duplicate_codes(df: pd.DataFrame, code_col="codigo_renipress"):
    flag = df.duplicated(subset=[code_col], keep=False) & df[code_col].notna()
    df = df.assign(flag_codigo_duplicado=flag)
    resumen = {
        "regla": "codigo_facility_duplicado",
        "n_flagged": int(flag.sum()),
        "accion": "mantener_primera_ocurrencia_descartar_resto (documentar criterio de cuál es 'primera')",
    }
    return df, resumen


def check_encoding_issues(df: pd.DataFrame, text_cols: list[str]):
    """Heurística simple: busca patrones típicos de mojibake latin-1 -> utf-8
    (ej. 'Ã±', 'Ã³', 'Â')."""
    mojibake_pat = r"Ã.|Â."
    flag = pd.Series(False, index=df.index)
    for col in text_cols:
        if col in df.columns:
            flag = flag | df[col].astype(str).str.contains(mojibake_pat, regex=True, na=False)
    df = df.assign(flag_posible_encoding_erroneo=flag)
    resumen = {
        "regla": "encoding_utf8_vs_latin1",
        "n_flagged": int(flag.sum()),
        "accion": "re-decodificar_columnas_afectadas y registrar tasa de recuperación",
    }
    return df, resumen


def build_quality_report(resumenes: list[dict], n_total: int) -> pd.DataFrame:
    reporte = pd.DataFrame(resumenes)
    reporte["pct_del_total"] = (reporte["n_flagged"] / n_total * 100).round(2)
    return reporte[["regla", "n_flagged", "pct_del_total", "accion"]]


if __name__ == "__main__":
    print(
        "Módulo de validación — importar y llamar las funciones check_* sobre el "
        "DataFrame de facilities cargado en el pipeline principal de Fase 1."
    )
