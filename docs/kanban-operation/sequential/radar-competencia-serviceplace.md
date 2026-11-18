# Radar Competencia ServicePlace — instrucciones y horarios

Conserva las dos automatizaciones existentes, en **America/Mexico_City**:

| Ejecución diaria | Hora |
| --- | --- |
| Búsqueda | 11:40 |
| Análisis | 12:00 |

## Búsqueda

Consulta las fuentes del radar según su configuración existente. Registra
cada señal con identidad estable y evidencia de origen. Conserva los accesos
actuales del MCP de radares; no uses tokens de workers Kanban para escribir
en la base. No inventes novedades ni vuelvas a crear un evento ya registrado.

## Análisis

Consulta los pendientes mediante el MCP, reclama su análisis según el contrato
existente y guarda la decisión y evidencia en la base **radars-n8n**, proyecto
`uobeshcvmtawjxibciuy`. Herramientas existentes: `radar_competencia_get_pending, radar_competencia_update_analysis`.

Este radar termina en análisis y seguimiento; no prepara ZIP Muse ni entra en las etapas de construcción de esta fábrica.

El estado `ready` de un paquete debe corresponder a un ZIP real y verificable
en la raíz `/mnt/c/_mcp/muse-packages`. Conserva `event_id`, `package_path` y
`package_filename`. Si la preparación falla, registra el error; no lo marques
listo. No investigues en nombre de Brio ni construyas el MVP de Codex.

## Relación con la fábrica

La fábrica consulta el resultado persistido desde las 12:20. No requiere
llamar a `factory/package-ready`, crear tarjetas ni despertar otro agente.
n8n valida el archivo y crea la tarjeta correspondiente cuando procede. Los
resúmenes y notificaciones existentes del radar son independientes de ese
avance. Estas instrucciones no cambian el calendario confirmado ni afirman
que se haya reconfigurado desde esta sesión la automatización externa.
