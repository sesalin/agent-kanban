# n8n — coordinación determinista

Instancia: **https://anyo.okehc.com**. Zona: **America/Mexico_City**.
No hay nodos de LLM ni mensajes para despertar a los agentes en estos flujos.

| Workflow | Horario | ID |
| --- | --- | --- |
| Conciliar cada 5 minutos | 12:20–22:00, diario | `qrBiN12e9J6bEvoc` |
| Entregar informe Telegram | Cada cinco minutos de 21:00 a 22:00 | `IDoapKWSS7Lg6eBH` |
| Registrar fallos | Error Trigger de los dos anteriores | `WIL1go2TjyOL1s68` |

El coordinador hace POST a
`https://kanban-api.okehc.com/api/factory/reconcile`, con la credencial
Bearer Auth `N8N_RADARES_KANBAN`. La lógica determinista reside en
`src/agent_kanban/factory_coordinator.py` y actúa por cuenta de esa identidad.
Su conexión privada a Supabase está en el contenedor Kanban; los workers no
reciben la clave de servidor. Solo acepta el proyecto `radars-n8n`,
`uobeshcvmtawjxibciuy`.

## En cada ejecución

1. Toma un bloqueo de coordinador para evitar dos conciliaciones simultáneas. Otra ejecución devuelve `already_running`.
2. Entre 12:20 y 14:59 busca paquetes con análisis `completed`, `muse_status=ready` y `package_status=ready`, sin pipeline previo. La consulta considera Gobierno NL, Compras y Regulación; Competencia conserva su recorrido de seguimiento sin Muse.
3. Comprueba el ZIP, conserva el original y prepara la copia canónica. Un origen inválido se registra en `factory_runtime` como `source:<event_id>` y tiene una espera de una hora antes de intentar de nuevo.
4. Crea el pipeline secuencial y la tarjeta de investigación. Usa una clave estable `<event_id>:sequential:<paso>` para que los reintentos recuperen la misma tarjeta.
5. Consulta todos los pipelines secuenciales activos, por páginas. Solo acepta una entrega de su tarjeta, proyecto y actor correctos, en `review` o ya en `done` por un reintento.
6. Valida el ZIP, sus límites y checksum. Investigación y prospección requieren los archivos indicados en los prompts. Evaluación y cierre requieren JSON con esquema estricto.
7. Aprueba la tarjeta y avanza la transición en Supabase. Si falta la transición después de aprobar, el siguiente intento puede recoger la tarjeta `done`. Solo crea la siguiente etapa activa: investigación → evaluación → MVP → prospección → landing → cierre.
8. Las ramas desactivadas quedan `SKIPPED`; NO_GO cierra como `REJECTED`. No se crean todas las ramas en paralelo.
9. El horario de reclamo se comprueba también en Kanban. Los Muse no pueden reclamar otro trabajo mientras haya uno suyo en progreso en el proyecto 1.
10. A partir de las 21:00 prepara un informe persistido por fecha. El informe resume estados al corte, cierres recientes y cantidad de incidencias de origen.

## Informe y fallos

`Telegram Cheko` es una credencial Telegram API. El destinatario es el chat
`7946431920`. El flujo lee el informe no enviado más antiguo, lo envía y
confirma su `message_id` con POST a `/api/factory/reports/<fecha>/sent`.
El informe queda pendiente cuando Telegram falla. No vuelve a construir
entregables para reintentar un mensaje.

Existe una ventana de duplicación si Telegram acepta el mensaje y falla la
confirmación posterior. Comprueba la ejecución y el chat antes de reenviar
manualmente. El registro conserva `telegram_message_id` y `sent_at`.

El Error Trigger registra únicamente IDs de workflow y ejecución en
`factory_runtime`; consulta el detalle del fallo en el historial de n8n. Si
Kanban o Supabase están caídos, también puede fallar ese registro: el historial
de ejecución de n8n sigue siendo la referencia. No actives ni importes los
WF1–WF5 históricos por eventos; están archivados.

## Credenciales y restauración

- `N8N_RADARES_KANBAN`: Bearer Auth, valor sin prefijo Bearer.
- `RADARS_SUPABASE`: Supabase API del proyecto de radares; se usa para leer los informes pendientes.
- `Telegram Cheko`: Telegram API; Access Token sin prefijo Bearer.
- Los JSON de `workflows/` contienen referencias, nunca claves.
- Generador: `deploy/factory/sequential-workflows.mjs`.
- Migraciones: `supabase.sql`, `transitions.sql` y después `sequential.sql` en `deploy/factory/`.

Las búsquedas y análisis mantienen sus horarios y accesos existentes. El
coordinador recoge su resultado persistido por consulta; no depende de que el
generador de paquetes llame WF1 ni de webhooks de finalización de los workers.
