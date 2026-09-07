"""
acquisition.py — Fase 1: descarga de fuentes crudas a data/raw/.

Reglas:
- Nunca modifica los archivos crudos ya descargados (idempotente).
- Si un archivo ya existe en raw_dir, lo salta y lo reporta.
- Si una fuente no responde, lo registra en logs/ y continúa con las demás
  (no debe tumbar todo el pipeline por una fuente caída).

Uso:
    python -m src.acquisition
"""
from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import requests

from src.config_loader import load_config

Path("logs").mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(Path("logs") / "acquisition.log", encoding="utf-8"),
    ],
)
log = logging.getLogger("acquisition")


@dataclass
class DownloadResult:
    name: str
    url: str
    path: Path
    status: str  # "descargado" | "ya_existia" | "error"
    detail: str = ""


def _download(name: str, url: str, dest: Path, timeout: int = 60) -> DownloadResult:
    if dest.exists() and dest.stat().st_size > 0:
        log.info("SKIP  %-12s ya existe en %s (%.1f KB)", name, dest, dest.stat().st_size / 1024)
        return DownloadResult(name, url, dest, "ya_existia")

    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        log.info("GET   %-12s %s", name, url)
        with requests.get(url, stream=True, timeout=timeout) as resp:
            resp.raise_for_status()
            tmp = dest.with_suffix(dest.suffix + ".part")
            with open(tmp, "wb") as f:
                for chunk in resp.iter_content(chunk_size=1 << 20):
                    f.write(chunk)
            tmp.rename(dest)
        log.info("OK    %-12s -> %s (%.1f KB)", name, dest, dest.stat().st_size / 1024)
        return DownloadResult(name, url, dest, "descargado")
    except Exception as exc:  # noqa: BLE001 — se quiere capturar cualquier fallo de red
        log.error("FAIL  %-12s %s (%s)", name, url, exc)
        return DownloadResult(name, url, dest, "error", detail=str(exc))


def _download_poblacion_sigrid(cfg, dest: Path, timeout: int = 120) -> DownloadResult:
    """Descarga población por centro poblado desde SIGRID (CENEPRED), filtrada a los
    departamentos de config.md. La capa limita a 1000 registros por página
    (MaxRecordCount), así que se pagina con resultOffset hasta agotar resultados."""
    url = cfg.url_poblacion_centros_poblados

    if dest.exists() and dest.stat().st_size > 0:
        log.info("SKIP  %-12s ya existe en %s", "poblacion", dest)
        return DownloadResult("poblacion", url, dest, "ya_existia")

    dest.parent.mkdir(parents=True, exist_ok=True)
    departamentos_sql = ", ".join(f"'{d}'" for d in cfg.departamentos)
    where = f"{cfg.poblacion_col_departamento} IN ({departamentos_sql})"
    headers = {"User-Agent": "Mozilla/5.0 (compatible; proyecto-golden-hour/1.0)"}

    features: list[dict] = []
    offset = 0
    page_size = 1000
    try:
        while True:
            params = {
                "where": where,
                "outFields": "*",
                "f": "geojson",
                "resultRecordCount": page_size,
                "resultOffset": offset,
            }
            log.info("GET   %-12s offset=%d", "poblacion", offset)
            resp = requests.get(url, params=params, headers=headers, timeout=timeout)
            resp.raise_for_status()
            try:
                data = resp.json()
            except ValueError:
                log.error(
                    "FAIL  %-12s el servidor no devolvió JSON válido. status=%d, "
                    "primeros 500 caracteres de la respuesta:\n%s",
                    "poblacion",
                    resp.status_code,
                    resp.text[:500],
                )
                return DownloadResult(
                    "poblacion", url, dest, "error", detail="respuesta no era JSON válido"
                )
            if "error" in data:
                log.error("FAIL  %-12s el servicio devolvió un error: %s", "poblacion", data["error"])
                return DownloadResult("poblacion", url, dest, "error", detail=str(data["error"]))
            page_features = data.get("features", [])
            features.extend(page_features)
            if len(page_features) < page_size:
                break
            offset += page_size

        import json

        geojson_out = {"type": "FeatureCollection", "features": features}
        with open(dest, "w", encoding="utf-8") as f:
            json.dump(geojson_out, f, ensure_ascii=False)
        log.info("OK    %-12s -> %s (%d centros poblados)", "poblacion", dest, len(features))
        return DownloadResult("poblacion", url, dest, "descargado")
    except Exception as exc:  # noqa: BLE001
        log.error("FAIL  %-12s %s (%s)", "poblacion", url, exc)
        return DownloadResult("poblacion", url, dest, "error", detail=str(exc))


def run(cfg=None) -> list[DownloadResult]:
    cfg = cfg or load_config()
    raw_dir = Path(cfg.raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)

    # NOTA: RENIPRESS y SIGMED no exponen un enlace de descarga directa estable;
    # ambos portales requieren navegar el sitio y seleccionar el dataset/versión.
    # Aquí se deja el patrón de descarga programática (para OSM, que sí tiene URL
    # directa), y se registra un TODO para las otras dos fuentes: descargar
    # manualmente el CSV/GeoJSON vigente y colocarlo en data/raw/ con el nombre
    # indicado, o reemplazar la URL por el enlace directo una vez identificado
    # inspeccionando el portal.
    fuentes = {
        "osm_peru": (cfg.url_osm_peru, raw_dir / "peru-latest.osm.pbf"),
    }

    resultados = [_download(name, url, dest) for name, (url, dest) in fuentes.items()]
    resultados.append(_download_poblacion_sigrid(cfg, Path(cfg.path_poblacion_raw)))

    for manual in ("renipress", "sigmed"):
        log.warning(
            "MANUAL %-12s requiere descarga manual desde el portal (ver config.md) — "
            "colocar el archivo resultante en %s/%s.csv|.geojson y documentar la fecha "
            "de descarga aquí.",
            manual,
            raw_dir,
            manual,
        )

    fecha = datetime.now(timezone.utc).isoformat(timespec="seconds")
    resumen_path = raw_dir / "_download_manifest.md"
    with open(resumen_path, "a", encoding="utf-8") as f:
        f.write(f"\n## Corrida {fecha}\n")
        for r in resultados:
            f.write(f"- {r.name}: {r.status} ({r.url})\n")
        f.write(
            "- renipress: PENDIENTE — descarga manual, declarar fecha aquí al colocarla\n"
            "- sigmed: PENDIENTE — descarga manual, declarar fecha aquí al colocarla\n"
        )
    log.info("Manifiesto de descargas actualizado en %s", resumen_path)
    return resultados


if __name__ == "__main__":
    run()
