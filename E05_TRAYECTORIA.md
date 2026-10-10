# E05 — Trayectoria académica y de desarrollo

**Estado:** implementado con frontend React/TypeScript/Vite y API Django REST Framework.  
**Base funcional:** [E01 § 4, RF-03/HU-03.1](E01_ESPECIFICACION_FUNCIONAL.md); [modelo y navegación E02](E02_DISENO_INTEGRAL.md); identidad/autorización [E04](E04_IDENTIDAD_ACADEMIA.md).

## Entregado

- Portal autenticado con entrada, cierre de sesión, resumen personal, historial de matrículas y grupos docentes asignados.
- SPA React con diseño adaptable de portal académico; Tailwind se compila localmente, con componentes, iconos Lucide y CSS del producto servidos sin CDN.
- API JSON del mismo origen: sesión Django, protección CSRF, autorización del servidor y acceso PostgreSQL solo desde Django. La API reutiliza servicios de dominio para validaciones, transacciones y auditoría.
- Perfil académico por matrícula con notas verificadas en modo de solo lectura, fuente, escala, umbral de aprobación, responsable y fecha de verificación. No muestra notas sin verificar ni inventa un promedio vacío. La media visible es simple e informativa; no decide elegibilidad.
- Las correcciones de notas crean una revisión enlazada, conservan la nota anterior y sus valores de escala/corte y auditan la corrección. Solo la vigente verificada cuenta en el resumen.
- Proyectos y habilidades pueden guardarse como borrador y enviarse a revisión. El estudiante puede editar sus registros propios declarados o que requieren cambios mientras su matrícula siga activa. No puede validar su propia declaración.
- Docentes/revisores pueden consultar perfiles únicamente desde listas de grupo a las que estén asignados y resolver declaraciones con validación o comentario obligatorio al pedir cambios. Se registran actor, fecha y eventos en auditoría.
- Componentes web compartidos con HTML semántico, foco visible, enlace para saltar al contenido, etiquetas de formularios, anuncios de estado, mensajes vacíos, tablas adaptables y CSS local sin fuentes/CDN externos.
- `seed_demo`, tras crear un superusuario técnico, permite crear de forma idempotente tres estudiantes, un docente, dos periodos de trayectoria, matrículas y grupos ficticios, notas históricas sintéticas, un proyecto en revisión y una habilidad declarada. Las cuentas sintéticas no tienen contraseña conocida ni utilizable hasta que el operador les asigne una localmente.

## Probar en el portal

Consulta el [README](README.md) para instalar Python, Node.js, PostgreSQL y arrancar ambos servidores en desarrollo. En un entorno local ya migrado:

```powershell
.\.venv\Scripts\python.exe manage.py createsuperuser
.\.venv\Scripts\python.exe manage.py seed_demo
.\.venv\Scripts\python.exe manage.py changepassword demo.estudiante02
.\.venv\Scripts\python.exe manage.py changepassword demo.docente01
```

En la primera ventana de PowerShell, inicia Django: `.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000`.
En una segunda ventana, inicia Vite: `npm run dev`.

Abre `http://127.0.0.1:5173/acceso/` e inicia sesión primero como `demo.estudiante02`. Revisa las matrículas, abre la trayectoria actual para ver el proyecto en revisión y la habilidad declarada; abre I/2026 para revisar notas históricas verificadas. Cierra sesión y entra como `demo.docente01`: consulta “Mis grupos”, abre un grupo y la trayectoria de `Mateo Ficticio`; valida el proyecto o solicita cambios dejando un comentario. El estudiante vuelve a ver quién revisó el dato, la fecha o el comentario.

Las rutas JSON usadas por la SPA están bajo `/api/v1/`: inicio/cierre de sesión, resumen, grupos, perfiles de matrícula, declaraciones y revisión. La sesión se conserva en una cookie HttpOnly; las operaciones que cambian datos requieren token CSRF. PostgreSQL no es accesible desde el navegador.

El usuario/contraseña del superusuario técnico sirven para `/admin/`; no habilitan acceso a trayectorias a través de los servicios de dominio. Para cuentas sintéticas, `changepassword` pide la clave nueva en el terminal sin registrarla en Git.

## Pruebas y controles

```powershell
.\.venv\Scripts\python.exe manage.py test apps.profiles apps.accounts apps.core --noinput
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe manage.py check
npm run typecheck
npm run build
```

La suite cubre inicio de sesión y CSRF, privacidad entre estudiantes, borrador/envío, bloqueo de edición al cerrar matrícula, revisión docente asignada, rechazo sin motivo, impedimento de autovalidación, ocultamiento de notas no verificadas y corrección enlazada. Se verificó además la interfaz contra [Web Interface Guidelines de Vercel](https://github.com/vercel-labs/web-interface-guidelines/blob/main/command.md) y los criterios locales de UI/UX Pro Max.

## Límites de la entrega

La gestión administrativa de altas/matrículas/notas y la consola completa de coordinación aún no tienen formularios propios. El acceso docente está limitado a grupos y su tarea académica; coordinación recibe paneles agregados en entregas posteriores. Puntos, niveles, evidencias, logros, oportunidades y participación se incorporan en sus módulos dependientes. Los registros cargados aquí son ficticios y no representan información oficial de UPEA.
