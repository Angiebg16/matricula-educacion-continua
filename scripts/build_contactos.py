"""Genera contactos.html: una página CIFRADA con los datos de contacto.

La página que se publica solo contiene texto cifrado (AES-256-GCM, clave derivada
con PBKDF2-SHA256, 600 000 iteraciones). Los datos solo se ven si se escribe la
contraseña. En ningún momento se guardan los datos en claro en el repositorio.
"""
import base64
import csv
import html
import io
import json
import os
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

ITERATIONS = 600_000
MIN_PASSWORD = 12


def encrypt(plain: str, password: str) -> str:
    salt, iv = os.urandom(16), os.urandom(12)
    key = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt,
                     iterations=ITERATIONS).derive(password.encode("utf-8"))
    ct = AESGCM(key).encrypt(iv, plain.encode("utf-8"), None)
    return base64.b64encode(salt + iv + ct).decode("ascii")


def _inner_page(title, updated_label, columns, rows):
    head = "".join(f"<th>{html.escape(n)}</th>" for _, n in columns)
    body = "".join(
        "<tr>" + "".join(f"<td>{html.escape(r.get(c, ''))}</td>" for c, _ in columns) + "</tr>"
        for r in rows)
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow([n for _, n in columns])
    for r in rows:
        w.writerow([r.get(c, "") for c, _ in columns])
    csv_json = json.dumps(buf.getvalue(), ensure_ascii=False).replace("</", "<\\/")
    return f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>Contactos – {html.escape(title)}</title>
<style>
body{{margin:0;font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;color:#1b2733;background:#f5f7fa}}
.wrap{{max-width:1400px;margin:0 auto;padding:24px 20px 48px}}
header{{display:flex;justify-content:space-between;align-items:flex-start;gap:20px;flex-wrap:wrap;margin-bottom:18px}}
h1{{margin:0;font-size:1.9rem}} .sub{{color:#5d6b78}}
.btn{{background:#0b5394;color:#fff;border:0;font-weight:600;padding:10px 18px;border-radius:8px;cursor:pointer;font-size:1rem}}
.upd{{margin-top:8px;font-size:.88rem;color:#5d6b78;text-align:right}}
input[type=search]{{padding:9px 12px;border:1px solid #dde3ea;border-radius:8px;width:100%;max-width:360px;font-size:1rem;margin-bottom:14px}}
.scroll{{overflow:auto;background:#fff;border:1px solid #dde3ea;border-radius:12px}}
table{{border-collapse:collapse;width:100%;font-size:.9rem}}
th,td{{text-align:left;padding:9px 12px;border-bottom:1px solid #dde3ea;white-space:nowrap}}
th{{background:#f0f4f8;position:sticky;top:0}}
.warn{{font-size:.85rem;color:#8a5a00;margin-top:12px}}
</style></head><body><div class="wrap">
<header><div><h1>Contactos de matrícula</h1><div class="sub">{html.escape(title)} · <span id="n">{len(rows)}</span> personas</div></div>
<div><button class="btn" id="dl">Descargar CSV completo</button><div class="upd">Última actualización: <strong>{html.escape(updated_label)}</strong></div></div></header>
<input type="search" id="q" placeholder="Buscar por nombre, correo, teléfono...">
<div class="scroll"><table><thead><tr>{head}</tr></thead><tbody id="tb">{body}</tbody></table></div>
<p class="warn">Contiene datos personales. No compartas la contraseña ni el contenido fuera del equipo.</p>
</div>
<script>
const CSV = {csv_json};
document.getElementById('dl').onclick = () => {{
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob(['\\ufeff' + CSV], {{type:'text/csv;charset=utf-8'}}));
  a.download = 'respuestas_completas.csv'; a.click();
}};
document.getElementById('q').oninput = e => {{
  const t = e.target.value.toLowerCase(); let n = 0;
  document.querySelectorAll('#tb tr').forEach(tr => {{
    const ok = tr.textContent.toLowerCase().includes(t); tr.style.display = ok ? '' : 'none'; if(ok) n++;
  }});
  document.getElementById('n').textContent = n;
}};
</script></body></html>"""


SHELL = """<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>Acceso restringido</title>
<style>
body{margin:0;min-height:100vh;display:grid;place-items:center;font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;background:#f5f7fa;color:#1b2733}
form{background:#fff;border:1px solid #dde3ea;border-radius:12px;padding:28px;width:min(92vw,380px)}
h1{margin:0 0 6px;font-size:1.3rem} p{margin:0 0 16px;color:#5d6b78;font-size:.92rem}
input{width:100%;padding:10px 12px;border:1px solid #dde3ea;border-radius:8px;font-size:1rem;margin-bottom:12px}
button{width:100%;background:#0b5394;color:#fff;border:0;font-weight:600;padding:11px;border-radius:8px;font-size:1rem;cursor:pointer}
#err{color:#b00020;font-size:.9rem;min-height:1.2em;margin-top:10px}
</style></head><body>
<form id="f"><h1>Acceso restringido</h1><p>Escribí la contraseña para ver los contactos.</p>
<input type="password" id="pw" placeholder="Contraseña" autocomplete="current-password" autofocus>
<button type="submit">Ver contactos</button><div id="err"></div></form>
<script>
const ITER = __ITER__;
const BLOB = "__BLOB__";
async function descifrar(b64, pw) {
  const raw = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
  const salt = raw.slice(0,16), iv = raw.slice(16,28), ct = raw.slice(28);
  const base = await crypto.subtle.importKey('raw', new TextEncoder().encode(pw), 'PBKDF2', false, ['deriveKey']);
  const key = await crypto.subtle.deriveKey({name:'PBKDF2', salt, iterations: ITER, hash:'SHA-256'}, base,
                                            {name:'AES-GCM', length:256}, false, ['decrypt']);
  const plain = await crypto.subtle.decrypt({name:'AES-GCM', iv}, key, ct);
  return new TextDecoder().decode(plain);
}
if (typeof document !== 'undefined') {
  document.getElementById('f').addEventListener('submit', async e => {
    e.preventDefault();
    const err = document.getElementById('err'); err.textContent = 'Verificando...';
    try {
      const html = await descifrar(BLOB, document.getElementById('pw').value);
      document.open(); document.write(html); document.close();
    } catch (_) { err.textContent = 'Contraseña incorrecta.'; }
  });
}
</script></body></html>
"""


def build(rows, columns, updated_label, out_path, password, title):
    if len(password) < MIN_PASSWORD:
        raise ValueError(f"La contraseña de la página de contactos debe tener al menos "
                         f"{MIN_PASSWORD} caracteres.")
    inner = _inner_page(title, updated_label, columns, rows)
    page = SHELL.replace("__ITER__", str(ITERATIONS)).replace("__BLOB__", encrypt(inner, password))
    Path(out_path).write_text(page, encoding="utf-8")
