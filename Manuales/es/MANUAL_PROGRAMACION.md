# VALBRICK | Pública | Manual de programación y mantenimiento

**V93-RC1**  |  **2026-11-01**  |  **AGPL-3.0-only**  |  **VALBRICK**

> Basado en los archivos de código de la edición validada. Candidato de publicación; no equivale a certificación de producción.

---

## Propósito y contrato de mantenimiento
Este manual esta redactado para una persona que sabe poco de Python y para quien asuma la responsabilidad técnica completa. No es una introducción genérica: explica **este repositorio**, los contratos que sostienen las cantidades y los anejos de rutas, modelos, servicios y pruebas del código examinado. Sigue siendo necesario leer los ficheros fuente antes de cambiar una regla.

- **Edición y revisión**: Pública **V93-RC1**. Mantener un repositorio y despliegue propios para esta edición.
- **Estado de validación comunicado**: 532 pruebas superadas, 1 omitida, 167 subtests, sin fallos en Docker; E2E y verificaciones de release superadas.
- **No V1.0 certificada**: la auditoria final del servidor, HTTPS, controles manuales y politica de dependencias aun son responsabilidades del desplegador.
- **Regla de negocio innegociable**: nunca convertir un voto rechazado en pedido, nunca contar dos veces un compromiso, nunca mezclar años, nunca perder cantidades elegidas ni datos históricos.

### Como estudiar el proyecto
Primera lectura: capítulos 1-6, luego observa `app/models.py` y la ruta de un formulario en `app/main/routes.py`. Segunda lectura: capítulos 7-16 y ejecuta una prueba pura sin base de datos. Tercera lectura: flujos anuales, SQL y ensayos E2E. Antes de modificar código, escribe una prueba que falle si se rompe lo que quieres conservar.

## 1. Glosario técnico para principiantes
**Funcion**: bloque `def nombre(...):` que recibe datos y devuelve un resultado. **Modulo**: un archivo `.py`. **Import**: acceso a otra función o clase. **Clase**: plantilla para objetos. **Modelo ORM**: clase Python que representa una tabla SQL. **Base de datos**: archivos SQLite con registros, indices y triggers. **Ruta HTTP**: URL asociada a una función Flask. **GET**: lectura; **POST**: petición que normalmente cambia datos. **Blueprint**: conjunto de rutas Flask. **Plantilla Jinja**: HTML con expresiones `{{ ... }}` y condicionales `{% ... %}`. **Transaccion**: conjunto de escrituras que se confirman o revierten juntas. **Commit**: confirmar; **rollback**: deshacer la transacción pendiente. **Fixture**: datos y entorno controlados para pruebas. **E2E**: ensayo que recorre varias capas reales de la aplicación.

Un ejemplo de la cadena de ejecución es:

```text
Navegador -> HTTPS/Caddy -> Gunicorn -> Flask route (/vote)
   -> autenticacion + CSRF + comprobacion de campana
   -> quantity_rules / commitment_ledger
   -> SQLAlchemy session -> SQLite
   -> commit -> redirect + flash -> plantilla HTML
```

Una redireccion no es igual a una insercion exitosa. El endpoint puede responder 302 tras mostrar un error de negocio. Las pruebas deben observar **base de datos, valores y avisos**, no solo el código de respuesta.

## 2. Mapa de carpetas y entrada de ejecución
| Ruta | Responsabilidad |
|---|---|
| `run.py` | Carga `.env`, escoge configuración, crea la app, llama a `init_db()` y expone `app` a Gunicorn. |
| `wsgi.py` | Entrada alternativa Flask; no sustituye automáticamente a `run.py` en el contenedor. |
| `config.py`, `.env.example` | Valores de seguridad, base de datos, costes y límites. |
| `app/__init__.py` | Factory `create_app`, extensiones, login, CSRF, rate limiting, proxy y preparación del esquema SQLite. |
| `app/models.py` | Tablas, relaciones, indices ORM y barrera de borrado de padres con pedidos. |
| `app/auth/routes.py` | Acceso, perfil, cambio de clave, documento firmado y onboarding. |
| `app/main/routes.py` | Panel de usuario y administrador, votaciones, fases, importaciones, pedido final e histórico. |
| `app/main/translation_admin.py`, `app/i18n.py` | Editor y carga de traducciones ES/EN. |
| `app/services/` | Lógica de negocio reutilizable: companas, límites, materializacion, exportaciones, archivo, backup. |
| `orders/`, `products/` | Blueprints con vistas complementarias. |
| `templates/`, `static/` | Jinja HTML, CSS y JS de interfaz. |
| `scripts/` | Mantenimiento, auditoria, importacion, backups y pruebas aisladas. |
| `tests/` | Contratos unitarios, integración SQLite, seguridad, HTTP, E2E y release. |
| `docs/` | Instrucciones originales de despliegue y recuperación. |
| `data/` | Volumen persistente del despliegue; NUNCA pertenece al repositorio público. |
| `LICENSE`, `NOTICE`, `EDITION`, `VALBRICK_EDITION` | Licencia y delimitacion de la edición. |

**Primer ejercicio de lectura:** busca en `templates/user_dashboard.html` el formulario que apunta a `/vote`; localiza en `app/main/routes.py` la función `vote`; sigue sus llamadas a servicios y los modelos afectados. Repitelo para `/admin/order/generate`.

## 3. Entorno reproducible y primeros comandos
El runtime de producción es **Python 3.11**, Flask 2.2-2.x, Flask-SQLAlchemy 3.x, SQLite, Gunicorn, openpyxl y fpdf2, con dependencias adicionales en `requirements.txt`. Usa Git y Docker Compose. Nunca ejecutes los scripts aislados contra un volumen de producción.

**A. Tests aislados recomendados en una carpeta clonada:**

```sh
sh scripts/run_v93_release_isolated.sh
sh scripts/run_v92_e2e_isolated.sh
sh scripts/run_full_tests_isolated.sh
```

Los runners construyen imagenes Docker sin montar tus datos ni publicar puertos. No requieren pytest instalado en el ordenador. Antes de cambiar código, guarda los resultados como línea base.

**B. Desarrollo local opcional solo con datos ficticios:**

```sh
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-dev.txt
cp .env.example .env
# Editar .env: SECRET_KEY aleatoria, ADMIN_PASSWORD,
# SITE_ACCESS_PASSWORD, DEFAULT_USER_PASSWORD y SOURCE_CODE_URL validos.
# Cambiar FLASK_ENV=development, HOST=127.0.0.1, PORT=5001.
python run.py
```

`run.py` importa clases de configuración con validaciones de seguridad: aun en desarrollo configura todas las claves necesarias. El valor `DATABASE_URL` por defecto apunta al archivo local `mi_app.db`; **fija explicitamente una base desechable** y nunca reutilices la de trabajo de un usuario. Despues de desarrollar, ejecuta tests con el mismo runtime Python 3.11 que Docker.

**C. Inspeccionar el servidor sin modificar datos:**

```sh
docker compose config --quiet
docker compose ps
docker compose logs --tail=80 app
```

## 4. Flask y ciclo de una solicitud
`create_app()` en `app/__init__.py` crea Flask, aplica config **antes** de decidir si confiar en `X-Forwarded-*`, inicializa SQLAlchemy, Flask-Login, CSRFProtect, Flask-Limiter e i18n y registra blueprints `auth`, `main`, `translations_admin`, `products`, `orders`. `before_request` impone la clave de acceso general (si esta configurada), cambio obligatorio de clave y, para participantes, inscripción/documento/aprobación en la campaña activa.

La sesión de Flask usa cookies HTTP-only, SameSite Lax y `Secure=true` en producción. Hay protección CSRF en formularios POST; copiar una ruta y quitar su token no es una solucion. La variable `TRUSTED_PROXY_COUNT` permite ProxyFix solo detras de un proxy que limpie cabeceras reenviadas. El limitador de intentos de login es independiente del presupuesto de voto.

**Patron de una ruta segura:** autenticar -> determinar campaña activa -> verificar permiso anual -> leer y validar todos los datos -> comprobar fase y límites -> escribir en una transacción -> log y commit -> mostrar resultado. No ejecutar `commit()` en funciones auxiliares que deban formar parte de una transacción mayor.

## 5. Configuración: que cambia y donde
| Clave | Significado / cuidado |
|---|---|
| `SECRET_KEY` | Firma las sesiones. Se genera fuera del repositorio, única por despliegue. |
| `ADMIN_USERNAME`, `ADMIN_PASSWORD` | Usuario inicial de administración. `init_db()` exige clave inicial de al menos 12 caracteres. |
| `DEFAULT_USER_PASSWORD` | Contrasena de reserva para importacion de usuarios; no se pública. |
| `SITE_ACCESS_PASSWORD` | Pantalla de acceso previa a login; distinta de la contraseña personal. |
| `DATABASE_URL` | Ubicacion SQLite; en Docker `sqlite:////data/db/app.sqlite`. |
| `DECLARATION_UPLOAD_FOLDER` | PDFs firmados; directorio persistente y privado. |
| `ORDER_EXPORT_FOLDER` | Excel y archivos de PDF; directorio persistente y protegido. |
| `BACKUP_FOLDER` | Copias; no subir a GitHub. |
| `SOURCE_CODE_URL` | URL HTTPS al código correspondiente de **esta edición**, visible para AGPL. |
| `TRUSTED_PROXY_COUNT` | Numero de proxies fiables que sobrescriben `X-Forwarded-*`; usar 0 si no hay uno. |
| `SESSION_COOKIE_SECURE` | Requiere HTTPS para mantener la sesión; debe ser true en producción. |
| `PORT` | Puerto interno/host configurado, por defecto 5001. |
| `PHASE_ONE_ORDER_LIMIT` | Presupuesto personal por defecto: 235 EUR, sujeto a ajuste anual y modo de pruebas. |
| `MIN_TOTAL_ORDER_AMOUNT` | Mínimo colectivo por defecto: 4800 EUR, sujeto a ajuste anual. |
| `MAX_REFERENCES_PER_USER` | Tope de referencias primera fase: 10 por defecto. |
| `PHASE_TWO_REFERENCE_LIMIT` | Tope segunda fase: 20 por defecto. |
| `FINAL_SELECTION_LIMIT` | Selección final: 85 referencias por defecto. |
| `DEFAULT_LANGUAGE`, `SUPPORTED_LANGUAGES` | Idioma inicial y lenguajes disponibles, normalmente `es,en`. |
| `ENABLE_ANNUAL_ACTIVATION` | Gate deliberado: solo `1` permite activar un borrador tras pasar preflight. No habilitar sin revisar las rutas anuales. |

Los ajustes con significado **anual** no deben almacenarse como claves globales simples. `app/services/campaign_settings.py` utiliza una lista de permitidos `ANNUAL_KEYS` y nombres `annual_<campaign_id>_<key>`. Un nuevo ajuste anual requiere agregar la clave a esta lista **y pruebas que demuestren aislamiento entre campañas**. El incidente de Extended RC1/RC2 fue exactamente la ausencia de una clave privada en la lista, que provocaba errores 500.

