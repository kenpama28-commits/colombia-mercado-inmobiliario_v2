# -*- coding: utf-8 -*-
"""
Base de sustento del proyecto — normativa de avalúos catastrales + trazabilidad.

Adaptado de proyecto_SECOP/FASE_0/normativa_pipeline.py (estructura probada:
145 documentos, 6.651 secciones indexadas). Convierte los PDF de docs/base_legal/
a Markdown legible (docs/md/) y los carga en SQLite con FTS5: docs/sustento.db

Uso (desde src/):
    python sustento_pipeline.py                       # procesa todos los PDF
    python sustento_pipeline.py --solo Ley_14_de_1983.pdf
    python sustento_pipeline.py --buscar "avalúo comercial" [--limite 10]
    python sustento_pipeline.py --estado               # qué hay y qué falta

POR QUÉ UNA SOLA BASE
    La norma, la fuente de datos y el método analítico viven en el MISMO índice.
    Una consulta ("valor de referencia") devuelve a la vez qué EXIGE la norma,
    de dónde SALE el dato y por qué se ELIGIÓ el método. Separarlos obliga a
    cruzar a mano justo lo que hay que leer junto para sustentar un avalúo.

DIFERENCIA CON SECOP
    Allá el eje era el expediente de un proceso. Aquí el eje es el PREDIO: la
    tabla `predios` ata cada documento (CTL, certificado catastral, plano) a una
    matrícula inmobiliaria, y `metodos`/`decisiones` registran el sustento
    analítico que un avalúo tiene que poder defender ante un tercero.
"""

import argparse
import re
import sqlite3
import sys
import unicodedata
from datetime import date
from pathlib import Path

for _flujo in (sys.stdout, sys.stderr):
    try:
        _flujo.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

SRC = Path(__file__).resolve().parent
RAIZ = SRC.parent
DOCS = RAIZ / "docs"
BASE_LEGAL = DOCS / "base_legal"       # normativa: qué EXIGE la ley
ESTUDIOS = DOCS / "estudios"           # literatura técnica: cómo SE HACE bien
EJEMPLARES = DOCS / "ejemplares"        # avalúos reales que sirven de plantilla
PREDIOS_DIR = DOCS / "predios"         # un subdirectorio por matrícula inmobiliaria
MD_DIR = DOCS / "md"
DB = DOCS / "sustento.db"
EXTENSIONES = {".pdf", ".docx", ".xlsx", ".xlsm"}

