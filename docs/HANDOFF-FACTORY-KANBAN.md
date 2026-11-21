# Hand-off: Agent Kanban y fábrica de oportunidades

> **Suspendido por instrucción del operador — 20-11-2026.**
> El worker de MVP `kanban-codex.service` está detenido y el temporizador
> `kanban-codex.timer` deshabilitado. No hay próxima ejecución programada.
> No reactivarlo sin nueva instrucción del operador. Las tarjetas y archivos
> se conservan; una tarjeta en progreso no acredita un proceso ejecutándose.
> Los horarios descritos más abajo son la configuración previa, no una
> autorización para reanudar. n8n y los demás agentes no se suspendieron.

**Corte:** 19 de noviembre de 2026, aproximadamente 21:15, hora de Ciudad de México.
**Zona horaria única:** `America/Mexico_City`.
**Objetivo:** que otro agente pueda entender, operar y continuar el montaje sin reconstruir el chat.

**Actualización posterior:** consulta el [segundo hand-off](HANDOFF-FACTORY-KANBAN-02.md)
y la [guía vigente de Codex](kanban-operation/sequential/codex.md). El operador
cambió la ventana futura del MVP a 15:00–17:30, con una tarjeta a la vez,
README de arranque inmediato, 3–5 pruebas y bloqueo explícito por falta de
accesos. Codex sigue suspendido; el horario histórico de este documento no
es una orden de reanudación.

## 1. Punto exacto de continuación

El sistema está desplegado con coordinación determinista por cron y estados en base de datos. El trabajo de investigación, evaluación y construcción lo hacen los agentes en sus turnos; n8n coordina y valida contratos de entrega sin usar un LLM.

La última instrucción del operador es **no cambiar nada de la ejecución ni iniciar una corrida extraordinaria hoy**. Se retoma mañana, **20 de noviembre de 2026**, con los horarios normales. El presente hand-off se crea únicamente como documentación. No se habilitó ninguna excepción de horarios.

Estado consultado al preparar este documento:

| Elemento | Estado observado |
| --- | --- |
| Kanban app | Contenedor ejecutándose |
| PostgreSQL de Kanban | Saludable |
| MegaMCP | Saludable; imagen `mega-mcp-dot-bridge:20261119-workspace` |
| Túnel Cloudflare | Contenedor `bibi-cloudflared` ejecutándose |
| Tres workflows de fábrica en anyo | Publicados, activos y sin cambios de borrador pendientes |
| Timer de Codex | Próxima ejecución: 20-11-2026 a las 16:00 |
| Último estado del coordinador | `last_error=null`; actualización aproximada 21:15 local |
| Pipelines de oportunidades | 7 en `EVALUATING`, 3 en `RESEARCH` |
| Tarjetas de investigación | 7 `done` y 3 `ready`, asignadas a Brio |
| Tarjetas de evaluación | 7 `ready`, asignadas a Bacha |
| Tarjetas de construcción/cierre de esta fábrica | Ninguna creada todavía en la consulta de corte |

Estos son datos de una instantánea, no valores que otro agente deba imponer. Antes de actuar, consulta de nuevo las tarjetas y los estados reales. El usuario reportó que la corrida se interrumpió porque Brio se detuvo o se extendió sobre su turno. No borres el acumulado ni recrees oportunidades para recuperarlo.

**Distinción de validaciones:** Dot ya confirmó su identidad y acceso desde su chat. El nuevo intercambio de ZIP completo se validó del lado del servidor y del SDK instalado; falta verificar desde el cliente real de Dot la descarga materializada en su workspace y la subida de un archivo local. No afirmar que esa parte ya quedó validada por Dot.

## 2. Proyecto, repositorios y ubicaciones

| Dato | Valor |
| --- | --- |
| Repositorio principal | https://github.com/sesalin/agent-kanban |
| Rama de trabajo | `main` |
| Versión declarada | `0.1.0`, Python `>=3.11` |
| Checkout WSL | `/home/cheko/_proyects/agent-kanban` |
| Stack | FastAPI, MCP Streamable HTTP, PostgreSQL y frontend React |
| Proyecto operativo en Kanban | **ID 1**, nombre `Kanban` |
| Raíz de paquetes en WSL/Windows | `/mnt/c/_mcp/muse-packages` |
| Raíz equivalente en contenedores | `/muse-packages` |
| Checkout del MCP compartido | `/mnt/c/_mcp/mega-mcp` |
| Registro del MCP en ChatGPT | **obsidian-mcp**; corresponde al contenedor MegaMCP existente |
| Último cambio funcional al corte | `dcb4575`, transferencia de ZIP entre MCP y workspace de Dot |
| Cambio anterior | `613d840`, puente de Dot y construcciones paralelas |
| Base de coordinación por cron | `86101f9`, fábrica por horarios y estados |

Los tres commits funcionales estaban publicados en `origin/main`. El documento presente se agrega después de ellos; su propio commit no se utiliza como versión funcional de la aplicación.

**Hay dos bases distintas:** PostgreSQL local de Kanban guarda tarjetas, permisos y actividad. Supabase `radars-n8n` guarda radares y pipelines. No son intercambiables.

