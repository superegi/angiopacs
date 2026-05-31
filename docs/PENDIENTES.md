# PENDIENTES

## Prioridad alta

### Usuarios y seguridad

- [ ] Cambio obligatorio de contraseña en primer login.
- [ ] Administradores solo pueden:
  - [ ] Resetear contraseñas temporales.
  - [ ] Gestionar repositorios.
  - [ ] Eliminar casos.
- [ ] Mostrar usuario logueado.
- [ ] Mostrar última conexión.
- [ ] Pantalla de perfil propio.
- [ ] Auditoría de login/logout.
- [x] Delay de seguridad de 3 segundos en login.

### Auditoría y trazabilidad

- [ ] Log global del sistema:
  - fecha
  - hora
  - usuario
  - acción
  - IP
- [ ] Log TXT por caso:
  - fecha
  - hora
  - usuario
  - cambio realizado
- [ ] Exportar logs dentro de ZIP de caso.

### Procedimientos

- [ ] Ordenar tabla por fecha procedimiento.
- [ ] Ordenar tabla por paciente.
- [ ] Mostrar visualmente filtros activos.
- [ ] Filtro de hospital basado en repositorio.
- [ ] Filtro de operador basado en repositorio.

## Prioridad media

### Gestión clínica

- [ ] Estado del caso:
  - abierto
  - hospitalizado
  - pendiente control
  - alta
- [ ] Dashboard de pacientes abiertos.
- [ ] Dashboard de hospitalizados.

### DICOM

- [ ] Asociar estudios DICOM a casos existentes.
- [ ] Agrupar múltiples archivos en un mismo estudio.
- [ ] Resolver timeout Weasis DICOM Send.

### Importación

- [ ] Drag and drop.
- [ ] Importación múltiple.
- [ ] Importación ZIP nativa.
- [ ] Compatibilidad futura de versiones.

## Prioridad baja

### Grupos

- [ ] Grupo Neurointervencional.
- [ ] Casos visibles por grupo.
- [ ] Usuarios en múltiples grupos.
- [ ] Filtro por grupo.

### Compartir casos

- [ ] Vista pública anonimizada.
- [ ] Link externo seguro.

### Optimización

- [ ] Autosave inmediato.
- [ ] Optimización móvil.
- [ ] Reducir tamaño/calidad DICOM en el futuro.

## Completado

- [x] GitHub operativo.
- [x] Docker Compose.
- [x] Orthanc integrado.
- [x] Login funcional.
- [x] Roles básicos.
- [x] Exportación de casos.
- [x] Subida DICOM.
- [x] Telegram operativo.