## 6. Git, ramas, cambios y versionado
Cada edición vive en un repositorio separado; no copies `app/main/routes.py` de una a otra: contienen procedimientos incompatibles. Una tarea tipica sigue este orden:

```sh
git checkout -b fix/resumen-pedido
# editar un modulo y crear/ampliar prueba
sh scripts/run_v93_release_isolated.sh
sh scripts/run_v92_e2e_isolated.sh
sh scripts/run_full_tests_isolated.sh
git status --short
git diff --check
git add app tests docs
git commit -m "Test and fix selected order summary"
```

Revisa siempre el diff antes del commit. `LICENSE`, `NOTICE` y el credito VALBRICK se conservan. Excluir `.env`, `data/`, backups, bases SQLite, certificados, CSV con claves, PDFs reales y `.pytest_cache` mediante `.gitignore`; examinar también el historial de Git, no solo el último commit.

## 7. Dominio: identidad, campaña y propiedad de los datos
El modelo mental correcto **no** es "un usuario tiene un pedido global". Hay dos ejes: una identidad `User` puede vivir varios años; una `CampaignParticipation` representa inscripción/aprobación para **un** `Campaign`. Las filas `Product`, `UserVote`, `UserFavorite` y `Order` contienen `campaign_id` y deben consultar solo el año activo. `Campaign` usa estados `legacy_active`, `draft`, `archived` o `closed`. El estado `draft` es preparación, no permiso de votar.

```text
User (identidad duradera) ----< CampaignParticipation >---- Campaign (ano)
   |                               |                          |
   +---- UserVote -----------------+---- Product --------------+
   +---- Order ------------------------- Product [seleccionado]|
   +---- UserFavorite ------------------ Product               |
   +---- ActionLog (auditoria)                                  |

Config: ajustes anuales namespaceados / fase especifica de campaña
CampaignInsightSnapshot: observaciones agregadas por campaña
```

En SQLite existen constraints e indices parciales, triggers de pertenencia anual, guards de productos entre años, control inverso de miembros y protección de filas archivadas. **No son adornos**: impiden que un script SQL fuera de Flask cambie una relación ya histórica. `app/__init__.py:init_db` y `_ensure_schema` realizan verificaciones/backfill; `db.create_all()` no es una migración general capaz de reconciliar cualquier base antigua.

**Invariante de consulta:** las funciones `products_query()`, `orders_query()`, `votes_query()` y `favorites_query()` de `app/services/campaign_data.py` son preferibles a consultar tablas operativas sin filtro anual. Un `User.query` puede ser global porque la identidad persiste, pero cualquier permiso de pedido necesita un join a la participación de **esa** campaña.

## 8. Estados, calendario y cambios atomicos
La fase se guarda de forma anual en `phase_campaign_<id>` (modulo `campaign_phase.py`). El acceso a una clave global `phase` se mantiene solo como compatibilidad de bases con exactamente una campaña. No debes heredar `order` del año archivado al activar otro año. Las fases funcionales son:

```text
first --activate-second--> second --advance-final--> final
    --advance-order + seleccion + materializacion atomica--> order
```

`annual_readiness.inspect_annual_readiness()` examina campañas, filas sin `campaign_id`, miembros ausentes, relaciones cruzadas y preparación del borrador. `campaign_calendar` válida fechas y solapamientos. `campaign_activation.activate_prepared_draft()` exige `ENABLE_ANNUAL_ACTIVATION=1`, texto de confirmación `ACTIVAR <ano>`, calendario válido y preflight limpio. Una base antigua puede necesitar una migración específica antes de esa activacion.

**Atomicidad en el paso `final -> order`:** `compute_final_selection(persist=False)` verifica empates y exceso sin escribir; luego se persiste la selección, `materialize_selected_commitments()` crea solo los registros faltantes, `assert_selected_commitments_materialized()` revisa el suelo prometido y `set_current_phase('order', commit=False)` cambia la fase. **Un único `db.session.commit()`** cierra el conjunto. Cualquier excepción provoca rollback total.

## 9. Compromisos, céntimos y cantidades
El problema histórico más peligroso es mantener dos representaciones de una compra: `UserVote` y `Order`. `commitment_ledger.committed_total()` agrega por producto dentro de cada fuente y toma **el mayor total por producto** entre voto y pedido. Ejemplo: referencia A con 50 votos y 50 pedidos cuenta 50, no 100; referencia B con 25 votos y 0 pedidos cuenta 25. Por eso tampoco se puede usar `max(total_votos, total_pedidos)` global, que perderia referencias disjuntas.

Despues de selección final, `effective_commitment()` solo incluye referencias elegidas; los votos de descartadas siguen en SQLite como historial, pero no se materializan ni se facturan. La regla de precio/cantidad `validate_quantity()` usa `Decimal`: `price <= 1.35` exige mínimo 25 y paso 25; `price > 1.35`, mínimo 10 y paso 10. Rechaza `bool`, `NaN`, infinitos, negativos y cantidades no enteras. En calculos financieros usa `Decimal(str(price))`, no acumulaciones ingenuas en `float`.

Para materializar, `missing_order_floors()` calcula `(usuario, producto) -> max(0, cantidad_votada - cantidad_pedida)`. Solo referencias seleccionadas. `materialize_selected_commitments()` guarda el deficit; es **idempotente**, por lo que repetirla no duplica filas. `assert_selected_commitments_materialized()` es la barrera antes de exportar. **Nunca borres la cantidad de una referencia votada solo porque no fue seleccionada**: conserva la trazabilidad.

### Ejercicio de razonamiento (sin ejecutar)
Si una persona vota A=25, B=10 y hay pedido A=25, B=0, la obligacion activa antes de selección incluye 25 de A y 10 de B. Si solo A queda seleccionada, `Order` debe representar al menos A=25, no B. Un aumento posterior de A en +25 lleva A a 50, no 75. Esta es la clase de caso que merece una prueba unitaria con distintas fuentes y precios.

## 10. Ranking y selección final
`app/services/final_selection.py` calcula agregados por referencia, prepara la clasificación, considera bloqueos/promociones y distingue elementos seleccionados, descartados, empates y exceso sobre limite. `compute_final_selection(limit=..., persist=False)` es la consulta de prevalidación; con `persist=True` puede actualizar marcas `Product.final_selected`, `final_disabled`, `final_promoted`. Las pruebas de desempate deben comprobar que los bloques de empate no producen una selección arbitraria al cambiar el orden SQL.

La cantidad seleccionada no se deduce de "tiene algun voto". `Product.final_selected` y `final_disabled` forman parte del contrato; la exportación filtra seleccionadas que **no** están deshabilitadas. Verifica el número máximo por campaña y los estados manuales antes de liberar pedidos.

## 11. Flujo de voto HTTP y límites reales
El usuario autenticado llega a `main.user_dashboard` (`/dashboard`) y envia `/vote` con `product_id` y `quantity`. La ruta comprueba fase, producto del año activo, documento/participación, cantidad, límites individuales y reglas de no-reduccion. La ruta de favoritos `/favorite` no altera votos; `/vote/delete` tiene restricciones de fase y compromiso. No asumas que `orders/create` es un carrito de compra libre: es un control administrativo y exige participante aprobado.

**Disciplina de cambios:** no dupliques verificaciones financieras en una ruta nueva. Reutiliza `quantity_rules`, `commitment_ledger` y el control de selección/campaña. Añade pruebas para precio limite exacto, ausencia de producto, producto de otro año, participante no aprobado y dos peticiones concurrentes.

## 12. Del pedido a Excel, PDF y archivo
`order_exports.build_final_order_context()` lee votos antes de abrir pedidos y **Order** en `order` y `final_extension`. Devuelve referencias con unidades e importes y desgloses por participante. `assert_current_export_summary()` vuelve a calcular un fingerprint y evita exportar una fotografia obsoleta o alterada. `generate_order_files()` exige suelos de voto presentes y crea:

| Fichero | Contenido |
|---|---|
| `pedido_total_<timestamp>.xlsx` | Una hoja `Pedido` con referencia, nombre, color, precio, cantidad e importe, más total. |
| `pedido_por_pieza_<timestamp>.zip` | PDF conjunto y PDFs por referencia. |
| `pedido_por_usuario_<timestamp>.zip` | PDF conjunto y PDFs por participante; incorpora costes/pago cuando existen. |

Los nombres de salida se guardan por año como `final_order_excel`, `final_order_piece_pdf`, `final_order_user_pdf`; `final_order_generated_at` marca el cierre. La imagen alternativa PNG debe ser válida para fpdf2 (se encontro una corrupcion en V92). Las descargas comprueban nombres de archivo y carpetas autorizadas mediante `export_path_safety.safe_export_path`.

El archivo anual (`campaign_archive.archive_completed_campaign`) verifica campaña y fase, fecha de exportación, integridad ZIP interna del XLSX, cabecera, datos y totales **exactos** contra pedidos actuales. Prohibe hojas ajenas, formulas donde deberia haber números, referencias duplicadas, cambios de cantidades e enlaces simbolicos que apunten fuera de la carpeta. El archivo pasa a `archived` con log y **sin borrar pedidos históricos**. Un Excel modificado a mano no es una fuente de verdad.

## 13. Datos de pago y tareas internas
IBAN y fecha limite se guardan como ajustes anuales. La ruta de cambio de pago puede lanzar una regeneracion **en un hilo daemon**, por lo que una notificacion de lanzamiento no garantiza que los archivos nuevos esten escritos ni que un proceso sobrevivira a un reinicio. En la evolución futura, sustituir por una cola persistente o tarea explicita con estado, logs y reintentos idempotentes si la fiabilidad operativa lo requiere.

Impuestos y gastos de envio dependen de configuración del pedido, no de un cambio arbitrario del Excel generado. Una refactorizacion debe conservar las reglas del reparto y comparar el total final de los PDFs con la hoja Excel y los pedidos.

## 14. Importaciones: CSV, Excel y borradores
`_handle_users_csv_upload()` exige `username,password` y codificacion UTF-8; rechaza `is_admin` e importaciones que alteren derechos administrativos. Para usuarios previos conserva identidad y contraseña, crea o revisa participación anual. `_parse_products_excel()` reconoce `Material`, `Communication number` o `reference`, `Description` o `name`, y campos de precio/imagen/grupos. No des por hecho que todas las hojas de cualquier proveedor cumplen el contrato: crea un archivo de prueba con una cabecera conocida y prueba duplicados, valores vacios, precios no finitos y referencias ya comprometidas.

`draft_catalog_import.validate_draft_catalog_rows()` y `import_draft_catalog()` permiten preparar catálogo para un `Campaign` en `draft`; la operación es transaccional. Un borrador puede tener catálogo y participantes, pero **no debe tener pedidos, votos ni favoritas** antes de activar. Un nuevo año no se crea borrando los registros del anterior.

