# VALBRICK Pública

**Manual de despliegue y operación del servidor**  
**Versión documentada:** V93-RC1 · 1 de noviembre de 2026  
**Edición:** PÚBLICA · Licencia del código propio: GNU AGPL-3.0-only  
**Autoría del proyecto:** VALBRICK (seudónimo)

> **Alcance de esta guía.** Explica cómo publicar el código, preparar un servidor Linux, configurar Docker y HTTPS, arrancar VALBRICK Pública, comprobar el funcionamiento y administrar copias, restauraciones y actualizaciones. Se ha contrastado con los archivos reales del ZIP `VALBRICK_Publica_V93.zip`. No se aplica a Extended y no certifica un servidor que aún no se haya verificado personalmente.

> **Antes de comenzar:** V93-RC1 superó las pruebas aisladas comunicadas por el responsable del proyecto (532 pruebas, 167 subtests y cero fallos). Esto no sustituye las comprobaciones de dominio, HTTPS, permisos, recuperación y operación en *tu* servidor. No emplees datos reales hasta completar la lista de aceptación de este manual.

## 1. Qué vas a instalar

VALBRICK Pública es una aplicación web de gestión de pedidos colectivos LEGO con inscripción y aprobación de participantes, catálogo, votaciones, selección, pedidos, generación de Excel/PDF e histórico anual. La edición Pública gestiona los pedidos insuficientes mediante el aviso público y las ampliaciones extraordinarias previstas para esa edición. **No incluye la ronda privada voluntaria de Extended.**

La instalación recomendada sigue este esquema:

```text
Navegador del usuario (HTTPS)
           |
           v
DNS del dominio -> Caddy en el servidor (puertos 80 y 443)
           |
           v
127.0.0.1:5001 -> Docker Compose -> Gunicorn -> Flask VALBRICK
                                          |
                                          v
                                ./data  (persistente)
                                db/app.sqlite
                                declarations/
                                exports/
                                backups/
```

El `Dockerfile` utiliza Python 3.11, ejecuta Gunicorn con **un solo trabajador** y usa el usuario no privilegiado **UID/GID 10001**. `docker-compose.yml` publica el puerto interno 5001 únicamente en el bucle local del servidor, no en todas las interfaces. La carpeta `./data` es un directorio persistente del equipo anfitrión.

## 2. Elige un escenario y reúne los requisitos

**Escenario de referencia:** un servidor o VPS Linux con Ubuntu LTS, Docker Engine, el complemento Docker Compose y Caddy instalado **en el propio host**. Si usas otra distribución, otro proxy o Docker Desktop, adapta las órdenes de instalación y los permisos: no copies ciegamente el ejemplo.

Antes de ejecutar comandos debes tener:

- Acceso de administrador al servidor por SSH, una cuenta con permisos para Docker y espacio disponible para futuras bases de datos y documentos.
- Un **nombre de dominio propio** y control sobre sus registros DNS A/AAAA; los registros que publiques deben apuntar al servidor correcto.
- Puertos públicos TCP **80 y 443** abiertos hacia Caddy; el 5001 **no** se abre en el cortafuegos externo.
- Git para obtener el código; Python 3 en el anfitrión solo se utiliza, de forma opcional, para generar secretos. La aplicación Python se ejecuta dentro de Docker.
- Una ubicación externa al servidor para guardar copias de seguridad cifradas o protegidas, con una política de retención.

**Seguridad de la cuenta del servidor.** Usa SSH con claves, actualizaciones del sistema y firewall. Antes de activar reglas, conserva acceso SSH. Pertenecer al grupo Linux `docker` concede privilegios equivalentes a root; reserva ese acceso a administradores confiables.

## 3. Identifica y conserva el paquete correcto

Trabaja únicamente con **VALBRICK Pública V93-RC1**. Al descomprimir el ZIP, la carpeta debe contener, entre otros:

