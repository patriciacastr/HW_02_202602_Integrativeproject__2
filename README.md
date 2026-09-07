# Golden Hour — Acceso a salud resolutiva por tiempo de viaje

Proyecto integrador: análisis geoespacial de accesibilidad a establecimientos de salud
con capacidad resolutiva (categoría II-1 en adelante) en tres departamentos del Perú.

**Departamentos analizados:** Lambayeque (costa), Ayacucho (andino), San Martín (amazónico).
Cambiables sin tocar código — ver `config.md`.

## Estructura del repositorio

```
├── config.md              # todos los parámetros del proyecto (departamentos, rutas, thresholds)
├── requirements.txt
├── README.md
├── src/
│   ├── config_loader.py   # parsea config.md a un objeto Python
│   ├── acquisition.py     # Fase 1 — descarga de fuentes crudas (cacheado, idempotente)
│   ├── validation.py       # Fase 1 — reglas de validación + reporte de calidad
│   ├── routing.py          # Fase 2 — motor de ruteo + caché de matriz (pendiente)
│   ├── metrics.py          # Fase 3 — métricas de accesibilidad (pendiente)
│   └── export.py           # Fase 5 — tablas/figuras para el reporte (pendiente)
├── data/
│   ├── raw/                # nunca se modifica a mano; solo la escribe acquisition.py o descarga manual
│   ├── processed/          # salidas de validation.py, en GeoParquet/GeoPackage
│   └── outputs/            # CSVs finales de metrics.py, tablas del reporte
├── app/
│   └── app.py              # Fase 4 — dashboard Streamlit (pendiente)
├── report/
│   ├── main.tex             # Fase 5 — reporte LaTeX (pendiente)
│   └── figures/
└── logs/                   # logs de ejecución (incluye el reporte de calidad de datos)
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
(idempotente: si ya existe, lo salta). **RENIPRESS y SIGMED requieren descarga manual**
desde sus portales (no exponen un enlace de descarga directa estable) — ver las URLs
y el TODO en `config.md` y en la salida del script. Colocar los archivos resultantes
en `data/raw/` con el nombre indicado y **declarar la fecha de descarga** en
`data/raw/_download_manifest.md` (el script ya deja la plantilla).

## Paso 2 — Validar y procesar

```bash
python -m src.validation   # (ejecutar vía el pipeline principal, ver TODO en el módulo)
```

Genera el reporte de calidad de datos: cuántos registros se marcaron por cada regla
(coordenadas faltantes/cero, fuera del bbox de Perú, lat/lon invertidos, fuera del
distrito declarado, códigos duplicados, problemas de encoding) y qué se hizo con ellos.

## Estado actual

- [x] Estructura del repositorio y `config.md`
- [x] `config_loader.py` (parseo de parámetros)
- [x] `acquisition.py` (descarga OSM automática; RENIPRESS/SIGMED con TODO manual)
- [x] `validation.py` (las 6 reglas de validación requeridas, como funciones puras)
- [ ] Pipeline de Fase 1 que orquesta acquisition + validation sobre los datos reales
- [ ] Fase 2 — Ruteo (OSRM/OSMnx/ORS), snapping, matriz origen×destino, caché
- [ ] Fase 3 — Métricas (bandas de cobertura, Gini, cruce con pobreza/ruralidad)
- [ ] Fase 4 — Dashboard Streamlit (incluye simulador de escenarios)
- [ ] Fase 5 — Reporte LaTeX

## Notas de reproducibilidad

- Todo parámetro (departamentos, categorías resolutivas, umbrales, rutas) vive en
  `config.md`, nunca hardcodeado en el código.
- `acquisition.py` es idempotente: una segunda corrida no vuelve a descargar lo que
  ya existe en `data/raw/`.
- La matriz de ruteo completa (Fase 2) se debe cachear en disco para que el dashboard
  (Fase 4) no dependa de un motor de ruteo corriendo en el momento de la demo.