# ---------------------------------------------------------------------------
# Catálogo de normativa de avalúos. `fuente` es la URL OFICIAL: sin ella no se
# puede probar que el PDF local es el texto vigente, y un avalúo se sustenta con
# la norma, no con un archivo suelto en el disco.
# estado: 'vigente' | 'derogada' | 'POR VERIFICAR'  ← nunca asumir vigencia.
# ---------------------------------------------------------------------------
# Los IDs de EVA se verificaron UNO A UNO contra el contenido del PDF: de siete
# supuestos, tres devolvían otra norma con HTTP 200 (i=1449 traía el Decreto 287
# de 1996) y uno un PDF vacío. Ver descargar_normativa.py, que revalida en cada
# descarga. NUNCA añadir aquí una URL sin haber leído lo que devuelve.
EVA = "https://www.funcionpublica.gov.co/eva/gestornormativo/norma.php?i="
IGAC_NORM = "https://www.igac.gov.co/sites/default/files/transparencia/normograma/"
IGAC_LM = "https://www.igac.gov.co/sites/default/files/listadomaestro/"
CATALOGO = {
    # --- Marco general del catastro y del avalúo (descargadas y verificadas) ---
    "Ley_14_de_1983.pdf": (
        "Ley 14 de 1983 — Catastro, avalúo catastral y su formación/actualización",
        "ley", 1983, EVA + "267", "descargada 2026-08-04; vigencia POR VERIFICAR"),
    "Ley_44_de_1990.pdf": (
        "Ley 44 de 1990 — Impuesto predial unificado (base gravable = avalúo catastral)",
        "ley", 1990, EVA + "283", "descargada 2026-08-04; vigencia POR VERIFICAR"),
    "Ley_388_de_1997.pdf": (
        "Ley 388 de 1997 — Desarrollo territorial; avalúos comerciales y "
        "participación en plusvalía (arts. 61 ss., 73 ss.)",
        "ley", 1997, EVA + "339", "descargada 2026-08-04; vigencia POR VERIFICAR"),
    "Decreto_1420_de_1998.pdf": (
        "Decreto 1420 de 1998 — Normas, procedimientos, parámetros y criterios para "
        "los avalúos comerciales (reglamenta Ley 388 arts. 56, 61, 62, 67, 75-87)",
        "decreto", 1998, EVA + "1508", "descargada 2026-08-04; vigencia POR VERIFICAR"),
    "Decreto_1170_de_2015.pdf": (
        "Decreto 1170 de 2015 — DUR del sector de información estadística "
        "(catastro): procedimientos y avalúo catastral",
        "decreto", 2015, EVA + "62870", "descargada 2026-08-04; vigencia POR VERIFICAR"),
    "Ley_1955_de_2019.pdf": (
        "Ley 1955 de 2019 — PND: catastro multipropósito (art. 79) y gestores catastrales",
        "ley", 2019, EVA + "93970", "descargada 2026-08-04; vigencia POR VERIFICAR"),
    "Decreto_148_de_2020.pdf": (
        "Decreto 148 de 2020 — Reglamenta los arts. 79-82 de la Ley 1955 y modifica "
        "el Decreto 1170 (catastro multipropósito). CALENDARIO: el avalúo catastral "
        "rige para efectos fiscales desde el 1 de enero del año siguiente",
        "decreto", 2020, EVA + "105952", "descargada 2026-08-04; vigencia POR VERIFICAR"),
    # --- Metodología del avalúo (IGAC) ---
    "Resolucion_IGAC_1137_de_2024.pdf": (
        "Resolución IGAC 1137 de 2024 — Criterios, parámetros y metodología para "
        "avalúos comerciales en compra por oferta voluntaria (art. 62 Ley 2294 de 2023). "
        "OJO: su ámbito es la oferta voluntaria, NO todo avalúo comercial",
        "resolucion", 2024, IGAC_NORM + "RESOLUCION%201137%20DE%202024.pdf",
        "PDF ESCANEADO: requiere --ocr para ser buscable"),
    "IGAC_PC-VAL-03_Procedimiento_Avaluos_Comerciales.pdf": (
        "IGAC PC-VAL-03 v3 — Procedimiento de avalúos comerciales (vigente 21/08/2025)",
        "referencia_tecnica", 2025, IGAC_LM + "PC-VAL-03%20V3%20Avaluos%20Comerciales.pdf",
        "descargada 2026-08-04"),
    # --- Pendientes de localizar en fuente oficial ---
    "Resolucion_IGAC_1939_de_2025.pdf": (
        "Resolución IGAC 1939 de 2025 — Metodologías de actualización masiva de "
        "valores de predios. CALENDARIO: afecta directamente el valor de referencia",
        "resolucion", 2025, "", "FALTA: localizar URL oficial"),
    "Decreto_555_de_2021_POT.pdf": (
        "Decreto Distrital 555 de 2021 — POT de Bogotá (tratamientos urbanísticos, "
        "clasificación de suelo, edificabilidad → método residual)",
        "decreto_distrital", 2021, "", "FALTA: localizar URL oficial"),
    "Decreto_352_de_2002.pdf": (
        "Decreto Distrital 352 de 2002 — Estatuto Tributario Distrital (predial)",
        "decreto_distrital", 2002, "", "FALTA: localizar URL oficial"),
    "UAECD_Resolucion_valores_referencia.pdf": (
        "UAECD — Resolución anual de valores de referencia por manzana (fuente "
        "directa del dataset principal). CALENDARIO: se expide cada año y redefine "
        "el V_REF de toda la ciudad",
        "resolucion", None, "", "FALTA: descargar la del año que se cite"),
    "Ley_1579_de_2012.pdf": (
        "Ley 1579 de 2012 — Estatuto de registro de instrumentos públicos "
        "(fundamento del certificado de tradición)",
        "ley", 2012, "", "FALTA: localizar URL oficial"),
    "Ley_1673_de_2013.pdf": (
        "Ley 1673 de 2013 — Regula la ACTIVIDAD DEL AVALUADOR: Registro Abierto "
        "de Avaluadores (RAA), autorregulación y vigilancia de la SIC. Define "
        "quién puede firmar un avalúo con validez",
        "ley", 2013, EVA + "53881", "descargada 2026-08-04; vigencia POR VERIFICAR"),

    # --- Literatura técnica: cómo se hace, no qué exige la ley ---
    "otc_modelos_econometricos.pdf": (
        "UAECD · Observatorio Técnico Catastral — Documento metodológico de "
        "modelos econométricos (convenio Cartagena). Es LA metodología con que "
        "la UAECD estima valores: muestra representativa + modelo econométrico "
        "sobre atributos físicos y valores de mercado",
        "estudio_metodologico", 2023,
        "https://www.catastrobogota.gov.co/sites/default/files/archivos/normas/"
        "20230106_MODELOS_ECONOMETRICOS_CARTAGENA.pdf",
        "descargado 2026-08-04"),
    "otc_reporte_catastral_2023.pdf": (
        "UAECD + Fincaraíz — Reporte Catastral e Inmobiliario de Bogotá 2023. "
        "Cruza catastro con OFERTA de mercado: es el puente hacia los comparables",
        "estudio_mercado", 2023,
        "https://www.catastrobogota.gov.co/sites/default/files/archivos/"
        "FR%20-%20Informe%20Catastro%202023%202.pdf",
        "descargado 2026-08-04"),
    "otc_construccion_vivienda_2009_2020.pdf": (
        "UAECD · OTC — Comportamiento de la construcción de vivienda nueva en "
        "Bogotá 2009-2020",
        "estudio_mercado", 2021,
        "https://www.catastrobogota.gov.co/sites/default/files/"
        "20210430_Construccion_vivienda_%202009-2020_vf_publicaciones.pdf",
        "descargado 2026-08-04"),
    "otc_area_construida_bogota.pdf": (
        "UAECD · OTC — Estudio del área construida en Bogotá",
        "estudio_mercado", 2021,
        "https://www.catastrobogota.gov.co/sites/default/files/"
        "20210430_Estudio_Area%20construida%20en%20Bogota%CC%81_vf_publicacion_0.pdf",
        "descargado 2026-08-04"),
    "uaecd_ficha_metodologica_ivpub.pdf": (
        "UAECD — Ficha metodológica de los Indicadores de Valor Predial Urbano "
        "de Bogotá (IVPUB). Operación estadística oficial del valor predial",
        "estudio_metodologico", None, "", "aportada por el usuario 2026-08-04"),
    "guia_normas_tecnicas_sectoriales_avaluos.pdf": (
        "Noguera Camacho, G. — Guía para entender las Normas Técnicas "
        "Sectoriales de avalúos (USN AVSA / ICONTEC / RNA). Explica la pirámide "
        "normativa: NIV-IVSC internacional → NTS colombianas",
        "norma_tecnica", None, "", "aportada por el usuario 2026-08-04"),

    # --- Literatura académica: precios hedónicos en Bogotá ---
    "cede_2007_transmilenio_precios_hedonicos.pdf": (
        "Mendieta, J.C. & Perdomo, J.A. (2007) — Modelo de precios hedónico "
        "ESPACIAL para el impacto de TransMilenio sobre el valor de la "
        "propiedad en Bogotá. CEDE, Uniandes. Elasticidades proximidad-precio: "
        "-0,36 / -0,55 / -1,13 (fases 1/2/3). SUSTENTO ACADÉMICO de la variable "
        "dist_tm_m del modelo del proyecto",
        "paper_academico", 2007, "", "aportado por el usuario 2026-08-04"),
    "tesis_un_2023_hedonicos_espaciales_bogota.pdf": (
        "Camargo Rincón, D.H. (2023) — Estimación de precios hedónicos en "
        "viviendas usadas en Bogotá usando modelos espaciales de efectos "
        "mixtos. Tesis, Depto. Estadística, Universidad Nacional. 7.850 "
        "observaciones por WEB SCRAPING de portales: método documentado para "
        "conseguir comparables",
        "tesis", 2023, "", "aportada por el usuario 2026-08-04"),
    "paper_hedonic_prices_bogota.pdf": (
        "Estimating Hedonic Prices for Residential and Commercial Property at "
        "Bogotá City",
        "paper_academico", None, "", "aportado por el usuario 2026-08-04; "
        "PDF sin texto extraíble: requiere --ocr"),
    "tesis_ud_2020_avaluo_niif_red_hospitalaria.pdf": (
        "Vásquez López, I.E. (2020) — Apoyo técnico en la elaboración de avalúo "
        "en normas NIIF de la red hospitalaria de la Subred Integrada de "
        "Servicios de Salud. Ing. Catastral y Geodesia, Universidad Distrital",
        "tesis", 2020, "", "aportada por el usuario 2026-08-04"),

    # --- Ejemplares: avalúos reales que sirven de plantilla ---
    "avaluo_comercial_2017_chapinero_kr16_90-63.pdf": (
        "Borrero Ochoa y Asociados (2017) — Avalúo comercial KR 16 No. 90-63, "
        "El Chicó, Chapinero. 752,90 m². Aplica 4 métodos y CONCLUYE POR "
        "RESIDUAL: $6.510.000/m² = $4.901.379.000. Declara NTS S 03, NTS S 04 y "
        "NTS I 01 como marco. EJEMPLAR DE REFERENCIA del entregable",
        "ejemplar_avaluo", 2017, "", "aportado por el usuario 2026-08-04"),
}

