# Bacha como orquestador de Agent Kanban

Bacha coordina el proyecto **Kanban** (`project_id: 1`). Tiene permiso para despachar, revisar y reasignar. Los workers son `codex`, `gemini`, `quoder`, `dot` y `brio`.

## 1. Conexión por REST o MCP

**REST funciona aunque el cliente carezca de MCP.** Para REST usa `KANBAN_LAN_URL` desde la LAN o `KANBAN_URL` por HTTPS público. En ambos casos envía `Authorization: Bearer <BACHA_KANBAN_TOKEN>`. Por HTTPS público también envía `CF-Access-Client-Id` y `CF-Access-Client-Secret` con los valores `BACHA_CF_ACCESS_CLIENT_ID` y `BACHA_CF_ACCESS_CLIENT_SECRET`.

| Acción | REST | Cuerpo o parámetros |
| --- | --- | --- |
| Consultar pendientes de revisión | `GET /api/tasks?project_id=1&status=review` | Sin cuerpo |
| Despachar | `POST /api/tasks/dispatch` | `{"project_id":1,"title":"Verificar catálogo","assigned_to":"codex","priority":"HIGH","dependencies":[]}` |
| Leer evidencia del feed | `GET /api/tasks/{id}/progress` | Sin cuerpo |
| Leer o añadir comentarios | `GET` o `POST /api/tasks/{id}/comments` | Para POST, `{"author":"bacha","content":"Adjunta evidencia"}` |
| Revisar | `POST /api/tasks/{id}/review` | `{"verdict":"APPROVE","feedback":"Verificado"}`. También acepta `REJECT`. |
| Reasignar | `POST /api/tasks/{id}/reassign` | `{"new_agent_name":"gemini"}` |

Ejemplo desde la LAN, con el Bearer disponible en el entorno de Bacha:

```bash
curl -fsS -H "Authorization: Bearer ${BACHA_KANBAN_TOKEN}" \
  "${KANBAN_LAN_URL}/api/tasks?project_id=${KANBAN_PROJECT_ID}&status=review"
```

Si el cliente de Bacha admite **MCP Streamable HTTP**, usa `KANBAN_LAN_MCP_URL` o `KANBAN_MCP_URL` con las mismas cabeceras según la red. Ejemplo LAN para clientes con configuración tipo `mcpServers`:

```json
{
  "mcpServers": {
    "kanban": {
      "url": "http://192.168.100.61:7331/mcp/",
      "headers": {
        "Authorization": "Bearer <BACHA_KANBAN_TOKEN>"
      }
    }
  }
}
```

