# E01 — Especificación funcional de UPEA Talent+

**Versión:** 1.0 · **Fecha:** 9 de octubre de 2026  
**Estado:** línea base de requisitos para las siguientes entregas.  
**Proyecto:** producto completo local descrito en [PLAN_DESARROLLO_UPEA_TALENT.md](PLAN_DESARROLLO_UPEA_TALENT.md).  
**Origen funcional:** [UPEA_TALENT_Proyecto_Feria_Cientifica.md](UPEA_TALENT_Proyecto_Feria_Cientifica.md).  
**Convenciones:** `RF` = requisito funcional; `RNF` = requisito no funcional; `HU` = historia de usuario; `RB` = regla de negocio; `DEC` = decisión de implementación.

## 1. Propósito y alcance de E01

Este documento convierte la propuesta de UPEA Talent+ en requisitos que guiarán el diseño, la implementación y la aceptación del producto. El sistema gestionará la trayectoria académica y de desarrollo, reconocimientos SPD, evidencias, oportunidades, evaluaciones, acompañamiento y actividades administrativas para más de una carrera.

La primera carga de demostración utilizará datos ficticios de Ingeniería de Sistemas. Los datos ficticios no son registros oficiales ni aprueban las reglas de negocio en nombre de la universidad. En tablas de este documento, **Propuesto** identifica un parámetro o procedimiento necesario para la implementación que el documento original no fija. Se usará como comportamiento de referencia para construir y demostrar el sistema, y quedará configurable/versionado. Antes de operar con estudiantes o decisiones reales, el área institucional competente deberá aprobarlo.

### Dentro de la versión 1.0

1. Usuarios, roles, carreras, periodos, asignaciones, grupos y matrículas.
2. Perfil de trayectoria, historial validado, habilidades, proyectos, cursos y logros.
3. Actividades, archivos de evidencia, revisión y SPD con reglamento versionado.
4. Oportunidades, comparación explicable de requisitos, postulación y decisión humana.
5. Transferencia limitada y auditable de puntos por colaboración.
6. Evaluación estructurada de docentes y auxiliares con agregación protegida.
7. Indicadores preventivos y seguimiento de actividades de apoyo.
8. Paneles, informes, notificaciones internas, auditoría, instalación y respaldo local.

### Fuera de esta línea base

Integraciones con sistemas académicos reales, notificaciones por correo/WhatsApp, aplicación móvil nativa, IA para decisiones, firma digital y servicios de terceros. En esta versión, los datos se ingresan manualmente y la elegibilidad/recomendación se calcula con reglas visibles y deterministas.

## 2. Actores y vocabulario

| Actor | Descripción y ámbito |
|---|---|
| Estudiante | Consulta su propia trayectoria y realiza acciones estudiantiles sobre su matrícula activa. |
| Docente | Registra actividades y revisa evidencias de grupos/carreras expresamente asignados. |
| Auxiliar | Puede ser evaluado por los estudiantes a quienes fue asignado. Solo revisa evidencias si además recibe autorización explícita de revisor. |
| Coordinación | Administra oportunidades, reportes agregados y acompañamiento de las carreras asignadas. Puede resolver decisiones que le sean delegadas. |
| Administrador | Gestiona cuentas, estructura, parámetros y acceso administrativo dentro de su ámbito. Los cambios sensibles requieren motivo y bitácora. |
| Revisor de evidencia | Permiso asignado a una persona habilitada, normalmente docente o coordinación; solo actúa sobre actividad y ámbito asignados. |
| Responsable de oportunidad | Persona autorizada por coordinación para publicar y evaluar postulaciones de esa oportunidad. |
| Administrador institucional | Administrador con ámbito institucional. No obtiene acceso a respuestas individuales de evaluación. |

Un **ámbito** es institución, carrera, grupo, campaña u oportunidad asignada. El usuario puede tener más de un rol y ámbito. El permiso efectivo es la intersección del rol, acción, recurso, asignación vigente y estado del recurso. Un filtro visual nunca concede autorización.

**Matrícula**: inscripción de un estudiante en una carrera durante un periodo. **Mérito propio**: puntos obtenidos por actividades del mismo estudiante validadas bajo regla vigente. **Transferencia recibida**: reconocimiento de colaboración enviado por otro estudiante; se muestra y audita aparte del mérito propio. **Evidencia**: dato/archivo sujeto a validación, asociado a una actividad. **Requisito**: condición tipada y versionada que se puede explicar a una persona usuaria. **Agregado de evaluación**: estadística de un conjunto de respuestas que pasó las salvaguardas de publicación.

## 3. Convenciones de aceptación

- Una operación fallida no debe dejar cambios parciales en saldo, decisión, evidencia, postulación o auditoría.
- Ante duda de autorización, el sistema deniega el acceso y evita revelar si el registro ajeno existe.
- Mensajes de validación deben indicar qué falta y cómo corregirlo, sin filtrar datos privados.
- Toda fecha de negocio se muestra en hora de Bolivia (`America/La_Paz`). Los registros técnicos conservan tiempo UTC.
- Los identificadores siguientes se mantienen entre diseño, pantallas, cambios de datos y verificación. Una modificación futura debe anotar el requisito afectado.

## 4. Requisitos funcionales e historias

### RF-01 — Identidad, sesión y cuentas

**RF-01.1** El sistema permitirá iniciar y cerrar sesión con cuenta habilitada. **RF-01.2** Administración creará, actualizará, desactivará y reactivará cuentas, asignando uno o varios roles y ámbitos autorizados. **RF-01.3** El usuario podrá cambiar la contraseña y recuperar el acceso mediante token temporal de un solo uso. **RF-01.4** Las cuentas de demostración estarán documentadas como ficticias y podrán recrearse de forma segura.

**HU-01.1 — Acceder según rol.** Como usuario habilitado, quiero iniciar sesión para ver la portada y las acciones que corresponden a mis roles y ámbitos.

- Dado usuario y contraseña válidos y cuenta habilitada, al autenticar, se crea sesión y se muestra su inicio autorizado.
- Dada una contraseña incorrecta o cuenta deshabilitada, el acceso se rechaza sin confirmar a un atacante si la cuenta existe.
- Al cerrar sesión, el identificador de sesión deja de funcionar.
- Después de expirar o invalidarse la sesión, páginas privadas y descargas requieren acceso de nuevo.

