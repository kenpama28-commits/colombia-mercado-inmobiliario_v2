# Preparación para GitHub

**Estado:** publicado en [GitHub](https://github.com/kenpama28-commits/colombia-mercado-inmobiliario_v2) desde la rama `main`.

Esta carpeta es una copia de publicación del proyecto local. El material de trabajo
original permanece en la carpeta de origen, fuera de este repositorio.

## Qué se incluyó

- Código ETL con rutas relativas y conexión a PostgreSQL mediante variables de entorno.
- Siete notebooks de análisis con sus resultados históricos y 20 figuras PNG.
- Esquema SQL, metadatos del modelo y módulos generales de avalúo.

## Qué se dejó local

- Datos geoespaciales y bases de datos, y binarios del modelo.
- Documentos y propuestas de un predio concreto, así como código que contiene
  información de ese expediente.
- El historial Git anterior, guardado descomprimido en `_historial_git_local/`
  dentro de la carpeta original. Se evitó
  importarlo porque requiere una revisión independiente de todos sus objetos.

## Revisión y mantenimiento

1. Cambiar la contraseña de PostgreSQL que apareció en los scripts originales.
2. Revisar `git status` y `git ls-files` en esta carpeta.
3. Mantener fuera de Git los datos, expedientes y modelos binarios.

## Comandos para futuras actualizaciones

```bash
git add .
git commit -m "Describir el cambio"
git push
```

Esta copia se preparó con un historial nuevo. El historial local anterior se
conserva por separado en la carpeta de origen.