LIGADURAS = {"ﬁ": "fi", "ﬂ": "fl", "ﬀ": "ff", "ﬃ": "ffi", "ﬄ": "ffl"}
RE_ENCABEZADO = re.compile(
    r"^\s*(Departamento Administrativo de la Función Pública\s*$"
    r"|.{0,120}EVA - Gestor Normativo\s*$)", re.MULTILINE)
RE_ARTICULO = re.compile(
    r"^\s*ART[ÍI]CULO\s+(\d+(?:\.\d+)*)(?-i:([A-Z]))?\s*[oOº°]?\s*[.\-–]?\s*(.*)$",
    re.IGNORECASE)
RE_ESTRUCTURA = re.compile(
    r"^\s*((?:LIBRO|PARTE|T[ÍI]TULO|CAP[ÍI]TULO|SECCI[ÓO]N)\s+[\dIVXLC]+.*)\s*$")
RE_ART_REF = re.compile(r"[Aa]rt[íi]culo\s+(\d+(?:\.\d+)*)")
VENTANA_ARTICULO = 4          # ver _es_articulo_real


def _sin_tildes(s: str) -> str:
    return unicodedata.normalize("NFKD", s.lower()).encode("ascii", "ignore").decode()


def _clave(num: str) -> tuple:
    return tuple(int(p) for p in num.split("."))


