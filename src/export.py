"""
export.py — Fase 5: genera figuras (PDF vectorial) y tablas LaTeX (booktabs)
a partir de los CSVs ya exportados en Fases 1-3. Nada se inventa aquí -- cada
función lee un CSV real y produce una figura o una tabla, para que el reporte
LaTeX (report/main.tex) las incluya con \\includegraphics / \\input.

Uso:
    python -m src.export

Salidas:
    report/figures/fig_cobertura_bandas.pdf
    report/figures/fig_brecha_critica.pdf
    report/figures/fig_urbano_rural.pdf
    report/figures/fig_altitud_bandas.pdf
    report/tables/tabla_calidad_renipress.tex
    report/tables/tabla_calidad_sigmed.tex
    report/tables/tabla_brecha_critica.tex
"""
from __future__ import annotations

import logging
from pathlib import Path

import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from src.config_loader import load_config
from src.metrics import brecha_critica, promedio_ponderado_por_nivel

log = logging.getLogger("export")

plt.rcParams.update({
    "font.size": 11,
    "axes.spines.top": True,
    "axes.spines.right": True,
    "axes.edgecolor": "#444444",
    "axes.linewidth": 1.1,
    "axes.grid": True,
    "axes.grid.axis": "y",
    "grid.alpha": 0.3,
    "grid.linestyle": "--",
    "axes.titlesize": 13,
    "axes.titleweight": "bold",
    "axes.titlepad": 12,
    "figure.autolayout": False,
})

# Paleta pastel
COLOR_PRIMARIO = "#a8c8e8"      # azul pastel
COLOR_PRIMARIO_BORDE = "#5b8fc4"
COLOR_ALERTA = "#f4a6a0"        # rojo/coral pastel
COLOR_ALERTA_BORDE = "#d4685e"
COLOR_URBANO = "#ffd8a8"        # naranja pastel
COLOR_URBANO_BORDE = "#e8a355"
COLOR_RURAL = "#a8e0c0"         # verde pastel
COLOR_RURAL_BORDE = "#5cb587"


def _guardar(fig, ruta: Path) -> None:
    """Guarda siempre con bbox_inches='tight' -- evita que etiquetas rotadas
    o texto sobre las barras se corten en el borde de la imagen."""
    fig.savefig(ruta, bbox_inches="tight", pad_inches=0.15)
    plt.close(fig)


def fig_cobertura_bandas(cfg, out_dir: Path) -> Path:
    df = pd.read_csv(Path(cfg.outputs_dir) / "cobertura_bandas.csv")
    fig, ax = plt.subplots(figsize=(7, 4))
    barras = ax.bar(df["banda"], df["pct_poblacion"], color=COLOR_PRIMARIO,
                     edgecolor=COLOR_PRIMARIO_BORDE, linewidth=1.3, width=0.6, zorder=3)
    ax.set_title("Cobertura poblacional por banda de tiempo de acceso")
    ax.set_ylabel("% de la población")
    ax.set_xlabel("Tiempo de acceso (auto) al hospital resolutivo más cercano")
    ax.set_ylim(0, max(df["pct_poblacion"]) * 1.18)
    for barra, pct in zip(barras, df["pct_poblacion"]):
        ax.text(barra.get_x() + barra.get_width() / 2, barra.get_height() + max(df["pct_poblacion"]) * 0.02,
                 f"{pct:.1f}%", ha="center", va="bottom", fontsize=10, fontweight="bold")
    ax.set_axisbelow(True)
    ruta = out_dir / "fig_cobertura_bandas.pdf"
    _guardar(fig, ruta)
    return ruta


