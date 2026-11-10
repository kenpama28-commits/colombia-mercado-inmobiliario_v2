# -*- coding: utf-8 -*-
"""
Descarga la normativa de avalúos desde su fuente OFICIAL y VERIFICA el contenido.

Por qué verifica: los identificadores del Gestor Normativo (EVA) no son
adivinables. En la primera pasada, 3 de 7 IDs supuestos devolvieron otra norma
(i=1449 traía el Decreto 287 de 1996, no el Decreto 1420 de 1998) y uno devolvió
un PDF vacío — con HTTP 200 en todos los casos. Un archivo que se llama
`Decreto_1420_de_1998.pdf` pero contiene otra cosa envenena toda la base de
sustento en silencio, así que aquí no se guarda nada sin comprobar que la primera
página nombra la norma esperada.

    python descargar_normativa.py              # descarga lo que falte
    python descargar_normativa.py --forzar     # vuelve a bajar todo
    python descargar_normativa.py --verificar  # solo revisa lo ya descargado
"""

import argparse
import re
import sys
import urllib.request
from pathlib import Path

for _f in (sys.stdout, sys.stderr):
    try:
        _f.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

DESTINO = Path(__file__).resolve().parent.parent / "docs" / "base_legal"
EVA = "https://www.funcionpublica.gov.co/eva/gestornormativo/norma_pdf.php?i="

# Centinela para PDF escaneados: no hay texto contra el cual verificar, así que
# solo se comprueba que sea un PDF legible con páginas. Queda marcado para OCR.
ESCANEADA = None

# (archivo, url, patrón que DEBE aparecer en la primera página | ESCANEADA)
# Los IDs de EVA fueron verificados uno a uno contra el contenido: no confiar en
# el número sin la comprobación.
FUENTES = [
    ("Ley_14_de_1983.pdf", EVA + "267", r"Ley\s+14\s+de\s+1983"),
    ("Ley_44_de_1990.pdf", EVA + "283", r"Ley\s+44\s+de\s+1990"),
    ("Ley_388_de_1997.pdf", EVA + "339", r"Ley\s+388\s+de\s+1997"),
    ("Decreto_1420_de_1998.pdf", EVA + "1508", r"Decreto\s+1420\s+de\s+1998"),
    ("Decreto_1170_de_2015.pdf", EVA + "62870", r"Decreto\s+1170\s+de\s+2015"),
    ("Ley_1955_de_2019.pdf", EVA + "93970", r"Ley\s+1955\s+de\s+2019"),
    ("Decreto_148_de_2020.pdf", EVA + "105952", r"Decreto\s+148\s+de\s+2020"),
    # ESCANEADA: 11 páginas de imagen, cero texto extraíble. No se puede verificar
    # por contenido; se acepta por tamaño y se marca para OCR. Es la norma
    # metodológica de avalúos, así que dejarla fuera no era opción.
    ("Resolucion_IGAC_1137_de_2024.pdf",
     "https://www.igac.gov.co/sites/default/files/transparencia/normograma/"
     "RESOLUCION%201137%20DE%202024.pdf",
     ESCANEADA),
    ("IGAC_PC-VAL-03_Procedimiento_Avaluos_Comerciales.pdf",
     "https://www.igac.gov.co/sites/default/files/listadomaestro/"
     "PC-VAL-03%20V3%20Avaluos%20Comerciales.pdf",
     r"PC-VAL-03|Aval[úu]os\s+Comerciales"),
]

UA = {"User-Agent": "Mozilla/5.0 (proyecto-catastro; sustento de avaluos)"}


def primera_pagina(pdf: Path) -> str:
    from pypdf import PdfReader
    try:
        texto = PdfReader(str(pdf)).pages[0].extract_text() or ""
    except Exception as exc:
        return f"[ILEGIBLE: {exc}]"
    return " ".join(texto.split())


def verificar(pdf: Path, patron: str | None) -> tuple[bool, str]:
    if not pdf.exists():
        return False, "no descargado"
    if pdf.stat().st_size < 5000:
        return False, f"tamaño sospechoso ({pdf.stat().st_size} bytes)"
    cabeza = primera_pagina(pdf)
    if cabeza.startswith("[ILEGIBLE"):
        return False, cabeza
    if patron is ESCANEADA:
        from pypdf import PdfReader
        n = len(PdfReader(str(pdf)).pages)
        return True, f"{n} págs ESCANEADAS — sin texto; indexar con --ocr"
    if not re.search(patron, cabeza, re.IGNORECASE):
        hallado = re.search(r"(Ley|Decreto|Resoluci[óo]n|Concepto)\s+N?[oº°]?\.?\s*"
                            r"[\d\-]+\s+de\s+\d{4}", cabeza, re.IGNORECASE)
        return False, f"contiene OTRA norma: {hallado.group(0) if hallado else cabeza[:70]}"
    from pypdf import PdfReader
    return True, f"{len(PdfReader(str(pdf)).pages)} págs"


def descargar(nombre: str, url: str, patron: str, forzar: bool) -> str:
    DESTINO.mkdir(parents=True, exist_ok=True)
    pdf = DESTINO / nombre
    if pdf.exists() and not forzar:
        ok, detalle = verificar(pdf, patron)
        return f"{'OK  ' if ok else 'FALLA'} {nombre}: ya estaba — {detalle}"
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=90) as r:
            datos = r.read()
    except Exception as exc:
        return f"FALLA {nombre}: descarga — {exc}"
    # A un archivo temporal primero: si la verificación falla, no queda un PDF
    # equivocado con nombre de norma correcta esperando a que alguien lo cite.
    tmp = pdf.with_suffix(".tmp")
    tmp.write_bytes(datos)
    ok, detalle = verificar(tmp, patron)
    if not ok:
        tmp.unlink(missing_ok=True)
        return f"FALLA {nombre}: {detalle} — NO se guarda"
    tmp.replace(pdf)
    return f"OK   {nombre}: {detalle} ({len(datos) // 1024} KB)"


def main() -> None:
    ap = argparse.ArgumentParser(description="Descarga y verifica la normativa de avalúos")
    ap.add_argument("--forzar", action="store_true", help="re-descarga aunque exista")
    ap.add_argument("--verificar", action="store_true", help="solo verifica lo descargado")
    a = ap.parse_args()

    if a.verificar:
        for nombre, _, patron in FUENTES:
            ok, detalle = verificar(DESTINO / nombre, patron)
            print(f"{'OK  ' if ok else 'FALLA'} {nombre}: {detalle}")
        return

    resultados = [descargar(n, u, p, a.forzar) for n, u, p in FUENTES]
    for r in resultados:
        print(r)
    fallas = sum(1 for r in resultados if r.startswith("FALLA"))
    print(f"\n{len(resultados) - fallas}/{len(resultados)} normas verificadas en {DESTINO}")
    if fallas:
        print(f"{fallas} pendiente(s): buscar la URL oficial correcta antes de citarlas.")


if __name__ == "__main__":
    main()
