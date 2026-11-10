# -*- coding: utf-8 -*-
"""
Reevaluación honesta del modelo de valor por m². Reemplaza las métricas del NB04b.

QUÉ ESTABA MAL
    El NB04b partió el panel con train_test_split aleatorio. Pero cada manzana
    aparece ~6 veces (una por año) y sus features son casi constantes en el
    tiempo, así que casi toda manzana del test tenía filas hermanas en el train.
    El R²=0,8454 mide sobre todo la capacidad de RE-IDENTIFICAR la manzana, no
    de estimar el valor de un predio que el modelo no ha visto.

    Y `variacion_localidad` se deriva de la mediana del propio target por
    localidad-año: además de fuga, NO existe ex ante — para predecir 2027 habría
    que conocer la variación de 2027. El modelo no podía proyectar.

QUÉ HACE ESTE SCRIPT
    Evalúa bajo cuatro protocolos y contra dos baselines triviales. La regla es
    que un modelo solo sirve si le gana a lo trivial BAJO EL MISMO protocolo.

    python reevaluacion_modelo.py            # tabla completa
    python reevaluacion_modelo.py --registrar # además, guarda en sustento.db
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import GroupShuffleSplit, train_test_split

for _f in (sys.stdout, sys.stderr):
    try:
        _f.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

RAIZ = Path(__file__).resolve().parent.parent
# Dataset de modelado SIN las columnas de predicción del Random Forest descartado
# (valor_predicho / error_abs / error_pct venían de predecir sobre el propio
# train, así que sus errores estaban encogidos y no medían nada).
DATOS = RAIZ / "data" / "processed" / "dataset_modelado.parquet"

FEATURES_NB04B = ["anio_norm", "localidad_enc", "territorio_enc", "variacion_localidad",
                  "dist_tm_m", "dist_metro_m", "dist_sitp_m", "estrato",
                  "indice_inseguridad"]
# Sin la variable derivada del target. Es el conjunto que sí está disponible
# antes de conocer el año que se quiere estimar.
FEATURES_LIMPIAS = [f for f in FEATURES_NB04B if f != "variacion_localidad"]
TARGET = "valor_final"


def cargar() -> pd.DataFrame:
    df = pd.read_parquet(DATOS)
    # Rezagos: lo que SÍ se conoce al momento de estimar el año t.
    df = df.sort_values(["cod_manzana", "anio"])
    g = df.groupby("cod_manzana")[TARGET]
    df["valor_manzana_t1"] = g.shift(1)          # valor de la manzana el año anterior
    # Variación de la localidad el año ANTERIOR (la del año en curso es fuga).
    med = df.groupby(["localidad", "anio"])[TARGET].median().rename("med_loc")
    var = med.groupby("localidad").pct_change().mul(100).rename("var_loc")
    df = df.merge(var.reset_index(), on=["localidad", "anio"], how="left")
    df["var_loc_t1"] = df.groupby("cod_manzana")["var_loc"].shift(1)
    return df


def modelo():
    from xgboost import XGBRegressor
    return XGBRegressor(n_estimators=300, max_depth=6, learning_rate=0.05,
                        subsample=0.8, n_jobs=-1, random_state=42, verbosity=0)


def evaluar(nombre, Xtr, ytr, Xte, yte, protocolo) -> dict:
    m = modelo()
    m.fit(Xtr, ytr)
    p = m.predict(Xte)
    return {"modelo": nombre, "protocolo": protocolo, "R2": r2_score(yte, p),
            "MAE": mean_absolute_error(yte, p), "n_test": len(yte)}


def main(registrar: bool) -> None:
    df = cargar()
    print(f"Dataset: {len(df):,} filas · {df['cod_manzana'].nunique():,} manzanas · "
          f"años {df['anio'].min()}–{df['anio'].max()}\n")
    res = []

    # ── A. El protocolo del NB04b: split aleatorio sobre el panel ──────────
    Xtr, Xte, ytr, yte = train_test_split(df[FEATURES_NB04B], df[TARGET],
                                          test_size=0.2, random_state=42)
    res.append(evaluar("XGBoost (9 features NB04b)", Xtr, ytr, Xte, yte,
                       "A · aleatorio (el del NB04b)"))
    # Baseline bajo el MISMO protocolo: predecir la media de la propia manzana.
    # Si el modelo no le gana a esto, su R² no prueba que aprendió el mercado.
    itr, ite = train_test_split(np.arange(len(df)), test_size=0.2, random_state=42)
    med_mz = df.iloc[itr].groupby("cod_manzana")[TARGET].mean()
    pred = df.iloc[ite]["cod_manzana"].map(med_mz).fillna(df.iloc[itr][TARGET].median())
    y = df.iloc[ite][TARGET]
    res.append({"modelo": "BASELINE media de la propia manzana", "protocolo":
                "A · aleatorio (el del NB04b)", "R2": r2_score(y, pred),
                "MAE": mean_absolute_error(y, pred), "n_test": len(y)})

    # ── B. Split por manzana: mide generalización a predios NO vistos ──────
    gss = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=42)
    tr, te = next(gss.split(df, groups=df["cod_manzana"]))
    res.append(evaluar("XGBoost (9 features NB04b)",
                       df.iloc[tr][FEATURES_NB04B], df.iloc[tr][TARGET],
                       df.iloc[te][FEATURES_NB04B], df.iloc[te][TARGET],
                       "B · por manzana (predio nuevo)"))
    res.append(evaluar("XGBoost (sin variacion_localidad)",
                       df.iloc[tr][FEATURES_LIMPIAS], df.iloc[tr][TARGET],
                       df.iloc[te][FEATURES_LIMPIAS], df.iloc[te][TARGET],
                       "B · por manzana (predio nuevo)"))

    # ── C. Holdout temporal: el caso de uso real (estimar el año siguiente) ─
    tr_t, te_t = df["anio"] <= 2025, df["anio"] == 2026
    res.append(evaluar("XGBoost (9 features NB04b)", df[tr_t][FEATURES_NB04B],
                       df[tr_t][TARGET], df[te_t][FEATURES_NB04B], df[te_t][TARGET],
                       "C · temporal (≤2025 → 2026)"))
    res.append(evaluar("XGBoost (sin variacion_localidad)", df[tr_t][FEATURES_LIMPIAS],
                       df[tr_t][TARGET], df[te_t][FEATURES_LIMPIAS], df[te_t][TARGET],
                       "C · temporal (≤2025 → 2026)"))
    # Baseline temporal: el valor del año anterior, sin modelo alguno.
    t = df[te_t].dropna(subset=["valor_manzana_t1"])
    res.append({"modelo": "BASELINE valor del año anterior", "protocolo":
                "C · temporal (≤2025 → 2026)",
                "R2": r2_score(t[TARGET], t["valor_manzana_t1"]),
                "MAE": mean_absolute_error(t[TARGET], t["valor_manzana_t1"]),
                "n_test": len(t)})

    # ── D. Autorregresivo: features limpias + valor rezagado de la manzana ──
    # Es el planteamiento correcto para la app: al estimar un predio SÍ se conoce
    # el valor de referencia del año anterior, que la UAECD publica.
    FEAT_AR = FEATURES_LIMPIAS + ["valor_manzana_t1", "var_loc_t1"]
    d = df.dropna(subset=FEAT_AR)
    tr_a, te_a = d["anio"] <= 2025, d["anio"] == 2026
    res.append(evaluar("XGBoost AUTORREGRESIVO (+valor t-1)", d[tr_a][FEAT_AR],
                       d[tr_a][TARGET], d[te_a][FEAT_AR], d[te_a][TARGET],
                       "C · temporal (≤2025 → 2026)"))

    tabla = pd.DataFrame(res)
    tabla["MAE"] = tabla["MAE"].round(0)
    tabla["R2"] = tabla["R2"].round(4)
    print("═" * 92)
    for prot in tabla["protocolo"].unique():
        print(f"\n── {prot} " + "─" * (86 - len(prot)))
        sub = tabla[tabla["protocolo"] == prot].sort_values("R2", ascending=False)
        for _, r in sub.iterrows():
            marca = "  ←" if r["modelo"].startswith("BASELINE") else "   "
            print(f"  {r['modelo']:<42} R²={r['R2']:>7.4f}   "
                  f"MAE=${r['MAE']:>12,.0f}   n={r['n_test']:>7,}{marca}")
    print("\n" + "═" * 92)

    salida = RAIZ / "data" / "processed" / "reevaluacion_modelo.csv"
    tabla.to_csv(salida, index=False)
    print(f"\nTabla → {salida}")

    if registrar:
        registrar_en_sustento(tabla)


def registrar_en_sustento(tabla: pd.DataFrame) -> None:
    """Deja el resultado en la base de sustento: sin esto, la reevaluación es un
    archivo suelto y el avalúo no puede citarla."""
    import sustento_pipeline as sp
    from datetime import date
    con = sp.abrir_db()
    con.execute("DELETE FROM validaciones WHERE ambito='estadistico'")
    for _, r in tabla.iterrows():
        con.execute("""INSERT INTO validaciones(ambito,objeto,regla,resultado,evidencia,
                       norma_o_referencia,fecha) VALUES(?,?,?,?,?,?,?)""",
                    ("estadistico", f"{r['modelo']} | {r['protocolo']}",
                     "El modelo debe superar al baseline trivial bajo el mismo protocolo",
                     "REGISTRO", f"R²={r['R2']:.4f} MAE=${r['MAE']:,.0f} n={r['n_test']:,}",
                     "Reevaluación 2026-08-04 (reemplaza métricas del NB04b)",
                     date.today().isoformat()))
    con.commit()
    print(f"Registradas {len(tabla)} mediciones en sustento.db (ambito='estadistico')")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Reevaluación honesta del modelo")
    ap.add_argument("--registrar", action="store_true",
                    help="guarda los resultados en docs/sustento.db")
    main(ap.parse_args().registrar)