def fig_brecha_critica(cfg, out_dir: Path, top_n: int = 10) -> Path:
    df = pd.read_csv(Path(cfg.outputs_dir) / "brecha_critica_top_distritos.csv").head(top_n)
    fig, ax = plt.subplots(figsize=(7.5, 0.45 * top_n + 1.5))
    barras = ax.barh(df["DIST"][::-1], df["t_min_promedio_ponderado"][::-1], color=COLOR_ALERTA,
                      edgecolor=COLOR_ALERTA_BORDE, linewidth=1.3, zorder=3)
    ax.set_title(f"Los {top_n} distritos con peor tiempo de acceso")
    ax.set_xlabel("Tiempo de acceso promedio ponderado (min)")
    ax.set_ylabel("Distrito")
    ax.set_xlim(0, df["t_min_promedio_ponderado"].max() * 1.15)
    for barra, val in zip(barras, df["t_min_promedio_ponderado"][::-1]):
        ax.text(barra.get_width() + df["t_min_promedio_ponderado"].max() * 0.015,
                 barra.get_y() + barra.get_height() / 2, f"{val:.0f}", va="center", fontsize=9)
    ax.set_axisbelow(True)
    ruta = out_dir / "fig_brecha_critica.pdf"
    _guardar(fig, ruta)
    return ruta


def fig_urbano_rural(cfg, out_dir: Path) -> Path:
    df = pd.read_csv(Path(cfg.outputs_dir) / "urbano_rural_contraste.csv")
    colores = [COLOR_RURAL if v == "Rural" else COLOR_URBANO for v in df["es_urbano"]]
    bordes = [COLOR_RURAL_BORDE if v == "Rural" else COLOR_URBANO_BORDE for v in df["es_urbano"]]
    fig, ax = plt.subplots(figsize=(6, 4.2))
    barras = ax.bar(df["es_urbano"], df["t_min_promedio_ponderado"], color=colores,
                     edgecolor=bordes, linewidth=1.3, width=0.5, zorder=3)
    ax.set_title("Tiempo de acceso: urbano vs. rural")
    ax.set_ylabel("Tiempo de acceso\npromedio ponderado (min)")
    ax.set_ylim(0, df["t_min_promedio_ponderado"].max() * 1.2)
    for barra, val in zip(barras, df["t_min_promedio_ponderado"]):
        ax.text(barra.get_x() + barra.get_width() / 2, barra.get_height() + df["t_min_promedio_ponderado"].max() * 0.03,
                 f"{val:.1f} min", ha="center", va="bottom", fontsize=10, fontweight="bold")
    ax.set_axisbelow(True)
    ruta = out_dir / "fig_urbano_rural.pdf"
    _guardar(fig, ruta)
    return ruta


def _cargar_demanda_acceso(cfg):
    """Helper reusado por varias figuras: demanda (Fase 1) + tiempo de acceso
    ya calculado (Fase 3), unidos por el ID del centro poblado."""
    id_demanda = cfg.sigmed_col_codigo_cp
    demanda = gpd.read_parquet(Path(cfg.processed_dir) / "sigmed_clean.parquet")
    acceso = pd.read_csv(Path(cfg.outputs_dir) / "acceso_tiempo_por_punto.csv")
    demanda[id_demanda] = demanda[id_demanda].astype(str)
    acceso[id_demanda] = acceso[id_demanda].astype(str)
    return demanda.merge(acceso, on=id_demanda, how="inner")


# Paleta consistente para los 3 departamentos en gráficos comparativos
def _paleta_departamentos(departamentos: list[str]) -> tuple[dict, dict]:
    base = [
        (COLOR_PRIMARIO, COLOR_PRIMARIO_BORDE),
        (COLOR_ALERTA, COLOR_ALERTA_BORDE),
        (COLOR_RURAL, COLOR_RURAL_BORDE),
        (COLOR_URBANO, COLOR_URBANO_BORDE),
    ]
    colores = {dep: base[i % len(base)][0] for i, dep in enumerate(departamentos)}
    bordes = {dep: base[i % len(base)][1] for i, dep in enumerate(departamentos)}
    return colores, bordes


