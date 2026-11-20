# Inventario de agentes de Kanban

Las identidades de esta tabla tienen un token emitido en Kanban. La asignación de proyecto permite operar sobre el proyecto indicado. Los tickets individuales se reservan o reclaman por separado.

| Agente | Proyecto | ID | Rol en Kanban | Puede leer | Puede reclamar |
| --- | --- | --- | --- | --- | --- |
| `bacha` | Kanban | 1 | `orchestrator` | Sí | Sí |
| `brio` | Kanban | 1 | `worker` | Sí | Sí |
| `codex` | Kanban | 1 | `worker` | Sí | Sí |
| `dot` | Kanban | 1 | `worker` | Sí | Sí |
| `gemini` | Kanban | 1 | `worker` | Sí | Sí |
| `instinct` | Kanban | 1 | `worker` | Sí | Sí |
| `nod` | Kanban | 1 | `orchestrator` | Sí | Sí |
| `n8n-radares` | Kanban | 1 | `orchestrator` | Sí | No |
| `quoder` | Kanban | 1 | `worker` | Sí | Sí |

La lista indica identidades configuradas. La disponibilidad del proceso de cada agente varía con su host. Los valores de las credenciales se administran en el archivo privado descrito en la [ficha técnica](ficha-tecnica.md).

El contrato de fábrica asigna a n8n la creación y el cierre de tarjetas. La fábrica secuencial usa Brio para investigación, Bacha para evaluación, prospección y cierre, Codex para MVP y Dot para landing. Nod e Instinct quedan fuera de las nuevas asignaciones de fábrica. Su archivo privado es `~/.config/agent-kanban/nod.env`. Consulta la [operación de fábrica](factory/README.md) y los prompts por identidad. Instinct usa el archivo privado `~/.config/agent-kanban/instinct.env`. El intermediario acepta el Bearer propio de Bacha, Brio, Codex, Dot e Instinct para consultar su cola y entregar.

## Qué pasar a cada agente

El archivo privado en WSL para los agentes de la tabla de conexión es `~/.config/agent-kanban/kk-agents.env`. Comparte únicamente las variables de la fila que corresponda y la URL del método elegido.

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

## Acceso de n8n para despachar tarjetas

Usa `POST https://kanban-api.okehc.com/api/tasks/dispatch` con `project_id: 1` en el JSON. Guarda `N8N_RADARES_KANBAN_TOKEN` en una credencial de n8n de tipo **Header Auth**, con nombre `Authorization` y valor `Bearer <token>`. El valor se guarda en WSL en `~/.config/agent-kanban/n8n-radares.env`.

El intermediario acepta ese Bearer para despachar por REST, consultar una tarjeta por ID y registrar su revisión. Agrega las dos cabeceras de su Service Token `kanban-n8n-radares`. La respuesta al crear una tarjeta es `201` con el `id`. Kanban registra `n8n-radares` como autor. Conserva el ID en el flujo para vincularlo con el radar que originó el despacho.

El Service Token vence el 16 de febrero de 2027 a las 16:04 UTC. Al renovarlo, actualiza `N8N_RADARES_CF_ACCESS_CLIENT_ID` y `N8N_RADARES_CF_ACCESS_CLIENT_SECRET` en el Worker de Cloudflare.

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


La operación vigente y los prompts por agente están en [sequential/README.md](sequential/README.md). Los permisos registrados de identidades antiguas se conservan; no significan que reciban trabajo del coordinador nuevo.


## Incorporación de Dot a landing

Dot conserva su identidad worker del proyecto 1. Su acceso de un solo Bearer
por el intermediario se habilitó el 19 de noviembre de 2026. Las variables
para entregar a Dot están fuera del repositorio, en
`~/.config/agent-kanban/dot.env`. El [mensaje de validación](sequential/dot-acceso.md)
comprueba MCP y REST desde su propio canal. La asignación de landing y los
horarios nuevos aún están pendientes; este acceso no cambia el reparto del
coordinador.


El puente [MegaMCP → Dot](mega-mcp/dot.md) permite usar su token desde el servidor. La validación directa por Bearer y la conexión a través del puente son rutas distintas; no hace falta resolver OAuth del Kanban para usar este puente.
