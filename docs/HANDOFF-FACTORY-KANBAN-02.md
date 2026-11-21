# Hand-off 02 — revisión de calidad y suspensión de Codex

**Fecha:** 20 de noviembre de 2026. **Zona:** `America/Mexico_City`.
**Proyecto Kanban:** 1. **Repositorio:** `/home/cheko/_proyects/agent-kanban`, rama `main`.

Este documento complementa [el primer hand-off](HANDOFF-FACTORY-KANBAN.md).
Para decisiones posteriores al 19 de noviembre, prevalece esta actualización.
No se cambia ni se reinicia ningún servicio al crear este documento.

## 1. Decisión operativa vigente

El operador consideró insatisfactoria esta ronda: calidad de las landings,
encargos insuficientemente definidos, decisiones GO que requieren revisión
y ejecución acumulada que no debe seguir creciendo sin corregir el método.

**Instrucción explícita: detener las ejecuciones del worker de MVP de Codex.**
Se suspendió el mecanismo local de esa fábrica:

- `kanban-codex.service`: `inactive`, `dead`, `MainPID=0`.
- `kanban-codex.timer`: `inactive`, `dead`, **disabled**.
- No había próximas ejecuciones del timer después de detenerlo.
- No se identificaron procesos `run-codex.py` o `codex exec` de esa fábrica
  en la comprobación posterior.
- No se cerró la aplicación Codex ni procesos interactivos ajenos identificados
  como tales; la suspensión corresponde al worker de MVP del Kanban.
- No se liberaron reclamos, cancelaron tarjetas, borraron archivos ni cambiaron
  estados por el hecho de detener el servicio.

**No reactivar Codex, su timer ni recuperar sus tarjetas sin nueva instrucción
del operador.** Tampoco actualizar los encargos de tarjetas activas o sobrescribir
los paquetes para introducir las nuevas especificaciones.

Bacha, Dot y n8n no recibieron orden de suspensión en esta conversación.
La conciliación puede seguir cambiando estados y preparando trabajo; parar
Codex no congela toda la fábrica. No asumir que la cola deja de crecer solo
porque su temporizador se deshabilitó.

## 2. Estado observado al preparar este hand-off

Consulta de solo lectura del PostgreSQL de Kanban, después de suspender Codex:

| Agente | Etapa | Estado | Cantidad |
| --- | --- | --- | --- |
| Bacha | Evaluación | `done` | 10 |
| Bacha | Prospección | `done` | 10 |
| Bacha | Cierre | `ready` | 3 |
| Codex | MVP | `in_progress` | 6 |
| Codex | MVP | `done` | 1 |
| Dot | Landing | `ready` | 6 |
| Dot | Landing | `done` | 1 |

El operador había reportado aproximadamente diez tarjetas de Codex activas y
que probablemente no terminaría por la calidad del encargo. La consulta posterior
no coincide exactamente con ese conteo: muestra seis activas y una terminada.
No se reconstruyó la causa de esa diferencia ni se atribuyó a una acción concreta.
Un estado `in_progress` o un heartbeat antiguo no prueba ejecución actual.

Estos conteos son una instantánea: consultar nuevamente antes de operar. No
identifican por sí solos la calidad o validez comercial de los entregables.
La razón por la que algunas oportunidades no tienen todas las ramas no se
investigó en esta actualización; no deducirla únicamente de los totales.

## 3. Lo ocurrido con Dot

### 3.1. Se corrigió el lugar de desarrollo

El primer puente permitía escribir archivos individuales y empaquetarlos en
el host MCP. El operador corrigió el requisito: **Dot desarrolla, analiza y
prueba en su propio workspace**. MCP únicamente transporta la entrada y recibe
el ZIP terminado. Codex no debe hacer el desarrollo de la landing por Dot.

Se retiraron `factory_dot_write_output_file`, `factory_dot_read_output_file`
y `factory_dot_publish_result`. La conexión sigue siendo **obsidian-mcp**,
el MegaMCP existente en `/mnt/c/_mcp/mega-mcp`; no se creó otro MCP/túnel.

### 3.2. Se corrigió la confirmación de reclamo

Dot reclamó la #34 pero se detuvo porque no recibió literalmente `ok=true`.
La instrucción se corrigió: consultar `factory_dot_get_task(task_id)` y
confirmar simultáneamente:

