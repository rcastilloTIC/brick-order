# Publicacion y despliegue de VALBRICK Publica V93-RC1

## A. Publicar el codigo sin datos privados

1. Descarga el ZIP completo de **esta edicion** y descomprimelo en una carpeta NUEVA.
   No mezcles Publica y Extended y no hagas `git add` desde una carpeta que
   contenga otras copias (`isolated/`).
2. Comprueba que el proyecto incluye `EDITION`, `LICENSE`, `NOTICE`, `Dockerfile`,
   `docker-compose.yml`, `tests/` y `.github/workflows/checks.yml`.
3. Revisa los contenidos antes de publicarlos: `git status --short`,
   `git diff --cached --name-only`; no incluir `.env`, `data/`, documentos,
   bases SQLite, logs ni ZIP con backups. La cuenta de GitHub es tuya;
   el `NOTICE` usa el seudonimo publico VALBRICK.
4. Crea un repositorio publico nuevo de GitHub, sin README inicial, y desde
   esta carpeta ejecuta:

```sh
git init
git branch -M main
git config user.name VALBRICK
# Usa tu direccion GitHub noreply para no publicar un email personal.
git add .
git status --short
git commit -m "VALBRICK Publica V93-RC1"
git remote add origin https://github.com/TU_CUENTA/TU_REPO.git
git push -u origin main
```

5. Activa las acciones CI, el analisis de dependencias y las alertas de secretos.
   NO crees el tag V1.0 hasta completar los ensayos de esta revision.

## B. Preparar un servidor con Docker, DNS y HTTPS

Prerequisitos: Docker Engine + Compose, un dominio bajo tu control,
DNS hacia el servidor, puertos publicos TCP 80 y 443 para el proxy, y
Caddy o un proxy HTTPS equivalente. Ejemplo Caddy **instalado en el host**:

```text
# Caddyfile.example: reemplaza el dominio.
mi-dominio.ejemplo.com {
    reverse_proxy 127.0.0.1:5001
}
```

Caddy solicita y renueva certificados HTTPS cuando el DNS y los puertos
estan configurados. No ejecutes este Caddyfile dentro de un contenedor
separado sin adaptar la direccion del backend.

Configura secretos y permisos ANTES de arrancar:

```sh
cp .env.example .env
chmod 600 .env
python3 -c 'import secrets; print(secrets.token_hex(32))'
# Copia el valor aleatorio a SECRET_KEY; utiliza contrasenas distintas
# de 16+ caracteres para ADMIN_PASSWORD, DEFAULT_USER_PASSWORD y SITE_ACCESS_PASSWORD.
# Edita SOURCE_CODE_URL con la URL HTTPS del codigo exacto de esta edicion.
# Si Caddy sobrescribe las cabeceras X-Forwarded-*: TRUSTED_PROXY_COUNT=1.
mkdir -p data/db data/declarations data/exports data/backups
# EN LINUX, dar acceso a UID/GID 10001 (contendor no root):
sudo chown -R 10001:10001 data
docker compose config --quiet
docker compose up --build -d
docker compose ps
docker compose logs --tail=80 app
```

**IMPORTANTE:** `docker-compose.yml` enlaza el backend solo a
`127.0.0.1:5001`, y las cookies de sesion son seguras por defecto.
No cambies esa vinculacion a `0.0.0.0`. Si no tienes HTTPS,
**no publiques el servicio**. En local, usa HTTPS del proxy; HTTP con
`SESSION_COOKIE_SECURE=true` no enviara la cookie de sesion.

`SOURCE_CODE_URL` es obligatorio en produccion y debe apuntar al codigo
real correspondiente a esa edicion (preferentemente un commit o tag).

## C. Ensayo de aceptacion y actualizaciones

Ejecuta **en una carpeta de pruebas distinta del despliegue**, usando los
scripts Docker aislados (sin base de datos real):

```sh
sh scripts/run_v92_e2e_isolated.sh
sh scripts/run_full_tests_isolated.sh
sh scripts/run_v93_release_isolated.sh
```

Comprueba manualmente: primer acceso HTTPS, alta y aprobacion, seleccion
final, paso por fase de pedido, boton Realizar pedido, Excel/PDF, archivo
anual y consulta historica. En Publica, ensaya solamente los procedimientos
que correspondan a esta edicion.

Antes de actualizar: genera y descarga un backup, copia el ZIP fuera del
servidor, para la aplicacion y comprueba los cambios de esquema. No lances
`docker compose down -v`: eliminaria volumenes de datos si los anades.

## D. Copias y restauracion

Ver `docs/RECUPERACION.md`. La restauracion web esta deshabilitada en esta
release candidate para evitar corrupcion de una instalacion activa.

## E. Limites conocidos

La suite V92 anterior supero los ensayos, pero V93 requiere su propia
confirmacion Docker. Las dependencias usan rangos y aun no existe lock
completo: tras la validacion de despliegue, fijar las versiones realmente
resueltas y supervisar avisos de seguridad. No declarar V1.0 aun.