def fig_mapa_distrital(cfg, out_dir: Path) -> Path:
    """
    Mapa coroplético estático: distritos coloreados por tiempo de acceso
    promedio ponderado, con el contorno de TODO el Perú de fondo (sin
    filtrar) para dar contexto -- así los 3 departamentos no se ven como
    piezas sueltas flotando en el vacío. Recalcula el promedio por UBIGEO
    (no por nombre de distrito) -- mismo enfoque que usa app.py.
    """
    col_poblacion = cfg.poblacion_col_total
    col_ubigeo_demanda = "UBIGEO_punto"  # ver nota en app.py: renombrada en Fase 1
    col_ubigeo_poligono = cfg.poligonos_campo_ubigeo_distrito

    demanda_acceso = _cargar_demanda_acceso(cfg)
    prom_distrito = promedio_ponderado_por_nivel(demanda_acceso, col_ubigeo_demanda, col_poblacion)
    prom_distrito = prom_distrito.rename(columns={col_ubigeo_demanda: col_ubigeo_poligono})

    distritos = gpd.read_file(cfg.path_poligonos_gpkg_salida, layer="distrito")
    mapa = distritos.merge(prom_distrito, on=col_ubigeo_poligono, how="left")

    # Contorno de TODO el país (fuente cruda, sin el filtro a 3 departamentos
    # que sí se aplicó en poligonos.gpkg) -- solo para dar contexto visual.
    peru_completo = gpd.read_file(cfg.path_poligonos_departamento)
    crs_salida = cfg.get("poligonos_crs_salida", "EPSG:4326")
    if peru_completo.crs is not None and str(peru_completo.crs).upper() != crs_salida.upper():
        peru_completo = peru_completo.to_crs(crs_salida)

    fig, ax = plt.subplots(figsize=(7, 8.5))
    peru_completo.plot(ax=ax, color="#f2f2f2", edgecolor="#bbbbbb", linewidth=0.5, zorder=1)
    mapa.plot(
        column="t_min_promedio_ponderado", cmap="YlOrRd", legend=True, ax=ax, zorder=2,
        edgecolor="#666666", linewidth=0.3,
        missing_kwds={"color": "#d9d9d9", "label": "Sin datos en la muestra"},
        legend_kwds={"label": "Tiempo de acceso promedio ponderado (min)", "shrink": 0.6},
    )
    minx, miny, maxx, maxy = peru_completo.total_bounds
    ax.set_xlim(minx, maxx)
    ax.set_ylim(miny, maxy)
    ax.set_title("Tiempo de acceso por distrito", fontsize=13, fontweight="bold")
    ax.set_axis_off()
    ruta = out_dir / "fig_mapa_distrital.pdf"
    _guardar(fig, ruta)
    return ruta


def fig_altitud_bandas(cfg, out_dir: Path) -> Path:
    df = pd.read_csv(Path(cfg.outputs_dir) / "cruce_altitud.csv")
    etiquetas_cortas = df["banda_altitud"].str.replace(" (costa)", "\n(costa)", regex=False)
    etiquetas_cortas = etiquetas_cortas.str.replace(" (altoandino)", "\n(altoandino)", regex=False)
    fig, ax = plt.subplots(figsize=(7, 4.2))
    barras = ax.bar(etiquetas_cortas, df["t_min_promedio_ponderado"], color=COLOR_PRIMARIO,
                     edgecolor=COLOR_PRIMARIO_BORDE, linewidth=1.3, width=0.6, zorder=3)
    ax.set_title("Tiempo de acceso por banda altitudinal")
    ax.set_ylabel("Tiempo de acceso promedio ponderado (min)")
    ax.set_xlabel("Banda altitudinal")
    ax.set_ylim(0, df["t_min_promedio_ponderado"].max() * 1.18)
    for barra, val in zip(barras, df["t_min_promedio_ponderado"]):
        ax.text(barra.get_x() + barra.get_width() / 2, barra.get_height() + df["t_min_promedio_ponderado"].max() * 0.03,
                 f"{val:.1f}", ha="center", va="bottom", fontsize=10, fontweight="bold")
    ax.set_axisbelow(True)
    ruta = out_dir / "fig_altitud_bandas.pdf"
    _guardar(fig, ruta)
    return ruta


