# E07 — Oportunidades, elegibilidad y postulaciones

E07 implementa el flujo de convocatorias para una o varias carreras en Django + PostgreSQL y el portal React. Los criterios se representan con campos y operadores permitidos; la elegibilidad orienta al estudiante, mientras que la adjudicación permanece bajo decisión humana.

## Alcance entregado

- Convocatorias de beca, pasantía, curso, concurso, proyecto e intercambio; descripción, beneficios, canal de postulación, carrera(s), apertura, cierre y cupo.
- Versiones consecutivas de los requisitos. Publicar una versión nueva la establece como vigente; las anteriores y sus postulaciones se conservan, pero ya no admiten solicitudes.
- Requisitos tipados: carrera(s) habilitada(s), periodo académico exacto, semestre mínimo, promedio verificado, puntos SPD propios, proyecto validado, actividad verificada, curso aprobado y habilidad validada. Las versiones publicadas y sus requisitos/carreras son inmutables. La validación comprueba existencia de los cursos y periodos exigidos en todas las carreras elegidas.
- Evaluación individual con cumple / no cumple / datos insuficientes, valor, origen, fecha, versión y huella de entradas. La media simple usa únicamente notas verificadas de la matrícula elegida y normaliza las escalas a 100 antes de comparar; cursos y demás evidencias corresponden al periodo de esa matrícula. Los movimientos sin actividad fuente, como potenciales créditos transferidos futuros, no suman a puntos de mérito propios.
- Postulación del titular de una matrícula activa, durante las fechas de la versión vigente y solo si todos los requisitos tienen evidencia suficiente y cumplen. La solicitud preserva su versión y evaluación inicial.
- Revisión por responsable o coordinación/admin autorizado en la carrera; se muestra la foto inicial junto al recálculo de resolución. Las decisiones exigen motivo y registran actor, hora y estado anterior. El sistema limita selecciones al cupo y vuelve a comprobar elegibilidad antes de seleccionar. Si cambia una evidencia tras una resolución, la interfaz advierte que el resultado quedó desactualizado y permite reabrir la revisión con motivo, conservando el historial. La decisión final sigue en manos institucionales.
- Retiro de postulación antes de resolución y antes del cierre. Un reintento posterior crea otro registro y conserva el retiro previo.
- Coordinación puede cerrar admisiones o cancelar la convocatoria con motivo; el cierre bloquea nuevas postulaciones y pasa a resuelta cuando ya no quedan solicitudes pendientes.
- Cuando se publica otra versión, la solicitud conserva su evaluación y versión inicial; el portal marca la nueva publicación al estudiante afectado. La versión anterior deja de aceptar postulaciones.
- Permisos filtrados en servidor por matrícula, titular, responsable y ámbito de carrera. La API no expone solicitudes a otro estudiante ni a coordinación de otra carrera.
- Bitácora para publicación, postulación, retiro y resolución.

## Beca ficticia de Ingeniería de Sistemas

`seed_demo` crea la oportunidad **Beca de Investigación** y los datos sintéticos necesarios para recorrerla:

- `demo.estudiante01` es un caso elegible, con promedio de periodo 87,60, 100 puntos propios SPD, proyecto validado y MET201 aprobado con 89.
- `demo.estudiante02` y `demo.estudiante03` muestran perfiles con requisitos faltantes o insuficientes.
- `demo.coordinador01` tiene el rol de coordinación limitado a SIS y puede publicar convocatorias y revisar postulaciones de esa carrera.
- Las contraseñas no se precargan: asígnalas localmente con `manage.py changepassword demo.estudiante01` y `manage.py changepassword demo.coordinador01`.

Los datos son ficticios. El promedio es simple y no ponderado, calculado sobre las notas verificadas del periodo de la matrícula seleccionada. No constituye una política académica oficial.

## Probar en el portal

1. Arranca PostgreSQL y aplica `manage.py migrate`.
2. Ejecuta `manage.py seed_demo` después de crear el superusuario.
3. Asigna una contraseña de prueba a `demo.estudiante01` y a `demo.coordinador01`.
4. Inicia Django y Vite como se describe en [README.md](README.md), y entra a `/trayectoria/oportunidades/`.
5. Con `demo.estudiante01`, revisa los cuatro criterios, postula y observa la solicitud en “Mis postulaciones”.
6. Con `demo.coordinador01`, abre “Gestionar”, inspecciona las fuentes iniciales y actuales, y resuelve con motivo. El formulario de versión crea una nueva publicación sin cambiar las solicitudes previas.

## Modelos y API

Los modelos principales son `Opportunity`, `OpportunityVersion`, `OpportunityRequirement`, `EligibilitySnapshot`, `Application` y `ApplicationDecision`. Las migraciones se encuentran en `apps/opportunities/migrations/`.

La API local se encuentra bajo `/api/v1/opportunities/`, `/api/v1/opportunity-versions/` y `/api/v1/applications/`. Todas las rutas requieren sesión y CSRF en operaciones que escriben.

## Verificación

```powershell
.\.venv\Scripts\python.exe manage.py test apps.opportunities
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
npm run typecheck
npm run build
```

Las pruebas cubren elegibilidad verificable e insuficiente, matrícula/actividad, postulación y foto inicial inmutable, publicación inicial, nuevas versiones y avisos, privacidad entre carreras, límites de cupo, cierre/resolución, cierre de ciclo al cambiar datos, reapertura motivada, e inmutabilidad de versiones.

