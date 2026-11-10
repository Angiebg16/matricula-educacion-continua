#!/usr/bin/env python3
"""Baja las respuestas de LimeSurvey y genera los archivos que lee la página.

Dos modos:
  1) API (automático): si existen las variables LS_URL, LS_USER y LS_PASSWORD,
     se conecta a LimeSurvey (RemoteControl, JSON-RPC) y baja las respuestas.
  2) Manual: si no hay API, lee el archivo data/manual/respuestas.csv
     (exportado a mano desde LimeSurvey).

Salida (carpeta data/):
  summary.json      -> números y gráficos de la página
  respuestas.csv    -> el archivo que se descarga desde la página
"""
import base64
import csv
import io
import json
import os
import re
import sys
import unicodedata
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
DATA = ROOT / "data"
MANUAL = DATA / "manual" / "respuestas.csv"

# Código de pregunta en LimeSurvey -> nombre de columna en el CSV
ALL_COLUMNS = [
    ("id", "ID"),
    ("submitdate", "Fecha de envío"),
    ("A6", "Curso"),
    ("A7", "Grado académico"),
    ("A8", "Área de estudio"),
    ("A14", "Horario preferido"),
    ("PROV", "Provincia"),
    ("A3_SQ2", "Cantón"),
    ("A3_SQ3", "Distrito"),
    ("A9", "Lugar de trabajo"),
    ("SLA1", "Sector institucional"),
    ("A1_SQ1", "Nombre"),
    ("A1_SQ2", "Primer apellido"),
    ("A1_SQ3", "Segundo apellido"),
    ("A2", "Cédula"),
    ("A10_SQ1", "Tel. trabajo"),
    ("A10_SQ2", "Tel. habitación"),
    ("A10_SQ3", "Tel. celular"),
    ("A13", "Correo electrónico"),
]
# Columnas con datos personales: solo salen si publish_personal_data = true
PERSONAL = {"A3_SQ3", "A1_SQ1", "A1_SQ2", "A1_SQ3", "A2",
            "A10_SQ1", "A10_SQ2", "A10_SQ3", "A13"}
NO_CEDULA = {"A2"}  # la cédula nunca se publica


def rpc(url, method, params):
    body = json.dumps({"method": method, "params": params, "id": 1}).encode()
    req = urllib.request.Request(url, data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        res = json.load(r)
    if res.get("error"):
        raise RuntimeError(f"Error de LimeSurvey: {res['error']}")
    return res["result"]


def fetch_api():
    base = os.environ["LS_URL"].rstrip("/")
    url = base if base.endswith("remotecontrol") else base + "/index.php/admin/remotecontrol"
    key = rpc(url, "get_session_key", [os.environ["LS_USER"], os.environ["LS_PASSWORD"]])
    if isinstance(key, dict):
        raise RuntimeError(f"No se pudo iniciar sesión en la API: {key}")
    try:
        # CSV, idioma, todas las respuestas, encabezados = código, respuestas = texto completo
        out = rpc(url, "export_responses",
                  [key, int(CONFIG["survey_id"]), "csv", CONFIG.get("language", "es"),
                   "all", "code", "long"])
        if isinstance(out, dict):
            # LimeSurvey devuelve {"status": "No Data..."} si aún no hay respuestas
            print(f"Aviso de LimeSurvey: {out.get('status')}")
            return []
        text = base64.b64decode(out).decode("utf-8-sig")
    finally:
        try:
            rpc(url, "release_session_key", [key])
        except Exception:
            pass
    return parse_csv(text)


def parse_csv(text):
    first = text.splitlines()[0] if text.strip() else ""
    delim = ";" if first.count(";") >= first.count(",") and ";" in first else \
            "\t" if "\t" in first else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delim)
    rows = []
    for r in reader:
        # A1[SQ1] -> A1_SQ1
        rows.append({re.sub(r"\[(.+?)\]", r"_\1", (k or "").strip()): (v or "").strip()
                     for k, v in r.items()})
    return rows


def fetch_manual():
    if not MANUAL.exists():
        print("No hay credenciales de API ni archivo manual: se deja todo en cero.")
        return []
    return parse_csv(MANUAL.read_text(encoding="utf-8-sig"))


PROVINCIAS = ["San José", "Alajuela", "Cartago", "Heredia",
              "Guanacaste", "Puntarenas", "Limón"]


def _fold(v):
    v = unicodedata.normalize("NFD", v.strip().lower())
    return "".join(ch for ch in v if unicodedata.category(ch) != "Mn")


def normalize_province(v):
    """Lleva cualquier texto de provincia a una de las 7 (o lo deja limpio)."""
    v = re.sub(r"^provincia de\s+", "", (v or "").strip(), flags=re.I)
    for p in PROVINCIAS:
        if _fold(v) == _fold(p):
            return p
    return v


