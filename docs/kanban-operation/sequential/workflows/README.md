# Exportaciones de n8n

Copias del montaje en anyo, 18 de noviembre de 2026.

- `errors.json`: registrador de fallos.
- `coordinator.json`: conciliación cada cinco minutos.
- `telegram.json`: entrega y confirmación de informes.

En producción los tres están publicados. Estas copias usan `active: false`
para permitir revisar credenciales y referencias antes de publicar una
restauración. No contienen los valores secretos de las credenciales.

Publica primero el registrador. Su ID puede cambiar al importar: selecciona
el nuevo ID en `settings.errorWorkflow` de los otros dos. Confirma la zona
`America/Mexico_City`, el chat de destino y las credenciales de tu instancia.
No actives otra copia de los mismos cron a la vez.
