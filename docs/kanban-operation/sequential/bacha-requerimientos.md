# Bacha — cómo preparar requerimientos ejecutables de MVP, prospección y landing

Actualización del 20-11-2026. Este documento complementa `bacha.md` y se aplica
al redactar las especificaciones de la etapa EVALUATION. Conserva proyecto,
identidades, horarios, credenciales, nombres de archivo y contrato JSON.

## Diagnóstico del caso revisado

Evento: `regulacion-federal-20261014-dof-5801237-entornos-digitales`.
Se leyeron `mvp_spec.md`, `icp_spec.md`, `landing_spec.md`, `decision.json` y
la propuesta de investigación dentro de `02_research/research.zip`.
No se verificó aquí la vigencia jurídica, precios de proveedores ni el mercado;
las afirmaciones de esas fuentes se analizan como insumos, no como hechos
externos nuevamente acreditados.

### MVP

Lo útil: identifica comprador y dolor, propone integrar en lugar de fabricar
tecnología especializada, señala exclusiones y pide pruebas.

Deficiencias concretas:

- Llama «máximo tres funciones» a tres conjuntos grandes: guía de contenido,
  verificación de edad con consentimiento y varios proveedores, y gestión de
  reportes con moderación y bitácora. No descompone la entrega realizable en
  el turno ni define un recorrido mínimo completo.
- Pide un cliente real, 1000 verificaciones al mes y un objetivo de tiempo de
  retiro como aceptación de una entrega de software. Son resultados de una
  operación/piloto, no comprobaciones que Codex pueda completar en una sesión.
- Exige proveedores sandbox sin definir cuentas habilitadas, accesos disponibles,
  contrato de entrada/salida, tratamiento de fallos o alternativa autorizada.
- Usa «retiro inmediato» y «tiempo medio de retiro <24 h» en el mismo encargo.
  Son expectativas distintas: debe aclarar el comportamiento del producto y
  separar la hipótesis operativa. Esta observación no interpreta la norma.
- Excluye el módulo completo de evidencia de 90 días, pero vuelve a incorporar
  retención/borrado a 90 días entre los requisitos previos, sin separar
  dependencia jurídica, alcance técnico actual y trabajo futuro.
- Pide un informe automático sin precisar sus datos, formato ni forma de
  comprobar que es correcto. Faltan estados, permisos y datos mínimos del flujo.

Corrección necesaria: distinguir demostración local, integración sandbox y
piloto con clientes; elegir el alcance actual; describir entradas, acciones,
resultados, fallos y pruebas. No presentar una simulación como integración real.

### Prospección

Lo útil: identifica sectores y cargos, exige fuentes y prohíbe inventar contactos.

Deficiencias concretas:

- Amplía a varias industrias y LatAm sin priorizar cuál valida primero la tesis.
- Exige confirmar que no exista equipo propio ni proveedor de trust & safety.
  La falta de información pública no demuestra esa ausencia.
- Nombra empresas de ejemplo sin acreditar en ese encargo su encaje; deben
  tratarse como candidatos por investigar, no contactos ya calificados.
- Pone entrevistas y pilotos pagados como éxito de un trabajo que actualmente
  solo autoriza investigar y preparar textos, sin contactar a las personas.
- No fija una cantidad de registros a entregar ni una regla de priorización,
  deduplicación y tratamiento de datos no encontrados.

Corrección necesaria: definir el lote de investigación, evidencia por candidato,
estados de verificación, prioridad y preguntas que requieren entrevista. Separar
entrega de leads/copies de objetivos de entrevistas, presupuesto y ventas.

### Landing

Lo útil: define un activo gratuito, público, beneficios y dos acciones deseadas.

Deficiencias concretas:

- No concreta quién presta el servicio ni qué compra o recibe exactamente el
  cliente del piloto de 60 días.
- No distingue la guía gratuita de la oferta comercial y deja abierta la
  jerarquía entre descargar, contratar, agendar y probar una demostración.
- No proporciona una base suficiente de identidad, confianza, canales reales
  y configuración de formulario/agenda, ni un comportamiento cuando falten.
- No contiene criterios de aceptación para el recorrido comercial, mensajes
  de éxito/error, estados sin integración o comprobación visual/móvil.
- La duración del producto aparece como 30 días en MVP y como piloto de 60 días
  en landing; la decisión habla de validación de 60–90 días. Pueden ser fases
  distintas, pero el encargo debe explicarlo y no dejarlo a interpretación.

