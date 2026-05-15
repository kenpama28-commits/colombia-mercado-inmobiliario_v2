# 🏙️ Bogotá: Análisis Predictivo del Mercado Inmobiliario Urbano


## 📌 Descripción

Proyecto de analítica geoespacial avanzada sobre el mercado inmobiliario urbano de Bogotá.
Integra datos catastrales de la UAECD (2020–2026) con variables de movilidad, seguridad y
normativa urbanística para construir modelos predictivos de valorización y expansión urbana.

**299.482 registros** · **7 años** · **20 localidades** · **~42.000 manzanas por año**

---

## 🗂️ Estructura del proyecto

colombia-mercado-inmobiliario_v2/
├── data/
│   ├── raw/          ← Shapefiles originales UAECD (gestionados con DVC)
│   ├── external/     ← Capas auxiliares: localidades, sectores, rural
│   └── processed/    ← Datos exportados listos para análisis
├── notebooks/        ← Análisis paso a paso
├── sql/              ← Consultas y KPIs en PostgreSQL + PostGIS
├── src/              ← Scripts ETL reutilizables
├── models/           ← Modelos entrenados
├── reports/          ← Informes y visualizaciones exportadas
└── dashboard/        ← Archivo Power BI y capturas

---

## 🔬 Stack tecnológico

| Capa | Tecnología |
|---|---|
| Lenguaje | Python 3.12 |
| Base de datos | PostgreSQL 18 + PostGIS 3.6 |
| Análisis geoespacial | GeoPandas · Shapely · Folium |
| Modelado | Scikit-learn · MGWR · SHAP |
| Visualización | Power BI · Matplotlib · Seaborn |
| Versionado de datos | DVC + Google Drive |

---

## 📊 Fuentes de datos

| Dataset | Fuente | Años |
|---|---|---|
| Valor de referencia por manzana | UAECD / IDECA | 2020–2026 |
| Localidades de Bogotá | Secretaría Distrital de Planeación | 2023 |
| Sectores / Barrios | DANE | 2023 |
| Microterritorios rurales | Secretaría Distrital | 2025 |

> ⚠️ Los archivos de datos no se incluyen en este repositorio por su tamaño.
> Consulta `data/README.md` para instrucciones de acceso mediante DVC.

---

## 🚀 Progreso del proyecto

| Fase | Estado | Descripción |
|---|---|---|
| ETL y base de datos | ✅ Completo | Carga de 7 años en PostGIS, joins espaciales |
| Exploración EDA | 🔄 En progreso | |
| Series de tiempo | ⏳ Pendiente | |
| Modelos predictivos | ⏳ Pendiente | |
| Expansión urbana | ⏳ Pendiente | |
| Dashboard Power BI | ⏳ Pendiente | |

---

## ⚙️ Instalación

```bash
git clone https://github.com/kenpama28-commits/colombia-mercado-inmobiliario_v2.git
cd colombia-mercado-inmobiliario_v2
pip install -r requirements.txt
```

---

## 👤 Autor

**Kevin Palacio**
[GitHub](https://github.com/kenpama28-commits)
