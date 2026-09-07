"""
run_phase2.py — Orquesta la Fase 2: muestreo de demanda si excede
max_demand_points, cálculo de matrices de ruteo (car completo, foot/bike
solo contra resolutivos), y comparación entre modos.

Requiere los 3 servidores OSRM corriendo (ver docker-compose.yml):
    docker compose up -d

Uso:
    python -m src.run_phase2              # corrida completa
    python -m src.run_phase2 --prueba 20   # solo 20 puntos de demanda (para probar rápido)

Salidas:
    data/processed/routing_cache/matrix_car_full.parquet
    data/processed/routing_cache/matrix_foot_resolutivo.parquet
    data/processed/routing_cache/matrix_bike_resolutivo.parquet
    data/outputs/comparacion_modos.csv
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd

from src.config_loader import Config, load_config
from src.routing import check_osrm_health, compute_matrix, muestrear_demanda

Path("logs").mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(Path("logs") / "run_phase2.log", encoding="utf-8"),
    ],
)
log = logging.getLogger("run_phase2")


def cargar_facilidades(cfg: Config) -> gpd.GeoDataFrame:
    path = Path(cfg.processed_dir) / "renipress_clean.parquet"
    gdf = gpd.read_parquet(path)
    antes = len(gdf)
    gdf = gdf[gdf.geometry.notna()].copy()
    log.info(
        "Facilidades cargadas: %d totales, %d con coordenadas válidas (%d descartadas por falta de coordenadas)",
        antes, len(gdf), antes - len(gdf),
    )
    return gdf


def cargar_demanda(cfg: Config) -> gpd.GeoDataFrame:
    path = Path(cfg.processed_dir) / "sigmed_clean.parquet"
    gdf = gpd.read_parquet(path)
    antes = len(gdf)
    gdf = gdf[gdf.geometry.notna()].copy()
    log.info(
        "Demanda cargada: %d totales, %d con coordenadas válidas (%d descartadas)",
        antes, len(gdf), antes - len(gdf),
    )
    return gdf


def comparar_modos(
    matriz_car: pd.DataFrame,
    matriz_foot: pd.DataFrame,
    matriz_bike: pd.DataFrame,
    facilidades_resolutivas: gpd.GeoDataFrame,
    id_col_demanda: str,
    id_col_facilidad: str,
) -> pd.DataFrame:
    """
    Para cada punto de demanda, encuentra el establecimiento RESOLUTIVO más
    cercano bajo cada uno de los 3 perfiles, y arma la comparación pedida por
    el enunciado (caminando vs. auto; comparación cruzada de los 3 modos).
    """
    ids_resolutivos = set(facilidades_resolutivas[id_col_facilidad])

    def nearest_resolutivo(matriz: pd.DataFrame, sufijo: str) -> pd.DataFrame:
        sub = matriz[matriz[id_col_facilidad].isin(ids_resolutivos) & matriz["routable"]]
        idx_min = sub.groupby(id_col_demanda)["duracion_min"].idxmin()
        resultado = sub.loc[idx_min, [id_col_demanda, id_col_facilidad, "duracion_min", "distancia_km"]].copy()
        resultado = resultado.rename(columns={
            id_col_facilidad: f"facilidad_mas_cercana_{sufijo}",
            "duracion_min": f"duracion_min_{sufijo}",
            "distancia_km": f"distancia_km_{sufijo}",
        })
        return resultado.set_index(id_col_demanda)

    car_near = nearest_resolutivo(matriz_car, "car")
    foot_near = nearest_resolutivo(matriz_foot, "foot")
    bike_near = nearest_resolutivo(matriz_bike, "bike")

    comparacion = car_near.join(foot_near, how="outer").join(bike_near, how="outer").reset_index()

    comparacion["mismo_hospital_car_foot"] = (
        comparacion["facilidad_mas_cercana_car"] == comparacion["facilidad_mas_cercana_foot"]
    )
    comparacion["ratio_foot_car"] = comparacion["duracion_min_foot"] / comparacion["duracion_min_car"]
    comparacion["ratio_bike_car"] = comparacion["duracion_min_bike"] / comparacion["duracion_min_car"]

    n_distinto = int((~comparacion["mismo_hospital_car_foot"]).sum())
    log.info(
        "Comparación car vs. foot: %d de %d puntos (%.1f%%) tienen un hospital resolutivo MÁS CERCANO distinto "
        "según el modo de transporte",
        n_distinto, len(comparacion), 100 * n_distinto / len(comparacion) if len(comparacion) else 0,
    )
    log.info(
        "Ratio foot/car -- mediana: %.1fx, media: %.1fx | Ratio bike/car -- mediana: %.1fx, media: %.1fx",
        comparacion["ratio_foot_car"].median(), comparacion["ratio_foot_car"].mean(),
        comparacion["ratio_bike_car"].median(), comparacion["ratio_bike_car"].mean(),
    )

    return comparacion


def run(n_prueba: int | None = None) -> None:
    cfg = load_config()

    log.info("=== Verificando salud de los 3 servidores OSRM ===")
    estados = {p: check_osrm_health(p, cfg) for p in cfg.perfiles}
    if not all(estados.values()):
        caidos = [p for p, ok in estados.items() if not ok]
        raise RuntimeError(
            f"Los siguientes perfiles OSRM no responden: {caidos}. "
            f"Corre 'docker compose up -d' y 'docker compose ps' para diagnosticar."
        )
    log.info("Los 3 servidores OSRM responden correctamente.")

    facilidades = cargar_facilidades(cfg)
    demanda = cargar_demanda(cfg)

    if n_prueba is not None:
        log.warning("MODO PRUEBA: usando solo %d puntos de demanda (de %d totales)", n_prueba, len(demanda))
        demanda = demanda.head(n_prueba)
    else:
        demanda = muestrear_demanda(
            demanda, cfg,
            col_poblacion=cfg.poblacion_col_total,
            col_distrito=cfg.sigmed_col_distrito,
        )

    resolutivas = facilidades[facilidades["es_resolutivo"]].copy()
    log.info("Establecimientos resolutivos disponibles para ruteo: %d", len(resolutivas))

    id_col_demanda = cfg.sigmed_col_codigo_cp
    id_col_facilidad = cfg.renipress_col_codigo
    cache_dir = Path(cfg.path_routing_cache_dir)

    log.info("=== Matriz CAR (demanda x TODOS los establecimientos) ===")
    matriz_car = compute_matrix(
        demanda, facilidades, "car", cfg,
        id_col_demanda, id_col_facilidad,
        cache_dir / ("matrix_car_full_prueba.parquet" if n_prueba else "matrix_car_full.parquet"),
    )

    log.info("=== Matriz FOOT (demanda x establecimientos RESOLUTIVOS) ===")
    matriz_foot = compute_matrix(
        demanda, resolutivas, "foot", cfg,
        id_col_demanda, id_col_facilidad,
        cache_dir / ("matrix_foot_resolutivo_prueba.parquet" if n_prueba else "matrix_foot_resolutivo.parquet"),
    )

    log.info("=== Matriz BIKE (demanda x establecimientos RESOLUTIVOS) ===")
    matriz_bike = compute_matrix(
        demanda, resolutivas, "bike", cfg,
        id_col_demanda, id_col_facilidad,
        cache_dir / ("matrix_bike_resolutivo_prueba.parquet" if n_prueba else "matrix_bike_resolutivo.parquet"),
    )

    log.info("=== Comparando los 3 modos de transporte ===")
    comparacion = comparar_modos(
        matriz_car, matriz_foot, matriz_bike, resolutivas,
        id_col_demanda, id_col_facilidad,
    )

    Path(cfg.outputs_dir).mkdir(parents=True, exist_ok=True)
    out_path = Path(cfg.outputs_dir) / ("comparacion_modos_prueba.csv" if n_prueba else "comparacion_modos.csv")
    comparacion.to_csv(out_path, index=False)
    log.info("Guardado %s (%d filas)", out_path, len(comparacion))

    print("\n" + "=" * 70)
    print("RESUMEN FASE 2")
    print("=" * 70)
    print(f"Puntos de demanda procesados: {len(demanda)}")
    print(f"Establecimientos totales (matriz car): {len(facilidades)}")
    print(f"Establecimientos resolutivos (matriz foot/bike): {len(resolutivas)}")
    print(f"\nMuestra de la comparación de modos:\n{comparacion.head(10).to_string(index=False)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--prueba", type=int, default=None,
        help="Si se pasa, usa solo N puntos de demanda (para probar rápido antes de la corrida completa)",
    )
    args = parser.parse_args()
    run(n_prueba=args.prueba)