def fig_cobertura_bandas_por_departamento(cfg, out_dir: Path) -> Path:
    """Igual que fig_cobertura_bandas, pero calculado por separado para cada
    departamento y mostrado como barras agrupadas."""
    from src.metrics import bandas_cobertura
    col_dep = cfg.sigmed_col_departamento
    col_pob = cfg.poblacion_col_total
    demanda_acceso = _cargar_demanda_acceso(cfg)

    departamentos = sorted(demanda_acceso[col_dep].dropna().unique())
    filas = []
    for dep in departamentos:
        sub = demanda_acceso[demanda_acceso[col_dep] == dep]
        resumen = bandas_cobertura(sub, cfg.bandas_cobertura_min, col_pob)
        resumen["departamento"] = dep
        filas.append(resumen)
    df = pd.concat(filas, ignore_index=True)

    bandas_orden = df["banda"].drop_duplicates().tolist()
    colores, bordes = _paleta_departamentos(departamentos)
    ancho = 0.8 / len(departamentos)
    x = list(range(len(bandas_orden)))

    fig, ax = plt.subplots(figsize=(8.5, 4.5))
    for i, dep in enumerate(departamentos):
        sub = df[df["departamento"] == dep].set_index("banda").reindex(bandas_orden)
        posiciones = [xi + i * ancho for xi in x]
        ax.bar(posiciones, sub["pct_poblacion"], width=ancho, label=dep,
               color=colores[dep], edgecolor=bordes[dep], linewidth=1.1, zorder=3)
    ax.set_xticks([xi + ancho * (len(departamentos) - 1) / 2 for xi in x])
    ax.set_xticklabels(bandas_orden)
    ax.set_ylabel("% de la población (del departamento)")
    ax.set_xlabel("Tiempo de acceso (auto)")
    ax.set_title("Cobertura poblacional por banda de tiempo, por departamento")
    ax.legend(title="Departamento", frameon=True, fontsize=9)
    ax.set_axisbelow(True)
    ruta = out_dir / "fig_cobertura_bandas_departamento.pdf"
    _guardar(fig, ruta)
    return ruta


def fig_urbano_rural_por_departamento(cfg, out_dir: Path) -> Path:
    """Igual que fig_urbano_rural, pero calculado por separado para cada departamento."""
    from src.metrics import clasificar_urbano_rural, contraste_urbano_rural
    col_dep = cfg.sigmed_col_departamento
    col_pob = cfg.poblacion_col_total
    demanda_acceso = _cargar_demanda_acceso(cfg)
    clasificada = clasificar_urbano_rural(
        demanda_acceso, cfg.sigmed_col_capital, col_pob, cfg.get("umbral_poblacion_urbano", 2000),
    )

    departamentos = sorted(clasificada[col_dep].dropna().unique())
    filas = []
    for dep in departamentos:
        sub = clasificada[clasificada[col_dep] == dep]
        resumen = contraste_urbano_rural(sub, col_pob)
        resumen["departamento"] = dep
        filas.append(resumen)
    df = pd.concat(filas, ignore_index=True)

    categorias = ["Rural", "Urbano"]
    colores, bordes = _paleta_departamentos(departamentos)
    ancho = 0.8 / len(departamentos)
    x = list(range(len(categorias)))

    fig, ax = plt.subplots(figsize=(7, 4.5))
    for i, dep in enumerate(departamentos):
        sub = df[df["departamento"] == dep].set_index("es_urbano").reindex(categorias)
        posiciones = [xi + i * ancho for xi in x]
        ax.bar(posiciones, sub["t_min_promedio_ponderado"], width=ancho, label=dep,
               color=colores[dep], edgecolor=bordes[dep], linewidth=1.1, zorder=3)
    ax.set_xticks([xi + ancho * (len(departamentos) - 1) / 2 for xi in x])
    ax.set_xticklabels(categorias)
    ax.set_ylabel("Tiempo de acceso promedio ponderado (min)")
    ax.set_title("Urbano vs. rural, por departamento")
    ax.legend(title="Departamento", fontsize=9)
    ax.set_axisbelow(True)
    ruta = out_dir / "fig_urbano_rural_departamento.pdf"
    _guardar(fig, ruta)
    return ruta


