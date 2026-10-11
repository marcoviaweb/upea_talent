# E12 — Consolidación

**Estado:** implementación y verificación base completadas; certificación integral de RNF pendiente de entorno de referencia.

## Alcance

Consolidar los recorridos E01–E11 y corregir defectos de seguridad, accesibilidad, rendimiento y consistencia antes de la operación. La suite local y el build constituyen la verificación repetible de esta entrega; las metas que requieren hardware concurrente, dataset de referencia o validación humana se declaran pendientes y no se consideran aprobadas por inferencia.

## Cambios realizados

- El perfil con `DJANGO_DEBUG=0` activa por defecto redirección HTTPS, HSTS de un año y cookies de sesión/CSRF seguras. En modo local `DEBUG=1`, estas opciones quedan desactivadas para que el entorno HTTP de desarrollo siga funcionando.
- HSTS para subdominios y preload son opt-in (`DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS`, `DJANGO_SECURE_HSTS_PRELOAD`): requieren confirmar que todos los subdominios del dominio institucional funcionan solo mediante HTTPS.
- Se fijan `X-Content-Type-Options: nosniff` y `Referrer-Policy: same-origin`; se mantiene `X-Frame-Options: DENY`, CSRF y sesión HTTP-only.
- Se revisó la interfaz con Web Interface Guidelines. La SPA ya ofrece enlace para saltar al contenido principal, foco visible, labels/formularios nativos, navegación mediante enlaces, mensajes de error, estados de carga, reglas responsive y `prefers-reduced-motion`. No se encontró uso de `transition: all`, `outline: none` ni bloqueo de zoom.

## Evidencia reproducible

| Verificación | Resultado | Comando / evidencia |
|---|---|---|
| Suite backend completa | 81/81 aprobadas (42,9 s) | `python manage.py test --keepdb` |
| Build TypeScript + Vite | Aprobado; 1.928 módulos; JS 420,59 kB / 120,15 kB gzip; CSS 103,81 kB / 22,56 kB gzip | `npm run build` |
| Verificaciones Django | Sin errores del sistema; sin cambios de migración | `python manage.py check`; `python manage.py makemigrations --check --dry-run` |
| Perfil local | Correcto; cookies seguras/redirect HTTPS apagados con `DEBUG=1` | `python manage.py check` |
| Perfil de producción | Correcto excepto avisos intencionales para HSTS subdominios y preload | `DJANGO_DEBUG=0 python manage.py check --deploy` |
| Higiene del diff | Sin errores de whitespace | `git diff --check` |

## Matriz de aceptación RNF

| Requisito | Estado E12 | Evidencia / pendiente |
|---|---|---|
| RNF-01 instalación local | Parcial | README, dependencias fijadas y compose existen; ensayo limpio/offline corresponde a E13. |
| RNF-02 permisos por rol/objeto/ámbito | Parcial | Suite incluye pruebas de permisos de funcionalidades; falta matriz integral que cubra todas las rutas, descargas y exportaciones con usuarios de carreras/grupos cruzados. |
| RNF-03 integridad transaccional | Parcial | Suite funcional aprobada; falta inyectar fallos/reintentos en cada operación crítica bajo escenario concurrente. |
| RNF-04 credenciales y sesión | Parcial | Framework hash, CSRF, cookies HTTP-only; perfil HTTPS corregido. Falta ensayar caducidad/logout y revisar despliegue/proxy real. |
| RNF-05 archivos | Parcial | Límites/validación y pruebas existentes del flujo; falta matriz de tipo/contenido, descargas no autorizadas y cabeceras sobre servidor de operación. |
| RNF-06 privacidad | Parcial | Roles, ámbito y supresión de encuestas están implementados; revisión institucional de privacidad sigue pendiente antes de datos reales. |
| RNF-07 WCAG 2.2 AA | Parcial | Inspección estática y soporte de teclado/foco/reducción de movimiento; requiere auditoría manual con teclado/lector, ampliación y contraste AA en pantallas principales. |
| RNF-08 p95 con 20 sesiones | Pendiente | No medido: falta declarar hardware objetivo y ejecutar carga representativa. |
| RNF-09 5.000 estudiantes / 100.000 movimientos | Pendiente | No ejecutado; falta dataset sintético de volumen y medición de paginación, índices y exportación. |
| RNF-10 respaldo y restauración | Pendiente de E13 | Requiere ensayo coordinado con base y archivos y medir RPO/RTO. |
| RNF-11 estados y tamaños de pantalla | Parcial | Estados y CSS responsive están implementados; falta recorrer cada estado en 360, 768 y 1366 px y registrar resultado visual. |
| RNF-12 mantenibilidad | Aprobado en verificación base | Migraciones sin cambios pendientes, reglas en backend y documentación E01–E11 enlazada desde el plan. |
| RNF-13 observabilidad | Parcial | Auditoría de negocio y respuestas restringidas existen; falta ensayo operativo de salud/logs y sanitización con credenciales centinela. |
| RNF-14 fiabilidad de datos | Aprobado en revisión base | `America/La_Paz`, `USE_TZ`, importes enteros y modelos de promedio decimal; suite backend aprobada. |

## Pendientes para cerrar formalmente E12

1. Ejecutar RNF-02/03/05/06/13 con la matriz completa de actores/ámbitos y capturar resultados por ruta, incluidos CSV, descarga y acceso directo.
2. Medir RNF-08/09 en una máquina de referencia declarada, con carga y dataset sintético versionados; guardar tiempos p50/p95, consultas lentas y memoria.
3. Completar auditoría manual WCAG 2.2 AA y recorrido visual en 360/768/1366 px; corregir los defectos encontrados.
4. Coordinar el ensayo de respaldo/restauración RNF-10 con E13, que entrega el proceso operativo.

Hasta completar estas mediciones, no se declara certificación de todos los RNF ni se recomienda usar datos personales reales.
