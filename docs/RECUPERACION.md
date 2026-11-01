# Copia y restauracion offline segura

La copia y la descarga desde el panel admin siguen disponibles. El boton
antiguo **Restaurar** se retira: no se debe sustituir SQLite y los PDF con
el servidor Flask y los procesos programados ejecutandose.

## Crear una copia offline sin perder la base

Deten cualquier tarea externa del scheduler y ejecuta desde la carpeta del
proyecto desplegado:

```sh
sh scripts/create_offline_backup.sh
```

Se detiene SOLO el contenedor `app`, se crea un ZIP consistente con
`database.sqlite3`, `declarations/`, `exports/` y `manifest.json`, se
comprueba su CRC y se reinicia el servicio. El archivo queda en
`data/backups/` y **es obligatorio copiarlo fuera de ese servidor**.
No subas backups a GitHub. Mantener una politica de retencion externa.

## Restaurar un ZIP completo

1. Ensaya primero en una instalacion desechable.
2. Comprueba que el ZIP pertenece a la misma edicion que el destino.
3. Deten cualquier cron/scheduler externo que escriba en SQLite o PDFs.
4. Coloca el ZIP en `data/backups/` y ejecuta:

```sh
sh scripts/restore_offline.sh ./data/backups/NOMBRE_DEL_BACKUP.zip
```

El script usa un contenedor Python temporal **sin red**, para el servicio,
verifica la integridad ZIP/SQLite, el manifiesto, las fases, la edicion y
los nombres de archivo, prepara un arbol de datos completo y lo instala.
Conserva una copia anterior `data.pre-restore-FECHA/` junto a `data/`.
Si un paso falla, el servidor queda parado para diagnosticar antes de
reiniciar. La prueba automatizada simula fallo en el cambio de directorios
y comprueba el rollback del estado anterior.

5. Comprueba historial, PDFs, pedidos y fase activa, y solo entonces reanuda
   el scheduler. Borra la copia `data.pre-restore-*` cuando hayas verificado
   la recuperacion y guardado una copia externa.

No eleves el limite general de subida de 12 MB para restaurar archivos grandes.
La restauracion offline no depende del limite HTTP. No pegues en ChatGPT ZIP
con documentos firmados o datos personales reales.