def fig_altitud_por_departamento(cfg, out_dir: Path) -> Path:
    """Igual que fig_altitud_bandas, pero calculado por separado para cada departamento."""
    from src.metrics import cruce_con_altitud
    col_dep = cfg.sigmed_col_departamento
    col_pob = cfg.poblacion_col_total
    col_alt = cfg.sigmed_col_altitud
    demanda_acceso = _cargar_demanda_acceso(cfg)

    departamentos = sorted(demanda_acceso[col_dep].dropna().unique())
    filas = []
    for dep in departamentos:
        sub = demanda_acceso[demanda_acceso[col_dep] == dep]
        try:
            resumen = cruce_con_altitud(sub, col_alt, col_pob)
        except (ValueError, ZeroDivisionError):
            log.warning(
                "%s: sin población utilizable para calcular el cruce con altitud "
                "(ver limitaciones) -- se omite del gráfico.", dep,
            )
            continue
        resumen["departamento"] = dep
        filas.append(resumen)
    df = pd.concat(filas, ignore_index=True)

    bandas_orden = df["banda_altitud"].drop_duplicates().tolist()
    etiquetas_cortas = [b.replace(" (costa)", "\n(costa)").replace(" (altoandino)", "\n(altoandino)") for b in bandas_orden]
    colores, bordes = _paleta_departamentos(departamentos)
    ancho = 0.8 / len(departamentos)
    x = list(range(len(bandas_orden)))

    fig, ax = plt.subplots(figsize=(9, 4.5))
    for i, dep in enumerate(departamentos):
        sub = df[df["departamento"] == dep].set_index("banda_altitud").reindex(bandas_orden)
        posiciones = [xi + i * ancho for xi in x]
        ax.bar(posiciones, sub["t_min_promedio_ponderado"], width=ancho, label=dep,
               color=colores[dep], edgecolor=bordes[dep], linewidth=1.1, zorder=3)
    ax.set_xticks([xi + ancho * (len(departamentos) - 1) / 2 for xi in x])
    ax.set_xticklabels(etiquetas_cortas)
    ax.set_ylabel("Tiempo de acceso promedio ponderado (min)")
    ax.set_xlabel("Banda altitudinal")
    ax.set_title("Tiempo de acceso por altitud, por departamento")
    ax.legend(title="Departamento", fontsize=9)
    ax.set_axisbelow(True)
    ruta = out_dir / "fig_altitud_departamento.pdf"
    _guardar(fig, ruta)
    return ruta


def fig_brecha_critica_por_departamento(cfg, out_dir: Path, top_n: int = 5) -> Path:
    """Los top_n distritos con peor acceso, calculados por separado dentro
    de cada departamento (en vez de un ranking nacional mezclado)."""
    col_dep = cfg.sigmed_col_departamento
    col_pob = cfg.poblacion_col_total
    col_ubigeo = "UBIGEO_punto"
    col_dist_nombre = cfg.sigmed_col_distrito
    demanda_acceso = _cargar_demanda_acceso(cfg)

    departamentos = sorted(demanda_acceso[col_dep].dropna().unique())
    colores, bordes = _paleta_departamentos(departamentos)

    fig, axes = plt.subplots(1, len(departamentos), figsize=(5.3 * len(departamentos), 4.5))
    if len(departamentos) == 1:
        axes = [axes]

    for ax, dep in zip(axes, departamentos):
        sub = demanda_acceso[demanda_acceso[col_dep] == dep]
        prom = promedio_ponderado_por_nivel(sub, col_ubigeo, col_pob)
        top = brecha_critica(prom, col_ubigeo, top_n)
        nombres = sub.drop_duplicates(col_ubigeo)[[col_ubigeo, col_dist_nombre]]
        top = top.merge(nombres, on=col_ubigeo, how="left")
        ax.barh(top[col_dist_nombre][::-1], top["t_min_promedio_ponderado"][::-1],
                color=colores[dep], edgecolor=bordes[dep], linewidth=1.2, zorder=3)
        ax.set_title(dep, fontsize=11, fontweight="bold")
        ax.set_xlabel("Min. promedio")
        ax.tick_params(axis="y", labelsize=9)
        ax.set_axisbelow(True)

    fig.subplots_adjust(wspace=0.9)
    fig.suptitle(f"Los {top_n} distritos con peor acceso, por departamento", fontsize=13, fontweight="bold", y=1.03)
    ruta = out_dir / "fig_brecha_critica_departamento.pdf"
    _guardar(fig, ruta)
    return ruta


