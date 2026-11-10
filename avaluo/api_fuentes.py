# -*- coding: utf-8 -*-
"""
Clientes de las APIs públicas de datos. Endpoints verificados en vivo 2026-08-03.

Sustituye la descarga manual de shapefiles: los mismos datos que hoy están en
data/external/ se consultan aquí en vivo y con trazabilidad de fecha.

    python api_fuentes.py --predio "KR 34" "10 58"     # dirección → lote → valores
    python api_fuentes.py --serie 004201027            # serie de valor por manzana
    python api_fuentes.py --buscar-bogota catastro     # catálogo CKAN

Las trampas de cada fuente están documentadas en catalogo_sustento.FUENTES;
lo que aquí se implementa ya las esquiva (ANO en epoch ms, área en grados²,
dirección partida en dos campos).
"""

import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone

# La consola de Windows viene en cp1252 y revienta con «⚠» o «²».
for _flujo in (sys.stdout, sys.stderr):
    try:
        _flujo.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

IDECA = ("https://serviciosgis.catastrobogota.gov.co/arcgis/rest/services/"
         "catastro/{capa}/MapServer/0/query")
CKAN = "https://datosabiertos.bogota.gov.co/api/3/action/{accion}"
SODA = "https://www.datos.gov.co/resource/{dataset}.json"
TIMEOUT = 60

# EPSG:9377 (MAGNA-SIRGAS / Origen Nacional) es el CRS oficial de Colombia y el
# que hay que pedir para medir: con 4326 el área sale en grados² y con 3857
# (Web Mercator) sale inflada. Verificado sobre el lote 004201027012:
# 9377 → 439,5 m² · 3116 → 440,0 m² · 3857 → 445,9 m².
CRS_METRICO = "9377"