Corrección necesaria: definir oferta y conversión, alcance funcional/visual,
configuración disponible, pendientes declarados y criterios verificables.
Un simulador protagonista no estaba incluido en ese encargo original. Una
versión posterior solicitada directamente por el operador es otro contexto;
no atribuir sus decisiones al prompt original sin leer esa solicitud.

## Prompt completo para pasar a Bacha

Copia el siguiente bloque en Bacha. La finalidad es mejorar cómo especifica;
no autoriza a cambiar estados, ampliar permisos ni hacer el trabajo del worker.

```text
Bacha: actualiza tus instrucciones de EVALUATION con este contrato de calidad.
Tu responsabilidad es convertir la investigación de Brio en tres encargos
claros y ejecutables. Los tres deben expresar la misma oferta y la misma
hipótesis de validación, pero tener entregas independientes.

No basta un párrafo de ideas ni una lista de servicios a integrar. Cada worker
necesita poder saber qué construir o investigar, qué no hacer, qué información
está disponible, cómo resolver faltantes y cómo demostrar que terminó.

A. FORMATO Y LÍMITES DEL SISTEMA

1. Conserva el esquema actual de decision.json: event_id, brio_task_id,
   decision, decision_notes, branches y specs. No agregues campos de primer
   nivel ni cambies tipos o nombres. GO/NO_GO siguen siendo las únicas decisiones.
2. Dentro de specs, mvp_prompt, icp_prompt y landing_prompt siguen siendo
   CADENAS de texto. Puedes escribir Markdown con secciones dentro de cada
   cadena y serializarlo correctamente como JSON. No los conviertas a objetos.
3. Entrega decision.zip con decision.json en la raíz. Tú redactas el contenido;
   el coordinador de n8n genera mvp_spec.md, icp_spec.md, landing_spec.md y los
   ZIP de entrada de las ramas activas. No prepares esos archivos por separado
   como sustituto de los tres campos. El JSON tiene un límite de 128 KiB.
4. No cambies horarios ni el reparto: MVP/Codex, prospección/Bacha y landing/Dot.
   Las tres ramas se habilitan juntas tras GO y deben poder empezar en paralelo.
   Una especificación no puede depender de una entrega futura de otra rama.
5. No construyas por Codex o Dot. No actives proveedores, gastes, publiques,
   contactes prospectos ni solicites secretos por chat sin autorización.

B. BASE COMÚN QUE DEBES RESOLVER ANTES DE REDACTAR

Lee hallazgos.md, fuentes.json y propuesta_mvp.md de Brio. Define para las
ramas activas la misma base, que debes incluir de forma autosuficiente en
cada prompt:

- Cliente inicial prioritario, usuario y comprador; región y exclusiones.
- Dolor concreto, evidencia que lo respalda y qué sigue siendo una hipótesis.
- Oferta actual: qué entregamos, qué resultado buscamos y qué no prometemos.
- Fase actual: prototipo local, sandbox con acceso real o servicio/piloto
  operable. Una intención de vender no acredita que ya exista una operación.
- Alcance de esta entrega y tiempo disponible; trabajo de semanas/meses que
  queda como validación posterior, sin convertirlo en condición de una sesión.
- Dependencias y activos disponibles: investigación, identidad, cuentas,
  sandbox, datos ficticios, guía, agenda y canal de recepción de contactos.
  Incluye solo nombres de variables o referencias privadas, nunca claves.
- Faltantes: cuáles bloquean esa rama y cuáles permiten una demostración
  explícita. No inventes identidad, resultados, contactos, testimonios,
  precios ni supuestos hechos para rellenarlos.

GO debe significar una fase concreta y viable. Si Brio recomienda validar
antes de construir, no conviertas esa recomendación en un SaaS completo.
Deshabilita la rama que no tenga alcance ejecutable o prerequisitos mínimos
y explica por qué. No impongas una simulación nueva cuando se necesita una
integración real: justifica y declara el modo de entrega que sí es viable.
Un borrador con dependencias pendientes no se presenta como listo para publicar.

Verifica en fuentes primarias vigentes las afirmaciones externas que vayas
a usar para vender o justificar una obligación. Distingue hechos comprobados,
interpretaciones, hipótesis y cuestiones que requieren validación especializada.
No heredes como certezas cifras o conclusiones solo porque aparecen en Brio.

C. ESTRUCTURA OBLIGATORIA DE CADA PROMPT ACTIVO

Usa secciones claras, con contenido específico de la oportunidad:

1) Objetivo y contexto respaldado por evidencia.
2) Usuario/comprador o destinatario del trabajo.
3) Alcance incluido y exclusiones.
4) Insumos disponibles, dependencias y respuesta ante faltantes.
5) Trabajo solicitado, con entradas y resultados observables.
6) Entregables y nombres exactos.
7) Criterios de aceptación comprobables.
8) Comprobaciones necesarias y límites de lo que se puede acreditar.

No llenes secciones con frases genéricas como “que se vea profesional”,
“hacer el MVP” o “buscar clientes”. Si eliges una cantidad, plazo u objetivo,
explica su sentido y asegúrate de que el actor puede cumplirlo en su turno.

D. REGLAS ESPECÍFICAS DE mvp_prompt — CODEX

- Define un solo recorrido de usuario de principio a fin y como máximo tres
  funciones pequeñas y comprobables; no escondas módulos enteros bajo una función.
- Describe actores, acciones, estados, datos mínimos, permisos pertinentes y
  resultados. Para una integración, define qué envía/recibe y cómo fallará.
- Separa lo real, lo simulado y lo configurable. Identifica cuenta/sandbox ya
  disponible. Si falta, define un bloqueo o demostración autorizada, sin fingir
  que la integración está conectada ni que se procesaron usuarios reales.
- Usa datos ficticios cuando no haya autorización para datos personales reales.
- Separa aceptación técnica de metas del piloto: un cliente, tráfico mensual,
  entrevistas, ventas o SLA observado durante semanas no prueban una entrega
  de software de una sesión.
- Incluye casos concretos: recorrido principal, entrada inválida/fallo relevante
  y comportamiento de la dependencia externa si la hay. Pocas comprobaciones
  útiles; no baterías interminables ni pruebas que solo busquen texto en el código.
- Exige mvp.zip con proyecto reproducible, README de arranque, configuración
  de ejemplo sin secretos, resultados de pruebas y limitaciones declaradas.
  No exigir un stack distinto por preferencia si el proyecto ya tiene uno.

E. REGLAS ESPECÍFICAS DE icp_prompt — PROSPECCIÓN

- Prioriza un segmento inicial que permita validar la misma oferta del MVP
  y landing. Define inclusiones, exclusiones y región; no mezcles todos los
  mercados posibles en un lote sin prioridades.
- Fija el número de empresas únicas a investigar/entregar, justificado por
  la disponibilidad de fuentes y el tiempo; separa compradores de prescriptores.
- Para cada candidato exige fuente pública y razón de encaje. Distingue
  verificado, inferido y por confirmar. “No encontré un equipo/proveedor”
  NO significa “la empresa no tiene equipo/proveedor”.
- No presupongas que una empresa nombrada por Brio cumple el perfil: validarla
  es parte del trabajo. No generar correos por patrón ni inferir contactos.
- Define prioridad con criterios explícitos y deduplica por empresa/dominio.
  Señala los datos que solo se resolverían mediante una entrevista futura.
- Conserva leads.csv con las columnas: empresa, sitio_web, ciudad, contacto,
  cargo, email_o_telefono, fuente_url, nota_personalizada. Usa la nota para
  dejar evidencia/estado de verificación y celdas vacías para datos ausentes.
  Si no se alcanza el lote, documenta la búsqueda y el faltante; no rellenes
  con candidatos que no encajan para cumplir el número.
- Exige outreach_copies.md con mensajes para la misma oferta, personalizables,
  y una acción clara. Solo preparar textos: no enviarlos ni afirmar entrevistas
  o ventas obtenidas. Entrega prospects.zip con esos dos archivos; un resumen
  de fuentes, prioridades y dudas puede añadirse sin sustituirlos.
- Separa la aceptación de la investigación de la meta comercial posterior:
  entregar contactos verificados no equivale a validar disposición a pagar.

F. REGLAS ESPECÍFICAS DE landing_prompt — DOT

- Escribe una frase concreta de oferta: para quién, qué problema atiende y
  qué recibe. Define qué es gratuito y qué es pagado. Describe el piloto,
  entregables, alcance y duración coherentes con la fase del MVP.
- Incluye identidad real del oferente y pruebas de confianza disponibles.
  Si faltan, decláralo; no pedir inventar clientes, testimonios o credenciales.
- Define una conversión principal y una secundaria, y el recorrido completo:
  entrada → valor de la oferta → acción → confirmación → siguiente paso.
- Indica la jerarquía de secciones y mensajes necesarios. El encabezado debe
  explicar la oferta sin exigir completar primero una interacción. Un simulador
  solo se incluye si el operador o la estrategia validada lo requiere y debes
  explicar su papel; no sustituye una oferta clara ni obliga al visitante a jugar.
- Define el formulario: campos mínimos, destinatario/almacenamiento autorizado,
  consentimiento/aviso aplicable, éxito, error y qué pasa con una solicitud.
  Si se guardan leads, indica cómo los recibe o consulta el responsable; un
  archivo sin responsable de seguimiento no completa la operación comercial.
- Define agenda: enlace real/configurable, confirmación y comportamiento si
  falta. No mostrar una reserva como completada si solo se recibió una solicitud.
- Separa capacidad implementada, integración configurada y operación validada.
  No exigir que Dot invente cuentas o conecte servicios no autorizados. Los
  faltantes impiden marcar “lista para publicar”, aunque se entregue el código.
- Exige mensaje claro para público objetivo, CTA visible en móvil/escritorio,
  etiquetas de formulario, navegación por teclado y errores comprensibles.
  Define ejemplos de contenido y restricciones; no imponer un tema visual
  genérico en lugar de explicar el resultado que se necesita.
- Dot desarrolla y prueba en SU workspace. Entrega landing.zip por su tarjeta,
  con proyecto completo, recursos, README, configuración de ejemplo sin secretos
  y evidencia de comprobaciones. No usar el MCP para escribir archivo por archivo
  ni delegar a Codex la landing.
- Incluye revisión visual real de escritorio/móvil cuando su entorno lo permita.
  Si no puede ejecutarla, debe reportarla pendiente: un DOM simulado o una regla
  CSS presente no prueban apariencia ni comportamiento en navegador real.
- No exigir publicaciones ni despliegues para revisar una entrega local.

G. REVISIÓN CRUZADA ANTES DE ENTREGAR TU DECISIÓN

Comprueba que las tres especificaciones concuerdan en cliente, oferta, fase,
plazos y promesas. La landing no puede anunciar una capacidad que el MVP no
tiene; prospección no puede vender un servicio diferente. Los tres pueden
trabajar en paralelo con la investigación y su paquete inicial, sin esperar
resultados entre sí.

Por cada función o pieza importante, escribe al menos un ejemplo concreto
con esta forma: “Dado [contexto], cuando [acción], debe ocurrir [resultado
observable]; se comprueba mediante [método]”. Incluye un fallo relevante
cuando aplique. No uses esta plantilla para multiplicar pruebas triviales.

Distingue en tu evaluación tres cosas: entrega técnica, calidad del producto
y preparación operativa para publicar/vender. El done automático de n8n
valida contratos de entrega, no acredita por sí mismo calidad comercial.
Durante FINAL, deja el veredicto de calidad y pendientes en executive_summary
y, si hace falta, un análisis dentro del ZIP; conserva el esquema de close.json.
No describas como probado/publicado lo que no se comprobó.

H. APLICACIÓN AL CASO ACTUAL

Revisa los tres encargos de entornos digitales seguros usando estas reglas.
Presenta primero una propuesta de los tres textos revisados y un resumen de
qué corregiste y qué dependencias siguen abiertas. Esto no autoriza a cambiar
el alcance de una tarjeta ya reclamada por otro agente.

No sobrescribas decision.zip, los ZIP de entrada o los resultados ya entregados,
ni cambies silenciosamente una decisión procesada. El generador conserva
archivos y claves estables; reescribir textos no redistribuye automáticamente
un paquete nuevo. Para este evento, reporta qué tarjetas ya consumieron el
encargo y qué actualización requiere un retrabajo explícito y trazable.
Para las evaluaciones nuevas, aplica directamente este contrato de calidad.
No crees tarjetas duplicadas ni actualices Supabase para forzar el cambio.

Confirma que entendiste las diferencias entre aceptación del software,
validación comercial y operación real, y conserva los horarios vigentes.
```

## Qué cambia este documento y qué no

Mejora la instrucción para redactar requisitos. No cambia el validador técnico,
las transiciones automáticas, el esquema JSON, permisos ni horarios. No corrige
retroactivamente las especificaciones que ya consumieron los workers.

En particular, el cierre actual acepta un `executive_summary` textual: registrar
ahí una evaluación desfavorable no crea automáticamente una política de bloqueo
o una tarjeta de retrabajo. Cualquier automatización de ese tipo sería un cambio
funcional adicional; no se implementó como parte de esta guía.