def _es_articulo_real(clave, letra, titulo, ultima, cita_ref) -> bool:
    """¿Abre un artículo REAL o es texto citado de otra norma?

    Las normas modificatorias transcriben el artículo que reforman; sin este
    filtro ese texto abre una sección falsa y deja vacío el artículo modificador.
    """
    if ultima is None:
        return True
    if titulo[:1].islower():
        return False
    if cita_ref is not None and clave == cita_ref:
        return False
    if len(clave) == 1 and len(ultima) == 1:
        if letra and clave[0] == ultima[0]:
            return True
        return ultima[0] < clave[0] <= ultima[0] + VENTANA_ARTICULO
    return True


def limpiar(texto: str) -> str:
    for lig, rep in LIGADURAS.items():
        texto = texto.replace(lig, rep)
    texto = RE_ENCABEZADO.sub("", texto)
    return re.sub(r"\n{3,}", "\n\n", texto).strip()


def _motor_ocr():
    """Primer motor OCR disponible: (nombre, fn(png_bytes) -> texto), o None.

    Se prefiere RapidOCR porque se instala solo con pip; pytesseract exige el
    binario Tesseract en el sistema.
    """
    try:
        from rapidocr_onnxruntime import RapidOCR
        motor = RapidOCR()

        def _texto(png: bytes) -> str:
            res, _ = motor(png)
            return "\n".join(linea[1] for linea in res) if res else ""
        return "RapidOCR", _texto
    except Exception:
        pass
    try:
        import io
        import pytesseract
        from PIL import Image

        def _texto(png: bytes) -> str:
            return pytesseract.image_to_string(Image.open(io.BytesIO(png)), lang="spa")
        return "pytesseract", _texto
    except Exception:
        return None