def tabla_calidad_latex(cfg, nombre_fuente: str, out_dir: Path) -> Path:
    df = pd.read_csv(Path(cfg.outputs_dir) / f"data_quality_report_{nombre_fuente}.csv")
    df = df.copy()
    # Los guiones bajos (estilo nombre_de_variable) no tienen puntos de corte
    # de línea en LaTeX -- se reemplazan por espacios para que el texto se
    # vea legible y quepa dentro de la celda sin desbordar el margen.
    df["regla"] = df["regla"].str.replace("_", " ")
    df["accion"] = df["accion"].str.replace("_", " ")
    df_mostrar = df.rename(columns={
        "regla": "Regla", "n_flagged": "N marcados",
        "pct_del_total": "\\% del total", "accion": "Acción",
    })
    latex = df_mostrar.to_latex(index=False, escape=False, column_format="lrrp{6cm}", float_format="%.2f")
    ruta = out_dir / f"tabla_calidad_{nombre_fuente}.tex"
    ruta.write_text(latex, encoding="utf-8")
    return ruta


def tabla_brecha_critica_latex(cfg, out_dir: Path, top_n: int = 10) -> Path:
    df = pd.read_csv(Path(cfg.outputs_dir) / "brecha_critica_top_distritos.csv").head(top_n)
    df_mostrar = df.rename(columns={
        "ranking": "No.", "DIST": "Distrito",
        "t_min_promedio_ponderado": "Min. promedio", "poblacion_total": "Población", "n_puntos": "Centros poblados",
    })
    latex = df_mostrar.to_latex(index=False, float_format="%.1f")
    ruta = out_dir / "tabla_brecha_critica.tex"
    ruta.write_text(latex, encoding="utf-8")
    return ruta


def run() -> None:
    cfg = load_config()
    figures_dir = Path("report/figures")
    tables_dir = Path("report/tables")
    figures_dir.mkdir(parents=True, exist_ok=True)
    tables_dir.mkdir(parents=True, exist_ok=True)

    log.info("Generando figuras...")
    fig_mapa_distrital(cfg, figures_dir)
    fig_cobertura_bandas(cfg, figures_dir)
    fig_cobertura_bandas_por_departamento(cfg, figures_dir)
    fig_brecha_critica(cfg, figures_dir)
    fig_brecha_critica_por_departamento(cfg, figures_dir)
    fig_urbano_rural(cfg, figures_dir)
    fig_urbano_rural_por_departamento(cfg, figures_dir)
    fig_altitud_bandas(cfg, figures_dir)
    fig_altitud_por_departamento(cfg, figures_dir)

    log.info("Generando tablas...")
    tabla_calidad_latex(cfg, "renipress", tables_dir)
    tabla_calidad_latex(cfg, "sigmed", tables_dir)
    tabla_brecha_critica_latex(cfg, tables_dir)

    log.info("Listo: %d figuras en %s, %d tablas en %s",
              9, figures_dir, 3, tables_dir)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