**HU-01.2 — Recuperar acceso.** Como usuario que no puede ingresar, quiero establecer una contraseña nueva sin conocer la anterior.

- La respuesta inicial es igual tanto si el correo existe como si no.
- Un token aleatorio vence en un plazo configurable, se consume una sola vez y no se registra en logs.
- Tras un cambio válido, el token no se reutiliza y las sesiones previas quedan invalidadas.
- La recuperación se muestra como flujo local; no promete envío de correo en la versión 1.0. La administración podrá emitir una recuperación siguiendo un procedimiento auditado.

**HU-01.3 — Administrar cuenta.** Como administrador del ámbito, quiero gestionar cuentas y asignaciones para habilitar acceso correcto.

- Solo administrador autorizado puede crear usuarios y conceder roles.
- El sistema registra actor, ámbito, cambios y motivo para conceder privilegios administrativos.
- Desactivar una cuenta revoca su próxima solicitud y conserva las relaciones históricas.
- Un usuario no puede ampliar su propio rol ni su ámbito.

### RF-02 — Organización académica y mult carrera

**RF-02.1** Administración institucional gestionará carreras; administración delegada podrá actuar dentro de su carrera. **RF-02.2** Administración gestionará periodos, asignaturas, grupos, asignaciones docente/auxiliar y matrículas. **RF-02.3** El sistema conservará el ámbito académico en perfiles, actividades, puntos, oportunidades, evaluaciones e informes. **RF-02.4** El sistema permitirá configurar escala de notas y criterio de aprobación por carrera/periodo antes de calcular promedios o puntos.

**HU-02.1 — Configurar carrera y periodo.** Como administrador autorizado, quiero configurar carreras y periodos para operar con varios programas académicos.

- Una segunda carrera puede registrarse desde interfaz/datos administrativos sin cambios de código.
- Periodos y escalas poseen vigencia y no reescriben el historial.
- No se crea una asignación que cruce grupo, carrera y periodo incompatibles.

**HU-02.2 — Matricular estudiante.** Como administrador académico, quiero vincular a un estudiante con una carrera y periodo para delimitar su trayectoria.

- Una matrícula guarda estudiante, carrera, periodo, estado y fecha de vigencia.
- El mismo estudiante puede tener más de una matrícula histórica, sin mezclar sus saldos o notas.
- La matrícula inactiva conserva la consulta histórica, pero impide nuevas postulaciones y acciones dependientes de matrícula activa, excepto permiso explícito de cierre.

### RF-03 — Perfil y trayectoria estudiantil

**RF-03.1** Estudiante verá un resumen de trayectoria por matrícula: promedio/periodos disponibles, materias aprobadas, puntos, nivel, habilidades, proyectos, cursos, participación, logros, evidencias y oportunidades. **RF-03.2** Cada atributo indicará si fue declarado, está pendiente o fue validado y quién/cuándo lo validó. **RF-03.3** Docente autorizado consultará el progreso de sus grupos asignados. **RF-03.4** Coordinación consultará vistas agregadas de su carrera. El sistema no permitirá cambiar notas oficiales desde el perfil.

**HU-03.1 — Consultar mi perfil.** Como estudiante, quiero comprender mi trayectoria y el origen de cada resultado.

- Se muestra contexto actual (carrera/periodo) y se puede consultar historial por matrícula.
- Saldo de puntos se enlaza con su historial y evidencia; transferencias recibidas se muestran separadas.
- Las habilidades/proyectos declarados se distinguen claramente de los validados.
- Si los datos académicos no han sido ingresados o validados, se explica «sin datos verificados»; no se inventa promedio ni elegibilidad.
- Se puede solicitar corrección por medio del proceso de evidencia o consulta administrativa; no se modifica una calificación directamente.

### RF-04 — Actividades, evidencias y validación

**RF-04.1** Estudiante enviará una actividad con categoría habilitada, descripción, fecha/contexto y evidencia. **RF-04.2** Docente/revisor autorizado revisará, aprobará, observará para corrección o rechazará motivadamente. **RF-04.3** Se permitirá reenviar una evidencia observada y consultar historial de revisiones. **RF-04.4** Actividades académicas verificadas por administración podrán registrarse por una persona autorizada, dejando fuente y actor. **RF-04.5** La validación no concede puntos si no existe regla activa que puntúe esa categoría.

**HU-04.1 — Presentar evidencia.** Como estudiante, quiero demostrar un logro o actividad para que se valide y aparezca en mi trayectoria.

- El formulario pide datos requeridos por categoría y ofrece criterios visibles.
- Solo admite tipos de archivo permitidos por el despliegue, inicialmente PDF/JPG/PNG, con límite inicial propuesto de 10 MB por archivo.
- Tras enviar, la evidencia pasa a estado «en revisión» y el estudiante recibe aviso interno.
- El estudiante no puede modificar el archivo mientras está en revisión; puede responder a una observación con nueva versión vinculada a la anterior.
- No se puede enviar para una matrícula ajena ni convertir la evidencia en nota.

**HU-04.2 — Resolver revisión.** Como revisor autorizado, quiero decidir sobre evidencias asignadas y documentar mi decisión.

- Solo el revisor asignado y con ámbito compatible abre o resuelve el caso.
- Aprobar exige categoría, criterio satisfecho y responsable; rechazar exige motivo; observar indica información faltante.
- Una actividad repetida vinculada al mismo hecho no produce una segunda concesión.
- Toda transición se audita y avisa al estudiante.
- Una actividad aprobada puede ser revocada solo mediante procedimiento administrativo motivado; la evidencia original y la resolución previa permanecen consultables por autorizados.

### RF-05 — SPD, reglas y niveles

**RF-05.1** Administración autorizada creará y publicará reglamentos versionados con categorías, criterios, puntos, transferibilidad, vigencia y revisores permitidos. **RF-05.2** El sistema incluirá los valores iniciales del § 5; una regla no aplicable estará inactiva, no borrada. **RF-05.3** Estudiante consultará cada movimiento, saldo propio, transferencias aparte, nivel y motivo. **RF-05.4** El saldo se reconstruirá a partir de movimientos inmutables con actor, fecha, origen y regla. **RF-05.5** Las modificaciones serán ajustes compensatorios auditados. **RF-05.6** Los niveles se calcularán desde mérito propio según las franjas originales.

