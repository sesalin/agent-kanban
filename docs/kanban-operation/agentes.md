# Inventario de agentes de Kanban

Permisos verificados en PostgreSQL el 17 de noviembre de 2026. Las seis identidades tienen un token emitido en Kanban. La asignación de proyecto permite operar sobre el proyecto indicado. Los tickets individuales se reservan o reclaman por separado.

| Agente | Proyecto | ID | Rol en Kanban | Puede leer | Puede reclamar |
| --- | --- | --- | --- | --- | --- |
| `bacha` | Kanban | 1 | `orchestrator` | Sí | No |
| `brio` | Kanban | 1 | `worker` | Sí | Sí |
| `codex` | Kanban | 1 | `worker` | Sí | Sí |
| `dot` | Kanban | 1 | `worker` | Sí | Sí |
| `gemini` | Kanban | 1 | `worker` | Sí | Sí |
| `quoder` | Kanban | 1 | `worker` | Sí | Sí |

La lista indica identidades configuradas. La disponibilidad del proceso de cada agente varía con su host. Los valores de las credenciales se administran en el archivo privado descrito en la [ficha técnica](ficha-tecnica.md).

## Qué pasar a cada agente

El archivo privado en WSL es `~/.config/agent-kanban/kk-agents.env`. Comparte únicamente las variables de la fila que corresponda y la URL del método elegido.

| Método y red | Variable de URL | Credenciales |
| --- | --- | --- |
| REST por LAN | `KANBAN_LAN_URL` | Bearer de Kanban |
| MCP por LAN | `KANBAN_LAN_MCP_URL` | Bearer de Kanban |
| REST por Internet | `KANBAN_URL` | Bearer de Kanban y el par de Cloudflare |
| MCP por Internet | `KANBAN_MCP_URL` | Bearer de Kanban y el par de Cloudflare |

| Agente | Siempre para autenticar en Kanban | Adicionales sólo vía Cloudflare |
| --- | --- | --- |
| Bacha | `BACHA_KANBAN_TOKEN` | `BACHA_CF_ACCESS_CLIENT_ID`, `BACHA_CF_ACCESS_CLIENT_SECRET` |
| Brio | `BRIO_KANBAN_TOKEN` | `BRIO_CF_ACCESS_CLIENT_ID`, `BRIO_CF_ACCESS_CLIENT_SECRET` |
| Codex | `CODEX_KANBAN_TOKEN` | `CODEX_CF_ACCESS_CLIENT_ID`, `CODEX_CF_ACCESS_CLIENT_SECRET` |
| Dot | `DOT_KANBAN_TOKEN` | `DOT_CF_ACCESS_CLIENT_ID`, `DOT_CF_ACCESS_CLIENT_SECRET` |
| Gemini | `GEMINI_KANBAN_TOKEN` | `GEMINI_CF_ACCESS_CLIENT_ID`, `GEMINI_CF_ACCESS_CLIENT_SECRET` |
| Quoder | `QUODER_KANBAN_TOKEN` | `QUODER_CF_ACCESS_CLIENT_ID`, `QUODER_CF_ACCESS_CLIENT_SECRET` |

`*_KANBAN_TOKEN` va en `Authorization: Bearer <valor>`. El par de Cloudflare va en `CF-Access-Client-Id` y `CF-Access-Client-Secret`. Las mismas credenciales sirven para ambos métodos. Pasa `KANBAN_PROJECT_ID=1` como parámetro de proyecto. `*_KANBAN_ROLE` es informativa y puede omitirse.

Para actualizar este inventario sin consultar valores de credenciales:

```bash
docker exec -i agent-kanban-postgres-1 psql -U kanban -d kanban <<'SQL'
SELECT p.id, p.name, ap.agent_name, ap.role, ap.can_read, ap.can_claim
FROM agent_projects ap
JOIN project p ON p.id = ap.project_id
ORDER BY p.id, ap.agent_name;
SQL
```

[Guía del orquestador](orquestador.md) · [Guía de workers](workers.md)
