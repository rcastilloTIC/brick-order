# VALBRICK | Pública | Manual de administrador

**V93-RC1**  |  **2026-11-01**  |  **AGPL-3.0-only**  |  **VALBRICK**

> Basado en los archivos de código de la edición validada. Candidato de publicación; no equivale a certificación de producción.

---

## Alcance, autoridad y advertencias
Este manual describe la operación de **VALBRICK Pública** sobre el código V93-RC1. El administrador gestiona personas, catálogo, fases, costes y pedidos con consecuencias reales. Una prueba automatizada verde no sustituye el despliegue HTTPS ni la revisión humana de una campaña.

**Reglas obligatorias:** no usar datos reales en `isolated`, no restaurar bases con Flask encendida, no subir documentos firmados a GitHub y no mezclar el código de Pública con Extended. Las fases de una campaña archivada no se reabren desde la interfaz.

## 1. Roles y primeros controles
1. Confirma la edición indicada por el archivo `EDITION` (`PUBLICA`) y el año operativo mostrado en el panel.
2. Accede mediante la clave del sitio y tu cuenta administrativa. Solo los usuarios con `is_admin` pueden utilizar rutas `/admin` y gestionar pedidos de terceros.
3. Revisa la configuración de producción: HTTPS, secreto de sesión, contraseñas iniciales, enlace AGPL al código, proxy y volumen persistente. El manual de programación explica las claves exactas.
4. Antes de importar o editar nada, crea y descarga una copia. Guarda otra fuera del servidor.
5. No utilices **modo de pruebas** para calcular compromisos definitivos: cambia límites y la semantica de algunos controles. El modo de pruebas debe estar claramente deshabilitado antes de usar datos reales.

## 2. Panel administrativo y navegación
El panel principal contiene secciones **Productos, Ranking, Usuarios, Colores, Pedidos y Logs**. Otras pantallas incluyen **Campañas**, **Preparacion anual**, **Calendario**, **Auditoria**, **Límites**, **Traducciones**, **Estadisticas** y **Simulador**. Las acciones de fase suelen ser botones de formulario: revisa el texto y el estado activo antes de pulsarlos.

**Regla del panel:** una redireccion HTTP después de enviar un formulario no demuestra que se haya efectuado la operación. Revisa siempre el mensaje de exito/error y el registro de destino.

## 3. Dar de alta participantes con CSV
Pantalla: `/admin/upload-users`. El CSV debe codificarse en **UTF-8**, con encabezado y las columnas obligatorias `username,password`. Se admiten otras como `first_name,last_name,dni,active,agreements,agreements_accepted,paid,declaration`.

```csv
username,password,first_name,last_name
persona_01,CLAVE_PROVISIONAL_UNICA_01,Ana,Ejemplo
persona_02,CLAVE_PROVISIONAL_UNICA_02,Luis,Ejemplo
```

**Ejemplo ficticio exclusivamente.** No publiques un CSV con contraseñas ni datos personales. El importador rechaza una columna `is_admin`, encabezados duplicados y la edición accidental de cuentas administrativas. Para identidades existentes de otra campaña, evita sobrescribir contraseñas y aprobaciones previas: la inscripción anual vive en `CampaignParticipation`. Un usuario nuevo debe cambiar su contraseña inicial.

Cuando prepares un borrador anual, usa la pantalla de participantes de **ese borrador**, no la importacion de la campaña activa. Las identidades y autorizaciones no deben trasladarse implicitamente.

## 4. Documento de compromiso y aprobación
1. Abre **Gestión del compromiso** (`/admin/commitment`) y carga o configura el documento oficial para la campaña.
2. Comprueba su disponibilidad desde una cuenta de ensayo no administrativa mediante `/commitment/download`.
3. Cada participante descarga, firma y sube un PDF. El panel permite **Validar DJ**, **Invalidar DJ** y, en casos autorizados, eliminar la referencia al documento. Revisa el documento real, no solo su extension.
4. La aprobación debe estar asociada al año activo. Una aprobación de un año archivado no habilita por si sola la campaña siguiente.
5. Los PDFs firmados contienen datos personales: no los incluyas en backups compartidos sin protección, commits, issues ni mensajes de soporte.

