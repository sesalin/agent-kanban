# Operación de la fábrica en anyo

**Montaje sustituido el 18 de noviembre de 2026:** el pipeline secuencial ya
está implementado y sus cron publicados. La documentación vigente, prompts,
horarios, incidencias y exportaciones están en
[../sequential/README.md](../sequential/README.md). Los WF1–WF5 descritos abajo
son históricos y están archivados. No los actives junto al coordinador nuevo.

Estado del montaje del 18 de noviembre de 2026. El contrato de los cinco documentos del usuario gobierna el flujo. Nod toma la decisión GO/NO_GO y n8n crea y cierra las tarjetas. El proyecto Kanban es el 1.

## Instalado y comprobado

- Supabase `radars-n8n`, ID `uobeshcvmtawjxibciuy`, contiene `opportunity_pipelines`, los enlaces a las tres tablas de radares y las funciones de transición de la fábrica. La tabla nueva tiene RLS y acceso de servidor. Las funciones de fábrica permiten ejecución a `service_role`.
- Kanban monta `/mnt/c/_mcp/muse-packages:/muse-packages`. Las tarjetas antiguas conservan el formato `metadata.muse_zip.path`. Las nuevas pueden indicar `output_path` para guardar el resultado en otra subcarpeta.
- El despacho acepta `metadata.factory_dispatch_key`. Un reintento del mismo agente y proyecto con la misma clave y metadatos recupera la tarjeta existente. Cambiar el destinatario o los metadatos con esa clave provoca error.
- Nod evalúa, realiza prospección, construye la landing y revisa el cierre. Brio investiga y Codex construye el MVP. Instinct queda fuera del flujo activo por decisión del usuario; sus registros anteriores se conservan. La identidad `n8n-radares` despacha, consulta tarjetas individuales, registra revisiones y prepara los archivos de fábrica.
- Los cinco workflows están guardados en `anyo.okehc.com` como borradores. Los tres borradores anteriores fueron archivados y conservan su historial.
- Windows tiene actualmente la IP LAN `192.168.100.91`. Kanban responde en `http://localhost:7331/` y publica también el puerto en esa IP privada.

## Workflows y contratos

Todos reciben POST con JSON y `Authorization: Bearer <token-factory>`.