| Archivo o directorio | Para qué sirve |
|---|---|
| `EDITION`, `VALBRICK_EDITION` | Identificación de la edición. Debe indicar `PUBLICA`. |
| `Dockerfile`, `docker-entrypoint.sh` | Construcción y arranque del contenedor. |
| `docker-compose.yml` | Servicio `app`, puertos, variables y volumen persistente. |
| `.env.example`, `.gitignore`, `.dockerignore` | Configuración de ejemplo y exclusiones. |
| `Caddyfile.example` | Ejemplo de proxy HTTPS en el host. |
| `app/`, `products/`, `orders/`, `templates/`, `static/` | Código y vistas. |
| `scripts/`, `tests/` | Validaciones, mantenimiento y recuperación. |
| `LICENSE`, `NOTICE` | Licencia y atribución del proyecto. |

Comprueba desde la raíz del proyecto:

```sh
cat EDITION
# Resultado esperado: PUBLICA
ls -la .env.example docker-compose.yml Dockerfile LICENSE NOTICE
```

No incorpores archivos de Extended, instalaciones antiguas, carpetas `isolated`, bases reales ni documentos personales al repositorio. **El ZIP de aplicación no es una copia de tus datos.** Guarda cualquier respaldo operativo por separado.

## 4. Publica la edición Pública en GitHub

Si ya tienes un repositorio público exclusivo para Pública, utiliza ese repositorio y revisa primero sus archivos e historial. Si empiezas desde cero, crea un repositorio público **vacío**, sin README inicial, y ejecuta los comandos en la carpeta que contiene `Dockerfile`:

```sh
git init
git branch -M main
git config --local user.name "VALBRICK"
# Sustituye este ejemplo por TU correo noreply obtenido en GitHub > Settings > Emails.
git config --local user.email "TU_DIRECCION_NOREPLY_DE_GITHUB"
git add .
git status --short
git diff --cached --name-only
git commit -m "VALBRICK Publica V93-RC1"
git remote add origin https://github.com/TU_CUENTA/TU_REPOSITORIO.git
git push -u origin main
```

**Revisión obligatoria antes del `commit`:** no deben aparecer `.env`, `data/`, `*.sqlite`, documentos firmados, PDFs de participantes, backups, archivos `.key` o copias de Extended. Si ya se publicó algún secreto, **retíralo, rótalo y revisa el historial Git**: añadir una regla a `.gitignore` no borra el historial antiguo.

Publicar el código en un repositorio abierto facilita el acceso al código fuente correspondiente exigible bajo AGPLv3. Configura después `SOURCE_CODE_URL` con la dirección HTTPS **de este repositorio público**, idealmente con un tag o commit identificable. No etiquetes aún una V1.0 que no se haya aceptado en producción.

## 5. Instala y comprueba Docker en el servidor

Sigue la instalación oficial de Docker Engine y su complemento Compose para tu distribución. Para Ubuntu consulta: <https://docs.docker.com/engine/install/ubuntu/>. No uses scripts de terceros sin revisión. Comprueba que el servicio funciona:

```sh
docker --version
docker compose version
docker info
```

Si tu usuario no tiene permiso, ejecuta las operaciones con un administrador autorizado o configura cuidadosamente el acceso a Docker. El ejemplo siguiente asume que `docker compose` funciona con la cuenta operativa. Comprueba que ningún otro proyecto utiliza ya el puerto local 5001:

```sh
sudo ss -ltnp | grep ':5001' || true
```

**No hace falta instalar Flask, Gunicorn ni pytest en el host.** El `Dockerfile` instala las dependencias Python dentro de la imagen. El archivo `requirements.txt` contiene rangos de versiones y no un bloqueo completo; para producción estable hay que registrar y revisar las versiones instaladas en la imagen probada.

## 6. Obtén el código y prepara un directorio estable

Ejemplo para un repositorio ya creado:

```sh
cd ~
git clone https://github.com/TU_CUENTA/TU_REPOSITORIO.git valbrick-publica
cd ~/valbrick-publica
cat EDITION
# Debe mostrar PUBLICA
```

Si todavía no usas GitHub, copia el contenido del ZIP a una carpeta nueva del servidor y entra en ella; **no** descomprimas sobre una instalación con datos reales ni mezcles repositorios. En esta guía, todos los comandos siguientes se ejecutan **desde la raíz de `~/valbrick-publica`**, salvo que se indique expresamente otro directorio.

## 7. Crea `.env` y protege las credenciales

El contenedor necesita un archivo `.env` privado. Nunca lo subas a GitHub ni lo adjuntes a una incidencia pública.

