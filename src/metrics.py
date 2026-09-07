"""
metrics.py — Fase 3: convierte tiempos de viaje en indicadores.

Todas las funciones son puras: reciben DataFrame(s), devuelven un DataFrame.
Ninguna lógica de métricas debe vivir en el dashboard (Fase 4) -- ese solo
debe leer los CSVs que este módulo exporta.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

log = logging.getLogger("metrics")


def calcular_tiempo_acceso(
    matriz_car: pd.DataFrame,
    ids_resolutivos: set,
    id_col_demanda: str,
    id_col_facilidad: str,
) -> pd.DataFrame:
    """
    t_min(i): minutos en auto desde cada punto de demanda al establecimiento
    RESOLUTIVO más cercano. Filtra la matriz completa (que incluye TODOS los
    establecimientos) a solo los resolutivos antes de tomar el mínimo.

    Devuelve: [id_demanda, facilidad_mas_cercana, t_min, distancia_km]
    """
    sub = matriz_car[matriz_car[id_col_facilidad].isin(ids_resolutivos) & matriz_car["routable"]]
    idx_min = sub.groupby(id_col_demanda)["duracion_min"].idxmin()
    resultado = sub.loc[idx_min, [id_col_demanda, id_col_facilidad, "duracion_min", "distancia_km"]].copy()
    resultado = resultado.rename(columns={
        id_col_facilidad: "facilidad_mas_cercana",
        "duracion_min": "t_min",
    })
    n_sin_acceso = matriz_car[id_col_demanda].nunique() - len(resultado)
    log.info(
        "Tiempo de acceso calculado para %d puntos de demanda (%d sin ningún establecimiento "
        "resolutivo alcanzable por auto en la red recortada)",
        len(resultado), n_sin_acceso,
    )
    return resultado.reset_index(drop=True)


def bandas_cobertura(
    demanda_con_acceso: pd.DataFrame,
    bandas_min: list[int],
    col_poblacion: str,
) -> pd.DataFrame:
    """
    % de población dentro de cada banda de tiempo (<=30, <=60, <=120, >120 min
    por defecto -- según bandas_min de config.md), ponderado por población.

    Devuelve: [banda, poblacion_en_banda, pct_poblacion]
    """
    df = demanda_con_acceso.copy()
    poblacion_total = df[col_poblacion].sum()

    limites = sorted(bandas_min)
    etiquetas = [f"<= {limites[0]} min"] + [
        f"{limites[i]}-{limites[i+1]} min" for i in range(len(limites) - 1)
    ] + [f"> {limites[-1]} min"]

    cortes = [-np.inf] + limites + [np.inf]
    df["banda"] = pd.cut(df["t_min"], bins=cortes, labels=etiquetas, right=True)

    resumen = (
        df.groupby("banda", observed=True)[col_poblacion]
        .sum()
        .reset_index()
        .rename(columns={col_poblacion: "poblacion_en_banda"})
    )
    resumen["pct_poblacion"] = 100 * resumen["poblacion_en_banda"] / poblacion_total

    log.info("Bandas de cobertura (%% de población):\n%s", resumen.to_string(index=False))
    return resumen


def promedio_ponderado_por_nivel(
    demanda_con_acceso: pd.DataFrame,
    col_nivel: str,
    col_poblacion: str,
) -> pd.DataFrame:
    """
    Tiempo de acceso promedio, PONDERADO POR POBLACIÓN, agregado al nivel
    administrativo indicado (distrito, provincia, o departamento).

    Devuelve: [col_nivel, t_min_promedio_ponderado, poblacion_total, n_puntos]
    """
    def promedio_ponderado(grupo: pd.DataFrame) -> float:
        peso = grupo[col_poblacion]
        if peso.sum() == 0:
            return grupo["t_min"].mean()
        return np.average(grupo["t_min"], weights=peso)

    resultado = (
        demanda_con_acceso.groupby(col_nivel)
        .apply(lambda g: pd.Series({
            "t_min_promedio_ponderado": promedio_ponderado(g),
            "poblacion_total": g[col_poblacion].sum(),
            "n_puntos": len(g),
        }), include_groups=False)
        .reset_index()
    )
    return resultado.sort_values("t_min_promedio_ponderado", ascending=False)


def brecha_critica(promedios_distrito: pd.DataFrame, col_nivel: str, top_n: int) -> pd.DataFrame:
    """Los top_n distritos con PEOR (mayor) tiempo de acceso promedio ponderado."""
    resultado = promedios_distrito.nlargest(top_n, "t_min_promedio_ponderado").reset_index(drop=True)
    resultado.insert(0, "ranking", range(1, len(resultado) + 1))
    log.info("Top %d distritos con peor acceso:\n%s", top_n, resultado.to_string(index=False))
    return resultado


def gini_ponderado(demanda_con_acceso: pd.DataFrame, col_valor: str, col_poblacion: str) -> pd.DataFrame:
    """
    Coeficiente de Gini ponderado por población, aplicado al tiempo de acceso
    (mide desigualdad en el acceso: 0 = todos tienen el mismo tiempo de
    acceso, cerca de 1 = muy desigual).

    Devuelve un DataFrame de una fila (para exportar consistente con el resto
    de funciones de este módulo, que siempre devuelven DataFrame).
    """
    df = demanda_con_acceso.dropna(subset=[col_valor, col_poblacion]).sort_values(col_valor)
    valores = df[col_valor].to_numpy(dtype=float)
    pesos = df[col_poblacion].to_numpy(dtype=float)

    peso_acum = np.cumsum(pesos)
    valor_ponderado_acum = np.cumsum(pesos * valores)

    p = np.concatenate([[0], peso_acum / peso_acum[-1]])
    l = np.concatenate([[0], valor_ponderado_acum / valor_ponderado_acum[-1]])

    area_bajo_lorenz = np.trapz(l, p)
    gini = 1 - 2 * area_bajo_lorenz

    log.info("Gini ponderado del tiempo de acceso: %.4f", gini)
    return pd.DataFrame([{"metrica": "gini_tiempo_acceso", "valor": round(gini, 4)}])


def clasificar_urbano_rural(
    demanda: pd.DataFrame,
    col_capital: str,
    col_poblacion: str,
    umbral_poblacion: float,
) -> pd.DataFrame:
    """
    Regla explícita (documentar en el reporte): un centro poblado es URBANO
    si es capital de distrito/provincia/departamento (CAPITAL >= 1) O su
    población supera umbral_poblacion. Todo lo demás es RURAL.

    Agrega la columna 'es_urbano' (bool) al DataFrame.
    """
    df = demanda.copy()
    es_capital = df[col_capital].fillna(0) >= 1
    supera_umbral = df[col_poblacion].fillna(0) >= umbral_poblacion
    df["es_urbano"] = es_capital | supera_umbral

    n_urbano = int(df["es_urbano"].sum())
    log.info(
        "Clasificación urbano/rural: %d urbanos (%.1f%%), %d rurales (%.1f%%)",
        n_urbano, 100 * n_urbano / len(df),
        len(df) - n_urbano, 100 * (len(df) - n_urbano) / len(df),
    )
    return df


def contraste_urbano_rural(demanda_clasificada: pd.DataFrame, col_poblacion: str) -> pd.DataFrame:
    """Tiempo de acceso promedio ponderado, urbano vs. rural, lado a lado."""
    def promedio_ponderado(grupo: pd.DataFrame) -> float:
        return np.average(grupo["t_min"], weights=grupo[col_poblacion])

    resultado = (
        demanda_clasificada.groupby("es_urbano")
        .apply(lambda g: pd.Series({
            "t_min_promedio_ponderado": promedio_ponderado(g),
            "poblacion_total": g[col_poblacion].sum(),
            "n_puntos": len(g),
        }), include_groups=False)
        .reset_index()
    )
    resultado["es_urbano"] = resultado["es_urbano"].map({True: "Urbano", False: "Rural"})
    log.info("Contraste urbano vs. rural:\n%s", resultado.to_string(index=False))
    return resultado


def cruce_con_altitud(demanda_con_acceso: pd.DataFrame, col_altitud: str, col_poblacion: str) -> pd.DataFrame:
    """
    Correlación entre tiempo de acceso y altitud. Devuelve el coeficiente de
    correlación (ponderado por población) y un resumen por banda altitudinal
    -- NO afirma causalidad; esa interpretación va en el texto del reporte.
    """
    df = demanda_con_acceso.dropna(subset=[col_altitud, "t_min"]).copy()

    # Correlación de Pearson ponderada por población
    peso = df[col_poblacion].to_numpy(dtype=float)
    x = df[col_altitud].to_numpy(dtype=float)
    y = df["t_min"].to_numpy(dtype=float)
    x_prom = np.average(x, weights=peso)
    y_prom = np.average(y, weights=peso)
    cov = np.average((x - x_prom) * (y - y_prom), weights=peso)
    var_x = np.average((x - x_prom) ** 2, weights=peso)
    var_y = np.average((y - y_prom) ** 2, weights=peso)
    correlacion = cov / np.sqrt(var_x * var_y)

    log.info("Correlación ponderada tiempo_acceso vs. altitud: r=%.4f", correlacion)

    df["banda_altitud"] = pd.cut(
        df[col_altitud],
        bins=[-np.inf, 500, 2000, 3500, np.inf],
        labels=["0-500m (costa)", "500-2000m", "2000-3500m", "> 3500m (altoandino)"],
    )
    resumen_bandas = (
        df.groupby("banda_altitud", observed=True)
        .apply(lambda g: pd.Series({
            "t_min_promedio_ponderado": np.average(g["t_min"], weights=g[col_poblacion]),
            "poblacion_total": g[col_poblacion].sum(),
            "n_puntos": len(g),
        }), include_groups=False)
        .reset_index()
    )
    resumen_bandas.insert(0, "correlacion_pearson_ponderada", round(correlacion, 4))

    log.info("Tiempo de acceso por banda altitudinal:\n%s", resumen_bandas.to_string(index=False))
    return resumen_bandas