## 3. Reparto vigente

| Actor | Responsabilidad | Resultado |
| --- | --- | --- |
| Automatizaciones de búsqueda | Encontrar señales/radares y persistir registros | Registros en la base de radares |
| Automatizaciones de análisis | Analizar señales, decidir si preparar investigación y producir el paquete inicial | Estado de análisis y ZIP inicial disponible |
| n8n, identidad `n8n-radares` | Conciliar, despachar tarjetas, validar ZIP/JSON y avanzar estados | Tarjetas y pipeline coherentes; informe por Telegram |
| Brio, Muse | Investigar evidencia, mercado y regulación | `research.zip` |
| Bacha, Muse | Evaluación GO/NO_GO y especificaciones; después prospección; después cierre | `decision.zip`, `prospects.zip`, `close.zip`, cada uno en su propia tarjeta |
| Codex, CLI en WSL | Construir y probar únicamente el MVP | `mvp.zip` |
| Dot, vía obsidian-mcp | Desarrollar, analizar y probar únicamente la landing en su propio workspace | `landing.zip` |
| Operador humano | Administrar, configurar programaciones externas y resolver recuperaciones explícitas | Supervisión y decisiones operativas |

Bacha conserva rol `orchestrator` en Kanban y permiso de reclamar. En esta fábrica, la creación y aprobación técnica de tarjetas las realiza el coordinador de n8n. Bacha no debe duplicar esas operaciones ni atribuirse cambios efectuados por n8n u otro agente.

Nod, Instinct y Hermes **no participan en el reparto vigente**. Otras identidades emitidas pueden seguir existiendo; eso no las convierte en participantes de esta fábrica.

## 4. Calendario completo

Todos los horarios son diarios en **America/Mexico_City**; no utilizar UTC ni una diferencia horaria fija en las programaciones.

| Hora | Responsable | Actividad |
| --- | --- | --- |
| 08:28 | Búsqueda existente | Gobierno NL |
| 09:00 | Análisis existente | Gobierno NL |
| 09:40 | Búsqueda existente | Compras Públicas |
| 10:00 | Análisis existente | Compras Públicas |
| 10:40 | Búsqueda existente | Regulación Federal |
| 11:00 | Análisis existente | Regulación Federal |
| 11:40 | Búsqueda existente | Competencia ServicePlace |
| 12:00 | Análisis existente | Competencia ServicePlace |
| 12:20–22:00, cada 5 minutos | n8n | Conciliación determinista |
| 12:30 | Brio | Investigación |
| 15:00 | Bacha | Evaluación GO/NO_GO |
| **16:00** | **Codex** | **MVP, en paralelo** |
| **16:00** | **Bacha** | **Prospectos y textos comerciales, en paralelo** |
| **16:00** | **Dot** | **Landing, en paralelo** |
| 19:00 | Bacha | Cierre de oportunidades con todas sus ramas activas terminadas |
| 19:30–22:00, cada 5 minutos | n8n | Entregar el informe diario pendiente por Telegram y reintentar si hace falta |

Los horarios de búsqueda/análisis son los proporcionados por el operador y conservados en las instrucciones; no se reprogramaron como parte de este hand-off. Competencia ServicePlace mantiene su recorrido de seguimiento; el coordinador actual admite paquetes desde las tres tablas de Gobierno NL, Compras y Regulación.

### Ventanas que aplica el servidor

| Etapa | Identidad autorizada | Nuevos reclamos permitidos |
| --- | --- | --- |
| `research` | `brio` | 12:30–14:59 |
| `evaluation` | `bacha` | 15:00–15:59 |
| `mvp` | `codex` | 16:00–17:59 |
| `prospection` | `bacha` | 16:00–17:59 |
| `landing` | `dot` | 16:00–17:59 |
| `final` | `bacha` | 19:00–19:29 |

Estos límites están implementados en `src/agent_kanban/factory_schedule.py`. Un arranque manual fuera del horario no evita el control: puede devolver `outside the daily factory window`. No se agregó una excepción para la noche del 19 de noviembre.

Los límites operativos recomendados son más conservadores:

- Brio: unos 30 minutos por tarjeta, sin reclamar otra después de 14:15; objetivo de entrega 14:45. Captchas o descargas fallidas se documentan como lagunas, sin inventar datos ni esperar horas.
- Bacha: no iniciar otra evaluación después de 15:30 y entregar la activa antes de 15:45, para dar al cron tiempo de preparar paquetes antes de las 16:00.
- Constructores: objetivo de entregar antes de 18:45, para permitir validación y preparación del cierre de las 19:00.
- Cada agente, después de entregar, consulta su siguiente tarjeta propia y continúa dentro de su ventana. El acumulado puede requerir varios días; no se exige vaciarlo falseando resultados.

Brio y Bacha son dos Muse que **no deben trabajar simultáneamente**. Kanban bloquea un nuevo reclamo de cualquiera de ellos si hay una tarjeta activa de Muse en el proyecto 1 según la guardia implementada. Codex y Dot sí pueden trabajar al mismo tiempo que Bacha.

