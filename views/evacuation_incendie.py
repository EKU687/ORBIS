# =========================================================================
# MODULE : REGISTRE D'ÉVACUATION & RASSEMBLEMENT (views/evacuation_incendie.py)
# Inclus : Consolidation AEOS + Visiteurs ORBIS V3, Pointage interactif,
#          Filtres par service/type, et Mode Appel d'Urgence.
# =========================================================================
import datetime
from pathlib import Path
import sys
import zoneinfo
import pandas as pd
import streamlit as st

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from utils.db_client import supabase

TZ_NC = zoneinfo.ZoneInfo("Pacific/Noumea")


def get_now_nc() -> datetime.datetime:
    return datetime.datetime.now(TZ_NC)


def fetch_aeos_presents(site_id: str) -> list[dict]:
    """Récupère les permanents présents remontés automatiquement par AEOS."""
    try:
        site_target = str(site_id).upper().strip() if site_id else "DINUM"
        res = (
            supabase.table("aeos_presence")
            .select("*")
            .eq("site_id", site_target)
            .execute()
        )
        data = res.data or []
        
        # Repli de sécurité incendie : si aucun résultat sur le site strict, on récupère tout
        if not data:
            res_all = supabase.table("aeos_presence").select("*").execute()
            data = res_all.data or []
            
        return data
    except Exception as e:
        st.error(f"⚠️ Erreur chargement AEOS : {e}")
        return []


def fetch_orbis_visiteurs_presents(site_id: str) -> list[dict]:
    """Récupère les visiteurs et livreurs actuellement sur site depuis badges_temporaires."""
    try:
        site_target = str(site_id).upper().strip() if site_id else "DINUM"
        res = (
            supabase.table("badges_temporaires")
            .select("*")
            .eq("site_id", site_target)
            .eq("statut", "EN_COURS")
            .execute()
        )
        return res.data or []
    except Exception as e:
        st.error(f"⚠️ Erreur chargement Visiteurs ORBIS : {e}")
        return []


def show():
    st.title("🚨 Registre de Présence & Évacuation Incendie")
    st.caption("Console de crise et d'appel au point de rassemblement (Consolidation AEOS + ORBIS V3).")

    site_actuel = st.session_state.get("site_actif", "DINUM")
    now_nc = get_now_nc()

    # Bouton de rafraîchissement
    c_title1, c_title2 = st.columns([3, 1])
    with c_title2:
        if st.button("🔄 Actualiser la liste", use_container_width=True):
            st.rerun()

    # 1. Chargement des données Supabase
    data_aeos = fetch_aeos_presents(site_actuel)
    data_visiteurs = fetch_orbis_visiteurs_presents(site_actuel)

    total_aeos = len(data_aeos)
    total_visiteurs = len(data_visiteurs)
    total_general = total_aeos + total_visiteurs

    # 2. Métriques en en-tête
    m1, m2, m3 = st.columns(3)
    m1.metric("🚨 Total Général sur Site", f"{total_general} pers.")
    m2.metric("🏢 Permanents (AEOS)", f"{total_aeos} pers.")
    m3.metric("✍️ Visiteurs / Livreurs (ORBIS)", f"{total_visiteurs} pers.")

    st.markdown("---")

    # 3. Consolidation dans un DataFrame unifié
    liste_globale = []

    # Formatage des permanents AEOS
    for item in data_aeos:
        nom_aff = f"{item.get('nom', '')} {item.get('prenom', '')}".strip()
        if not nom_aff:
            nom_aff = item.get("nom_complet", "Inconnu")

        liste_globale.append({
            "Source": "🏢 AEOS",
            "Nom & Prénom": nom_aff,
            "Service / Société": item.get("service", "DINUM"),
            "Catégorie": item.get("type_personne", "Employé"),
            "Badge / Mode": "Carte Permanente",
            "Zone": item.get("zone_acces", "Zone sur site"),
        })

    # Formatage des visiteurs ORBIS
    for vis in data_visiteurs:
        bdg = vis.get("num_badge", "Sans Badge")
        cat = "📦 LIVRAISON" if bdg == "LIVRAISON" else ("📦 DÉPÔT MATÉRIEL" if bdg == "DEPOT_MATERIEL" else "✍️ VISITEUR")

        liste_globale.append({
            "Source": "✍️ ORBIS V3",
            "Nom & Prénom": vis.get("nom_porteur", "Inconnu"),
            "Service / Société": vis.get("organisme", "Extérieur"),
            "Catégorie": cat,
            "Badge / Mode": bdg,
            "Zone": f"Hôte: {vis.get('hote_referent', 'Non précisé')}",
        })

    if not liste_globale:
        st.info("ℹ️ Aucune personne recensée actuellement sur le site.")
        return

    df_presents = pd.DataFrame(liste_globale)

    # 4. Filtres de recherche
    f1, f2 = st.columns([2, 2])
    with f1:
        filtre_source = st.multiselect(
            "Filtrer par Source :",
            options=["🏢 AEOS", "✍️ ORBIS V3"],
            default=["🏢 AEOS", "✍️ ORBIS V3"]
        )
    with f2:
        recherche_nom = st.text_input("🔍 Rechercher une personne ou un service :", placeholder="Ex: KUTER ou SIN")

    # Application des filtres
    df_filtered = df_presents[df_presents["Source"].isin(filtre_source)].copy()

    if recherche_nom.strip():
        term = recherche_nom.strip().upper()
        df_filtered = df_filtered[
            df_filtered["Nom & Prénom"].str.upper().str.contains(term)
            | df_filtered["Service / Société"].str.upper().str.contains(term)
        ]

    st.markdown(f"### 📋 Liste de Pointage ({len(df_filtered)} / {total_general} personnes affichées)")

    # 5. Tableau d'affichage dynamique avec case de pointage
    df_filtered.insert(0, "Présent au Rassemblement", False)

    edited_df = st.data_editor(
        df_filtered,
        column_config={
            "Présent au Rassemblement": st.column_config.CheckboxColumn(
                "Pointage 🟢",
                help="Cocher au point de rassemblement",
                default=False,
            ),
            "Source": st.column_config.TextColumn("Origine", width="small"),
            "Nom & Prénom": st.column_config.TextColumn("Nom & Prénom", width="medium"),
            "Service / Société": st.column_config.TextColumn("Service / Société", width="medium"),
            "Catégorie": st.column_config.TextColumn("Type", width="small"),
            "Badge / Mode": st.column_config.TextColumn("Badge", width="small"),
        },
        disabled=["Source", "Nom & Prénom", "Service / Société", "Catégorie", "Badge / Mode", "Zone"],
        hide_index=True,
        use_container_width=True,
    )

    # Compteur de pointage en direct
    nb_pointes = edited_df["Présent au Rassemblement"].sum()
    st.progress(nb_pointes / len(edited_df) if len(edited_df) > 0 else 0)
    st.caption(f"Status Pointage : **{nb_pointes}** personnes localisées au point de rassemblement sur **{len(edited_df)}**.")


if __name__ == "__main__":
    show()