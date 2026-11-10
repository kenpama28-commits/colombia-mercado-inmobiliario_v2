# Datos

Los datos originales y procesados no se publican en GitHub. Coloca los shapefiles de UAECD en `data/raw/` y las capas auxiliares en `data/external/` para ejecutar los ETL. Los notebooks usan PostGIS con la tabla `catastro.valor_manzana`. Esta copia no contiene archivos `.dvc` ni un remoto DVC configurado; `dvc pull` no funcionará hasta que se configure uno.
