# Hermes como orquestador de Agent Kanban

Esta guía configura Hermes Agent en Windows para coordinar el proyecto **Kanban** (`project_id: 1`) con el servidor MCP de Agent Kanban, que corre en Docker Desktop con WSL. La identidad `hermes` tiene permiso para despachar, revisar y reasignar. Los workers habilitados son `codex`, `gemini`, `quoder`, `dot`, `brio` y `bacha`.

## 1. Conectar Hermes desde Windows

1. En el perfil que arranca Hermes, normalmente en `%USERPROFILE%\.hermes\.env`, agrega `HERMES_KANBAN_TOKEN=<valor>`. Toma únicamente ese valor del archivo privado `~/.config/agent-kanban/kk-agents.env` de WSL. El archivo de WSL reúne las credenciales de todos los agentes. Mantén el valor en el archivo privado de Hermes.
2. En el `config.yaml` del mismo perfil, agrega el servidor `kanban` dentro de `mcp_servers`. Si ya existe esa sección, agrega la entrada al bloque existente.
3. Reinicia el proceso de Hermes que usas para orquestar y ejecuta `hermes mcp test kanban` desde ese mismo perfil. La prueba de conexión descubre las herramientas. Después, pídele a Hermes que liste las tareas del proyecto 1 para comprobar también el Bearer.

```yaml
mcp_servers:
  kanban:
    url: "http://192.168.100.61:7331/mcp/"
    headers:
      Authorization: "Bearer ${HERMES_KANBAN_TOKEN}"
    tools:
      include:
        - list_tasks
        - dispatch_task
        - get_comments
        - post_comment
        - review_task
        - reassign_stalled_task
```