## 5. Importar el catálogo Excel
Pantalla: `/admin/upload-data`. Usa un `.xlsx` con cabecera y una columna de referencia identificable como **Material**, **Communication number** o `reference`; otra para **Description** o `name`. El importador reconoce precio (`2026_prices_in_eur`, `2025_prices_in_eur` o `price`), identificador de color, imagen y grupos, entre otras columnas.

| Material | Description | 2026_prices_in_eur | colour_id |
|---|---|---:|---|
| 300100 | Pieza ficticia roja | 1.00 | 5 |
| 300101 | Pieza ficticia azul | 2.00 | 1 |

**Verifica siempre la previsualizacion/reporte:** precios importados, referencias duplicadas, colores, filas descartadas y diferencias entre el catálogo anterior y el nuevo. Cambiar precios después de admitir compromisos afecta cantidades y límites; exige copia, revisión y comprobaciones de integridad. Un catálogo de borrador se importa desde `/admin/campaign-draft/<id>/catalog` y se válida integro antes de escribir.

## 6. Fases del ciclo de pedido
| Estado interno | Accion administrativa | Condicion decisiva |
|---|---|---|
| `first` | Abrir segunda fase | La campaña debe estar en primera fase. |
| `second` | Pasar a selección final | Revisar el mínimo y el ranking. |
| `final` | Resolver selección y activar pedidos | Sin empates pendientes, sin exceso de referencias y con selección no vacia. |
| `order` | Confirmar pedidos y generar documentos | Compromisos seleccionados materializados en `Order`. |

Las transiciones usan `/admin/phase/activate-second`, `/admin/phase/advance-final` y `/admin/phase/advance-order`. El paso `final -> order` recalcula la selección, materializa las cantidades aceptadas y cambia de fase en una sola transacción; si algo falla, revierte todos los cambios. Las copias automáticas antes de fases **pueden fallar sin bloquear la transición**: si ves el aviso de backup fallido, genera otra copia y descarga el log.

## 7. Gestión del ranking y productos
En **Ranking** verifica las referencias seleccionadas, bloqueadas y descartadas, su posicion, votos y total en euros. El limite normal de selección final parte de 85 referencias, pero puede configurarse por campaña y el modo de pruebas lo modifica. Los desempates y los excesos impiden liberar pedidos. No utilices **promover todas** sin comprobar el impacto y las reglas activas.

En **Productos** comprueba el bloqueo de referencias, nombre, código, color, precio y restricciones de voto. El sistema protege registros históricos; borrar productos o cuentas con pedidos no es un método válido de limpieza.

## 8. Límites, fechas y calendario
En `/admin/settings/limits` modifica los límites anuales que ofrece la interfaz, como mínimo colectivo, limite de importe individual y número de seleccionadas. Otros topes de referencias proceden de `config.py`, no de todos los campos editables del panel. **No supongas que todos los parametros son configurables por campaña**.

Las fechas pueden ajustarse en `/admin/set-dates` y `/admin/campaigns/<id>/calendar` con comprobaciones de solapamiento. Cambiar el calendario mientras hay participantes y votos exige revisar el estado real, la zona horaria del servidor y si existe automatizacion externa de snapshots o reconciliacion. Documenta cada cambio.

