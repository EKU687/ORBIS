# =========================================================================
# MINI-APP : ORBIS-EVAC - CONSOLE DE CRISE & POINTAGE TERRAIN (MOBILE/TABLETTE)
# Inclus : Déclenchement d'alerte, Chronomètre de crise, Pointage interactif
#          en direct vers Supabase, Clôture et enregistrement Main Courante.
# =========================================================================
import datetime
from pathlib import Path
import sys
import time
import zoneinfo
import pandas as pd
import streamlit as st
from streamlit_autorefresh import st_autorefresh

# --- FIX DES CHEMINS PYTHON & IMPORTS SOCLE ---
ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from utils.db_client import supabase

# FUSEAU HORAIRE NOUVELLE-CALÉDONIE
TZ_NC = zoneinfo.ZoneInfo("Pacific/Noumea")


def get_now_nc() -> datetime.datetime:
    return datetime.datetime.now(TZ_NC)


# --- CONFIGURATION STREAMLIT EMBARQUÉE TERRAIN ---
st.set_page_config(
    page_title="ORBIS - Évacuation & Pointage",
    page_icon="🚨",
    layout="wide",
    initial_sidebar_state="collapsed",  # Masqué par défaut pour maximiser la surface tactile
)


# =========================================================================
# 1. HELPERS ACCÈS BASE DE DONNÉES SUPABASE
# =========================================================================
def get_session_evac_active(site_id: str) -> dict | None:
    """Récupère la session d'évacuation en cours pour le site."""
    try:
        res = (
            supabase.table("evacuations_sessions")
            .select("*")
            .eq("site_id", site_id)
            .eq("statut", "EN_COURS")
            .order("date_debut", desc=True)
            .limit(1)
            .execute()
        )
        return res.data[0] if res.data else None
    except Exception as e:
        st.error(f"⚠️ Erreur vérification session évacuation : {e}")
        return None


def fetch_presents_consolidated(site_id: str) -> list[dict]:
    """Extrait et consolide la présence courante (AEOS + Visiteurs ORBIS)."""
    liste = []

    # 1. Permanents AEOS
    try:
        res_aeos = (
            supabase.table("aeos_presence")
            .select("*")
            .eq("site_id", site_id)
            .execute()
        )
        for item in res_aeos.data or []:
            nom_aff = f"{item.get('nom', '')} {item.get('prenom', '')}".strip()
            if not nom_aff:
                nom_aff = item.get("nom_complet", "Inconnu")

            raw_type = str(item.get("type_personne", "Employé")).strip()
            is_presta = "PRESTA" in raw_type.upper()

            liste.append({
                "id_uid": f"AEOS_{item.get('id')}",
                "Source": "🏢 AEOS",
                "Nom & Prénom": nom_aff,
                "Service / Société": item.get("service", "DINUM"),
                "Catégorie": "Prestataire" if is_presta else "Employé",
                "Badge": "Permanent",
                "Ordre_Tri": 2 if is_presta else 1,
            })
    except Exception as err:
        st.error(f"Erreur chargement AEOS : {err}")

    # 2. Visiteurs ORBIS
    try:
        res_vis = (
            supabase.table("badges_temporaires")
            .select("*")
            .eq("site_id", site_id)
            .eq("statut", "EN_COURS")
            .execute()
        )
        for vis in res_vis.data or []:
            bdg = vis.get("num_badge", "Visiteur")
            liste.append({
                "id_uid": f"VIS_{vis.get('id')}",
                "Source": "✍️ ORBIS",
                "Nom & Prénom": vis.get("nom_porteur", "Visiteur Inconnu"),
                "Service / Société": vis.get("organisme", "Extérieur"),
                "Catégorie": "Visiteur / Livreur",
                "Badge": bdg,
                "Ordre_Tri": 3,
            })
    except Exception as err:
        st.error(f"Erreur chargement Visiteurs : {err}")

    # Tri : Employés -> Prestataires -> Visiteurs puis Nom
    liste.sort(key=lambda x: (x["Ordre_Tri"], x["Nom & Prénom"]))
    return liste


def enregistrer_main_courante(site_id: str, agent: str, titre: str, description: str):
    """Génère un enregistrement officiel dans la Main Courante ORBIS."""
    try:
        data_mc = {
            "site_id": site_id,
            "agent_auteur": agent,
            "categorie": "SECURITE",
            "titre": titre,
            "description": description,
            "horodatage": get_now_nc().isoformat(),
            "statut": "CLOTURE",
        }
        supabase.table("main_courante").insert(data_mc).execute()
    except Exception as e:
        print(f"Erreur injection Main Courante : {e}")


