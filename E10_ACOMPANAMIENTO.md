# E10 — Acompañamiento

**Estado:** implementado · **Dependencias:** E06, E07 · **Alcance de esta entrega:** reglas explicables, indicadores descriptivos, expedientes restringidos y seguimiento humano.

## Alcance funcional

- Calcula promedio normalizado a escala 100, cantidad de notas verificadas y actividades aprobadas por matrícula/periodo.
- La regla inicial identifica un descenso de promedio comparando a cada estudiante consigo mismo en dos periodos cerrados consecutivos. Ambos deben tener matrícula concluida y al menos el número configurado de notas verificadas. Las notas se normalizan usando su escala histórica.
- La regla por carrera tiene vigencia, parámetros, versión y publicación inmutable. Publicar una modificación conserva las versiones anteriores.
- Cada alerta conserva una foto de los datos fuente, periodos, cantidad de verificaciones, diferencia, umbral y versión de regla. El análisis es idempotente.
- Coordinación puede abrir un caso y asignarlo a una persona coordinadora autorizada de la misma carrera, registrar asesorías, tutorías, cursos o refuerzos, añadir interacciones y cerrar el caso con resultado.
- El estudiante consulta sus propias señales y expediente, y puede enviar una respuesta a su equipo. Coordinación ve la información del ámbito autorizado; el responsable asignado puede trabajar el expediente delegado.
- Los eventos sensibles se guardan en auditoría. Las alertas no alteran calificaciones oficiales, puntos SPD ni elegibilidad.

Las actividades aprobadas se muestran como indicador descriptivo. Su ausencia nunca dispara una alerta. Tampoco se evalúan periodos abiertos, notas sin verificar, matrículas incompletas ni periodos no consecutivos.

## Operación local y prueba

1. Ejecutar `python manage.py migrate` y `python manage.py seed_demo`.
2. Asignar una contraseña local al usuario `demo.coordinador01` con `python manage.py changepassword demo.coordinador01`.
3. Entrar a **Acompañamiento** como coordinación. Se carga una regla ficticia versionada y un caso de demostración para Mateo Ficticio, generado con datos verificados de II/2025 y I/2026.
4. Abrir el caso, revisar la explicación, registrar interacción/fecha acordada y cerrarlo con un resultado de al menos 10 caracteres.
5. Entrar como `demo.estudiante02` para revisar su expediente y responder al equipo.
6. Como coordinación, crear la siguiente versión de regla y analizar periodos cerrados. Una segunda ejecución sin cambios no duplica alertas.

Todas las credenciales de demo se asignan localmente; el comando de semilla no establece contraseñas utilizables.

## Endpoints

- `GET /api/v1/support/`: reglas según ámbito, alertas autorizadas, indicadores propios.
- `POST /api/v1/support/`: publica una nueva versión de regla en la carrera autorizada.
- `POST /api/v1/support/scan/`: evalúa reglas activas de una carrera o todas las carreras administradas.
- `POST /api/v1/support/cases/`: abre un caso y lo asigna a coordinación de la misma carrera (por defecto, quien lo abre).
- `POST /api/v1/support/cases/<uuid>/actions/`: registra plan, interacción o respuesta del estudiante.
- `POST /api/v1/support/cases/<uuid>/close/`: cierra con resultado obligatorio.
- `POST /api/v1/support/cases/<uuid>/discard/`: descarta con motivo obligatorio y auditado.

## Verificación

Las pruebas E10 comprueban promedios normalizados, comparación entre periodos cerrados consecutivos, idempotencia, exclusión de notas no verificadas, aislamiento del expediente y denegación de acceso ajeno.