```sh
cp .env.example .env
chmod 600 .env
python3 -c 'import secrets; print(secrets.token_hex(32))'
# Edita el archivo con: nano .env
```

Sustituye **todos** los valores `REPLACE_...`. Ejemplo explicativo (no reutilices estas palabras):

```dotenv
FLASK_ENV=production
ADMIN_USERNAME=admin
ADMIN_PASSWORD=CAMBIAR_POR_CLAVE_UNICA_DE_16_O_MAS_CARACTERES
DEFAULT_USER_PASSWORD=OTRA_CLAVE_UNICA_DE_16_O_MAS_CARACTERES
SECRET_KEY=PEGAR_AQUI_64_CARACTERES_HEXADECIMALES_ALEATORIOS
SITE_ACCESS_PASSWORD=OTRA_FRASE_DE_ACCESO_LARGA_Y_UNICA
PORT=5001
TRUSTED_PROXY_COUNT=1
SOURCE_CODE_URL=https://github.com/TU_CUENTA/TU_REPOSITORIO
```

| Variable | Función y regla práctica |
|---|---|
| `FLASK_ENV` | `production` activa validaciones de configuración y desactiva el modo depuración. |
| `SECRET_KEY` | Clave de firma de sesiones Flask; genera al menos 32 bytes aleatorios. Conserva una copia privada. |
| `ADMIN_USERNAME` | Usuario administrador que se crea si no existe. |
| `ADMIN_PASSWORD` | Contraseña del administrador **inicial**. El arranque exige al menos 12 caracteres; se recomiendan 16 o más. |
| `DEFAULT_USER_PASSWORD` | Contraseña inicial utilizada al crear o importar participantes; no debe ser la del administrador. |
| `SITE_ACCESS_PASSWORD` | Contraseña adicional de acceso al sitio, previa al login de usuario. |
| `PORT` | Puerto **del host** para el proxy, por defecto 5001; el contenedor escucha internamente en 5001. |
| `TRUSTED_PROXY_COUNT` | `1` **solo** detrás de un Caddy confiable que sobrescriba correctamente las cabeceras `X-Forwarded-*`; si no hay proxy confiable, `0`. |
| `SOURCE_CODE_URL` | URL pública HTTPS del **código correspondiente a Pública**; obligatoria en modo producción. |

**Atención a las contraseñas existentes:** `ADMIN_PASSWORD` se usa para crear el administrador en una base nueva; cambiarla después en `.env` **no restablece** automáticamente la contraseña almacenada de un usuario ya existente. Para una instalación existente, utiliza los procedimientos de gestión de cuentas.

`SESSION_COOKIE_SECURE` ya queda fijada a `true` en `docker-compose.yml`: el navegador solo enviará la cookie de sesión mediante HTTPS. **No publiques la web por HTTP** para intentar sortearlo. Opciones adicionales como `REDIS_URL`, límites de pedidos e idiomas existen en `config.py`; no modifiques sus valores sin una prueba de regresión.

## 8. Crea y protege el almacenamiento persistente

La configuración monta el directorio anfitrión `./data` como `/data` en el contenedor:

```sh
mkdir -p data/db data/declarations data/exports data/backups
sudo chown -R 10001:10001 data
ls -ld data data/db data/declarations data/exports data/backups
```

En Linux, `10001` es el UID/GID del proceso de VALBRICK, definido en el Dockerfile. Este usuario debe poder leer y escribir `data/db/app.sqlite`, las declaraciones, exportaciones y backups. La estructura real es:

```text
valbrick-publica/
  .env                   # secreto: nunca publicar
  data/                  # datos reales: nunca publicar
    db/app.sqlite        # SQLite operativa
    declarations/        # documentos firmados; datos personales
    exports/             # Excel, PDF y archivos de salida
    backups/             # ZIP de respaldo y otros respaldos
```

**Precaución:** no confundas `data/db/app.sqlite` (base operativa) con `database.sqlite3` (nombre de la copia de SQLite *dentro* del ZIP offline). No elimines `data` al actualizar. Si el contenedor informa de `Permission denied`, revisa propietario, montaje y permisos antes de volver a arrancar.

## 9. Valida la configuración y arranca la aplicación

Desde la carpeta del proyecto:

```sh
docker compose config --quiet
docker compose up --build -d
docker compose ps
docker compose logs --tail=100 app
```