# =========================================================================
# 2. INTERFACE TERRAIN STREAMLIT (ORBIS-EVAC)
# =========================================================================
st.title("🚨 ORBIS-EVAC | Console de Crise & Pointage")

site_actif = st.session_state.get("site_actif", "DINUM")
agent_actif = st.session_state.get("user_profile", {}).get("full_name", "AGENT_TERRAIN")

session_active = get_session_evac_active(site_actif)

# -------------------------------------------------------------------------
# CAS A : AUCUNE ÉVACUATION EN COURS ➔ ÉCRAN DE VEILLE / DÉCLENCHEMENT
# -------------------------------------------------------------------------
if not session_active:
    # Rafraîchissement modéré en période de calme
    st_autorefresh(interval=15 * 1000, key="auto_refresh_idle")

    st.info("🟢 **SITUATION NORMALE** : Aucune session d'évacuation n'est actuellement ouverte.")

    presents_actuels = fetch_presents_consolidated(site_actif)
    st.metric("👥 Effectif total estimé sur site", f"{len(presents_actuels)} personnes")

    st.markdown("---")
    st.subheader("🔥 Déclencher une Alerte ou un Exercice")

    col1, col2 = st.columns(2)
    with col1:
        type_evt = st.selectbox("Type d'événement :", ["EXERCICE", "INCENDIE_REEL", "ALERTE_SURETE"])
    with col2:
        nom_agent_declencheur = st.text_input("Nom de l'agent / Responsable :", value=agent_actif)

    if st.button("🚨 OUVRIR LA SESSION D'ÉVACUATION", type="primary", use_container_width=True):
        now_iso = get_now_nc().isoformat()
        
        # Structure initiale du JSON de pointage { "id_uid": false }
        pointage_init = {p["id_uid"]: False for p in presents_actuels}

        new_session = {
            "site_id": site_actif,
            "type_event": type_evt,
            "statut": "EN_COURS",
            "agent_declencheur": nom_agent_declencheur,
            "date_debut": now_iso,
            "total_initial": len(presents_actuels),
            "pointage_json": pointage_init,
        }

        try:
            res_ins = supabase.table("evacuations_sessions").insert(new_session).execute()
            
            # Message automatique dans la Main Courante
            enregistrer_main_courante(
                site_id=site_actif,
                agent=nom_agent_declencheur,
                titre=f"🚨 DÉCLENCHEMENT ÉVACUATION ({type_evt})",
                description=f"Ouverture d'une session d'évacuation par {nom_agent_declencheur}. Effectif initial à pointer : {len(presents_actuels)} personnes."
            )
            st.success("✅ Session d'évacuation ouverte avec succès !")
            time.sleep(1)
            st.rerun()
        except Exception as err:
            st.error(f"Erreur lors de l'ouverture de session : {err}")

