# -*- coding: utf-8 -*-
"""
Entrena y exporta el modelo autorregresivo v2 con metadatos honestos.

QUÉ CAMBIA FRENTE AL v1 (eliminado)
    v1: 9 features, split aleatorio sobre un panel, R²=0,8454 · MAE $308.368.
        Esas métricas medían la capacidad de re-identificar la manzana, no de
        estimar su valor: un baseline trivial las superaba.
    v2: features sin fuga + el valor de la manzana en t-1, evaluado con holdout
        temporal (≤2025 → 2026). Es la única configuración que gana al baseline
        ingenuo de repetir el valor del año anterior.

DOS MODELOS, A PROPÓSITO
    - El que se EVALÚA se entrena solo con ≤2025 y se mide contra 2026. De ahí
      salen las métricas que se publican.
    - El que se EXPORTA se reentrena con todo (≤2026) para estimar 2027. No se
      puede medir todavía: sus métricas son, por construcción, las del anterior.
    Confundirlos es la trampa clásica — medir sobre datos que el modelo ya vio.

    python entrenar_modelo.py             # entrena, evalúa y exporta v2
    python entrenar_modelo.py --sin-exportar   # solo evalúa
"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

from reevaluacion_modelo import FEATURES_LIMPIAS, TARGET, cargar, modelo

for _f in (sys.stdout, sys.stderr):
    try:
        _f.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

RAIZ = Path(__file__).resolve().parent.parent
MODELOS = RAIZ / "models"
VERSION = "v2"
# El rezago del valor de la manzana es lo que convierte el problema en uno
# resoluble: al estimar un predio SÍ se conoce el valor que la UAECD publicó el
# año pasado. `var_loc_t1` es la variación de la localidad en t-1, no en t —
# la de t se derivaba del propio target y era fuga.
FEATURES_V2 = FEATURES_LIMPIAS + ["valor_manzana_t1", "var_loc_t1"]


def metricas(y, p) -> dict:
    return {"r2": round(float(r2_score(y, p)), 4),
            "mae_cop_m2": int(mean_absolute_error(y, p)),
            "rmse_cop_m2": int(np.sqrt(mean_squared_error(y, p)))}


def main(exportar: bool) -> None:
    df = cargar().dropna(subset=FEATURES_V2)
    anio_max = int(df["anio"].max())
    corte = anio_max - 1

    # ── 1. Modelo de EVALUACIÓN: ≤corte → anio_max ─────────────────────────
    tr, te = df["anio"] <= corte, df["anio"] == anio_max
    m_eval = modelo()
    m_eval.fit(df[tr][FEATURES_V2], df[tr][TARGET])
    pred = m_eval.predict(df[te][FEATURES_V2])
    met = metricas(df[te][TARGET], pred)

    # Baseline ingenuo bajo el MISMO protocolo: repetir el valor del año
    # anterior. Si el modelo no le gana a esto, no aporta nada.
    base = metricas(df[te][TARGET], df[te]["valor_manzana_t1"])

    print(f"── Evaluación · holdout temporal (≤{corte} → {anio_max}) ──────────")
    print(f"  n_train {tr.sum():,} · n_test {te.sum():,}\n")
    print(f"  Modelo v2 autorregresivo   R²={met['r2']:.4f}  "
          f"MAE=${met['mae_cop_m2']:,}  RMSE=${met['rmse_cop_m2']:,}")
    print(f"  BASELINE valor año previo  R²={base['r2']:.4f}  "
          f"MAE=${base['mae_cop_m2']:,}  RMSE=${base['rmse_cop_m2']:,}")
    ganancia = base["mae_cop_m2"] - met["mae_cop_m2"]
    veredicto = "SUPERA al baseline" if ganancia > 0 else "NO SUPERA al baseline"
    print(f"\n  → {veredicto}: {ganancia:+,} COP/m² de MAE "
          f"({ganancia / base['mae_cop_m2'] * 100:+.1f}%)")

    if ganancia <= 0:
        print("\n  El modelo no aporta sobre lo trivial. NO se exporta.")
        return

    print(f"\n  Importancia de variables:")
    imp = pd.Series(m_eval.feature_importances_, index=FEATURES_V2).sort_values(ascending=False)
    for f, v in imp.items():
        print(f"    {f:<22} {v:.4f}")

    if not exportar:
        return

    # ── 2. Modelo de PRODUCCIÓN: reentrenado con TODO ──────────────────────
    m_prod = modelo()
    m_prod.fit(df[FEATURES_V2], df[TARGET])
    MODELOS.mkdir(exist_ok=True)
    ruta = MODELOS / f"xgboost_autorregresivo_{VERSION}.joblib"
    joblib.dump({"modelo": m_prod, "features": FEATURES_V2, "target": TARGET,
                 "version": VERSION}, ruta)

    meta = {
        "modelo": "XGBoost autorregresivo",
        "version": VERSION,
        "fecha_entrenamiento": date.today().isoformat(),
        "reemplaza_a": "xgboost_final_v1 (eliminado 2026-08-04)",
        "por_que_se_reemplazo":
            "El v1 se evaluó con train_test_split aleatorio sobre un panel donde "
            "cada manzana aparece ~6 veces con features casi constantes. Su "
            f"R²=0.8454 medía re-identificación de la manzana, no estimación de "
            "valor: un baseline trivial (media de la propia manzana) obtenía "
            "R²=0.8942. Además usaba `variacion_localidad`, derivada del target "
            "y no disponible ex ante.",
        "features": FEATURES_V2,
        "target": TARGET,
        "unidad_target": "COP por m² de terreno (valor de referencia UAECD por manzana)",

        "protocolo_evaluacion": {
            "tipo": "holdout temporal",
            "train": f"años ≤ {corte}",
            "test": f"año {anio_max}",
            "n_train": int(tr.sum()),
            "n_test": int(te.sum()),
            "por_que": "Es el caso de uso real: estimar un año que el modelo no "
                       "ha visto. Un split aleatorio sobre panel sobreestima."},
        "metricas": met,
        "baseline_mismo_protocolo": {
            "descripcion": "Repetir el valor de referencia del año anterior, sin modelo",
            **base,
            "ganancia_mae_cop_m2": int(ganancia)},

        "modelo_exportado": {
            "entrenado_con": f"todos los años ≤ {anio_max} ({len(df):,} filas)",
            "para": f"estimar {anio_max + 1}",
            "advertencia": "Las métricas publicadas son las del modelo de "
                           f"evaluación (≤{corte}→{anio_max}), NO de este. Este no "
                           "se puede medir hasta que exista el dato real de "
                           f"{anio_max + 1}."},

        "limitaciones": [
            f"MAE de ${met['mae_cop_m2']:,}/m² sobre una mediana de ~$2,5M/m²: "
            "~10% de error típico. Sirve para acotar un RANGO, no para fijar un "
            "valor puntual en un avalúo.",
            "Estima el valor de referencia de TERRENO por MANZANA, no el valor "
            "comercial de un predio: no distingue lotes dentro de la manzana ni "
            "incorpora construcciones, frente, fondo ni forma.",
            "No sustituye el método de comparación de mercado que exige el "
            "Decreto 1170 de 2015 art. 2.2.2.6.3 num. 1.",
            "Requiere el valor de la manzana en t-1. Sin ese dato no aplica.",
            "Entrenado con el valor de referencia UAECD, que se actualiza por "
            "resolución anual: declarar siempre el año de corte de los insumos."],

        "datos": {
            "fuente": "data/processed/dataset_modelado.parquet",
            "origen": "UAECD/IDECA vía PostGIS catastro.valor_manzana",
            "cobertura": f"{int(df['anio'].min())}–{anio_max} · "
                         f"{df['cod_manzana'].nunique():,} manzanas · {len(df):,} filas"},
    }
    meta_ruta = MODELOS / f"modelo_{VERSION}_metadata.json"
    meta_ruta.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\n✓ Modelo   → {ruta.name} ({ruta.stat().st_size // 1024} KB)")
    print(f"✓ Metadatos→ {meta_ruta.name}")
    registrar(meta)


def registrar(meta: dict) -> None:
    """Deja el modelo v2 en la base de sustento para poder citarlo en un avalúo."""
    import sustento_pipeline as sp
    con = sp.abrir_db()
    con.execute("DELETE FROM validaciones WHERE ambito='modelo'")
    con.execute("""INSERT INTO validaciones(ambito,objeto,regla,resultado,evidencia,
                   norma_o_referencia,fecha) VALUES(?,?,?,?,?,?,?)""",
                ("modelo", f"xgboost_autorregresivo_{VERSION}",
                 "Debe superar al baseline ingenuo bajo holdout temporal",
                 "APROBADO",
                 f"R²={meta['metricas']['r2']} MAE=${meta['metricas']['mae_cop_m2']:,} vs "
                 f"baseline MAE=${meta['baseline_mismo_protocolo']['mae_cop_m2']:,} "
                 f"(ganancia ${meta['baseline_mismo_protocolo']['ganancia_mae_cop_m2']:,})",
                 "Protocolo: " + meta["protocolo_evaluacion"]["tipo"],
                 meta["fecha_entrenamiento"]))
    con.commit()
    print("✓ Registrado en sustento.db (ambito='modelo')")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Entrena y exporta el modelo v2")
    ap.add_argument("--sin-exportar", action="store_true", help="solo evalúa")
    main(not ap.parse_args().sin_exportar)