## 15. Backups, seguridad de archivos y recuperación
**Copia web:** `backups.create_phase_backup()` produce ZIP de fase y se invoca en puntos administrativos. La descarga de ultima copia o log usa rutas restringidas al administrador. **Restauración web:** `/admin/backup/restore` responde 409 deliberadamente: sustituir SQLite y documentos con Flask activo no es seguro.

**Copia offline:** `scripts/create_offline_backup.sh` detiene el servicio app, usa `create_offline_backup.py` y conserva `data/backups`. **Restauración offline:** `scripts/restore_offline.sh` detiene app, usa un contenedor Python sin red y `restore_offline.py` para verificar ZIP, manifiesto, edición, SQLite, fases y rutas; prepara un arbol nuevo, cambia directorios y conserva `data.pre-restore-*`. Las pruebas simulan fallos a mitad y exigen rollback. Para automatizaciones externas hay que detener el scheduler aparte.

Un archivo ZIP no es fiable solo porque se puede abrir. Rechaza nombres duplicados peligrosos, `../` (zip slip), rutas absolutas, archivos inesperados, symlinks y payloads malformados. Nunca uses `ZipFile.extractall` sobre un ZIP arbitrario sin controles. No subas backups reales ni PDFs firmados a un issue público.

## 16. Seguridad de aplicación y amenaza principal
| Riesgo | Defensa que debe mantenerse |
|---|---|
| Acceso a pedidos de terceros | `login_required`, `_ensure_admin`, `require_campaign_participant`, `campaign_id`. |
| Peticiones POST desde terceros | CSRFProtect y token oculto en formularios Jinja. |
| Fuerza bruta | Flask-Limiter en login y clave de acceso al sitio. |
| Permisos de usuarios entre años | `CampaignParticipation` con documento/estado de ese año, no bandera antigua de `User`. |
| Confusion de fases/clave global | `get_campaign_phase()`, `ANNUAL_KEYS` y preflight anual. |
| Contabilidad incorrecta | `Decimal`, `effective_commitment()`, materializacion y fingerprint de exportación. |
| Inyeccion de rutas de archivo | `safe_export_path`, basenames verificados, sin symlinks. |
| Proxy mal configurado | `TRUSTED_PROXY_COUNT` cero sin proxy; HTTPS externo confiable. |
| Filtracion de secretos | `.env` privado, `.gitignore`, secretos unicos y logs saneados. |
| Corrupcion por restauración | Restauración offline con app parada, validación y rollback. |

Los enlaces a imagenes externas requieren red y pueden fallar: el flujo de PDF tiene imagen local alternativa. Revisa dependencias con avisos de seguridad y fija versiones cuando haya un conjunto validado. Usar SQLite con varios workers o escritores externos requiere analizar `BEGIN IMMEDIATE`, timeout y bloqueos; no prometas compatibilidad con PostgreSQL solo porque se importe `libpq-dev` en Docker.

## 17. Subsistema exclusivo de Pública: aviso de pedido insuficiente
**Fuente:** `app/services/shortage.py`; modelos `ShortageWindow`, `ShortageAcknowledgement`; rutas `/admin/shortage`, `/shortage/acknowledge`, `/shortage/increase`. Extended no contiene este servicio ni estas tablas.

1. `order_total(campaign_id)` calcula el importe desde **Order**, nunca desde el total bruto de votos. `minimum_total()` lee el mínimo anual y su valor de configuración por defecto.
2. `open_window(actor_id, days)` solo admite campaña activa en `order`, total inferior al mínimo y una decision no existente. El plazo debe ser entero entre 1 y 30 días. Crea `ShortageWindow` abierto, con fecha limite y log.
3. `acknowledge(user_id)` exige participación aprobada y PDF firmado de esa campaña, aviso abierto y no vencido. Guarda `ShortageAcknowledgement`; repetirlo es idempotente.
4. `add_extra_order()` válida aviso aceptado, producto seleccionado, precio, escalones de cantidad, margen restante y compromiso no decreciente. Abre `BEGIN IMMEDIATE` en SQLite antes de leer-comprobar-escribir, para serializar peticiones concurrentes. Un cambio a PostgreSQL exige redisenar esta parte.
5. `reconcile(now)` resuelve `reached` cuando se alcanza el mínimo, incluso en el limite temporal; si no, al vencer resuelve `cancelled`. No hay un worker automático garantizado por la mera importacion del modulo.
6. `cancel(actor_id)` permite cancelacion administrativa controlada en fase `order`, con log y sin borrar el histórico.

**Modelo de estados:** `open -> reached` o `open -> cancelled`; la decision no se vuelve a abrir arbitrariamente. La comprobación temporal usa UTC de servidor. El scheduler externo, si existe, debe ejecutarse con las mismas garantías de datos y permisos. **Pruebas relevantes:** `test_v85_shortage.py`, `test_v86_shortage_increase.py`, `test_v92_campaign_e2e.py`, `test_iteration_46_public_only.py` y contratos de concurrencia V92.

### Ejemplo de regresion que debe existir
Dos participantes intentan ampliar a la vez y ambos cabrian por separado pero no juntos. Solo la suma permitida debe confirmarse; el segundo debe recibir rechazo o reintento coherente, sin superar presupuesto. Otra prueba debe demostrar que un plazo vencido no altera pedidos antiguos de una campaña archivada.

## 18. Frontend, traducciones y accesibilidad
La interfaz usa **Jinja2 + Bootstrap 5.3 CDN + CSS local** (`static/css/`) y JavaScript de apariencia (`static/js/valbrick-appearance.js`). `templates/base.html` define navegación, controles ES/EN, aspecto claro/oscuro, enlace a código y estructura de contenido. `templates/admin_dashboard.html` muestra formularios sensibles que dependen de la fase. No basta cambiar el texto de un boton: la ruta POST debe verificar **la misma condición** de seguridad.

Las traducciones base son `app/translations/es.json` y `en.json`. `app/i18n.py` escoge idioma desde sesión o cabecera, aplica fallback y permite overrides JSON en `/data/translations`. `app/main/translation_admin.py` restringe claves, tamanos e importaciones para que un admin no inyecte contenido arbitrario. Para agregar un mensaje visible: crea la clave en ambos archivos, referencia `{{ _('clave') }}` en Jinja y prueba idioma y fallback. No incrustes credenciales ni URLs privadas en las traducciones.

**Comprobacion visual manual:** pantalla pequena, teclado, navegación de menus, mensajes de error, tokens CSRF, tema claro/oscuro, PDFs sin foto y enlaces HTTPS. Las pruebas HTTP con regex del boton solo comprueban el HTML renderizado, no sustituyen revisar con un navegador.

## 19. Tests: pirámide y comandos de calidad
| Tipo | Ejemplos | Contrato |
|---|---|---|
| Puro (sin Flask) | `test_quantity_rules.py`, `test_commitment_ledger.py` | Cantidades exactas y calculos con Decimal. |
| ORM / SQLite | `test_order_materialization.py`, `test_campaign_write_guards.py` | FKs, triggers, aislamiento y rollback. |
| HTTP | `test_v93_release_http.py`, `test_v90_private_extension_http.py` si aplica | Sesión, CSRF/autoridad, fase y resultado real. |
| Seguridad | `test_backup_zip_safety.py`, `test_proxy_configuration.py` | ZIP hostil, acceso, proxy, rutas. |
| E2E | `test_v92_campaign_e2e.py` | Campaña ficticia desde fases hasta Excel/PDF/archivo. |
| Release | `test_v93_offline_restore.py`, `test_v93_release_security_contract.py` | Recuperación, rollback, despliegue sin root. |

- `run_v93_release_isolated.sh`: tests de recuperación offline y HTML/rutas de cierre.
- `run_v92_e2e_isolated.sh`: dos recorridos reales de campaña en base desechable.
- `run_full_tests_isolated.sh`: pytest integral; en la edición Extended incluye el modulo de invitaciones privadas.
- `.github/workflows/checks.yml`: acciones `push`/`pull_request` para instalar dependencias, compilar y lanzar pytest en GitHub.

**Linea base declarada para este código:** Pública V93-RC1 532 passed, 1 skipped, 167 subtests; Extended V93-RC2 517 passed, 1 skipped, 160 subtests. Una prueba omitida por edición es una comparación cruzada imposible desde el contenedor aislado. Advertencias de ZIP duplicado en una prueba hostil y `LegacyAPIWarning` de SQLAlchemy no son fallo pero deben revisarse como deuda.

### Ejemplo mínimo de prueba pura
Este caso usa una función pura ya existente y no toca ninguna base:

```python
from app.services.quantity_rules import validate_quantity

def test_quantities_step_and_threshold():
    assert validate_quantity(1.00, 25)[0] is True
    assert validate_quantity(1.00, 30)[0] is False
    assert validate_quantity(2.00, 10)[0] is True
    assert validate_quantity(2.00, 25)[0] is False
```

Ejecuta **solo en entorno de pruebas** `python -m pytest -q tests/test_quantity_rules.py` si pytest esta disponible, o usa Docker. Para integraciones HTTP, reutiliza el fixture `tests/_v92_campaign_fixture.py` que crea directorios temporales, participantes y campañas ficticias. Cada caso debe revisar la base al final, no solo los codigos de redireccion.

## 20. Cómo agregar una funcionalidad sin romper dinero ni historia
**Ejemplo guiado: mostrar en admin el importe seleccionado de una campaña.**
1. Define el requisito y aclara si el dato es "votos" o "pedidos"; después de `order`, el importe efectivo procede de `Order`.
2. Escribe primero una prueba de `build_final_order_context()` con 2 usuarios, dos referencias y un producto descartado; comprueba que no hay doble conteo.
3. Reutiliza un servicio existente o crea un helper puro de cálculo. No hagas consultas de todos los años ni uses claves de configuración globales.
4. Añade el campo de contexto a `/admin` detras de `_ensure_admin`; no agregues una ruta GET que modifique DB.
5. Muestra un elemento Jinja con clave traducida en `es.json` y `en.json`; no dupliques reglas en JavaScript.
6. Ejecuta test puro, HTTP, E2E y suite completa en Docker desechable.
7. Compara dos campañas distintas y un usuario no aprobado. Revisa que archivos de Pública/Extended no se hayan mezclado.
8. Documenta el cambio, ensaya el despliegue con backup y pública un commit revisable.

**Ejemplo de cambio peligroso:** agregar una columna anual en `CampaignParticipation` y hacer `db.create_all()` esperando que aparezca en una base antigua. Eso **no migra columnas existentes**: necesita plan de esquema, compatibilidad y ensayo de rollback. Emplea scripts de mantenimiento existentes como referencia, no como permiso para ejecutar ALTER TABLE sobre producción sin copia.

## 21. Migraciones de SQLite y operaciones atómicas
Antes de modificar el esquema: exporta la lista de tablas/indices/triggers, copia la BD, identifica claves foraneas y tablas históricas, prepara migración de avance y restauración, ensaya en una copia anonima. Evita `drop_all()`, truncados y borrados de cuentas que tengan pedidos. Las tablas de archivo y las referencias históricas tienen restricciones especiales.