**HU-05.1 — Consultar puntos.** Como estudiante, quiero saber por qué recibí o perdí puntos.

- Cada operación presenta categoría, valor, fecha, regla/vigencia, origen, estado y responsable autorizado.
- El resumen diferencia mérito propio, puntos enviados, puntos recibidos y saldo disponible para transferencia.
- Una regla posterior no cambia movimientos históricos ni borra el motivo originalmente aplicado.
- Una penalización no se aplica si falta la regla publicada o la evidencia/motivo exigidos.

**HU-05.2 — Mantener reglamento.** Como administrador autorizado, quiero cambiar reglas con vigencia controlada.

- Solo un reglamento aprobado/configurado puede publicarse; usuario, fecha y versión quedan en bitácora.
- No se modifica retroactivamente una regla publicada. La revisión crea versión con nueva vigencia.
- Una excepción histórica requiere autorización y ajuste explícito, con impacto sobre elegibilidad señalado.
- La interfaz muestra al estudiante el reglamento vigente de su carrera.

### RF-06 — Oportunidades

**RF-06.1** Coordinación/responsable publicará becas, pasantías, cursos, concursos, proyectos e intercambios. **RF-06.2** Cada oportunidad contendrá descripción, beneficios, carrera(s), fechas, cupos, condiciones tipadas, versión, responsable y estado. **RF-06.3** Las condiciones publicadas se congelan para las postulaciones existentes; una corrección crea versión notificada. **RF-06.4** El sistema generará lista elegible explicable y no reemplazará decisión humana institucional.

**HU-06.1 — Publicar oportunidad.** Como responsable, quiero publicar condiciones precisas antes de postular.

- Solo persona autorizada para ámbito y oportunidad puede publicar.
- Requisitos no editables como texto de código: cada condición usa tipo, comparador y valor permitido.
- No se publica con fecha de cierre anterior a apertura, cupo no positivo o requisito inválido.
- Estudiante ve condiciones, criterio de elegibilidad, fechas y canal de postulación antes de enviar.
- Cambio posterior crea una versión nueva; las postulaciones afectadas se conservan y reciben aviso interno.

### RF-07 — Elegibilidad y postulaciones

**RF-07.1** El motor comparará datos validados del estudiante con requisitos de oportunidad. **RF-07.2** Cada requisito devolverá «cumple», «no cumple» o «datos insuficientes», con valor, fuente, versión de criterio y fecha. **RF-07.3** Estudiante podrá postular dentro del plazo y ver su estado. **RF-07.4** Responsable autorizado podrá revisar, comparar, seleccionar/no seleccionar dentro del cupo y motivar la resolución. **RF-07.5** El resultado de elegibilidad no garantiza adjudicación. **RF-07.6** No se podrá usar puntos transferidos como promedio, nota ni mérito para requisitos académicos.

**HU-07.1 — Comprobar oportunidad.** Como estudiante, quiero saber qué condiciones cumplo y qué información falta antes de postular.

- La Beca de Investigación de ejemplo aplica promedio mínimo 70, 100 puntos de trayectoria, participación en un proyecto y curso de investigación aprobado.
- El motor muestra los cuatro resultados individualmente y enlaza su origen validado.
- Si falta una nota verificada, declara datos insuficientes en vez de calcular elegibilidad por defecto.
- La solicitud congela versión de requisitos y foto de los valores usados.
- Coordinación conserva autoridad sobre la decisión y registra motivo; el resultado automatizado permanece en el expediente.

**HU-07.2 — Resolver postulaciones.** Como responsable, quiero resolver una convocatoria con reglas visibles y trazabilidad.

- Solo solicitudes de la oportunidad asignada son visibles.
- El resultado ordenado aplica condiciones publicadas; si una oportunidad requiere mérito comparativo adicional, esa regla debe quedar definida/publicada antes de abrir la convocatoria.
- No se supera cupo; cada resolución guarda actor, fecha, motivo y estado anterior.
- Una corrección de perfil que altere elegibilidad queda señalada para revisión, sin borrar la decisión inicial.

### RF-08 — Evaluación académica de docentes y auxiliares

**RF-08.1** Coordinación publicará campañas versionadas para docente/auxiliar y asignatura/grupo/periodo. **RF-08.2** El sistema habilitará solo estudiantes vinculados al grupo y periodo. **RF-08.3** Cada estudiante habilitado enviará una respuesta por persona evaluada, asignación y campaña. **RF-08.4** El cuestionario cubrirá claridad de enseñanza, organización, cumplimiento del contenido, retroalimentación, puntualidad, atención a consultas e igualdad de trato percibida. **RF-08.5** Se usarán escalas estructuradas; la primera versión no tendrá comentarios de texto libre. **RF-08.6** El sistema presentará indicadores agregados y publicará solo si supera el mínimo configurable. **RF-08.7** No generará automáticamente una acusación ni ranking punitivo. Cualquier revisión será institucional, contextual y auditada.

**HU-08.1 — Responder encuesta.** Como estudiante habilitado, quiero valorar una experiencia académica mediante criterios respetuosos.

- Solo se puede responder mientras la campaña está abierta y a personal asignado.
- Se limita a una respuesta por combinación estudiante, personal, asignación y campaña; el reintento no duplica el voto.
- La interfaz describe la escala y recoge únicamente respuestas estructuradas.
- Una respuesta enviada no puede modificarse por el sujeto evaluado ni por el estudiante; corrección/retiro requiere procedimiento explícito auditado antes del cierre.
- El sujeto evaluado no ve participación identificable ni respuestas individuales.

**HU-08.2 — Publicar resultados.** Como coordinación, quiero usar resultados agregados para la mejora académica.

- No se muestra resultado cuando el conjunto tiene menos de 5 respuestas; el umbral inicial 5 es **propuesto y configurable**, se revisará por riesgo de identificación antes del uso real.
- Los reportes muestran número de respuestas, periodo, escala y metodología; suprimen o combinan cortes pequeños.
- No hay texto ofensivo publicable, inferencia automática de favoritismo ni puntuación de disciplina.
- El acceso de revisión institucional no expone respuestas enlazadas a identidades estudiantiles.

