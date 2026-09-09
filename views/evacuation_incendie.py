# =========================================================================
# MODULE : REGISTRE D'ÉVACUATION & RASSEMBLEMENT (views/evacuation_incendie.py)
# Inclus : Consolidation AEOS + Visiteurs ORBIS V3, Tri hiérarchisé,
#          Pointage séparé (Employés / Prestataires / Visiteurs).
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
        
        # Repli de sécurité : si aucun résultat sur le site strict, on récupère tout
        if not data:
            res_all = supabase.table("aeos_presence").select("*").execute()
            data = res_all.data or []
            
        return data
    except Exception as e:
        st.error(f"⚠️ Erreur chargement AEOS : {e}")
        return []


def fetch_orbis_visiteurs_presents(site_id: str) -> list[dict]:
    """Récupère tous les visiteurs et livreurs actuellement sur site depuis BDD (mc_evenements + badges_temporaires)."""
    clean_visiteurs = []
    site_target = str(site_id).upper().strip() if site_id else "DINUM"
    now_nc = get_now_nc()
    dt_start = datetime.datetime.combine(now_nc.date(), datetime.time.min, tzinfo=TZ_NC).isoformat()
    dt_end = datetime.datetime.combine(now_nc.date(), datetime.time.max, tzinfo=TZ_NC).isoformat()

    try:
        # 1. Source A : badges_temporaires
        res_bdg = (
            supabase.table("badges_temporaires")
            .select("*")
            .eq("site_id", site_target)
            .eq("statut", "EN_COURS")
            .execute()
        )
        for vis in (res_bdg.data or []):
            nom_test = vis.get("nom_porteur") or vis.get("nom_agent") or vis.get("nom_complet") or vis.get("nom") or ""
            if str(nom_test).strip() and str(nom_test).strip().upper() != "INCONNU":
                clean_visiteurs.append({
                    "nom_porteur": str(nom_test).strip().upper(),
                    "num_badge": vis.get("num_badge", "Sans Badge"),
                    "type_badge": vis.get("type_porteur", "VISITEUR"),
                    "organisme": vis.get("organisme", "Extérieur"),
                    "hote_referent": vis.get("hote_referent", "Non précisé")
                })

        # 2. Source B : Recherche des entrées sans sortie du jour dans mc_evenements (ASAP, CSV, Imprévus)
        res_mc = (
            supabase.table("mc_evenements")
            .select("*")
            .eq("site_id", site_target)
            .eq("type_evenement", "VISITEUR")
            .gte("horodatage", dt_start)
            .lte("horodatage", dt_end)
            .order("horodatage", desc=False)
            .execute()
        )

        presents_mc = {}
        for ev in (res_mc.data or []):
            ref = ev.get("reference", "")
            desc = ev.get("description", "")
            
            # Nom du visiteur extrait de la description
            nom_key = desc.split(":")[1].split("(")[0].strip().upper() if ":" in desc else desc.strip().upper()

            if "-IN-" in ref:
                bdg_val = "Sans Badge"
                if "LIVRAISON" in desc.upper():
                    bdg_val = "LIVRAISON"
                elif "DEPOT" in desc.upper() or "MATERIEL" in desc.upper():
                    bdg_val = "DEPOT_MATERIEL"
                elif "BADGE" in desc.upper():
                    parts = desc.split("Badge")
                    if len(parts) > 1:
                        bdg_val = parts[1].split(")")[0].strip()

                presents_mc[nom_key] = {
                    "nom_porteur": nom_key,
                    "num_badge": bdg_val,
                    "type_badge": "VISITEUR",
                    "organisme": "Extérieur",
                    "hote_referent": "Accueilli sur site"
                }
            elif "-OUT-" in ref or "-ABS-" in ref:
                presents_mc.pop(nom_key, None)

        # 3. Déduplication par nom entre les deux sources
        noms_existants = {v["nom_porteur"] for v in clean_visiteurs}
        for nom_mc, info_mc in presents_mc.items():
            if nom_mc not in noms_existants:
                clean_visiteurs.append(info_mc)

        return clean_visiteurs

    except Exception as e:
        st.error(f"⚠️ Erreur chargement Visiteurs ORBIS : {e}")
        return clean_visiteurs

