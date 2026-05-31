# NeuroPACS / AngioPACS

Sistema web para registro, organizacion y visualizacion de casos de neurointervencion.

El proyecto integra:

* FastAPI como backend web.
* PostgreSQL como base de datos.
* Orthanc como servidor DICOM/PACS.
* Gateway interno desde la web hacia Orthanc mediante `/orthanc`.
* Docker Compose para despliegue local, servidor de prueba y produccion.

## Estado actual

El flujo validado es:

```text
Usuario
  -> Web NeuroPACS
  -> FastAPI
  -> /orthanc/*
  -> Orthanc interno
```

El usuario no debe acceder directamente a Orthanc ni ingresar la clave de Orthanc en el navegador. El acceso a Orthanc debe pasar por la sesion web de NeuroPACS.

## Arquitectura

Servicios principales:

```text
backend-bot     FastAPI / NeuroPACS
postgres-db     PostgreSQL
orthanc-pacs    Orthanc
```

Puertos habituales:

```text
Backend web:       8000 o 8001 segun .env
Orthanc web:       8042
Orthanc DICOM:     4242
PostgreSQL:        5432 interno
```

En produccion, Orthanc web debe quedar protegido. Se recomienda publicarlo solo en localhost o red interna.

Ejemplo esperado en produccion:

```text
Web publica:
https://neurobib.rix.cl

Gateway Orthanc:
https://neurobib.rix.cl/orthanc/system

```

## Requisitos

* Linux
* Docker
* Docker Compose
* Git

Verificacion rapida:

```bash
docker --version
docker compose version
git --version
```

## Instalacion desde cero

Clonar el repositorio:

```bash
mkdir -p ~/Experimentos
cd ~/Experimentos
git clone https://github.com/superegi/angiopacs.git angiopacs
cd angiopacs
```

## Generar archivo .env

El proyecto incluye un wizard:

```bash
chmod +x scripts/generate_env.sh
./scripts/generate_env.sh
```

Valores recomendados para servidor de prueba local:

```text
PORT_BACKEND=8000
PORT_ORTHANC_WEB=8042
PORT_ORTHANC_DICOM=4242

WEB_PUBLIC_URL=http://localhost:8000
ANGIOPACS_PUBLIC_URL=http://localhost:8000

ORTHANC_URL=http://orthanc-pacs:8042
ORTHANC_PUBLIC_URL=/orthanc

ORTHANC_AUTHENTICATION_ENABLED=true
ORTHANC_BIND_ADDRESS=127.0.0.1

POSTGRES_USER=admin_angio
POSTGRES_DB=angiopacs_db
```

El wizard debe generar claves seguras para:

```text
ANGIOPACS_PASSWORD
ANGIOPACS_SESSION_SECRET
POSTGRES_PASSWORD
ORTHANC_BACKEND_PASSWORD
ORTHANC_ADMIN_PASSWORD
ORTHANC_VISIT_PASSWORD
```

No subir `.env` a Git.

## Variables importantes

```text
DATABASE_URL
POSTGRES_USER
POSTGRES_PASSWORD
POSTGRES_DB

ORTHANC_URL
ORTHANC_USER
ORTHANC_PASSWORD
ORTHANC_PUBLIC_URL

WEB_PUBLIC_URL
ANGIOPACS_PUBLIC_URL

PORT_BACKEND
PORT_ORTHANC_WEB
PORT_ORTHANC_DICOM
```

`DATABASE_URL` debe apuntar al servicio interno de PostgreSQL:

```text
postgresql://usuario:clave@postgres-db:5432/base
```

`ORTHANC_URL` debe apuntar al servicio interno de Orthanc:

```text
http://orthanc-pacs:8042
```

`ORTHANC_PUBLIC_URL` debe ser:

```text
/orthanc
```

## Levantar el stack

```bash
docker compose up -d --build
```

Ver estado:

```bash
docker compose ps
```

Ver logs del backend:

```bash
docker compose logs --tail=100 backend-bot
```

## Validacion local

Sin sesion web activa:

```bash
curl -sS -o /dev/null -w "web / -> %{http_code}\n" http://127.0.0.1:8000/
curl -sS -o /dev/null -w "web /login -> %{http_code}\n" http://127.0.0.1:8000/login
curl -sS -o /dev/null -w "gateway /orthanc/system -> %{http_code}\n" http://127.0.0.1:8000/orthanc/system
curl -sS -o /dev/null -w "orthanc directo /system -> %{http_code}\n" http://127.0.0.1:8042/system
```

Resultado esperado:

```text
web / -> 303
web /login -> 200
gateway /orthanc/system -> 303
orthanc directo /system -> 401
```

El codigo `303` en `/orthanc/system` es correcto sin sesion. Significa que NeuroPACS intercepta la ruta y envia al login.

Luego abrir en navegador:

```text
http://localhost:8000/login
```

Despues de iniciar sesion, abrir:

```text
http://localhost:8000/orthanc/system
```

Resultado esperado: JSON de Orthanc sin pedir clave de Orthanc.

## Gateway interno hacia Orthanc

El gateway vive en:

```text
backend/routers/orthanc_gateway.py
```

Debe estar registrado en:

```text
backend/main.py
```

Debe existir una linea de importacion:

```python
from routers.orthanc_gateway import router as orthanc_gateway_router
```

Y una linea de registro:

```python
app.include_router(orthanc_gateway_router)
```

Tambien se requiere `httpx` en:

```text
backend/requirements.txt
```

## Seguridad

Reglas basicas:

* No exponer Orthanc web publicamente sin control.
* No desactivar autenticacion de Orthanc en produccion.
* No subir `.env` ni archivos de secretos a Git.
* La web debe acceder a Orthanc por `ORTHANC_URL`.
* El usuario debe acceder a Orthanc por `/orthanc`, no por `:8042`.

Archivos que no deben subirse:

```text
.env
.env.generated.secrets.txt
.env.bak*
*.bak.*
```

## Flujo recomendado de desarrollo

1. Probar cambios en servidor de prueba.
2. Validar login web.
3. Validar `/orthanc/system` con sesion.
4. Validar que Orthanc directo devuelve `401`.
5. Hacer commit.
6. Subir a GitHub.
7. En produccion, hacer pull y rebuild.
8. Validar nuevamente.
