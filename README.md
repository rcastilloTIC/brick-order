# VALBRICK - Brick Order Manager (Publica)

Aplicacion web Flask para pedidos colectivos LEGO. Edicion **Publica**, separada e independiente.

**Estado:** candidato de publicacion y despliegue **V93-RC1** (2026-11-01). No es V1.0
certificada. Las suites V92 anteriores fueron comunicadas como satisfactorias
(521 pruebas Publica, 504 Extended), pero los cambios V93 deben ser verificados
de nuevo en Docker antes de atender pedidos o documentos reales.

## Alcance

Pedidos insuficientes, aviso publico y aumentos extraordinarios. No incluye tablas ni rutas de invitaciones privadas.

- Usuarios, compromisos anuales, seleccion final, pedidos, Excel y PDF, archivo historico.
- Docker en Python 3.11 y SQLite persistente en `./data`.
- Limites de referencias y cantidades sujetos a las reglas de la aplicacion.
- El nuevo cierre de pedido desde el panel solo esta habilitado en fases de pedido.
- No utilizar este paquete para activar anios nuevos sin completar la prevalidacion anual.

## Instalacion y publicacion

Consulta **`docs/DESPLIEGUE.md`** antes de ejecutar nada. Resumen:

1. Crear un repositorio publico de GitHub dedicado **solo** a esta edicion.
2. Copiar `.env.example` a `.env`, fijar contrasenas/secretos unicos y
   `SOURCE_CODE_URL` con la URL HTTPS de este repositorio (preferentemente el tag/commit exacto).
3. Preparar `data/` con propietario UID 10001 para el contenedor no privilegiado.
4. Instalar y configurar un proxy HTTPS; la aplicacion solo escucha en
   `127.0.0.1:5001` en el anfitrion, nunca directamente en Internet.
5. Ejecutar `docker compose up --build -d` y revisar logs/salud.
6. Probar en un entorno desechable antes de usar datos reales.

Más información en **`docs/Manuales`**

## Backup y recuperacion

La **creacion y descarga** de copias desde el panel siguen habilitadas.
La **restauracion online** esta deshabilitada para impedir reemplazar SQLite
mientras existan conexiones abiertas. Para restaurar una copia completa, detener
la aplicacion con `scripts/restore_offline.sh` siguiendo
`docs/RECUPERACION.md`. El procedimiento conserva el anterior directorio
`data.pre-restore-*` para recuperarlo. Hay tambien `scripts/create_offline_backup.sh`.

## Seguridad y datos

No publicar `.env`, SQLite, PDFs firmados, exportaciones, backups, datos personales
ni archivos de recuperacion. Revisar el historial Git si reutilizas un repositorio.
Usar HTTPS, no exponer el puerto del contenedor a Internet, no habilitar
`TRUSTED_PROXY_COUNT` si no existe un proxy confiable.

## Licencia

El codigo propio de VALBRICK se distribuye bajo **GNU AGPLv3 exclusivamente**
(`AGPL-3.0-only`). Ver `LICENSE` y `NOTICE`. VALBRICK es el **seudonimo del autor unico**
del codigo propio. Las dependencias mantienen sus licencias. En la version
servida, el pie muestra `SOURCE_CODE_URL` para acceder al codigo correspondiente.

## Limitaciones previas a V1.0

- Los ensayos del nuevo codigo V93 necesitan confirmacion en Docker del autor.
- Probar la interfaz completa con navegador y administracion en una instancia desechable.
- Verificar proxy HTTPS, permisos del volumen, restauracion y alarmas en el servidor real.
- Consolidar lock de dependencias y revisar posibles vulnerabilidades antes del tag estable.
- La siguiente campana anual requiere su prevalidacion; no asumir automatizacion total.