def afficher_tableau_pointage(df_data: pd.DataFrame, key_suffix: str):
    """Affiche un tableau interactif Streamlit avec case de pointage et progression."""
    if df_data.empty:
        st.info("ℹ️ Personne recensée dans cette catégorie.")
        return

    df_display = df_data.copy()
    if "Présent au Rassemblement" not in df_display.columns:
        df_display.insert(0, "Présent au Rassemblement", False)

    # Ordre des colonnes masquant la colonne technique 'Ordre_Tri'
    cols_to_show = [
        "Présent au Rassemblement",
        "Source",
        "Nom & Prénom",
        "Service / Société",
        "Catégorie",
        "Badge / Mode",
        "Zone",
    ]
    df_display = df_display[cols_to_show]

    edited_df = st.data_editor(
        df_display,
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
        key=f"editor_{key_suffix}",
    )

    nb_pointes = edited_df["Présent au Rassemblement"].sum()
    total_cat = len(edited_df)
    ratio = nb_pointes / total_cat if total_cat > 0 else 0
    st.progress(ratio)
    st.caption(f"Status Pointage : **{nb_pointes} / {total_cat}** personnes localisées.")


def show():
    st.title("🚨 Registre de Présence & Évacuation Incendie")
    st.caption("Console de crise et d'appel au point de rassemblement (Consolidation AEOS + ORBIS V3).")

    site_actuel = st.session_state.get("site_actif", "DINUM")

    # Bouton de rafraîchissement
    c_title1, c_title2 = st.columns([3, 1])
    with c_title2:
        if st.button("🔄 Actualiser la liste", use_container_width=True):
            st.rerun()

    # 1. Chargement des données Supabase
    data_aeos = fetch_aeos_presents(site_actuel)
    data_visiteurs = fetch_orbis_visiteurs_presents(site_actuel)

    # 2. Consolidation dans un DataFrame unifié
    liste_globale = []

    # Formatage des permanents AEOS
    for item in data_aeos:
        nom_aff = f"{item.get('nom', '')} {item.get('prenom', '')}".strip()
        if not nom_aff:
            nom_aff = item.get("nom_complet", "Inconnu")

        raw_type = str(item.get("type_personne", "Employé")).strip()
        is_presta = "PRESTA" in raw_type.upper()
        
        # Tri : 1=Employé, 2=Prestataire AEOS
        ordre_tri = 2 if is_presta else 1
        cat_lib = "Prestataire" if is_presta else "Employé"

        liste_globale.append({
            "Source": "🏢 AEOS",
            "Nom & Prénom": nom_aff,
            "Service / Société": item.get("service", "DINUM"),
            "Catégorie": cat_lib,
            "Badge / Mode": "Carte Permanente",
            "Zone": item.get("zone_acces", "Zone sur site"),
            "Ordre_Tri": ordre_tri,
        })

    # Formatage des visiteurs ORBIS (Exclusion des badges T pour éviter le double comptage avec AEOS)
    for vis in data_visiteurs:
        bdg = str(vis.get("num_badge", "Sans Badge")).strip().upper()
        type_badge = str(vis.get("type_badge", "")).strip().upper()

        # 🚫 RÈGLE DE SÛRETÉ : Si c'est un Badge Agent (T), AEOS le compte déjà à l'entrée !
        is_badge_agent = bdg.startswith("T") or "AGENT" in type_badge or "TEMPORAIRE" in type_badge
        if is_badge_agent:
            continue

        cat = "📦 LIVRAISON" if bdg == "LIVRAISON" else ("📦 DÉPÔT MATÉRIEL" if bdg == "DEPOT_MATERIEL" else "✍️ VISITEUR")

        nom_aff = (
            vis.get("nom_porteur")
            or vis.get("nom_agent")
            or vis.get("nom_complet")
            or vis.get("nom")
            or "Visiteur"
        ).strip().upper()

        liste_globale.append({
            "Source": "✍️ ORBIS V3",
            "Nom & Prénom": nom_aff,
            "Service / Société": vis.get("organisme", "Extérieur"),
            "Catégorie": cat,
            "Badge / Mode": bdg,
            "Zone": f"Hôte: {vis.get('hote_referent', 'Non précisé')}",
            "Ordre_Tri": 3, # 3=Visiteurs / Livreurs
        })

    if not liste_globale:
        st.info("ℹ️ Aucune personne recensée actuellement sur le site.")
        return

    df_presents = pd.DataFrame(liste_globale)

    # 🎯 TRI HIERARCHIQUE : PAR TYPE (Employés -> Prestataires -> Visiteurs) PUIS PAR NOM
    df_presents.sort_values(by=["Ordre_Tri", "Nom & Prénom"], ascending=[True, True], inplace=True)

    # Décompte par sous-groupes
    df_employes = df_presents[df_presents["Ordre_Tri"] == 1]
    df_prestataires = df_presents[df_presents["Ordre_Tri"] == 2]
    df_visiteurs = df_presents[df_presents["Ordre_Tri"] == 3]

    cnt_emp = len(df_employes)
    cnt_presta = len(df_prestataires)
    cnt_vis = len(df_visiteurs)
    total_general = len(df_presents)

    # 3. Métriques synthétiques
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("🚨 Total sur Site", f"{total_general} pers.")
    m2.metric("👔 Employés (Public)", f"{cnt_emp} pers.")
    m3.metric("🛠️ Prestataires", f"{cnt_presta} pers.")
    m4.metric("✍️ Visiteurs / Livreurs", f"{cnt_vis} pers.")

    st.markdown("---")

    # 4. Filtre de recherche universel
    recherche_nom = st.text_input("🔍 Rechercher une personne ou un service :", placeholder="Ex: KUTER ou SIN")

    if recherche_nom.strip():
        term = recherche_nom.strip().upper()
        df_presents = df_presents[
            df_presents["Nom & Prénom"].str.upper().str.contains(term)
            | df_presents["Service / Société"].str.upper().str.contains(term)
        ]
        # Re-calcul des sous-groupes filtrés
        df_employes = df_presents[df_presents["Ordre_Tri"] == 1]
        df_prestataires = df_presents[df_presents["Ordre_Tri"] == 2]
        df_visiteurs = df_presents[df_presents["Ordre_Tri"] == 3]

    # 5. RUPTURE PAR ONGLETS DÉDIÉS + VUE CONSOLIDÉE
    tab_globale, tab_emp, tab_presta, tab_vis = st.tabs([
        f"📊 Liste Consolidée ({len(df_presents)})",
        f"👔 Employés ({len(df_employes)})",
        f"🛠️ Prestataires ({len(df_prestataires)})",
        f"✍️ Visiteurs / Livreurs ({len(df_visiteurs)})",
    ])

    with tab_globale:
        st.markdown("### 📋 Liste Générale Triée (Employés ➔ Prestataires ➔ Visiteurs)")
        afficher_tableau_pointage(df_presents, "globale")

    with tab_emp:
        st.markdown("### 👔 Liste des Employés / Agents Publics")
        afficher_tableau_pointage(df_employes, "employes")

    with tab_presta:
        st.markdown("### 🛠️ Liste des Prestataires")
        afficher_tableau_pointage(df_prestataires, "prestataires")

    with tab_vis:
        st.markdown("### ✍️ Liste des Visiteurs & Livreurs")
        afficher_tableau_pointage(df_visiteurs, "visiteurs")


if __name__ == "__main__":
    show()