## 9. Preparar y cerrar el pedido final
1. Llega a `order` desde `final` usando el boton de liberar pedidos; el boton **Realizar pedido** debe estar deshabilitado antes de ese paso.
2. Comprueba las cantidades materializadas y el total de las referencias finalmente seleccionadas. No sumes simultaneamente `UserVote` y `Order`: tras la materializacion la fuente de exportación son los pedidos.
3. Revisa el mínimo colectivo (configuración de campaña; el valor por defecto de código es **4800 EUR**) y los límites individuales. Fuera de modo de pruebas, una cantidad inferior al mínimo no produce el Excel final directamente.
4. Configura impuesto y transporte si procede. Valida IBAN y fecha limite futura cuando los datos de pago deban aparecer en los PDFs.
5. Pulsa **Realizar pedido**. Debe guardar `final_order_generated_at` y crear el Excel definitivo más dos paquetes ZIP con PDFs por referencia y por usuario; también se generan PDFs consolidados internamente.
6. Descarga los archivos desde **Pedidos** y abre varios PDFs, especialmente aquellos sin imagen. Compara referencias, cantidades, precios, impuestos y transporte.
7. Una vez cerrado el pedido, las ediciones normales quedan bloqueadas. El boton de regeneracion puede crear nuevos archivos usando los datos de pago actualizados: revisa los logs y no confundas una notificacion de inicio con una finalizacion acreditada.

**Archivado:** `/admin/campaign-archive` solo admite la campaña operativa indicada por el año confirmado, una fase de pedido compatible, marca de generación y Excel válido. Comprueba que el Excel coincide exactamente con pedidos, referencias, cantidades y precios. Una edición manual del XLSX invalida el archivado.

## 10. Exclusivo de Pública: pedido insuficiente
Si el total real de `Order` es inferior al mínimo, abre `/admin/shortage`. Puedes **Avisar y abrir plazo** entre 1 y 30 días. El mensaje se pública para participantes elegibles; cada uno debe aceptar el aviso antes de ampliar. Los aumentos usan solo referencias seleccionadas y límites personales disponibles.

Puedes **Revisar cumplimiento ahora** para reconciliar el estado. `reconcile()` cierra el plazo como alcanzado si se consigue el mínimo; también puede cancelarlo cuando vence. El cierre por vencimiento no sucede por magia en ausencia de solicitudes o del trabajador externo: planifica su ejecución si necesitas automatizacion puntual. La cancelacion manual exige escribir `CANCELAR` y no borra los pedidos archivados. No generes Excel definitivo mientras siga sin cumplirse el mínimo en modo normal.

La campaña no tiene `FinalExtensionInterest` ni rutas de invitaciones privadas. No emplees instrucciones de Extended aquí.

## 11. Archivo anual, borrador y preparación del siguiente año
1. Descarga una copia del Excel y los PDF ya generados y verifica que los ficheros están presentes en el servidor.
2. Desde **Campañas** usa el cierre/archivo confirmando **exactamente el año** solicitado. La operación preserva las filas históricas.
3. Solo después de archivar podrás crear un borrador de un año posterior; su estado es `draft`, nunca una campaña operativa por crear el registro.
4. Importa el catálogo del borrador y el listado de participantes del borrador, sin reactivar por accidente inscripciones antiguas.
5. Abre `/admin/campaign-readiness` y las auditorias anuales. Corrige incoherencias de tablas, permisos, documentos, registros sin año o solapamientos antes de activar.
6. La activacion de borrador usa una transacción y validaciones adicionales; si no supera el preflight, **no la fuerces con SQL manual**.

**Advertencia para mantenedores:** varios comentarios de compatibilidad heredada siguen presentes en el código; los procesos de nueva campaña requieren prevalidación específica, aun cuando las pruebas de escenarios anuales pasan. No prometas una migración universal de bases históricas sin ensayo.

## 12. Copias de seguridad y recuperación real
**Desde la web:** `Crear backup manual`, `Descargar backup` y `Descargar log de error`. El formulario antiguo de `Restaurar` puede aparecer en una plantilla por compatibilidad, pero el endpoint `/admin/backup/restore` devuelve **409** y no debe utilizarse.

**Copia fuera de la web:** desde la carpeta de despliegue, después de detener tareas externas que escriban en SQLite:

```sh
sh scripts/create_offline_backup.sh
```

**Restaurar una copia completa:** prepara una segunda copia externa, detiene las tareas programadas y ejecuta:

```sh
sh scripts/restore_offline.sh ./data/backups/NOMBRE_DEL_BACKUP.zip
```

