# E11 — Gestión y análisis

**Estado:** implementado · **Dependencias:** E07–E10 · **Alcance:** informes agregados por carrera/periodo, CSV e impresión, bandeja personal de notificaciones y consulta de auditoría de solo lectura.

## Informes

La página **Gestión y análisis** presenta métricas de matrículas, grupos, notas verificadas, evidencias, movimientos SPD, oportunidades, postulaciones, transferencias y casos de acompañamiento. El selector de carrera y periodo restringe la consulta en el servidor: el identificador enviado por el navegador nunca amplía los ámbitos del usuario. Las tarjetas resumen valores sin comparar escalas heterogéneas; la tabla ofrece una alternativa accesible equivalente. Estudiantes ven un resumen agregado de su propia trayectoria, aislado de los demás estudiantes y sin filtros de carrera o exportación institucional.

Los informes son descriptivos. No muestran expedientes ajenos, respuestas individuales de evaluación ni afirmaciones de causalidad. El promedio convierte notas verificadas y vigentes a escala 100 con su escala histórica; puntos SPD corresponden al saldo neto de movimientos. Los conteos reflejan registros existentes en las fuentes de cada módulo.

**CSV:** `GET /api/v1/reports/?career=<uuid>&period=<uuid>&export=csv`. El formato usa UTF‑8 con BOM para hojas de cálculo, incluye filtros, fuente/definición, denominador y fecha de extracción. La vista **Imprimir informe** utiliza los mismos datos y filtros visibles.

## Notificaciones

La bandeja personal lista hasta 50 avisos recientes, indica cuántos siguen sin leer y permite marcarlos como leídos. Se notifican envíos y revisiones de evidencia, postulaciones y decisiones, publicación de oportunidades, transferencias y cambios en acompañamiento. Los avisos contienen texto genérico y una ruta interna, nunca archivos o evidencia privada. Se programan al confirmar la transacción auditada y se deduplican por destinatario/evento. Abrir el destino vuelve a pasar por la autorización del módulo.

Endpoints: `GET /api/v1/notifications/` y `POST /api/v1/notifications/<uuid>/read/`. Cada usuario solo puede listar y marcar sus propios avisos.

## Auditoría y permisos

La pestaña **Bitácora** solo aparece para coordinación y administración con carreras vigentes en su asignación, administración institucional dentro de su institución y superusuario técnico. El servidor filtra por ámbito y permite filtrar acción y fechas; devuelve hasta 200 eventos recientes. La respuesta muestra actor, rol/ámbito observado en el momento de la operación, acción, objeto, ámbito, resultado y motivo, sin exponer el JSON de metadatos interno. El endpoint es exclusivamente `GET`.

Los eventos continúan siendo inmutables. `record_event` conserva una instantánea no secreta de roles/ámbitos en `safe_metadata.actorRoles`; la API solo presenta los campos necesarios. La auditoría no incluye respuestas individuales de campañas de evaluación.

## Instalación y verificación local

```powershell
python manage.py migrate
python manage.py check
python manage.py test apps.reporting --keepdb
cd frontend
npm run build
```

La migración crea `reporting_notification`. Los informes requieren asignación vigente `coordinator`, `career_admin` o `institution_admin`; estudiantes y docentes sin uno de esos ámbitos pueden consultar su bandeja, pero no ven el módulo de informes ni bitácora.

## Cobertura

Las pruebas comprueban aislamiento entre carreras y estudiantes, resumen personal, filtros de carrera/periodo, CSV, bitácora de solo lectura, cola de revisión a partir de eventos comprometidos, privacidad de la bandeja y rechazo de rutas externas. El cierre integral y la revisión completa de accesibilidad/performance corresponden a E12.
