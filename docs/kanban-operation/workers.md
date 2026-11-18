# Workers · conexión y operación por MCP

La fábrica secuencial vigente, con horarios y prompts de Brio, Bacha y Codex, se documenta en [sequential/README.md](sequential/README.md). Sus entregas se concilian por cron, sin callbacks de los workers.


Un worker toma tickets disponibles en los proyectos autorizados, informa actividad y entrega evidencia para que el orquestador revise. En esta instalación el proyecto es **Kanban**, ID `1`. Usa únicamente el Bearer emitido para tu identidad. Consulta los nombres en el [inventario](agentes.md).

## Conectar el cliente

Consulta [qué variables entregar a cada agente](agentes.md#qué-pasar-a-cada-agente).

| Dónde corre el worker | URL Streamable HTTP | Cabeceras |
| --- | --- | --- |
| En el mismo Windows | `http://127.0.0.1:7331/mcp/` | `Authorization: Bearer <token-kanban>` |
| En otro equipo de la LAN | `http://192.168.100.91:7331/mcp/` | `Authorization: Bearer <token-kanban>` |
| Fuera de la LAN | `https://kk.okehc.com/mcp/` | Bearer de Kanban, `CF-Access-Client-Id` y `CF-Access-Client-Secret` del worker |

Ejemplo de configuración para clientes que aceptan `mcpServers`, URL y cabeceras. Usa el mecanismo de secretos de tu cliente para resolver los valores de ejemplo.

```json
{
  "mcpServers": {
    "kanban": {
      "url": "http://192.168.100.91:7331/mcp/",
      "headers": {
        "Authorization": "Bearer <TOKEN_KANBAN_DE_ESTE_WORKER>"
      }
    }
  }
}
```

El operador encuentra los valores en `~/.config/agent-kanban/kk-agents.env` en WSL. Por ejemplo, Codex usa `CODEX_KANBAN_TOKEN` y, si entra por HTTPS público, también `CODEX_CF_ACCESS_CLIENT_ID` y `CODEX_CF_ACCESS_CLIENT_SECRET`. Comparte con cada proceso sólo sus valores. Para verificar conexión y permisos, llama a `list_my_tasks` con `{"project_id":1}`. Una lista vacía es una respuesta válida cuando el worker carece de tickets reclamables.

## Procesar un ticket

| Paso | Herramienta | Argumentos de ejemplo |
| --- | --- | --- |
| Consultar disponibles | `list_my_tasks` | `{"project_id":1}` |
| Reclamar | `claim_task` | `{"task_id":12}` |
| Leer feedback | `get_comments` | `{"task_id":12}` |
| Consultar o dejar un enlace | `post_comment` | `{"task_id":12,"agent":"codex","content":"Evidencia: https://example.test/pull/25"}` |
| Reportar actividad | `heartbeat_and_progress` | `{"task_id":12,"notes":"Pruebas ejecutadas","git_branch":"codex/ticket-12","git_pr_url":"https://example.test/pull/25","git_commit_hash":"abc123"}` |
| Entregar a revisión | `submit_for_review` | `{"task_id":12,"summary_of_work":"Cambios y pruebas verificadas","artifacts":["https://example.test/pull/25"]}` |

1. Elige una tarea `ready` que esté abierta o reservada a tu nombre. Confirma que `claim_task` devolvió `ok: true` y `in_progress` antes de empezar. Si otro worker ganó el reclamo, vuelve a listar.
2. Ejecuta el trabajo en el repositorio indicado por el ticket. Mientras siga activo, informa avances con intervalos menores de 15 minutos. Si el ticket fue reasignado, el antiguo titular debe detener su trabajo sobre ese ticket.
3. Si necesitas señalar un bloqueo en el tablero, la herramienta `post_progress` del titular acepta `kind: "status_change"` con un `status` que indique `to: "blocked"`. Incluye el motivo y qué necesitas para continuar. Este bloqueo se reporta aparte de las dependencias automáticas entre tickets.
4. Adjunta resultados accesibles para el orquestador. Incluye el enlace del PR en `git_pr_url` o en un comentario para que Bacha pueda verlo por MCP. Indica qué se verificó, qué falló y qué queda pendiente. Las rutas locales en el feed pueden ser inaccesibles para otros hosts.
5. Entrega con `submit_for_review` y confirma `review`. Bacha aprueba a `done` o devuelve con feedback. Si la tarea vuelve a `in_progress` a tu nombre, lee los comentarios, corrige y vuelve a entregar.

Usa el ID real del ticket. Si una herramienta pide `agent`, pasa el nombre exacto del Bearer. La edición libre de columnas requiere una sesión humana. El flujo de un worker usa reclamo, progreso y entrega por MCP.

## Piloto ZIP de Brio

El intermediario acepta el Bearer propio de Brio en `https://kanban-api.okehc.com` para REST y en `https://kanban-api.okehc.com/mcp/` para MCP. Las cabeceras de Cloudflare se agregan del lado del intermediario. Las variables para el piloto están en el archivo local privado `~/.config/agent-kanban/brio-piloto.env`.

Bacha despacha la tarjeta con `metadata.muse_zip`, que contiene `path` relativo a la raíz de paquetes, `input_file` y `output_file`. El POST de despacho recibe `metadata` y la respuesta lo devuelve como `metadata_payload`. Verifica que aparezca `metadata_payload.muse_zip` antes de avisar al worker. La instalación sólo monta la carpeta de la prueba con datos sintéticos. La tarjeta vigente del piloto es la #8. Para operarla desde el canal de Brio, usa REST y un único Bearer:

| Paso | Operación | Resultado esperado |
| --- | --- | --- |
| Reclamar la tarjeta | `POST /api/tasks/8/claim` | `200`, `in_progress` |
| Descargar el ZIP de entrada | `GET /api/tasks/8/package/input` | `200` con `application/zip` |
| Subir hallazgos | `PUT /api/tasks/8/package/result` con `Content-Type: application/zip` y el ZIP binario como cuerpo | `201`, con nombre, tamaño y ruta del resultado |
| Entregar a revisión | `POST /api/tasks/8/submit` con JSON, `summary_of_work` y la URL de resultado en `artifacts` | `200`, `review` |

La carga admite hasta 10 MiB y la tarjeta debe seguir reclamada por Brio y en progreso. Si ya hay un ZIP de salida, la respuesta es `409`. Bacha puede descargar la entrega con su Bearer mediante `GET /api/tasks/8/package/result`.

## Instrucción para pegar en el agente

> Eres un worker de Kanban con tu propia identidad. Consulta el proyecto 1 con `list_my_tasks`. Selecciona una tarjeta cuyo `assigned_to` coincida con tu identidad. Reclama el ticket antes de trabajar y confirma que quedó a tu nombre. Reporta heartbeat y avances durante la ejecución. Pide aclaraciones en los comentarios del ticket. Cuando termines, incluye el resultado, las comprobaciones y evidencia accesible, y entrega con `submit_for_review`. Completa la notificación del workflow correspondiente y vuelve a consultar `list_my_tasks({"project_id":1})` para reclamar la siguiente tarjeta a tu nombre. Continúa hasta que esa cola quede vacía y entonces espera un nuevo aviso. Si Bacha devuelve la entrega, lee su feedback y vuelve a presentar el trabajo. Si pierdes el reclamo, detén el trabajo sobre ese ticket.

[Guía del orquestador](orquestador.md) · [Ficha técnica](ficha-tecnica.md)
