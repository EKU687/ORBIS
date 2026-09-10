# =========================================================================
# SCRIPT DE DIAGNOSTIC : COMPARAISON PRÉSENCE AEOS / MC V3
# =========================================================================
from pathlib import Path
import sys
import pandas as pd

# Ajout du dossier racine au PATH Python
ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from utils.db_client import supabase

def diagnostiquer_aeos():
    print("\n🔍 --- DIAGNOSTIC PRÉSENCE AEOS ---\n")

    # 1. Extraction AEOS stricte avec filtre "DINUM"
    res_aeos_strict = supabase.table("aeos_presence").select("*").eq("site_id", "DINUM").execute()
    data_strict = res_aeos_strict.data or []
    print(f"📊 Total AEOS Filtre Strict 'DINUM' : {len(data_strict)} personnes")

    # 2. Extraction globale AEOS (sans filtre de site)
    res_aeos_all = supabase.table("aeos_presence").select("*").execute()
    data_all = res_aeos_all.data or []
    print(f"📊 Total AEOS Global (Toutes lignes BDD) : {len(data_all)} personnes")

    if not data_all:
        print("⚠️ Aucune donnée trouvée dans la table aeos_presence.")
        return

    df = pd.DataFrame(data_all)

    # Création d'une colonne Nom Complet propre
    df["nom_complet"] = (
        df.get("nom", "").fillna("") + " " + df.get("prenom", "").fillna("")
    ).str.strip().str.upper()

    # Si nom/prenom étaient vides, secours sur nom_complet
    df["nom_complet"] = df["nom_complet"].replace("", None).fillna(
        df.get("nom_complet", pd.Series(["INCONNU"] * len(df))).str.upper()
    )

    # 3. Détection des doublons sur les personnes physiques
    doublons = df[df.duplicated(subset=["nom_complet"], keep=False)]
    if not doublons.empty:
        print(f"\n⚠️ {len(doublons)} doublon(s) de nom détecté(s) dans AEOS :")
        print(doublons[["nom_complet", "site_id", "type_personne"]].to_string(index=False))
    else:
        print("\n✅ Aucun doublon de nom trouvé dans la table AEOS.")

    # 4. Affichage de la répartition par site_id
    if "site_id" in df.columns:
        print("\n📍 Répartition par site_id dans BDD :")
        print(df["site_id"].value_counts(dropna=False).to_string())

if __name__ == "__main__":
    diagnostiquer_aeos()