SECTORES = CONFIG.get("sectores", [])


def counts(values, fixed=()):
    """Cuenta valores; las categorías fijas salen siempre, aunque tengan 0."""
    c = Counter(v for v in values if v)
    out = [{"label": k, "value": n} for k, n in c.most_common()]
    seen = {o["label"] for o in out}
    out += [{"label": f, "value": 0} for f in fixed if f not in seen]
    return out


def missing(values):
    return sum(1 for v in values if not v)


def slug(text):
    t = re.sub(r"[^a-z0-9]+", "-", _fold(text)).strip("-")
    return t[:60] or "curso"


def stats(subset):
    """Todos los números de un grupo de matriculados (todos los cursos o uno)."""
    by_day = Counter(r["submitdate"][:10] for r in subset)
    acc, daily = 0, []
    for d in sorted(by_day):
        acc += by_day[d]
        daily.append({"date": d, "nuevos": by_day[d], "acumulado": acc})
    return {
        "total": len(subset),
        "grado": counts(r.get("A7", "") for r in subset),
        "horario": counts(r.get("A14", "") for r in subset),
        "provincia": counts((r["PROV"] for r in subset), PROVINCIAS),
        "provincia_sin_dato": missing(r["PROV"] for r in subset),
        "sector": counts((r.get("SLA1", "") for r in subset), SECTORES),
        "sector_sin_dato": missing(r.get("SLA1", "") for r in subset),
        "daily": daily,
    }


def main():
    DATA.mkdir(exist_ok=True)
    use_api = all(os.environ.get(k) for k in ("LS_URL", "LS_USER", "LS_PASSWORD"))
    rows = fetch_api() if use_api else fetch_manual()
    print(f"Modo: {'API' if use_api else 'manual'} · filas recibidas: {len(rows)}")

    for r in rows:
        r["PROV"] = normalize_province(r.get("PROV") or r.get("A3_SQ1", ""))

    complete = [r for r in rows if r.get("submitdate")]
    incomplete = len(rows) - len(complete)
    complete.sort(key=lambda r: r.get("submitdate", ""))
    total = len(complete)

    publish_personal = bool(CONFIG.get("publish_personal_data"))
    cols = [(c, n) for c, n in ALL_COLUMNS
            if (publish_personal and c not in NO_CEDULA) or c not in PERSONAL]

    def write_csv(path, subset):
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, delimiter=";")  # ';' para que Excel en español abra columnas
            w.writerow([n for _, n in cols])
            for r in subset:
                w.writerow([r.get(c, "") for c, _ in cols])

    # --- un bloque de números por curso (se crean solos al aparecer cursos nuevos) ---
    courses = []
    keep = {"respuestas.csv"}
    for c in counts(r.get("A6", "") for r in complete):
        subset = [r for r in complete if r.get("A6", "") == c["label"]]
        fname = f"respuestas-{slug(c['label'])}.csv"
        keep.add(fname)
        write_csv(DATA / fname, subset)
        courses.append({**c, "pct": round(100 * c["value"] / total, 1) if total else 0,
                        "csv": f"data/{fname}", "stats": stats(subset)})
    for old in DATA.glob("respuestas-*.csv"):   # cursos que ya no existen
        if old.name not in keep:
            old.unlink()

    tz = ZoneInfo(CONFIG.get("timezone", "America/Costa_Rica"))
    now = datetime.now(timezone.utc).astimezone(tz)
    summary = {
        "title": CONFIG["title"],
        "subtitle": CONFIG.get("subtitle", ""),
        "updated_at": now.isoformat(timespec="minutes"),
        "incompletas": incomplete,
        "courses": courses,
        "personal_data_public": publish_personal,
        **stats(complete),
    }
    (DATA / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(DATA / "respuestas.csv", complete)

    # --- página de contactos cifrada (solo si existe la contraseña) ---
    pw = os.environ.get("CONTACTOS_PASSWORD", "")
    if pw:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from build_contactos import build
        label = now.strftime("%d/%m/%Y %I:%M %p").lower()
        names = dict(ALL_COLUMNS)
        order = ["id", "A1_SQ1", "A1_SQ2", "A1_SQ3", "A13", "A10_SQ3", "A10_SQ1",
                 "A10_SQ2", "A6", "PROV", "A3_SQ2", "A3_SQ3", "A9", "SLA1", "A7",
                 "A8", "A14", "submitdate"]
        build(complete, [(c, names[c]) for c in order],
              label, ROOT / "contactos.html", pw, CONFIG["title"])
        print("Página de contactos cifrada: generada.")
    else:
        print("Sin CONTACTOS_PASSWORD: no se genera la página de contactos.")
    print(f"Listo: {total} matriculados, {incomplete} incompletas. "
          f"CSV con datos personales: {'SÍ' if publish_personal else 'no'}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