Un trabajo ya reclamado puede terminar después de la ventana y seguir enviando heartbeat. Eso no habilita nuevos reclamos. Un reclamo abandonado no se libera automáticamente.

**n8n no despierta a los agentes:** Brio/Bacha se programan en Muse; Dot en su plataforma con obsidian-mcp y su workspace; Codex usa systemd local. El operador había confirmado Brio/Bacha programados antes del cambio de reparto; las modificaciones posteriores y la programación de Dot requieren confirmación en sus plataformas, no se verificaron remotamente desde esta sesión.

## 5. Flujo de datos y estados

1. La búsqueda guarda un radar en Supabase.
2. El análisis actualiza el registro y prepara un ZIP inicial existente en disco. Para admitirlo, el coordinador exige `analysis_status=completed`, `muse_status=ready`, `package_status=ready` y que no exista pipeline previo para ese `event_id`.
3. Entre 12:20 y 14:59, n8n recoge nuevas oportunidades, conserva el original y prepara `01_input/paquete.zip`. Los paquetes nuevos posteriores quedan para la siguiente ventana de admisión.
4. Crea el pipeline y la tarjeta de investigación de Brio, con identidad, etapa, evento y rutas en metadatos.
5. Brio reclama, descarga por ID de tarjeta, investiga, sube `research.zip` y envía la tarjeta a `review`.
6. n8n comprueba archivo y contrato, aprueba técnicamente la tarjeta y crea la evaluación de Bacha.
7. Bacha evalúa y entrega `decision.zip` con `decision.json`. n8n valida su esquema estricto y correspondencia con el evento y la tarjeta de Brio.
8. Si es NO_GO, el pipeline queda `REJECTED`, con justificación, sin construcciones.
9. Si es GO, el coordinador genera automáticamente las especificaciones y ZIP de cada rama habilitada, y crea sus tarjetas **juntas**, asignadas a Codex, Bacha y Dot respectivamente.
10. Cada constructor reclama su tarjeta, trabaja y entrega el ZIP en su resultado. Una rama puede entregar antes que las otras; no necesita esperar al MVP para comenzar prospección o landing.
11. Cuando todas las ramas activas están `DONE`, se prepara el paquete final y la tarjeta de cierre de Bacha. Una rama deshabilitada queda `SKIPPED` y no requiere tarjeta ni entrega.
12. Bacha revisa coherencia y límites de los entregables y entrega `close.zip` con `close.json`.
13. n8n valida, completa la oportunidad, guarda el resumen y prepara el informe diario desde las 19:30. El workflow Telegram envía el informe y registra su `message_id`.

Estados de `opportunity_pipelines.stage`:

```text
RESEARCH → EVALUATING ── GO ──→ BUILDING → FINAL_REVIEW → DONE
                   └── NO_GO → REJECTED
```

La decisión NO_GO sale de EVALUATING, antes de entrar a BUILDING. El campo técnico sigue siendo **`factory_mode=sequential`** por compatibilidad; ese nombre no significa que las tres construcciones sigan ejecutándose una detrás de otra.

Las tarjetas usan su propio ciclo `ready → in_progress → review → done`. Un agente mueve una tarjeta mediante las transiciones autorizadas de reclamar, entregar y revisar; no tiene el permiso de edición libre de columnas de una sesión humana. Todo trabajo, resultado, progreso y revisión permanece vinculado a una tarjeta.

El coordinador usa bloqueo para evitar dos conciliaciones simultáneas y una clave estable `<event_id>:sequential:<factory_step>` para no duplicar despachos en reintentos. No regenerar oportunidades, cambiar sus IDs ni crear tarjetas manuales paralelas a ese mecanismo.

## 6. Contrato de archivos: quién los crea y cómo se identifican

**Bacha redacta el contenido de las especificaciones en `decision.json`. El coordinador invocado por n8n genera los `.md` y los paquetes de construcción.** Bacha confirmó que ya corrigió su interpretación: no debe confeccionar esos tres `.md` dentro de `decision.zip`.

Cada oportunidad tiene su carpeta:

```text
/mnt/c/_mcp/muse-packages/<event_id>/
├── 01_input/paquete.zip
├── 02_research/research.zip
├── 03_specs/
│   ├── decision.zip
│   ├── decision.json
│   ├── mvp_spec.md
│   ├── mvp-input.zip
│   ├── icp_spec.md
│   ├── prospection-input.zip
│   ├── landing_spec.md
│   └── landing-input.zip
├── 04_mvp/mvp.zip
├── 05_prospects/prospects.zip
├── 06_landing/landing.zip
└── 07_release/
    ├── final-input.zip
    ├── close.zip
    └── resumen_ejecutivo.md
```

Los archivos de ramas deshabilitadas pueden no existir. Los agentes descargan **por ID de su tarjeta**, nunca buscan globalmente un nombre de archivo repetido. `event_id`, proyecto, asignación y `metadata_payload.muse_zip` determinan la entrada y el destino exactos.

