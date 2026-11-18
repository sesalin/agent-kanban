# Diseño previo del pipeline secuencial

Implementado el 18 de noviembre de 2026. Consulta la [operación vigente](../sequential/README.md), sus horarios confirmados y el estado de activación. El texto siguiente conserva la propuesta previa a la implementación.

## Decisión y alcance

El 18 de noviembre de 2026 el usuario sustituyó la coordinación por eventos
por ejecuciones programadas durante el día. Esta guía define el diseño nuevo;
todavía no representa una migración desplegada. WF1–WF5 siguen como borradores
del diseño anterior. Sus webhooks y avisos WAKEUP dejan de ser el mecanismo
propuesto para coordinar la fábrica.

Se conservan Supabase `radars-n8n` (`uobeshcvmtawjxibciuy`), el proyecto 1 de
Kanban, las identidades, los ZIP y las conexiones autenticadas existentes.
Brio investiga; Bacha evalúa, realiza prospección, construye la landing y revisa
el cierre; Codex construye el MVP. Nod e Instinct quedan fuera del nuevo flujo.
El usuario confirmó que Brio permite ejecuciones programadas y decidió
regresar a Bacha, el otro Muse, para esta estrategia.

## Responsabilidades

- Supabase conserva el estado del pipeline y los vínculos con el radar y las tarjetas.
- n8n consulta por horario, valida entregas, actualiza Supabase y crea la siguiente tarjeta habilitada. Conserva la responsabilidad de aprobar y cerrar tarjetas.
- Cada agente arranca mediante un horario de su propio entorno, consulta Kanban y trabaja las tarjetas asignadas a su identidad.
- Los agentes entregan archivos y resultados estructurados en sus tarjetas mediante las herramientas MCP y las rutas de paquetes existentes. No necesitan escribir directamente en Supabase ni llamar a un webhook de fábrica al terminar.
- Telegram es un canal de informe; su disponibilidad no debe controlar el avance del trabajo.

Un Schedule Trigger de n8n inicia un workflow de n8n. Para ejecutar un Muse o
un agente del PC hace falta que ese entorno tenga su propia ejecución
programada. Consultar estados no sustituye ese arranque. Brio permite programación, según confirmó el usuario. Faltan los horarios
actuales de los radares y fijar las ventanas de Brio y Bacha en sus entornos.

## Orden de las etapas por oportunidad

Los nombres de pasos de esta tabla son conceptuales; todavía no se han añadido
como nuevos valores de estado a la base.

| Paso | Responsable | Condición para comenzar | Entrega que habilita el siguiente paso |
| --- | --- | --- | --- |
| Detectar señales | Automatizaciones de radares | Horario de cada radar | Registro persistido con identidad estable |
| Analizar y preparar | Automatizaciones de análisis | Radar pendiente de análisis | Análisis registrado y ZIP listo para un caso elegible |
| Preparar investigación | n8n | Registro elegible, ZIP válido, sin tarjeta de investigación existente | Pipeline y tarjeta de Brio vinculados |
| Investigar | Brio | Tarjeta propia disponible | `research.zip` válido y tarjeta en revisión |
| Evaluar | Bacha | Investigación validada por n8n y tarjeta de evaluación disponible | Decisión estructurada GO/NO_GO, banderas, justificación y especificaciones en su tarjeta |
| Construir MVP | Codex | GO, `run_mvp=true`, tarjeta propia disponible | `mvp.zip` válido y tarjeta en revisión |
| Prospectar | Bacha | Paso anterior terminado u omitido y `run_prospection=true` | `prospects.zip` válido y tarjeta en revisión |
| Construir landing | Bacha | Paso anterior terminado u omitido y `run_landing=true` | `landing.zip` válido y tarjeta en revisión |
| Revisar cierre | Bacha | Todas las etapas habilitadas terminadas y tarjeta de cierre disponible | Resumen ejecutivo y comprobación de entregables en su tarjeta |
| Cerrar e informar | n8n | Cierre validado | Pipeline terminado y envío del informe registrado |

NO_GO cierra la oportunidad con su justificación, sin crear las tarjetas de
construcción. Una etapa desactivada por las banderas se registra como omitida;
no bloquea la siguiente. Para cada oportunidad solo se habilita una etapa a la
vez. El avance hacia MVP, prospección y landing será secuencial.

Evaluación y cierre requieren tarjetas propias de Bacha. El diseño anterior
iniciaba esas actividades mediante avisos; esa parte también debe migrarse.
Los formatos exactos de sus entregas estructuradas deben definirse antes de
implementar los consumidores, para no depender de interpretar comentarios libres.

## Qué hace cada ejecución programada