# -------------------------------------------------------------------------
# CAS B : ÉVACUATION EN COURS ➔ CONSOLE DE POINTAGE TERRAIN
# -------------------------------------------------------------------------
else:
    session_id = session_active["id"]

    # ⏱️ Rafraîchissement automatique toutes les 2 secondes pour faire défiler le chrono
    st_autorefresh(interval=2000, key=f"chrono_refresh_{session_id}")

    # Calcul du chronomètre dynamique
    date_debut = datetime.datetime.fromisoformat(session_active["date_debut"].replace("Z", "+00:00"))
    duree_sec = int((get_now_nc() - date_debut).total_seconds())
    minutes, secondes = divmod(duree_sec, 60)

    # Bandeau Rouge d'Alerte Active
    st.error(
        f"🚨 **ÉVACUATION EN COURS ({session_active['type_event']})** | "
        f"⏱️ Chrono : **{minutes:02d} min {secondes:02d} s** | "
        f"👤 Responsable : **{session_active['agent_declencheur']}**"
    )

    # Chargement du pointage initial enregistré en BDD
    pointage_db = session_active.get("pointage_json", {})
    presents_liste = fetch_presents_consolidated(site_actif)

    # Alignement du DataFrame avec les cases de la BDD
    for p in presents_liste:
        uid = p["id_uid"]
        p["Pointage 🟢"] = pointage_db.get(uid, False)

    df_presents = pd.DataFrame(presents_liste)

    # 🎯 RÉCUPÉRATION EN DIRECT DES MODIFICATIONS DU DATA EDITOR (EN MÉMOIRE VIVE)
    editor_key = f"editor_evac_{session_id}"
    edited_state = st.session_state.get(editor_key, {})
    edited_rows = edited_state.get("edited_rows", {})

    # Reconstruction dynamique du dictionnaire de pointage pour mise à jour instantanée des compteurs
    pointage_live = pointage_db.copy()
    for row_idx, changes in edited_rows.items():
        if "Pointage 🟢" in changes and row_idx < len(df_presents):
            uid_modifie = df_presents.iloc[row_idx]["id_uid"]
            pointage_live[uid_modifie] = bool(changes["Pointage 🟢"])

    # Calcul instantané des métriques sur la base des données "Live"
    total_site = len(df_presents)
    nb_pointes_live = sum(pointage_live.values())
    nb_restants_live = total_site - nb_pointes_live

    # Affichage des compteurs dynamiques
    c1, c2, c3 = st.columns(3)
    c1.metric("👥 Total à localiser", f"{total_site} pers.")
    c2.metric("🟢 Localisés au Rassemblement", f"{nb_pointes_live} pers.")
    c3.metric("🔴 NON LOCALISÉS", f"{nb_restants_live} pers.", delta=-nb_restants_live if nb_restants_live > 0 else 0)

    st.progress(nb_pointes_live / total_site if total_site > 0 else 0)

    st.markdown("---")

    # Recherche rapide par nom/service
    recherche = st.text_input("🔍 Recherche rapide sur le terrain :", placeholder="Nom, prénom ou service...")
    if recherche.strip():
        term = recherche.strip().upper()
        df_presents = df_presents[
            df_presents["Nom & Prénom"].str.upper().str.contains(term)
            | df_presents["Service / Société"].str.upper().str.contains(term)
        ]

    # Formulaire de pointage interactif
    st.markdown("### 📋 Formulaire de Pointage")
    
    df_editor = df_presents[["Pointage 🟢", "Source", "Nom & Prénom", "Service / Société", "Catégorie", "Badge", "id_uid"]]

    edited_df = st.data_editor(
        df_editor,
        column_config={
            "Pointage 🟢": st.column_config.CheckboxColumn("Présent", default=False),
            "id_uid": None,  # Masquer la colonne d'identifiant unique
        },
        disabled=["Source", "Nom & Prénom", "Service / Société", "Catégorie", "Badge"],
        hide_index=True,
        use_container_width=True,
        key=editor_key,
    )

    # Sauvegarde explicite vers la BDD Supabase
    if st.button("💾 Synchroniser le pointage avec la BDD Supabase", type="primary", use_container_width=True):
        try:
            supabase.table("evacuations_sessions").update({
                "pointage_json": pointage_live
            }).eq("id", session_id).execute()
            st.toast("✅ Pointage sauvegardé dans la BDD Supabase !", icon="💾")
            time.sleep(0.5)
            st.rerun()
        except Exception as err:
            st.error(f"Erreur de synchronisation Supabase : {err}")

    st.markdown("---")

    # -------------------------------------------------------------------------
    # CLÔTURE DE L'ÉVACUATION & RETEX
    # -------------------------------------------------------------------------
    with st.expander("✅ Clôturer la session d'évacuation (Fin d'alerte)"):
        st.warning("Attention : la clôture figera le bilan et enregistrera le rapport final dans la Main Courante.")
        if st.button("🏁 CLÔTURER L'ÉVACUATION MAINTENANT", type="primary", use_container_width=True):
            now_cloture = get_now_nc()
            
            # Extraction des personnes non localisées sur la base du pointage live
            non_loc = [p["Nom & Prénom"] for p in presents_liste if not pointage_live.get(p["id_uid"], False)]

            try:
                supabase.table("evacuations_sessions").update({
                    "statut": "CLOTUREE",
                    "date_fin": now_cloture.isoformat(),
                    "pointage_json": pointage_live,
                    "non_localises": non_loc,
                }).eq("id", session_id).execute()

                # Inscription du RETEX dans la Main Courante
                msg_retex = (
                    f"Fin d'évacuation ({session_active['type_event']}). "
                    f"Durée totale : {minutes} min {secondes} s. "
                    f"Bilan : {nb_pointes_live}/{total_site} personnes localisées au point de rassemblement. "
                    f"Non localisés ({len(non_loc)}) : {', '.join(non_loc[:5])}{'...' if len(non_loc) > 5 else ''}."
                )

                enregistrer_main_courante(
                    site_id=site_actif,
                    agent=session_active["agent_declencheur"],
                    titre=f"✅ FIN D'ÉVACUATION - BILAN ({nb_pointes_live}/{total_site})",
                    description=msg_retex,
                )

                st.success("🎉 Évacuation clôturée et rapport généré dans la Main Courante !")
                time.sleep(1.5)
                st.rerun()
            except Exception as err:
                st.error(f"Erreur lors de la clôture : {err}")