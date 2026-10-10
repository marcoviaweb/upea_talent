# E09 — Evaluaciones académicas anónimas

E09 permite recoger retroalimentación estructurada de estudiantes sobre docentes y auxiliares asignados a sus grupos. Se limita a respuestas cerradas; no hay comentarios libres, sanción automática, ranking disciplinario ni consulta de votos individuales.

## Flujo implementado

1. Coordinación o administración crea un borrador ligado a una asignatura/grupo, periodo y carrera de su ámbito. El sistema toma las asignaciones docentes/auxiliares vigentes; los borradores se pueden reemplazar por una versión nueva antes de recibir respuestas.
2. Al abrirla, el padrón de matrículas activas del grupo queda congelado. Solo esas personas pueden responder; la persona evaluada no puede evaluarse a sí misma.
3. Cada respondiente puede contestar una vez por persona evaluada/asignación. La encuesta tiene siete criterios estructurados con escala de cinco opciones: claridad, organización, cobertura, retroalimentación, puntualidad, atención e igualdad de trato. No se almacena texto libre.
4. El contenido del voto está en `EvaluationSubmission`, que no tiene FK a usuario, matrícula ni habilitación. La tabla separada `EvaluationEligibility` conserva únicamente quién está habilitado y si ya completó su respuesta. El servicio bloquea la habilitación durante el envío para impedir doble voto. La respuesta no se registra como evento con actor en auditoría, porque esa relación revelaría quién respondió.
5. Coordinación cierra la campaña y solicita la publicación agregada. Para cada asignación se calculan media y distribución 1–5. Si hay menos del mínimo, el resultado queda suprimido, sin métricas ni conteo exacto. El mínimo nunca puede ser menor a cinco.
6. El personal evaluado solo consulta los agregados que superaron el umbral y que correspondan a una asignación propia. Coordinación accede a agregados dentro de su carrera. No existe endpoint de respuestas individuales.

El cuestionario v1, la escala y el mínimo inicial cinco son una línea base ficticia/propuesta; se deben validar con la institución antes de evaluar a personal real. Los resultados son retroalimentación descriptiva, no prueba causal ni calificación de desempeño.

## Demostración local

`seed_demo` genera una campaña abierta de ejemplo para INF101, grupo A, en Ingeniería de Sistemas, con cinco matrículas ficticias habilitadas. La campaña no contiene votos precargados. Así se puede completar el recorrido con cuentas separadas y llegar al umbral mínimo sin reutilizar identidades.

1. Ejecuta migraciones y `manage.py seed_demo`.
2. Asigna contraseñas locales a `demo.estudiante01` hasta `demo.estudiante05`, `demo.docente01` y `demo.coordinador01` con `manage.py changepassword <usuario>`.
3. Abre `/trayectoria/evaluaciones/`. Entra con cada uno de los cinco estudiantes y responde la campaña INF101. El historial de participación solo lo ve cada persona.
4. Entra como `demo.coordinador01`, cierra la campaña y publica los resultados agregados. Si se recibieron cinco votos, se muestran medias y distribución por criterio; si hay menos, no se muestra el conteo ni métricas.
5. Entra como `demo.docente01` y consulta únicamente los agregados publicados para sus asignaciones. No puede ver quién participó ni el contenido de ningún voto individual.

Una vez que una campaña se abre no se crea otra para el mismo grupo/periodo, aunque todavía no haya respuestas. Así la gestión no puede inferir participación consultando si existe algún voto. Solo los borradores pueden cancelarse o reemplazarse por una versión nueva. Las respuestas, agregados y versiones publicadas son inmutables.

## API y almacenamiento

- `GET/POST /api/v1/evaluations/`: encuestas propias habilitadas, agregados propios publicados y campañas/ofertas de gestión limitadas al ámbito.
- `POST /api/v1/evaluations/respond/`: voto estructurado; no acepta identidad ni matrícula del respondiente.
- `POST /api/v1/evaluations/campaigns/<id>/open/`: congela padrón y abre el borrador.
- `POST /api/v1/evaluations/campaigns/<id>/close/`: cierra respuestas.
- `POST /api/v1/evaluations/campaigns/<id>/publish-results/`: calcula agregados y suprime objetivos bajo el mínimo.
- `POST /api/v1/evaluations/campaigns/<id>/cancel/`: cancelación motivada, solo antes de recibir votos.

Modelos: `EvaluationCampaign`, `EvaluationTarget`, `EvaluationEligibility`, `EvaluationSubmission` y `EvaluationAggregate`. Los votos no están registrados en Django Admin. Migración: `apps/evaluations/migrations/0001_initial.py`.

## Verificación

```powershell
.\.venv\Scripts\python.exe manage.py test apps.evaluations
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
npm run typecheck
npm run build
```

Las pruebas cubren habilitación y ámbito, envío único, valores de escala, ausencia de identidad en votos/auditoría, aislamiento de agregados, supresión con cuatro respuestas, publicación con cinco, versionado antes de respuestas y acceso docente posterior a publicación.