El procedimiento para el contenedor, verifica archivo y SQLite, comprueba la edición y conserva `data.pre-restore-*`. Si falla, no reinicies automáticamente: inspecciona logs y estado; válida la campaña y documentos antes de volver a abrir acceso. Sigue `docs/RECUPERACION.md`.

## 13. Diagnosticos y auditoria
- `/admin/audit`: revisa la integridad y problemas de campañas.
- `/admin/campaign-readiness`: informe de condiciones para iniciar un nuevo año; diagnostica, no sustituye una autorización.
- `/admin/campaign-history`: consulta histórica, no tabla editable de pedidos antiguos.
- `/admin/simulator`: utiliza resultados ilustrativos, no compromisos reales.
- `/admin/translations`: personaliza claves permitidas de idioma; importa/exporta JSON y conserva cambios en `/data/translations`.
- `docker compose logs --tail=80 app`: muestra errores de contenedor y aplicación.

Ante un error reproducible, guarda: fecha, año, fase, ruta, accion, resultado esperado, resultado observado, log sin datos sensibles y referencia al ZIP versionado.

## 14. Operación segura del servidor
- Docker debe ejecutarse con volumen `./data:/data`, usuario no-root UID 10001 y permisos adecuados. Las claves `.env` no se incluyen en repositorios.
- Mantener `127.0.0.1:5001` como vinculo del contenedor y HTTPS delante mediante proxy confiable. Ajustar `TRUSTED_PROXY_COUNT` solo si el proxy sobrescribe cabeceras reenviadas.
- `SOURCE_CODE_URL` debe apuntar al código exacto de esta edición para ofrecer el acceso a fuentes AGPL.
- Antes de actualizar, crear copia externa; probar en `isolated`; revisar esquemas; usar `docker compose up --build -d`; verificar estado y logs. **No ejecutar `docker compose down -v`** sobre datos importantes.
- Establecer rotacion/retencion de backups, monitorizar espacio de disco, seguridad de dependencias y caducidad de certificados.

## 15. Plan de ensayo manual de aceptacion
| Caso | Resultado esperado |
|---|---|
| Usuario provisional entra y cambia contraseña | Accede solo tras completar el cambio. |
| Documento anual de participante | Queda pendiente hasta validación y no usa aprobación vieja. |
| CSV y Excel en instalacion ficticia | Se importan sin elevar privilegios ni duplicar referencias. |
| Fase `final` con empate | No permite liberar pedidos. |
| Fase `order` con selección válida | Boton Realizar pedido habilitado; cantidades materializadas. |
| Excel y paquetes PDF | Contenidos descargables, totales coherentes. |
| Excel modificado a mano | Archivado rechazado. |
| Archivo anual válido | Estado `archived`, historial intacto. |
| Nuevo borrador | No hereda votos ni pedidos del año anterior. |
| Restauración web | Rechazada con 409 sin mutacion. |
| Restauración offline | Mantiene copia anterior y permite recuperación probada. |

## 16. Checklist final del administrador
- [ ] Confirmado `EDITION`, año, servidor y dominio correctos.
- [ ] Fuera de modo de pruebas; límites, fechas, catálogo y documentos revisados.
- [ ] Usuarios aprobados para **este** año; autorizaciones y consentimiento registrados.
- [ ] Selección final comprobada; pedidos y cantidades conciliados.
- [ ] Procedimiento específico de esta edición concluido antes de exportar.
- [ ] Excel, ZIP/PDF y datos de pago contrastados.
- [ ] Backup local + copia externa; recuperación probada con datos ficticios.
- [ ] Auditoria anual sin problemas pendientes; historial conservado.
- [ ] HTTPS, permisos, seguridad del servidor y enlace AGPL revisados.

## Referencias de código
`app/main/routes.py`, `app/auth/routes.py`, `app/services/campaign_phase.py`, `app/services/campaign_settings.py`, `app/services/final_selection.py`, `app/services/order_materialization.py`, `app/services/order_exports.py`, `app/services/campaign_archive.py`, `app/services/backups.py`, `docs/DESPLIEGUE.md` y `docs/RECUPERACION.md`. Consulta el manual de programación para arquitectura, contratos y pruebas.

