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

## Cambio del 19-11-2026 para la jornada del 20-11

- Se detectó que las ramas se despachaban en cadena, aunque ya existían tres
  posibles constructores. Se corrigieron coordinador, funciones SQL y horarios:
  MVP/Codex, prospección/Bacha y landing/Dot se habilitan juntas tras GO.
- No había construcciones creadas que reasignar: siete eventos estaban en
  EVALUATING (tarjetas 22–28 para Bacha) y tres en RESEARCH (19–21 para Brio).
  Las investigaciones 12–18 permanecen done. Se conservaron IDs y resultados.
- Dot tiene lectura/reclamo como worker del proyecto 1. Su puente de archivos
  limita lectura a la entrada de su tarjeta y escritura a su carpeta de landing;
  se verificaron rechazo de rutas externas, symlinks y tarjetas ajenas. El ZIP
  se publica en la misma tarjeta. Dot confirmó personalmente la conexión MCP.
- El fallo de relevo de Brio es operativo: la investigación se extendió sobre
  el turno de Bacha. Se ajustaron instrucciones: unas 30 min por tarjeta,
  sin nuevos reclamos después de 14:15 y objetivo de entrega 14:45. Fuentes
  inaccesibles se registran como lagunas, sin inventar datos. Un acumulado
  puede requerir varios días; el horario no garantiza vaciar toda la cola.
- Bacha debe entregar evaluaciones antes de 15:45 para que la conciliación
  de cinco minutos prepare las ramas antes de las 16:00. Un resultado tardío
  puede esperar al siguiente turno si su worker ya terminó por cola vacía.
- El cierre sigue condicionado a todas las ramas activas DONE. Una entrega
  ausente o inválida impide cerrar esa oportunidad; el informe de las 19:30
  muestra estados al corte, no afirma que todos los trabajos terminaron. Un
  cierre posterior no regenera el informe diario que ya fue enviado.
- Sigue pendiente cargar las nuevas programaciones externas de Bacha/Dot y
  comprobar una jornada real. El acceso interactivo de Dot no demuestra aún
  que su ejecución programada conserve las herramientas del plugin. Si su
  plataforma no permite tareas programadas con herramientas, el operador
  deberá iniciar ese turno; no se implementó otro despertador por eventos.

### Validación del cambio

Se verificaron 12 casos de Kanban/coordinador: ciclo completo con las tres
ramas reclamadas a la vez y entregas fuera de orden, NO_GO, idempotencia,
permisos SQL, horarios, exclusión Muse, informe desde las 19:30, orquestación
y API de paquetes. Se usó PostgreSQL temporal y archivos de prueba. No se
crearon pilotos ni se produjo trabajo por Brio, Bacha, Codex o Dot.

Las 17 comprobaciones de puente/HTTP de MegaMCP pasaron; cubren lectura,
escritura acotada, ZIP, publicación y revisión. La suite del intermediario
pasó. El primer intento de pruebas con sockets falló por el sandbox: se
repitieron solo los casos afectados con acceso al Postgres/socket temporal.
Hay avisos previos de deprecación de pytest-asyncio/AnyIO; no afectaron resultados.

Los workflows fueron validados, se verificaron conexiones y se publicaron.
Pruebas n8n 221 y 222 correctas con todos los nodos de red y Telegram
simulados: no enviaron mensajes ni cambiaron la base. El cron productivo 220
corrió después del despliegue con éxito y factory_runtime sin last_error.
La nueva función de ramas permite service_role y rechaza anon; la base
modificada fue exclusivamente radars-n8n / uobeshcvmtawjxibciuy.

## Corrección del contrato de Dot: workspace propio

El primer puente promovía escribir archivos individuales y empaquetar en el
host del MCP. El operador corrigió el requisito: Dot debe descargar la
entrada, realizar análisis/desarrollo/pruebas en su propio workspace y subir
el ZIP terminado. Se retiraron esas herramientas de escritura y se añadieron
factory_dot_download_input (recurso binario MCP) y factory_dot_upload_result
(archivo nativo con openai/fileParams). El servidor conserva los bytes de
la entrega, sin ejecutar ni reconstruir el proyecto. Codex no participa en
el desarrollo de Dot. Horarios, asignaciones y coordinación permanecen iguales.

Cinco pruebas del puente verificaron el contrato corregido, incluidas rutas,
permisos, binarios, hashes, reintentos, schema y metadata del archivo nativo.
Se comprobó también el intercambio en el SDK 1.12.4 real de la imagen sin
red ni secretos productivos. La imagen derivada conserva el dashboard anterior.

Falta validar desde el cliente de Dot el materializado real del recurso en
su workspace y la conversión de su archivo al parámetro nativo. Refrescar el
catálogo es necesario; no se debe declarar el flujo completo validado por
Dot basándose únicamente en la prueba del servidor. Si el cliente no admite
el recurso binario o la referencia de archivo, documentar el bloqueo exacto
antes de cambiar de transporte. No se crearon pilotos ni entregables reales
en nombre del agente.

## 20-11-2026: Dot #34, recurso de entrada no resuelto por su cliente

Dot confirmó su reclamo de la #34 y reportó que la descarga devolvía tamaño,
hash y una URI mcp-file://, pero resources/read fallaba con Unknown resource
(-32002) y no había ZIP en su workspace. Desde el conector del operador se
confirmó esa respuesta de referencia: entrada de 25 392 bytes y hash
876ec821cf68f393b6dbe4fc87f129d9c6bcc0b85cdb8fef792309bc2d80fb24.

La corrección entrega EmbeddedResource con bytes binarios en la respuesta
inicial, sin depender de una segunda resolución de esa URI y sin duplicar
el contenido en structuredContent. Se mantienen identidad, proyecto y
reclamo requeridos. La subida de resultado y los horarios no cambian.
No se crea trabajo por Dot ni se modifica el estado de la tarjeta para
resolver esta descarga. Sigue siendo necesaria su confirmación de que el
adjunto se materializa en su workspace y de que coincide tamaño/hash.

Verificación posterior al despliegue: el conector obsidian-mcp del operador
recibió el EmbeddedResource con blob binario, sin structuredContent duplicado.
Se decodificaron los 25 392 bytes y se verificaron SHA-256 y CRC del ZIP,
coincidentes con la entrada previa. Las cinco pruebas del puente pasaron,
así como el contrato binario/subida en el SDK 1.12.4 real. MegaMCP quedó
saludable con imagen mega-mcp-dot-bridge:20261120-inline. No se modificó el
estado ni se subió un resultado de la #34. Queda pendiente la confirmación
de Dot de que el adjunto se materializa en su workspace concreto.
