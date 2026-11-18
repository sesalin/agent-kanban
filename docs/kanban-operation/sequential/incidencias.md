# Incidencias y límites del montaje

Corte del 18 de noviembre de 2026.

## Registros listos sin archivo

La consulta de las tres tablas devolvió 26 paquetes en estado `ready` con
análisis `completed` y `muse_status=ready`. Nueve archivos existen; los otros
17 no están en `package_path/package_filename` de WSL:

| `event_id` |
| --- |
| `test-gobierno-nl-001` |
| `gobierno-nl-20260928-ponte-nuevo-c5-40k` |
| `regulacion-federal-2026-09-28-se-reglas-comercio-exterior-5799697` |
| `gobierno-nl-20260929-nlinea-9-tramites-economia-educacion` |
| `regulacion-federal-2026-09-30-dof-5799963` |
| `gobierno-nl-20260930-micromovilidad-mesa-trabajo` |
| `compras-publicas-20260930-banjercito-n51-fallo-desierto` |
| `regulacion-federal-2026-10-01-velagro-aguacate-cla` |
| `gobierno-nl-2026-10-01-sedra-manual-procesos` |
| `compras-publicas-20261001-asipona-lc-n142` |
| `gobierno-nl-2026-10-02-fraude-inmobiliario-ircnl-3dias` |
| `regulacion-federal-2026-10-02-nom-em-008-asea-2026` |
| `regulacion-federal-20261002-rmf3-aguacate-deducibilidad` |
| `regulacion-federal-20261005-nom-em-009-asea-2026` |
| `compras-publicas-20261001-nl-as400-desierta` |
| `regulacion-federal-20261006-fgr-saer` |
| `regulacion-federal-20261006-afac-circulares` |

El coordinador no crea tarjetas con esos ZIP ausentes. Durante la ventana de
admisión registra `source:<event_id>` en `factory_runtime`, espera una hora
antes de intentar de nuevo y continúa con otros registros. El informe incluye
la cantidad de incidencias de origen.

Recuperación: localizar el respaldo del ZIP y restaurarlo en la ruta registrada,
o pedir al analizador correspondiente que regenere el paquete sobre el mismo
evento. Comprobar el archivo y sus permisos antes de volver a admitirlo. El
registro `test-gobierno-nl-001` es de prueba: no restaurarlo como una oportunidad
comercial sin revisar su clasificación. No se borraron ni reclasificaron esos
registros y no se rehízo investigación histórica durante este montaje.

## Activación de los Muse

Las herramientas de esta sesión administran n8n y Kanban, pero no crean ni
editan las tareas programadas de Brio/Bacha en Muse. El operador debe cargar
los archivos `brio.md` y `bacha.md`, sus tokens propios y los cinco arranques
diarios indicados. Hasta hacerlo, n8n puede preparar tarjetas pero esas
sesiones no se iniciarán automáticamente.

## Operación con demoras

Un trabajo reclamado puede superar su ventana. El siguiente Muse queda
bloqueado mientras la tarjeta esté en progreso. Si su arranque diario ya pasó,
la tarea espera su siguiente ventana; n8n no inicia otro LLM para recuperarla.
La exclusividad se comprueba sobre reclamos de Kanban, no sobre procesos
internos de la plataforma Muse. Respeta también la separación de sesiones en
la plataforma y termina la sesión anterior antes de iniciar otra.

## Entregables inválidos y recuperación

La API conserva el primer ZIP subido y rechaza sobrescribirlo. Un ZIP inválido
queda en revisión con el error del pipeline. El operador debe corregir el
archivo o recuperar la tarjeta explícitamente, conservando su trazabilidad.
No hay recuperación automática de reclamos abandonados para evitar dobles
trabajos.

## Informe, servicios y datos externos

Telegram puede duplicar un mensaje si el envío tuvo éxito y falló la
confirmación posterior. La clave diaria evita crear otro informe, pero no
puede deshacer un envío externo. Conserva `message_id` para la recuperación.
WSL debe estar encendido para Codex y Kanban. Una sesión de Codex vencida o una
aprobación rechazada por el CLI se registra en sus logs y requiere revisión.

La coordinación es determinista; la calidad de investigación y construcción
la revisan los agentes según sus instrucciones. La validación automática de
ZIP y JSON no sustituye una revisión semántica de los entregables.
