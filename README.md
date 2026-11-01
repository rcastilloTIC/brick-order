# VALBRICK - Brick Order Manager (Edición Pública)

Aplicación web desarrollada con Flask para gestionar pedidos colectivos de LEGO. La **Edición Pública** es una distribución separada e independiente.

**Estado:** versión candidata para publicación y despliegue **V93-RC1** (2026-11-01). No es una versión V1.0 certificada. La validación automatizada de V93-RC1 se ha completado satisfactoriamente en Docker (**532 pruebas superadas, 1 omitida y 167 subpruebas superadas**). Sigue pendiente la validación manual del despliegue en el servidor definitivo antes de gestionar pedidos o documentos reales.

## Alcance

Gestión de pedidos por debajo del importe mínimo, avisos públicos y aumentos extraordinarios de cantidades. Esta edición no incluye tablas ni rutas de invitaciones privadas.

- Usuarios, compromisos anuales, selección final, pedidos definitivos, exportaciones Excel y PDF y archivo histórico.
- Ejecución mediante Docker con Python 3.11 y almacenamiento persistente SQLite en `./data`.
- Límites por referencia y reglas de cantidad definidos por la aplicación.
- La generación del pedido definitivo desde el panel de administración solo está habilitada en la fase de pedido (`order`).
- No activar una nueva campaña anual sin completar la prevalidación anual.

## Instalación y publicación

Consulta **`docs/DESPLIEGUE.md`** antes de ejecutar cualquier procedimiento. Resumen:

1. Crear un repositorio público de GitHub dedicado exclusivamente a la **Edición Pública**.
2. Copiar `.env.example` a `.env`, configurar contraseñas y claves secretas únicas y establecer `SOURCE_CODE_URL` con la dirección HTTPS del repositorio (preferiblemente vinculada a la etiqueta de versión o al identificador exacto de la confirmación de cambios).
3. Preparar el directorio `data/` con el identificador de usuario UID 10001 como propietario para que el contenedor se ejecute sin privilegios de administrador del sistema.
4. Instalar y configurar un servidor intermediario inverso con HTTPS. La aplicación solo debe estar accesible en `127.0.0.1:5001` del equipo anfitrión, nunca directamente desde Internet.
5. Ejecutar `docker compose up --build -d` y comprobar los registros de funcionamiento y el estado del servicio.
6. Realizar las pruebas en un entorno aislado y desechable antes de utilizar datos reales.

Más información en **`docs/Manuales`**.

## Copias de seguridad y recuperación

La **creación y descarga de copias de seguridad** desde el panel de administración siguen habilitadas.

La **restauración desde la aplicación mientras está en funcionamiento** está deshabilitada para evitar que se sustituya la base de datos SQLite mientras existan conexiones abiertas.

Para restaurar una copia de seguridad completa, utilizar el procedimiento de **restauración sin conexión**, mediante `scripts/restore_offline.sh`, siguiendo las instrucciones de `docs/RECUPERACION.md`.

El procedimiento conserva el directorio anterior `data.pre-restore-*` para permitir la recuperación del estado previo si fuera necesario.

También está disponible `scripts/create_offline_backup.sh` para crear copias de seguridad sin conexión.

## Seguridad y protección de datos

No publicar archivos `.env`, bases de datos SQLite, documentos PDF firmados, exportaciones, copias de seguridad, datos personales ni archivos de recuperación.

Revisar el historial de cambios de Git si se reutiliza un repositorio existente.

Utilizar siempre HTTPS y no exponer directamente el puerto del contenedor a Internet.

No habilitar `TRUSTED_PROXY_COUNT` si no existe un servidor intermediario inverso de confianza correctamente configurado.

## Licencia

El código original de VALBRICK se distribuye **exclusivamente bajo GNU AGPLv3** (`AGPL-3.0-only`).

Consultar los archivos `LICENSE` y `NOTICE`.

**VALBRICK** es el seudónimo del **autor único del código original**.

Las dependencias de terceros conservan sus respectivas licencias.

En la aplicación desplegada, el pie de página muestra el enlace configurado mediante `SOURCE_CODE_URL`, que permite acceder al código fuente correspondiente.

