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
- `fuente_limites_administrativos`: (declarar aquí la fuente elegida, ej. INEI / GADM / IGN, con fecha de descarga)

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
- `sigmed_col_poblacion`: PENDIENTE — SIGMED (CP_P) no trae columna de población. Se necesita cruzar por UBIGEO/CODCP con una fuente de población (ej. INEI - Censos Nacionales 2017, o proyecciones poblacionales por centro poblado), declarar aquí la fuente elegida y su fecha de descarga en cuanto se resuelva.

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