| Flujo | Ruta de webhook de producción | Editor |
| --- | --- | --- |
| WF1 | `/webhook/factory/package-ready` | [01_Radar_Ready_To_Brio](https://anyo.okehc.com/workflow/NWIvkLOXKPe3yUZa) |
| WF2 | `/webhook/factory/brio-done` | [02_Brio_Done_To_Nod_Eval](https://anyo.okehc.com/workflow/JlsGr3jYEd5tmoJj) |
| WF3 | `/webhook/factory/nod-decision` | [03_Nod_Decision_Router](https://anyo.okehc.com/workflow/anHYNSMXip5G2ze3) |
| WF4 | `/webhook/factory/branch-done` | [04_Branch_Collector_And_Join](https://anyo.okehc.com/workflow/8zG48MWjzi5VTYEL) |
| WF5 | `/webhook/factory/final-close` | [05_Final_Delivery_To_User](https://anyo.okehc.com/workflow/gwu7uCq8i3sTAaeH) |

La ruta base es `https://anyo.okehc.com`. Las rutas `/webhook-test/` sirven durante una escucha de prueba en el editor. Los webhooks de producción funcionan al publicar cada workflow.

Los JSON importables están junto a esta guía como `WF1.json` a `WF5.json`. Contienen referencias de credenciales de esta instancia. En una restauración hay que seleccionar las nuevas credenciales. El generador reproducible está en `deploy/factory/workflows.mjs`. Ejecutar `node deploy/factory/workflows.mjs` produce los SDK en `deploy/factory/generated/`.

WF1 recibe `{event_id, radar_table, title, package_path, package_filename}`. Comprueba el ZIP en WSL, lo copia a `01_input/paquete.zip`, registra el pipeline y despacha a Brio con clave `<event_id>:research`. Guarda la tarjeta en Supabase y después envía el aviso por Evolution.

WF2 recibe `{event_id, brio_task_id, research_zip_path, summary}`. Contrasta la tarjeta con el pipeline, comprueba el reclamo de Brio y el estado `review`, verifica el ZIP en disco y registra la entrega. Después despierta a Nod para evaluación.

WF3 recibe el `decision.json` completo del contrato. Valida el vínculo de Brio, el veredicto, las tres banderas booleanas y los prompts de las ramas activas. Aprueba la investigación, registra la decisión y, para GO, prepara los archivos de especificación y despacha las ramas activas con claves estables. El aviso de Codex prepara un archivo en `~/workspace_tasks`. Las otras ramas usan Evolution.

WF4 recibe `{event_id, branch, task_id, zip_path}`. Comprueba que la rama esté activa, que la tarjeta corresponda al pipeline y que haya un ZIP real. La tarjeta debe estar en `review` o ya en `done` por un reintento. Registra `APPROVE` cuando corresponde. Una transacción bloquea la fila del pipeline, actualiza la rama y pasa a `FINAL_REVIEW` cuando todas las ramas activas están completas. Solo la ejecución que hace esa transición recibe `wake_final_review=true`.

WF5 recibe `{event_id, executive_summary, bundle_path}`. Exige el estado de revisión final, guarda `07_release/resumen_ejecutivo.md`, registra `DONE` en Supabase y envía el resumen a Telegram.

## Carpetas y archivos

```text
/mnt/c/_mcp/muse-packages/<event_id>/
  01_input/paquete.zip
  02_research/research.zip
  03_specs/decision.json
  03_specs/mvp_spec.md
  03_specs/icp_spec.md
  03_specs/landing_spec.md
  03_specs/mvp-input.zip
  03_specs/prospection-input.zip
  03_specs/landing-input.zip
  04_mvp/mvp.zip
  05_prospects/prospects.zip
  06_landing/landing.zip
  07_release/resumen_ejecutivo.md
```

Los archivos de una rama se preparan cuando su bandera está activa. Cada ZIP de especificaciones incluye su Markdown y `research.zip`. Esto permite que el agente descargue su entrada mediante la API existente. Las carpetas versionadas de los radares se conservan como origen. La preparación copia el ZIP original a la estructura del contrato.

Ejemplo de metadatos de Brio en el campo `metadata` del despacho REST.

```json
{
  "event_id": "ejemplo-1",
  "factory_dispatch_key": "ejemplo-1:research",
  "muse_zip": {
    "path": "ejemplo-1/01_input",
    "input_file": "paquete.zip",
    "output_path": "ejemplo-1/02_research",
    "output_file": "research.zip"
  }
}
```

La respuesta de Kanban devuelve esos datos en `metadata_payload`. La descarga de entrada requiere que el worker tenga la tarjeta reclamada en `in_progress`. La subida usa PUT binario con `Content-Type: application/zip`. El límite actual de esa subida es 10 MiB. Un resultado existente se conserva y otro PUT al mismo archivo recibe 409. Codex también puede escribir su ZIP directamente en WSL.

## Credenciales y conexiones en n8n

### Webhook para conectar Evolution a n8n

El receptor está publicado en `https://anyo.okehc.com/webhook/factory/evolution-events`.
Configura POST con JSON y la cabecera `Authorization: Bearer <N8N_RADARES_HEADER_KANBAN_TOKEN>`.
El valor se obtiene del archivo privado de fábrica. La prueba pública devolvió
200 con `{"received":true}`. Una clave enviada sin el prefijo Bearer recibió 403.

El [receptor de eventos](https://anyo.okehc.com/workflow/m0EdU2DRzcpZqqpo)
registra los eventos en el historial de ejecución, reconoce mensajes que empiezan
con `WAKEUP` y confirma la recepción. Su exportación es `Evolution-events.json`.
La recepción registra `instance`, `message_id`, `from_me` y `wakeup`. El agente
Nod inicia su trabajo al recibir el WhatsApp en su conexión local.

Evolution usa su webhook nativo con `headers.Authorization` para este transporte.
Los eventos suscritos son `SEND_MESSAGE` y `MESSAGES_UPSERT`, con `byEvents=false`
y `base64=false`. La integración de bot n8n anterior quedó desactivada con
`triggerType=none` después de la autorización explícita del usuario. Su copia
privada está en `~/.config/agent-kanban/evolution-before-native-webhook.json`.
El receptor mantiene Header Auth y recibe también los eventos de mensajes propios.

Abre [Credentials de anyo](https://anyo.okehc.com/home/credentials). El MCP de n8n permite vincular credenciales existentes. La creación y edición de sus valores secretos se realiza en esa pantalla.

| Credencial | Configuración | Dónde seleccionarla |
| --- | --- | --- |
| `openai-radar-header` existente | Header Auth, nombre `Authorization`, valor `Bearer <N8N_RADARES_HEADER_KANBAN_TOKEN>` | Nodos `Entrada`, ya vinculados |
| `N8N_RADARES_KANBAN` existente | Bearer Auth, valor de `N8N_RADARES_KANBAN_TOKEN` | HTTP de Kanban, ya vinculados |
| `RADARS_SUPABASE` vinculada y verificada | Tipo Supabase API, Host `https://uobeshcvmtawjxibciuy.supabase.co`, clave secreta de servidor de ese proyecto | Todos los HTTP con Predefined Credential Type `supabaseApi` |
| `Evolution Factory` vinculada y verificada | Header Auth con Name `apikey` y Value igual a la API key de Evolution | Nodos `Despertar...` |
| `Telegram Cheko` pendiente | Tipo Telegram API, campo Access Token con el token del bot, sin Bearer | `Entregar al usuario por Telegram` y el notificador de radares |

Los secretos de webhooks y Kanban están en `~/.config/agent-kanban/n8n-radares.env`, fuera del repositorio y con permisos 0600. Ambos usan el valor común acordado. Las credenciales de los servicios externos deben corresponder a sus respectivas cuentas. [Configuración de Supabase en n8n](https://docs.n8n.io/integrations/builtin/credentials/supabase/)

La instancia `anyo` y el destinatario de Nod ya están configurados. Falta identificar el destinatario de WhatsApp de Brio: no apareció al buscar Brio, Brío o Muse en los 59 contactos, 31 chats y 3 grupos devueltos por Evolution. El usuario confirma que su canal debe ser WhatsApp. WF1 conserva `CONFIGURAR_NUMERO_BRIO` y sigue inactivo. En WF5 falta `CONFIGURAR_CHAT_CHEKO` y vincular Telegram API.

El host de Evolution confirmado es `http://192.168.100.86:8080`, versión 2.3.7,
con instancia `anyo`. El usuario confirmó `528145925005` como número conectado
a Evolution y destinatario de Nod. Los nodos de Nod envían al mismo número de
esa instancia. La API key común de fábrica recibió 401 al consultar Evolution;
La credencial `Evolution Factory` ya está vinculada a los cuatro nodos de envío.
El usuario guardó `EVO_KEY` en el archivo privado `n8n-radares.env`. Las consultas
directas con esa clave devolvieron 200 e instancia `anyo` en estado `open`.
La ejecución 26 desde n8n confirmó el acceso con `Evolution Factory`.
La ejecución 27 envió un WhatsApp de prueba al mismo número y recibió HTTP 201,
con `fromMe=true` y destino normalizado por Evolution a `5218145925005@s.whatsapp.net`.
La aceptación del envío devolvió `PENDING`. Después del ajuste autorizado del
webhook, la ejecución 30 envió una prueba final y obtuvo HTTP 201. La ejecución
31 recibió el evento desde Evolution, con el mismo `message_id`, `wakeup=true`
y `from_me=true`. Queda por confirmar la ejecución de una tarea real por Nod.
El diagnóstico está en
[Comprobación de acceso Evolution](https://anyo.okehc.com/workflow/CdT93Pts94MnW2rq).

El usuario autorizó configurar el webhook nativo y desactivar la integración
n8n de bot que apuntaba a la misma URL. Se conserva una copia privada para
recuperación. El webhook nativo envía la cabecera de autorización correcta y
recibe los eventos de mensajes propios sin depender de `listeningFromMe`
del bot anterior. El usuario confirmó que el número emisor y el de Nod son el mismo.

```text
/home/cheko/_proyects/agent-kanban/deploy/factory/files.py
```

## Activación de Codex y configuración de agentes

Entrega a Brio, Nod y Codex su prompt de esta carpeta y su credencial propia de Kanban. Brio y Codex conservan sus identidades existentes. Nod usa la identidad nod y el archivo privado `~/.config/agent-kanban/nod.env`. Los Service Tokens de los agentes están configurados en el intermediario, por lo que basta su Bearer de Kanban para la URL pública del intermediario.

El archivo `TASK_MVP_<event_id>.md` queda preparado por WF3. Falta conectar el lanzador local de Codex que detectará esos archivos y abrirá una ejecución. El montaje actual prepara el archivo, pero la ejecución automática de Codex sigue pendiente de ese lanzador. Debe reclamar la tarjeta indicada, leer `03_specs/mvp_spec.md`, entregar el MVP y llamar WF4. El estado de ese lanzador debe verificarse antes de activar `run_mvp` en un evento real.

Tras cada entrega, los prompts exigen `list_my_tasks({"project_id":1})`, filtrar `assigned_to` por la identidad y reclamar la siguiente tarjeta. El ciclo continúa hasta vaciar la cola de esa identidad. Un nuevo aviso inicia otro ciclo.

Para los webhooks de entrega se usa la cabecera `Authorization`. La fábrica sigue los callbacks directos de los agentes descritos en el contrato. Los avisos automáticos de Kanban usan `X-Webhook-Secret` y un payload distinto, por lo que este montaje no registra un segundo disparador paralelo para el mismo trabajo.

## Corte pendiente de las automatizaciones hacia anyo

MegaMCP todavía conserva tres destinos anteriores en `/mnt/c/_mcp/mega-mcp/.env`. El receptor de ingesta `radar-events` necesita migrarse a anyo antes de cambiar el envío. El notificador de anyo existe como borrador en [Radar Analysis Notify](https://anyo.okehc.com/workflow/dsB1enlQ0YuZ3qey) y espera su credencial de Telegram y configuración de chat.

1. Exporta el workflow de ingesta anterior y ábrelo como importación en anyo. Conserva su validación, deduplicación y enrutamiento hacia inbox y las cuatro tablas. Selecciona exclusivamente la credencial `RADARS_SUPABASE` del proyecto verificado. Conserva el path `radar-events` y selecciona `openai-radar-header` como autenticación del webhook.
2. Completa el notificador `radar-analysis-notify` de anyo y su credencial Telegram. Puede recibir tanto el resumen de Gobierno como el general.
3. Publica ambos receptores y comprueba un evento autorizado. Verifica la persistencia y la deduplicación antes del corte de envío.
4. Revisa la vista previa del cambio de destinos desde este repositorio.

```bash
python3 deploy/factory/cutover-radars.py
```

5. Cuando los receptores estén verificados, aplica la configuración y recrea MegaMCP.

```bash
python3 deploy/factory/cutover-radars.py --apply
docker compose --project-directory /mnt/c/_mcp/mega-mcp up -d --no-deps mega-mcp
```

El script cambia `RADAR_WEBHOOK_URL`, `RADAR_ANALYSIS_NOTIFY_URL` y `RADAR_GOBIERNO_NOTIFY_URL` a anyo y sincroniza sus tres secretos con el token de entrada acordado. Guarda una copia privada de la configuración previa en `~/.config/agent-kanban/mega-mcp-before-anyo.env`. El corte se deja pendiente hasta que los receptores estén publicados.

Las herramientas de automatización de ChatGPT no están expuestas para editar sus prompts desde esta sesión. El destino de `radar_publish` y de los notificadores está centralizado en MegaMCP. Para cualquier automatización que haya escrito la URL anterior directamente en su prompt, cambia ese texto por la URL de anyo y conserva su calendario.

El generador actual de paquetes debe llamar WF1 después de registrar y verificar un ZIP listo. Usa el payload descrito arriba, la cabecera de autorización común y conserva `event_id` en reintentos. Este enlace del generador con WF1 también está pendiente.

## Secuencia de puesta en marcha

1. Completa las credenciales y campos pendientes en los cinco workflows.
2. Pega los prompts de Brio, Nod y Codex en sus entornos y asigna sus credenciales privadas.
3. Las operaciones WSL por API ya funcionan. Configura el lanzador local de Codex.
4. Migra y verifica ingesta/notificador. Aplica el corte de MegaMCP.
5. Publica WF5, WF4, WF3, WF2 y WF1. Comprueba las URLs desde el canal de cada agente.
6. Conecta el generador de paquetes a WF1.
7. Ejecuta una oportunidad real de Gobierno NL y verifica el recorrido hasta el aviso final. La prueba E2E real queda pendiente de los pasos anteriores.

## Recuperación y límites verificados

La investigación usa `muse_status=sent` al despachar y `completed` al entregar, compatibles con la base existente. `decision` conserva GO/NO_GO en el pipeline. La resolución del radar usa `discarded` para NO_GO, `build_mvp` para GO con MVP e `interesting` para otras ramas GO. Esto conserva las restricciones actuales del radar.

La migración reproducible está en `deploy/factory/supabase.sql` seguida de `deploy/factory/transitions.sql`. Ambos archivos forman una transacción. Ejecútalos únicamente en el proyecto `uobeshcvmtawjxibciuy`. En la instalación actual ya están aplicados mediante las migraciones `opportunity_factory_pipeline` y `factory_read_pipeline`.

Las notificaciones externas se envían después de los cambios de estado. Si falla el aviso final a Nod después de pasar a `FINAL_REVIEW`, reanuda el nodo de notificación de esa ejecución. Reenviar WF4 conserva el estado y evita generar otro disparo final. Queda pendiente automatizar la recuperación de ese aviso si el proveedor falla después del commit. WF5 también puede repetir el aviso al usuario si se reenvía el callback de cierre. Comprueba el historial de ejecución antes de repetir notificaciones.

Se verificaron seis pruebas de paquetes y orquestación, cuatro pruebas del intermediario, la preparación local de archivos con rutas de prueba, las transiciones SQL en PostgreSQL temporal y una ejecución simulada de cada workflow en n8n. Las cinco ejecuciones de n8n fijaron los servicios externos con datos de prueba. Esas pruebas simuladas no validan los proveedores externos ni el recorrido E2E real. Las comprobaciones reales posteriores se detallan abajo.


## Reemplazo del evaluador por Nod

La prueba inicial de conexión usa la tarjeta #11, asignada a `nod` en el proyecto 1.
El [workflow de prueba](https://anyo.okehc.com/workflow/9i1pJhfF3Qx5unM3)
la creó con la identidad `n8n-radares` y envió el WhatsApp mediante Evolution.
Prueba completada y verificada en Kanban el 18 de noviembre de 2026. La tarjeta
#11 está en `review`, con `claimed_by=nod`. El comentario #9 tiene autor `nod`
y el texto «Nod confirmó acceso al proyecto 1 y reclamó esta tarjeta».
La consulta posterior no devolvió otra tarjeta disponible asignada a `nod`.
Esto verifica el acceso del propio agente, el reclamo, el comentario, la entrega
y la consulta de la siguiente tarjeta. El archivo privado de Nod es
`~/.config/agent-kanban/nod.env`. La clave de despacho
`nod-connection-check-2026-11-18` permite recuperar la misma tarjeta si se
repite la preparación. Esta comprobación cubre la conexión y el ciclo básico de
Nod; la prueba completa de una oportunidad con ZIP y ramas sigue pendiente.

Nod es el agente externo que se ejecuta en el PC del usuario y está conectado a
n8n. Su prompt está en [nod.md](nod.md). La credencial de acceso al MCP de n8n
sigue siendo la que el usuario ya conectó. Kanban tiene una identidad propia
`nod` con acceso al proyecto 1, lectura de investigaciones y reclamo de sus
tarjetas de landing.

Los callbacks de Nod son `factory/nod-decision`, `factory/branch-done` y
`factory/final-close`. Usa el `NOD_FACTORY_WEBHOOK_TOKEN` del archivo
privado para esos tres callbacks. Para el MCP y REST de Kanban usa
`NOD_KANBAN_TOKEN`.

Los workflows siguen en borrador. El usuario confirmó WhatsApp mediante
Evolution API como canal para despertar a Nod, igual que Brio. WF2 envía
`WAKEUP NOD [EVALUACION]`, la rama landing de WF3 envía `WAKEUP NOD [LANDING]`
y WF4 envía `WAKEUP NOD [CIERRE FINAL]`. El host de Evolution, la instancia
`anyo`, la credencial `Evolution Factory` y el número de Nod están configurados.
La recepción del WhatsApp por el agente local inicia el modo indicado. La conexión MCP de
Nod se usa después para consultar la evidencia y trabajar las tarjetas.

La identidad anterior de Bacha permanece registrada. No había tarjetas activas
asignadas a Bacha al configurar el reemplazo. Las nuevas tarjetas de landing
se reservan a `nod`. La validación de entrega de WF4 exige ese mismo
`claimed_by`.


## Archivos WSL por API y prospección de Nod (18 de noviembre de 2026)

Los cinco workflows sustituyeron sus nodos SSH por HTTP autenticado:
`POST https://kanban-api.okehc.com/api/factory/files/{operation}`.
Reutilizan `N8N_RADARES_KANBAN`, tipo Bearer Auth. Las operaciones admitidas son
`input`, `specs`, `verify`, `wakeup` y `release`; el cuerpo JSON mantiene el
contrato que utilizaba el helper. Las respuestas contienen `event_id` y el
resultado de la operación. Los nodos de comprobación comprueban ese JSON.

El intermediario solo permite estas rutas a `n8n-radares`; el backend exige
además su permiso de orquestador del proyecto 1. Los workers no reciben acceso
a estas operaciones. La API conserva los originales, acepta reintentos con el
mismo contenido y rechaza sobrescribir archivos diferentes o atravesar rutas
fuera de las raíces y enlaces simbólicos. No ejecuta comandos recibidos por HTTP.
El helper compartido está en `src/agent_kanban/factory_files.py`; la entrada
CLI de `deploy/factory/files.py` conserva compatibilidad para mantenimiento.

El override local `docker-compose.cloudflare.yml`, excluido de Git, contiene:

```yaml
services:
  app:
    environment:
      MUSE_PACKAGES_ROOT: /muse-packages
      FACTORY_TASKS_ROOT: /workspace-tasks
    volumes:
      - /mnt/c/_mcp/muse-packages:/muse-packages
      - /home/cheko/workspace_tasks:/workspace-tasks
```

Esas líneas se agregan al override existente, que conserva puertos LAN,
PostgreSQL 17 y la red del túnel. No reemplaces el archivo completo con este
fragmento. Las rutas que ve Codex en los avisos siguen siendo las rutas WSL.
El archivo `TASK_MVP_*.md` prepara el aviso; aún falta el lanzador que lo ejecute.

`RADARS_SUPABASE` ya está vinculada a los 11 nodos de Supabase de WF1–WF5.
Su copia privada está en `~/.config/agent-kanban/radars-supabase.env`, modo 0600.
La ejecución 38 de n8n comprobó una lectura real de `opportunity_pipelines`
en `uobeshcvmtawjxibciuy`. La ejecución 39 comprobó la escritura real de un
resumen de conexión mediante Kanban y volvió a leer Supabase. Se verificó el
archivo en WSL y se retiró únicamente esa carpeta de comprobación.
[Workflow de diagnóstico](https://anyo.okehc.com/workflow/uAdh2UIHvSNMhL3D).
El diagnóstico es manual e inactivo; al repetirlo se recrea su carpeta de prueba.

Las ramas `prospection` y `landing` se asignan a `nod` en WF3 y WF4 valida
`claimed_by=nod` para ambas. Los avisos usan `[PROSPECCION]` o `[LANDING]` y
el mismo WhatsApp de Nod. El prompt `nod.md` especifica los dos entregables
independientes. Instinct no recibe nuevas tarjetas de la fábrica.

Verificación de este cambio:

- `pytest -q tests/test_factory_files.py tests/test_task_packages.py tests/test_orchestration.py`: 8 pruebas correctas contra PostgreSQL temporal, retirado al terminar.
- Ruff sin incidencias en el helper, la ruta nueva, la CLI y sus pruebas.
- Pruebas del intermediario correctas, incluida la exclusividad de las cinco rutas para n8n.
- WF1–WF5 validados por el SDK y guardados sin nodos SSH; se comprobaron sus conexiones y credenciales guardadas.
- Ejecuciones simuladas 40 y 41 correctas para despacho de prospección a Nod y recepción de su entrega. No crearon tarjetas ni enviaron mensajes.
- Contenedor Kanban e intermediario HTTPS desplegados. Una solicitud de archivo fuera de raíz devolvió 422 tanto local como por HTTPS.

La fábrica completa sigue en borrador: faltan el destinatario de Brio,
Telegram API y chat ID, el lanzador de Codex, la ingesta en anyo y el enlace del
generador de paquetes con WF1. No se ha validado una oportunidad completa hasta
el informe final. Los límites de recuperación de notificaciones de la sección
anterior siguen vigentes.
