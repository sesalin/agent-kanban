# Programaciones vigentes desde el 20 de noviembre de 2026

> **Refactor preparado (no publicado automáticamente):** el nuevo flujo,
> horarios y sustitución del polling están en [FACTORY_RUNBOOK](../../FACTORY_RUNBOOK.md).
> Los bloques anteriores conservados abajo describen la instalación histórica.

Todos los horarios son **America/Mexico_City**, todos los días. Sustituye
las programaciones anteriores; no agregues otra copia de la misma etapa.

| Inicio | Responsable | Trabajo | Configuración |
| --- | --- | --- | --- |
| 12:20–22:00 cada 5 min | n8n | Conciliar tarjetas/ZIP/estados sin LLM | Publicado en anyo |
| 12:30 | Brio | Investigación; no tomar otra después de 14:15, entregar antes de 14:45 | Su Muse; actualizar brio.md |
| 15:00 | Bacha | Evaluar GO/NO_GO | Su Muse |
| 15:00–17:25 cada 5 min | Codex | Ventana futura de MVP hasta antes de 17:30; una tarjeta a la vez | Timer WSL suspendido por el operador |
| 16:00 | Bacha | Prospectos y textos comerciales | Su Muse; reemplaza turno 18:00 |
| 16:00 | Dot | Landing mediante obsidian-mcp | Programar en su plataforma |
| 19:00 | Bacha | Cierre de las oportunidades con todas sus ramas listas | Su Muse; reemplaza 20:30 |
| 19:30–22:00 cada 5 min | n8n | Entregar informe diario y reintentar si falla Telegram | Publicado en anyo |

Las búsquedas/análisis de radares conservan sus horarios de mañana. Brio y
Bacha comparten la restricción de una sesión Muse activa; Codex y Dot no.
Los tres constructores pueden iniciar a las 16:00 si ya se aceptó el GO.
Una rama pendiente no impide iniciar o entregar las otras; sí impide crear
el cierre. Un GO aceptado después de las 16:00 se recoge si la sesión del
agente continúa consultando su cola, o en su siguiente ejecución diaria si
ya terminó. El cron de n8n no inicia las sesiones externas de los agentes.

## Mensaje a Dot

«Carga las instrucciones de dot.md y programa su ejecución diaria a las
16:00, America/Mexico_City, con obsidian-mcp habilitado. Confirma el horario
y que la ejecución programada dispone de las herramientas factory_dot_*.
Trabaja solo tus landings del proyecto 1, desarrollando y probando en tu propio workspace. Descarga la entrada con factory_dot_download_input; empaqueta allí el resultado y súbelo con factory_dot_upload_result usando el parámetro de archivo nativo, y envía a revisión. No delegues la landing a Codex ni desarrolles en la carpeta del MCP.
Tras entregar continúa con tu siguiente tarjeta propia dentro de la ventana.»

[Prompt completo de Dot](dot.md).

## Mensaje a Bacha

«Sustituye tu programación anterior por tres tareas diarias, zona
America/Mexico_City: 15:00 EVALUATION (entregar antes de 15:45), 16:00 PROSPECTION, 19:00 FINAL.
Elimina tus turnos viejos de prospección 18:00, landing 19:00 y cierre 20:30.
La landing ahora es de Dot. Carga bacha.md actualizado y confirma los tres
horarios. Durante cada turno entrega tus tarjetas y sigue con la siguiente
propia de esa etapa. No esperes al MVP para comenzar prospección. En FINAL
solo revisa lo que n8n ya habilitó con todas las ramas activas terminadas.»

[Contrato y mensajes de cada etapa de Bacha](bacha.md).

Antes de la siguiente evaluación, pasar también el
[prompt de calidad de requerimientos](bacha-requerimientos.md) y pedir que lo
incorpore a sus instrucciones de EVALUATION y revisión FINAL. Debe definir
encargos ejecutables para las tres ramas y distinguir entrega técnica de
validación comercial y operación real. Este ajuste conserva los tres horarios,
el esquema JSON y el reparto; no regenera paquetes ya consumidos.


## Corrección de Codex

Codex continúa suspendido. La ventana futura de nuevos reclamos es
15:00–17:30, con consultas cada cinco minutos hasta 17:25, una tarjeta a
la vez. No crear otra programación ni reactivar el timer sin autorización.
El lanzador lee [codex.md](codex.md) en cada trabajo.

Instrucción vigente: «Entrega el flujo principal del MVP sin sobreingeniería.
README con arranque en un comando y pruebas en las primeras diez líneas;
3–5 pruebas automatizadas incluyendo un error crítico. Si falta un acceso
exigido y no se autoriza MODO DEMO CON DATOS SEED, registra blocked con el
acceso faltante. A las 17:30 no reclames otra; termina y prueba la tarjeta
viable ya iniciada antes de empaquetar y enviar a revisión.»

## Mensaje breve a Brio

«Conserva las 12:30. Actualiza brio.md: no tomes otra tarjeta después de
14:15; unos 30 minutos de investigación por tarjeta y entrega antes de 14:45.
Si hay captcha o descarga inaccesible, documenta la laguna y sintetiza con
la evidencia verificable, sin inventar. El acumulado puede quedar para mañana;
no ocupes la ventana de Bacha esperando horas una sola fuente.»

## Qué falta confirmar fuera de este servidor

El operador debe cargar los documentos y confirmar los horarios de Bacha y
Dot en sus plataformas, y pasar a Brio su ajuste. Aquí no hay herramientas
para editar esas programaciones externas. WSL debe permanecer encendido y
Codex autenticado. La primera jornada con los tres agentes reales comprobará
el arranque programado; las pruebas locales no sustituyen esa comprobación.