En el primer arranque, `run.py` crea la aplicación Flask, inicializa las tablas de la base y crea el administrador inicial si no existía. Si faltan `SECRET_KEY`, `SITE_ACCESS_PASSWORD`, `SOURCE_CODE_URL` o una contraseña inicial válida, **el arranque debe fallar** y los logs explicarán el requisito.

Comprueba que el servicio solo escucha en loopback:

```sh
docker compose ps
sudo ss -ltnp | grep ':5001'
# Diagnóstico HTTP LOCAL del backend; no sirve para iniciar sesión:
curl -I http://127.0.0.1:5001/access
```

Puede responder `200` o una redirección según la sesión y la ruta; es una prueba de conectividad, **no** una prueba del acceso HTTPS ni de toda la aplicación. El `healthcheck` de Compose solo intenta establecer una conexión TCP, así que el estado `healthy` no acredita por sí solo que funcionen login, exportaciones o base de datos.

No conviertas `127.0.0.1:${PORT:-5001}:5001` en `0.0.0.0:5001:5001`: eso expondría directamente Gunicorn y el sitio quedaría sin la capa HTTPS prevista.

## 10. Configura Caddy y el HTTPS público

Este ejemplo supone **Caddy instalado como servicio del propio servidor** (no en otro contenedor). Sigue la guía oficial: <https://caddyserver.com/docs/install>. En un VPS con DNS correcto y puertos 80/443 disponibles, Caddy puede obtener y renovar automáticamente certificados TLS.

Cambia el dominio y configura `/etc/caddy/Caddyfile`:

```caddyfile
pedidos.ejemplo.com {
    reverse_proxy 127.0.0.1:5001
}
```

Comprueba y aplica:

```sh
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl reload caddy
sudo systemctl status caddy
curl -I https://pedidos.ejemplo.com/access
```

El dominio anterior es **ficticio**; sustitúyelo por uno que controles. Comprueba que su registro DNS A, y AAAA si publicas IPv6, apunta al servidor adecuado. Permite 80/443 hacia Caddy y **no abras 5001** al exterior. Si utilizas un Caddyfile en un contenedor distinto, `127.0.0.1` apuntaría a ese contenedor, no al de Flask: habría que rediseñar la red del proxy.

Cuando Caddy sea el único proxy confiable, `TRUSTED_PROXY_COUNT=1` permite a Flask interpretar las cabeceras reenviadas; no aumentes el contador sin justificar la cadena completa de proxies. Si el certificado no se emite, revisa DNS, cortafuegos, puertos y logs de Caddy: <https://caddyserver.com/docs/automatic-https>.

## 11. Comprueba el primer acceso de extremo a extremo

Abre **`https://TU_DOMINIO/`**, no la dirección HTTP del puerto 5001. El recorrido normal incluye:

1. La pantalla de **contraseña de acceso al sitio**, configurada con `SITE_ACCESS_PASSWORD`.
2. El **inicio de sesión** de VALBRICK, con `ADMIN_USERNAME` y la contraseña inicial.
3. El panel de administración y el registro/activación de la campaña anual correspondiente.
4. La preparación de usuarios, declaraciones firmadas, catálogo, límites y calendario según el manual de administrador.
5. La selección final, el paso a fase `order`, el botón **«Realizar pedido»**, Excel/PDF, archivo anual e histórico.

Haz primero una campaña con datos **ficticios**, no con documentos reales. Verifica que el pie de página muestre el enlace al código Público configurado en `SOURCE_CODE_URL`. Usa únicamente los flujos públicos; no debe aparecer invitación o ampliación privada de Extended.

Anota la fecha, versión, URL probada, persona responsable y resultado en la hoja de aceptación. La prueba funcional debe hacerse también desde un navegador externo, no solo desde el propio servidor.

## 12. Ejecuta las pruebas automatizadas sin tocar producción

Hazlo **en un clon o carpeta aislada**, nunca mezclando código de otra edición o volúmenes reales. Los scripts Docker están preparados para crear contenedores desechables sin publicar puertos ni montar `./data` de producción:

```sh
sh scripts/run_v93_release_isolated.sh
sh scripts/run_v92_e2e_isolated.sh
sh scripts/run_full_tests_isolated.sh
```

