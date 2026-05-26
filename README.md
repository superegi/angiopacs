# AngioPACS / BiblioNeuro

Plataforma web para registro de procedimientos neurointervencionales, carga de fotos clínicas, archivos ZIP/DICOM e integración con Orthanc PACS.

## Componentes

- FastAPI backend
- PostgreSQL
- Orthanc PACS
- Bot de Telegram
- Interfaz web con login
- Gestión básica de usuarios
- Carga de archivos por procedimiento
- Soporte inicial para DICOM y ZIP

## Servicios

- Web AngioPACS: `neurobib.rix.cl`
- Orthanc Web: `neuropacs.rix.cl`
- Recepción DICOM C-STORE: `neurosend.rix.cl:4242`

## Estructura

```text
backend/
  main.py
  models.py
  routers/
  services/
  templates/
  static/
docker-compose.yml
.env
