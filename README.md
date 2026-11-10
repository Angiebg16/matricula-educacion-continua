# Página de matrícula – Educación Continua en Estadística

Página sencilla que muestra cuántas personas se han matriculado (por curso, por día, grado académico, horario y provincia) y permite descargar un CSV con las respuestas. Se actualiza sola una vez al día desde LimeSurvey.

## Cómo funciona

```
LimeSurvey ──(API, 1 vez al día)──> GitHub Actions ──> data/summary.json + data/respuestas.csv ──> index.html (GitHub Pages)
```

- `index.html`: la página que ve tu jefa.
- `scripts/fetch_data.py`: baja las respuestas y calcula los números.
- `.github/workflows/actualizar.yml`: la tarea automática (todos los días ~6:17 a. m. hora de Costa Rica).
- `config.json`: título, ID de la encuesta y la opción de datos personales.

## Puesta en marcha (una sola vez)

1. **Crear el repositorio.** En GitHub: *New repository*. Nombre sugerido: `matricula-educacion-continua`. Marcalo como **Public** (GitHub Pages gratis lo requiere). Subí todos los archivos de este paquete, incluida la carpeta oculta `.github`.
2. **Guardar las credenciales de LimeSurvey.** En el repo: *Settings → Secrets and variables → Actions → New repository secret*. Creá tres:
   - `LS_URL`: la dirección de tu LimeSurvey, por ejemplo `https://tu-servidor.ucr.ac.cr` (sin nada más).
   - `LS_USER`: tu usuario de LimeSurvey.
   - `LS_PASSWORD`: tu contraseña.

   Estos valores quedan cifrados: nadie los ve en el código ni en la página.
3. **Activar GitHub Pages.** *Settings → Pages → Build and deployment → Source: Deploy from a branch → Branch: `main` / carpeta `/ (root)` → Save*. En un par de minutos GitHub te muestra la dirección, algo como `https://tu-usuario.github.io/matricula-educacion-continua/`.
4. **Primera actualización.** Pestaña *Actions → Actualizar datos de matrícula → Run workflow*. Cuando termine (círculo verde), recargá la página: ya deben aparecer los datos.

Desde ahí se actualiza sola todos los días. Para actualizar en cualquier momento, repetí el paso 4.

## Si la API no funciona

La API de LimeSurvey (RemoteControl) tiene que estar habilitada en el servidor: *Configuración global → Interfaces → RPC interface → JSON-RPC*. Si no, pedíselo a quien administra LimeSurvey en la UCR.

Mientras tanto hay un plan B sin API:
1. En LimeSurvey: *Respuestas → Exportar → Exportar respuestas*. Formato CSV, encabezados "Código de pregunta", respuestas "Respuesta completa".
2. Guardá el archivo como `data/manual/respuestas.csv` y ejecutá `python scripts/fetch_data.py` en tu computadora (esa carpeta no se sube a GitHub por seguridad). Subí luego `data/summary.json` y `data/respuestas.csv`.

## Datos personales (importante)

Una página de GitHub Pages es **pública**: cualquiera con el enlace puede abrirla y descargar el CSV. Por eso, por defecto el CSV **no incluye** nombre, cédula, teléfonos, correo ni distrito (`"publish_personal_data": false` en `config.json`).

Si ponés `true`, el CSV público trae todo, incluida la cédula. No lo hagas sin que la jefatura y la unidad de protección de datos de la UCR lo hayan aprobado. Para quien necesite los datos completos, lo más seguro es exportarlos desde LimeSurvey con su usuario.

## Cursos nuevos

No hay que tocar nada. La tabla agrupa por la pregunta "Curso por matricular" (`A6`): cuando agreguen opciones nuevas en la encuesta, aparecerán solas en la tabla.

## Cambiar el título

Editá `config.json` (`title` y `subtitle`).
