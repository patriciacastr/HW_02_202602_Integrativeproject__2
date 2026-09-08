# Golden Hour — Acceso a salud resolutiva por tiempo de viaje

Proyecto integrador: análisis geoespacial de accesibilidad a establecimientos de salud
con capacidad resolutiva (categoría II-1 en adelante) en tres departamentos del Perú.

**Departamentos analizados:** Lambayeque (costa), Ayacucho (andino), San Martín (amazónico).
Cambiables sin tocar código — ver `config.md`.

## Estructura del repositorio

```
├── config.md # todos los parámetros del proyecto (departamentos, rutas, thresholds)
├── docker-compose.yml # levanta los 3 servidores OSRM (car/foot/bike) para Fase 2
├── requirements.txt
├── README.md
├── src/
│ ├── config_loader.py # parsea config.md a un objeto Python
│ ├── acquisition.py # Fase 1 — descarga de fuentes crudas (cacheado, idempotente)
│ ├── validation.py # Fase 1 — reglas de validación + reporte de calidad
│ ├── poligonos.py # Fase 1 — carga/filtra polígonos, valida punto vs. distrito declarado
│ ├── run_phase1.py # Fase 1 — orquesta acquisition + validation + población + polígonos
│ ├── obtener_bboxes.py # utilitario de un solo uso — calcula bboxes de los 3 departamentos
│ ├── routing.py # Fase 2 — cliente OSRM, matrices con caché, muestreo poblacional
│ ├── run_phase2.py # Fase 2 — orquesta muestreo + matrices + comparación entre modos
│ ├── metrics.py # Fase 3 — funciones puras: acceso, cobertura, Gini, urbano/rural, altitud
│ ├── run_phase3.py # Fase 3 — orquesta el cálculo de todas las métricas y exporta CSVs
│ └── export.py # Fase 5 — tablas/figuras para el reporte (pendiente)
├── data/
│ ├── raw/ # nunca se modifica a mano; solo la escribe acquisition.py o descarga manual
│ │ └── osrm/ # grafos OSRM compilados por perfil (car/foot/bike) — NO versionado (pesado)
│ ├── processed/ # salidas limpias de Fase 1 + poligonos.gpkg + routing_cache/ de Fase 2
│ └── outputs/ # CSVs de calidad de datos, comparación de modos, y métricas de Fase 3
├── app/
│ └── app.py # Fase 4 — dashboard Streamlit (pendiente)
├── report/
│ ├── main.tex # Fase 5 — reporte LaTeX (pendiente)
│ └── figures/
```

## Setup

```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

**Además, para Fase 2 necesitas Docker Desktop instalado y corriendo** (motor de ruteo OSRM).

## Paso 1 — Descargar datos crudos

```bash
python -m src.acquisition
```

Descarga automáticamente el extracto OSM de Perú a `data/raw/peru-latest.osm.pbf`.

**Los siguientes datasets requieren descarga manual**, colocar en la ruta indicada y
declarar la fecha en `data/raw/_download_manifest.md`:

- RENIPRESS → `data/raw/renipress.csv`
- SIGMED → `data/raw/sigmed/CP_P.shp`
- Población (GeoPerú/INEI, centros poblados) → `data/raw/poblacion_centros_poblados_geoperu/`
- Polígonos administrativos (GEOGPSPERU/INEI) → `data/raw/limites_geogpsperu/{distrito,provincia,departamento}/`

## Paso 2 — Ejecutar el pipeline de Fase 1

```bash
python -m src.run_phase1
```

Carga y valida RENIPRESS/SIGMED, cruza población espacialmente, carga polígonos
administrativos, valida cada punto contra su distrito declarado, y exporta todo a
`data/processed/`. Ver "Hallazgos de Fase 1" abajo.

## Paso 3 — Construir los grafos OSRM (Fase 2, un solo uso)

**Decisión técnica importante:** en vez de compilar el grafo sobre el `.pbf` de
Perú completo (220MB), se recorta primero a los 3 departamentos analizados
(con margen de 0.3° para no perder rutas que crucen la frontera departamental).
Esto fue necesario por restricción de hardware (8GB RAM totales; el `.pbf`
completo causaba un OOM kill durante `osrm-extract`), y de paso reduce
drásticamente el tiempo de cómputo.

```bash
# 1. Calcular los bounding boxes de los 3 departamentos (usa los polígonos de Fase 1)
python -m src.obtener_bboxes