| Etapa/agente | ZIP de entrada | Contenido principal | ZIP de salida |
| --- | --- | --- | --- |
| Investigación / Brio | `paquete.zip` | Dossier inicial preparado por el análisis | `research.zip` |
| Evaluación / Bacha | `research.zip` | Investigación | `decision.zip` |
| MVP / Codex | `mvp-input.zip` | `mvp_spec.md` y `research.zip` | `mvp.zip` |
| Prospección / Bacha | `prospection-input.zip` | `icp_spec.md` y `research.zip` | `prospects.zip` |
| Landing / Dot | `landing-input.zip` | `landing_spec.md` y `research.zip` | `landing.zip` |
| Cierre / Bacha | `final-input.zip` | Decisión, investigación y ZIP de las ramas activas | `close.zip` |

Archivos exigidos en las entregas:

- `research.zip`: `hallazgos.md`, `fuentes.json`, `propuesta_mvp.md` en la raíz.
- `decision.zip`: `decision.json` en la raíz; puede incluir análisis complementario, pero no necesita los tres `.md` de especificación.
- `prospects.zip`: `leads.csv`, `outreach_copies.md` en la raíz. Los prospectos son verificables; no enviarles mensajes comerciales como parte de este flujo.
- `landing.zip`: proyecto terminado y probado por Dot, recursos necesarios y `README.md` en la raíz. Excluir secretos, `.git`, dependencias instaladas y temporales.
- `mvp.zip`: proyecto reproducible, README, configuración de ejemplo sin secretos y comprobaciones razonables.
- `close.zip`: `close.json` en la raíz, con `event_id` y `executive_summary`.

Ejemplo del contrato exacto de decisión; sustituir IDs e instrucciones por los reales:

```json
{
  "event_id": "ID_DEL_EVENTO",
  "brio_task_id": 123,
  "decision": "GO",
  "decision_notes": "Justificación contrastada con la evidencia",
  "branches": {
    "run_mvp": true,
    "run_prospection": true,
    "run_landing": true
  },
  "specs": {
    "mvp_prompt": "Alcance del MVP, funciones y criterios de aceptación",
    "icp_prompt": "Perfil de cliente y criterios verificables de prospección",
    "landing_prompt": "Alcance de landing, público, propuesta y CTA"
  }
}
```

Las banderas son booleanos reales. GO exige al menos una rama activa y un prompt no vacío por rama activa. NO_GO exige las tres banderas en `false`. `brio_task_id` es un entero positivo de la investigación de ese evento, no el ID de la evaluación. El esquema rechaza campos adicionales.

## 7. Conexiones y autenticación

| Entrada | Dirección | Autenticación/uso |
| --- | --- | --- |
| Web humana pública | https://kk.okehc.com | Cloudflare Access y login de Kanban |
| Web local Windows | http://localhost:7331/ | Sesión web de Kanban |
| REST LAN, publicación Docker verificada | `http://192.168.100.91:7331` | Bearer propio de Kanban; IP del host a comprobar si cambia la red |
| MCP LAN | `http://192.168.100.91:7331/mcp/` | Bearer propio de Kanban |
| REST público de agentes | `https://kanban-api.okehc.com` | Un solo Bearer de la identidad |
| MCP público de agentes | `https://kanban-api.okehc.com/mcp/` | Streamable HTTP, mismo Bearer |
| n8n operativo | https://anyo.okehc.com | Credenciales de n8n ya guardadas en la instancia |
| Dot | Conexión existente **obsidian-mcp** | Bearer guardado en el servidor MegaMCP; no pedirlo en el chat |

MCP también utiliza HTTP; REST y MCP son dos interfaces de aplicación, no dos redes diferentes.

El intermediario Cloudflare `kanban-bacha-rest` reconoce el Bearer del agente y agrega las credenciales de máquina de Cloudflare Access para llegar al origen protegido `kk.okehc.com`. Los clientes del intermediario no envían las tres cabeceras. El origen continúa protegido. No quitar Access ni publicar el puerto 7331 para resolver una limitación del cliente.

El puerto 7331 se publica actualmente en localhost y en la IP LAN indicada. No debe existir reenvío de ese puerto desde el router público. Una publicación LAN no acredita por sí sola las reglas del router; este hand-off no hizo una auditoría externa de red.

Bacha/Brio pueden usar el MCP público y REST con su Bearer propio. Para REST:

- Entrada: `GET /api/tasks/{ID}/package/input`, después de reclamar. La lectura requiere el reclamo activo correspondiente.
- Salida: **PUT** `/api/tasks/{ID}/package/result`, ZIP crudo, `Content-Type: application/zip`; confirmar **201**. No POST ni multipart.
- Enviar a revisión mediante `submit_for_review` o `POST /api/tasks/{ID}/submit`, conservando el vínculo al resultado en artifacts.
- La subida REST permite hasta **10 MiB** y conserva el primer resultado; no sobrescribir ni borrar automáticamente ante un 409.

### Dot: solo transporte MCP, desarrollo en su workspace

Herramientas vigentes:

```text
factory_dot_status
factory_dot_list_tasks
factory_dot_get_task
factory_dot_claim_task
factory_dot_heartbeat
factory_dot_download_input
factory_dot_list_input_files
factory_dot_read_input_file
factory_dot_upload_result
factory_dot_submit_review
```