**Transacciones SQLAlchemy:** `db.session.add()` prepara una fila, `flush()` la envia a la transacción sin confirmar, `commit()` confirma, `rollback()` revierte y `session.remove()` libera el contexto. `Config.set()` confirma por defecto, por lo que no debe llamarse desde una operación atómica compuesta salvo que el helper admita `commit=False` o se emplee un objeto dentro de la misma session. Verifica el comportamiento concreto antes de refactorizar.

**Concurrencia SQLite:** no extrapoles razonamientos de una sola petición a dos usuarios simultaneos. Los servicios de aumento público y de voto usan una estrategia de reserva de escritura para serializar comprobación de presupuesto y mutacion. Una ruta que lee el total, tarda y luego escribe sin lock permite superar el presupuesto. Prueba dos peticiones concurrentes con almacenamiento real SQLite; mocks solos no sirven.

## 22. Diagnostico orientado a síntomas
| Sintoma | Hipotesis y primeras comprobaciones |
|---|---|
| `Not an annual setting` | Falta clave en `ANNUAL_KEYS` de esta edición; comprobar nombres por año y añadir regresion. |
| Redirect pero nada cambia | El endpoint puede haber mostrado un `flash` de error; inspecciona fase, permiso, datos y DB. |
| Error de PDF / `final_order_generated_at` nulo | Revisar logs de fpdf2, PNG fallback, fotos remotas y permisos de `ORDER_EXPORT_FOLDER`. |
| Excel tiene menos unidades que votos seleccionados | Falta materializacion/sync; compara `Order` con `UserVote` por usuario/referencia. |
| Excel editado no permite archivar | Verifica hoja `Pedido`, cabecera, tipos, duplicados y coincidencia con pedidos actuales. |
| Fase del siguiente año incorrecta | Revisar `phase_campaign_<id>` y que no se usa `Config.get('phase')` con varias campañas. |
| `403` al votar | Revisar usuario activo, aprobación anual y documento firmado, no solo `User.declaration_validated`. |
| `409` al restaurar por web | Comportamiento previsto; usa el script offline con servicio parado. |
| `sqlite3.OperationalError: database is locked` | Revisar escritor externo, timeout, transacciones largas y `BEGIN IMMEDIATE`. |
| Imposible escribir `/data` | UID/GID 10001, permisos del bind mount y espacio de disco. |
| No mantiene login tras HTTPS | Cookie Secure y `TRUSTED_PROXY_COUNT`; revisar que el proxy limpia `X-Forwarded-*`. |
| GitHub Actions falla y Docker no | Comparar variables, versiones resueltas y el comando CI sin volúmenes; no ocultar el error. |

## 23. Operación, monitoreo y plan de mejora
En producción el Dockerfile crea entorno Python, instala dependencias, cambia a UID/GID 10001, usa `gunicorn --workers 1` y expone 5001 solo internamente; Compose pública `127.0.0.1:${PORT:-5001}:5001`, monta `./data:/data`, healthcheck TCP y `restart: unless-stopped`. El proxy HTTPS se configura **fuera de ese contenedor**; `Caddyfile.example` apunta al host local.

Tareas aconsejadas para mantenimiento: alertas de certificado, espacio y backups; pruebas periodicas de restauración; capturas de indicadores `flask capture-insights` mediante scheduler externo si se desea; auditorias de integridad/ready antes de una campaña; escaneo de dependencias y version-lock reproducible; seguimiento de `LegacyAPIWarning` de SQLAlchemy. La UI de restauración no sustituye al runbook offline.

**Deuda conocida:** dependencias con rangos, sin lock completo; algunos comentarios heredados de migración; mezcla histórica `UserVote`/`Order` hasta consolidar un ledger único; generación de documentos a traves de hilos daemon en determinados flujos; soporte SQLite sin orquestador externo de jobs; validación real de accesibilidad y restauración en el host de producción pendiente. Prioriza seguridad de cantidades y datos antes de mejorar aspecto visual.

## 24. Itinerario didáctico de evolución (12 tareas)
| Nivel | Trabajo práctico | Como sabes que esta bien |
|---|---|---|
| 1 | Dibujar el flujo de `/vote` hasta SQLAlchemy. | Identificas ruta, servicio, modelo, commit, permisos y test. |
| 1 | Añadir una clave traducida a una plantilla. | Existe en ES/EN y el fallback no muestra la clave literal. |
| 1 | Crear un test puro de `validate_quantity()`. | Pasa en Python 3.11 y detecta un valor invalido. |
| 2 | Escribir tabla de fases y POSTs administrativos. | No hay `order` antes de `final`, y no se genera Excel prematuro. |
| 2 | Probar un compromiso en voto y pedido a la vez. | No se duplica importe por producto. |
| 2 | Incluir un producto descartado en fixture. | No llega a `Order` ni exportación, conserva su voto. |
| 3 | Hacer un cambio seguro en un servicio anual. | Prueba dos años y no introduce clave global. |
| 3 | Probar un archivo XLSX malicioso o modificado. | Rechazado sin cambiar `Campaign.status`. |
| 3 | Ejecutar ensayo de backup y rollback ficticio. | Datos anteriores conservados tras fallo. |
| 4 | Planificar una migración de campo anual. | Define upgrade, preflight, copias, reversibilidad y pruebas. |
| 4 | Ensayar dos peticiones simultaneas de presupuesto. | Nunca supera el limite ni deja escrituras parciales. |
| 4 | Ensayar GitHub -> proxy HTTPS -> Docker aislado. | Suite verde, sesiones seguras, logs limpios y copia externa. |

**Criterio de autonomia:** quien herede el proyecto debe poder localizar un error, reproducirlo con una prueba, explicar el modelo y fase implicados, hacer una correccion mínima, validar las dos ediciones *por separado* y revertir un despliegue sin perder datos.

## 25. Anexo: diccionario exhaustivo de tablas ORM

Este inventario procede de `app/models.py`, no de una reconstruccion del esquema SQLite en producción. Las columnas, claves ajenas y restricciones se listan con su declaración de código. Revisa también `__table_args__`, los indices y los triggers del instalador al planificar una migración.

### `User` - `user`

Identidad de cuenta, hash de clave, datos personales y privilegios; una cuenta no equivale a permiso anual.

Archivo: `app/models.py:8`. Campos: **15**.

| Campo | Definicion en el ORM |
|---|---|
| `id` | `db.Column(db.Integer, primary_key=True)` |
| `username` | `db.Column(db.String(50), unique=True, nullable=False)` |
| `password_hash` | `db.Column(db.String(128), nullable=False)` |
| `first_name` | `db.Column(db.String(50))` |
| `last_name` | `db.Column(db.String(50))` |
| `dni` | `db.Column(db.String(15))` |
| `age` | `db.Column(db.Integer)` |
| `agreements_accepted` | `db.Column(db.Boolean, default=False)` |
| `active` | `db.Column(db.Boolean, default=True)` |
| `is_admin` | `db.Column(db.Boolean, default=False)` |
| `declaration` | `db.Column(db.String(255))` |
| `paid` | `db.Column(db.Boolean, default=False)` |
| `must_change_password` | `db.Column(db.Boolean, default=True)` |
| `declaration_file` | `db.Column(db.String(255))` |
| `declaration_validated` | `db.Column(db.Boolean, default=False)` |

**Relaciones:** `orders`, `votes`, `favorites`, `action_logs`.

### `Product` - `product`

Catálogo anual, precio, color, selección final y bloqueo.

Archivo: `app/models.py:37`. Campos: **17**.

| Campo | Definicion en el ORM |
|---|---|
| `id` | `db.Column(db.Integer, primary_key=True)` |
| `campaign_id` | `db.Column(db.Integer, db.ForeignKey('campaign.id'), index=True, nullable=True)` |
| `image_url` | `db.Column(db.String(255))` |
| `reference` | `db.Column(db.String(100), nullable=False)` |
| `name` | `db.Column(db.String(255))` |
| `price` | `db.Column(db.Float, nullable=True)` |
| `is_locked` | `db.Column(db.Boolean, default=False)` |
| `colour_id` | `db.Column(db.String(50))` |
| `color_bl` | `db.Column(db.String(255))` |
| `present_in_2024` | `db.Column(db.Boolean, default=False)` |
| `main_group_top` | `db.Column(db.String(100))` |
| `main_group` | `db.Column(db.String(100))` |
| `main_group_sub` | `db.Column(db.String(100))` |
| `present_in_2025` | `db.Column(db.Boolean, default=True)` |
| `final_selected` | `db.Column(db.Boolean, default=False)` |
| `final_disabled` | `db.Column(db.Boolean, default=False)` |
| `final_promoted` | `db.Column(db.Boolean, default=False)` |

**Relaciones:** `orders`, `votes`, `favorites`.

### `Order` - `order`

Cantidad efectiva de cada usuario por producto y campaña; base del pedido exportado.

Archivo: `app/models.py:62`. Campos: **6**.

| Campo | Definicion en el ORM |
|---|---|
| `id` | `db.Column(db.Integer, primary_key=True)` |
| `campaign_id` | `db.Column(db.Integer, db.ForeignKey('campaign.id'), index=True, nullable=True)` |
| `user_id` | `db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)` |
| `product_id` | `db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)` |
| `quantity` | `db.Column(db.Integer, nullable=False)` |
| `timestamp` | `db.Column(db.DateTime, default=datetime.utcnow)` |

**Relaciones:** `user`, `product`.

### `ActionLog` - `action_log`

Acciones auditables realizadas por usuarios y administradores.

Archivo: `app/models.py:75`. Campos: **5**.

| Campo | Definicion en el ORM |
|---|---|
| `id` | `db.Column(db.Integer, primary_key=True)` |
| `user_id` | `db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)` |
| `action` | `db.Column(db.String(40), nullable=False)` |
| `detail` | `db.Column(db.String(255))` |
| `created_at` | `db.Column(db.DateTime, default=datetime.utcnow, nullable=False)` |

**Relaciones:** `user`.

### `ColorMap` - `color_map`

Correspondencias de nombres entre colores LEGO y BrickLink.

Archivo: `app/models.py:85`. Campos: **3**.

| Campo | Definicion en el ORM |
|---|---|
| `id` | `db.Column(db.Integer, primary_key=True)` |
| `lego_name` | `db.Column(db.String(100), unique=True, nullable=False)` |
| `bl_name` | `db.Column(db.String(100))` |

### `UserVote` - `user_vote`

Compromiso de unidades expresado durante las fases de votacion.

Archivo: `app/models.py:92`. Campos: **7**.

| Campo | Definicion en el ORM |
|---|---|
| `id` | `db.Column(db.Integer, primary_key=True)` |
| `campaign_id` | `db.Column(db.Integer, db.ForeignKey('campaign.id'), index=True, nullable=True)` |
| `user_id` | `db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)` |
| `product_id` | `db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)` |
| `quantity` | `db.Column(db.Integer, nullable=False)` |
| `initial_quantity` | `db.Column(db.Integer, nullable=True)` |
| `phase` | `db.Column(db.String(20), default='first')` |

