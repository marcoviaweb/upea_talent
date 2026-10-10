# E06 — Evidencias y Sistema de Puntos de Desarrollo

E06 incorpora en React + Django REST Framework evidencias privadas, revisión docente por asignación vigente, reglamento SPD por carrera/versionado, libro append-only de puntos y niveles derivados. Los datos iniciales son ficticios; las reglas del documento de proyecto son referencia de demostración, no una aprobación institucional.

## Flujo implementado

1. El estudiante con matrícula activa presenta una actividad y un PDF/JPG/PNG de hasta 10 MB. La categoría debe estar publicada para su carrera y el archivo queda almacenado en `private_uploads/evidence`, fuera de las rutas públicas estáticas.
2. El revisor con asignación de rol vigente y matrícula coincidente consulta evidencia, descarga archivos autorizados y aprueba, observa o rechaza con motivo cuando corresponde. El estudiante conserva el historial y puede reenviar una observación como una versión nueva.
3. Aprobar genera una sola concesión de puntos ligada a evidencia, categoría y versión del reglamento. No hay API para editar o borrar movimientos. Revocar por coordinación/admin de carrera/institucional crea una reversión exacta y auditada.
4. El saldo se obtiene sumando movimientos por matrícula; los niveles usan las franjas de origen. Las transferencias se mostrarán aparte en E08 y no se incluyen aquí.

La misma matrícula, fecha y nombre de actividad no puede generar dos casos activos, aunque se seleccione otra categoría. Esta es una protección determinista inicial; antes de producción se deberá establecer con la instancia académica cómo resolver actividades equivalentes cuyo nombre o fecha difiera.

## Puesta en marcha y recorrido

Desde PowerShell en la raíz:

```powershell
docker compose up -d db
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py createsuperuser
.\.venv\Scripts\python.exe manage.py seed_demo
.\.venv\Scripts\python.exe manage.py changepassword demo.estudiante02
.\.venv\Scripts\python.exe manage.py changepassword demo.docente01
npm run dev
```

Entra en `http://127.0.0.1:5173/acceso/`; la navegación **Evidencias y SPD** tiene el registro de estudiante/docente y el libro de puntos. Abre dos sesiones: estudiante para presentar y responder observación, docente para resolver desde un grupo asignado. El reglamento se consulta en **Mi SPD**. Cada carrera mantiene su propia versión y catálogo; el seed de Ingeniería de Sistemas crea las 11 categorías y los valores de referencia.

## Administración y operación

Coordinación y administración de carrera/institución pueden registrar un mérito ya verificado desde la interfaz; la fuente, responsable, auditoría y movimiento SPD quedan vinculados. Solo pueden elegir matrículas de sus ámbitos. Estos roles también pueden revocar una aprobación con motivo, y la interfaz solicita confirmación antes de registrar la reversión.

Los reglamentos y categorías se administran en `/admin/` con el modelo de datos de Django; una versión publicada y sus categorías no se pueden editar. Para cambiar reglas, crea un reglamento borrador en la carrera, agrega/ajusta sus categorías y guárdalo; en una edición posterior publica la versión para congelar su contenido y vigencia. Solo una cuenta técnica autorizada tiene acceso al admin de Django en esta entrega.

La detección de archivos comprueba extensión, firma básica, tamaño y descarga con autorización, `Content-Disposition` de adjunto, `nosniff` y política CSP restrictiva. No equivale a antivirus; una instalación institucional deberá agregar análisis antimalware antes de publicación. No se sirven archivos desde `MEDIA_URL`.

## Verificación

```powershell
.\.venv\Scripts\python.exe manage.py test apps.activities
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
npm run typecheck
npm run build
```

Las pruebas cubren aprobación/idempotencia, reversión, observación y reenvío versionado, rol de revisor, propiedad de matrícula, duplicación del mismo hecho e inmutabilidad publicada.
