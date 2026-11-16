# Inventario de agentes de Kanban

Permisos verificados en PostgreSQL el 16 de noviembre de 2026. Las siete identidades tienen un token emitido en Kanban. La asignación de proyecto permite operar sobre el proyecto indicado. Los tickets individuales se reservan o reclaman por separado.

| Agente | Proyecto | ID | Rol en Kanban | Puede leer | Puede reclamar |
| --- | --- | --- | --- | --- | --- |
| `hermes` | Kanban | 1 | `orchestrator` | Sí | No |
| `bacha` | Kanban | 1 | `worker` | Sí | Sí |
| `brio` | Kanban | 1 | `worker` | Sí | Sí |
| `codex` | Kanban | 1 | `worker` | Sí | Sí |
| `dot` | Kanban | 1 | `worker` | Sí | Sí |
| `gemini` | Kanban | 1 | `worker` | Sí | Sí |
| `quoder` | Kanban | 1 | `worker` | Sí | Sí |

La lista indica identidades configuradas. La disponibilidad del proceso de cada agente varía con su host. Los valores de las credenciales se administran en el archivo privado descrito en la [ficha técnica](ficha-tecnica.md).

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
