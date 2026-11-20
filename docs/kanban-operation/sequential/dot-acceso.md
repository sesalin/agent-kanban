> Actualización 19-11-2026: Dot ya validó su acceso mediante obsidian-mcp.
> Su conexión vigente está descrita en [dot.md](dot.md). No necesita cargar
> un Bearer en el chat ni configurar OAuth. El texto siguiente conserva el
> contexto del diagnóstico anterior, no instrucciones de conexión actuales.

# Dot — validación inicial de acceso

**Ruta vigente para Dot:** [MegaMCP ya conectado](../mega-mcp/dot.md). El puente guarda su credencial en el servidor. El procedimiento de Bearer directo de abajo queda como referencia para clientes que lo admiten.


Dot será el constructor de landing. Este documento cubre la prueba de acceso;
el coordinador aún conserva el reparto secuencial anterior. No programes ni
reclames trabajo de landing hasta que se complete el cambio de reparto.

## Bloqueo del cliente de Dot

El cliente reportó que no ofrece un campo para guardar un Bearer de API, tanto
en web como en la aplicación de Windows. El MCP actual y el intermediario
aceptan tokens estáticos; no implementan un flujo OAuth de vinculación. Las
pruebas del operador demuestran acceso del servidor, pero no completan la
conexión del cliente de Dot.

Para conectar el MCP mediante OAuth hace falta implementar descubrimiento,
autorización y canje de tokens, y vincular el acceso autorizado a la identidad
`dot`, worker del proyecto 1. Es un cambio pendiente, no una función disponible
actualmente. El login del tablero no equivale a esa vinculación. Los pasos de
Bearer de abajo solo sirven en clientes que permiten configurarlo.

[Autenticación MCP de ChatGPT: documentación oficial](https://developers.openai.com/plugins/build/auth).

## Datos de conexión

| Dato | Valor |
| --- | --- |
| Identidad | `dot` |
| Rol | `worker` |
| Proyecto | `1` |
| MCP Streamable HTTP | `https://kanban-api.okehc.com/mcp/` |
| REST base | `https://kanban-api.okehc.com` |
| Credencial | `DOT_KANBAN_TOKEN`, del archivo privado `~/.config/agent-kanban/dot.env` |

El archivo privado contiene solo la configuración de Dot para el intermediario.
No contiene secretos de los demás agentes ni las credenciales de Cloudflare.
Los campos de un cliente que pide **Access Token / API key** reciben el token
sin prefijo. Si el cliente pide una cabecera, usa
`Authorization: Bearer <DOT_KANBAN_TOKEN>`.

## Mensaje para entregar a Dot

```text
Eres Dot y vas a encargarte de construir las landing de nuestra fábrica de oportunidades.
Primero valida únicamente tu conexión; todavía no inicies trabajo ni programes ejecuciones.

Identidad: dot. Rol: worker. Proyecto Kanban: 1.
MCP Streamable HTTP: https://kanban-api.okehc.com/mcp/
REST base: https://kanban-api.okehc.com
Usa exclusivamente tu credencial privada DOT_KANBAN_TOKEN como Bearer.
Si el formulario pide solo Access Token, pega el valor sin la palabra Bearer.
No necesitas cabeceras adicionales de Cloudflare. No muestres el token en tu respuesta.

Prueba desde tu propio canal:
1. Inicializa el MCP y lista sus herramientas. Confirma que puedes ver list_my_tasks, claim_task, heartbeat_and_progress y submit_for_review.
2. Ejecuta list_my_tasks({"project_id":1}). Una lista vacía es un resultado válido: todavía no te hemos asignado una tarjeta de landing.
3. Si puedes hacer REST, consulta GET https://kanban-api.okehc.com/api/tasks/available?project_id=1 con Authorization: Bearer <tu credencial>. Debe responder HTTP 200 y JSON, no HTML ni un formulario de acceso. Usa User-Agent: Dot-Kanban/1.0 si tu cliente permite configurarlo.
4. En el resultado identifica solamente las tarjetas cuyo assigned_to sea dot. No reclames tarjetas de otros agentes ni las que estén sin asignar.
5. No crees, modifiques, comentes, reclames ni cierres tarjetas durante esta validación. No uses tokens ajenos ni cambies configuraciones del servidor.

Devuelve un reporte breve: MCP conectado o error exacto, herramientas comprobadas, resultado de list_my_tasks, código HTTP y tipo de contenido de REST si lo probaste, e IDs de tarjetas asignadas a dot. Distingue lo que ejecutaste tú de lo que te hayan reportado otros. Si algo falla, indica el paso y el error sin repetir intentos en bucle.
```

No se necesita una tarjeta de prueba para comprobar esta conexión. La
validación de reclamo, ZIP y entrega se realizará después, sobre la tarjeta
que se asigne para ese fin. Una consulta vacía no valida esas operaciones.

## Comprobaciones del operador

El 19 de noviembre se comprobó, sin crear ni reclamar tarjetas:

- Token y Service Token existentes válidos contra el origen protegido.
- Permiso de Dot: worker, proyecto 1, lectura y reclamo habilitados.
- Intermediario actualizado para Dot, con los mismos límites REST de los workers.
- MCP initialize HTTP 200, listado de 17 herramientas y consulta `list_my_tasks` del proyecto 1 sin error.
- REST de tareas disponibles HTTP 200 con JSON; no había tarjetas asignadas a Dot.
- Bacha conservó acceso REST HTTP 200 después del despliegue.
- Pruebas del intermediario correctas, incluyendo Dot en la cola, reclamo y rechazo de despacho y operaciones de archivos de fábrica.

Estas comprobaciones se hicieron desde el canal del operador. Falta el reporte
de Dot desde su propio entorno y no se ha probado todavía una entrega de landing.