```text
project_id=1
assigned_to=dot
status=in_progress
claimed_by=dot
```

Si ya cumple esos cuatro campos, retomar la misma tarjeta **sin reclamarla
otra vez**. Si difieren o falla la consulta, detenerse y reportar. La regla
aplica a todas sus tarjetas; no altera permisos ni permite trabajar sin reclamo.

### 3.3. Se corrigió la descarga binaria

La primera descarga devolvía tamaño, hash y un `resource_link` con una URI
`mcp-file://` generada por el servidor. Dot reportó `Unknown resource (-32002)`
y ningún ZIP materializado en su workspace.

Se cambió `factory_dot_download_input` para adjuntar los bytes completos del
ZIP como `EmbeddedResource` (`resource.blob`, MIME `application/zip`) en la
misma respuesta. La codificación base64 es interna del protocolo, no contenido
que deba pegarse manualmente en el chat. Se evita duplicar el binario en
`structuredContent`. No hace falta resolver una segunda URI para obtenerlo.

Imagen desplegada: `mega-mcp-dot-bridge:20261120-inline`.
Se validaron las cinco pruebas del puente, el SDK 1.12.4 de la imagen y la
respuesta real por obsidian-mcp. La entrada de la #34 tenía **25 392 bytes** y
SHA-256 `876ec821cf68f393b6dbe4fc87f129d9c6bcc0b85cdb8fef792309bc2d80fb24`.
Dot luego confirmó que la guardó en su workspace y que el hash coincidía.
Ese paso ya no debe figurar como pendiente para esta entrada concreta.

### 3.4. Se entregó la primera landing, pero se cuestionó su calidad

Dot reportó que desarrolló la landing, subió `landing.zip`, confirmó tamaño/hash
y envió la #34 a revisión. También informó pruebas locales correctas y revisión
visual Chromium pendiente. Posteriormente se consultó la #34 en `done`.

El ZIP original guardado existe en:

```text
/mnt/c/_mcp/muse-packages/regulacion-federal-20261014-dof-5801237-entornos-digitales/06_landing/landing.zip
```

Equivalente Windows:

```text
C:\_mcp\muse-packages\regulacion-federal-20261014-dof-5801237-entornos-digitales\06_landing\landing.zip
```

En la inspección tenía **8017 bytes**, con `README.md`, `index.html`, `style.css`,
`app.js`, `guia-dof-5801237.md` y `test.cjs`. La primera entrega era HTML estático,
no un PDF, aunque el operador expresó que su apariencia/calidad era la de un
PDF y que no cumplía sus expectativas de landing comercial.

La primera versión no guardaba correos ni tenía agenda conectada. Su encabezado
y oferta eran poco concretos y no había validación visual completa.

### 3.5. La versión con simulador fue un encargo separado del operador

El operador pidió directamente a Dot versiones adicionales. La versión con
simulador se encontró en:

```text
/mnt/c/Users/cheko/Downloads/landing-34-v3-simulador/
/mnt/c/Users/cheko/Downloads/landing-34-v3-simulador.zip
```

Esta versión incluye backend Node y almacenamiento local de solicitudes.
Se ejecutaron sus cinco pruebas existentes sobre una copia temporal, con datos
ficticios: todas pasaron. El README reconoce integración de agenda/configuración
y revisión visual pendientes. No se pudo inspeccionar el navegador real desde
esta sesión; la evaluación visual se basó en las capturas del operador.

**Aclaración del operador:** que estuviera revisando esa versión separada no
es un fallo de trazabilidad de su prueba personal. No usarlo como objeción a
su evaluación ni atribuir ese rediseño al encargo original de Bacha sin leer
la instrucción adicional. El ZIP original de Kanban y esa versión local son
artefactos distintos.

El juicio comercial fue que el simulador dominaba la página antes de explicar
la oferta; la implementación había mejorado, pero eso no acredita que la
landing esté lista para vender. No se modificó el diseño ni se desarrolló
una landing en nombre de Dot.

### 3.6. Dot no continuó la cola

El operador reportó que Dot hizo una landing y dejó las demás en `ready`.
Indicó que ya le aclaró que, después de entregar, debe consultar y continuar
con su siguiente tarjeta propia, y que Dot dijo haber actualizado sus
instrucciones. La consulta de este hand-off todavía muestra una terminada
y seis listas; no está demostrado que la corrección ya se ejecutó en una
ronda posterior. No afirmar que el worker ya vacía la cola automáticamente.

