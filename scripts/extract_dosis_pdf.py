"""
VetDose — Extractor de Dosis desde Fichas Técnicas AEMPS
=========================================================
Lee vademecum_base.json, descarga los PDFs de las fichas técnicas,
extrae el texto de la sección de posología y detecta patrones de dosis.

Salida: static/vademecum_dosis.json
        Cada entrada: { id, nombre, posologia_raw, dosis }
        donde dosis = { perro: {valor, max, unidad, texto} | null,
                        gato:  {valor, max, unidad, texto} | null }

Uso:
    python scripts/extract_dosis_pdf.py
    python scripts/extract_dosis_pdf.py --limit 50
    python scripts/extract_dosis_pdf.py --id "EU/2/22/288/003"

Requiere: pip install pdfminer.six requests
"""

import os, sys, re, json, time, argparse, io, logging
from pathlib import Path
from typing import Optional

import requests
from pdfminer.high_level import extract_text
from pdfminer.pdfpage import PDFPage
from pdfminer.pdfinterp import PDFResourceManager, PDFPageInterpreter
from pdfminer.converter import TextConverter
from pdfminer.layout import LAParams

# ── Rutas ────────────────────────────────────────────────────────────────────
ROOT      = Path(__file__).resolve().parent.parent
BASE_JSON = ROOT / "static" / "vademecum_base.json"
OUT_JSON  = ROOT / "static" / "vademecum_dosis.json"
CKPT_FILE = ROOT / "scripts" / ".extract_checkpoint.json"

# ── Configuración ─────────────────────────────────────────────────────────────
DELAY_SECS   = 1.5   # pausa entre peticiones — aumentado para evitar 429 en EMA
TIMEOUT_SECS = 20
MAX_PDF_MB   = 10
SESSION_HDR  = {"User-Agent": "VetDose-Research/1.0 (veterinary dose extractor)"}

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger("vetdose")

# ── Patrones de dosis ─────────────────────────────────────────────────────────
# Captura: "10 mg/kg", "5-10 mg/kg", "1,5 mg/kg", "0,1 ml/kg", "200 UI/kg"
_DOSE_RE = re.compile(
    r"(\d+[,.]?\d*)"                         # valor mínimo
    r"(?:\s*(?:[-–a]|hasta)\s*"              # rango opcional
      r"(\d+[,.]?\d*))?"                     # valor máximo
    r"\s*(mg|mcg|µg|ml|ui|iu|g)"            # unidad de dosis
    r"\s*/\s*"
    r"(kg|10\s*kg|animal|perro|gato|felino|canino)",
    re.IGNORECASE
)

# Sección 4 de la ficha técnica EU: posología
_SECTION_RE = re.compile(
    r"(?:4\.|POSOLOG[IÍ]A|VÍA DE ADMINISTRACIÓN|DOSIS\s+RECOMENDADA)"
    r"(.+?)"
    r"(?:5\.|CONTRAINDICACIONES|PRECAUCIONES|ADVERTENCIAS|\Z)",
    re.IGNORECASE | re.DOTALL
)

# Contexto de especie (palabras clave ±200 chars alrededor de la dosis)
_PERRO_KW = re.compile(r"\b(perro|canino|canis|dog)\b", re.IGNORECASE)
_GATO_KW  = re.compile(r"\b(gato|felino|felis|cat)\b",  re.IGNORECASE)


# ── Extracción de texto PDF ───────────────────────────────────────────────────
def pdf_bytes_to_text(pdf_bytes: bytes) -> str:
    """Convierte bytes de PDF a texto plano usando pdfminer."""
    rsrc = PDFResourceManager()
    buf  = io.StringIO()
    laparams = LAParams(line_margin=0.5, word_margin=0.1)
    device = TextConverter(rsrc, buf, laparams=laparams)
    interp = PDFPageInterpreter(rsrc, device)
    try:
        for page in PDFPage.get_pages(
            io.BytesIO(pdf_bytes),
            caching=True,
            check_extractable=True
        ):
            interp.process_page(page)
    except Exception:
        pass
    device.close()
    return buf.getvalue()


