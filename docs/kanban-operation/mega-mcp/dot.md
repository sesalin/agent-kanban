# Dot — herramientas MCP para intercambio de ZIP

Contrato corregido el 19-11-2026: **tarjeta → ZIP a workspace de Dot →
desarrollo, análisis y pruebas propios → ZIP terminado a la tarjeta → revisión**.

Usa la conexión existente **obsidian-mcp**. El Bearer de Dot permanece en el
servidor. Proyecto 1, worker `dot`. El horario se conserva a las 16:00,
America/Mexico_City. Codex solo tiene su rama independiente de MVP; no hace
el desarrollo de la landing ni recibe el workspace de Dot.

[Prompt completo y programación para entregar a Dot](../sequential/dot.md).

## Herramientas actuales

| Herramienta | Función |
| --- | --- |
| `factory_dot_status()` | Verifica identidad y acceso, sin revelar secretos. |
| `factory_dot_list_tasks()` | Lista hasta 20 tarjetas propias listas por prioridad. |
| `factory_dot_get_task(task_id)` | Lee la tarjeta y sus metadatos. |
| `factory_dot_claim_task(task_id)` | Reclama; Kanban aplica permisos y horarios. |
| `factory_dot_heartbeat(task_id, notes)` | Mantiene el reclamo y registra progreso. |
| `factory_dot_download_input(task_id)` | Ofrece el ZIP completo como recurso binario MCP, junto con tamaño y SHA-256. El cliente lo descarga al workspace de Dot. |
| `factory_dot_list_input_files(task_id, archive="")` | Consulta opcional del contenido; permite inspeccionar research.zip anidado. |
| `factory_dot_read_input_file(task_id, path, archive="", start_line=1, max_lines=160)` | Consulta opcional de texto de entrada; no es el mecanismo de desarrollo. |
| `factory_dot_upload_result(task_id, file)` | Recibe el archivo ZIP que Dot ya creó y probó en su workspace; lo guarda mediante la API de su tarjeta. |
| `factory_dot_submit_review(task_id, summary)` | Tras subida confirmada envía la tarjeta a revisión. |

Se retiraron las herramientas `factory_dot_write_output_file`,
`factory_dot_read_output_file` y `factory_dot_publish_result`, que promovían
construir archivos y armar el ZIP en el servidor. Refresca la conexión MCP
para que Dot vea el catálogo nuevo; no uses sus descripciones anteriores.

## Transferencia binaria

La descarga devuelve `resource_link`, MIME `application/zip`, con URI:

`mcp-file://factory-dot/tasks/<task_id>/landing-input.zip`

El mismo servidor resuelve `resources/read` de esa URI con bytes del ZIP,
comprobando de nuevo tarjeta, identidad y reclamo. El cliente debe guardar
el archivo en su workspace y verificar su hash. La URI no es una URL web
pública ni una ruta del filesystem local del agente.

La subida declara `_meta["openai/fileParams"] = ["file"]`. El host convierte
el archivo local a `{download_url, file_id, mime_type?, file_name?}`. El
servidor descarga el ZIP sin credenciales de Kanban, comprueba límites,
rutas internas, checksum y README.md, y envía los bytes originales con PUT
al resultado de la tarjeta. No recibe un path arbitrario del host del MCP y
no extrae ni ejecuta el proyecto. El límite de salida es 10 MiB comprimidos,
100 MiB descomprimidos y 2000 entradas; admite recursos binarios y frameworks.

El destino continúa siendo `<event_id>/06_landing/landing.zip` bajo la raíz
privada de paquetes. `.dot-transfer/task-<id>/uploaded.json` es solo el recibo
con hash, bytes y vínculo de tarjeta. No se sobrescribe un resultado existente.
Si la comunicación se corta después de aceptar el PUT y antes de guardar el
recibo, puede aparecer 409; el operador debe verificar la entrega antes de
reintentar. No se borran archivos para resolver ese conflicto automáticamente.

[Entrada nativa de archivos: documentación oficial](https://developers.openai.com/plugins/reference#define-file-inputs).
[Recursos binarios y enlaces: especificación MCP](https://modelcontextprotocol.io/specification/2025-06-18/server/resources).

## Qué está validado

Dot ya confirmó acceso al proyecto 1 con su identidad desde obsidian-mcp.
El servidor corregido se probó con ZIP completos, recursos binarios y entrada
nativa de archivos, incluido el SDK 1.12.4 de la imagen desplegada. Las pruebas
usan datos temporales, sin reclamar tarjetas de producción.

**Pendiente:** después de refrescar el catálogo, Dot debe confirmar desde su
propio cliente la materialización del ZIP y la entrega de un archivo de su
workspace. Esa capacidad pertenece también al host de Dot y no puede
acreditarse solo con una prueba del servidor.
