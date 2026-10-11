# Plan de adecuación del flujo para el jurado

**Objetivo:** que la demostración descrita en la sección 17 del proyecto pueda ejecutarse de principio a fin, en un entorno local preparado, con tres cambios de rol, resultados deterministas y sin interrupciones para preparar datos durante la exposición.

**Criterio de presentación:** los datos están preparados para la feria, pero la interfaz, los nombres, las evidencias, las fuentes, los avisos, las oportunidades, los reportes y la bitácora no deben mostrar rótulos como “ficticio”, “ficticia”, “datos ficticios”, “sintético” ni similares. Se usarán nombres y descripciones naturales. Las instrucciones técnicas podrán describir el entorno local de demostración cuando sea necesario, sin introducir esas etiquetas en las pantallas.

## Diferencias que se deben resolver

1. La trayectoria está disponible, pero las cuentas de presentación se entregan sin contraseña y hay que prepararlas una por una.
2. Se puede presentar evidencia y aprobarla con el rol docente, pero el seed no prepara una evidencia con archivo lista para enseñar el cambio de estado.
3. La aprobación incrementa el SPD, pero el estado inicial de ninguna cuenta está diseñado para cruzar un umbral de nivel como resultado visible de esa aprobación.
4. La beca ya está publicada al preparar el seed; el guion pide enseñar su creación/publicación.
5. La oportunidad elegible ya tiene un caso precargado. El guion necesita que el resultado de elegibilidad use al estudiante que acaba de ganar puntos.
6. Hay transferencias previas, pero no están encadenadas al evento que se acaba de validar en la exposición.
7. La campaña de evaluación empieza sin votos y requiere cinco sesiones estudiantiles, cierre y publicación durante o antes del recorrido.
8. `seed_demo` es idempotente, pero no restablece los cambios de las pruebas anteriores. El estado de la feria no queda garantizado al repetir el recorrido.
9. Se muestran nombres y textos de origen como “Mateo Ficticio”, “Datos sintéticos” y “Actividad ficticia”, además de eventos técnicos `demo.*` en la bitácora.

## Entregas incrementales

### J01 — Guion único y recorrido encadenado — Implementado

Definir una historia con Valeria como estudiante protagonista, una docente revisora y una persona de coordinación. La actividad aprobada debe cambiar su nivel y habilitarla para la beca que se publica durante el recorrido.

Escenario de referencia:

- Valeria inicia con 90 puntos propios, promedio y notas verificadas, una matrícula activa y un proyecto validado.
- Presenta una constancia de curso certificado, cuya aprobación agrega 10 puntos y la lleva de Explorador (0–99) a Participante (100–249).
- La beca publicada por coordinación exige, entre sus condiciones, promedio mínimo, 100 puntos propios, proyecto validado y aprobación de MET201. Valeria reúne las condiciones después de la revisión docente.
- Valeria envía una transferencia limitada desde un mérito transferible ya aprobado. Coordinación la resuelve; la pantalla explica que los puntos recibidos no se suman a mérito propio ni a elegibilidad.
- La sección de evaluación muestra un agregado ya publicado con el mínimo de cinco respuestas alcanzado; no se navegan cinco cuentas durante la exposición.
- Coordinación termina en Gestión y análisis, mostrando indicadores y bitácora de las acciones ejecutadas.

**Aceptación:** una preparación limpia reproduce el punto de partida exacto; la aprobación produce +10 y el cruce de nivel; la evaluación de requisitos indica cada fuente y resultado; la transferencia queda limitada, revisada y auditada.

### J02 — Dataset de presentación coherente — Implementado

Actualizar `seed_demo` o crear una preparación específica de feria para que cree de forma idempotente instituciones/carrera, matrículas y roles necesarios, calificaciones, proyecto, reglamento, balance inicial calibrado, actividad pendiente de aprobación, origen transferible, oportunidad en borrador, campaña agregada y registros de reportes.

- Usar nombres naturales y consistentes para estudiantes, docente y coordinación; por ejemplo, Valeria Quispe, Mateo Rojas, Lucía Condori, Carlos Mamani, docente Patricia Choque y coordinación Sandra López.
- Mantener los datos consistentes entre trayectoria, archivo, origen del SPD, transferencias, elegibilidad, informes y auditoría.
- Evitar fuentes que afirmen una institución emisora o verificación oficial no realizada. La evidencia del guion se entrega como material de presentación y usa una descripción neutral de procedencia.
- Generar cinco respuestas estructuradas sin relación con identidades en `EvaluationSubmission` y publicar sus agregados mediante los mismos servicios de negocio de E09. No exponer votos individuales ni alterar la separación de privacidad.
- Evitar duplicar notas, actividades, puntos, notificaciones, auditorías o votos cuando la preparación se ejecuta nuevamente.

**Aceptación:** desde una base vacía, un solo comando deja listo el recorrido; una segunda ejecución no duplica registros ni altera el escenario; las invariantes de E06–E11 permanecen válidas.

