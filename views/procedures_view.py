# views/procedures_view.py
"""
Vue ORBIS : Consultation du Référentiel Documentaire OPERA (Procédures & Rondes) en lecture seule.
"""

import streamlit as st
from utils.opera_bridge import (
    charger_procedures_actives_site,
    charger_rondes_actives_site,
    resoudre_site_uuid,
)


def afficher_page_procedures_opera(supabase_client, site_courant: str):
    st.title("📚 Référentiel Documentaire & Rondes du Site")
    st.caption("Référentiel officiel issu de l'application OPERA (Lecture seule).")

    site_uuid = resoudre_site_uuid(supabase_client, site_courant)

    # Chargement parallèle des deux sources de données OPERA
    procedures = charger_procedures_actives_site(supabase_client, site_courant)
    rondes = charger_rondes_actives_site(supabase_client, site_courant)

    if not procedures and not rondes:
        st.info(
            f"ℹ️ Aucune procédure ni ronde active répertoriée pour le site **{site_courant}**."
        )
        return

    # Barre de recherche rapide globale
    recherche = st.text_input(
        "🔍 Rechercher une procédure, une ronde ou un mot-clé :",
        placeholder="ex: Ronde, Incendie, D07, Fermeture...",
    )

    st.markdown("---")

    # Organisation sous deux onglets métiers
    tab_proc, tab_rondes = st.tabs(
        [
            f"📜 Procédures & Protocoles ({len(procedures)})",
            f"🧭 Rondes & Patrouilles ({len(rondes)})",
        ]
    )

    # =========================================================================
    # ONGLET 1 : PROCÉDURES & FICHES RÉFLEXES (opera_procedures)
    # =========================================================================
    with tab_proc:
        if not procedures:
            st.info("Aucune fiche de procédure enregistrée.")
        else:
            for proc in procedures:
                code_doc = proc.get("code_doc", "PROC")
                titre = proc.get("titre", "Procédure Sans Titre")
                version = proc.get("version", "1.0")
                date_v = proc.get("date_version", "N/C")
                objectif = proc.get("objectif", "Non renseigné.")
                deroulement = proc.get("deroulement", [])
                points_vigilance = proc.get("points_vigilance")

                # Filtre de recherche
                if (
                    recherche
                    and recherche.lower()
                    not in f"{code_doc} {titre} {objectif}".lower()
                ):
                    continue

                label_expander = (
                    f"📄 [{code_doc}] {titre} — Version {version} (du {date_v})"
                )

                with st.expander(label_expander, expanded=False):
                    st.markdown(f"**🎯 Objectif :** {objectif}")

                    if proc.get("domaine_application"):
                        st.markdown(
                            "**📍 Domaine d'application :**"
                            f" {proc['domaine_application']}"
                        )

                    if proc.get("materiel_requis"):
                        st.info(f"🧰 **Matériel requis :** {proc['materiel_requis']}")

                    st.markdown("#### 📋 Déroulement / Étapes de la procédure")

                    if isinstance(deroulement, list) and len(deroulement) > 0:
                        for idx, step in enumerate(deroulement, start=1):
                            code_step = step.get("code", f"STEP-{idx:02d}")
                            action = (
                                step.get("action")
                                or step.get("consigne")
                                or "Action non spécifiée"
                            )
                            zone = step.get("zone", "N/A")

                            st.markdown(
                                f"**{idx}. `{code_step}` — Zone `{zone}`** :"
                                f" {action}"
                            )
                    else:
                        st.text("Aucun déroulement détaillé renseigné.")

                    if points_vigilance:
                        st.warning(f"⚠️ **Points de vigilance :** {points_vigilance}")

                    st.caption(
                        f"✍️ Rédacteur : {proc.get('redacteur', 'Sûreté')} | ID"
                        f" Document : `{proc['id']}`"
                    )

    # =========================================================================
    # ONGLET 2 : RONDES TERRAIN & SECTEURS (opera_missions)
    # =========================================================================
    with tab_rondes:
        if not rondes:
            st.info("Aucune ronde ou patrouille configurée dans OPERA.")
        else:
            for mis in rondes:
                titre_mission = mis.get("titre_mission", "Ronde Terrain")
                horaire = mis.get("horaire_cible", "Horaire non spécifié")
                secteurs = mis.get("opera_secteurs", [])

                # Filtre de recherche sur les rondes
                if (
                    recherche
                    and recherche.lower() not in f"{titre_mission} {horaire}".lower()
                ):
                    # Recherche étendue dans le nom des secteurs et consignes
                    mots_clefs_secteurs = " ".join(
                        [s.get("nom_secteur", "") for s in secteurs]
                    )
                    if recherche.lower() not in mots_clefs_secteurs.lower():
                        continue

                label_ronde = f"🕒 {titre_mission} (Créneau : {horaire})"

                with st.expander(label_ronde, expanded=False):
                    st.markdown(f"**🧭 Titre de la mission :** {titre_mission}")

                    # Tri des secteurs par ordre de passage
                    secteurs_tries = sorted(
                        secteurs, key=lambda x: x.get("ordre_passage", 1)
                    )

                    if secteurs_tries:
                        st.markdown("#### 🏢 Parcours Séquentiel par Secteur :")
                        for sec in secteurs_tries:
                            ordre = sec.get("ordre_passage", 1)
                            nom_sec = sec.get("nom_secteur", "Secteur Inconnu")
                            st.markdown(f"**Secteur {ordre} : {nom_sec}**")

                            consignes = sorted(
                                sec.get("opera_consignes", []),
                                key=lambda x: x.get("ordre_execution", 1),
                            )

                            if consignes:
                                for con in consignes:
                                    type_act = con.get("type_action", "Vérification")
                                    desc = con.get("description", "Pas de description")
                                    icone = (
                                        "🔒"
                                        if "fermeture" in type_act.lower()
                                        or "verrou" in type_act.lower()
                                        else "👁️"
                                    )
                                    st.write(f"  • {icone} **[{type_act}]** {desc}")
                            else:
                                st.caption("  *Aucune consigne spécifique.*")
                    else:
                        st.text("Aucun secteur configuré pour cette ronde.")

                    st.caption(f"ID Mission OPERA : `{mis['id']}`")