## 4. Lo ocurrido con Bacha

### 4.1. Los tres encargos originales necesitaban mejorar

Caso analizado: evento `regulacion-federal-20261014-dof-5801237-entornos-digitales`,
investigación #12 y evaluación #22. Se leyeron los tres `.md`, `decision.json`
y la investigación de Brio.

- **MVP:** escondía módulos amplios bajo «tres funciones», exigía varias
  integraciones sin accesos confirmados y mezclaba aceptación del software
  con metas de un piloto de semanas/meses. Faltaban criterios concretos y
  comportamiento ante dependencias no disponibles.
- **Prospección:** mezclaba entregar candidatos con conseguir entrevistas y
  ventas, no priorizaba suficientemente un segmento y pedía demostrar que una
  empresa no tenía equipo/proveedor aunque ese dato pudiera no ser público.
- **Landing:** daba público/beneficios/CTA, pero dejaba incompletos la oferta,
  entregables del piloto, identidad, operación de conversión y aceptación.

La investigación proponía validación acotada antes de construir un SaaS completo.
El operador también cuestionó que Bacha hubiera dado GO a todas las oportunidades.
No se realizó una nueva auditoría completa de los diez GO: no concluir que todos
son inválidos ni que quedaron comercialmente validados.

La responsabilidad se separó: Bacha debe formular encargos suficientes; Dot
sigue siendo responsable de claridad, jerarquía y calidad de su ejecución.
No atribuir todo el resultado visual al encargo original.

### 4.2. Se documentó un contrato de calidad

Se creó [bacha-requerimientos.md](kanban-operation/sequential/bacha-requerimientos.md)
y se enlazó en las guías de Bacha, calendario y primer hand-off.
Ese material explica aceptación, dependencias y coherencia de las ramas.

**Contrato de datos conservado:** Bacha entrega `decision.zip` con `decision.json`.
Redacta `specs.mvp_prompt`, `specs.icp_prompt` y `specs.landing_prompt` como
cadenas de texto. No necesita incluir los tres `.md`. El coordinador invocado
por n8n genera especificaciones y paquetes por rama. No hay nuevo esquema JSON.

### 4.3. Hubo dos propuestas de corrección del caso actual

Bacha presentó un documento con ocho secciones por encargo y luego otra versión.
Ambas se declararon **propuestas no aplicadas**. Las ramas ya habían consumido
los textos originales: #33 prospección, #34 landing y #32 MVP según el corte
reportado por Bacha. Sus estados y horas eran históricos, no pruebas de un
proceso trabajando «ahora».

Las revisiones detectaron contradicciones que seguían abiertas en el texto:

- Cambio automático a un stub si fallaba una integración real, pese a no estar
  autorizada una simulación sustitutiva.
- Promesa pública de precio supuesto y de contacto en un día hábil sin canal
  ni responsable confirmados. Aunque luego se corrigieron secciones, quedaban
  menciones antiguas en otras partes del documento.
- Una entrega puramente estática servida con `http.server` no implementa
  guardado de solicitudes en un archivo del servidor.
- Docker impuesto a Dot sin confirmar su disponibilidad; la exigencia debe
  ser reproducibilidad y funcionalidad, no una herramienta arbitraria.
- Dependencias sandbox no confirmadas pero exigidas como aceptación real.
- Criterios de prospección que confundían ausencia de información con ausencia
  de equipo, y falta inicial de prioridad de segmento.

Las propuestas no se aplicaron ni autorizaron un retrabajo de las ramas.
No volver a revisarlas indefinidamente como si ése fuera el objetivo actual.

### 4.4. Corrección de rumbo: mejorar el método permanente

El operador aclaró expresamente que no buscaba seguir corrigiendo lo ya hecho:
quería corregir **cómo Bacha debe preparar los encargos futuros**.

Se entregó por chat un prompt de método permanente que exige:

1. Definir qué se valida: problema, evidencia, cliente, oferta, fase y resultado
   de esta ronda, sin convertir investigación en construcción de un SaaS entero.
2. Definir una base común de cliente/oferta/promesas para las tres ramas,
   incluyéndola de forma autosuficiente en cada encargo.