**Verificación realizada:** prueba de integración que ejecuta el seed dos veces, comprueba el punto de partida y el adjunto, aprueba la evidencia por el rol docente, publica la oportunidad por coordinación, revisa los cuatro requisitos, procesa una transferencia limitada y verifica el agregado publicado con cinco respuestas anónimas. El recorrido queda ejecutado en la base temporal de pruebas; la base local de trabajo no se reinició.

### J03 — Reinicio y acceso local de feria

Preparar un mecanismo repetible de inicio que opere únicamente sobre una base local dedicada a la feria. Debe aplicar migraciones, cargar el escenario, preparar las cuentas y comprobar salud del backend/frontend.

- No guardar contraseñas de feria en el repositorio, `.env.example`, documentación pública, logs ni historial de auditoría.
- Permitir asignar la misma clave local temporal a las cuentas de presentación mediante un comando interactivo; las cuentas conservan permisos separados.
- Documentar las cuentas por rol y la secuencia de cambio de sesión. Incluir una lista de comprobación previa y un plan alternativo si falla PostgreSQL o la campaña.
- No ejecutar limpieza destructiva sobre la base normal del proyecto. El comando de reinicio debe comprobar que la conexión apunta a la base local de feria y detenerse ante otra base.

**Aceptación:** la preparación es segura e idempotente y no requiere crear cuentas, cargar archivos ni modificar configuración durante la presentación.

### J04 — Interfaz sin marcadores de datos preparados

Revisar tanto la UI común como E05–E11 y los valores del dataset que allí se muestran.

- Retirar del contenido visible palabras de marcador como “ficticio/ficticia”, “datos ficticios”, “sintético”, “de demostración” usadas como origen o nombre de persona, y nombres como “Mateo Ficticio”.
- Sustituirlas por nombres y copy naturales que describan la actividad y su fuente sin afirmar validaciones oficiales inexistentes.
- No presentar los eventos de carga inicial (`demo.*`, `demo_*_seeded`) como acciones de usuarios en la bitácora del recorrido. Las acciones hechas en vivo sí deben aparecer con actor, objeto y motivo.
- Mantener la documentación técnica fiel sobre el carácter de datos locales de presentación, sin trasladar avisos internos a las pantallas del jurado.

**Aceptación:** una búsqueda de cadenas en el contenido renderizado de las pantallas del recorrido no devuelve esos marcadores; los registros y sus fuentes siguen siendo comprensibles y auditables.

### J05 — Cierre funcional y ensayo de extremo a extremo

Crear pruebas de integración del guion desde el login de cada rol hasta el informe/bitácora final. Añadir pruebas de preparación limpia/repetida, y validar que la campaña publicada conserva privacidad.

Ensayar el recorrido a 360, 768 y 1366 px, con teclado y foco visible, comprobar cargas/errores/confirmaciones y medir duración total. Completar la matriz de permisos para estudiante, docente y coordinación: evidencia/archivo, aprobación, publicación, elegibilidad, transferencia, evaluación, CSV e informe.

**Aceptación:** todos los pasos de la sección 17 son reproducibles sin editar datos por consola; cada paso tiene verificación observable; el recorrido completo cabe en un guion de 8–10 minutos y existe una alternativa preparada para evaluación y conexión local.

## Correspondencia con la sección 17

| Paso del proyecto | Entrega que lo habilita | Resultado que se debe mostrar |
|---|---|---|
| 1. Inicio como estudiante | J02–J03 | Acceso de Valeria. |
| 2. Perfil y trayectoria actual | J02 | Matrícula, notas, proyecto, SPD y nivel inicial. |
| 3. Registrar curso/proyecto y evidencia | J01–J02 | Constancia adjunta y actividad pendiente. |
| 4. Validar desde rol docente | J01–J03 | Patricia aprueba la evidencia del grupo asignado. |
| 5. Puntos y nivel | J01–J02 | Saldo propio 90 → 100; Explorador → Participante. |
| 6. Publicar beca con requisitos | J01–J02 | Sandra publica la versión con criterios visibles. |
| 7. Identificar elegibilidad | J01–J02 | Valeria cumple con resultados y fuentes por requisito. |
| 8. Transferir puntos limitados | J01–J02 | Solicitud dentro del tope, resolución separada y mérito propio intacto. |
| 9. Evaluación y agregados | J02 | Agregado publicado con al menos cinco respuestas, sin votos individuales. |
| 10. Estadísticas y bitácora | J02, J05 | Informe de carrera y acciones del recorrido en el ámbito autorizado. |

## Orden recomendado de implementación

J01 y J02 se implementan en conjunto porque comparten los datos de escenario. Después se construye J03 para hacer el entorno reproducible, J04 para limpiar textos y nombres de presentación, y finalmente J05 para certificar el recorrido completo. Cada entrega conserva datos locales únicamente y respeta permisos, trazabilidad y privacidad ya definidos en E01–E11.