Ciclo de Dot: reclamar → descargar ZIP completo a su workspace → verificar hash → desarrollar, analizar y probar allí → crear `landing.zip` allí → subir archivo nativo por MCP → verificar bytes/hash y `uploaded=true` → enviar a revisión → consultar siguiente propia.

**Corrección del 20-11-2026 sobre reclamos:** Dot reportó que la tarjeta #34
estaba `in_progress` y `claimed_by=dot`, pero se detuvo porque no vio `ok=true`.
Ese reporte proviene del agente; no es una nueva consulta productiva realizada
para este hand-off. La regla vigente exige consultar
`factory_dot_get_task(task_id)` y confirmar `project_id=1`, `assigned_to=dot`,
`status=in_progress` y `claimed_by=dot`. Si ya cumple esas condiciones, se
retoma sin volver a reclamar, aunque la respuesta previa no incluyera `ok`.
Si algún campo difiere o la consulta falla, se detiene y reporta. Se aplica
a todas las tarjetas. No se cambiaron permisos ni lógica del servidor para
esta corrección de instrucciones. La instantánea del inicio sigue fechada
el 19 de noviembre y no representa el estado actual de la #34.

**Corrección de descarga del 20-11-2026:** `factory_dot_download_input` ahora adjunta los bytes completos del ZIP como `EmbeddedResource` (`resource.blob`, MIME `application/zip`), junto con tamaño y SHA-256. La URI identificadora es `kanban-dot://tasks/<ID>/landing-input.zip`, pero no se necesita resolverla: el contenido viene en esa misma respuesta. Se desactiva la salida estructurada duplicada para no enviar otra copia JSON del binario al modelo. El contrato anterior entregaba solo un `resource_link` con una URI `mcp-file://` generada por el servidor y Dot reportó `Unknown resource (-32002)` con la #34. Solicitar una nueva descarga, no reutilizar esa respuesta antigua. El agente todavía debe confirmar la materialización real en su propio workspace; un adjunto anunciado sin archivo local no acredita ese paso.

`factory_dot_upload_result(task_id, file)` declara `openai/fileParams`; el host debe transformar el archivo local del agente en referencia temporal descargable. No pasar un path local del workspace como si el MCP pudiera abrirlo. No usar base64 por el chat. El servidor comprueba el ZIP, descarga sin reenviar el token de Kanban y guarda los bytes originales en el resultado canónico de la tarjeta.

El puente acepta solo la tarjeta propia del proyecto 1, reclamada por Dot, con los metadatos canónicos de landing. No permite elegir rutas arbitrarias del servidor. Admite recursos binarios y proyectos con framework: límite 10 MiB comprimidos, 100 MiB descomprimidos y 2000 entradas, con README en la raíz. No extrae ni ejecuta el proyecto en el host del MCP.

El recibo `.dot-transfer/task-<ID>/uploaded.json` queda en la carpeta de la landing únicamente para trazabilidad de la transferencia; no es el workspace de desarrollo.

**Se retiraron** `factory_dot_write_output_file`, `factory_dot_read_output_file` y `factory_dot_publish_result`. Refrescar el catálogo de obsidian-mcp para ver el contrato nuevo. No reutilizar las herramientas antiguas `kanban_*` o `agent_*` de MegaMCP: corresponden a otro servicio, no a Agent Kanban 7331.

### Codex: ejecución local independiente

- Timer de usuario: `kanban-codex.timer`; servicio: `kanban-codex.service`.
- Lanzador: `deploy/factory/run-codex.py`; consulta cada cinco minutos de 16:00 a 17:55.
- Si no hay tarjeta propia de MVP, termina sin iniciar modelo. `--check` solo consulta.
- Lee `docs/kanban-operation/sequential/codex.md` en cada trabajo y conserva el modelo configurado en el CLI.
- Usa el MCP público y la variable `CODEX_KANBAN_TOKEN` del entorno privado; no la imprime.
- Construye dentro de la carpeta `04_mvp` de su evento en WSL, sin modificar este repositorio para realizar el MVP.
- No hace el trabajo de Dot ni recibe su workspace. WSL debe estar encendido y el CLI autenticado.

## 8. n8n y base de radares

**Instancia única para estos workflows: anyo.okehc.com.** No utilizar el host anterior `nn`.

| Workflow | ID | Función |
| --- | --- | --- |
| Fábrica secuencial - Conciliar cada 5 minutos | `qrBiN12e9J6bEvoc` | POST al coordinador, 12:20–22:00 |
| Fábrica secuencial - Entregar informe Telegram | `IDoapKWSS7Lg6eBH` | Leer informe no enviado, enviar y confirmar, 19:30–22:00 |
| Fábrica secuencial - Registrar fallos | `WIL1go2TjyOL1s68` | Error Trigger de los anteriores; registra referencias de ejecución |

El coordinador se llama en `POST https://kanban-api.okehc.com/api/factory/reconcile`. Su lógica determinista vive dentro de Kanban, no en un nodo de IA. Una invocación manual **puede crear/aprobar tarjetas y cambiar estados**; no usarla como prueba inocua de conectividad.