La IP es la de Windows, donde Docker publica el puerto en la LAN. Si Hermes corre como proceso nativo en ese mismo Windows, también puedes usar `http://127.0.0.1:7331/mcp/`. Esta conexión usa sólo el Bearer de Kanban. Hermes muestra las herramientas con nombres como `mcp_kanban_list_tasks`. [Configuración MCP de Hermes](https://hermes-agent.nousresearch.com/docs/reference/mcp-config-reference/) · [Prueba de conexión](https://hermes-agent.nousresearch.com/docs/guides/use-mcp-with-hermes/)

Si Hermes se mueve fuera de la LAN, usa `https://kk.okehc.com/mcp/` y suma las cabeceras `CF-Access-Client-Id` y `CF-Access-Client-Secret` con las variables `HERMES_CF_ACCESS_CLIENT_ID` y `HERMES_CF_ACCESS_CLIENT_SECRET` del mismo archivo privado. Consulta la [guía de despliegue](ficha-tecnica.md).

## 2. Coordinar tickets

Cada columna refleja el estado devuelto por una herramienta. La edición directa por `PATCH /api/tasks/{id}` requiere una sesión de usuario del tablero. Si Hermes recibe `403: task editing requires a user session`, debe usar la herramienta correspondiente al paso del flujo con su Bearer de orquestador.

| Transición | Quién la ejecuta | Herramienta MCP |
| --- | --- | --- |
| Crear en `ready` o `blocked` | Hermes | `dispatch_task` |
| De `ready` a `in_progress` | Worker autorizado | `claim_task` |
| Renovar la actividad de la tarea | Worker que la reclamó | `heartbeat_and_progress` |
| De `in_progress` a `review` | Worker que la reclamó | `submit_for_review` |
| De `review` a `done` o devolverla con feedback | Hermes | `review_task` |
| De `in_progress` a `ready` con nueva reserva tras 15 minutos de inactividad | Hermes | `reassign_stalled_task` |

| Acción | Herramienta | Argumentos de ejemplo |
| --- | --- | --- |
| Inspeccionar el proyecto | `list_tasks` | `{"project_id":1}` |
| Despachar trabajo | `dispatch_task` | `{"project_id":1,"title":"Validar respuestas del catálogo","description":"Comprueba los estados de error. Reporta qué verificaste y adjunta el PR o el resultado.","assigned_to":"codex","priority":"HIGH"}` |
| Consultar la cola de revisión | `list_tasks` | `{"project_id":1,"status":"review"}` |
| Leer comentarios | `get_comments` | `{"task_id":12}` |
| Pedir evidencia o dar contexto | `post_comment` | `{"task_id":12,"agent":"hermes","content":"Comparte el PR y cómo verificaste los casos de error."}` |
| Aprobar o devolver una entrega | `review_task` | `{"task_id":12,"verdict":"APPROVE","feedback":"Validé los estados de error y la evidencia."}` |
| Reasignar una tarea detenida | `reassign_stalled_task` | `{"task_id":12,"new_agent_name":"gemini"}` |

Usa el `id` devuelto por Kanban en lugar del `12` de los ejemplos. En el despacho, describe el resultado esperado, los criterios de aceptación y la evidencia que el worker debe entregar. Omite `assigned_to` si cualquier worker autorizado puede tomar la tarea. `assigned_to` es la reserva y `claimed_by` indica quién la reclamó. Las prioridades válidas son `URGENT`, `HIGH`, `MEDIUM` y `LOW`.

Cuando dos tareas deban ejecutarse en orden, despacha la primera y usa el ID devuelto en `dependencies` al despachar la segunda. Las dependencias deben pertenecer al proyecto 1. La segunda queda en `blocked` mientras alguna dependencia esté pendiente y pasa a `ready` cuando todas están en `done`.

Los workers reclaman, reportan heartbeat y envían la entrega a revisión. Hermes consulta `status: "review"` cuando le pidas revisar. Antes de decidir, contrasta la evidencia con los criterios del ticket. MCP expone los comentarios y campos del ticket como `pr_url`. El resumen y los artefactos enviados con `submit_for_review` también se guardan en el feed de progreso del tablero, que esta integración no expone como herramienta MCP. Si falta evidencia, pídela en un comentario. `APPROVE` mueve la tarea a `done`. `REJECT` registra el feedback y devuelve la tarea a `in_progress` si tiene dueño, o a `ready` si está libre.

Para detectar tareas detenidas, consulta `status: "in_progress"` y revisa `last_heartbeat_at`. Kanban acepta la reasignación tras 15 minutos de inactividad y deja el ticket en `ready` reservado al nuevo worker. Un ticket en `blocked` por dependencias sigue el flujo de desbloqueo.

## 3. Instrucción para pegar en Hermes

> Eres el orquestador del proyecto Kanban con ID 1. Usa el servidor MCP `kanban`. Cuando te pida planificar trabajo, revisa primero los tickets existentes y despacha tareas con un resultado, criterios de aceptación y evidencia esperada. Usa los IDs que devuelva Kanban para registrar dependencias. Deja que los workers reclamen y ejecuten sus tareas. Cuando te pida revisar, lista los tickets en `review`, comprueba la evidencia y aprueba o devuelve cada entrega con feedback concreto. Si falta evidencia, pídela en el ticket. Si una tarea en `in_progress` se queda sin heartbeat durante al menos 15 minutos y debe continuar, reasígnala a un worker habilitado. Reporta los IDs, el estado devuelto y los bloqueos. Si una llamada de despacho falla de forma ambigua, consulta primero si el ticket se creó antes de volver a enviarla.

## Comprobación rápida

- Si Hermes descubre herramientas pero listar tareas falla por autenticación, revisa que `HERMES_KANBAN_TOKEN` esté en el perfil activo y que la cabecera empiece por `Bearer `.
- Si Hermes falla en la comprobación preliminar del transporte aunque el endpoint MCP funcione, agrega `skip_preflight: true` en la entrada `kanban` y vuelve a probar. [Referencia de configuración MCP](https://hermes-agent.nousresearch.com/docs/reference/mcp-config-reference/)
- Si recibe `Invalid Host header` o hay un error de conexión, comprueba que el contenedor siga publicado en la IP privada de Windows y que el hostname usado esté en la configuración MCP de Kanban.

[Guía de workers](workers.md) · [Inventario](agentes.md)