La última suite completa de Pública V93-RC1 comunicada por el responsable terminó con **532 pruebas superadas, 1 omitida, 167 subtests superados y cero fallos**. Es un precedente, no una garantía de una imagen reconstruida con dependencias cambiantes. Conserva el resultado de las pruebas y los identificadores del commit/imagen que realmente desplegaste.

Las pruebas unitarias comprueban funciones y rutas, pero no sustituyen las comprobaciones del DNS, HTTPS, firewall, permisos, restauración externa y experiencia desde el navegador.

## 13. Haz copias de seguridad recuperables

Desde la interfaz de administración es posible **crear y descargar** una copia. Para una copia completa y consistente con el servicio parado, usa el script offline desde la raíz del proyecto:

```sh
sh scripts/create_offline_backup.sh
```

El script muestra un aviso para detener procesos externos, detiene el servicio `app`, crea y verifica un ZIP en `data/backups/`, y arranca de nuevo el servicio si finaliza correctamente. Si hay un error, **el servicio permanece detenido** para que lo revises. El archivo contiene `manifest.json`, `database.sqlite3`, `declarations/` y `exports/` (con los archivos existentes).

**Una base SQLite sola no es un respaldo completo del pedido:** las declaraciones y documentos exportados se guardan fuera de ella. Copia el ZIP fuera del mismo servidor y controla su acceso, ya que puede contener datos personales y pedidos. Comprueba periódicamente que la copia puede restaurarse en un entorno desechable. Si necesitas extraer un archivo de backup con permisos `0600` y propietario `10001`, utiliza una operación administrativa autorizada sin relajar permisos a todo el mundo.

## 14. Restaura una copia completa con el sistema detenido

**La restauración desde la web está deshabilitada** en V93-RC1. No la reactives como solución rápida. Para restaurar:

1. Identifica el ZIP correcto de **Pública** y comprueba que no contiene datos equivocados. Ensaya en una instalación desechable.
2. Detén también cualquier tarea externa `cron` o scheduler que pueda escribir datos. La parada del contenedor web no detiene procesos externos.
3. Copia el ZIP al proyecto, por ejemplo a `./data/backups/`, asegurando su lectura por el procedimiento de restauración. Si el directorio es propiedad de UID 10001, necesitarás permisos de administrador para copiarlo. Por ejemplo:

```sh
sudo cp /RUTA_SEGURA/BACKUP_PUBLICA.zip ./data/backups/
sudo chown 10001:10001 ./data/backups/BACKUP_PUBLICA.zip
sudo chmod 600 ./data/backups/BACKUP_PUBLICA.zip
```

4. Ejecuta desde la raíz del proyecto:

```sh
sh scripts/restore_offline.sh ./data/backups/NOMBRE_DEL_BACKUP.zip
```

El script detiene `app`, valida ZIP, manifiesto, integridad de SQLite, edición y fase, prepara los datos y sustituye el árbol `data` con capacidad de rollback si falla el intercambio. Al tener éxito conserva la carpeta anterior como `data.pre-restore-FECHA/`. Si falla, **la aplicación queda detenida**. No fuerces un reinicio sin investigar el error.

Después compara campaña, participantes, pedidos, referencias, Excel/PDF e histórico. Conserva `data.pre-restore-*` hasta haber verificado todo y guardado otro respaldo externo. Nunca restaures un ZIP de **Extended** sobre Pública: el procedimiento lo rechazará.

## 15. Actualiza y vuelve atrás sin perder pedidos

No actualices directamente una instalación en uso a partir de un ZIP nuevo. Procedimiento conservador:

1. Programa una ventana sin usuarios y verifica que existe una copia externa reciente.
2. Prueba el nuevo commit en una **instalación aislada** con copias ficticias; documenta cambios de esquema y dependencias.
3. Haz una copia completa offline justo antes de la actualización.
4. Detén el servicio, actualiza el código a un commit o tag **revisado**, reconstruye y comprueba los logs.

```sh
sh scripts/create_offline_backup.sh
# Primero verifica en otra carpeta el commit/tag objetivo.
docker compose stop app
git status --short
git fetch --tags
git checkout IDENTIFICADOR_DEL_COMMIT_PROBADO
docker compose up --build -d
docker compose ps
docker compose logs --tail=100 app
```