# 2. Recortar el .pbf con osmium-tool (usar los bboxes impresos arriba)
docker run -it -v "${PWD}/data/raw:/wkd" mschilde/osmium-tool osmium extract --overwrite \
  --bbox=<bbox_departamento> -o /wkd/osmium_tmp/<nombre>.osm.pbf /wkd/peru-latest.osm.pbf
# (repetir para los 3 departamentos, luego fusionar con "osmium merge" en un solo .pbf)

# 3. Compilar el grafo para cada perfil (car, foot, bike) — repetir 3 veces:
docker run -t -v "${PWD}/data/raw/osrm/<perfil>:/data" osrm/osrm-backend osrm-extract -p /opt/<perfil>.lua /data/peru-3departamentos.osm.pbf
docker run -t -v "${PWD}/data/raw/osrm/<perfil>:/data" osrm/osrm-backend osrm-partition /data/peru-3departamentos.osrm
docker run -t -v "${PWD}/data/raw/osrm/<perfil>:/data" osrm/osrm-backend osrm-customize /data/peru-3departamentos.osrm

# 4. Levantar los 3 servidores
docker compose up -d
docker compose ps   # confirmar que los 3 digan "Up"
```

Los grafos compilados (`data/raw/osrm/`) NO se versionan (son pesados y
regenerables) — cualquiera que clone el repo debe repetir este paso.

## Paso 4 — Ejecutar el pipeline de Fase 2

Con los 3 servidores OSRM corriendo:

```bash
python -m src.run_phase2              # corrida completa
python -m src.run_phase2 --prueba 20  # solo 20 puntos, para probar rápido
```

Aplica muestreo poblacional estratificado por distrito (la demanda real,
18713 puntos, excede `max_demand_points=5000`), calcula la matriz completa de
auto (demanda × todos los establecimientos) y las matrices de a pie/bici
(demanda × solo establecimientos resolutivos), y compara los 3 modos de
transporte. Resultados cacheados en `data/processed/routing_cache/` y
`data/outputs/comparacion_modos.csv`.

## Paso 5 — Ejecutar el pipeline de Fase 3

No requiere Docker/OSRM corriendo (solo lee la matriz ya calculada en Fase 2):

```bash
python -m src.run_phase3
```

Calcula el tiempo de acceso al establecimiento resolutivo más cercano por auto,
bandas de cobertura poblacional, promedios ponderados por distrito/provincia/
departamento, el ranking de brecha crítica, el coeficiente de Gini del acceso,
la clasificación y contraste urbano/rural, y el cruce con altitud. Todos los
resultados se exportan como CSV a `data/outputs/`.

## Hallazgos de Fase 1 (para la sección de limitaciones del reporte)

- **Cruce espacial de población:** 74.96% de match a 1000m entre SIGMED y la
  fuente de población (GeoPerú/INEI). El 25% restante corresponde a centros
  poblados más granulares sin equivalente censal cercano — limitación real,
  no error del pipeline.
- **Discordancia distrital en RENIPRESS:** de los establecimientos con
  coordenadas válidas, **40.2%** caen en un distrito distinto al que declara
  su propio registro (vs. 0.7% en SIGMED) — sugiere error de digitación en el
  campo texto DISTRITO/UBIGEO de RENIPRESS, no en las coordenadas.

## Hallazgos de Fase 2 (para la sección de discusión/limitaciones del reporte)

- **Muestreo poblacional:** con solo 26.7% de los puntos de demanda (5004 de
  18713) se conserva el 97.4% de la población total representada.
- **Pares no-ruteables por recorte geográfico:** 64.9% de los pares en la
  matriz de auto son "no ruteables" — esperado, no un error: el grafo se
  recortó a 3 zonas separadas sin las carreteras que las conectan entre sí,
  así que un punto de demanda en un departamento nunca puede rutear hacia un
  hospital en otro. El resultado de "hospital más cercano" no se ve afectado.
- **Auto vs. a pie — hospital resolutivo distinto:** en **40.4%** de los
  puntos de demanda, el hospital resolutivo más cercano EN AUTO es distinto
  al más cercano CAMINANDO — hallazgo geográfico real (la ruta vial puede
  rodear un accidente geográfico que el camino peatonal cruza directo).
- **Ratio de tiempo foot/car:** mediana 12.0x, media 15.3x.

## Hallazgos de Fase 3 (para resultados/discusión/limitaciones del reporte)

- **Cobertura:** 94.2% de la población está a ≤30 min de un hospital
  resolutivo; **0.7% (≈70,800 personas)** está a más de 2 horas.
- **Desigualdad de acceso — Gini = 0.6867.** Muy alto: para referencia, el
  Gini de ingresos en Perú ronda 0.40-0.45. El acceso a salud resolutiva
  está más desigualmente distribuido que el ingreso mismo.
- **Brecha crítica:** el distrito peor atendido es Oronccoy (Ayacucho), con
  272.9 min promedio ponderado — casi toda la lista de los 15 peores
  distritos pertenece a Ayacucho (zona andina).
- **Urbano vs. rural:** definidos como urbano = capital de distrito/
  provincia/departamento (campo CAPITAL de SIGMED) o población ≥2000
  habitantes; todo lo demás rural. Resultado: 6.4 min promedio en zonas
  urbanas vs. **62.2 min en zonas rurales** (~10x peor).
- **Cruce con altitud:** correlación de Pearson ponderada r=0.19 (positiva
  pero débil) — sin embargo, el desglose por banda altitudinal muestra una
  relación NO lineal: 6.7 min (costa, 0-500m) → 47.4 min (500-2000m) →
  11.1 min (2000-3500m) → 94.2 min (>3500m, puna). La correlación lineal
  global subestima la relación real por ser no-monótona. **La relación es
  correlacional, no causal**: la altitud en sí no causa la demora; está
  asociada a terreno más difícil, menor densidad vial, y mayor dispersión
  poblacional, que son las causas mecánicas reales.
- **Dimensión de cruce elegida: altitud, no pobreza** — SIGMED ya trae el
  campo `Z` (altitud), evitando una descarga adicional del mapa de pobreza
  del INEI bajo restricción de tiempo.

## Estado actual

- [x] Fase 1 completa (acquisition, validation, población, polígonos)
- [x] Fase 2 completa (grafos OSRM, matrices car/foot/bike, comparación de modos)
- [x] Fase 3 completa (acceso, cobertura, Gini, urbano/rural, cruce con altitud)
- [ ] Fase 4 — Dashboard Streamlit (incluye simulador de escenarios)
- [ ] Fase 5 — Reporte LaTeX

## Notas de reproducibilidad

- Todo parámetro vive en `config.md`, nunca hardcodeado en el código.
- `acquisition.py` es idempotente.
- Los grafos OSRM no se versionan; se regeneran con los comandos del Paso 3.
- Las matrices de ruteo se cachean en `data/processed/routing_cache/` — si
  ya existe el archivo de caché, `run_phase2.py` NO recalcula.
- Todas las funciones de `metrics.py` son puras (DataFrame → DataFrame); el
  dashboard de Fase 4 solo debe leer los CSVs exportados, sin lógica propia
  de cálculo de métricas.
- Las columnas `CAPITAL` y `Z` (altitud) de SIGMED vienen tipadas como texto
  en el shapefile original; `metrics.py` las convierte a numérico
  explícitamente antes de operar.