**Relaciones:** `user`, `product`.

**Restricciones de tabla:** `(db.UniqueConstraint('user_id', 'product_id', name='uq_user_vote_product'),)`.

### `UserFavorite` - `user_favorite`

Marcador personal por campaña y referencia; no crea pedido.

Archivo: `app/models.py:109`. Campos: **5**.

| Campo | Definicion en el ORM |
|---|---|
| `id` | `db.Column(db.Integer, primary_key=True)` |
| `campaign_id` | `db.Column(db.Integer, db.ForeignKey('campaign.id'), index=True, nullable=True)` |
| `user_id` | `db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)` |
| `product_id` | `db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)` |
| `created_at` | `db.Column(db.DateTime, default=datetime.utcnow)` |

**Relaciones:** `user`, `product`.

**Restricciones de tabla:** `(db.UniqueConstraint('user_id', 'product_id', name='uq_user_favorite_product'),)`.

### `Config` - `config`

Almacen clave/valor; algunas claves requieren prefijo anual.

Archivo: `app/models.py:124`. Campos: **3**.

| Campo | Definicion en el ORM |
|---|---|
| `id` | `db.Column(db.Integer, primary_key=True)` |
| `key` | `db.Column(db.String(50), unique=True, nullable=False)` |
| `value` | `db.Column(db.String(255), nullable=True)` |

### `CampaignParticipation` - `campaign_participation`

Inscripcion, estado de aprobación y PDF firmado para una campaña concreta.

Archivo: `app/models.py:151`. Campos: **8**.

| Campo | Definicion en el ORM |
|---|---|
| `id` | `db.Column(db.Integer, primary_key=True)` |
| `campaign_id` | `db.Column(db.Integer, db.ForeignKey('campaign.id'), nullable=False, index=True)` |
| `user_id` | `db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)` |
| `status` | `db.Column(db.String(20), nullable=False, default='pending_commitment')` |
| `signed_document` | `db.Column(db.String(255), nullable=True)` |
| `document_approved_at` | `db.Column(db.DateTime, nullable=True)` |
| `document_approved_by` | `db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)` |
| `enrolled_at` | `db.Column(db.DateTime, nullable=False, default=datetime.utcnow)` |

**Relaciones:** `user`, `campaign`.

**Restricciones de tabla:** `(db.UniqueConstraint('campaign_id', 'user_id', name='uq_campaign_participation_user'),)`.

### `Campaign` - `campaign`

Registro de ediciones anuales con estado y fecha de archivo.

Archivo: `app/models.py:178`. Campos: **6**.

| Campo | Definicion en el ORM |
|---|---|
| `id` | `db.Column(db.Integer, primary_key=True)` |
| `year` | `db.Column(db.Integer, unique=True, nullable=False)` |
| `title` | `db.Column(db.String(120), nullable=False)` |
| `status` | `db.Column(db.String(20), nullable=False, default='legacy_active')` |
| `created_at` | `db.Column(db.DateTime, default=datetime.utcnow, nullable=False)` |
| `archived_at` | `db.Column(db.DateTime, nullable=True)` |

### `CampaignInsightSnapshot` - `campaign_insight_snapshot`

Serie temporal agregada por campaña, no fuente de cantidades facturables.

Archivo: `app/models.py:222`. Campos: **9**.

| Campo | Definicion en el ORM |
|---|---|
| `id` | `db.Column(db.Integer, primary_key=True)` |
| `campaign_id` | `db.Column(db.Integer, db.ForeignKey('campaign.id'), nullable=False, index=True)` |
| `recorded_at` | `db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)` |
| `vote_cents` | `db.Column(db.Integer, nullable=False)` |
| `order_cents` | `db.Column(db.Integer, nullable=False)` |
| `vote_units` | `db.Column(db.Integer, nullable=False)` |
| `order_units` | `db.Column(db.Integer, nullable=False)` |
| `voters` | `db.Column(db.Integer, nullable=False)` |
| `buyers` | `db.Column(db.Integer, nullable=False)` |

### `ShortageWindow` - `shortage_window`

Ventana extraordinaria de insuficiencia y estado/fecha de cierre; solo Pública.

Archivo: `app/models.py:239`. Campos: **8**.

| Campo | Definicion en el ORM |
|---|---|
| `id` | `db.Column(db.Integer, primary_key=True)` |
| `campaign_id` | `db.Column(db.Integer, db.ForeignKey('campaign.id'), nullable=False, unique=True, index=True)` |
| `status` | `db.Column(db.String(24), nullable=False)` |
| `opened_at` | `db.Column(db.DateTime, nullable=False, default=datetime.utcnow)` |
| `deadline_at` | `db.Column(db.DateTime, nullable=True)` |
| `resolved_at` | `db.Column(db.DateTime, nullable=True)` |
| `opened_by` | `db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)` |
| `closing_reason` | `db.Column(db.String(120), nullable=True)` |

### `ShortageAcknowledgement` - `shortage_acknowledgement`

Aceptacion individual y fechada del aviso de falta de mínimo; solo Pública.

Archivo: `app/models.py:252`. Campos: **4**.

| Campo | Definicion en el ORM |
|---|---|
| `id` | `db.Column(db.Integer, primary_key=True)` |
| `window_id` | `db.Column(db.Integer, db.ForeignKey('shortage_window.id'), nullable=False, index=True)` |
| `user_id` | `db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)` |
| `accepted_at` | `db.Column(db.DateTime, nullable=False, default=datetime.utcnow)` |

**Restricciones de tabla:** `(db.UniqueConstraint('window_id', 'user_id', name='uq_shortage_ack_window_user'),)`.

## 26. Anexo: mapa completo de rutas HTTP

Inventario extraido de los decoradores de rutas: **no es una API REST pública garantizada**. Una ruta `POST` requiere la sesión/autorización correcta, token CSRF y fase compatible. El prefijo de las blueprints `orders` y `products` se aplica al formar la URL final. Las rutas marcadas `GET / POST` muestran formularios y procesan sus datos. Para cada cambio revisa tanto la vista como el test asociado.

### `app/main/routes.py` (55 rutas)

| Metodo | Ruta real | Funcion | Finalidad |
|---|---|---|---|
| `GET` | `/` | `index` | Pagina inicial y redireccion al flujo permitido |
| `GET` | `/language/<string:lang>` | `set_language` | Idioma de interfaz |
| `GET` | `/dashboard` | `user_dashboard` | Panel de participante y compromisos |
| `POST` | `/vote` | `submit_vote` | Registrar o ampliar compromiso de voto |
| `POST` | `/favorite` | `toggle_favorite` | Marcar/desmarcar favorito |
| `POST` | `/vote/delete` | `delete_vote` | Retirada controlada según fase |
| `GET` | `/dashboard/order-pdf` | `download_user_order_pdf` | Descargar el PDF del propio pedido |
| `POST` | `/admin/campaign-archive` | `campaign_archive` | Archivar pedido final comprobado |
| `POST` | `/admin/campaign-draft` | `campaign_draft` | Crear borrador para nueva campaña |
| `POST` | `/admin/campaign-activate` | `campaign_activate` | Activar borrador si autorización/readiness |
| `GET` | `/admin/campaign-readiness` | `campaign_readiness` | Consultar diagnóstico de preparación anual |
| `GET` | `/admin/campaign-history` | `campaign_history` | Histórico de campañas anteriores |
| `GET` | `/admin/simulator` | `demo_simulator` | Simulador administrativo |
| `GET` | `/insights` | `order_insights` | Estadisticas de la campaña |
| `GET` | `/admin` | `admin_dashboard` | Panel de administración |
| `POST` | `/admin/products/toggle-lock` | `toggle_lock` | Bloquear/desbloquear referencia |
| `POST` | `/admin/products/toggle-final` | `toggle_final_status` | Modificar selección final |
| `POST` | `/admin/products/promote-all` | `promote_all_products` | Promocion masiva a la selección |
| `POST` | `/admin/users/toggle-access` | `toggle_user_active` | Cambiar acceso de la cuenta |
| `POST` | `/admin/users/toggle-admin` | `toggle_user_admin` | Cambiar rol administrativo |
| `POST` | `/admin/users/validate-declaration` | `validate_declaration` | Aprobar documento firmado |
| `POST` | `/admin/users/delete-declaration` | `delete_declaration` | Eliminar documento pendiente |
| `POST` | `/admin/users/invalidate-declaration` | `invalidate_declaration` | Revocar aprobación documental |
| `POST` | `/admin/users/reset-password` | `reset_user_password` | Reiniciar contraseña |
| `GET` | `/admin/users/declaration/<int:user_id>` | `download_declaration` | Descargar documento firmado |
| `POST` | `/admin/phase/activate-second` | `activate_phase2` | Iniciar segunda votacion |
| `POST` | `/admin/phase/advance-final` | `advance_phase` | Entrar en selección final |
| `POST` | `/admin/phase/advance-order` | `advance_order_phase` | Liberar pedido efectivo |
| `POST` | `/admin/clean-data` | `clean_data` | Consultar código fuente |
| `POST` | `/admin/test-mode` | `toggle_test_mode` | Consultar código fuente |
| `POST` | `/admin/backup/create` | `create_backup_endpoint` | Crear ZIP de copia |
| `GET` | `/admin/backup/download` | `download_backup` | Descargar ultima copia |
| `GET` | `/admin/backup/error-log` | `download_backup_log` | Descargar registro de copia |
| `POST` | `/admin/backup/restore` | `restore_backup_endpoint` | Restauración web bloqueada: 409 |
| `POST` | `/admin/order/costs` | `update_order_costs` | Impuestos y transporte de la campaña |
| `POST` | `/admin/order/generate` | `generate_order_exports_route` | Generar Excel y PDFs definitivos |
| `POST` | `/admin/order/regenerate` | `regenerate_order_exports_route` | Recrear archivos bajo reglas de fase |
| `POST` | `/admin/order/payment-details` | `update_order_payment_details` | Datos de pago e instrucciones |
| `GET` | `/admin/order/download/<string:kind>` | `download_order_file` | Descargar exportación protegida |
| `POST` | `/admin/orders/update` | `admin_update_order` | Ajustar cantidades de pedidos |
| `POST` | `/admin/orders/add` | `admin_add_order` | Agregar pedidos por administrador |
| `POST` | `/admin/colors/update` | `update_color_map` | Consultar código fuente |
| `GET / POST` | `/admin/upload-data` | `upload_data` | Importar catálogo anual |
| `GET / POST` | `/admin/upload-users` | `upload_users` | Importar usuarios |
| `GET / POST` | `/admin/campaign-draft/<int:campaign_id>/participants` | `draft_participants` | Preparar inscripciones en borrador |
| `GET / POST` | `/admin/campaign-draft/<int:campaign_id>/catalog` | `draft_catalog` | Preparar catálogo del siguiente año |
| `GET / POST` | `/admin/set-dates` | `set_dates` | Configurar hitos temporales |
| `GET / POST` | `/admin/commitment` | `commitment_management` | Gestionar compromiso documental |
| `GET` | `/admin/audit` | `audit_dashboard` | Consultar auditoria administrativa |
| `GET / POST` | `/admin/settings/limits` | `manage_limits` | Editar límites por campaña |
| `GET` | `/admin/campaigns` | `campaign_registry` | Consultar registro de campañas |
| `GET / POST` | `/admin/campaigns/<int:campaign_id>/calendar` | `manage_campaign_calendar` | Configurar ventanas del calendario |
| `GET / POST` | `/admin/shortage` | `shortage_admin` | Gestionar ventana de pedido insuficiente |
| `POST` | `/shortage/acknowledge` | `shortage_acknowledge` | Aceptar aviso de insuficiencia |
| `GET / POST` | `/shortage/increase` | `shortage_increase` | Incremento extraordinario voluntario |

