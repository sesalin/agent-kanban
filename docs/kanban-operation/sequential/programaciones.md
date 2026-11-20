# Programaciones vigentes desde el 20 de noviembre de 2026

Todos los horarios son **America/Mexico_City**, todos los días. Sustituye
las programaciones anteriores; no agregues otra copia de la misma etapa.

| Inicio | Responsable | Trabajo | Configuración |
| --- | --- | --- | --- |
| 12:20–22:00 cada 5 min | n8n | Conciliar tarjetas/ZIP/estados sin LLM | Publicado en anyo |
| 12:30 | Brio | Investigación; no tomar otra después de 14:15, entregar antes de 14:45 | Su Muse; actualizar brio.md |
| 15:00 | Bacha | Evaluar GO/NO_GO | Su Muse |
| 16:00–17:55 cada 5 min | Codex | Revisar cola de MVP; inicia modelo solo si hay tarjeta | Timer WSL activo |
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

## Corrección de Codex

Su timer ya consulta desde las 16:00 hasta las 17:55. No hay que crear otro.
El lanzador lee [codex.md](codex.md) en cada trabajo, con la corrección:
«MVP a las 16:00 en paralelo con Bacha y Dot; no esperes sus entregas.
Entrega en tu tarjeta y continúa con la siguiente propia. Objetivo antes
18:45 para cierre 19:00 e informe 19:30.»

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
