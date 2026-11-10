# Preparación para GitHub

Esta carpeta es una copia de publicación del proyecto local. El material de trabajo
original permanece en la carpeta de origen, fuera de este repositorio.

## Qué se incluyó

- Código ETL con rutas relativas y conexión a PostgreSQL mediante variables de entorno.
- Siete notebooks de análisis con sus resultados históricos y 20 figuras PNG.
- Esquema SQL, metadatos del modelo y módulos generales de avalúo.

## Qué se dejó local

- Datos geoespaciales y bases de datos, archivos ZIP y binarios del modelo.
- Documentos y propuestas de un predio concreto, así como código que contiene
  información de ese expediente.
- El historial Git anterior, guardado en un ZIP en la carpeta original. Se evitó
  importarlo porque requiere una revisión independiente de todos sus objetos.

## Antes de publicar

1. Cambiar la contraseña de PostgreSQL que apareció en los scripts originales.
2. Revisar `git status` y `git ls-files` en esta carpeta.
3. Crear un repositorio vacío en GitHub, sin README ni `.gitignore` iniciales.
4. Confirmar el destino y la visibilidad del repositorio. Si se reutiliza un
   repositorio existente, comparar primero su historial con esta copia nueva.

## Comandos para publicar esta copia

```bash
git remote add origin https://github.com/kenpama28-commits/colombia-mercado-inmobiliario_v2.git
git push -u origin main
```

Si GitHub informa que `main` ya tiene commits, detener el push y revisar la
relación entre ambos historiales antes de integrar cambios. Esta copia se preparó
con un historial nuevo.
