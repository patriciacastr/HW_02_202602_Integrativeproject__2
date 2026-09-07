"""
routing.py — Fase 2: cálculo de tiempos/distancias de viaje usando OSRM.

Requiere que los 3 servidores OSRM (car/foot/bike) estén corriendo localmente
(ver docker-compose.yml y README, sección "Fase 2 — Ruteo").

Diseño (documentar en el reporte, sección Discusión / Decisiones técnicas):
  - Perfil CAR: matriz completa demanda x TODOS los establecimientos (resolutivos
    y no-resolutivos). Se necesita completa porque el simulador de escenarios de
    Fase 4 permite "upgradear" un establecimiento I-3/I-4 a resolutivo y mostrar
    la ganancia de cobertura -- para eso hace falta la distancia a ESE
    establecimiento no-resolutivo también, no solo a los ya-resolutivos.
  - Perfiles FOOT y BIKE: matriz solo contra establecimientos RESOLUTIVOS (set
    mucho más chico). El enunciado solo pide comparar el tiempo al hospital
    resolutivo más cercano entre los tres modos, no la matriz completa a pie/
    bici contra todos los establecimientos. Esto reduce el cómputo drásticamente
    sin perder ningún requisito de la tarea.
  - OSRM /table tiene un límite --max-table-size (filas x columnas por request,
    fijado en docker-compose.yml). Por eso el tamaño de chunk de orígenes se
    calcula dinámicamente según cuántos destinos haya, no es un número fijo.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import requests

from src.config_loader import Config

log = logging.getLogger("routing")

_PUERTOS = {"car": "osrm_puerto_car", "foot": "osrm_puerto_foot", "bike": "osrm_puerto_bike"}


def osrm_base_url(profile: str, cfg: Config) -> str:
    puerto = cfg.get(_PUERTOS[profile])
    return f"http://localhost:{puerto}"


def check_osrm_health(profile: str, cfg: Config) -> bool:
    """Prueba rápida: pide una ruta trivial para confirmar que el servidor responde."""
    url = f"{osrm_base_url(profile, cfg)}/nearest/v1/{profile}/-77.0,-12.0"
    try:
        r = requests.get(url, timeout=5)
        ok = r.status_code == 200
        log.info("OSRM %s (%s): %s", profile, url, "OK" if ok else f"status={r.status_code}")
        return ok
    except requests.exceptions.RequestException as exc:
        log.error("OSRM %s no responde en %s -- %s", profile, url, exc)
        return False


def _coords_str(gdf: gpd.GeoDataFrame) -> str:
    """OSRM espera 'lon,lat;lon,lat;...' en el orden de las filas del GeoDataFrame."""
    return ";".join(f"{geom.x},{geom.y}" for geom in gdf.geometry)


def _call_osrm_table(
    origenes: gpd.GeoDataFrame,
    destinos: gpd.GeoDataFrame,
    profile: str,
    cfg: Config,
) -> dict:
    """
    Llama a /table/v1/{profile} para un bloque de orígenes x destinos.
    Devuelve el JSON crudo de OSRM (durations, distances, sources, destinations).
    """
    n_o, n_d = len(origenes), len(destinos)
    coords = _coords_str(pd.concat([origenes.geometry.to_frame(), destinos.geometry.to_frame()]).set_geometry("geometry"))
    idx_src = ";".join(str(i) for i in range(n_o))
    idx_dst = ";".join(str(i) for i in range(n_o, n_o + n_d))

    url = f"{osrm_base_url(profile, cfg)}/table/v1/{profile}/{coords}"
    params = {
        "sources": idx_src,
        "destinations": idx_dst,
        "annotations": "duration,distance",
    }
    r = requests.get(url, params=params, timeout=120)
    r.raise_for_status()
    data = r.json()
    if data.get("code") != "Ok":
        raise RuntimeError(f"OSRM table respondió code={data.get('code')}: {data.get('message')}")
    return data


def _chunk_size_dinamico(n_destinos: int, cfg: Config) -> int:
    """Cuántos orígenes caben por request dado --max-table-size y el número de destinos."""
    max_table = cfg.get("osrm_max_table_size", 8000)
    tope = cfg.get("ruteo_chunk_size_origenes", 200)
    if n_destinos == 0:
        return tope
    calculado = max(1, max_table // n_destinos)
    return min(tope, calculado)


def compute_matrix(
    demanda: gpd.GeoDataFrame,
    facilidades: gpd.GeoDataFrame,
    profile: str,
    cfg: Config,
    id_col_demanda: str,
    id_col_facilidad: str,
    cache_path: str | Path,
) -> pd.DataFrame:
    """
    Calcula (o carga desde caché) la matriz origen x facilidad para un perfil.
    Devuelve un DataFrame largo: [id_demanda, id_facilidad, duracion_min,
    distancia_km, snap_dist_origen_m, snap_dist_destino_m, routable].

    Cachea en Parquet: si cache_path ya existe, se carga tal cual y NO se
    recalcula (borra el archivo manualmente si necesitas forzar un recálculo).
    """
    cache_path = Path(cache_path)
    if cache_path.exists():
        log.info("Caché encontrada en %s, cargando sin recalcular", cache_path)
        return pd.read_parquet(cache_path)

    n_destinos = len(facilidades)
    chunk = _chunk_size_dinamico(n_destinos, cfg)
    log.info(
        "Calculando matriz perfil=%s: %d orígenes x %d destinos, chunk de %d orígenes por request",
        profile, len(demanda), n_destinos, chunk,
    )

    filas = []
    n_chunks = (len(demanda) + chunk - 1) // chunk
    t0 = time.time()

    for i in range(0, len(demanda), chunk):
        bloque = demanda.iloc[i : i + chunk]
        n_actual = i // chunk + 1
        try:
            data = _call_osrm_table(bloque, facilidades, profile, cfg)
        except (requests.exceptions.RequestException, RuntimeError) as exc:
            log.error(
                "Chunk %d/%d falló (%s) -- se marca todo el bloque como no-ruteable y se continúa",
                n_actual, n_chunks, exc,
            )
            for _, fila_origen in bloque.iterrows():
                for _, fila_dest in facilidades.iterrows():
                    filas.append({
                        id_col_demanda: fila_origen[id_col_demanda],
                        id_col_facilidad: fila_dest[id_col_facilidad],
                        "duracion_min": np.nan,
                        "distancia_km": np.nan,
                        "snap_dist_origen_m": np.nan,
                        "snap_dist_destino_m": np.nan,
                        "routable": False,
                    })
            continue

        durations = data["durations"]  # segundos, [n_o][n_d]
        distances = data["distances"]  # metros
        snap_o = [s["distance"] if s else np.nan for s in data["sources"]]
        snap_d = [d["distance"] if d else np.nan for d in data["destinations"]]

        for oi, (_, fila_origen) in enumerate(bloque.iterrows()):
            for di, (_, fila_dest) in enumerate(facilidades.iterrows()):
                dur = durations[oi][di]
                dist = distances[oi][di]
                filas.append({
                    id_col_demanda: fila_origen[id_col_demanda],
                    id_col_facilidad: fila_dest[id_col_facilidad],
                    "duracion_min": (dur / 60.0) if dur is not None else np.nan,
                    "distancia_km": (dist / 1000.0) if dist is not None else np.nan,
                    "snap_dist_origen_m": snap_o[oi],
                    "snap_dist_destino_m": snap_d[di],
                    "routable": dur is not None,
                })

        if n_actual % 5 == 0 or n_actual == n_chunks:
            log.info("  chunk %d/%d completado (%.1fs transcurridos)", n_actual, n_chunks, time.time() - t0)

    df = pd.DataFrame(filas)

    n_no_routable = int((~df["routable"]).sum())
    log.info(
        "Matriz %s completa: %d pares, %d no-ruteables (%.2f%%). Snap origen promedio=%.1fm, destino promedio=%.1fm",
        profile, len(df), n_no_routable,
        100 * n_no_routable / len(df) if len(df) else 0,
        df["snap_dist_origen_m"].mean(), df["snap_dist_destino_m"].mean(),
    )

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(cache_path)
    log.info("Guardado %s (%d filas)", cache_path, len(df))
    return df


def muestrear_demanda(
    demanda: gpd.GeoDataFrame,
    cfg: Config,
    col_poblacion: str,
    col_distrito: str,
) -> gpd.GeoDataFrame:
    """
    Si la demanda excede max_demand_points, aplica muestreo estratificado por
    distrito y ponderado por población (estrategia declarada en config.md).
    Si no se excede, devuelve la demanda intacta.
    """
    tope = cfg.get("max_demand_points", 5000)
    if len(demanda) <= tope:
        log.info("Demanda (%d) no excede max_demand_points (%d) -- sin muestreo", len(demanda), tope)
        return demanda

    log.warning(
        "Demanda (%d) excede max_demand_points (%d) -- aplicando muestreo "
        "poblacional estratificado por distrito. Esto introduce error de "
        "muestreo: documentar en Fase 5.",
        len(demanda), tope,
    )

    peso = demanda[col_poblacion].fillna(1.0).clip(lower=1.0)
    frac = tope / len(demanda)
    rng = np.random.default_rng(42)

    partes = []
    for distrito, grupo in demanda.groupby(col_distrito):
        n_grupo = min(max(1, round(len(grupo) * frac)), len(grupo))
        pesos_grupo = peso.loc[grupo.index].to_numpy(dtype=float)
        probs = pesos_grupo / pesos_grupo.sum()
        # np.random.Generator.choice maneja sin problema pesos muy sesgados
        # (ej. un centro poblado con población mucho mayor al resto del
        # distrito), a diferencia de pandas.sample(weights=...) que a veces
        # rechaza esa combinación con replace=False.
        idx_seleccionados = rng.choice(grupo.index.to_numpy(), size=n_grupo, replace=False, p=probs)
        partes.append(grupo.loc[idx_seleccionados])

    resultado = pd.concat(partes)
    log.info(
        "Muestreo completado: %d -> %d puntos de demanda (%.1f%% de la población total conservada: %.2f%%)",
        len(demanda), len(resultado),
        100 * len(resultado) / len(demanda),
        100 * resultado[col_poblacion].sum() / demanda[col_poblacion].sum(),
    )
    return gpd.GeoDataFrame(resultado, geometry="geometry", crs=demanda.crs)