1. n8n reconcilia las tarjetas en revisión con los pipelines pendientes. Verifica identidad, proyecto, etapa, metadatos y archivos antes de aprobar una entrega.
2. Registra el resultado y habilita únicamente el siguiente paso correspondiente. La creación usa una clave estable por oportunidad y etapa, aprovechando `factory_dispatch_key` para evitar tarjetas duplicadas al reintentar.
3. Cada agente, en su ventana, consulta su cola del proyecto 1 y filtra `assigned_to` por su identidad exacta. Reclama antes de trabajar y mantiene heartbeat.
4. Después de subir el resultado y enviar a revisión, el agente consulta la siguiente tarjeta a su nombre y continúa mientras tenga trabajo y tiempo en su ventana.
5. Si una etapa no está lista, la ejecución termina sin inventar resultados. La siguiente ventana vuelve a consultar el estado persistido. No mantiene una sesión esperando ni pregunta repetidamente por el resultado de otro agente.

La hora habilita una oportunidad de ejecución; no acredita que el trabajo
anterior haya terminado. Si Brio se demora, Bacha no evalúa una investigación
incompleta: queda pendiente hasta una ventana posterior. El proceso puede
continuar al día siguiente sin reiniciar las etapas ya completadas.

La secuencia se aplica por oportunidad. Si además se requiere que solo exista
una oportunidad activa en toda la fábrica, esa restricción global debe
acordarse: no se deduce del orden entre etapas de una misma oportunidad.

## Exclusividad de los dos Muse

Brio y Bacha comparten la limitación confirmada de no poder trabajar al mismo
tiempo. Sus ventanas deben ser sucesivas. Si Brio sigue ejecutándose al llegar
la ventana de Bacha, Bacha queda pendiente; el horario no permite saltarse esa
restricción. La coordinación debe comprobar la ejecución Muse activa antes
de habilitar otra y registrar su finalización. Esta exclusividad abarca toda
la fábrica, aunque existan varias oportunidades pendientes.

Al terminar una tarjeta, cada Muse continúa con la siguiente propia dentro de
su ventana. No inicia una nueva si ya corresponde ceder el turno al otro Muse.
La política de duración y el control de exclusividad deben quedar definidos
antes de activar ambos horarios.

## Calendario pendiente

Zona horaria: `America/Mexico_City`.

La documentación del corte del 14 de noviembre registra análisis a las 09:00
(Gobierno NL), 10:00 (Compras), 11:00 (Regulación) y 12:00 (Competencia).
Son una referencia histórica, no horarios verificados de las automatizaciones
actuales. Competencia conserva su recorrido de análisis y seguimiento sin ZIP Muse.

Tras confirmar los horarios reales, se reservan ventanas sucesivas para:
preparación de tarjetas, Brio, conciliación, evaluación de Bacha, conciliación,
Codex, conciliación, prospección de Bacha, conciliación, landing de Bacha,
conciliación, cierre de Bacha e informe. Los intervalos deben contemplar el
tiempo disponible de cada agente. No se asignan cron definitivos sin confirmar
el arranque programado de esos agentes.

## Reglas de recuperación

- El cambio de etapa exige entrega válida y vínculo con la tarjeta correcta.
- Los avances y la habilitación del siguiente paso requieren una transición atómica en Supabase y protección contra dos ejecuciones de conciliación superpuestas.
- Un reintento conserva el mismo evento y la misma clave de despacho. No recrea una tarjeta por falta de respuesta después de un envío.
- Un fallo conserva etapa, tarjeta, motivo y momento del intento. Agotar una ventana no equivale a terminar una etapa.
- Una tarjeta reclamada sin heartbeat necesita recuperación explícita por el coordinador; no se debe reclamar de nuevo en paralelo con otro trabajo activo.
- El estado de entrega del informe debe persistir separado del estado de finalización, para reintentar una notificación sin repetir la construcción ni el cierre.
- Los archivos originales y entregables aceptados se conservan. La migración no borra tarjetas ni oportunidades previas.

## Trabajo de migración pendiente

1. Confirmar horarios de radares y fijar los arranques de Brio, Bacha y Codex, con exclusividad entre los dos Muse.
2. Adaptar el estado persistido para identificar evaluación, siguiente rama secuencial, cierre y notificación pendiente. Reutilizar los campos actuales que ya expresen esos hechos.
3. Adaptar los workflows para consultar pendientes por horario y reconciliar resultados desde las tarjetas. Retirar la dependencia de WAKEUP y de los callbacks de los agentes.
4. Añadir las tarjetas y los contratos de entrega de evaluación y cierre de Bacha.
5. Actualizar prompts: consultar la cola al iniciar cada ventana, entregar en la tarjeta y continuar con la siguiente propia.
6. Verificar un recorrido acotado, incluida una ejecución repetida y una etapa aún no lista, antes de activar el calendario productivo.

Las conexiones de Kanban y la API de archivos ya verificadas siguen siendo
reutilizables. Todavía no se ha ejecutado una oportunidad completa bajo este
nuevo diseño. El contacto de WhatsApp de Brio deja de ser un requisito del
arranque programado; Telegram sigue pendiente para la entrega del informe.