Credenciales de n8n, por nombre, sin valores:

- `N8N_RADARES_KANBAN`: tipo Bearer Auth; el campo contiene el token sin prefijo `Bearer`.
- `RADARS_SUPABASE`: Supabase API del proyecto de radares.
- `Telegram Cheko`: Telegram API; destino `7946431920`.

**Única base Supabase autorizada para esta fábrica:** `radars-n8n`, proyecto `uobeshcvmtawjxibciuy`, URL `https://uobeshcvmtawjxibciuy.supabase.co`. Comprobar el project ID antes de cualquier consulta o migración. No tocar otras bases conectadas.

Tablas relevantes:

| Tabla | Uso |
| --- | --- |
| `radar_gobierno_nl` | Fuente de oportunidades Gobierno NL |
| `radar_compras_publicas` | Fuente de oportunidades Compras |
| `radar_regulacion_federal` | Fuente de oportunidades Regulación |
| `opportunity_pipelines` | Estado, IDs de tarjetas, decisión, ramas, rutas y último error por evento |
| `factory_runtime` | Última conciliación, errores de origen y referencias de fallos de n8n |
| `factory_daily_reports` | Informe por fecha, `sent_at` y `telegram_message_id` |

Las funciones y tablas de coordinación restringen acceso a `service_role`; los agentes no reciben esa clave. La configuración privada de Supabase permanece en el contenedor Kanban. No ampliar acceso a anon/authenticated para resolver errores del pipeline.

El informe se construye una vez por fecha desde las 19:30: resume estados al corte y pendientes, no garantiza que todo acabó. Un cierre posterior no regenera el mensaje enviado. Si Telegram acepta un envío y falla su confirmación, puede duplicarse al reintentar; comprobar `message_id`, chat e historial antes de reenviar.

Los antiguos WF1–WF5 de fábrica por eventos están archivados. Evolution/WhatsApp se exploró antes, pero no es el mecanismo de coordinación vigente. Pueden existir componentes históricos; no reactivarlos ni borrarlos incidentalmente.

## 9. Archivos privados, despliegue y recuperación

Los valores secretos no forman parte de este documento ni del repositorio. Se guardan bajo `/home/cheko/.config/agent-kanban/`, con permisos privados.

| Archivo privado | Uso |
| --- | --- |
| `kk-compose.env` | Configuración sensible del despliegue Kanban |
| `kk-agents.env` | Bearer y credenciales de agentes existentes |
| `n8n-radares.env` | Variables de la identidad n8n y referencias históricas de integración |
| `factory.env` | URL y clave servidor de Supabase de radares |
| `codex-factory.env` | Entorno privado del lanzador local de MVP |
| `mega-mcp-dot.env` | Identidad Dot guardada en MegaMCP y URL interna de Kanban |

Compartir con cada agente solo su propia credencial cuando corresponda. Dot no necesita recibir token adicional en el chat. No copiar archivos privados a entregables, logs públicos, ZIP o Git; conservar las exclusiones existentes.

### Kanban

Contenedores: `agent-kanban-app-1` y `agent-kanban-postgres-1`. La instalación usa PostgreSQL **17** mediante override; el Compose base usa **16**. No ejecutar una restauración o reconstrucción con la versión equivocada sobre el volumen existente.

El despliegue utiliza `docker-compose.yml`, override privado `docker-compose.cloudflare.yml`, env privado `kk-compose.env`, red de túnel `bibi_edge` y el montaje de paquetes. Comando de actualización para un cambio funcional autorizado, **no necesario para leer este hand-off**:

```bash
docker compose -p agent-kanban \
  --env-file /home/cheko/.config/agent-kanban/kk-compose.env \
  -f docker-compose.yml -f docker-compose.cloudflare.yml \
  up -d --build app
```

Respaldar PostgreSQL local, Supabase, la raíz de ZIP y los secretos privados. El backup de base no incluye los archivos ZIP. Los Bearer originales no se recuperan a partir de sus hashes en Kanban.

Para reconstruir el esquema de fábrica en una instalación autorizada de la base de radares, seguir en orden los SQL de `deploy/factory/`: `supabase.sql`, `transitions.sql`, `sequential.sql`, `parallel.sql`. Los dos primeros forman el bloque de transacción histórico. En producción ya están aplicados: no ejecutarlos otra vez por rutina. Conservar RLS y privilegios privados.

### MegaMCP / obsidian-mcp

- Código operativo: `/mnt/c/_mcp/mega-mcp/app/mcp/factory_dot_bridge.py`.
- Registro: `app/mcp/http_server.py`, activación `FACTORY_DOT_BRIDGE_ENABLED=true`.
- Copia versionada del módulo y sus pruebas: `deploy/mega-mcp/` de este repositorio.
- Contenedor: `mega-mcp`; imagen activa `mega-mcp-dot-bridge:20261120-inline`.
- Override: `/mnt/c/_mcp/mega-mcp/docker-compose.override.yml`.
- Transporte cliente: túnel OpenAI ya existente; no se creó otro contenedor MCP ni un OAuth nuevo para Dot.
- Hacia Kanban: `http://host.docker.internal:7331`, con Bearer propio de Dot, sin pasar por Cloudflare para ese tramo interno.
- Raíz compartida de paquetes: `/mnt/c/_mcp/muse-packages`, vista como `/muse-packages`.
- Catálogo desplegado: 34 herramientas totales, 10 `factory_dot_*`.

