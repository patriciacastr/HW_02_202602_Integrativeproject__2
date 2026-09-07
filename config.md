# config.md — Golden Hour: parámetros del proyecto

Este archivo es la única fuente de verdad para parámetros. `src/config_loader.py` lo parsea.
No hardcodear ninguno de estos valores en el código.

## Departamentos de análisis

| rol        | departamento | código INEI (ubigeo dep.) |
|------------|--------------|---------------------------|
| costa      | LAMBAYEQUE   | 14                        |
| andino     | AYACUCHO     | 05                        |
| amazónico  | SAN MARTIN   | 22                        |

- `departamentos`: ["LAMBAYEQUE", "AYACUCHO", "SAN MARTIN"]
- `ubigeo_departamentos`: ["14", "05", "22"]

## Rutas de datos

- `raw_dir`: data/raw/
- `processed_dir`: data/processed/
- `outputs_dir`: data/outputs/
- `logs_dir`: logs/

## Fuentes de datos (declarar fecha de descarga real al ejecutar)

- `url_renipress`: https://www.datosabiertos.gob.pe/dataset/registro-nacional-de-entidades-prestadoras-de-servicios-de-salud-renipress
- `url_sigmed`: https://sigmed.minedu.gob.pe/descargas/
- `path_renipress_raw`: data/raw/renipress.csv
- `path_sigmed_raw`: data/raw/sigmed/CP_P.shp
- `url_osm_peru`: https://download.geofabrik.de/south-america/peru-latest.osm.pbf
- `fuente_limites_administrativos`: GEOGPSPERU (INEI actualizado), descarga manual 6 de setiembre 2026 — ver _download_manifest.md

## Población por centro poblado (resuelve el pendiente de SIGMED)

**Fuente usada: GeoPerú/INEI (respaldo manual)** — SIGRID (CENEPRED) resultó no
confiable (timeouts/errores de servidor recurrentes, confirmado en pruebas), se
descartó como fuente automática.

Shapefile descargado manualmente desde:
https://www.geogpsperu.com/2017/08/descarga-gratis-centros-poblados-censo.html
(link "GEOPERU (INEI) — Centros Poblados"), colocado en
`data/raw/poblacion_centros_poblados_geoperu/`.

**Importante:** el código de centro poblado de esta fuente (`CODIGO`, formato
UBIGEO+secuencial, ej. `0101010001`) NO es compatible con el `CODCP` de SIGMED
(otro esquema de codificación del INEI, ej. `661851`). El cruce se hace por
**proximidad espacial** (vecino más cercano dentro de un radio máximo), no por
código — ver `cruzar_poblacion()` en `run_phase1.py`.

- `path_poblacion_raw`: data/raw/poblacion_centros_poblados_geoperu/Centros_Poblados_Categoria_INEI_geogpsperu_SuyoPomalia.shp
- `poblacion_col_total`: POBLACION
- `poblacion_col_departamento`: DEPARTAMEN
- `poblacion_max_distancia_metros`: 1000  # radio máximo para considerar un match válido en el cruce espacial

Fuente descartada (SIGRID, se deja documentada por si el servicio se estabiliza):
- `url_poblacion_sigrid_descartado`: https://sigrid.cenepred.gob.pe/arcgis/rest/services/sectores/tcp_informacion_complementaria/MapServer/2010000/query

## Definición de capacidad resolutiva (Fase 1)

- `categorias_resolutivas`: ["II-1", "II-2", "II-E", "III-1", "III-2", "III-E"]
- `categorias_no_resolutivas`: ["I-1", "I-2", "I-3", "I-4"]
- `categorias_invalidas`: ["0"]  # valor basura encontrado en CATEGORIA real — tratar como dato faltante, no como no-resolutivo
- `estado_operativo_valido`: ["ACTIVO"]  # confirmado contra datos reales — únicos 7 valores de ESTADO son: ACTIVO, BAJA DEFINITIVA, CIERRE TEMPORAL DE OFICIO, BAJA PROVISIONAL, CIERRE TEMPORAL DE PARTE, BAJA PROVISIONAL DE OFICIO, BAJA DEFINITIVA DE OFICIO

## Nombres de columnas reales (confirmados por src/inspect_raw_data.py)

RENIPRESS (`data/raw/renipress.csv`, separador `;` autodetectado):
- `renipress_col_codigo`: COD_IPRESS
- `renipress_col_categoria`: CATEGORIA
- `renipress_col_estado`: ESTADO
- `renipress_col_lat`: NORTE
- `renipress_col_lon`: ESTE
- `renipress_col_departamento`: DEPARTAMENTO
- `renipress_col_provincia`: PROVINCIA
- `renipress_col_distrito`: DISTRITO
- `renipress_col_ubigeo`: UBIGEO
- `renipress_col_institucion`: INSTITUCION

SIGMED (`data/raw/sigmed/CP_P.shp`, CRS ya en EPSG:4326, no requiere reproyección):
- `sigmed_col_ubigeo`: UBIGEO
- `sigmed_col_distrito`: DIST
- `sigmed_col_provincia`: PROV
- `sigmed_col_departamento`: DEP
- `sigmed_col_codigo_cp`: CODCP
- `sigmed_col_nombre_cp`: NOMCP
- `sigmed_col_lon`: XGD
- `sigmed_col_lat`: YGD
- `sigmed_col_poblacion`: RESUELTO — ver sección "Población por centro poblado" más abajo (fuente SIGRID/CENEPRED, cruzar por CODCP=codccpp)

## Polígonos administrativos (distrito, provincia, departamento)

Fuente: GEOGPSPERU (shapefile INEI actualizado). CRS ya en EPSG:4326,
confirmado por inspección — no requiere reproyección.

- `poligonos_fuente`: geogpsperu
- `path_poligonos_distrito`: data/raw/limites_geogpsperu/distrito/DISTRITOS.shp
- `path_poligonos_provincia`: data/raw/limites_geogpsperu/provincia/PROVINCIAS.shp
- `path_poligonos_departamento`: data/raw/limites_geogpsperu/departamento/DEPARTAMENTOS.shp
- `poligonos_crs_salida`: EPSG:4326
- `poligonos_campo_ubigeo_distrito`: UBIGEO
- `poligonos_campo_departamento`: DEPARTAMEN
- `path_poligonos_gpkg_salida`: data/processed/poligonos.gpkg

## Validación (Fase 1) — bounding box Perú

- `lon_min`: -81.4
- `lon_max`: -68.6
- `lat_min`: -18.4
- `lat_max`: -0.04

## Ruteo (Fase 2)

- `motor_ruteo`: OSRM  # opciones: OSRM | OSMNX | ORS
- `perfiles`: ["car", "foot", "bike"]
- `max_demand_points`: 5000
- `estrategia_muestreo`: "poblacional_estratificada_por_distrito"  # aplica solo si se excede max_demand_points
- `ors_api_key`: (dejar vacío si no se usa OpenRouteService; leer de variable de entorno ORS_API_KEY)

## Métricas (Fase 3)

- `bandas_cobertura_min`: [30, 60, 120]
- `medida_desigualdad`: "gini"  # alternativa: "lorenz"
- `dimension_cruce`: "pobreza"  # alternativa: "ruralidad" | "poblacion_menor_5" | "altitud"

## Dashboard (Fase 4)

- `filtros_sidebar`: ["departamento", "provincia", "categoria", "institucion", "umbral_tiempo"]

## Reporte (Fase 5)

- `paginas_min`: 8
- `paginas_max`: 12