### RF-09 — Acompañamiento

**RF-09.1** El sistema calculará indicadores académicos y de participación por periodo. **RF-09.2** Las alertas compararán al estudiante consigo mismo en periodos comparables y mostrarán el dato/regla que las originó. **RF-09.3** Coordinación asignará tutoría, curso, asesoría o refuerzo; registrará responsable, fecha, interacción y resultado. **RF-09.4** No habrá penalización por una alerta; no se expondrán listas de riesgo a otros estudiantes.

**HU-09.1 — Atender una alerta.** Como coordinación autorizada, quiero identificar y seguir una necesidad de apoyo.

- Cada regla de alerta está activa, versionada, explicable y delimitada a carrera/periodo.
- Periodos incompletos, falta de nota o inactividad de datos no se interpretan por sí solos como bajo desempeño.
- El expediente de apoyo solo es visible al estudiante y equipo autorizado.
- Se registra sugerencia, aceptación/derivación según proceso local y seguimiento hasta cerrar o descartar con motivo.
- La alerta no cambia puntos, nota, elegibilidad ni posición en una clasificación.

### RF-10 — Transferencias

**RF-10.1** El estudiante solicitará transferencia por una colaboración con motivo y actividad de referencia. **RF-10.2** Reglas definidas por carrera limitarán categorías, monto, acumulado mensual y beneficiarios. **RF-10.3** Un revisor distinto de emisor y receptor aprobará o rechazará. **RF-10.4** El sistema detectará solicitudes repetidas y superación de límites y las marcará para revisión. **RF-10.5** La operación genera débito y crédito pareados, sin cambiar el total global. **RF-10.6** Puntos recibidos no se retransfieren ni cuentan para niveles o requisitos de mérito propio bajo la política inicial.

**HU-10.1 — Reconocer colaboración.** Como estudiante, quiero proponer un reconocimiento por contribución comprobable.

- La solicitud requiere receptor de la misma carrera bajo configuración inicial, motivo y referencia a actividad/proyecto.
- Se rechaza auto-transferencia, operación nula/negativa/fraccionaria, falta de saldo transferible, repetición del mismo reconocimiento o exceder límite.
- Límites iniciales propuestos: hasta 10 puntos por solicitud y 20 puntos enviados por cuenta y mes calendario Bolivia; solo colaboración/mentoría configuradas. Estos valores son provisionales, no una regla aprobada por UPEA.
- El emisor, receptor y revisor reciben notificación de la resolución permitida por sus roles.
- Al aprobar, débito y crédito aparecen simultáneamente con mismo identificador de operación; no se alteran notas, mérito propio, niveles ni requisitos oficiales.
- Las señales de patrón sospechoso crean caso restringido de revisión; nunca sancionan automáticamente.

### RF-11 — Administración y auditoría

**RF-11.1** Administración gestionará cuentas, carreras, parámetros, reglas, oportunidades asignadas y catálogos. **RF-11.2** Cada operación sensible registrará actor, rol/ámbito, acción, objeto, fecha, resultado y motivo. **RF-11.3** La bitácora será de solo lectura para usuarios finales y consultable por permiso. **RF-11.4** Coordinación consultará indicadores únicamente dentro de su ámbito. **RF-11.5** La actividad rutinaria de consulta de respuestas individuales de evaluación no existirá.

**HU-11.1 — Revisar bitácora.** Como auditor/administrador autorizado, quiero reconstruir decisiones y correcciones.

- Buscar/filtrar no modifica eventos.
- No se almacenan contraseñas, tokens, datos íntegros de archivos ni respuestas individuales de evaluación en eventos.
- Ajustes, cambios de rol, resolución de evidencia, publicación de regla, elegibilidad, transferencia y exportación quedan trazados.
- Usuario sin permiso no puede ver la bitácora ni averiguar detalles mediante la URL directa.

### RF-12 — Analítica e informes

**RF-12.1** Paneles mostrarán trayectoria, participación, estados, oportunidades y actividades de la carrera/periodo autorizado. **RF-12.2** Informes incluirán visualización y tabla accesible equivalente. **RF-12.3** Administradores/coordinación exportarán CSV o vista imprimible dentro de su ámbito. **RF-12.4** Los gráficos no darán acceso a expedientes privados ni representarán asociaciones como causales.

**HU-12.1 — Consultar indicadores.** Como coordinación, quiero conocer el estado de mi carrera y detectar procesos pendientes.

- Filtros aplican en servidor y se comprueban con permiso.
- Cada gráfico tiene etiquetas, fecha de extracción, fuente, periodo, conteos y tabla alternativa.
- Denominadores y criterios de cálculo están descritos.
- CSV e impresión contienen los mismos filtros/permisos y solo columnas autorizadas.

### RF-13 — Notificaciones internas

**RF-13.1** El sistema avisará de envío/revisión de evidencias, postulaciones, transferencias, oportunidades y tareas de apoyo. **RF-13.2** La bandeja permitirá leído/no leído. **RF-13.3** Un aviso enlaza a la acción solo si el usuario aún tiene permiso. **RF-13.4** La notificación no llevará evidencia privada embebida.

**HU-13.1 — Seguir mis trámites.** Como usuario, quiero enterarme de una acción que requiere mi atención.

- El evento se crea solo después de confirmar la transacción de negocio.
- Abrir el aviso verifica autorización vigente; perder permiso elimina el detalle aunque el aviso siga visible.
- Marcar leído no cambia estado de evidencia, oportunidad o puntos.

### RF-14 — Instalación y datos ficticios

**RF-14.1** Se podrá instalar/iniciar localmente con dependencias gratuitas siguiendo manual. **RF-14.2** Dataset ficticio de Ingeniería de Sistemas se cargará de modo repetible en entorno de demostración y estará separado de operación. **RF-14.3** Se podrá hacer copia y restauración coherente de base y archivos. **RF-14.4** Funciones operativas no dependerán de Internet una vez instaladas.

**HU-14.1 — Preparar demostración.** Como responsable de la presentación, quiero recrear el escenario limpio y repetible.

