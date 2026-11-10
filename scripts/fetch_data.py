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
    ("A3_SQ1", "Provincia"),
    ("A3_SQ2", "Cantón"),
    ("A3_SQ3", "Distrito"),
    ("A9", "Lugar de trabajo"),
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


def clean_province(v):
    v = re.sub(r"^provincia de\s+", "", v.strip(), flags=re.I)
    return v.title() if v.islower() else v


def counts(values):
    c = Counter(v for v in values if v)
    return [{"label": k, "value": n} for k, n in c.most_common()]


def main():
    DATA.mkdir(exist_ok=True)
    use_api = all(os.environ.get(k) for k in ("LS_URL", "LS_USER", "LS_PASSWORD"))
    rows = fetch_api() if use_api else fetch_manual()
    print(f"Modo: {'API' if use_api else 'manual'} · filas recibidas: {len(rows)}")

    complete = [r for r in rows if r.get("submitdate")]
    incomplete = len(rows) - len(complete)
    complete.sort(key=lambda r: r.get("submitdate", ""))

    # --- resumen para la página ---
    by_day = Counter(r["submitdate"][:10] for r in complete)
    days = sorted(by_day)
    acc, daily = 0, []
    for d in days:
        acc += by_day[d]
        daily.append({"date": d, "nuevos": by_day[d], "acumulado": acc})

    total = len(complete)
    courses = counts(r.get("A6", "") for r in complete)
    for c in courses:
        c["pct"] = round(100 * c["value"] / total, 1) if total else 0

    tz = ZoneInfo(CONFIG.get("timezone", "America/Costa_Rica"))
    now = datetime.now(timezone.utc).astimezone(tz)
    summary = {
        "title": CONFIG["title"],
        "subtitle": CONFIG.get("subtitle", ""),
        "updated_at": now.isoformat(timespec="minutes"),
        "total": total,
        "incompletas": incomplete,
        "courses": courses,
        "grado": counts(r.get("A7", "") for r in complete),
        "horario": counts(r.get("A14", "") for r in complete),
        "provincia": counts(clean_province(r.get("A3_SQ1", "")) for r in complete),
        "daily": daily,
        "personal_data_public": bool(CONFIG.get("publish_personal_data")),
    }
    (DATA / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    # --- CSV descargable ---
    publish_personal = bool(CONFIG.get("publish_personal_data"))
    cols = [(c, n) for c, n in ALL_COLUMNS
            if (publish_personal and c not in NO_CEDULA) or c not in PERSONAL]
    with open(DATA / "respuestas.csv", "w", newline="", encoding="utf-8-sig") as f:
        # ';' para que Excel en español lo abra en columnas
        w = csv.writer(f, delimiter=";")
        w.writerow([n for _, n in cols])
        for r in complete:
            w.writerow([r.get(c, "") for c, _ in cols])
    # --- página de contactos cifrada (solo si existe la contraseña) ---
    pw = os.environ.get("CONTACTOS_PASSWORD", "")
    if pw:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from build_contactos import build
        label = now.strftime("%d/%m/%Y %I:%M %p").lower()
        names = dict(ALL_COLUMNS)
        order = ["id", "A1_SQ1", "A1_SQ2", "A1_SQ3", "A13", "A10_SQ3", "A10_SQ1",
                 "A10_SQ2", "A6", "A3_SQ1", "A3_SQ2", "A3_SQ3", "A9", "A7", "A8",
                 "A14", "submitdate"]
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