La orden `git checkout` es un ejemplo **solo** para un árbol sin cambios locales y un commit ya probado. Si la actualización ha alterado el esquema SQLite, volver atrás **solo el código** puede ser inseguro: recupera el conjunto **código + datos** correspondiente a una copia anterior y valida antes de abrir a los usuarios.

**No ejecutes** `docker compose down -v` ni borres `data` pensando que es caché. Guarda un registro de versión, hash del commit, fecha, copia de respaldo y resultados de pruebas.

## 16. Mantenimiento programado y límites operativos

`docker-compose.yml` inicia **solo** el servicio `app`: no declara un servicio scheduler independiente. La aplicación dispone de los comandos Flask `check-shortage` y `capture-insights`, agrupados en `scripts/run_v87_maintenance.sh`. Su ejecución periódica requiere un planificador externo administrado por ti.

**No inicies dos planificadores simultáneos** ni ejecutes scripts de mantenimiento sin el mismo entorno de aplicación y la base de datos correcta. Si decides crear un cron o servicio aparte, documenta su propietario, frecuencia, logs y procedimiento de parada antes de cualquier backup/restauración. El `run_v87_scheduler.sh` existente espera ejecutarse **dentro de un contenedor configurado**, no en el host sin dependencias.

Mantén Gunicorn con **un trabajador** mientras no revises concurrencia y rate limiting: el proyecto usa SQLite y por defecto `memory://` para el limitador de peticiones, lo cual no equivale a un almacén compartido entre procesos. Registra regularmente espacio (`df -h`), tamaño del directorio (`du -sh data`), estado del contenedor y últimas copias externas.

## 17. Seguridad mínima para un servidor accesible por Internet

- Usa secretos distintos, HTTPS, actualizaciones del sistema y contraseñas fuertes; conserva `.env` fuera de Git.
- No publiques SQLite, documentos de identidad, declaraciones firmadas, exportaciones, ZIP de backup ni logs que contengan datos personales.
- El puerto 5001 está reservado al **host local**; Internet solo debe acceder a 80/443 del proxy.
- Usa `TRUSTED_PROXY_COUNT=1` únicamente cuando el proxy sea confiable y normalice `X-Forwarded-*`.
- Limita el acceso Docker y SSH. Comprueba alertas de dependencias y secretos en GitHub.
- Los requisitos Python del paquete se expresan como **rangos**, sin lock integral: verifica nuevas imágenes cuando cambien dependencias.
- Protege backups fuera del servidor; prueba el procedimiento de recuperación y documenta el tiempo máximo aceptable de indisponibilidad.
- Revisa que la URL de código correspondiente y `LICENSE`/`NOTICE` se mantengan en las publicaciones AGPL.

## 18. Diagnóstico rápido de problemas frecuentes

| Síntoma | Causa probable | Comprobación / actuación |
|---|---|---|
| `docker: command not found` | Docker no instalado | Instala Engine + Compose desde documentación oficial. |
| `permission denied` al usar Docker | Cuenta sin acceso al daemon | Revisa permisos administrativos; el grupo `docker` concede acceso privilegiado. |
| `Permission denied: /data/...` | Volumen sin permisos para UID 10001 | Verifica `./data`, propietario 10001:10001 y rutas internas. |
| El contenedor sale al arrancar | `.env` incompleto o esquema incompatible | `docker compose logs --tail=100 app`; comprueba claves y `SOURCE_CODE_URL`. |
| `502 Bad Gateway` en HTTPS | Caddy no conecta a Flask | `docker compose ps`, puerto 127.0.0.1:5001 y Caddyfile. |
| Certificado HTTPS no emitido | DNS/80/443 incorrectos | Revisa dominio, registros A/AAAA, firewall y logs de Caddy. |
| Redirecciones o URL con esquema erróneo | Configuración de proxy | Comprueba que Caddy reenvía cabeceras confiables y valor de `TRUSTED_PROXY_COUNT`. |
| No se inicia sesión por HTTP | Cookie segura | Accede mediante `https://TU_DOMINIO`, no desactives HTTPS en producción. |
| No aparece una campaña activa | Registro anual sin preparar | Accede como administrador y realiza la preparación anual. |
| Alta/importación devuelve 503 | `DEFAULT_USER_PASSWORD` ausente o insegura | Configúrala en `.env` y reinicia, sin exponer su valor. |
| Falta exportación | Fase incorrecta o validación fallida | Revisa fase `order`, avisos del panel y logs; no fuerces datos SQL. |
| Backup offline falla | Escrituras externas, espacio o permisos | Detén procesos externos, verifica disco y logs; el script deja `app` parado si falla. |
| Restauración rechazada | ZIP equivocado, dañado o de Extended | Usa el backup correcto y consulta el error; no elimines validaciones. |