def download_pdf(url: str, session: requests.Session) -> Optional[bytes]:
    try:
        resp = session.get(url, timeout=TIMEOUT_SECS, stream=True)
        resp.raise_for_status()
        chunks = []
        size = 0
        for chunk in resp.iter_content(65536):
            chunks.append(chunk)
            size += len(chunk)
            if size > MAX_PDF_MB * 1024 * 1024:
                log.warning("  PDF demasiado grande (>%d MB), omitiendo", MAX_PDF_MB)
                return None
        return b"".join(chunks)
    except Exception as e:
        log.warning("  Error descargando PDF: %s", e)
        return None


# ── Extracción de dosis ───────────────────────────────────────────────────────
def _normalise_num(s: str) -> float:
    return float(s.replace(",", "."))


def extract_section(text: str) -> str:
    """Extrae solo la sección de posología del texto completo."""
    m = _SECTION_RE.search(text)
    if m:
        return m.group(1)[:4000]   # limitar a 4000 chars
    # Fallback: primeros 3000 chars del documento completo
    return text[:3000]


def _species_of_match(text: str, match_start: int, match_end: int) -> str:
    """Devuelve 'perro', 'gato', 'ambos' o 'desconocido' según el contexto."""
    ctx = text[max(0, match_start - 200) : match_end + 200]
    has_dog = bool(_PERRO_KW.search(ctx))
    has_cat = bool(_GATO_KW.search(ctx))
    if has_dog and has_cat:
        return "ambos"
    if has_dog:
        return "perro"
    if has_cat:
        return "gato"
    return "desconocido"


def parse_dosis(section_text: str) -> dict:
    """
    Devuelve dict con claves 'perro' y 'gato', cada una:
      None  — no detectado
      { valor, max, unidad, texto }
    """
    results = {"perro": None, "gato": None}

    for m in _DOSE_RE.finditer(section_text):
        val_min = _normalise_num(m.group(1))
        val_max = _normalise_num(m.group(2)) if m.group(2) else None
        unidad  = m.group(3).lower().replace("µg", "mcg")
        per_kg  = m.group(4).lower()

        # Normalizar "X mg / 10 kg" → X/10 mg/kg
        if "10" in per_kg:
            val_min = round(val_min / 10, 4)
            val_max = round(val_max / 10, 4) if val_max else None
            per_kg  = "kg"

        unidad_final = f"{unidad}/{per_kg}" if per_kg in ("kg", "animal") else f"{unidad}/kg"
        texto = m.group(0).strip()

        entry = {"valor": val_min, "max": val_max, "unidad": unidad_final, "texto": texto}

        sp = _species_of_match(section_text, m.start(), m.end())

        if sp in ("perro", "ambos", "desconocido") and results["perro"] is None:
            results["perro"] = entry
        if sp in ("gato", "ambos") and results["gato"] is None:
            results["gato"] = entry
        if sp == "desconocido" and results["gato"] is None:
            results["gato"] = entry

        # Terminamos si encontramos ambas especies
        if results["perro"] and results["gato"]:
            break

    return results


