# utils/opera_bridge.py
"""
Module d'interfaçage ORBIS <-> OPERA.
Gère la détection des mises à jour de procédures OPERA, la résolution des UUID de sites,
l'affichage des deltas dans la modale de prise de poste et l'enregistrement de l'émargement.

Auteur : Éric KUTER
Date de révision : 28/09/2026
"""

import re
from typing import Dict, List, Optional
import streamlit as st
from supabase import Client


def est_uuid_valide(val: str) -> bool:
    """Vérifie si une chaîne correspond au format UUID standard (v4/v5)."""
    uuid_pattern = re.compile(
        r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
    )
    return bool(uuid_pattern.match(str(val)))


def resoudre_site_uuid(supabase_client: Client, site_input: str) -> Optional[str]:
    """Convertit un nom de site (ex: 'SITE OUEMO' ou 'OUEMO') en UUID Supabase OPERA.

    Extrait les mots-clés significatifs pour tolérer les préfixes comme 'SITE'.
    """
    if not site_input:
        return None

    if est_uuid_valide(site_input):
        return site_input

    try:
        # 1. Recherche directe par ilike
        res = (
            supabase_client.table("opera_sites")
            .select("id")
            .ilike("nom_site", f"%{site_input}%")
            .execute()
        )
        if res.data and len(res.data) > 0:
            return res.data[0]["id"]

        # 2. Découpage par mots-clés pour ignorer les mots génériques ("SITE", "ZONE")
        mots = [
            m
            for m in site_input.split()
            if len(m) > 3 and m.upper() not in ["SITE", "BATIMENT", "ZONE", "POSTE"]
        ]
        for mot in mots:
            res_mot = (
                supabase_client.table("opera_sites")
                .select("id")
                .ilike("nom_site", f"%{mot}%")
                .execute()
            )
            if res_mot.data and len(res_mot.data) > 0:
                return res_mot.data[0]["id"]

    except Exception as err:
        print(f"⚠️ Erreur de résolution UUID site OPERA : {err}")

    return None


def verifier_deltas_opera_non_lus(
    supabase_client: Client, site_id: str, agent_login: str
) -> List[Dict]:
    """Interroge la BDD OPERA pour identifier les notifications de procédures

    actives non encore émargées par l'agent connecté.
    """
    try:
        site_uuid = resoudre_site_uuid(supabase_client, site_id)
        if not site_uuid:
            return []

        # Récupération des notifications actives pour ce site
        res_notifs = (
            supabase_client.table("opera_orbis_notifications")
            .select("*, opera_procedures(code_doc, titre)")
            .eq("site_id", site_uuid)
            .eq("est_active", True)
            .execute()
        )

        notifs_actives = res_notifs.data or []
        deltas_a_emarger = []

        agent_clean = str(agent_login).strip()

        for notif in notifs_actives:
            procedure_id = notif["procedure_id"]
            version_cible = str(notif["version_cible"]).strip()

            # Vérification rigoureuse dans 'opera_emargements'
            res_emargement = (
                supabase_client.table("opera_emargements")
                .select("id")
                .eq("procedure_id", procedure_id)
                .eq("version_emargee", version_cible)
                .eq("agent_login", agent_clean)
                .execute()
            )

            if not res_emargement.data:
                deltas_a_emarger.append(notif)

        return deltas_a_emarger

    except Exception as err:
        st.error(f"⚠️ Erreur lors du contrôle des procédures OPERA : {err}")
        return []


def enregistrer_emargement_procedure_opera(
    supabase_client: Client,
    procedure_id: str,
    version_emargee: str,
    agent_login: str,
    agent_nom: str,
    site_id: str,
    vacation_ref: Optional[str] = None,
) -> bool:
    """Enregistre l'émargement légal de l'agent dans la table 'opera_emargements'.

    Vérifie au préalable si l'émargement n'est pas déjà présent pour éviter les doublons.
    """
    try:
        site_uuid = resoudre_site_uuid(supabase_client, site_id) or site_id
        version_clean = str(version_emargee).strip()
        agent_clean = str(agent_login).strip()

        # 1. Vérification d'existence
        check_exist = (
            supabase_client.table("opera_emargements")
            .select("id")
            .eq("procedure_id", procedure_id)
            .eq("version_emargee", version_clean)
            .eq("agent_login", agent_clean)
            .execute()
        )

        if check_exist.data:
            return True  # Déjà émargé

        # 2. Insertion de la preuve d'émargement
        payload = {
            "procedure_id": procedure_id,
            "version_emargee": version_clean,
            "agent_login": agent_clean,
            "agent_nom": agent_nom,
            "site_id": site_uuid,
            "orbis_vacation_ref": vacation_ref,
        }

        supabase_client.table("opera_emargements").insert(payload).execute()
        return True

    except Exception as err:
        st.error(f"❌ Erreur lors de l'enregistrement de l'émargement OPERA : {err}")
        return False