- La carga solo corre con marca/confirmación del entorno de demo y no puede apuntar accidentalmente a datos de uso real.
- Toda persona, correo, calificación y evidencia es sintética y claramente identificada.
- La secuencia beca, curso/puntos, transferencia, evaluación y acompañamiento se puede completar con esas cuentas.
- Los recursos web son locales; una vez instaladas dependencias, los recorridos declarados no necesitan acceso a CDN/internet.
- Copia/restauración comprueba datos, archivos, movimientos y auditoría y se puede repetir en entorno vacío.

## 5. Reglas de negocio (RB)

La fuente de cada regla se indica entre corchetes: **Origen** = documento de proyecto; **Propuesta** = detalle no fijado allí, configurado para la línea base; **Pendiente** = requiere validación institucional antes de uso real.

### RB-01 — Catálogo del Sistema de Puntos de Desarrollo

| Código/categoría | Valor base | Fuente |
|---|---:|---|
| Aprobar una materia | +10 | Origen |
| Mejorar rendimiento respecto al periodo anterior | +15 | Origen |
| Curso certificado | +10 | Origen |
| Seminario o conferencia | +5 | Origen |
| Proyecto académico | +20 | Origen |
| Proyecto destacado | +30 | Origen |
| Participación en investigación | +25 | Origen |
| Participación en concurso | +15 | Origen |
| Ganador de concurso | +40 | Origen |
| Colaboración validada | +5 | Origen |
| Mentoría a otro estudiante | +10 | Origen |

Un reglamento publicado muestra categoría, criterio de validación, puntos, transferibilidad y vigencia. No borra versiones previas.

### RB-02 — Niveles de trayectoria

| Nivel | Mérito propio acumulado |
|---|---:|
| Explorador | 0–99 |
| Participante | 100–249 |
| Desarrollador | 250–499 |
| Líder | 500–749 |
| Talento destacado | 750 o más |

Los cortes son del documento original. La definición de «puntos válidos/acumulados» para el cálculo excluye transferencias recibidas bajo DEC-06. No existen niveles negativos.

### RB-03 — Concesión, historial y corrección

1. Cada categoría requiere regla vigente y evidencia/criterio satisfecho (Origen).
2. La validación la registra actor autorizado distinto del estudiante, y su decisión indica fecha y motivo (desarrollo operativo de Origen).
3. Nota oficial vive como dato académico con fuente/permisos propios; un punto nunca la modifica (Origen).
4. Duplicado del mismo hecho no concede dos veces; proyecto destacado sustituye valor de proyecto académico y ganador sustituye participación en mismo concurso (Propuesta).
5. Un cambio/reversión crea movimiento compensatorio vinculado, conserva regla y motivo inicial y avisa a afectados (Propuesta que implementa auditoría/historial del Origen).
6. Penalización solo después de definir y publicar la causa y registrar evidencia (Origen); catálogo inicial vacío (Propuesta).

### RB-04 — Mejora de rendimiento

Valor base +15 (Origen). Método de comparación, política de materias incompletas y escala de notas no definidos por la fuente. Para el prototipo: comparar promedio verificado del estudiante contra periodo cerrado inmediatamente anterior y comparable de la misma carrera; conceder una vez por periodo cuando aumente estrictamente; si faltan datos, no conceder y explicar. Carrera configura escala y promedio ponderado antes del uso real (**Propuesta, validación institucional pendiente**).

### RB-05 — Elegibilidad a oportunidades

- Condiciones se definen/publican antes de admitir solicitudes (Origen).
- Solo datos validados pueden cumplir requisito académico. El resultado por requisito es sí/no/datos insuficientes (Propuesta).
- Beca de ejemplo requiere promedio ≥ 70, ≥ 100 puntos de trayectoria, participación en proyecto y curso de investigación aprobado (Origen). «Aprobado» se determina con escala/corte configurado por carrera (Propuesta pendiente).
- Puntos transferidos no satisfacen promedio o puntos propios bajo DEC-06 (Propuesta); no cambian requisitos oficiales (Origen).
- Elegibilidad identifica candidatos; adjudicación que exija juicio institucional queda humana y motivada (Origen).
- Cambiar requisitos o datos conserva versiones e historial e identifica postulaciones afectadas (Propuesta).

### RB-06 — Evaluación de docentes y auxiliares

- Criterios estructurados: claridad de enseñanza, organización, cumplimiento del contenido, retroalimentación, puntualidad, atención a consultas, igualdad de trato percibida (Origen).
- No admitir/presentar insultos, contenido ofensivo, acusación automática de favoritismo ni resultado derivado de muestras pequeñas (Origen).
- Umbral mínimo inicial de cinco respuestas por grupo publicado, ajustable tras evaluación de privacidad (Propuesta, aprobación pendiente).
- Estudiante no ve identidad de otros respondientes; sujeto evaluado recibe solo agregados publicables. Separar registro de habilitación/participación del contenido de respuesta (Propuesta).
- Primera versión sin comentario libre; si se agrega más adelante, requiere moderación, denuncia, retención y evaluación institucional (Propuesta).
- Publicar tendencia/distribución con conteo y contexto; no inferir causalidad o sanción automáticamente (Origen + Propuesta de representación).

### RB-07 — Transferencia

- El documento permite reconocimiento limitado por colaboración con motivo y registro, establece límites mensuales, categorías no transferibles, posible revisión de sospechas y prohibición de alterar requisitos académicos oficiales (Origen).
- Valores iniciales de demostración: máximo 10 por solicitud, 20 enviados por persona/mes calendario, misma carrera, solicitud con referencia y motivo, aprobación independiente, no auto-transferencia (Propuesta).
- Solo categorías marcadas transferibles (Propuesta); materias, promedio, investigación, cursos y premios no transferibles bajo configuración inicial.
- Débito/crédito atómicos; puntos recibidos no retransmisibles ni computables para nivel/mérito propio (Propuesta para prevenir manipulación; validar institucionalmente).
- Límites cuentan en hora local Bolivia, incluyen operaciones aprobadas del mes, y se reevalúan atómicamente al aprobar (Propuesta).
- Rechazo/congelación/resolución de una sospecha requiere revisión humana, acceso restringido y motivo (Origen + Propuesta).

### RB-08 — Encuestas y acompañamiento