Los comandos de primera respuesta son:

```sh
docker compose ps
docker compose logs --tail=100 app
sudo systemctl status caddy
sudo ss -ltnp | grep -E ':(80|443|5001)\b'
df -h
```

No compartas logs completos o `.env` en foros sin eliminar antes información sensible.

## 19. Lista de aceptación antes de usar datos reales

Marca todos los puntos, conservando evidencias para tu instalación:

- [ ] El repositorio es **solo Pública** y tiene `LICENSE`, `NOTICE` y código correspondiente público.
- [ ] Git y la imagen Docker se han construido a partir del commit/version que se probó.
- [ ] `.env` contiene secretos únicos, `SOURCE_CODE_URL` real y `FLASK_ENV=production`.
- [ ] `data/` persiste, pertenece al UID 10001 y no está publicado en GitHub.
- [ ] La aplicación responde localmente en `127.0.0.1:5001` y **no** en una interfaz pública.
- [ ] El dominio abre exclusivamente con HTTPS válido y Caddy funciona como servicio.
- [ ] Contraseña de acceso al sitio, cuenta admin y navegación funcionan desde un navegador externo.
- [ ] Campaña ficticia: usuario, declaración, selección, pedido, Excel/PDF e histórico funcionan.
- [ ] El botón «Realizar pedido» solo se habilita cuando procede.
- [ ] Pruebas aisladas V93, E2E y suite completa sin fallos en la revisión desplegada.
- [ ] Backup ZIP completo copiado fuera del servidor y restaurado con éxito en ensayo.
- [ ] Actualización y rollback documentados; no hay otro scheduler escribiendo durante restauraciones.
- [ ] Se han comprobado seguridad de firewall/SSH, espacio disponible y política de retención.

**Criterio de salida:** hasta superar estos controles en el servidor real, utiliza la etiqueta de **candidata V93-RC1**, no una declaración de V1.0 certificada.

## 20. Mapa de referencia y fuentes

**Archivos del propio proyecto contrastados:** `README.md`, `.env.example`, `config.py`, `run.py`, `app/__init__.py`, `Dockerfile`, `docker-entrypoint.sh`, `docker-compose.yml`, `Caddyfile.example`, `docs/DESPLIEGUE.md`, `docs/RECUPERACION.md`, `scripts/create_offline_backup.sh`, `scripts/create_offline_backup.py`, `scripts/restore_offline.sh`, `scripts/restore_offline.py`, `scripts/run_v87_maintenance.sh`, `scripts/run_v93_release_isolated.sh`, `scripts/run_v92_e2e_isolated.sh`, `scripts/run_full_tests_isolated.sh`, `.gitignore`, `.dockerignore` y `.github/workflows/checks.yml`.

**Documentación externa para instalaciones y configuración actualizadas:**

- Docker Engine para Ubuntu: <https://docs.docker.com/engine/install/ubuntu/>
- Docker Compose y archivos de entorno: <https://docs.docker.com/compose/how-tos/environment-variables/variable-interpolation/>
- Permisos del daemon Docker: <https://docs.docker.com/engine/install/linux-postinstall/>
- Instalación oficial de Caddy: <https://caddyserver.com/docs/install>
- HTTPS automático en Caddy: <https://caddyserver.com/docs/automatic-https>
- Proxy inverso Caddy: <https://caddyserver.com/docs/caddyfile/directives/reverse_proxy>

**Control de edición:** Este manual describe exclusivamente el ZIP **Pública V93-RC1**. No incorpora funcionalidades de Extended ni sustituye el manual de administrador. Actualízalo y vuelve a comprobar los comandos cuando cambien Dockerfile, Compose, rutas, secretos, esquema de SQLite o scripts de recuperación.