3. Verificar dependencias antes de despachar: confirmadas, pendientes no
   bloqueantes o bloqueantes. Documentación pública no equivale a acceso.
4. Redactar alcance, exclusiones, acciones, resultados, entregables, aceptación
   y comprobaciones concretas por rama.
5. Aplicar reglas de MVP, prospección y landing sin confundir aceptación técnica,
   validación comercial y operación real.
6. Revisar todo el texto y los tres encargos juntos para detectar contradicciones,
   no solo corregir la sección que originó una observación.
7. Mantener el contrato JSON, horarios, reparto e independencia de las ramas.

Ese último prompt metodológico se entregó en el chat después de las revisiones
de documentos. No se debe asumir que el archivo de guías del commit anterior
reproduce palabra por palabra esa instrucción final ni que la memoria externa
de Bacha quedó actualizada de forma verificable. Bacha había reportado actualizar
su contrato para nuevas evaluaciones, pero falta demostrar el método en una
evaluación nueva. Si se sincronizan las guías, hacerlo alrededor del método,
no de una lista creciente de parches para este único caso.

## 5. Qué significa `done` y qué todavía no funciona como control de calidad

La #34 tenía un comentario de `n8n-radares`: «Entrega validada por el coordinador
secuencial». El coordinador llama automáticamente a `review_task(..., APPROVE, ...)`
cuando valida el ZIP y el contrato técnico. No es evidencia de una aprobación
comercial realizada por Bacha.

Bacha tiene una tarjeta posterior de cierre para revisar coherencia del conjunto,
pero no se implementó una puerta de calidad comercial que impida automáticamente
cada `done` de rama. No existe en este montaje un bloqueo automático por estética,
conversión, pruebas visuales ausentes o calidad comercial.

Por eso deben distinguirse:

- **Contrato técnico:** archivo recibido y estructura válida.
- **Calidad de producto:** satisface de verdad el encargo y la experiencia esperada.
- **Validación comercial:** evidencia de interés, dolor y disposición a pagar.
- **Operación:** identidad, cuentas, canales, agenda y responsables funcionando.

Actualizar instrucciones no añade por sí solo un validador o una nueva transición.
No prometer que el pipeline ya resolverá automáticamente estos problemas.

## 6. Estado de horarios y límites de la suspensión

Los horarios de referencia siguen documentados: Brio 12:30; Bacha evaluación
15:00, prospección 16:00 y cierre 19:00; Dot 16:00; conciliación n8n cada cinco
minutos 12:20–22:00; Telegram desde 19:30.

**Excepción vigente:** el worker y timer de Codex están suspendidos. Su horario
anterior de 16:00–17:55 no autoriza reactivarlo. No programarlo mañana ni ejecutar
manualmente su lanzador para «probar» mientras siga esta orden.

La suspensión no modifica la base, el contrato de reclamo ni las tarjetas. El
estado de sus tarjetas activas debe resolverse explícitamente después de revisar
archivos, actividad y resultados; no resetearlos automáticamente a ready.

## 7. Punto de continuación para otro agente

El siguiente trabajo debe partir de la suspensión y del cambio de método, no
reanudar la ronda como si todo estuviera validado.

- Mantener Codex suspendido hasta nueva instrucción humana.
- No borrar entregas ni recuperar reclamos para limpiar el tablero sin una
  decisión concreta y trazable.
- No sobrescribir los paquetes actuales con prompts revisados: el generador
  usa claves y archivos estables; eso no redistribuye un encargo nuevo.
- Confirmar qué método permanente incorporó Bacha y evaluar una nueva salida
  con ese método antes de volver a dar por resuelta la calidad del despacho.
- Revisar los GO y el alcance de sus ramas solo cuando se autorice esa tarea;
  esta conversación los cuestionó, pero no realizó ese análisis completo.
- Verificar el seguimiento de cola de Dot en una ejecución real, sin hacer
  su trabajo ni crear pilotos por cuenta del operador.
- Si se propone una puerta de revisión de calidad, describirla como cambio
  pendiente: todavía no está implementada. No alterar el esquema del pipeline
  incidentalmente al actualizar documentación.

**No se acordó todavía:** reanudar Codex, cancelar la ronda, borrar tarjetas,
reencargar las diez oportunidades, aplicar las propuestas a la #22 o rediseñar
el flujo de revisiones. No inferir esas autorizaciones de este hand-off.

