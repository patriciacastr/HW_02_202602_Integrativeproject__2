"""
run_phase3.py — Orquesta la Fase 3: carga la matriz de auto (Fase 2) + datos
de demanda (Fase 1), calcula todas las métricas requeridas, y exporta CSVs.

Uso:
    python -m src.run_phase3

Salidas (todas en data/outputs/):
    acceso_tiempo_por_punto.csv
    cobertura_bandas.csv
    promedio_ponderado_distrito.csv
    promedio_ponderado_provincia.csv
    promedio_ponderado_departamento.csv
    brecha_critica_top_distritos.csv
    gini_tiempo_acceso.csv
    urbano_rural_contraste.csv
    cruce_altitud.csv
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd

from src.config_loader import Config, load_config
from src.metrics import (
    bandas_cobertura,
    brecha_critica,
    calcular_tiempo_acceso,
    clasificar_urbano_rural,
    contraste_urbano_rural,
    cruce_con_altitud,
    gini_ponderado,
    promedio_ponderado_por_nivel,
)

Path("logs").mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(Path("logs") / "run_phase3.log", encoding="utf-8"),
    ],
)
log = logging.getLogger("run_phase3")


def cargar_insumos(cfg: Config) -> tuple[pd.DataFrame, gpd.GeoDataFrame, gpd.GeoDataFrame]:
    matriz_path = Path(cfg.path_routing_cache_dir) / "matrix_car_full.parquet"
    if not matriz_path.exists():
        raise FileNotFoundError(
            f"No se encontró {matriz_path}. Corre 'python -m src.run_phase2' primero (corrida "
            f"completa, sin --prueba)."
        )
    matriz_car = pd.read_parquet(matriz_path)
    log.info("Matriz de auto cargada: %d pares", len(matriz_car))

    demanda = gpd.read_parquet(Path(cfg.processed_dir) / "sigmed_clean.parquet")
    facilidades = gpd.read_parquet(Path(cfg.processed_dir) / "renipress_clean.parquet")

    # La demanda con la que trabajamos en Fase 3 es solo la que SÍ tiene
    # resultados de ruteo (el subconjunto muestreado en Fase 2), no las
    # 18713 filas originales.
    ids_con_ruteo = matriz_car[cfg.sigmed_col_codigo_cp].unique()
    demanda = demanda[demanda[cfg.sigmed_col_codigo_cp].isin(ids_con_ruteo)].copy()
    log.info("Demanda con resultados de ruteo disponibles: %d puntos", len(demanda))

    return matriz_car, demanda, facilidades


def run() -> None:
    cfg = load_config()
    Path(cfg.outputs_dir).mkdir(parents=True, exist_ok=True)

    matriz_car, demanda, facilidades = cargar_insumos(cfg)

    resolutivas = facilidades[facilidades["es_resolutivo"]]
    ids_resolutivos = set(resolutivas[cfg.renipress_col_codigo])

    id_col_demanda = cfg.sigmed_col_codigo_cp
    col_poblacion = cfg.poblacion_col_total

    # --- 1. Tiempo de acceso por punto ---
    log.info("=== Calculando tiempo de acceso (t_min) ===")
    acceso = calcular_tiempo_acceso(matriz_car, ids_resolutivos, id_col_demanda, cfg.renipress_col_codigo)
    acceso.to_csv(Path(cfg.outputs_dir) / "acceso_tiempo_por_punto.csv", index=False)

    # Unir con atributos de demanda (población, distrito/provincia/depto, altitud, capital)
    demanda_con_acceso = demanda.merge(acceso, on=id_col_demanda, how="inner")
    log.info(
        "Demanda con tiempo de acceso calculado: %d de %d puntos (el resto no tuvo ningún "
        "establecimiento resolutivo alcanzable en la red recortada -- limitación a documentar)",
        len(demanda_con_acceso), len(demanda),
    )

    # --- 2. Bandas de cobertura ---
    log.info("=== Bandas de cobertura ===")
    cobertura = bandas_cobertura(demanda_con_acceso, cfg.bandas_cobertura_min, col_poblacion)
    cobertura.to_csv(Path(cfg.outputs_dir) / "cobertura_bandas.csv", index=False)

    # --- 3. Promedio ponderado por nivel administrativo ---
    log.info("=== Promedios ponderados por nivel administrativo ===")
    for nivel, col in [
        ("distrito", cfg.sigmed_col_distrito),
        ("provincia", cfg.sigmed_col_provincia),
        ("departamento", cfg.sigmed_col_departamento),
    ]:
        prom = promedio_ponderado_por_nivel(demanda_con_acceso, col, col_poblacion)
        prom.to_csv(Path(cfg.outputs_dir) / f"promedio_ponderado_{nivel}.csv", index=False)

    # --- 4. Brecha crítica (a nivel distrito) ---
    log.info("=== Brecha crítica ===")
    prom_distrito = promedio_ponderado_por_nivel(demanda_con_acceso, cfg.sigmed_col_distrito, col_poblacion)
    brecha = brecha_critica(prom_distrito, cfg.sigmed_col_distrito, cfg.get("top_n_brecha_critica", 15))
    brecha.to_csv(Path(cfg.outputs_dir) / "brecha_critica_top_distritos.csv", index=False)

    # --- 5. Gini ---
    log.info("=== Gini ponderado ===")
    gini = gini_ponderado(demanda_con_acceso, "t_min", col_poblacion)
    gini.to_csv(Path(cfg.outputs_dir) / "gini_tiempo_acceso.csv", index=False)

    # --- 6. Urbano vs. rural ---
    log.info("=== Clasificación y contraste urbano/rural ===")
    demanda_clasificada = clasificar_urbano_rural(
        demanda_con_acceso, cfg.sigmed_col_capital, col_poblacion, cfg.get("umbral_poblacion_urbano", 2000),
    )
    contraste = contraste_urbano_rural(demanda_clasificada, col_poblacion)
    contraste.to_csv(Path(cfg.outputs_dir) / "urbano_rural_contraste.csv", index=False)

    # --- Cruce con altitud ---
    log.info("=== Cruce con altitud ===")
    cruce = cruce_con_altitud(demanda_con_acceso, cfg.sigmed_col_altitud, col_poblacion)
    cruce.to_csv(Path(cfg.outputs_dir) / "cruce_altitud.csv", index=False)

    print("\n" + "=" * 70)
    print("RESUMEN FASE 3")
    print("=" * 70)
    print(f"Puntos con tiempo de acceso calculado: {len(demanda_con_acceso)}")
    print(f"\nBandas de cobertura:\n{cobertura.to_string(index=False)}")
    print(f"\nGini: {gini.iloc[0]['valor']}")
    print(f"\nContraste urbano/rural:\n{contraste.to_string(index=False)}")
    print(f"\nTop 5 distritos con peor acceso:\n{brecha.head(5).to_string(index=False)}")


if __name__ == "__main__":
    run()
