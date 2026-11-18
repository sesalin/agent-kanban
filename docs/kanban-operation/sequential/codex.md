# Codex — MVP local en WSL

Identidad: **codex**. Proyecto: **1**. Zona: **America/Mexico_City**.
Inicio de ventana: **16:00**. Nuevos reclamos permitidos hasta **17:59**.
El temporizador local consulta cada cinco minutos dentro de esa ventana y
solo inicia el modelo cuando encuentra una tarjeta de MVP secuencial.
Conserva el modelo ya configurado en el CLI; el lanzador no selecciona otro.

MCP Streamable HTTP: `https://kanban-api.okehc.com/mcp/`, con Bearer de
`CODEX_KANBAN_TOKEN`. REST usa `https://kanban-api.okehc.com` y el mismo
Bearer. El lanzador pasa la credencial al transporte MCP mediante una variable
de entorno. No imprimas tokens ni copies archivos privados a un entregable.

## Instrucciones de ejecución

1. Consulta `list_my_tasks({"project_id":1})`, filtra `assigned_to=codex`, `metadata_payload.factory_mode=sequential` y `factory_step=mvp`. Sigue el orden de prioridad. Si se indicó un ID inicial, comprueba esos mismos datos antes de usarlo.
2. Reclama con `claim_task({"task_id":ID})` y exige `ok=true`. Un conflicto de horario o de reclamo no autoriza cambiar permisos, crear otra tarjeta ni usar otra identidad.
3. Descarga el ZIP de entrada con `GET /api/tasks/{ID}/package/input`. También puedes leer `03_specs/mvp_spec.md` bajo `/mnt/c/_mcp/muse-packages/<event_id>/`. El paquete incluye `research.zip`.
4. Construye únicamente el MVP especificado, dentro de `/mnt/c/_mcp/muse-packages/<event_id>/04_mvp/`. No modifiques este repositorio Kanban ni Supabase de producción para construir el MVP.
5. Incluye código funcional, `.env.example` sin secretos, `README.md` con comandos de arranque y una comprobación razonable de las funciones pedidas. No generes una batería interminable de pruebas ni agregues funciones no solicitadas.
6. Mantén heartbeat con `heartbeat_and_progress` aproximadamente cada cinco minutos. Si una dependencia requiere permiso que tu entorno no concede, documenta el bloqueo en la tarjeta y termina; no omitas el sandbox ni los controles del CLI.
7. Entrega `mvp.zip`, sin `.git`, `node_modules`, credenciales ni archivos temporales. Puedes escribirlo directamente en `04_mvp/mvp.zip` de WSL o subirlo con PUT binario a `/api/tasks/{ID}/package/result`, `Content-Type: application/zip`, límite de subida 10 MiB. Conserva el archivo original de entrada.
8. Verifica el ZIP. Ejecuta `submit_for_review` con `task_id`, resumen de lo hecho y probado y URL del resultado en `artifacts`; confirma `review`.
9. No llames `/factory/branch-done` ni otros callbacks. El coordinador valida la tarjeta y el archivo en su próxima ejecución programada.
10. Consulta otra vez tu cola y continúa con la siguiente tarjeta propia mientras la ventana siga abierta. Después de las 18:00 termina el trabajo ya reclamado; no inicies otro.

No informes como probado o desplegado lo que no ejecutaste. Si no hay tarjetas
propias, termina sin crear un proyecto de ejemplo. Una entrega rechazada o un
reclamo abandonado se revisa explícitamente; no ejecutes dos sesiones sobre
la misma tarjeta.

## Lanzador y operación

- Script: `deploy/factory/run-codex.py` del repositorio Kanban.
- Unidades de usuario: `kanban-codex.timer` y `kanban-codex.service`.
- Variables privadas: `~/.config/agent-kanban/codex-factory.env`, modo 0600.
- Logs privados: `~/.local/state/agent-kanban/codex-*.log`.
- El CLI usa `--approve-for-me`, conserva el sandbox y no usa `--yolo`.
- WSL necesita estar encendido y la sesión del CLI debe seguir autenticada. La unidad tiene un límite de seis horas por ejecución; si se interrumpe, verifica el reclamo antes de recuperarlo.

```bash
systemctl --user status kanban-codex.timer
systemctl --user list-timers kanban-codex.timer
journalctl --user -u kanban-codex.service --since today
```

El temporizador no arranca tarde para recuperar una ventana perdida. Si WSL
estaba apagado, la cola se conserva para la siguiente ventana diaria.
