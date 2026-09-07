"""
poligonos.py — Carga y valida polígonos administrativos (distrito, provincia,
departamento).

Usa `cfg` como objeto Config de atributos planos (src/config_loader.py),
igual que el resto del proyecto — NO diccionario anidado.

Fuente: GEOGPSPERU (shapefile INEI actualizado), ya en EPSG:4326.
Ver config.md, sección "Polígonos administrativos", para rutas y nombres
de columna reales.
"""
from __future__ import annotations

import logging
from pathlib import Path

import geopandas as gpd

from src.config_loader import Config

log = logging.getLogger("poligonos")


def cargar_poligonos(nivel: str, cfg: Config) -> gpd.GeoDataFrame:
    """
    Carga un nivel de polígono administrativo y lo filtra a los departamentos
    declarados en config.md.

    nivel: 'distrito' | 'provincia' | 'departamento'
    """
    path = Path(cfg.get(f"path_poligonos_{nivel}"))
    if not path.exists():
        raise FileNotFoundError(
            f"No se encontró {path}. Verifica que el shapefile de '{nivel}' "
            f"esté descargado y que la ruta en config.md (path_poligonos_{nivel}) sea correcta."
        )

    log.info("Cargando polígonos de %s desde %s", nivel, path)
    gdf = gpd.read_file(path)
    log.info("%s: %d polígonos leídos, CRS original = %s", nivel, len(gdf), gdf.crs)

    crs_salida = cfg.get("poligonos_crs_salida", "EPSG:4326")
    if gdf.crs is None:
        raise ValueError(f"{path} no tiene CRS definido. Revisar el archivo .prj.")
    if str(gdf.crs).upper() != str(crs_salida).upper():
        gdf = gdf.to_crs(crs_salida)
        log.info("Reproyectado de %s a %s", gdf.crs, crs_salida)
    else:
        log.info("Ya está en %s, sin reproyección necesaria", crs_salida)

    campo_depto = cfg.get("poligonos_campo_departamento", "DEPARTAMEN")
    deptos = [d.upper() for d in cfg.departamentos]
    antes = len(gdf)
    gdf = gdf[gdf[campo_depto].str.upper().isin(deptos)].copy()
    log.info("Filtrado a %s: %d -> %d polígonos", deptos, antes, len(gdf))

    if len(gdf) == 0:
        log.warning(
            "El filtro a %s dejó 0 polígonos en el nivel '%s'. Revisa que "
            "poligonos_campo_departamento (%s) tenga los valores exactos esperados.",
            deptos, nivel, campo_depto,
        )

    return gdf


def validar_punto_en_distrito(
    puntos: gpd.GeoDataFrame,
    distritos: gpd.GeoDataFrame,
    campo_ubigeo_punto: str,
    cfg: Config,
) -> gpd.GeoDataFrame:
    """
    Para cada punto, verifica si cae dentro del polígono del distrito que su
    propio registro declara (comparando UBIGEO del punto vs. UBIGEO del
    polígono que espacialmente lo contiene).

    Agrega las columnas:
      - dentro_distrito_declarado (bool)
      - el UBIGEO del polígono que realmente lo contiene (para diagnóstico)
    """
    campo_ubigeo_poligono = cfg.get("poligonos_campo_ubigeo_distrito", "UBIGEO")

    log.info(
        "Validando punto vs. distrito declarado (campo punto=%s, campo polígono=%s)",
        campo_ubigeo_punto, campo_ubigeo_poligono,
    )

    # Si el campo del punto y el del polígono se llaman igual (ej. ambos
    # "UBIGEO"), gpd.sjoin les pone sufijos automáticos para no chocar y la
    # columna sin sufijo deja de existir. Forzamos sufijos explícitos y
    # resolvemos los nombres reales después del join, para que funcione
    # tanto si los nombres son iguales como si son distintos.
    mismo_nombre = campo_ubigeo_punto == campo_ubigeo_poligono

    join = gpd.sjoin(
        puntos,
        distritos[[campo_ubigeo_poligono, "geometry"]],
        how="left",
        predicate="within",
        lsuffix="punto",
        rsuffix="poligono",
    )

    # sjoin puede duplicar filas si un punto cae justo sobre un borde
    # compartido por dos polígonos; nos quedamos con el primer match.
    join = join[~join.index.duplicated(keep="first")]

    if mismo_nombre:
        col_punto_real = f"{campo_ubigeo_punto}_punto"
        col_poligono_real = f"{campo_ubigeo_poligono}_poligono"
    else:
        # Con nombres distintos, sjoin no les pone sufijo a ninguno de los
        # dos (solo se sufija cuando hay colisión real).
        col_punto_real = campo_ubigeo_punto
        col_poligono_real = campo_ubigeo_poligono

    join["dentro_distrito_declarado"] = (
        join[col_punto_real].astype(str) == join[col_poligono_real].astype(str)
    )

    n_fuera = int((~join["dentro_distrito_declarado"]).sum())
    n_sin_match = int(join[col_poligono_real].isna().sum())
    n_sin_geometria = int(join.geometry.isna().sum())
    n_fuera_con_coords = n_fuera - n_sin_geometria
    log.info(
        "Puntos fuera de su distrito declarado: %d de %d totales -- de los cuales "
        "%d NO tienen coordenadas (no se pudo validar, no es un error de ubicación) "
        "y %d SÍ tienen coordenadas válidas pero caen en un distrito distinto al declarado "
        "(este es el número real a reportar como hallazgo)",
        n_fuera, len(join), n_sin_geometria, n_fuera_con_coords,
    )

    return join


def guardar_poligonos_geopackage(poligonos: dict[str, gpd.GeoDataFrame], cfg: Config) -> None:
    """Guarda distrito/provincia/departamento como capas separadas en un solo .gpkg."""
    ruta_salida = cfg.get("path_poligonos_gpkg_salida")
    Path(ruta_salida).parent.mkdir(parents=True, exist_ok=True)
    for nivel, gdf in poligonos.items():
        gdf.to_file(ruta_salida, layer=nivel, driver="GPKG")
        log.info("Capa '%s' guardada en %s (%d polígonos)", nivel, ruta_salida, len(gdf))