**Precaución de código ajeno:** el checkout de MegaMCP tiene cambios pendientes del dashboard ajenos al puente. Las imágenes de Dot se construyeron sobre una imagen base conocida y solo incorporaron módulo/registro, preservando el dashboard desplegado. No hacer un build indiscriminado de ese checkout ni revertir cambios de otra persona. Consultar el procedimiento de imagen derivada en `kanban-operation/mega-mcp/README.md`.

No cambiar el túnel ni rotar tokens para resolver un catálogo antiguo. Refrescar obsidian-mcp y comprobar los nombres y metadata nuevos. El SDK instalado es 1.12.4; se conserva compatibilidad sin actualizar dependencias. La metadata de archivo nativo se añade al descriptor de la herramienta de subida mediante el handler de listado del SDK.

## 10. Verificaciones realizadas y límites pendientes

### Evidencia ya obtenida

- Pruebas de Kanban/coordinador sobre Postgres temporal: ciclo completo, tres reclamos de construcción coexistentes, entregas fuera de orden, cierre condicionado, NO_GO, idempotencia, permisos SQL, horarios, exclusión Muse, informe, orquestación y API de paquetes. Doce casos relevantes pasaron tras las correcciones.
- Suite del intermediario Cloudflare correcta, con acceso de Dot y rechazo de operaciones no permitidas a un worker.
- El puente inicial y HTTP tuvieron 17 comprobaciones correctas. Después se corrigió el contrato de workspace: las cinco pruebas del puente se actualizaron y pasaron para ZIP completo, binarios, rutas, identidad, reintento, archivo nativo y recurso MCP.
- Se verificó la transferencia simulada sin red ni secretos sobre el SDK 1.12.4 de la imagen real, además del catálogo, recurso binario y metadata de archivo por MCP HTTP desplegado.
- Dot confirmó desde su propio chat `connected=true`, `identity=dot`, `project_id=1`, `role=worker`. En esa consulta no había tarjetas listas propias.
- Workflows n8n validados, conexiones verificadas y versiones publicadas. Pruebas manuales 221/222 con nodos de red/Telegram simulados; no enviaron mensajes ni cambiaron datos. También se observaron ejecuciones reales de cron correctas y coordinador sin error.
- Se escanearon los cambios antes de los commits funcionales; no se encontraron valores de secretos privados. No se crearon pilotos ni se hizo investigación o desarrollo en nombre de los agentes.

### Lo que aún no debe darse por validado

1. Jornada completa con Brio, Bacha, Codex y Dot bajo el calendario nuevo.
2. Descarga real del recurso binario al workspace de Dot y subida nativa desde su cliente, después de refrescar el catálogo.
3. Que las tareas programadas externas conserven sus herramientas y el acceso al workspace; una validación interactiva no prueba una ejecución programada.
4. Confirmación de que el operador actualizó los tres turnos de Bacha y agregó Dot después del cambio de reparto. Bacha sí confirmó la corrección del contrato de decision.zip en sus instrucciones/memoria; eso no acredita los horarios por sí solo.
5. Recuperación del histórico: se documentaron 17 ZIP ausentes entre 26 registros marcados listos en una revisión anterior. No se restauraron ni reclasificaron; consultar la lista en `kanban-operation/sequential/incidencias.md`. Ese conteo es histórico, no una nueva consulta de archivos en este hand-off.

La validación técnica de ZIP/JSON no sustituye revisión semántica. Las entregas pueden estar estructuralmente correctas y contener investigación insuficiente. Bacha revisa la evidencia en evaluación y la coherencia en cierre.

Un resultado inválido puede bloquear el avance de su oportunidad hasta intervención; no se debe asumir aislamiento de todos los errores por rama. La conciliación procesa las ramas pendientes, pero una excepción durante una rama puede impedir procesar las siguientes de ese mismo evento en esa pasada. No esconder el error ni cerrar por horario.

## 11. Cómo retomar sin perder trazabilidad

1. Leer este documento y el prompt específico del actor antes de actuar. Conservar proyecto 1, `event_id`, IDs de tarjetas y rutas existentes.
2. Revisar la cola real de Brio/Bacha y los estados de Supabase; no actuar sobre la instantánea histórica como si fuera el estado actual.
3. Dejar la ejecución para el **20-11-2026 en sus horarios normales**, según la última instrucción humana. No liberar horario, permisos o reclamos para ejecutar de noche.
4. Brio continúa sus propias investigaciones pendientes. Bacha evalúa las investigaciones ya entregadas, sin depender de que se vacíe todo el acumulado de Brio; sí requiere que no siga activo el otro Muse al reclamar.
5. Tras GO, esperar a la conciliación para disponer de las tarjetas de cada rama. Los agentes usan el ID de su tarjeta para descargar; no piden a otro agente que les copie archivos por fuera del flujo.
6. Comprobar con Dot el intercambio real en la primera tarjeta de landing asignada. Si la plataforma no materializa el recurso o no admite el archivo nativo, registrar el paso exacto y el error; no volver a desarrollo archivo por archivo en el MCP ni asumir que Codex debe construir por Dot.
7. Si hay un bloqueo, documentarlo en la tarjeta y en docs con actor, hora, ID, paso y código HTTP/herramienta. No atribuir a un agente operaciones efectuadas por otro.
8. Hacer solo pruebas proporcionales al cambio que se esté corrigiendo. No ejecutar suites repetidas sin motivo, crear pilotos innecesarios ni tomar el trabajo de los agentes.