## 8. Código, documentación y Git

| Referencia | Ubicación |
| --- | --- |
| Primer hand-off | [HANDOFF-FACTORY-KANBAN.md](HANDOFF-FACTORY-KANBAN.md) |
| Guía de Bacha | [bacha.md](kanban-operation/sequential/bacha.md) |
| Contrato de requerimientos y diagnóstico | [bacha-requerimientos.md](kanban-operation/sequential/bacha-requerimientos.md) |
| Guía de Codex, con aviso de suspensión | [codex.md](kanban-operation/sequential/codex.md) |
| Guía de Dot | [dot.md](kanban-operation/sequential/dot.md) |
| Transferencia de Dot y despliegue MegaMCP | [mega-mcp/dot.md](kanban-operation/mega-mcp/dot.md), [README](kanban-operation/mega-mcp/README.md) |
| Coordinador y aprobación técnica | `src/agent_kanban/factory_coordinator.py` |
| Horarios y exclusión Muse | `src/agent_kanban/factory_schedule.py` |
| Preparación de paquetes | `src/agent_kanban/factory_files.py` |
| Lanzador y unidades de Codex | `deploy/factory/run-codex.py`, `kanban-codex.service`, `kanban-codex.timer` |
| Puente versionado de Dot | `deploy/mega-mcp/factory_dot_bridge.py` |

Commits publicados relevantes, en orden:

- `dcb4575`: ZIP entre MCP y workspace de Dot.
- `b54983d`: confirmación del reclamo y primer hand-off.
- `c3573ae`: ZIP adjunto binario para evitar referencias no resueltas.
- `7d5169b`: guías de calidad de requerimientos para Bacha.

Al iniciar este hand-off estaban pendientes de commit los avisos de suspensión
en el primer hand-off y en `sequential/codex.md`. Este segundo documento se crea
a continuación. No confundir cambios documentales pendientes con cambios
funcionales de esos commits.

No se incluyen secretos. Tokens y credenciales continúan en los archivos
privados descritos en el primer hand-off. Se conservaron los archivos y las
configuraciones de Kanban, MegaMCP, n8n y los entregables existentes.

## 9. Nuevas reglas de Codex, recibidas después de la suspensión

El operador definió el rol de ingeniero full-stack pragmatic-first para MVP
funcional y demostrable en una sesión. Se actualizaron sus instrucciones en
[sequential/codex.md](kanban-operation/sequential/codex.md):

- Reclamos nuevos de 15:00 a antes de 17:30, America/Mexico_City, una tarjeta
  a la vez. A las 17:30 no tomar otra; terminar y probar la ya iniciada si es
  viable, y enviarla a revisión sin entregar código roto o incompleto.
- Mantener entrada `03_specs/mvp-input.zip`, workspace `04_mvp` y salida
  `04_mvp/mvp.zip`, con proyecto, README y ejemplo de entorno sin secretos.
- Priorizar el recorrido principal y evitar arquitectura y funciones extra.
- Primeras diez líneas del README: comando exacto de arranque en un comando
  y comando de pruebas, ambos comprobados.
- Si falta API key/sandbox exigido y no se autoriza explícitamente MODO DEMO
  CON DATOS SEED, registrar `blocked`, indicando el acceso faltante y el error;
  no sustituir por simulación ni entregar como completado.
- Entre tres y cinco pruebas automatizadas en total, incluido un error crítico,
  ejecutadas antes de empaquetar.

La guía documenta la transición existente mediante post_progress con
kind=status_change y status.to=blocked. No se implementó otra API de bloqueo.

Al preparar esta actualización ya existían cambios previos en curso en el
checkout que ajustaban horario, timer y límite WIP=1, además de otros cambios
del pipeline. Se conservaron: no se reconstruyó ni desplegó el checkout completo
para aplicar esta guía ni se editaron esos archivos como parte de esta tarea.
Su presencia en disco no acredita por sí sola su despliegue o verificación.

**La suspensión se conserva.** Actualizar el método y el horario futuro de
Codex no autoriza reactivar el servicio/timer ni recuperar las tarjetas de la
ronda anterior. Los horarios históricos de las secciones anteriores son
contexto: esta nueva instrucción prevalece para Codex cuando se autorice retomar.
