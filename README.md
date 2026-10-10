# UPEA Talent+

Guía para instalar y probar la aplicación local. **El portal de E05 usa React + TypeScript + Vite; Django REST Framework mantiene la lógica, la sesión y el acceso a PostgreSQL.** El prototipo visual de E02 sigue siendo una maqueta aparte y no guarda datos.

## Qué necesitas

- Windows 10/11 de 64 bits y PowerShell.
- Python 3.12. Puedes revisar la [descarga oficial de Python para Windows](https://www.python.org/downloads/windows/). Durante la instalación, habilita la opción para agregar Python al `PATH`.
- Node.js 22.12 o posterior y npm para compilar y desarrollar el frontend React/Vite. Descarga la versión LTS desde [Node.js](https://nodejs.org/).
- Docker Desktop con el motor Linux iniciado. No necesitas instalar PostgreSQL aparte: Docker ejecuta una imagen gratuita de PostgreSQL 17. Consulta la [instalación oficial de Docker Desktop](https://docs.docker.com/desktop/setup/install/windows-install/). En este equipo, comprueba también que `docker info` muestra datos del servidor, no solo la versión del cliente.
- Acceso a Internet durante la instalación inicial para descargar las dependencias Python y la imagen de PostgreSQL. Después, la aplicación corre localmente.

No hace falta activar el entorno virtual ni cambiar la política de ejecución de PowerShell: los comandos llaman directamente al Python local del proyecto.

## Preparación inicial

Abre PowerShell en la carpeta del proyecto, donde están `manage.py` y `compose.yaml`. Si no sabes dónde estás, entra primero a la carpeta del proyecto; por ejemplo:

```powershell
Set-Location E:\proyectos\upea_talent
```

### 1. Crear la configuración local

La plantilla de configuración está en [.env.example](.env.example). Copia esa plantilla una sola vez a `.env` en la raíz del proyecto:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
notepad .env
```

El archivo `.env` contiene estos valores; el ejemplo es apropiado solo para una base local de pruebas:

```dotenv
DJANGO_SECRET_KEY=dev-only-replace-before-any-shared-deployment
DJANGO_DEBUG=1
DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost

POSTGRES_DB=upea_talent
POSTGRES_USER=upea_talent
POSTGRES_PASSWORD=local-dev-change-this
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=55432
```

En esta computadora ya generé un `.env` ignorado por Git con una clave Django y una contraseña de base aleatorias; si ese archivo ya existe, **consérvalo y no lo reemplaces**. Las variables de conexión deben coincidir con el contenedor. `55432` es el puerto de Windows; dentro del contenedor PostgreSQL escucha en `5432`. Se eligió `55432` porque Windows rechazó el puerto local `5432` durante la puesta en marcha. Si el puerto alternativo también está ocupado, cambia solo `POSTGRES_PORT` a otro puerto libre, como `55433`, antes de iniciar la base.

No subas `.env` ni compartas sus claves. Git excluye el archivo automáticamente. Si ya inicializaste PostgreSQL, cambiar `POSTGRES_PASSWORD` en `.env` no cambia la contraseña guardada dentro de la base.

### 2. Instalar las dependencias

La primera vez crea el entorno virtual e instala las versiones fijadas en [requirements-lock.txt](requirements-lock.txt):

```powershell
python --version
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
```

Debe aparecer Python 3.12 al consultar la versión. Si ya existe `.venv`, omite el comando que lo crea; si PowerShell dice que `python` no se reconoce, instala Python y vuelve a abrir PowerShell. Instala también las dependencias exactas del frontend con el archivo de lock:

```powershell
node --version
npm --version
npm ci
```

Las dependencias de React, TypeScript, Vite y Tailwind quedan dentro de `node_modules`; no se envían a servicios externos durante el uso.

### 3. Iniciar PostgreSQL y preparar la base

Abre Docker Desktop y espera a que indique que el motor está iniciado. Luego, desde la raíz del proyecto:

```powershell
docker info
docker compose up -d db
docker compose ps
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py migrate
```

`docker compose ps` debe mostrar el servicio `db` como `running` o `healthy`. La primera vez Docker descarga PostgreSQL 17 y puede tardar unos minutos. La base se conserva en el volumen `postgres_data` entre reinicios.

## Abrir y probar la aplicación

Primero crea una cuenta técnica para el panel. Django te pedirá nombre de usuario, correo y contraseña; la contraseña se escribe sin mostrar caracteres:

```powershell
.\.venv\Scripts\python.exe manage.py createsuperuser
```

Después de crearla, vuelve a ejecutar `manage.py seed_demo` para generar las cuentas sintéticas y sus trayectorias. Para probar el portal, asigna una clave local a `demo.estudiante02` y `demo.docente01` con `manage.py changepassword <usuario>`.

Inicia el frontend y el backend en **dos ventanas de PowerShell**. En la primera ejecuta Django:

```powershell
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

En la segunda ejecuta Vite para servir React y actualizar la interfaz al guardar cambios:

```powershell
npm run dev
```

Abre `http://127.0.0.1:5173/acceso/`. Vite sirve la interfaz y reenvía `/api/` a Django; las cookies de sesión y el token CSRF mantienen protegidas las operaciones. El panel de administración y los endpoints de salud permanecen en el puerto `8000`. Si Vite no está iniciado, la interfaz de desarrollo no cargará. Para verificar el paquete que se usará en una instalación compilada, genera los estáticos con:

```powershell
npm run typecheck
npm run build
```

La compilación queda en `apps/profiles/static/profiles/frontend/` y Django referencia sus archivos sin depender de Node durante la ejecución compilada.

En el navegador abre:

- `http://127.0.0.1:8000/admin/` — inicia sesión con la cuenta técnica que acabas de crear. El panel restringido permite configurar catálogos; matrículas y perfiles privados no se exponen allí.
- `http://127.0.0.1:5173/acceso/` — portal React en desarrollo; en compilación se monta bajo las rutas de Django.
- `http://127.0.0.1:8000/health/live` — confirma que Django responde.
- `http://127.0.0.1:8000/health/ready` — confirma que Django puede consultar PostgreSQL.
- `prototipo/e02/index.html` — maqueta visual local de E02, con datos ficticios. Sus botones simulan interacciones, no guardan nada ni aplican permisos reales.

Para verificar la base desde PowerShell, deja el servidor corriendo y ejecuta en una segunda ventana:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health/live
Invoke-RestMethod http://127.0.0.1:8000/health/ready
```

La segunda respuesta debe indicar `"database": "connected"`. Para detener Django, vuelve a su ventana y pulsa `Ctrl+C`. Para detener PostgreSQL sin borrar los datos:

```powershell
docker compose down
```

No uses `docker compose down -v` salvo que quieras eliminar permanentemente la base de prueba y todos sus datos.

## Pruebas automatizadas

Con PostgreSQL iniciado, ejecuta desde la raíz del proyecto:

```powershell
.\.venv\Scripts\python.exe manage.py test
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
```

Las pruebas comprueban salud y conexión, aislamiento E04, login/CSRF de API, privacidad por matrícula, declaraciones y revisiones auditadas, notas verificadas y correcciones enlazadas. `npm run typecheck` y `npm run build` comprueban el frontend. Consulta [E05_TRAYECTORIA.md](E05_TRAYECTORIA.md) para recorrer el portal.

El comando `seed_demo` carga datos ficticios de Ingeniería de Sistemas. Es idempotente, no establece contraseñas y, si ya existe un superusuario, añade tres estudiantes, un docente y la trayectoria para probar E05. Detalles: [E04_IDENTIDAD_ACADEMIA.md](E04_IDENTIDAD_ACADEMIA.md) y [E05_TRAYECTORIA.md](E05_TRAYECTORIA.md).

## Problemas habituales

- **`docker info` muestra error de conexión o permiso:** inicia Docker Desktop, espera al motor Linux y verifica otra vez. No basta con instalar Docker CLI.
- **No puede enlazar el puerto 55432:** detén otro proceso que lo use o cambia `POSTGRES_PORT` por `55433` en `.env`; luego ejecuta `docker compose up -d --force-recreate db`.
- **Django informa que PostgreSQL no acepta la conexión:** revisa `docker compose ps` y que `POSTGRES_HOST=127.0.0.1`, `POSTGRES_PORT=55432`, base, usuario y contraseña correspondan al `.env` usado al crear la base.
- **El panel pide usuario y contraseña:** créalos con `manage.py createsuperuser`; no hay credenciales de demostración precargadas.
- **No puedes entrar a `/acceso/`:** no hay contraseñas predeterminadas. Ejecuta `seed_demo` después de crear el superusuario y establece una clave local con `manage.py changepassword demo.estudiante02` o `demo.docente01`.

## Estructura técnica

```text
config/                         Ajustes y puntos de entrada Django
apps/core/                      Endpoints de salud y pruebas
apps/accounts/                  Usuario, asignaciones de rol y permisos por ámbito
apps/academics/                 Institución, carreras, periodos, grupos, matrículas y notas
apps/profiles/                  Dominio de trayectoria, API y portal Django/React
apps/audit/                     Bitácora básica append-only
design-system/upea-talent/      Tokens visuales y especificación de pantalla
apps/<dominio>/                 Paquetes para los límites definidos en E02
compose.yaml                    PostgreSQL 17 en loopback
.env.example                    Plantilla de configuración local
requirements.txt                Dependencias directas
package.json                    Herramientas y bibliotecas React/TypeScript/Vite
frontend/src/                   Interfaz React del portal
vite.config.ts                  Desarrollo local y compilación de recursos frontend
requirements-lock.txt           Versiones exactas para instalación repetible
prototipo/e02/                  Maqueta visual sin conexión al backend
```

La aplicación usa `America/La_Paz`, Django 5.2 LTS, Python 3.12 y PostgreSQL 17. Django 5.2 es LTS y admite Python 3.12 ([notas oficiales de Django](https://docs.djangoproject.com/en/5.2/releases/5.2/)). Esta instalación es solo de desarrollo local: no la expongas en una red institucional ni la uses con expedientes reales.