def _ocr_paginas(pdf: Path, paginas: list[str]) -> list[str]:
    """OCR solo a las páginas SIN texto. Las que ya lo tenían quedan intactas
    (un PDF puede ser mixto texto+imagen).

    Caso real: la Resolución IGAC 1137 de 2024 —la norma metodológica de avalúos—
    son 11 páginas escaneadas con cero texto extraíble. Sin OCR entra al índice
    muda: la fila existe y ninguna búsqueda la devuelve.
    """
    motor = _motor_ocr()
    if motor is None:
        print(f"  OCR pedido pero sin motor: pip install rapidocr-onnxruntime pymupdf. "
              f"{pdf.name} queda sin OCR.")
        return paginas
    nombre, texto_de = motor
    import fitz
    doc = fitz.open(pdf)
    salida, hechas = list(paginas), 0
    for i, pag in enumerate(doc):
        if i < len(salida) and len(salida[i].strip()) >= 10:
            continue
        png = pag.get_pixmap(dpi=300).tobytes("png")   # en memoria: sin tmpfile
        txt = limpiar(texto_de(png) or "")
        if i < len(salida):
            salida[i] = txt
        else:
            salida.append(txt)
        hechas += 1
    doc.close()
    print(f"  OCR ({nombre}): {hechas} página(s) de {pdf.name}")
    return salida


def extraer_paginas(archivo: Path, ocr: bool = False) -> list[str]:
    ext = archivo.suffix.lower()
    if ext == ".docx":
        import zipfile
        from xml.etree import ElementTree as ET
        W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
        with zipfile.ZipFile(archivo) as z:
            raiz = ET.fromstring(z.read("word/document.xml"))
        parrafos = ["".join(t.text or "" for t in p.iter(f"{W}t"))
                    for p in raiz.iter(f"{W}p")]
        return [limpiar("\n".join(p for p in parrafos if p.strip()))]
    if ext in (".xlsx", ".xlsm"):
        from openpyxl import load_workbook
        libro = load_workbook(str(archivo), read_only=True, data_only=True)
        hojas = []
        for hoja in libro.worksheets:
            filas = [" | ".join(str(c).strip() for c in fila if c is not None and str(c).strip())
                     for fila in hoja.iter_rows(values_only=True)]
            hojas.append(f"[Hoja: {hoja.title}]\n" + "\n".join(f for f in filas if f))
        libro.close()
        return [limpiar(h) for h in hojas]
    from pypdf import PdfReader
    paginas = [limpiar(p.extract_text() or "") for p in PdfReader(str(archivo)).pages]
    if ocr and any(len(p.strip()) < 10 for p in paginas):
        paginas = _ocr_paginas(archivo, paginas)
    return paginas


def secciones_por_articulo(paginas: list[str]) -> list[dict]:
    secciones, actual, ultima, cita_ref = [], {"referencia": "Preámbulo", "titulo": "", "lineas": []}, None, None
    for linea in "\n".join(paginas).splitlines():
        m_art = RE_ARTICULO.match(linea)
        m_est = RE_ESTRUCTURA.match(linea) if not m_art else None
        if m_art:
            clave, letra = _clave(m_art.group(1)), (m_art.group(2) or "").strip()
            titulo = m_art.group(3).strip()
            if _es_articulo_real(clave, letra, titulo, ultima, cita_ref):
                secciones.append(actual)
                actual = {"referencia": f"Artículo {m_art.group(1)}{letra}",
                          "titulo": titulo, "lineas": []}
                ultima = clave
                m = RE_ART_REF.search(titulo)
                cita_ref = _clave(m.group(1)) if m else None
            else:
                actual["lineas"].append(linea)
                if cita_ref is not None and clave == cita_ref:
                    cita_ref = None
        elif m_est:
            secciones.append(actual)
            actual = {"referencia": m_est.group(1).strip(), "titulo": "",
                      "lineas": [], "estructural": True}
            cita_ref = None
        else:
            actual["lineas"].append(linea)
    secciones.append(actual)
    return [s for s in secciones if s["lineas"] or s["referencia"] != "Preámbulo"]


def secciones_por_pagina(paginas: list[str]) -> list[dict]:
    return [{"referencia": f"Página {i}", "titulo": "", "lineas": p.splitlines()}
            for i, p in enumerate(paginas, 1) if p.strip()]


def nombre_md(nombre: str) -> str:
    base = unicodedata.normalize("NFKD", Path(nombre).stem.lower())
    base = base.encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", base).strip("_") + ".md"


