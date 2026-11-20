# Puente MegaMCP → Agent Kanban para Dot

Reutiliza el contenedor `mega-mcp` y el túnel OpenAI existentes en WSL.
[Instrucciones y catálogo para Dot](dot.md).

## Montaje

- Código fuente de MegaMCP: `/mnt/c/_mcp/mega-mcp`.
- Módulo añadido: `app/mcp/factory_dot_bridge.py`.
- Registro en `app/mcp/http_server.py`, activado solo con `FACTORY_DOT_BRIDGE_ENABLED=true`.
- La raíz `/mnt/c/_mcp/muse-packages` ya está montada en ambos servicios; MegaMCP la ve como `/muse-packages` con escritura.
- API interna: `http://host.docker.internal:7331`, con el token existente de Dot. No hace falta pasar por el intermediario Cloudflare para esta comunicación interna.
- Variables privadas: `/home/cheko/.config/agent-kanban/mega-mcp-dot.env`, modo 0600. Define `FACTORY_DOT_BRIDGE_ENABLED`, `FACTORY_DOT_KANBAN_URL`, `FACTORY_DOT_PACKAGES_ROOT` y `FACTORY_DOT_KANBAN_TOKEN`.
- El módulo limita el destino a esa URL interna o al intermediario HTTPS ya conocido, y no sigue redirecciones con la credencial.
- Las nuevas herramientas son `factory_dot_*`. Las herramientas de otros proyectos y las funciones antiguas `kanban_*` no se reutilizan para este servicio.

## Despliegue realizado

Se partió de la imagen que estaba ejecutando MegaMCP, guardada como
`mega-mcp-dot-base:c291a337ed51`. Se añadió únicamente el módulo y el registro
HTTP. Imagen activa: `mega-mcp-dot-bridge:20261119-workspace`.

`/mnt/c/_mcp/mega-mcp/docker-compose.override.yml` agrega la imagen y el archivo
privado de variables. No contiene el token. Los valores efectivos de Compose
se compararon con el contenedor antes de recrearlo y no tenían diferencias.
El túnel conserva su configuración y el dashboard conserva la versión de la
imagen anterior. Los cambios pendientes del dashboard en el checkout no se
incluyeron en esta imagen derivada.

Los archivos reproducibles del puente se conservan también en este repositorio
bajo `deploy/mega-mcp/`. Para una construcción normal futura de MegaMCP, el
módulo y las dos líneas de registro ya están en su árbol de código. Revisa
antes los cambios ajenos pendientes de ese repositorio.

Para recrear la imagen derivada sin incorporar otros cambios:

1. Usa como base una imagen comprobada de MegaMCP que ya incluya su túnel y configuración.
2. Prepara un contexto con `factory_dot_bridge.py`, `Dockerfile.bridge` y una copia de `http_server.py` de esa imagen. Añade a esta última el import `register_dot_tools` y su llamada después de `register_read_tools`.
3. Construye con `docker build --build-arg MEGA_MCP_BASE=<imagen-base> -f Dockerfile.bridge -t mega-mcp-dot-bridge:<versión> <contexto>`.
4. Conserva el env privado, ajusta la imagen del override y ejecuta `docker compose --project-directory /mnt/c/_mcp/mega-mcp up -d --no-deps --no-build mega-mcp`.
5. Comprueba estado saludable, el catálogo y `factory_dot_status`. Refresca el catálogo de la conexión del cliente si conserva metadatos antiguos.

## Recuperación

Si el puente impide arrancar, vuelve temporalmente al Compose base, que utiliza
la imagen anterior:

```bash
docker compose --project-directory /mnt/c/_mcp/mega-mcp \
  -f /mnt/c/_mcp/mega-mcp/docker-compose.yml \
  up -d --no-deps --no-build mega-mcp
```

Ese comando omite deliberadamente el override del puente. No elimina paquetes,
configuración ni código. Después de corregir la causa, vuelve a aplicar el
override. No reconstruyas ni elimines el túnel para corregir un catálogo en caché.

## Verificación

- Cinco pruebas del puente: ZIP completo desde/hacia workspace, permisos/rutas, binarios, límites, referencia nativa de archivo, recurso MCP, reintentos y protección del token.
- Doce pruebas HTTP existentes de MegaMCP correctas.
- Imagen validada con el SDK real 1.12.4: 34 herramientas, de las cuales 10 son de Dot.
- En producción, initialize/listado/llamadas MCP a `factory_dot_status` y `factory_dot_list_tasks` correctas. Identidad `dot`, proyecto 1 y cola propia vacía.
- No se creó ni reclamó trabajo real en estas comprobaciones. Dot también confirmó el acceso desde su propio chat. Falta una entrega de landing productiva realizada por Dot en su turno.

El SDK antiguo requiere anotaciones de parámetros resueltas al registrar las
herramientas. El módulo evita anotaciones diferidas; no se actualizó el SDK ni
se agregaron dependencias para resolver esa compatibilidad.

## Corrección: workspace de Dot

Dot desarrolla y prueba en su propio workspace. El servidor solo entrega la
entrada y guarda el ZIP final, sin desarrollo remoto archivo por archivo.
Se sustituyeron tres herramientas de archivos preparados por descarga binaria
y subida de archivo nativo; consulta el [contrato vigente](dot.md). No se
modificaron horarios, roles, Supabase ni las ramas de Codex y Bacha para este
ajuste. El túnel y el dashboard conservan su configuración anterior.

El SDK 1.12.4 no propaga _meta de descriptores desde FastMCP; se usa su registro
de list_tools de bajo nivel para añadir openai/fileParams únicamente al tool
de subida, conservando el resto del catálogo. El recurso ZIP se registra con
el mecanismo de recursos del mismo servidor. No se añadieron dependencias.