# ── Checkpoint helpers ────────────────────────────────────────────────────────
def load_checkpoint() -> dict:
    if CKPT_FILE.exists():
        try:
            return json.loads(CKPT_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_checkpoint(data: dict):
    CKPT_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Extrae dosis de fichas técnicas AEMPS")
    parser.add_argument("--limit",   type=int,  default=0,  help="Procesar solo N fármacos (0 = todos)")
    parser.add_argument("--id",      type=str,  default="", help="Procesar solo este ID")
    parser.add_argument("--resume",  action="store_true",   help="Retomar desde checkpoint")
    parser.add_argument("--delay",   type=float, default=DELAY_SECS, help="Segundos entre peticiones")
    args = parser.parse_args()

    # Cargar base
    if not BASE_JSON.exists():
        log.error("No encontrado: %s", BASE_JSON)
        sys.exit(1)

    drugs = json.loads(BASE_JSON.read_text(encoding="utf-8"))
    log.info("Cargados %d medicamentos de %s", len(drugs), BASE_JSON.name)

    # Filtrar si se especificó --id
    if args.id:
        drugs = [d for d in drugs if d["id"] == args.id]
        if not drugs:
            log.error("ID no encontrado: %s", args.id)
            sys.exit(1)

    # Solo los que tienen urlFicha
    drugs = [d for d in drugs if d.get("urlFicha")]
    log.info("Con ficha técnica disponible: %d", len(drugs))

    if args.limit:
        drugs = drugs[: args.limit]
        log.info("Limitado a %d fármacos", args.limit)

    # Checkpoint
    checkpoint = load_checkpoint() if (args.resume or not args.id) else {}

    # Cargar resultados anteriores si existen
    existing: dict[str, dict] = {}
    if OUT_JSON.exists():
        try:
            for entry in json.loads(OUT_JSON.read_text(encoding="utf-8")):
                existing[entry["id"]] = entry
        except Exception:
            pass

    session = requests.Session()
    session.headers.update(SESSION_HDR)

    ok_count  = 0
    err_count = 0
    skip_count = 0

    for i, drug in enumerate(drugs, 1):
        did   = drug["id"]
        name  = drug["nombre"]
        url   = drug["urlFicha"]

        # Ya procesado con éxito — omitir en resume
        if args.resume and checkpoint.get(did) == "ok":
            skip_count += 1
            continue

        prefix = f"[{i:4d}/{len(drugs)}]"
        log.info("%s %s", prefix, name[:70])

        pdf_bytes = download_pdf(url, session)
        if not pdf_bytes:
            err_count += 1
            checkpoint[did] = "error"
            time.sleep(args.delay)
            continue

        try:
            full_text = pdf_bytes_to_text(pdf_bytes)
        except Exception as e:
            log.warning("  Error extrayendo texto: %s", e)
            err_count += 1
            checkpoint[did] = "error"
            time.sleep(args.delay)
            continue

        section  = extract_section(full_text)
        dosis    = parse_dosis(section)

        # Mostrar resultado
        d_perro = dosis["perro"]
        d_gato  = dosis["gato"]
        if d_perro or d_gato:
            log.info("  🐕 %s  |  🐈 %s",
                     d_perro["texto"] if d_perro else "—",
                     d_gato["texto"]  if d_gato  else "—")
        else:
            log.info("  (sin dosis detectada en posología)")

        existing[did] = {
            "id":            did,
            "nombre":        name,
            "posologia_raw": section[:600].strip(),  # extracto del texto
            "dosis":         dosis,
        }

        checkpoint[did] = "ok"
        ok_count += 1

        # Guardar incrementalmente cada 10 fármacos
        if ok_count % 10 == 0:
            _flush(existing)
            save_checkpoint(checkpoint)
            log.info("  → Guardado parcial (%d procesados)", ok_count)

        time.sleep(args.delay)

    # Guardar final
    _flush(existing)
    save_checkpoint(checkpoint)

    total = ok_count + err_count + skip_count
    log.info("")
    log.info("══ Resumen ══════════════════════════════")
    log.info("  Procesados : %d", ok_count)
    log.info("  Errores    : %d", err_count)
    log.info("  Omitidos   : %d (ya en checkpoint)", skip_count)
    log.info("  Con dosis  : %d perro  /  %d gato",
             sum(1 for e in existing.values() if e["dosis"]["perro"]),
             sum(1 for e in existing.values() if e["dosis"]["gato"]))
    log.info("  Salida     : %s", OUT_JSON)


def _flush(data: dict):
    entries = sorted(data.values(), key=lambda x: x["id"])
    OUT_JSON.write_text(
        json.dumps(entries, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


if __name__ == "__main__":
    main()