def _get(url: str, params: dict) -> dict:
    req = urllib.request.Request(url + "?" + urllib.parse.urlencode(params),
                                 headers={"User-Agent": "proyecto-catastro/1.0"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.load(r)


def consultar_ideca(capa: str, where: str = "1=1", campos: str = "*",
                    geometria: bool = False, sr: str = "4326",
                    punto: tuple[float, float] | None = None,
                    limite: int = 200) -> list[dict]:
    """Consulta una capa de IDECA. `punto` = (lon, lat) para filtro espacial."""
    p = {"where": where, "outFields": campos, "f": "json", "outSR": sr,
         "returnGeometry": str(geometria).lower(), "resultRecordCount": limite}
    if punto:
        p.update({"geometry": f"{punto[0]},{punto[1]}",
                  "geometryType": "esriGeometryPoint", "inSR": "4326",
                  "spatialRel": "esriSpatialRelIntersects"})
    d = _get(IDECA.format(capa=capa), p)
    if "error" in d:
        raise RuntimeError(f"IDECA/{capa}: {d['error'].get('message')}")
    return d.get("features", [])


def geocodificar(via: str, placa: str) -> dict | None:
    """Dirección → lote. La dirección va PARTIDA: PDONVIAL='KR 34', PDOTEXTO='10 58'.

    Buscar la cadena completa en PDOTEXTO devuelve 0 resultados — es el error que
    hace creer que el predio no está en catastro.
    """
    where = f"PDONVIAL='{via}' AND PDOTEXTO LIKE '{placa}%'"
    fs = consultar_ideca("placadomiciliaria", where,
                         "PDOTEXTO,PDOCLOTE,PDONVIAL", geometria=True)
    if not fs:
        return None
    f = fs[0]
    return {"direccion": f"{f['attributes']['PDONVIAL']} {f['attributes']['PDOTEXTO']}".strip(),
            "lote": f["attributes"]["PDOCLOTE"],
            "lon": f["geometry"]["x"], "lat": f["geometry"]["y"]}


def _area_anillo(anillo: list) -> float:
    """Área por fórmula del zapato. El anillo debe venir en un CRS MÉTRICO."""
    return abs(sum(anillo[i][0] * anillo[i + 1][1] - anillo[i + 1][0] * anillo[i][1]
                   for i in range(len(anillo) - 1))) / 2


def area_lote_m2(lote: str) -> float | None:
    """Área del lote en m² reales, calculada sobre la geometría en EPSG:9377.

    NO usar el campo SHAPE.AREA del servicio: viene en las unidades del outSR.
    """
    fs = consultar_ideca("lote", f"LOTCODIGO='{lote}'", "LOTCODIGO",
                         geometria=True, sr=CRS_METRICO)
    if not fs:
        return None
    return _area_anillo(fs[0]["geometry"]["rings"][0])


def serie_valor_referencia(manzana: str) -> list[tuple[int, float]]:
    """[(año, COP/m² de terreno)] para una manzana. ANO llega en epoch ms."""
    fs = consultar_ideca("valorreferencia", f"MANCODIGO='{manzana}'",
                         "MANCODIGO,V_REF,ANO")
    filas = [(datetime.fromtimestamp(f["attributes"]["ANO"] / 1000, timezone.utc).year,
              f["attributes"]["V_REF"]) for f in fs if f["attributes"].get("ANO")]
    return sorted(set(filas))


def contexto_predio(via: str, placa: str) -> dict:
    """Ficha completa de un predio a partir de su dirección: lote, área, sector,
    uso predominante y serie de valor de referencia."""
    geo = geocodificar(via, placa)
    if not geo:
        return {"error": f"Sin placa domiciliaria para '{via} {placa}'. "
                         "Probar la otra dirección catastral del CTL."}
    lote = geo["lote"]
    punto = (geo["lon"], geo["lat"])
    ficha = dict(geo, manzana=lote[:9], area_m2=area_lote_m2(lote),
                 consultado=datetime.now().date().isoformat())
    sec = consultar_ideca("sectorcatastral", punto=punto, campos="SCACODIGO,SCANOMBRE")
    if sec:
        ficha["sector"] = sec[0]["attributes"]["SCANOMBRE"]
        ficha["sector_codigo"] = sec[0]["attributes"]["SCACODIGO"]
    uso = consultar_ideca("usopredominante", punto=punto, campos="MANCODIGO,GRUPOUSOECON,ANO")
    if uso:
        ultimo = max(uso, key=lambda f: f["attributes"].get("ANO") or 0)
        ficha["uso_predominante"] = ultimo["attributes"]["GRUPOUSOECON"]
    ficha["serie_valor_m2"] = serie_valor_referencia(ficha["manzana"])
    return ficha


def buscar_bogota(termino: str, filas: int = 10) -> list[dict]:
    """Catálogo CKAN de datosabiertos.bogota.gov.co (NO es Socrata)."""
    d = _get(CKAN.format(accion="package_search"), {"q": termino, "rows": filas})
    return [{"id": p["name"], "titulo": p["title"],
             "entidad": (p.get("organization") or {}).get("title", ""),
             "recursos": len(p.get("resources", []))}
            for p in d["result"]["results"]]


def consultar_socrata(dataset: str, limite: int = 100, **filtros) -> list[dict]:
    """datos.gov.co (SODA). Para Bogotá aporta poco frente a IDECA."""
    p = {"$limit": limite}
    p.update({f"${k}" if k in ("where", "select", "order") else k: v
              for k, v in filtros.items()})
    return _get(SODA.format(dataset=dataset), p)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Consulta las APIs catastrales")
    ap.add_argument("--predio", nargs=2, metavar=("VIA", "PLACA"),
                    help='ej: --predio "KR 34" "10 58"')
    ap.add_argument("--serie", metavar="MANZANA")
    ap.add_argument("--buscar-bogota", metavar="TERMINO")
    a = ap.parse_args()

    if a.predio:
        f = contexto_predio(*a.predio)
        if "error" in f:
            print(f["error"])
        else:
            print(f"\nDirección   : {f['direccion']}")
            print(f"Lote        : {f['lote']}   Manzana: {f['manzana']}")
            print(f"Sector      : {f.get('sector','—')} ({f.get('sector_codigo','—')})")
            print(f"Área        : {f['area_m2']:,.1f} m²  (geometría IDECA, EPSG:9377)")
            print(f"Uso manzana : {f.get('uso_predominante','—')}")
            print(f"Coordenadas : {f['lat']:.6f}, {f['lon']:.6f}")
            print(f"\nValor de referencia de TERRENO (COP/m²):")
            for anio, v in f["serie_valor_m2"]:
                print(f"   {anio}   ${v:>12,.0f}")
            if f["serie_valor_m2"] and f["area_m2"]:
                ult_anio, ult = f["serie_valor_m2"][-1]
                print(f"\n   Referencia de terreno {ult_anio}: "
                      f"{f['area_m2']:,.1f} m² × ${ult:,.0f} = ${f['area_m2']*ult:,.0f}")
                print("   ⚠ Es valor de referencia administrativo de TERRENO, no un "
                      "avalúo: no incluye construcciones ni ajustes del predio.")
    elif a.serie:
        for anio, v in serie_valor_referencia(a.serie):
            print(f"{anio}  ${v:,.0f}")
    elif a.buscar_bogota:
        for p in buscar_bogota(a.buscar_bogota):
            print(f"  {p['id'][:50]:<50} {p['recursos']:>3} rec. | {p['entidad'][:35]}")
    else:
        ap.print_help()