### `app/main/translation_admin.py` (5 rutas)

| Metodo | Ruta real | Funcion | Finalidad |
|---|---|---|---|
| `GET` | `/admin/translations` | `index` | Pagina inicial y redireccion al flujo permitido |
| `POST` | `/admin/translations/save` | `save` | Guardar traducciones |
| `POST` | `/admin/translations/reset` | `reset` | Restablecer traducciones |
| `GET` | `/admin/translations/export/<language>` | `export` | Exportar idiomas |
| `POST` | `/admin/translations/import` | `import_file` | Importar idiomas |

### `app/auth/routes.py` (8 rutas)

| Metodo | Ruta real | Funcion | Finalidad |
|---|---|---|---|
| `GET / POST` | `/login` | `login` | Inicio de sesión |
| `GET / POST` | `/access` | `site_access` | Contraseña de acceso al sitio si configurada |
| `GET` | `/logout` | `logout` | Cerrar sesión |
| `GET / POST` | `/change-password` | `change_password` | Cambio de contraseña |
| `GET / POST` | `/profile` | `profile` | Ver/cambiar perfil propio |
| `GET / POST` | `/upload-declaration` | `upload_declaration` | Subir PDF firmado anual |
| `GET` | `/declaration-pending` | `declaration_pending` | Consultar aprobación documental |
| `GET` | `/commitment/download` | `download_commitment` | Descargar documento a firmar |

### `orders/routes.py` (2 rutas)

| Metodo | Ruta real | Funcion | Finalidad |
|---|---|---|---|
| `GET` | `/orders/` | `list_orders` | Listar pedidos |
| `GET / POST` | `/orders/create` | `create_order` | Alta de pedido según estado |

### `products/routes.py` (2 rutas)

| Metodo | Ruta real | Funcion | Finalidad |
|---|---|---|---|
| `GET` | `/products/` | `list_products` | Listar catálogo visible |
| `GET` | `/products/<int:product_id>` | `product_detail` | Detalle de referencia |

## 27. Anexo: índice detallado de servicios y funciones

Las funciones siguientes aparecen en `app/services`. Se incluyen los auxiliares privados con prefijo `_` porque explican el funcionamiento; **no los llames desde nuevas rutas sin revisar sus condiciones previas**. Una firma no constituye contrato estable. Para localizar pruebas busca la función o el modulo en `tests/` y verifica el flujo completo.

### `active_campaign.py` (61 líneas)

Campaña y autorización anual actuales

- `current_campaign()` - `app/services/active_campaign.py:10` - Resolve the one legacy-active campaign while excluding archived/draft years.  A draft year is never operational. Do not permit a second active campaign; activation is intentionally blocked p
- `current_membership()` - `app/services/active_campaign.py:29`
- `allowed_to_participate()` - `app/services/active_campaign.py:36`
- `require_campaign_participant()` - `app/services/active_campaign.py:44` - Reject edits to an account outside the registered campaign.  This guard must be called at the mutation boundary, including administrative edits, not just when a participant opens a page. It

### `activity_log.py` (32 líneas)

Registro auditable de mutaciones

- `log_user_action()` - `app/services/activity_log.py:22`

### `annual_readiness.py` (139 líneas)

Diagnostico antes de migración/activacion

- `inspect_annual_readiness()` - `app/services/annual_readiness.py:13` - Return diagnostic findings without modifying the session or database.

### `backups.py` (215 líneas)

Copias de seguridad; no activar la restauración web

- `_db_path()` - `app/services/backups.py:32`
- `_copy_sqlite()` - `app/services/backups.py:43`
- `_copy_optional_folder()` - `app/services/backups.py:52`
- `_zip_directory()` - `app/services/backups.py:63`
- `_safe_extract()` - `app/services/backups.py:72` - Unpack a trusted-format backup defensively.  Reject zip-slip paths, symlinks, duplicate names, excessive file counts, and oversized decompressed archives before touching the destination. A b
- `create_phase_backup()` - `app/services/backups.py:113` - Create a ZIP with DB + user files and record it on disk.
- `restore_backup()` - `app/services/backups.py:162` - Restore DB and files from a ZIP; force phase to manifest target.
- `write_backup_error_log()` - `app/services/backups.py:205` - Persist an error log and return its path.

### `campaign_activation.py` (88 líneas)

Activacion de borrador preparado

- `activate_prepared_draft()` - `app/services/campaign_activation.py:13` - Promote a prepared draft without copying historical records.  This is a deliberately opt-in release gate. An administrator must enable it only after validating all application routes and Doc

### `campaign_archive.py` (164 líneas)

Validación del Excel y archivo anual

- `valid_final_workbook()` - `app/services/campaign_archive.py:20` - Require a readable XLSX workbook, not just a non-empty renamed file.
- `_finite_decimal()` - `app/services/campaign_archive.py:37` - Reject booleans, Excel formulas, non-numeric and non-finite values.
- `final_workbook_matches_order()` - `app/services/campaign_archive.py:47` - Compare the final XLSX against current campaign's authoritative order.  Reject duplicate/missing/foreign references, edited quantities/prices and totals. Excel formulas are not accepted as n
- `archive_completed_campaign()` - `app/services/campaign_archive.py:110` - Fail closed unless a finished order and its XLSX are present.  This transition is atomic with its audit record, and is idempotently rejected on repeat. Existing orders/votes are never delete

### `campaign_calendar.py` (95 líneas)

Fechas y ausencia de solapamientos

- `validate_campaign_window()` - `app/services/campaign_calendar.py:13` - Validate a campaign's configured season without imposing fixed days.  A season starts in its named year and finishes in the following year. The October-March convention is informative, not a
- `assert_no_window_overlap()` - `app/services/campaign_calendar.py:28` - Reject any shared calendar day across different annual campaigns.  Windows are inclusive: a campaign ending on a date cannot share that date with the next campaign. Missing historical dates
- `other_campaign_windows()` - `app/services/campaign_calendar.py:40` - Load configured windows of other years; reject incomplete history.
- `campaign_window_key()` - `app/services/campaign_calendar.py:51`
- `read_campaign_window()` - `app/services/campaign_calendar.py:59` - Read dates for any campaign, including archived history; never global keys.
- `configure_campaign_window()` - `app/services/campaign_calendar.py:75` - Store both dates in the same transaction; no schema migration required.  Existing archived campaigns may be inspected, but their dates are immutable.

### `campaign_data.py` (44 líneas)

Filtros de consultas al año activo

- `active_campaign_id()` - `app/services/campaign_data.py:13` - Use the same fail-closed campaign policy as access controls.
- `products_query()` - `app/services/campaign_data.py:24`
- `orders_query()` - `app/services/campaign_data.py:28`
- `votes_query()` - `app/services/campaign_data.py:32`
- `favorites_query()` - `app/services/campaign_data.py:36`
- `validate_product_campaign()` - `app/services/campaign_data.py:40` - Prevent a foreign or unmigrated product from entering an annual order.

### `campaign_participation.py` (87 líneas)

Inscripcion, PDF firmado y aprobación

- `participation_for()` - `app/services/campaign_participation.py:16` - Look up membership using *both* the campaign and user id.
- `enroll_existing_user()` - `app/services/campaign_participation.py:23` - Enrol an existing user; never inherit last year's approval.  Does not activate a campaign or grant access to legacy endpoints. Caller must commit its transaction. Unique constraint prevents
- `_require_active_membership_campaign()` - `app/services/campaign_participation.py:52` - Reject stale participation records before changing their approval state.
- `submit_signed_document()` - `app/services/campaign_participation.py:59` - New upload invalidates any prior approval; file validation is caller's job.
- `review_signed_document()` - `app/services/campaign_participation.py:72` - Approval requires an admin and an uploaded document.
- `is_eligible()` - `app/services/campaign_participation.py:84` - Never authorise based on a previous year's membership.

### `campaign_phase.py` (41 líneas)

Maquina de estados de campaña

- `phase_config_key()` - `app/services/campaign_phase.py:6`
- `get_campaign_phase()` - `app/services/campaign_phase.py:15`
- `set_campaign_phase()` - `app/services/campaign_phase.py:34`

### `campaign_registry.py` (76 líneas)

Registro y borradores anuales

- `list_campaigns()` - `app/services/campaign_registry.py:14` - Return registered campaigns without modifying operational records.
- `register_current_campaign()` - `app/services/campaign_registry.py:19` - Record the current legacy dataset; no reset, archival or activation.  A second legacy campaign is refused because the pre-migration database cannot distinguish data from different years.
- `create_next_campaign_draft()` - `app/services/campaign_registry.py:45` - Register a future year without activating it or copying historical data.  The only permitted situation is a fully archived previous campaign and no existing draft. This does not authorize im

### `campaign_settings.py` (46 líneas)

Configuración con namespace anual

- `annual_key()` - `app/services/campaign_settings.py:21`
- `get_annual_setting()` - `app/services/campaign_settings.py:29`
- `set_annual_setting()` - `app/services/campaign_settings.py:42`

### `commitment_ledger.py` (119 líneas)

Contabilidad de compromisos sin doble sumar

- `committed_total()` - `app/services/commitment_ledger.py:15` - Return conservative monetary commitment from (product_id, price, quantity).  Quantities within *one* source for a product are summed; sources are then combined using the maximum for that pro
- `effective_commitment()` - `app/services/commitment_ledger.py:59` - Calculate the active monetary commitment for a specific campaign phase.  ``order_lines`` and ``vote_lines`` contain (product_id, price, quantity). During voting all votes are binding. From t
- `materialized_order_quantity()` - `app/services/commitment_ledger.py:96` - Amount to persist for an additive order operation after the cutoff.  The first actual order must include any selected voting commitment not already represented by stored Order rows. This pre

### `declarations.py` (49 líneas)

Archivos privados y motivos de rechazo

- `_issue_key()` - `app/services/declarations.py:13`
- `get_declaration_issue()` - `app/services/declarations.py:17` - Return the persistent warning shown to a user when their DJ was rejected.
- `set_declaration_issue()` - `app/services/declarations.py:22` - Store a warning message so the user knows their previous DJ was invalid.
- `clear_declaration_issue()` - `app/services/declarations.py:27` - Remove any stored warning for the given user.
- `remove_declaration_file()` - `app/services/declarations.py:32` - Delete the stored DJ file from disk and reset the DB fields.