Configura el valor con el mecanismo de secretos del cliente. Confirma el acceso con `list_tasks({"project_id":1})`. Consulta la [tabla de variables](agentes.md#qué-pasar-a-cada-agente).

## 2. Coordinar tickets

Cada columna refleja el estado devuelto por una herramienta. La edición directa por `PATCH /api/tasks/{id}` requiere una sesión de usuario del tablero. Si Bacha recibe `403: task editing requires a user session`, debe usar la operación de flujo correspondiente en REST o MCP con su Bearer de orquestador.

| Transición | Quién la ejecuta | Herramienta MCP |
| --- | --- | --- |
| Crear en `ready` o `blocked` | Bacha | `dispatch_task` |
| De `ready` a `in_progress` | Worker autorizado | `claim_task` |
| Renovar la actividad de la tarea | Worker que la reclamó | `heartbeat_and_progress` |
| De `in_progress` a `review` | Worker que la reclamó | `submit_for_review` |
| De `review` a `done` o devolverla con feedback | Bacha | `review_task` |
| De `in_progress` a `ready` con nueva reserva tras 15 minutos de inactividad | Bacha | `reassign_stalled_task` |

| Acción | Herramienta | Argumentos de ejemplo |
| --- | --- | --- |
| Inspeccionar el proyecto | `list_tasks` | `{"project_id":1}` |
| Despachar trabajo | `dispatch_task` | `{"project_id":1,"title":"Validar respuestas del catálogo","description":"Comprueba los estados de error. Reporta qué verificaste y adjunta el PR o el resultado.","assigned_to":"codex","priority":"HIGH"}` |
| Consultar la cola de revisión | `list_tasks` | `{"project_id":1,"status":"review"}` |
| Leer comentarios | `get_comments` | `{"task_id":12}` |
| Pedir evidencia o dar contexto | `post_comment` | `{"task_id":12,"agent":"bacha","content":"Comparte el PR y cómo verificaste los casos de error."}` |
| Aprobar o devolver una entrega | `review_task` | `{"task_id":12,"verdict":"APPROVE","feedback":"Validé los estados de error y la evidencia."}` |
| Reasignar una tarea detenida | `reassign_stalled_task` | `{"task_id":12,"new_agent_name":"gemini"}` |

Usa el `id` devuelto por Kanban en lugar del `12` de los ejemplos. En el despacho, describe el resultado esperado, los criterios de aceptación y la evidencia que el worker debe entregar. Omite `assigned_to` si cualquier worker autorizado puede tomar la tarea. `assigned_to` es la reserva y `claimed_by` indica quién la reclamó. Las prioridades válidas son `URGENT`, `HIGH`, `MEDIUM` y `LOW`.

Cuando dos tareas deban ejecutarse en orden, despacha la primera y usa el ID devuelto en `dependencies` al despachar la segunda. Las dependencias deben pertenecer al proyecto 1. La segunda queda en `blocked` mientras alguna dependencia esté pendiente y pasa a `ready` cuando todas están en `done`.

Los workers reclaman, reportan heartbeat y envían la entrega a revisión. Bacha consulta `status: "review"` cuando le pidas revisar. Antes de decidir, contrasta la evidencia con los criterios del ticket. MCP expone los comentarios y campos del ticket como `pr_url`. El resumen y los artefactos enviados con `submit_for_review` también se guardan en el feed de progreso del tablero, que esta integración no expone como herramienta MCP. Si falta evidencia, pídela en un comentario. `APPROVE` mueve la tarea a `done`. `REJECT` registra el feedback y devuelve la tarea a `in_progress` si tiene dueño, o a `ready` si está libre.

Para detectar tareas detenidas, consulta `status: "in_progress"` y revisa `last_heartbeat_at`. Kanban acepta la reasignación tras 15 minutos de inactividad y deja el ticket en `ready` reservado al nuevo worker. Un ticket en `blocked` por dependencias sigue el flujo de desbloqueo.

## 3. Instrucción para pegar en Bacha

> Eres el orquestador del proyecto Kanban con ID 1. Usa el servidor MCP `kanban`. Cuando te pida planificar trabajo, revisa primero los tickets existentes y despacha tareas con un resultado, criterios de aceptación y evidencia esperada. Usa los IDs que devuelva Kanban para registrar dependencias. Deja que los workers reclamen y ejecuten sus tareas. Cuando te pida revisar, lista los tickets en `review`, comprueba la evidencia y aprueba o devuelve cada entrega con feedback concreto. Si falta evidencia, pídela en el ticket. Si una tarea en `in_progress` se queda sin heartbeat durante al menos 15 minutos y debe continuar, reasígnala a un worker habilitado. Reporta los IDs, el estado devuelto y los bloqueos. Si una llamada de despacho falla de forma ambigua, consulta primero si el ticket se creó antes de volver a enviarla.

## Comprobación rápida

- Si el servidor responde `401`, comprueba que `BACHA_KANBAN_TOKEN` esté en el proceso de Bacha y que la cabecera empiece con `Bearer `.
- Si la URL pública devuelve una página o redirección de Cloudflare, revisa las dos cabeceras de Access. En la LAN se usa el Bearer de Kanban.
- Ante un error de conexión en LAN, comprueba la IP de Windows. Para MCP, esa IP y el puerto deben estar en los hosts permitidos.

[Guía de workers](workers.md) · [Inventario y variables](agentes.md)