- Habilitación de encuesta: matrícula y asignación verificada a sujeto evaluado/campaña (Propuesta).
- Una respuesta por estudiante–sujeto–asignación–campaña (Propuesta).
- Una alerta preventiva requiere regla explícita, dato fuente y periodo comparable; falta de datos no es alerta adversa (Propuesta acorde con acompañamiento del Origen).
- Alertas no afectan calificaciones, SPD ni oportunidades; se usan para ofrecer tutoría, asesoría, curso o recuperación (Origen + Propuesta).

## 6. Matriz de permisos

La matriz describe acciones de negocio; todas presuponen inicio de sesión activo y alcance de carrera/grupo/oportunidad. `Sí` permite la acción indicada, `Propio` solo sobre los objetos del usuario, `Asignado` sobre grupos/recursos explícitamente asignados, `Agregado` solo sobre estadística protegida, y `—` deniega.

| Acción/recurso | Estudiante | Docente/revisor | Coordinación | Admin. de carrera | Admin. institucional |
|---|---|---|---|---|---|
| Ver perfil privado | Propio | Asignado, campos necesarios | Asignado, campos necesarios | — | — |
| Ver su historial oficial | Propio | Asignado, según tarea | Asignado | — | — |
| Ver notas oficiales ajenas | — | Asignado, solo ámbito académico | Agregado o caso autorizado | — | — |
| Declarar habilidad/proyecto | Propio | — | — | — | — |
| Crear actividad para otra persona | — | Asignado | Asignado | — | — |
| Presentar evidencia | Propio | — | — | — | — |
| Revisar/aprobar evidencia | — | Asignado | Asignado/delegado | — | — |
| Cambiar puntos/saldo directamente | — | — | — | — | — |
| Crear ajuste compensatorio SPD | — | — | Motivo y ámbito, si delegado | Regla/motivo, ámbito | Regla/motivo, institucional |
| Consultar propios movimientos | Propio | — | Solo caso autorizado | Solo tarea autorizada | Solo tarea autorizada |
| Editar/publicar reglamento | — | — | Solo si delegado | Sí, ámbito | Sí, institucional |
| Ver oportunidad publicada | Sí, elegible/abierta | Sí, pública | Sí, ámbito | Sí, ámbito | Sí |
| Crear/publicar oportunidad | — | — | Sí | Delegado por coordinación | Sí |
| Postular | Propio | — | — | — | — |
| Revisar postulaciones | — | — | Asignado | Delegado/asignado | Delegado/asignado |
| Resolver adjudicación | — | — | Sí, motivo/cupo | Delegado | Delegado |
| Enviar respuesta de evaluación | Propio, si habilitado | Propio, si se habilita como estudiante | Propio, si habilitado | Propio, si habilitado | Propio, si habilitado |
| Ver respuestas individuales | — | — | — | — | — |
| Ver agregados publicados | — | — | Agregado | Agregado del ámbito | Agregado |
| Ver alertas de acompañamiento | Propias, con explicación | Solo por asignación/función | Asignado | — | — |
| Gestionar caso de apoyo | — | Acción de apoyo asignada | Sí, ámbito | — | — |
| Solicitar transferencia | Propio | Propio, si tiene matrícula | Propio, si tiene matrícula | — | — |
| Revisar transferencia | — | — | Sí, evitando partes | — | Delegado, evitando partes |
| Ver auditoría | — | Propias acciones limitadas si se ofrece | Ámbito, permiso explícito | Ámbito, permiso explícito | Sí, permiso explícito |
| Ver reportes de trayectoria | Propio | Asignado | Ámbito | Agregado de ámbito | Agregado institucional |
| Exportar datos | Propio limitado | Casos asignados y minimizados | Ámbito/permiso | Solo datos mínimos | Solo datos mínimos |
| Administrar cuentas/roles | — | — | Asignaciones delegadas | Usuarios/roles del ámbito | Sí, ámbito institucional |
| Administrar carreras/periodos | — | — | No, salvo delegación | Carrera delegada | Sí |

### Reglas de separación de funciones

1. Nadie aprueba su propia evidencia, transferencia, postulación ni cambio de puntos que le beneficie.
2. Emisor y receptor de transferencia nunca la revisan.
3. Docente evaluado no ve identidad de respondientes, disponibilidad de respuesta ni respuestas individuales.
4. Administrar la aplicación no da acceso rutinario a expedientes académicos ni a respuestas de evaluación individuales.
5. Operaciones de emergencia requieren motivo, evento de auditoría y acceso temporal revocable.
6. Si una misma persona tiene varios roles, se registra el rol efectivo en cada operación; el rol más amplio no elimina el conflicto de interés.

### Permisos técnicos transversales

| Operación | Política |
|---|---|
| Leer/listar | Aplicar ámbito al conjunto en servidor antes de serializar o paginar. No confiar en identificador o filtros enviados por navegador. |
| Crear | Derivar actor/carrera/periodo de asignaciones verificadas; rechazar ámbito arbitrario del cliente. |
| Modificar | Verificar propiedad, ámbito, permiso y estado permitido; usar transición de estado. |
| Eliminar | No borrar historia de actividad/puntos/postulación/auditoría; desactivar o crear reversión justificada. |
| Archivos | Comprobar cada descarga con el mismo ámbito que su evidencia; almacenamiento privado y nombre interno aleatorio. |
| Exportación | Aplicar permisos y filtros en servidor; registrar actor, alcance, fecha y cantidad exportada. |
| API/acciones HTMX | Mismos servicios y permisos que una petición HTML; CSRF y autorización servidor. |

## 7. Requisitos no funcionales y aceptación