def a_markdown(titulo, tipo, anio, fuente, estado, pdf, secciones) -> str:
    partes = ["---", f'titulo: "{titulo}"', f"tipo: {tipo}", f"anio: {anio}",
              f'fuente: "{fuente or "local"}"', f'estado: "{estado}"',
              f'pdf_origen: "{pdf}"', f"procesado: {date.today().isoformat()}",
              "---", "", f"# {titulo}", ""]
    for s in secciones:
        cuerpo = "\n".join(s["lineas"]).strip()
        if s.get("estructural") or s["referencia"] == "Preámbulo":
            partes.append(f"## {s['referencia']}\n")
        else:
            tit = f" — {s['titulo']}" if s["titulo"] else ""
            partes.append(f"### {s['referencia']}{tit}\n")
        if cuerpo:
            partes.append(cuerpo + "\n")
    return "\n".join(partes)


# ---------------------------------------------------------------------------
# Esquema
# ---------------------------------------------------------------------------
def abrir_db() -> sqlite3.Connection:
    DOCS.mkdir(exist_ok=True)
    con = sqlite3.connect(DB)
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript("""
    CREATE TABLE IF NOT EXISTS documentos(
        id INTEGER PRIMARY KEY,
        titulo TEXT NOT NULL, tipo TEXT NOT NULL, anio INTEGER,
        archivo_pdf TEXT NOT NULL UNIQUE, archivo_md TEXT,
        fuente_url TEXT, estado TEXT, paginas INTEGER, fecha_procesado TEXT,
        matricula TEXT);
    CREATE TABLE IF NOT EXISTS secciones(
        id INTEGER PRIMARY KEY,
        documento_id INTEGER NOT NULL REFERENCES documentos(id) ON DELETE CASCADE,
        orden INTEGER, referencia TEXT, titulo TEXT, texto TEXT);
    CREATE VIRTUAL TABLE IF NOT EXISTS secciones_fts USING fts5(
        documento, referencia, titulo, texto, documento_id UNINDEXED);

    -- Eje del proyecto: el PREDIO. Un avalúo se defiende predio por predio.
    CREATE TABLE IF NOT EXISTS predios(
        matricula TEXT PRIMARY KEY,           -- EJEMPLO
        chip TEXT, lote_catastral TEXT, manzana TEXT, sector_catastral TEXT,
        direccion TEXT, localidad TEXT, area_terreno_m2 REAL, area_construida_m2 REAL,
        uso_predominante TEXT, fuente_area TEXT,   -- de DÓNDE salió el área
        observaciones TEXT, fecha_registro TEXT);

    -- Cada dato del expediente con SU origen. Sin esto, un número del informe no
    -- se puede defender: hay que poder decir de qué documento o API salió.
    CREATE TABLE IF NOT EXISTS procedencia(
        id INTEGER PRIMARY KEY,
        matricula TEXT, campo TEXT, valor TEXT,
        origen_tipo TEXT,     -- documento | api | derivado | supuesto
        origen TEXT,          -- capa/endpoint o nombre del documento
        detalle TEXT,         -- consulta exacta, artículo, página
        fecha_consulta TEXT);
    CREATE INDEX IF NOT EXISTS ix_proc_mat ON procedencia(matricula);

    -- Lo que FALTA y cómo conseguirlo. Un avalúo con vacíos se firma igual;
    -- la diferencia está en si los vacíos están declarados o escondidos.
    CREATE TABLE IF NOT EXISTS documentos_faltantes(
        id INTEGER PRIMARY KEY,
        matricula TEXT, documento TEXT, para_que TEXT,
        criticidad TEXT,      -- bloqueante | importante | deseable
        como_obtenerlo TEXT, enlace TEXT, estado TEXT);

    -- Calendarios de actualización: cuándo cambia cada fuente. Una actualización
    -- catastral o una nueva resolución de valores CAMBIA el valor del lote, así
    -- que un avalúo sin fecha de corte de sus insumos no es reproducible.
    CREATE TABLE IF NOT EXISTS calendario_actualizacion(
        id INTEGER PRIMARY KEY,
        fuente TEXT, periodicidad TEXT, momento TEXT,
        efecto_en_avaluo TEXT, norma TEXT, ultima_verificacion TEXT);

    -- Validación de datos: qué se comprobó, contra qué y con qué resultado.
    CREATE TABLE IF NOT EXISTS validaciones(
        id INTEGER PRIMARY KEY,
        ambito TEXT,          -- dato | metodo | estadistico | juridico
        objeto TEXT,          -- qué se valida (tabla, campo, modelo, predio)
        regla TEXT,           -- qué se exigió
        resultado TEXT,       -- OK | FALLA | PARCIAL
        evidencia TEXT,       -- cifra/consulta que lo prueba
        norma_o_referencia TEXT,
        fecha TEXT);
    CREATE INDEX IF NOT EXISTS ix_val_objeto ON validaciones(objeto);
    """)
    con.commit()
    return con


