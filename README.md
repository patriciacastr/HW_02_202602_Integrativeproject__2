# Golden Hour — Acceso a salud resolutiva por tiempo de viaje

Proyecto integrador: análisis geoespacial de accesibilidad a establecimientos de salud
con capacidad resolutiva (categoría II-1 en adelante) en tres departamentos del Perú.

**Departamentos analizados:** Lambayeque (costa), Ayacucho (andino), San Martín (amazónico).
Cambiables sin tocar código — ver `config.md`.

## Estructura del repositorio

```
├── config.md # todos los parámetros del proyecto (departamentos, rutas, thresholds)
├── requirements.txt
├── README.md
├── src/
│ ├── config_loader.py # parsea config.md a un objeto Python
│ ├── acquisition.py # Fase 1 — descarga de fuentes crudas (cacheado, idempotente)
│ ├── validation.py # Fase 1 — reglas de validación + reporte de calidad
│ ├── poligonos.py # Fase 1 — carga/filtra polígonos distrito-provincia-departamento,
│ │ # valida punto vs. distrito declarado, exporta GeoPackage
│ ├── run_phase1.py # Fase 1 — orquesta acquisition + validation + población + polígonos
│ ├── routing.py # Fase 2 — motor de ruteo + caché de matriz (pendiente)
│ ├── metrics.py # Fase 3 — métricas de accesibilidad (pendiente)
│ └── export.py # Fase 5 — tablas/figuras para el reporte (pendiente)
├── data/
│ ├── raw/ # nunca se modifica a mano; solo la escribe acquisition.py o descarga manual
│ ├── processed/ # salidas de run_phase1.py: parquets limpios + poligonos.gpkg
│ └── outputs/ # CSVs de reporte de calidad (Fase 1) y, luego, tablas de metrics.py
├── app/
│ └── app.py # Fase 4 — dashboard Streamlit (pendiente)
├── report/
│ ├── main.tex # Fase 5 — reporte LaTeX (pendiente)
│ └── figures/
└── logs/ # logs de ejecución (incluye el reporte de calidad de datos)
```


## Setup

```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Paso 1 — Descargar datos crudos

```bash
python -m src.acquisition
```

Esto descarga automáticamente el extracto OSM de Perú a `data/raw/peru-latest.osm.pbf`
(idempotente: si ya existe, lo salta).

**Los siguientes datasets requieren descarga manual** (portales sin enlace directo estable),
colocar en la ruta indicada y **declarar la fecha de descarga** en
`data/raw/_download_manifest.md`:

- RENIPRESS → `data/raw/renipress.csv`
- SIGMED → `data/raw/sigmed/CP_P.shp`
- Población (GeoPerú/INEI, centros poblados) → `data/raw/poblacion_centros_poblados_geoperu/`
- Polígonos administrativos (GEOGPSPERU/INEI — distrito, provincia, departamento) →
  `data/raw/limites_geogpsperu/{distrito,provincia,departamento}/`

## Paso 2 — Ejecutar el pipeline de Fase 1

```bash
python -m src.run_phase1
```

Este script orquesta todo lo siguiente en un solo comando:

1. Carga y filtra RENIPRESS y SIGMED a los 3 departamentos declarados en `config.md`.
2. Corre las reglas de validación (coordenadas faltantes/cero, fuera del bbox de Perú,
   lat/lon invertidos, códigos duplicados, encoding) y exporta el reporte de calidad a
   `data/outputs/data_quality_report_{renipress,sigmed}.csv`.
3. Cruza SIGMED con población (GeoPerú/INEI) por proximidad espacial — ver sección
   "Hallazgos" abajo.
4. Carga los polígonos de distrito/provincia/departamento, los filtra a los 3
   departamentos, y los exporta a `data/processed/poligonos.gpkg` (una capa por nivel).
5. Valida cada punto (RENIPRESS y SIGMED) contra el distrito que su propio registro
   declara, usando los polígonos cargados.
6. Exporta los datasets limpios a `data/processed/{renipress,sigmed}_clean.parquet`.

## Hallazgos de Fase 1 (para la sección de limitaciones del reporte)

- **Cruce espacial de población:** 74.96% de los centros poblados de SIGMED
  encontraron un centro poblado equivalente en la fuente de población (GeoPerú/INEI)
  dentro de un radio de 1000m. El 25% restante corresponde a centros poblados más
  granulares de SIGMED sin equivalente cercano en el catastro censal — se documenta
  como limitación real, no como error del pipeline (ver `config.md`,
  `poblacion_max_distancia_metros`).
- **Discordancia distrital en RENIPRESS:** de los establecimientos con coordenadas
  válidas (1992 de 2684; el resto no tiene coordenadas registradas), **40.2%** caen,
  según su coordenada real, en un distrito distinto al que declara su propio registro.
  En SIGMED esa misma tasa es de solo 0.7%, lo que sugiere que el problema está
  concentrado en el campo texto DISTRITO/UBIGEO de RENIPRESS, no en las coordenadas.

## Estado actual

- [x] Estructura del repositorio y `config.md`
- [x] `config_loader.py` (parseo de parámetros)
- [x] `acquisition.py` (descarga OSM automática; RENIPRESS/SIGMED/población/polígonos con TODO manual)
- [x] `validation.py` (las 6 reglas de validación requeridas, como funciones puras)
- [x] `poligonos.py` (carga, filtrado, validación de distrito declarado, export a GeoPackage)
- [x] `run_phase1.py` — pipeline de Fase 1 completo y corrido sobre los datos reales
- [ ] Fase 2 — Ruteo (OSRM/OSMnx/ORS), snapping, matriz origen×destino, caché
- [ ] Fase 3 — Métricas (bandas de cobertura, Gini, cruce con pobreza/ruralidad)
- [ ] Fase 4 — Dashboard Streamlit (incluye simulador de escenarios)
- [ ] Fase 5 — Reporte LaTeX

## Notas de reproducibilidad

- Todo parámetro (departamentos, categorías resolutivas, umbrales, rutas) vive en
  `config.md`, nunca hardcodeado en el código.
- `acquisition.py` es idempotente: una segunda corrida no vuelve a descargar lo que
  ya existe en `data/raw/`.
- Los polígonos administrativos (GEOGPSPERU/INEI) ya vienen en EPSG:4326 — no
  requieren reproyección; `poligonos.py` valida el CRS igual y reproyecta si
  la fuente cambiara en el futuro.
- La matriz de ruteo completa (Fase 2) se debe cachear en disco para que el dashboard
  (Fase 4) no dependa de un motor de ruteo corriendo en el momento de la demo.