| ID | Requisito | Criterio de aceptación |
|---|---|---|
| RNF-01 | Instalación gratuita y local | Instalación desde instrucciones en Windows destino, con dependencias fijadas y sin servicio pagado ni Internet requerido durante operación normal. |
| RNF-02 | Seguridad por rol, objeto y ámbito | Casos positivos/negativos de toda matriz, acceso cruzado entre carreras/grupos y descarga/exportación directa verificados. Denegar por defecto. |
| RNF-03 | Integridad transaccional | Ningún resultado parcial de puntos, transferencia, adjudicación o revisión en fallo/reintento. Duplicados impedidos por regla y restricciones. |
| RNF-04 | Protección de credenciales | Contraseñas con algoritmo recomendado por framework; CSRF; sesión cerrada/expirada; tokens temporales; secretos excluidos del código y logs. |
| RNF-05 | Manejo de archivo | Lista por extensión y contenido, límite configurable inicial 10 MB, nombre interno, ruta privada, descarga autorizada, respuestas `Content-Disposition` restrictivas. |
| RNF-06 | Privacidad | Menor dato necesario, perfil privado, permisos de apoyo, encuestas separadas y supresión de agregados pequeños. Aprobación institucional requerida antes de usar datos personales reales. |
| RNF-07 | Accesibilidad | Objetivo WCAG 2.2 AA para recorridos principales: teclado, foco visible, etiquetas, errores asociados, contraste, ampliación y equivalentes textuales de gráficos. |
| RNF-08 | Rendimiento local | Objetivo inicial p95 ≤ 2 s en consultas típicas y ≤ 5 s por evaluación de elegibilidad individual con 20 sesiones y hardware de referencia declarado; medir y documentar. |
| RNF-09 | Crecimiento | Validar con dataset sintético de 5.000 estudiantes/100.000 movimientos; consultas paginadas, índices medidos y exportación por lotes si es necesario. |
| RNF-10 | Respaldo/restauración | Copia de base y archivos coordinada; ensayo restaura movimientos, adjuntos y auditoría. Objetivo propuesto RPO 24 h/RTO 60 min al volumen de referencia. |
| RNF-11 | Usabilidad | Flujos tienen carga, error, vacío, éxito, falta de permiso y datos insuficientes; mensajes accionables; uso en anchuras de 360, 768 y 1366 px. |
| RNF-12 | Mantenibilidad | Migraciones repetibles, reglas de negocio centralizadas en backend, dependencias/versiones identificables, errores sin secretos y documentación enlazada a requisitos. |
| RNF-13 | Observabilidad | Salud técnica restringida, diagnósticos útiles, registro estructurado sin contraseñas/tokens/encuestas; auditoría de negocio consultable por permiso. |
| RNF-14 | Fiabilidad de datos | Fechas de negocio en America/La_Paz, horas almacenadas UTC, cantidades enteras, promedios con tipo decimal y movimientos reproducibles. |

## 8. Estados y transiciones

| Objeto | Transición permitida | Quién actúa | Restricciones |
|---|---|---|---|
| Evidencia | Borrador → En revisión | Estudiante | Matrícula propia activa; campos/archivo completos. |
| Evidencia | En revisión → Observada | Revisor asignado | Motivo y solicitud de corrección; sin puntos. |
| Evidencia | En revisión → Rechazada | Revisor asignado | Motivo obligatorio; sin concesión. |
| Evidencia | En revisión → Aprobada | Revisor asignado | Criterio/evidencia verificados; si hay regla SPD, movimiento atómico e idempotente. |
| Evidencia | Observada → En revisión | Estudiante | Nueva respuesta vinculada a observación; historial anterior se conserva. |
| Evidencia aprobada | Aprobada → Revocada | Admin/coordinación delegada | Motivo y evidencia; asiento compensatorio y revisión de elegibilidad afectada. |
| Oportunidad | Borrador → Publicada | Responsable asignado | Condiciones tipadas, periodo y fechas válidos. |
| Oportunidad | Publicada → Cerrada | Automático/responsable | Fecha/hora límite; ninguna postulación nueva. |
| Oportunidad | Cerrada → En resolución → Resuelta | Responsable autorizado | Revisión de elegibilidad y cupo; razón por decisión. |
| Oportunidad | Cualquier estado abierto → Cancelada | Responsable/coordinación | Justificación y aviso a postulantes; historial conservado. |
| Postulación | Borrador → Enviada | Estudiante | Dentro del plazo, requisitos/formulario válidos. |
| Postulación | Enviada → En revisión → Seleccionada/No seleccionada | Responsable | Cupo disponible, motivo y versión histórica. |
| Postulación | Enviada → Retirada | Estudiante | Solo antes de cierre/resolución según configuración publicada. |
| Transferencia | Solicitada → Aprobada/Rechazada | Revisor independiente | Límite/saldo revalidados al confirmar; decisión motivada. |
| Transferencia | Solicitada → Cancelada | Emisor | Solo antes de decisión. |
| Transferencia aprobada | Aprobada → Revertida | Admin/coordinación delegada | Movimiento compensatorio, causa e historial vinculados. |
| Campaña | Borrador → Abierta → Cerrada → Publicada | Coordinación/sistema | Fechas/encuesta versionadas; publicar solo agregados elegibles por umbral. |
| Caso de apoyo | Detectado → Revisado → Asignado → Seguimiento → Cerrado/Descartado | Coordinación | Regla explicable, responsable y nota final; confidencialidad. |

## 9. Decisiones de dominio registradas

