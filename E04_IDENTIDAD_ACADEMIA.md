# E04 — Identidad, academia y acceso por ámbito

**Estado:** implementado y verificado en entorno local.  
**Base:** E01 § 2, RF-01/RF-02 y reglas de autorización; E02 §§ 5, 7, 8 y 11.

## Alcance implementado

- Las cuentas Django mantienen credenciales y estado de acceso. El rol no está embebido en la cuenta: `RoleAssignment` permite varios roles y ámbitos con vigencia, otorgante y motivo.
- El ámbito es exactamente una institución, una carrera o un grupo (`CourseOffering`). Las combinaciones ambiguas y fechas invertidas se rechazan en base de datos; la validación de modelo limita roles a ámbitos compatibles.
- Academia incluye institución, carreras, periodos con escala de notas, asignaturas, grupos/ofertas, perfil estudiantil, matrículas, inscripción a grupo y asignación de docentes/auxiliares.
- `visible_course_enrollments(user)` filtra en servidor. Estudiantes ven su propia matrícula; docentes/revisores requieren rol del grupo y asignación docente vigente; coordinación/administración de carrera queda limitada a sus carreras. El rol de administrador institucional no expone listas de estudiantes.
- Concesión y revocación de roles se hacen mediante servicios transaccionales; requieren actor autorizado, motivo y evento de auditoría. No permiten autoasignación. Las cuentas desactivadas pierden acceso sin borrar historial.
- Auditoría básica guarda contexto seguro y es inmutable desde el modelo de aplicación. No debe incluir contraseñas, tokens, contenido de respuestas de evaluación ni datos secretos.
- El panel técnico `/admin/` está restringido a superusuarios. Solo administra catálogos académicos; matrículas/perfiles no se exponen allí. Ser superusuario técnico no concede acceso mediante los servicios de consulta académica.
- `seed_demo` carga de forma idempotente una institución/carrera ficticias, cuatro periodos, cinco asignaturas y grupos de Ingeniería de Sistemas. Tras crear un superusuario, también carga cuentas sintéticas y asignaciones sin contraseñas predefinidas.

## Preparar y probar

Desde PowerShell, en la carpeta del proyecto, con `.env`, dependencias y Docker Desktop configurados según el [README](README.md):

```powershell
docker compose up -d db
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py createsuperuser
.\.venv\Scripts\python.exe manage.py seed_demo
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

Abre `http://127.0.0.1:8000/admin/` para administrar catálogos como superusuario técnico. El portal operativo de trayectoria está descrito en [E05](E05_TRAYECTORIA.md); la gestión diaria de cuentas y matrículas y las pantallas completas de coordinación siguen pendientes.

Pruebas automatizadas:

```powershell
.\.venv\Scripts\python.exe manage.py test
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
```

Las pruebas E04 verifican el inicio de sesión/estado de cuenta, aislamiento entre carreras, visibilidad de lista de grupo docente, ausencia de acceso de listas para administración institucional, prohibición de autoasignación y auditoría append-only.

## API de dominio para las siguientes entregas

- Crear privilegio: `apps.accounts.services.grant_role(...)`.
- Revocar privilegio: `apps.accounts.services.revoke_role(...)`.
- Resolver matrículas visibles: `apps.accounts.permissions.visible_course_enrollments(user)`.
- Comprobar acceso puntual: `apps.accounts.permissions.can_access_course_enrollment(user, id)`.

Las futuras vistas deben derivar la lista desde estos servicios y aplicar autorización puntual en cada acción/descarga. Un UUID difícil de adivinar y un selector de carrera no son controles de acceso.

## Refinamiento al diseño E02

Se materializó `CourseEnrollment` (matrícula en grupo) además de la matrícula carrera/periodo de E02. Esta relación es necesaria para obtener una lista de estudiantes asignados a cada grupo y verificar acceso docente granular. Complementa, no reemplaza, la matrícula académica.
