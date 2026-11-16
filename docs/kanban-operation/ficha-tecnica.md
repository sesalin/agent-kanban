# Agent Kanban · ficha técnica y recuperación

Verificado el 16 de noviembre de 2026.

| Dato | Valor |
| --- | --- |
| Repositorio | [sesalin/agent-kanban](https://github.com/sesalin/agent-kanban), rama `main` |
| Versión del paquete | `0.1.0`, declarada en `pyproject.toml` |
| Implementación de orquestación | Commit `2ec1417`, migración Alembic `0005_orchestration` |
| Ubicación | WSL en Windows, `/home/cheko/_proyects/agent-kanban`, con Docker Desktop |
| Aplicación | FastAPI y MCP Streamable HTTP sobre Python 3.11, tablero React compilado en Docker |
| Base de datos | PostgreSQL 17.12 en la instancia verificada, volumen Docker `agent-kanban_ak_pgdata` |
| Compose | Proyecto `agent-kanban`, servicios `app` y `postgres` |
| Tablero desde Windows | [localhost:7331](http://localhost:7331/) |
| LAN | `http://192.168.100.61:7331` para REST y `http://192.168.100.61:7331/mcp/` para MCP. Usa el Bearer de Kanban. |
| Internet | [kk.okehc.com](https://kk.okehc.com/) para web y REST, `https://kk.okehc.com/mcp/` para MCP. Cloudflare Access protege el hostname. |
| Túnel | `IIQ-tunnel`, conector `bibi-cloudflared`, red externa `bibi_edge`, origen `http://agent-kanban:7331` |
| Proyecto inicial | `Kanban`, ID `1`. Consulta el [inventario de agentes](agentes.md). |

Docker publica el puerto de la app en `127.0.0.1` y en la IP LAN de Windows. PostgreSQL usa la red interna de Compose. El túnel alcanza la app por su alias Docker. Mantén el 7331 sin redirección desde Internet en el router. La opción LAN usa HTTP en una red de confianza.

## Qué respaldar

- **Datos.** Un dump de PostgreSQL conserva tickets, proyectos, usuarios, hashes de tokens, permisos, eventos y configuración de webhooks. Guarda el dump en almacenamiento privado. Archivos externos referenciados por ruta requieren su propio respaldo.
- **Secretos locales de WSL.** Conserva `~/.config/agent-kanban/kk-compose.env` con `SESSION_SECRET` y `PUBLIC_URL`, y `~/.config/agent-kanban/kk-agents.env` con las credenciales de los agentes. Permisos `0600`. Kanban guarda hashes y no permite recuperar los Bearer originales a partir del dump.
- **Cloudflare.** Conserva el acceso administrativo a la zona `okehc.com`, Zero Trust y al túnel. La credencial del conector, los Service Tokens y el secreto de sesión se guardan fuera del repositorio.

Para generar el dump desde WSL:

```bash
install -d -m 700 "$HOME/kanban-backups"
umask 077
backup="$HOME/kanban-backups/kanban-$(date +%F-%H%M%S).dump"
docker exec agent-kanban-postgres-1 pg_dump -U kanban -d kanban -Fc > "$backup"
docker exec -i agent-kanban-postgres-1 pg_restore --list < "$backup"
```

## Reconstrucción del host

1. Habilita WSL y la integración de Docker Desktop en la distribución. Comprueba `docker info` y `docker compose version`. Desde WSL, clona el repositorio con `git clone -b main git@github.com:sesalin/agent-kanban.git` y entra al checkout.
2. Confirma la IP LAN del host con `ipconfig.exe`. En la raíz del checkout, crea el siguiente override local. Ajusta la IP en los tres lugares si Windows tiene otra. El Compose base usa PostgreSQL 16, por lo que el override debe acompañar los comandos de este despliegue con PostgreSQL 17.

```yaml
# docker-compose.cloudflare.yml
services:
  postgres:
    image: postgres:17-alpine
  app:
    ports: !override
      - "127.0.0.1:7331:7331"
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

3. Recupera los archivos privados y la red. Si el secreto de sesión se perdió, genera uno nuevo y vuelve a iniciar sesión en el tablero. El ejemplo crea un archivo de Compose únicamente cuando falta.

```bash
install -d -m 700 "$HOME/.config/agent-kanban"
umask 077
deployment_env="$HOME/.config/agent-kanban/kk-compose.env"
if [ ! -e "$deployment_env" ]; then
  (set -C; printf 'SESSION_SECRET=%s\nPUBLIC_URL=https://kk.okehc.com\n' \
    "$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')" > "$deployment_env")
fi

docker network inspect bibi_edge >/dev/null 2>&1 || docker network create bibi_edge
ak() {
  docker compose -p agent-kanban --env-file "$deployment_env" \
    -f docker-compose.yml -f docker-compose.cloudflare.yml "$@"
}
ak config --quiet
```

4. Si tienes un dump, inicia sólo PostgreSQL y restáuralo en una base `kanban` vacía de esta instalación nueva. Si la base original sigue disponible en el volumen, conserva ese volumen y usa sus datos. Después inicia la app. Al arrancar, la imagen aplica las migraciones y sirve el tablero.

```bash
# Restauración, sólo si se usa un dump sobre una base vacía
ak up -d --wait postgres
ak exec -T postgres pg_restore -U kanban -d kanban --no-owner --no-privileges \
  --exit-on-error --single-transaction < /ruta/privada/kanban.dump

# Arranque de la aplicación, con datos restaurados o base nueva
ak up -d --build app
ak ps
ak logs --tail 40 app
```

5. Si arrancas sin datos, crea el administrador y entra al tablero. Crea el proyecto `Kanban` mediante `POST /api/projects`, usando la sesión humana y el cuerpo `{"name":"Kanban"}`. Anota el ID generado. En **Admin → Tokens**, emite un Bearer por agente y guarda los valores en privado. Ejecuta este SQL desde el host, sustituyendo `1` si el proyecto recibió otro ID.

```bash
ak exec -T postgres psql -U kanban -d kanban -v ON_ERROR_STOP=1 <<'SQL'
INSERT INTO agent_projects (agent_name, project_id, role, can_read, can_claim)
VALUES ('hermes', 1, 'orchestrator', true, false),
       ('bacha', 1, 'worker', true, true),
       ('brio', 1, 'worker', true, true),
       ('codex', 1, 'worker', true, true),
       ('dot', 1, 'worker', true, true),
       ('gemini', 1, 'worker', true, true),
       ('quoder', 1, 'worker', true, true)
ON CONFLICT (agent_name, project_id) DO UPDATE
SET role = EXCLUDED.role, can_read = EXCLUDED.can_read, can_claim = EXCLUDED.can_claim;
SQL
```

6. Recupera el conector `bibi-cloudflared` con la credencial del túnel y conéctalo a `bibi_edge`. Si se perdió la configuración de la ruta, crea primero en Cloudflare Access una app Self-hosted para todo `kk.okehc.com`, con **Allow** limitado al correo del administrador y MFA TOTP, más **Service Auth** para los Service Tokens individuales. Añade el hostname al túnel con destino `http://agent-kanban:7331` y **Protect with Access**, y verifica que el DNS proxied apunte al túnel. Conserva las demás rutas si reutilizas `IIQ-tunnel`. Si un Service Token se perdió, vuelve a emitirlo o rota su secreto, actualiza el cliente y la política cuando corresponda. Los tokens originales vencen el 12 de febrero de 2027.

Si recuperas el conector compartido, restaura su despliegue original con las redes de todas sus rutas. Si sólo vas a recuperar Kanban en el nuevo host, usa un túnel dedicado a Kanban y guarda su credencial como `TUNNEL_TOKEN` en `~/.config/agent-kanban/kk-tunnel.env` con permisos `0600`. [Parámetros de Cloudflare Tunnel](https://developers.cloudflare.com/tunnel/reference/run-parameters/)

```bash
docker run -d --name kanban-cloudflared --restart unless-stopped --network bibi_edge \
  --env-file "$HOME/.config/agent-kanban/kk-tunnel.env" \
  cloudflare/cloudflared:latest tunnel --no-autoupdate run
```

## Comprobación tras el arranque

- Desde Windows, `curl.exe -fsS http://localhost:7331/api/setup-status` debe responder. `needs_setup: false` indica que ya existe un usuario. Entra al tablero y revisa **Admin → Tokens**.
- Ejecuta `ak exec -T postgres psql -U kanban -d kanban -c "SELECT version_num FROM alembic_version;"` y comprueba la revisión esperada. `ak port app 7331` debe mostrar sólo las dos IP configuradas.
- Desde un agente autorizado, consulta las tareas por MCP con su propio Bearer. Para Internet usa también las dos cabeceras de Cloudflare. Sin credenciales, el dominio HTTPS debe llevar a Access o denegar el acceso.
- En una instalación de prueba, despacha una tarea, reclámala como worker, entrégala y apruébala con Hermes. El tablero debe terminar en `done`. El flujo de dependencias y la reasignación tras inactividad ya se verificaron en una instancia temporal.

## Pendientes conocidos

- La interfaz lista tokens en **Admin → Tokens**. Los permisos por proyecto se consultan en `agent_projects`.
- El resumen y los artefactos de entrega están en el feed del tablero. MCP permite leer comentarios y campos del ticket, incluido `pr_url`.
- Al verificar la instancia había cero webhooks activos. Los eventos se registran en `task_events`. La entrega externa de webhooks es de mejor esfuerzo y queda por verificar con un receptor real.
- Falta una prueba desde el equipo LAN `192.168.100.200`. La conexión a la IP LAN se verificó desde el propio Windows. El acceso humano con MFA se comprueba con el autenticador del titular.
- El procedimiento de recuperación documentado no se ejecutó contra la base activa. Los ensayos de la suite de orquestación usaron PostgreSQL 17 aislado.

[Guía del orquestador](orquestador.md) · [Guía de workers](workers.md) · [Inventario](agentes.md)