| ID | Decisión de trabajo | Base | Estado / efecto |
|---|---|---|---|
| DEC-01 | Una identidad puede tener varios roles, cada uno acotado a ámbitos explícitos. | Necesidad mult carrera y roles del documento. | Adoptada para diseño. |
| DEC-02 | Puntos, matrícula y actividades conservan carrera/periodo de origen. | Multi carrera requerida por el usuario. | Adoptada; el modelo ER de E02 debe resolver trayectoria al cambiar de carrera. |
| DEC-03 | Usar movimientos anexados e inmutables; ajuste por contrapartida. | Motivo visible y trazabilidad del documento. | Adoptada. |
| DEC-04 | Distinguir puntos propios, enviados, recibidos y saldo transferible. | Transferencia y límites del documento; prevención de manipulación. | Propuesta adoptada para prototipo; aprobar significado institucional del saldo/meritaje antes de uso real. |
| DEC-05 | Mismo hecho da un solo reconocimiento SPD; categoría de premio superior sustituye categoría base. | Documento lista actividad académica, proyecto destacado y ganador por separado, sin regla de acumulación. | Propuesta; etiquetar el hecho y definir excepciones institucionales. |
| DEC-06 | Puntos transferidos no cuentan para niveles ni requisitos de mérito propio y no se retransfieren. | El documento impide que transferencias alteren requisitos académicos oficiales, pero no define efecto en nivel. | Propuesta conservadora para demo; validar antes de decisión real. |
| DEC-07 | Topes iniciales de transferencia: 10 por solicitud, 20 por mes/cuenta, misma carrera y aprobación independiente. | Fuente requiere límite mensual; no establece números ni revisor. | Provisional/configurable; aprobación institucional pendiente. |
| DEC-08 | Evaluación sin texto libre en versión 1.0; respuesta estructurada y sujetos ven agregados. | Documento exige evaluación respetuosa y agregada, sin insultos. | Adoptada para demo; confirmación de cuestionario/retención pendiente. |
| DEC-09 | Suprimir agregado con menos de 5 respuestas. | Fuente exige mínimo, no número. | Provisional/configurable; evaluación de privacidad institucional pendiente. |
| DEC-10 | Publicación no interpreta automáticamente favoritismo ni aplica sanción a personal/estudiantes. | Prohibición expresa del documento. | Adoptada. |
| DEC-11 | Notificaciones se mantienen dentro de la aplicación; nada depende de servicios externos. | Restricción local/gratuita y correo/WhatsApp están en segunda versión. | Adoptada. |
| DEC-12 | Recuperación de acceso local mediante token temporal mostrado por flujo local/admin; sin SMTP obligatorio. | Restricción de red local; correo es una extensión. | Requiere definición de experiencia segura en E02. |
| DEC-13 | El promedio exige escala, regla de aprobado y método de ponderación por carrera/periodo. | El origen da promedio mínimo de ejemplo, no escala, corte, ponderación ni fuente. | Parámetros configurables; institución debe proporcionarlos antes de datos reales. |
| DEC-14 | Elegibilidad muestra por requisito los datos usados y versión; adjudicación humana donde corresponde. | Transparencia y revisión humana del documento. | Adoptada. |
| DEC-15 | Indicadores de apoyo son preventivos y no alteran puntos, notas ni oportunidades. | El documento plantea acompañamiento y no solo premiación. | Adoptada; umbrales de alerta se decidirán con responsables académicos. |
| DEC-16 | Retención y borrado de datos reales queda sujeta a política aprobada de la institución. | La propuesta no define plazos ni tratamiento de privacidad. | Pendiente antes de adopción real; datos sintéticos durante desarrollo. |
| DEC-17 | La operación será localhost por defecto; acceso por red local es configuración aparte. | Preferencia local/gratuita del usuario. | Adoptada para seguridad operacional. |

### Riesgo pendiente de aclaración institucional

Este documento deja operativo el software para datos ficticios, pero los siguientes valores no se deben mostrar como normas oficiales ni usar para adjudicar oportunidades reales hasta aprobación: topes/categorías de transferencia; ponderación y nota mínima de aprobación por asignatura; definición oficial del promedio; mínimo de respuestas y reglas de agregación; umbrales preventivos y acceso a casos; causas y proceso de penalización; conservación/corrección de evaluaciones. El sistema permitirá administrarlos con versión, responsable y vigencia.

## 10. Matriz de trazabilidad

| Requisito/tema | Fuente | Historia/caso | Entrega prevista |
|---|---|---|---|
| Perfil integral, habilidades, logros, proyectos y participación | Doc. §1–7, RF-03 | HU-03.1; declarar y validar | E05 |
| Login, roles | Doc. §8–9 | HU-01.1–01.3 | E04 |
| Varias carreras, periodos, grupos y matrícula | Solicitud del usuario; doc. §8 | HU-02.1–02.2; cruce de ámbito | E04 |
| Actividad, evidencia y validación | Doc. §3, 5, 9 | HU-04.1–04.2 | E06 |
| Puntos, niveles, reglamento | Doc. §10 | HU-05.1–05.2 | E06 |
| Elegibilidad, becas, trazabilidad | Doc. §11 | HU-06.1, HU-07.1–07.2 | E07 |
| Encuesta estructurada/agregada | Doc. §12 | HU-08.1–08.2 | E09 |
| Alertas y apoyo | Doc. §13 | HU-09.1 | E10 |
| Transferencias | Doc. §14 | HU-10.1 | E08 |
| Reportes, panel, bitácora | Doc. §9, 16–18 | HU-11.1, HU-12.1 | E11 |
| Notificaciones internas | Doc. §9; extensión funcional local | HU-13.1 | E11 |
| Datos sintéticos, operación local | Solicitud del usuario; Doc. §15, 17–19 | HU-14.1 | E03, E13 |

## 11. Criterios de cierre de E01

E01 queda completo para continuar al diseño cuando:

1. Los 14 requisitos funcionales tienen identificador, comportamiento y criterios comprobables.
2. La matriz contempla permisos y restricciones para cada rol, y marca denegaciones de alto riesgo.
3. Las categorías de puntos, valores y niveles coinciden exactamente con el documento de origen.
4. Las reglas propuestas se separan visiblemente de las originales y tienen configuración/versionado.
5. Los estados cubren revisión, corrección, rechazo, adjudicación, transferencias y acompañamiento.
6. Los requisitos están vinculados a historias y a la entrega E02–E13 correspondiente.
7. Las decisiones pendientes de validación institucional no impiden crear un prototipo con datos ficticios.

**Resultado:** los siete criterios están representados en esta línea base. E02 debe convertirla en diagrama de datos, flujos de pantalla, decisiones visuales y modelo de amenazas. Si el usuario cambia una definición, actualizar primero las secciones y requisitos afectados antes de usarlos como contrato de implementación.

## 12. Glosario

| Término | Definición en esta especificación |
|---|---|
| Carrera | Programa académico que delimita configuración, asignaciones y reportes. |
| Periodo | Intervalo académico al que pertenecen asignaturas, grupos, notas y evaluaciones. |
| Evidencia | Registro/archivo asociado a actividad para demostrar el cumplimiento de una regla. |
| Regla versionada | Definición de negocio con alcance, valores, criterio, responsable y vigencia inmutables tras publicación. |
| Saldo disponible | Puntos de origen transferible no comprometidos, conforme al reglamento vigente; no equivale a mérito propio. |
| Adjudicación | Decisión institucional sobre una oportunidad después de la comprobación de requisitos. |
| Agregado | Estadística combinada que superó umbral y filtros de privacidad; no es respuesta individual. |
| Caso de apoyo | Registro confidencial de recomendación y seguimiento académico; no es sanción ni puntaje. |
| Reversión | Asiento nuevo que compensa un movimiento anterior sin borrar historia. |

