# E08 — Transferencias limitadas y revisión de irregularidades

E08 agrega reconocimiento entre estudiantes desde **Evidencias y SPD → Transferencias**. Una solicitud usa puntos ya concedidos por una actividad propia aprobada bajo categoría transferible; los puntos recibidos no son una fuente transferible ni modifican mérito académico, nivel o elegibilidad.

## Reglas implementadas

- Solo matrículas activas de la misma carrera; el emisor y destinatario deben ser personas distintas.
- El origen debe ser una actividad del emisor, aprobada, con un movimiento SPD positivo sin reversión y una categoría marcada como transferible en la versión del reglamento.
- Cada solicitud es de 1 a 10 puntos; la persona puede enviar o reservar hasta 20 puntos por mes calendario de Bolivia. La reserva ocurre al enviar y se libera al cancelar/rechazar.
- La solicitud exige destinatario, origen, motivo y clave de idempotencia. No se repite el reconocimiento activo de una misma actividad a la misma persona.
- Emisor y receptor no pueden revisar. Una persona autorizada en el ámbito —coordinación/administración de carrera, administración institucional o revisor de evidencia/docente asignado a la actividad— aprueba o rechaza con motivo.
- Al aprobar, el servidor vuelve a comprobar origen, reserva y cupo mensual, y crea en una transacción movimientos de débito y crédito de igual magnitud por cada origen. Cada línea conserva la referencia al movimiento SPD original; el libro global de transferencias suma cero.
- El historial separa mérito propio, puntos enviados, recibidos y saldo elegible. Los recibidos no se retransfieren y permanecen fuera del libro de mérito propio de E06.
- Se marcan para revisión prioritaria patrones recíprocos o solicitudes repetidas a una persona. Las señales no sancionan automáticamente y sus detalles se restringen al revisor.
- Si se revoca un mérito que ya originó una transferencia, se crea una alerta restringida y se bloquean nuevos envíos de esa persona. Al resolverla, el sistema registra contrapartidas compensatorias append-only vinculadas al movimiento original y a la alerta, y deja el motivo/actor en auditoría.
- El emisor puede cancelar una solicitud pendiente. Las solicitudes aprobadas/rechazadas y los movimientos no se editan ni eliminan.

Los límites de 10/20 y la transferibilidad de colaboración/mentoría son valores de demostración propuestos en el plan, no una política oficial aprobada por UPEA. Se sirven desde el backend y se validan en la base transaccional; no dependen del navegador.

## Datos ficticios de prueba

`seed_demo` añade a `demo.estudiante02` (Mateo Ficticio) una mentoría ficticia aprobada por 10 puntos y una transferencia aprobada de 2 puntos recibida de `demo.estudiante03` (Lucía Muestra). Lucía tiene su propio origen de mentoría con 10 puntos, del que ya envió esos 2; puede enviar reconocimientos adicionales. Así Mateo ve un saldo disponible para enviar y un movimiento real en su historial desde el primer ingreso. No cambia los 100 puntos propios del recorrido E07 de `demo.estudiante01` (Andrea Ejemplo). Las cuentas no tienen contraseñas precargadas.

Recorrido local:

1. Inicia PostgreSQL y Django, ejecuta `manage.py migrate` y luego `manage.py seed_demo`.
2. Asigna claves locales a `demo.estudiante02`, `demo.estudiante03`, `demo.estudiante01` y `demo.coordinador01` con `manage.py changepassword <usuario>`.
3. Entra como `demo.estudiante02` para ver sus 10 puntos propios transferibles y los 2 puntos recibidos de Lucía en el historial. También puede proponer hasta 10 puntos a `demo.estudiante01` desde su actividad **Mentoría entre pares para prueba E08**.
4. Para probar otra solicitud, entra como `demo.estudiante03` y envía hasta 8 de los 10 puntos de su mentoría a `demo.estudiante01`; explica el aporte. Lucía conserva 2 puntos disponibles porque el ejemplo ya transfirió 2 a Mateo.
5. Abre otra sesión como `demo.coordinador01`, vuelve a **Transferencias**, revisa la nueva actividad y motivo; registra una aprobación o rechazo motivado.
6. Reingresa como emisor y destinatario para consultar el movimiento en el historial. Verifica que el saldo propio/nivel y la elegibilidad de Andrea no aumenten por puntos recibidos.

Para recorrer una cancelación, inicia otra solicitud antes de resolverla y cancélala desde el historial del emisor. Para probar alertas con datos controlados, usa las pruebas automatizadas; no revoques méritos del seed general solo para probar.

## API y almacenamiento

- `GET/POST /api/v1/transfers/`: ámbitos, orígenes disponibles, balances separados, solicitudes propias/recibidas, cola de revisión y alertas autorizadas.
- `POST /api/v1/transfers/<id>/cancel/`: liberar reserva por acción del emisor.
- `POST /api/v1/transfers/<id>/review/`: resolución independiente y pareado transaccional.
- `POST /api/v1/transfers/alerts/<id>/resolve/`: resolución administrativa de alerta con motivo y movimientos compensatorios cuando corresponda.

Modelos: `TransferRequest`, `TransferAllocation` (reserva del origen), `TransferMovement`, `TransferAdjustment`, `TransferReview` y `TransferRiskAlert`. Los movimientos, revisiones y ajustes son append-only. Las migraciones iniciales y compensatorias están bajo `apps/transfers/migrations/`.

## Verificación

```powershell
.\.venv\Scripts\python.exe manage.py test apps.transfers
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
npm run typecheck
npm run build
```

Las pruebas cubren origen no transferible, carrera y ámbito, deduplicación/idempotencia, cuotas mensual/por operación, reserva y liberación, aprobación independiente, libro balanceado, no retransmisión, señales recíprocas, revocación/compensación y dos solicitudes concurrentes sobre el mismo origen.
