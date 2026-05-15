# 📁 Datos del proyecto

## Estructura

| Carpeta | Contenido | Origen |
|---|---|---|
| `raw/` | Shapefiles originales valor de referencia por manzana | UAECD / IDECA |
| `external/` | Capas auxiliares geoespaciales | SDP · DANE |
| `processed/` | Datos exportados tras ETL y análisis | Generado en el proyecto |

## ⚠️ Acceso a los datos

Los datos no están incluidos en el repositorio por su tamaño (~2GB).
Están gestionados con **DVC**. Para obtenerlos:

```bash
pip install dvc dvc-gdrive
dvc pull
```

Contacta al autor para solicitar acceso al almacenamiento remoto.
