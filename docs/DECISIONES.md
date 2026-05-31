# DECISIONES

## Seguridad

- El primer login debe obligar cambio de contraseña.
- Los administradores no trabajan casos clínicos como usuarios normales.
- Los administradores solo pueden:
  - resetear claves temporales
  - gestionar repositorios
  - eliminar casos

## Usuarios

- Los usuarios se desactivan, no se eliminan.
- Debe existir historial de acciones.
- Debe existir pantalla de perfil propio.
- Debe mostrarse usuario logueado y última conexión.

## Auditoría

- Cada caso tendrá log TXT propio.
- Existirá log global del sistema.
- Los logs deben registrar fecha, hora, usuario y acción.

## Diseño

- La optimización para celular es requisito.
- Los filtros activos deben visualizarse claramente.
- La tabla principal debe poder ordenarse por fecha procedimiento y paciente.

## Infraestructura

- Plataforma principal: neuropacs.rix.cl.
- Biblioteca/repositorio: neurobib.rix.cl.
- Bot/servicio asociado: neurobot.rix.cl.