## Limitaciones previas a V1.0

- Aunque V93-RC1 ha superado las pruebas automatizadas en Docker, todavía debe completarse la validación manual del despliegue real.
- Probar la interfaz completa, las funciones de usuario y el panel de administración en una instalación de prueba aislada y desechable.
- Verificar el servidor intermediario inverso con HTTPS, los permisos del almacenamiento persistente, la restauración sin conexión y las alertas de supervisión en el servidor definitivo.
- Establecer un archivo que fije las versiones exactas de las dependencias y revisar las posibles vulnerabilidades antes de crear la etiqueta de la versión estable.
- La siguiente campaña anual requiere su propia prevalidación anual; no debe asumirse una automatización completa.

---

# VALBRICK - Brick Order Manager (Public Edition)

Flask web application for managing group LEGO orders. The **Public Edition** is a separate and independent distribution.

**Status:** publication and deployment release candidate **V93-RC1** (2026-11-01). This is not a certified V1.0 release. Automated validation of V93-RC1 has been successfully completed in Docker (**532 tests passed, 1 skipped, and 167 subtests passed**). Manual deployment validation on the final server is still required before processing real orders or documents.

## Scope

Management of orders below the minimum amount, public notices, and extraordinary quantity increases. This edition does not include private invitation tables or routes.

- Users, annual commitments, final selection, final orders, Excel and PDF exports, and historical archives.
- Deployment through Docker with Python 3.11 and persistent SQLite storage in `./data`.
- Item reference limits and quantity rules defined by the application.
- Final order generation from the administration panel is only enabled during the order phase (`order`).
- Do not activate a new annual campaign without completing its annual pre-validation.

## Installation and publication

Read **`docs/DESPLIEGUE.md`** before running any procedure. Summary:

1. Create a public GitHub repository dedicated exclusively to the **Public Edition**.
2. Copy `.env.example` to `.env`, configure unique passwords and secrets, and set `SOURCE_CODE_URL` to the repository's HTTPS URL (preferably pointing to the exact tag or commit).
3. Prepare the `data/` directory with UID 10001 as its owner for the unprivileged container.
4. Install and configure an HTTPS reverse proxy. The application must only be accessible at `127.0.0.1:5001` on the host server, never directly from the Internet.
5. Run `docker compose up --build -d` and check the service logs and health status.
6. Perform testing in a disposable test environment before using real data.

More information is available in **`docs/Manuales`**.

## Backup and recovery

**Creating and downloading backups** from the administration panel remain enabled.

**Online restore** is disabled to prevent the SQLite database from being replaced while active connections are open.

To restore a complete backup, use the **offline restore** procedure through `scripts/restore_offline.sh`, following the instructions in `docs/RECUPERACION.md`.

The procedure preserves the previous `data.pre-restore-*` directory, allowing recovery of the previous state if necessary.

The `scripts/create_offline_backup.sh` script is also available for creating offline backups.

## Security and data protection

Do not publish `.env` files, SQLite databases, signed PDF documents, exports, backups, personal data, or recovery files.

Review the Git history if reusing an existing repository.

Always use HTTPS and do not expose the container port directly to the Internet.

Do not enable `TRUSTED_PROXY_COUNT` unless a properly configured trusted reverse proxy is in place.

## License

VALBRICK's original code is distributed **exclusively under GNU AGPLv3** (`AGPL-3.0-only`).

See the `LICENSE` and `NOTICE` files.

**VALBRICK** is the pseudonym of the **sole author of the original code**.

Third-party dependencies retain their respective licenses.

In the deployed application, the footer displays the link configured through `SOURCE_CODE_URL`, providing access to the corresponding source code.

## Limitations before V1.0

- Although V93-RC1 has passed automated testing in Docker, manual validation of the actual deployment is still required.
- Test the complete user interface, user features, and administration panel in a disposable test instance.
- Verify the HTTPS reverse proxy, persistent volume permissions, offline restore, and monitoring alerts on the final server.
- Establish a dependency lockfile and review potential vulnerabilities before creating the stable release tag.
- The next annual campaign requires its own annual pre-validation; full automation must not be assumed.
