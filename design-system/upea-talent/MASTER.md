# UPEA Talent+ — sistema visual

## Producto y usuarios

Portal académico local, mult carrera, para estudiantes, docentes, revisores y coordinación. La interfaz prioriza comprensión de trayectoria, privacidad por rol, estados verificables y lectura de datos antes que promoción comercial.

## Dirección visual

Usar una superficie clara, institucional y serena consistente con el prototipo E02. La consulta de UI/UX Pro Max propuso un patrón «Enterprise Gateway» y modo oscuro OLED; estos resultados no representan una herramienta académica cotidiana y no sustituyen el lenguaje ya validado en E02. Se adopta una interfaz de portal estudiantil con navegación estable, tarjetas de información, tablas semánticas y estados diferenciados.

## Recursos locales

- No cargar Google Fonts, CDN, imágenes ni iconos remotos. Usar `system-ui`, `Segoe UI` y gráficos SVG locales cuando se necesiten.
- Paleta: navy `#17324D`; teal `#176B63`; teal suave `#EAF4F2`; texto `#182B3A`; texto secundario `#526475`; fondo `#F5F7F8`; superficie `#FFFFFF`; borde `#DCE3E8`.
- Estados: verde `#256343`; ámbar `#744800`; rojo `#9D3036`; azul `#245675`; acompañar siempre color con etiqueta textual.
- Espaciado base: 4, 8, 12, 16, 20, 24, 32, 40 px. Radios: 6, 10, 14 px.
- Tipografía de sistema; cuerpo 16 px; line-height 1.5; contraste de texto normal de al menos 4.5:1.

## Interacción y accesibilidad

- Emplear enlaces para navegar y botones para acciones; formularios con etiquetas visibles y errores junto al campo.
- Mantener un enlace para saltar al contenido, jerarquía de encabezados, foco visible, operación completa con teclado y zoom disponible.
- Diseñar primero para móvil; no introducir desplazamiento horizontal de página; convertir tablas en filas etiquetadas en pantallas estrechas.
- Estados vacíos explican por qué faltan datos y qué acción puede realizar la persona.
- Respetar `prefers-reduced-motion`; las transiciones indican cambio de estado y nombran propiedades explícitamente.
- Distinguir visual y textualmente “Declarado”, “En revisión”, “Validado” y “Requiere cambios”. No inferir notas, promedios ni elegibilidad cuando los datos oficiales estén ausentes.

## Componentes compartidos

Cabecera institucional, navegación por rol, migas de pan, encabezado de página, tarjeta de resumen, tabla adaptable, insignia textual de estado, formulario con ayuda/error, estado vacío y mensajes de resultado accesibles.
