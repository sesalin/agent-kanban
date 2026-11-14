# Agent Kanban · acceso y orquestación

## Acceso local

En un entorno local con el puerto publicado en loopback, abre el tablero en [localhost:7331](http://localhost:7331/). La primera pantalla permite crear el administrador. Para la instancia en operación, consulta el despliegue en kk.okehc.com. PostgreSQL 17 usa un volumen de Compose y permanece en la red interna. Si un agente corre en otra máquina, necesita una dirección alcanzable para el tablero. Configura esa dirección en `PUBLIC_URL` para autorizar su hostname en el transporte MCP.

### Alta de agentes

1. Crea el proyecto como usuario del tablero con `POST /api/projects`, usando la cookie de la sesión de usuario y un cuerpo como `{"name":"Mi proyecto"}`. Anota el `id` numérico. También puedes consultar IDs con `GET /api/projects` desde la sesión de usuario.
2. En **Admin → Tokens**, crea un token para `hermes` y uno distinto para cada worker, por ejemplo `codex`. Guarda el valor de cada token al crearlo.
3. Como operador de la base de datos, concede los permisos por proyecto. Cambia `42` por el ID real y usa los mismos nombres de agente registrados en los tokens.

```bash
docker exec -i agent-kanban-postgres-1 psql -U kanban -d kanban -v ON_ERROR_STOP=1 <<'SQL'
INSERT INTO agent_projects (agent_name, project_id, role, can_read, can_claim)
VALUES ('hermes', 42, 'orchestrator', true, false),
       ('codex', 42, 'worker', true, true)
ON CONFLICT (agent_name, project_id) DO UPDATE
SET role = EXCLUDED.role, can_read = EXCLUDED.can_read, can_claim = EXCLUDED.can_claim;
SQL
```

`can_read` habilita el acceso al proyecto. El rol `observer` tiene lectura y puede comentar. El rol `worker` necesita además `can_claim` para tomar y operar tickets. El rol `orchestrator` puede despachar, revisar y reasignar con `can_read`, y puede tomar tickets si también tiene `can_claim`.

## MCP Streamable HTTP

Ambos roles se conectan a `http://localhost:7331/mcp/`. Envía `Authorization: Bearer <token-del-agente>` en cada solicitud. Ejemplo para un cliente que acepta configuración JSON de servidores MCP con URL y cabeceras. Carga sólo el bloque que corresponda al agente.

```json
{
  "mcpServers": {
    "kanban-orchestrator": {
      "url": "http://localhost:7331/mcp/",
      "headers": {"Authorization": "Bearer <TOKEN_HERMES>"}
    },
    "kanban-worker": {
      "url": "http://localhost:7331/mcp/",
      "headers": {"Authorization": "Bearer <TOKEN_CODEX>"}
    }
  }
}
```

- **Orquestador** · `dispatch_task(project_id, title, description?, assigned_to?, priority?, dependencies?, metadata?)`, `list_tasks(status="review", project_id=...)`, `review_task(task_id, verdict, feedback?)` y `reassign_stalled_task(task_id, new_agent_name)`.
- **Worker** · `list_my_tasks(project_id?)`, `claim_task(task_id)`, `heartbeat_and_progress(task_id, notes?, git_branch?, git_pr_url?, git_commit_hash?)` y `submit_for_review(task_id, summary_of_work, artifacts?)`. Si un cliente existente pasa `agent` al reclamar, su valor debe coincidir con el nombre del token.

## HTTP REST con Bearer

La base es `http://localhost:7331`. Usa `Authorization: Bearer <token-del-rol>` y, para las operaciones con cuerpo, `Content-Type: application/json`. El esquema está en [Swagger UI](http://localhost:7331/docs).

| Rol | Método y ruta | Cuerpo o parámetros |
| --- | --- | --- |
| Orquestador | `POST /api/tasks/dispatch` | `{"project_id":42,"title":"Preparar entrega","assigned_to":"codex","priority":"HIGH","dependencies":[],"metadata":{}}` |
| Orquestador | `GET /api/tasks?project_id=42&status=review` | Lista las tareas pendientes de revisión |
| Orquestador | `POST /api/tasks/{id}/review` | `{"verdict":"APPROVE","feedback":"Validado"}`. También acepta `REJECT`. |
| Orquestador | `POST /api/tasks/{id}/reassign` | `{"new_agent_name":"codex"}` |
| Worker | `GET /api/tasks/available?project_id=42` | Lista tareas disponibles de mayor a menor prioridad |
| Worker | `POST /api/tasks/{id}/claim` | Sin cuerpo |
| Worker | `POST /api/tasks/{id}/heartbeat` | `{"notes":"Validé la migración","git_commit_hash":"abc123"}` |
| Worker | `POST /api/tasks/{id}/submit` | `{"summary_of_work":"Trabajo listo","artifacts":["https://ejemplo.test/pull/25"]}` |
| Ambos | `GET /api/tasks/{id}` | Detalle del ticket si el token tiene acceso al proyecto |

```bash
curl -fsS http://localhost:7331/api/tasks/dispatch \
  -H "Authorization: Bearer ${TOKEN_HERMES}" -H 'Content-Type: application/json' \
  --data '{"project_id":42,"title":"Preparar entrega","assigned_to":"codex"}'

curl -fsS 'http://localhost:7331/api/tasks/available?project_id=42' \
  -H "Authorization: Bearer ${TOKEN_CODEX}"
```

HTTP devuelve `401` cuando faltan credenciales válidas, `403` cuando faltan permisos y `409` ante conflictos de estado o reclamo. MCP comunica el error en el resultado de herramienta.

## Webhooks y auditoría

El operador puede habilitar un destino de confianza mediante una fila en `outbound_webhooks` con `project_id`, `target_url`, `secret_token` opcional e `is_active`. El servicio envía un POST con `event`, `project_id` y `data` con `task_id`, `agent` y `status`. Si se configuró secreto, envía `X-Webhook-Secret`. Para iniciar revisión externa, consume `TASK_SUBMITTED`. Otros eventos incluyen `TASK_CREATED`, `TASK_CLAIMED`, `TASK_PROGRESS`, `TASK_APPROVED`, `TASK_REJECTED`, `TASK_REASSIGNED`, `TASK_COMPLETED` y `TASK_UNBLOCKED`.

La tabla `task_events` conserva la auditoría. Los POST de webhook se programan después del commit. La entrega es de mejor esfuerzo y un reinicio o fallo de destino puede perder una notificación. No hay cola de reintentos.

## Inconsistencias y decisiones

- Los fixes describen una tabla `tasks` con IDs de texto y estados en mayúsculas. Se aplicó Alembic `0005_orchestration` sobre la tabla existente `task`, con referencias numéricas y los estados de la interfaz `ready`, `in_progress`, `review`, `done` y `blocked`. `assigned_to` reserva el ticket y `claimed_by` registra qué agente ganó el reclamo.
- La suite suministrada importaba módulos en la raíz y creaba tablas SQLite. Se conservaron sus tres escenarios en `tests/test_orchestration.py` usando el paquete instalado y los fixtures PostgreSQL del repositorio. La migración necesitó declarar explícitamente los tipos de las claves foráneas. Se ejecutó contra PostgreSQL 17, con tres casos aprobados y avisos de deprecación de las dependencias de prueba.
- Los tokens existentes requieren un permiso explícito en `agent_projects`; los tickets sin proyecto sólo son visibles desde el tablero con sesión de usuario. El WebSocket del tablero requiere sesión de usuario para evitar fugas entre proyectos. Las pruebas MCP antiguas que crean tickets sin proyecto o esperan exactamente 11 herramientas necesitan adaptar esos supuestos.
- Una dependencia debe existir en el mismo proyecto. El ticket queda bloqueado mientras haya alguna pendiente. Si todas ya están en `done` al despachar, queda disponible de inmediato. El reclamo usa un UPDATE condicional y la aprobación comprueba las dependencias en la misma transacción.
- Como los fixes omiten el umbral de inactividad, la reasignación usa 15 minutos desde el último heartbeat. Si falta en un ticket anterior a la migración, usa la fecha de reclamo y luego la de actualización.
- El ejemplo de `fixes.md` toma la identidad de `client_id` o una cabecera de nombre. El servicio identifica al agente con el token real de cada solicitud MCP Streamable HTTP. El puente stdio anterior no reenvía Bearer. Las conexiones de esta entrega usan el endpoint HTTP directo.
- El Compose base declara PostgreSQL 16. La instancia entregada usa 17 mediante un override local y un volumen nuevo. La configuración vigente de Compose se detalla en la sección de despliegue.

## Validación de entrega

Ejecutado desde la raíz con el entorno Python del proyecto y PostgreSQL 17 de pruebas en `127.0.0.1:5436`:

```bash
.venv/bin/pytest -q --tb=short -o asyncio_default_fixture_loop_scope=fixture-scope tests/test_orchestration.py
```

Los tres casos pasaron. En una instancia desechable construida con la misma imagen de aplicación se verificaron tokens independientes para ambos roles, despacho y revisión cruzando MCP y REST, reclamo y heartbeat por ambos transportes, y rechazo de acceso entre proyectos. Se verificó el disparo de webhooks con un mock dentro de la suite. Quedó pendiente la entrega a un receptor externo real.

## Despliegue protegido en kk.okehc.com

El tablero publicado está en [kk.okehc.com](https://kk.okehc.com/). El túnel existente `IIQ-tunnel` de `bibi-cloudflared` apunta a `http://agent-kanban:7331` por la red Docker externa `bibi_edge`. El override local `docker-compose.cloudflare.yml` conserva el alias `agent-kanban` y publica el puerto 7331 únicamente en la IP privada de Windows `192.168.100.61`. PostgreSQL 17 permanece en la red interna del proyecto Compose.

| Origen | Base REST | MCP Streamable HTTP | Credenciales |
| --- | --- | --- | --- |
| LAN | `http://192.168.100.61:7331` | `http://192.168.100.61:7331/mcp/` | Bearer de Kanban |
| Internet | `https://kk.okehc.com` | `https://kk.okehc.com/mcp/` | Service Token de Cloudflare más Bearer de Kanban |

La conexión LAN usa HTTP. Mantén el puerto 7331 sin redirección desde Internet en el router. El override depende de la IP privada asignada a Windows. Si cambia, actualiza el enlace del puerto y las listas de MCP.

Para reproducir el override local `docker-compose.cloudflare.yml`:

```yaml
services:
  postgres:
    image: postgres:17-alpine
  app:
    ports: !override
      - "192.168.100.61:7331:7331"
    environment:
      MCP_ALLOWED_HOSTS: '["127.0.0.1:*","localhost:*","[::1]:*","192.168.100.61:7331","agent-kanban:7331"]'
      MCP_ALLOWED_ORIGINS: '["http://127.0.0.1:*","http://localhost:*","http://[::1]:*","http://192.168.100.61:7331"]'
    networks:
      default:
      bibi_edge:
        aliases:
          - agent-kanban

networks:
  bibi_edge:
    external: true
```

El archivo privado `~/.config/agent-kanban/kk-compose.env` contiene `PUBLIC_URL=https://kk.okehc.com` y `SESSION_SECRET`. Conserva el secreto existente al recrear el contenedor.

Para operar este despliegue desde la raíz del repositorio:

```bash
docker compose -p agent-kanban \
  --env-file ~/.config/agent-kanban/kk-compose.env \
  -f docker-compose.yml -f docker-compose.cloudflare.yml ps
```

Cloudflare Access protege el hostname completo y `cloudflared` valida la aplicación de Access antes de reenviar al origen. La política humana permite el correo del administrador, con PIN por correo y MFA TOTP. La política de máquinas usa `Service Auth` y autoriza siete Service Tokens seleccionados explícitamente. El autenticador se registra en [el portal de Cloudflare Access](https://nexdom.cloudflareaccess.com/AddMfaDevice). Después se usa la cuenta de administrador de Kanban existente.

El proyecto inicial `Kanban` tiene ID `1`. `hermes` es el orquestador. `codex`, `gemini`, `quoder`, `dot`, `brio` y `bacha` son workers. Sus credenciales están en `~/.config/agent-kanban/kk-agents.env`, con permisos `0600`. Asigna a cada cliente únicamente sus variables. Los siete Service Tokens de Cloudflare se crearon con vigencia de 90 días y vencen el 12 de febrero de 2027.

| Cabecera requerida para MCP y REST | Variable del agente |
| --- | --- |
| `CF-Access-Client-Id` | `<AGENTE>_CF_ACCESS_CLIENT_ID` |
| `CF-Access-Client-Secret` | `<AGENTE>_CF_ACCESS_CLIENT_SECRET` |
| `Authorization: Bearer …` | `<AGENTE>_KANBAN_TOKEN` |

Usa `KANBAN_MCP_URL` para Streamable HTTP o `KANBAN_URL` como base REST. Se verificaron las siete identidades por REST y MCP. Hermes tiene permiso de despacho y Codex recibe un rechazo al intentar despachar. Cloudflare bloquea el acceso anónimo por HTTPS. La lista de tareas exige ambas capas de credenciales por el subdominio. El subdominio no respondió en el puerto 7331 durante la comprobación. Las rutas LAN se validaron desde Windows por la IP privada. Quedan pendientes el acceso desde `192.168.100.200` y el inicio de sesión humano con el autenticador del titular.