### `draft_activation_preflight.py` (30 líneas)

Condiciones de seguridad del siguiente año

- `evaluate_draft_activation()` - `app/services/draft_activation_preflight.py:8` - Return actionable blockers for a draft; inputs are read-only snapshots.

### `draft_catalog_import.py` (100 líneas)

Catalogos de borradores y validaciones

- `validate_draft_catalog_rows()` - `app/services/draft_catalog_import.py:14` - Reject malformed Excel payloads before any database write.
- `import_draft_catalog()` - `app/services/draft_catalog_import.py:54` - Upsert by (campaign, reference), never copy or modify archived products.  Validate the entire file before making any writes. Caller must hold admin access.

### `export_path_safety.py` (20 líneas)

Rutas seguras a documentos exportados

- `safe_export_path()` - `app/services/export_path_safety.py:5`

### `final_selection.py` (476 líneas)

Ranking, selección y simulación neutral

- `get_vote_aggregates()` - `app/services/final_selection.py:35` - Return aggregate vote information per product.
- `compute_final_selection()` - `app/services/final_selection.py:65` - Evaluate (and optionally persist) the final selection respecting the given cap.  When ``persist`` is False no database writes are performed, making it safe to call from read-only contexts su
- `get_final_selection_snapshot()` - `app/services/final_selection.py:78` - Helper to obtain the current selection summary without writing to the DB.
- `get_neutral_ranking()` - `app/services/final_selection.py:83` - Return the neutral ranking list for admin review.
- `get_phase_two_selection_snapshot()` - `app/services/final_selection.py:177` - Return the ranked phase 2 selection without writing to the DB.
- `_build_neutral_row()` - `app/services/final_selection.py:182`
- `_build_neutral_scores()` - `app/services/final_selection.py:197`
- `_determine_final_selection()` - `app/services/final_selection.py:242`
- `_persist_final_selection()` - `app/services/final_selection.py:277` - Apply the computed selection to the database.
- `_fetch_promoted_ids()` - `app/services/final_selection.py:290`
- `_fetch_locked_ids()` - `app/services/final_selection.py:300`
- `_fetch_disabled_ids()` - `app/services/final_selection.py:309`
- `_fetch_voted_product_ids()` - `app/services/final_selection.py:318`
- `_iter_ranked_products()` - `app/services/final_selection.py:328`
- `_serialize_tie_candidate()` - `app/services/final_selection.py:383`
- `_determine_phase_two_selection()` - `app/services/final_selection.py:395`

### `history_summary.py` (50 líneas)

Totales históricos para el panel

- `_money()` - `app/services/history_summary.py:11`
- `archived_campaign_summaries()` - `app/services/history_summary.py:17` - Return archival totals with no global, cross-year order/vote aggregations.

### `mode.py` (78 líneas)

Reglas de límites y modo de ensayo

- `is_test_mode_enabled()` - `app/services/mode.py:22` - Return True when the admin has enabled the test mode.
- `get_limit_configuration()` - `app/services/mode.py:27` - Provide the active limits for phase/order/final selection.  Values default to the standard configuration but are overridden when the test mode flag is enabled.

### `order_exports.py` (657 líneas)

Construccion de Excel, PDFs y hashes

- `build_final_order_context()` - `app/services/order_exports.py:27` - Aggregate selected references from votes before ordering, orders afterwards.  Returns a dictionary with per-product summaries, per-user breakdowns, and the total amount contributed by the pr
- `_summary_fingerprint()` - `app/services/order_exports.py:151` - Canonical quantities in the export, independent of display ordering.  Product and participant identifiers are checked separately: identical totals distributed to different participants must
- `assert_current_export_summary()` - `app/services/order_exports.py:180` - Reject a stale or forged export summary before writing any files.
- `generate_order_files()` - `app/services/order_exports.py:186` - Persist the Excel and PDF exports for the final order.  Returns the filenames (relative to the export folder) for later download.
- `_write_excel()` - `app/services/order_exports.py:249`
- `_write_piece_pdf()` - `app/services/order_exports.py:281`
- `_write_user_pdf()` - `app/services/order_exports.py:296`
- `_write_piece_zip()` - `app/services/order_exports.py:332`
- `_write_user_zip()` - `app/services/order_exports.py:352`
- `_write_single_piece_pdf()` - `app/services/order_exports.py:392`
- `_write_single_user_pdf()` - `app/services/order_exports.py:403`
- `_append_piece_entry()` - `app/services/order_exports.py:427`
- `_append_user_document()` - `app/services/order_exports.py:467`
- `_base_pdf()` - `app/services/order_exports.py:533`
- `_download_image()` - `app/services/order_exports.py:541`
- `_build_display_name()` - `app/services/order_exports.py:561`
- `_write_line()` - `app/services/order_exports.py:570` - Helper to ensure we always start from the left margin before writing.  Avoids layout errors when the cursor is positioned near the right edge.
- `_truncate_text()` - `app/services/order_exports.py:580`
- `_safe_filename_part()` - `app/services/order_exports.py:595`
- `_format_due_date()` - `app/services/order_exports.py:600`
- `_truncate_text()` - `app/services/order_exports.py:609`
- `_resolve_product_image()` - `app/services/order_exports.py:637`
- `_create_placeholder_image()` - `app/services/order_exports.py:651`

### `order_insights.py` (187 líneas)

Estadisticas de campaña y snapshot

- `_money()` - `app/services/order_insights.py:11`
- `_product_metrics()` - `app/services/order_insights.py:15`
- `_summarize()` - `app/services/order_insights.py:31`
- `_top()` - `app/services/order_insights.py:39`
- `_groups()` - `app/services/order_insights.py:48`
- `build_insights()` - `app/services/order_insights.py:59` - Only currently active campaign; private per-user branch never exposes others.
- `capture_snapshot()` - `app/services/order_insights.py:136` - Persist actual observed figures; avoid one row per page refresh. Admin only caller.  Same-minute changes are captured on next eligible observation (or CLI with 0).
- `load_snapshots()` - `app/services/order_insights.py:160` - Only real observations: no fake backfill or synthetic daily trend.
- `yearly_comparison()` - `app/services/order_insights.py:171` - Historical campaigns use last actual observation; otherwise show unavailable.

### `order_materialization.py` (94 líneas)

Sincronizar compromiso seleccionado con Order

- `missing_order_floors()` - `app/services/order_materialization.py:13` - Pure planner: return {(user_id, product_id): missing_quantity}.
- `materialize_selected_commitments()` - `app/services/order_materialization.py:41` - Persist only the missing vote floor, in the current campaign.  Call at the controlled final -> order transition, after final selection has been computed. The caller owns the transaction and
- `assert_selected_commitments_materialized()` - `app/services/order_materialization.py:66` - Fail closed if any selected vote floor is absent from persisted orders.  Must run in the same transaction/snapshot as the final export. Historical votes for discarded products are intentiona

### `order_simulator.py` (167 líneas)

Escenario no vinculante de previsualizacion

- `_eur()` - `app/services/order_simulator.py:16`
- `build_demo()` - `app/services/order_simulator.py:20` - Build reproducible fictitious end-to-end journey (no I/O).

### `quantity_rules.py` (33 líneas)

Escalones y minimos de cantidad

- `validate_quantity()` - `app/services/quantity_rules.py:9` - Return (valid, human-readable explanation) for a product quantity.  Reject bool, NaN, infinity, fractional and negative quantities. Values should be loaded from validated campaign configurat

### `shortage.py` (206 líneas)

Ventana de pedido insuficiente y bloqueo transaccional

- `order_total()` - `app/services/shortage.py:17`
- `minimum_total()` - `app/services/shortage.py:23`
- `personal_total()` - `app/services/shortage.py:29`
- `user_margin()` - `app/services/shortage.py:35` - Conservative margin including selected voting floors not yet materialized.
- `window_for_active()` - `app/services/shortage.py:52`
- `open_window()` - `app/services/shortage.py:57`
- `acknowledge()` - `app/services/shortage.py:76`
- `reconcile()` - `app/services/shortage.py:92` - Idempotent worker. A reached minimum wins even at the deadline.
- `cancel()` - `app/services/shortage.py:110`
- `selected_products_for_extension()` - `app/services/shortage.py:128` - Only selected, enabled products in the current annual catalogue.
- `_add_extra_order_locked()` - `app/services/shortage.py:133` - Additive participant order during the acknowledged extraordinary window.  Fail closed on deadline, cancelled state, unsigned membership, unselected products, invalid price/quantity, material
- `add_extra_order()` - `app/services/shortage.py:200` - Atomic read-check-write boundary; roll back reserved locks on failure.

### `vote_commitments.py` (19 líneas)

Comprobacion de voto no decreciente

- `assert_nondecreasing_vote()` - `app/services/vote_commitments.py:10` - Reject invalid or decreasing quantities, including deletion (zero).

## 28. Anexo: vistas HTML e internacionalizacion

Jinja genera HTML en el servidor. El menu y los botones pueden estar condicionados por permisos/fase. Al tocar una plantilla: identifica primero las variables pasadas por la ruta; escapa datos de usuarios; conserva CSRF y nombres de campos; añade cadenas traducidas a ES y EN; ensaya las dos ediciones por separado. El inventario indica las plantillas existentes en este código, no todas las rutas de navegación posibles.

| Plantilla | Titulo detectado o uso |
|---|---|
| `templates/admin_audit.html` | Registro de auditoría |
| `templates/admin_campaign_calendar.html` | Calendario · campaña {{ campaign.year }} |
| `templates/admin_campaign_history.html` | Histórico de campañas |
| `templates/admin_campaign_readiness.html` | Diagnóstico de aislamiento anual |
| `templates/admin_campaigns.html` | Campañas anuales |
| `templates/admin_commitment.html` | Compromisos de campaña |
| `templates/admin_dashboard.html` | {{ _('admin.title') }} |
| `templates/admin_limits.html` | Límites de la campaña |
| `templates/admin_translations.html` | {{ _('tr.title') }} |
| `templates/auth/commitment_unavailable.html` | Compromiso pendiente |
| `templates/auth/declaration_pending.html` | Declaración jurada recibida |
| `templates/auth/login.html` | Acceso a VALBRICK |
| `templates/auth/profile.html` | Perfil de {{ current_user.username }} |
| `templates/auth/site_access.html` | Introduce la contraseña de acceso |
| `templates/auth/upload_declaration.html` | Sube tu declaración jurada firmada |
| `templates/base.html` | Vista HTML / HTML view |
| `templates/draft_catalog.html` | Importar catálogo Excel — {{ draft.year }} |
| `templates/order_insights.html` | {{ _('insights.title') }} |
| `templates/order_simulator.html` | {{ _('sim.title') }} |
| `templates/orders/create.html` | Crear nuevo pedido |
| `templates/orders/list.html` | Pedidos registrados |
| `templates/phase_info.html` | Fase Siguiente |
| `templates/products/detail.html` | {{ product.name or product.reference }} |
| `templates/products/list.html` | Listado de Productos |
| `templates/register_agreements.html` | Acepta los compromisos |
| `templates/register_details.html` | Completa tus datos |
| `templates/set_dates.html` | Configurar Fechas |
| `templates/shortage_admin.html` | Pedido insuficiente |
| `templates/shortage_increase.html` | Ampliar mi pedido durante el plazo extraordinario |
| `templates/upload_excel.html` | Subir Excel Definitivo |
| `templates/upload_users_csv.html` | {% if draft %}Preparar participantes — {{ draft.year }}{% else %}Subir CSV de Usuarios{% endif %} |
| `templates/user_dashboard.html` | {{ _('user.title') }} |
| `templates/user_order.html` | Pedido Final |