Comprobaciones operativas de solo lectura:

```bash
git status --short
docker ps --format '{{.Names}} | {{.Status}}'
systemctl --user status kanban-codex.timer
systemctl --user list-timers kanban-codex.timer
journalctl --user -u kanban-codex.service --since today
```

Consultar datos concretos sin imprimir tokens. Las llamadas que reclaman, suben archivos, envían a revisión, ejecutan conciliación o disparan Telegram tienen efectos reales; no confundirlas con verificaciones de lectura.

## 12. Mapa de código y documentación

| Ruta relativa al repositorio | Referencia |
| --- | --- |
| `src/agent_kanban/factory_coordinator.py` | Conciliación, contratos JSON, despacho de ramas, validación y reporte |
| `src/agent_kanban/factory_files.py` | Preparación de entrada, especificaciones y ZIP por rama |
| `src/agent_kanban/factory_schedule.py` | Actores, ventanas y exclusión de los Muse |
| `src/agent_kanban/routes/task_packages.py` | Entrada/salida de ZIP por ID, autorización y límites |
| `src/agent_kanban/routes/factory.py` | Endpoints privados de coordinación y confirmación de informe |
| `deploy/factory/` | SQL, generador de workflows, lanzador y unidades de Codex |
| `deploy/bacha-rest/` | Worker intermediario HTTPS y pruebas |
| `deploy/mega-mcp/` | Módulo de Dot y pruebas reproducibles del puente |
| `tests/test_factory_sequential.py` | Ciclo de fábrica, estados, ventanas y reporte |
| `tests/test_orchestration.py` | Contrato de orquestación; el nombre real lleva orchestration |
| `tests/test_task_packages.py` | Contrato de paquetes REST |

Documentación operativa relacionada:

- [Calendario y flujo general](kanban-operation/sequential/README.md).
- [Mensajes de programación para copiar](kanban-operation/sequential/programaciones.md).
- [Brio](kanban-operation/sequential/brio.md).
- [Bacha](kanban-operation/sequential/bacha.md).
- [Calidad de requerimientos de Bacha](kanban-operation/sequential/bacha-requerimientos.md): análisis del caso y prompt completo de las tres ramas.
- [Codex](kanban-operation/sequential/codex.md).
- [Dot: contrato vigente de workspace](kanban-operation/sequential/dot.md).
- [n8n](kanban-operation/sequential/n8n.md).
- [MegaMCP: despliegue y recuperación](kanban-operation/mega-mcp/README.md).
- [MegaMCP: catálogo y transferencia de Dot](kanban-operation/mega-mcp/dot.md).
- [Incidencias históricas y límites](kanban-operation/sequential/incidencias.md).
- [Ficha técnica y restauración de Kanban](kanban-operation/ficha-tecnica.md).
- [Inventario de identidades](kanban-operation/agentes.md).

La documentación histórica puede contener reparto anterior, horario Telegram 21:00, landing para Bacha, integración por eventos, usuarios retirados o la primera escritura de Dot archivo por archivo. Para continuar, prevalecen este hand-off, el código desplegado y los prompts vigentes de `sequential/`. Si divergen, verificar el estado real y documentar la diferencia antes de tocar producción.


## Actualización del 20-11-2026: requerimientos de Bacha

Se revisaron los tres encargos de la oportunidad de entornos digitales
seguros contra la investigación de Brio. MVP mezclaba aceptación del software
con resultados de un piloto de semanas y dependencias externas sin concretar;
prospección mezclaba investigación con entrevistas/ventas y ausencia de datos
con ausencia de capacidades del candidato; landing dejaba incompletos oferta,
operación de conversión y criterios de aceptación. No se revalidaron las
afirmaciones jurídicas o de mercado de esos insumos.

El operador aprobó el prompt de mejora. `bacha-requerimientos.md` forma parte
de la guía vigente de Bacha: exige una base comercial común, alcance realizable,
dependencias y faltantes explícitos, aceptación comprobable y separación entre
prototipo, sandbox, piloto y operación. En FINAL debe distinguir contrato
técnico, calidad del producto y preparación para publicar/vender.

El esquema de `decision.json` y sus tres campos de texto no cambian. n8n sigue
generando las especificaciones y paquetes; ninguna entrega previa se reescribió.
El agente Bacha debe recibir/cargar el prompt: documentarlo en el repositorio
no actualiza automáticamente su memoria o programación externa. No se cambiaron
servicios, horarios, permisos, tarjetas ni validadores mediante este ajuste.