def afficher_section_deltas_opera_dans_modale(
    supabase_client: Client,
    deltas_non_lus: List[Dict],
    agent_login: str,
    agent_nom: str,
    site_id: str,
    vacation_ref: Optional[str] = None,
) -> bool:
    """Affiche le composant d'UI Streamlit avec le résumé des modifications de procédures.

    Enregistre les émargements en BDD lors de la validation et rafraîchit l'IHM.
    """
    if not deltas_non_lus:
        return True

    st.warning("🚨 **MODIFICATIONS DE PROCÉDURES / RONDES DE SÛRETÉ (OPERA)**")
    st.caption(
        "Des consignes opérationnelles ou étapes de rondes ont été mises à jour par la Sûreté. "
        "Vous devez en prendre connaissance pour démarrer votre service."
    )

    notifications_coch_ees = []

    for notif in deltas_non_lus:
        proc_info = notif.get("opera_procedures") or {}
        code_doc = proc_info.get("code_doc") or "PROC"
        titre_proc = proc_info.get("titre") or notif.get(
            "titre_notification", "Procédure Opérationnelle"
        )
        version_cible = notif.get("version_cible", "1.0")
        resume_delta = notif.get("resume_delta", "Mise à jour de la fiche.")

        with st.container(border=True):
            st.subheader(f"📋 {code_doc} — {titre_proc} (Version {version_cible})")

            st.markdown(
                f"""
                <div style="background-color: #e8f4f8; border-left: 5px solid #0288d1; padding: 12px; border-radius: 4px; margin: 10px 0;">
                    <b style="color: #01579b;">📌 Éléments modifiés / Nouveaux points de contrôle :</b><br>
                    <span style="color: #212121; font-size: 1.05em;">{resume_delta}</span>
                </div>
                """,
                unsafe_allow_html=True,
            )

            cle_checkbox = f"chk_emarge_{notif['id']}"
            est_coche = st.checkbox(
                f"J'atteste avoir lu et assimilé la modification (v{version_cible})",
                key=cle_checkbox,
            )

            if est_coche:
                notifications_coch_ees.append(notif)

    tous_emarges = len(notifications_coch_ees) == len(deltas_non_lus)

    # Bouton de validation d'émargement explicite si tous les deltas sont cochés
    if notifications_coch_ees:
        if st.button(
            "✍️ Valider mes émargements OPERA", type="primary", use_container_width=True
        ):
            succes_total = True
            for notif_a_valider in notifications_coch_ees:
                ok = enregistrer_emargement_procedure_opera(
                    supabase_client=supabase_client,
                    procedure_id=notif_a_valider["procedure_id"],
                    version_emargee=notif_a_valider["version_cible"],
                    agent_login=agent_login,
                    agent_nom=agent_nom,
                    site_id=site_id,
                    vacation_ref=vacation_ref,
                )
                if not ok:
                    succes_total = False

            if succes_total:
                st.success("✅ Prise de connaissance enregistrée avec succès.")
                st.rerun()  # Réactualise la page : le compteur repasse à 0 !

    return tous_emarges


def charger_procedures_actives_site(
    supabase_client: Client, site_id: str
) -> List[Dict]:
    """Récupère l'ensemble des procédures et rondes actives destinées au site concerné."""
    try:
        site_uuid = resoudre_site_uuid(supabase_client, site_id)
        if not site_uuid:
            return []

        res = (
            supabase_client.table("opera_procedures")
            .select("*")
            .eq("site_id", site_uuid)
            .eq("est_actif", True)
            .order("code_doc")
            .execute()
        )
        return res.data or []

    except Exception as err:
        st.error(f"⚠️ Erreur lors du chargement des procédures OPERA : {err}")
        return []


def charger_rondes_actives_site(supabase_client, site_courant: str) -> list:
    """
    Charge l'arborescence complète des rondes (opera_missions -> opera_secteurs -> opera_consignes)
    pour un site donné depuis la BDD OPERA.
    """
    site_uuid = resoudre_site_uuid(supabase_client, site_courant)
    if not site_uuid:
        return []

    try:
        res = (
            supabase_client.table("opera_missions")
            .select("*, opera_secteurs(*, opera_consignes(*))")
            .eq("site_id", site_uuid)
            .eq("est_actif", True)
            .execute()
        )
        return res.data or []
    except Exception as e:
        print(f"⚠️ Erreur chargement rondes OPERA : {e}")
        return []