Los textos se cargan desde `app/translations/es.json` y `app/translations/en.json` con la capa `app/i18n.py`. El panel `/admin/translations` permite guardar, restablecer, exportar e importar traducciones; usa backups y revisiones antes de importar traducciones en un servidor. Los estilos y scripts de navegador residen bajo `static/` y forman parte de la interfaz; no sustituyen validaciones del servidor.

## 29. Anexo: índice de pruebas, scripts y procedimientos

El arbol de pruebas de esta edición tiene **121 archivos `test_*.py`**. El listado sirve para localizar ejemplos antes de editar cada subsistema. El nombre del archivo no garantiza cobertura: revisar casos y asserts.

### Archivo y copias (10)

- `tests/test_archive_multiple_years.py`
- `tests/test_archive_sqlite_guards.py`
- `tests/test_archived_participation_write_guard.py`
- `tests/test_backup_zip_safety.py`
- `tests/test_campaign_archive_action.py`
- `tests/test_campaign_archive_policy.py`
- `tests/test_iteration_67_archive_export_symlinks.py`
- `tests/test_iteration_69_archive_semantics.py`
- `tests/test_iteration_70_archive_strict_values.py`
- `tests/test_v93_offline_restore.py`

### Campañas y anios (44)

- `tests/test_active_campaign_policy_contract.py`
- `tests/test_active_campaign_registry.py`
- `tests/test_active_campaign_runtime.py`
- `tests/test_annual_catalog_import.py`
- `tests/test_annual_commitment_boundary.py`
- `tests/test_annual_export_path_safety.py`
- `tests/test_annual_financial_settings.py`
- `tests/test_annual_limit_enforcement.py`
- `tests/test_annual_limits_isolation.py`
- `tests/test_annual_participant_import_contract.py`
- `tests/test_annual_phase_isolation.py`
- `tests/test_annual_profile_catalog_scope.py`
- `tests/test_annual_readiness.py`
- `tests/test_annual_readiness_extra_tables_contract.py`
- `tests/test_annual_readiness_template.py`
- `tests/test_annual_safety_contract.py`
- `tests/test_annual_write_boundaries.py`
- `tests/test_campaign_activation_gate.py`
- `tests/test_campaign_data_consistency.py`
- `tests/test_campaign_draft_flow.py`
- `tests/test_campaign_integrity_audit.py`
- `tests/test_campaign_integrity_lifecycle_schema.py`
- `tests/test_campaign_integrity_missing_schema.py`
- `tests/test_campaign_participation_contract.py`
- `tests/test_campaign_registry_contract.py`
- `tests/test_campaign_registry_cross_state.py`
- `tests/test_campaign_registry_sqlite_indexes.py`
- `tests/test_campaign_route_scope_regression.py`
- `tests/test_draft_activation_preflight.py`
- `tests/test_draft_annual_consent.py`
- `tests/test_draft_catalog_transaction.py`
- `tests/test_draft_catalog_validation.py`
- `tests/test_draft_participant_import_route.py`
- `tests/test_export_campaign_history.py`
- `tests/test_iteration_63_campaign_integration_contract.py`
- `tests/test_iteration_64_campaign_calendar.py`
- `tests/test_iteration_65_campaign_calendar_admin.py`
- `tests/test_iteration_66_campaign_overlap.py`
- `tests/test_iteration_71_draft_atomicity.py`
- `tests/test_iteration_72_annual_consent_gate.py`
- `tests/test_prepare_campaign_columns.py`
- `tests/test_v83_multi_campaign_auto.py`
- `tests/test_v92_campaign_e2e.py`
- `tests/test_year_scope_regression.py`

### HTTP e interfaz (2)

- `tests/test_history_admin_ui.py`
- `tests/test_v93_release_http.py`

### Otras regresiones (35)

- `tests/test_activation_admin_template.py`
- `tests/test_activation_cas_sqlite.py`
- `tests/test_activation_phase_atomicity.py`
- `tests/test_activation_service_transaction.py`
- `tests/test_actual_schema_bootstrap.py`
- `tests/test_compose_production_health.py`
- `tests/test_dashboard_budget_integration.py`
- `tests/test_excel_duplicate_rows.py`
- `tests/test_existing_product_scope_integrity.py`
- `tests/test_iteration_38_public_phase.py`
- `tests/test_iteration_46_public_only.py`
- `tests/test_iteration_47_sqlite_schema_contract.py`
- `tests/test_iteration_48_phase_read_integrity.py`
- `tests/test_iteration_49_selection_integrity.py`
- `tests/test_iteration_51_admin_no_delete.py`
- `tests/test_iteration_54_phase_transition_preflight.py`
- `tests/test_iteration_55_atomic_transition.py`
- `tests/test_iteration_56_transition_failures.py`
- `tests/test_iteration_57_sqlite_rollback.py`
- `tests/test_iteration_58_flask_sqlalchemy_integration.py`
- `tests/test_iteration_59_integration_contract.py`
- `tests/test_iteration_60_integration_coverage.py`
- `tests/test_iteration_61_sqlalchemy_transaction.py`
- `tests/test_license_agplv3.py`
- `tests/test_membership_reverse_integrity.py`
- `tests/test_optional_product_link_tables.py`
- `tests/test_participant_boundary_regression.py`
- `tests/test_participant_import_safety.py`
- `tests/test_private_edition_source_boundary.py`
- `tests/test_public_schedule_separation.py`
- `tests/test_run_production_default.py`
- `tests/test_simulator_v81_standalone.py`
- `tests/test_sqlite_volume_bootstrap.py`
- `tests/test_v87_maintenance.py`
- `tests/test_v88_concurrency.py`

### Pedidos y documentos (12)

- `tests/test_dashboard_orders_query_import.py`
- `tests/test_export_order_floors.py`
- `tests/test_export_snapshot_integrity.py`
- `tests/test_final_selection_export_scope.py`
- `tests/test_historical_order_parent_deletion.py`
- `tests/test_init_db_credentials_order.py`
- `tests/test_iteration_53_materialization_integrity.py`
- `tests/test_order_export_source.py`
- `tests/test_order_floor_materialization.py`
- `tests/test_order_materialization.py`
- `tests/test_v84_full_order_rehearsal.py`
- `tests/test_v92_export_missing_image.py`

### Seguridad y permisos (10)

- `tests/test_admin_order_guard_contract.py`
- `tests/test_annual_membership_sqlite_guards.py`
- `tests/test_campaign_mutation_guard.py`
- `tests/test_campaign_write_guards.py`
- `tests/test_iteration_52_vote_entry_guard.py`
- `tests/test_iteration_62_docker_security.py`
- `tests/test_proxy_config_order.py`
- `tests/test_proxy_configuration.py`
- `tests/test_v88_http_security.py`
- `tests/test_v93_release_security_contract.py`

### Votos, límites y ampliaciones (8)

- `tests/test_commitment_ledger.py`
- `tests/test_effective_commitment.py`
- `tests/test_iteration_50_admin_commitment_boundary.py`
- `tests/test_quantity_rules.py`
- `tests/test_v85_shortage.py`
- `tests/test_v86_shortage_increase.py`
- `tests/test_vote_commitments.py`
- `tests/test_vote_db_lock.py`

### Scripts presentes

- `scripts/audit_campaign_integrity.py`
- `scripts/audit_release_readiness.py`
- `scripts/backup_sqlite.py`
- `scripts/create_offline_backup.py`
- `scripts/create_offline_backup.sh`
- `scripts/export_campaign_history.py`
- `scripts/install_annual_write_boundaries.py`
- `scripts/install_archive_guards.py`
- `scripts/install_campaign_guards.py`
- `scripts/install_vote_lock.py`
- `scripts/prepare_campaign_columns.py`
- `scripts/restore_offline.py`
- `scripts/restore_offline.sh`
- `scripts/run_full_tests_isolated.sh`
- `scripts/run_v83_isolated.sh`
- `scripts/run_v84_isolated.sh`
- `scripts/run_v85_isolated.sh`
- `scripts/run_v86_isolated.sh`
- `scripts/run_v86_maintenance.sh`
- `scripts/run_v87_isolated.sh`
- `scripts/run_v87_maintenance.sh`
- `scripts/run_v87_scheduler.sh`
- `scripts/run_v88_isolated.sh`
- `scripts/run_v89_isolated.sh`
- `scripts/run_v90_isolated.sh`
- `scripts/run_v91_isolated.sh`
- `scripts/run_v92_e2e_isolated.sh`
- `scripts/run_v92_isolated.sh`
- `scripts/run_v93_release_isolated.sh`

**Orden de mantenimiento:** primero un test unitario que reproduzca el defecto, después los tests de rutas, después E2E y finalmente suite completa. Los scripts `install_*`, `prepare_*`, `migrate_*` y `restore_*` **pueden alterar datos o esquema**: ejecutarlos solo con instrucciones, backup verificable, ventana de mantenimiento y plan de rollback. Los `run_*_isolated.sh` están pensados para entornos desechables.

## 30. Referencias y límites de esta edición

**Base analizada:** VALBRICK Pública V93-RC1 (2026-11-01). Extraido de **13 modelos**, **72 rutas**, **27 modulos de servicios con **129 funciones** declaradas, **33 plantillas HTML** y **29 scripts. Los listados se derivaron mediante análisis sintactico; no son una auditoria de producción, ni una garantía de cobertura de todas las ramas. Si el código cambia, regenerar y revisar inventarios.

**Correspondencia:** adjunta estos manuales junto al ZIP exacto del código de esta edición. `docs/DESPLIEGUE.md`, `docs/RECUPERACION.md`, `README.md`, `LICENSE`, `NOTICE` y `SECURITY.md` son referencias primarias para su instalacion. En caso de contradiccion entre un manual y el código versionado, detener el procedimiento, verificar la implementacion y actualizar la documentación antes de manipular datos reales.

**Pendientes de puesta en producción:** configuración de dominio y TLS reales, validación visual en un navegador, recuperación desde copia externa en el servidor de destino, permiso de almacenamiento y versionado bloqueado de dependencias. No convertir este documento en un certificado de V1.0; la decision de publicar exige comprobar estas condiciones y mantener soporte operativo.