def cargar(con, clave, titulo, tipo, anio, fuente, estado, md_rel, n_pag,
           secciones, matricula=None) -> None:
    fila = con.execute("SELECT id FROM documentos WHERE archivo_pdf=?", (clave,)).fetchone()
    if fila:
        doc_id = fila[0]
        con.execute("DELETE FROM secciones WHERE documento_id=?", (doc_id,))
        con.execute("DELETE FROM secciones_fts WHERE documento_id=?", (doc_id,))
        con.execute("""UPDATE documentos SET titulo=?,tipo=?,anio=?,archivo_md=?,
                       fuente_url=?,estado=?,paginas=?,fecha_procesado=?,matricula=?
                       WHERE id=?""",
                    (titulo, tipo, anio, md_rel, fuente, estado, n_pag,
                     date.today().isoformat(), matricula, doc_id))
    else:
        doc_id = con.execute("""INSERT INTO documentos(titulo,tipo,anio,archivo_pdf,
                archivo_md,fuente_url,estado,paginas,fecha_procesado,matricula)
                VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (titulo, tipo, anio, clave, md_rel, fuente, estado, n_pag,
                 date.today().isoformat(), matricula)).lastrowid
    for orden, s in enumerate(secciones):
        texto = "\n".join(s["lineas"]).strip()
        con.execute("INSERT INTO secciones(documento_id,orden,referencia,titulo,texto)"
                    " VALUES(?,?,?,?,?)", (doc_id, orden, s["referencia"], s["titulo"], texto))
        con.execute("INSERT INTO secciones_fts(documento,referencia,titulo,texto,documento_id)"
                    " VALUES(?,?,?,?,?)", (titulo, s["referencia"], s["titulo"], texto, doc_id))
    con.commit()


def procesar(archivo: Path, con, matricula: str = None, ocr: bool = False) -> str:
    paginas = extraer_paginas(archivo, ocr=ocr)
    if matricula:
        titulo = f"[{matricula}] {archivo.stem}"
        tipo, anio, fuente, estado = "documento_predio", None, "", "aportado"
    else:
        titulo, tipo, anio, fuente, estado = CATALOGO.get(
            archivo.name, (archivo.stem.replace("_", " "), "otro", None, "", "POR VERIFICAR"))
    secciones = (secciones_por_articulo(paginas)
                 if tipo in ("ley", "decreto", "decreto_distrital", "resolucion")
                 else secciones_por_pagina(paginas))
    MD_DIR.mkdir(parents=True, exist_ok=True)
    md = MD_DIR / nombre_md((f"{matricula}_" if matricula else "") + archivo.name)
    md.write_text(a_markdown(titulo, tipo, anio, fuente, estado, archivo.name, secciones),
                  encoding="utf-8")
    clave = f"predios/{matricula}/{archivo.name}" if matricula else archivo.name
    cargar(con, clave, titulo, tipo, anio, fuente, estado, f"md/{md.name}",
           len(paginas), secciones, matricula)
    # Un documento sin secciones entra MUDO al índice: la fila existe pero ninguna
    # búsqueda lo devuelve. Decir "OK" ahí es mentir sobre la cobertura.
    if not secciones:
        return (f"AVISO  {archivo.name}: {len(paginas)} págs → 0 secciones — sin texto "
                f"extraíble (escaneado). Indexado pero VACÍO: requiere OCR.")
    n_art = sum(1 for s in secciones if s["referencia"].startswith("Artículo"))
    extra = f" ({n_art} artículos)" if n_art else ""
    return f"OK  {archivo.name}: {len(paginas)} págs → {len(secciones)} secciones{extra}"


def buscar(con, consulta: str, limite: int) -> None:
    sql = """SELECT d.titulo, d.tipo, d.estado, f.referencia,
                    snippet(secciones_fts,3,'>>','<<',' … ',14)
             FROM secciones_fts f JOIN documentos d ON d.id=f.documento_id
             WHERE f.secciones_fts MATCH ? ORDER BY rank LIMIT ?"""
    filas = con.execute(sql, (consulta, limite)).fetchall()
    if not filas:
        print(f"Sin resultados para: {consulta}")
        return
    for tit, tipo, estado, ref, frag in filas:
        marca = f" [{estado}]" if estado and estado.startswith("POR") else ""
        print(f"[{tipo}]{marca} {tit} — {ref}")
        print(f"    {' '.join((frag or '').split())}\n")


def estado(con) -> None:
    """Qué hay en la base y qué falta por descargar. Sin esto es imposible saber
    si una cita quedó sin respaldo."""
    print(f"Base: {DB}")
    n_doc, n_sec = con.execute(
        "SELECT (SELECT COUNT(*) FROM documentos),(SELECT COUNT(*) FROM secciones)").fetchone()
    print(f"  {n_doc} documentos · {n_sec} secciones indexadas\n")
    presentes = {r[0] for r in con.execute("SELECT archivo_pdf FROM documentos")}
    print("── Normativa del catálogo ─────────────────────────────")
    for pdf, (titulo, *_ , est) in sorted(CATALOGO.items()):
        marca = "✓" if pdf in presentes else "·"
        falta = "" if pdf in presentes else "  ← FALTA descargar"
        print(f"  {marca} {titulo[:66]}{falta}")
        if pdf in presentes and est.startswith("POR VERIFICAR"):
            print(f"      ⚠ {est}")
    print("\n── Predios con documentos ─────────────────────────────")
    for m, n in con.execute("""SELECT matricula, COUNT(*) FROM documentos
                               WHERE matricula IS NOT NULL GROUP BY matricula"""):
        print(f"  {m}: {n} documento(s)")


def main() -> None:
    ap = argparse.ArgumentParser(description="Normativa y documentos → Markdown + SQLite FTS5")
    ap.add_argument("--solo", help="procesar únicamente este archivo de docs/base_legal/")
    ap.add_argument("--buscar", help="consulta FTS5 sobre sustento.db")
    ap.add_argument("--limite", type=int, default=10)
    ap.add_argument("--predio", help="matrícula: ingesta docs/predios/<matricula>/*")
    ap.add_argument("--estado", action="store_true", help="qué hay indexado y qué falta")
    ap.add_argument("--ocr", action="store_true",
                    help="aplica OCR a las páginas escaneadas sin texto "
                         "(requiere rapidocr-onnxruntime + pymupdf)")
    args = ap.parse_args()

    con = abrir_db()
    if args.estado:
        return estado(con)
    if args.buscar:
        return buscar(con, args.buscar, args.limite)
    if args.predio:
        carpeta = PREDIOS_DIR / args.predio
        carpeta.mkdir(parents=True, exist_ok=True)
        archivos = sorted(p for p in carpeta.rglob("*")
                          if p.is_file() and p.suffix.lower() in EXTENSIONES)
        if not archivos:
            print(f"Sin documentos en {carpeta}. Copia ahí el CTL, el certificado "
                  f"catastral y los planos, y vuelve a ejecutar.")
            return
        for a in archivos:
            try:
                print(procesar(a, con, args.predio, ocr=args.ocr))
            except Exception as exc:
                print(f"ERROR {a.name}: {exc}")
        return
    for carpeta in (BASE_LEGAL, ESTUDIOS, EJEMPLARES):
        carpeta.mkdir(parents=True, exist_ok=True)
    if args.solo:
        archivos = [c / args.solo for c in (BASE_LEGAL, ESTUDIOS, EJEMPLARES)
                    if (c / args.solo).exists()] or [BASE_LEGAL / args.solo]
    else:
        archivos = sorted(
            (p for c in (BASE_LEGAL, ESTUDIOS, EJEMPLARES) for p in c.iterdir()
             if p.suffix.lower() in EXTENSIONES), key=lambda x: x.name)
    if not archivos:
        print(f"Sin documentos en {BASE_LEGAL}.")
        print("Descarga primero la normativa: python sustento_pipeline.py --estado")
        return
    for a in archivos:
        if not a.exists():
            print(f"NO EXISTE {a}")
            continue
        try:
            print(procesar(a, con, ocr=args.ocr))
        except Exception as exc:
            print(f"ERROR {a.name}: {exc}")
    estado(con)


if __name__ == "__main__":
    main()
