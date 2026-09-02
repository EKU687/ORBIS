# =========================================================================
# MODULE : CONSULTATION RÉFÉRENTIEL PRESTATAIRES (views/recherche_prestataires.py)
# Inclus : Interrogation Supabase, conversion des UUIDs (Sites & Sociétés),
#          affichage du statut terrain et intégration dynamique de la Société.
# =========================================================================
import datetime
from pathlib import Path
import sys
import pandas as pd
import streamlit as st

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from utils.db_client import supabase


def format_date_fr(date_str: str) -> str:
    """Transforme une date ISO (AAAA-MM-JJ) au format français (JJ/MM/AAAA)."""
    if not date_str:
        return "Non renseignée"
    try:
        clean_date = date_str.split("T")[0]
        dt = datetime.datetime.strptime(clean_date, "%Y-%m-%d")
        return dt.strftime("%d/%m/%Y")
    except Exception:
        return str(date_str)


@st.cache_data(ttl=300)
def get_sites_dict() -> dict:
    """Récupère la correspondance UUID -> nom_site depuis la table 'Sites'."""
    try:
        res = supabase.table("Sites").select("id, nom_site").execute()
        if res.data:
            return {item["id"]: item["nom_site"] for item in res.data}
    except Exception:
        pass
    return {}


@st.cache_data(ttl=300)
def get_societes_dict() -> dict:
    """🎯 Récupère la correspondance UUID (id) -> nom_societe depuis la table 'Societes'."""
    try:
        res = supabase.table("Societes").select("id, nom_societe").execute()
        if res.data:
            return {item["id"]: item["nom_societe"] for item in res.data}
    except Exception as e:
        print(f"⚠️ Erreur chargement table Societes : {e}")
    return {}


def resolve_sites_names(sites_raw, sites_map: dict) -> str:
    """Convertit un ou plusieurs UUIDs de sites en leurs noms lisibles."""
    if not sites_raw:
        return "Non spécifié"

    if isinstance(sites_raw, list):
        uuids = sites_raw
    else:
        uuids = [s.strip() for s in str(sites_raw).split(",") if s.strip()]

    names = [sites_map.get(u, u) for u in uuids]
    return ", ".join(names)


def show():
    st.title("🔍 Consultation Référentiel Prestataires (IDENTIS)")
    st.caption(
        "Module en **lecture seule** — Contrôle des habilitations et accès"
        " intervenants."
    )

    site_actuel = st.session_state.get("site_actif", "DINUM")
    today = datetime.date.today()
    
    # Chargement des tables de correspondance (Cache 5 min)
    sites_map = get_sites_dict()
    societes_map = get_societes_dict()

    # --- 1. BARRE DE RECHERCHE ET FILTRES ---
    col_search, col_statut, col_badge = st.columns([2, 1, 1])

    with col_search:
        query_nom = st.text_input(
            "🔎 Nom, Prénom ou Identifiant (ID Ident) :",
            placeholder="Ex: ARAMION, PRES-2026...",
        )
    with col_statut:
        filter_statut = st.selectbox(
            "🛡️ Statut d'accès terrain :",
            ["TOUS", "AUTORISE", "EN_ATTENTE", "SUSPENDU", "EXPIRE"],
        )
    with col_badge:
        filter_badge = st.selectbox(
            "🏷️ Type de badge :",
            ["TOUS", "PERMANENT", "TEMPORAIRE", "VISITEUR"],
        )

    st.markdown("---")

    # --- 2. REQUÊTE SUPABASE DYNAMIQUE ---
    try:
        req = supabase.table("Prestataires").select("*")

        if query_nom.strip():
            req = req.or_(
                f"nom.ilike.%{query_nom}%,prenom.ilike.%{query_nom}%,id_ident.ilike.%{query_nom}%"
            )

        if filter_badge != "TOUS":
            req = req.eq("type_badge", filter_badge)

        res = req.order("nom", desc=False).execute()
        prestataires = res.data if res.data else []

    except Exception as e:
        st.error(f"Erreur d'interrogation de la base IDENTIS : {e}")
        prestataires = []

    # --- 3. AFFICHAGE DES RÉSULTATS ---
    if prestataires:
        results_to_display = []

        for p in prestataires:
            statut_raw = (p.get("statut") or "INCONNU").upper()
            dt_fin_raw = p.get("date_fin_prestation")

            is_expired = False
            if dt_fin_raw:
                try:
                    dt_fin_obj = datetime.datetime.strptime(
                        dt_fin_raw.split("T")[0], "%Y-%m-%d"
                    ).date()
                    if dt_fin_obj < today:
                        is_expired = True
                except Exception:
                    pass

            if statut_raw in ["SUSPENDU", "INTERDIT", "BLOQUE"]:
                status_key = "SUSPENDU"
                badge = "🔴 **ACCÈS INTERDIT / SUSPENDU**"
            elif is_expired:
                status_key = "EXPIRE"
                badge = "🟠 **PRESTATION EXPIRÉE**"
            elif statut_raw in [
                "CLOTURE",
                "CLÔTURÉ",
                "VALIDE",
                "AUTORISE",
                "ACTIF",
            ]:
                status_key = "AUTORISE"
                badge = "🟢 **ACCÈS AUTORISÉ (DOSSIER VALIDÉ)**"
            elif statut_raw in ["EN_ATTENTE", "ATTENTE"]:
                status_key = "EN_ATTENTE"
                badge = "🔵 **EN ATTENTE DE VALIDATION**"
            else:
                status_key = "AUTRE"
                badge = f"⚪ **{statut_raw}**"

            p["computed_badge"] = badge
            p["computed_status"] = status_key

            if filter_statut == "TOUS" or filter_statut == status_key:
                results_to_display.append(p)

        st.subheader(f"📋 {len(results_to_display)} prestataire(s) trouvé(s)")

        if results_to_display:
            with st.container(height=420):
                for p in results_to_display:
                    dt_debut = format_date_fr(p.get("date_debut_validite"))
                    dt_fin = format_date_fr(p.get("date_fin_prestation"))

                    hab = p.get("niveau_habilitation") or "Standard"
                    badge_type = p.get("type_badge") or "Non défini"
                    ref_id = p.get("id_ident") or "N/A"

                    # 🎯 Résolution de l'id_societe vers le nom_societe
                    id_soc = p.get("id_societe")
                    nom_societe = (
                        societes_map.get(id_soc)
                        or p.get("societe")
                        or p.get("organisme")
                        or "Non renseignée"
                    )

                    # Résolution des UUIDs vers le nom_site lisible
                    sites_raw = (
                        p.get("id_sites")
                        or p.get("id_site")
                        or p.get("site_autorise")
                    )
                    sites_display = resolve_sites_names(sites_raw, sites_map)

                    # Entête enrichie avec le nom de la société résolu
                    title_expander = (
                        f"{p['computed_badge']} — **{p['nom'].upper()}"
                        f" {p['prenom']}** (*{nom_societe}*) (ID: `{ref_id}`)"
                    )

                    with st.expander(title_expander, expanded=False):
                        c1, c2, c3 = st.columns(3)

                        with c1:
                            st.write(f"**Identifiant IDENTIS :** `{ref_id}`")
                            st.write(
                                "🏢 **Société / Entreprise :**"
                                f" **{nom_societe}**"
                            )
                            st.write(
                                "**Téléphone :**"
                                f" {p.get('telephone') or 'N/A'}"
                            )
                            st.write(f"**Email :** {p.get('email') or 'N/A'}")

                        with c2:
                            st.write(f"**Type de badge :** `{badge_type}`")
                            st.write(f"**Habilitation :** `{hab}`")
                            st.write(
                                "**Site(s) autorisé(s) :**"
                                f" `{sites_display}`"
                            )
                            st.write(
                                "**Agent référent GNC :**"
                                f" {p.get('agent_referent_gnc') or 'Non défini'}"
                            )

                        with c3:
                            st.write(f"**Début validité :** {dt_debut}")
                            st.write(f"**Fin prestation :** `{dt_fin}`")
                            st.caption(
                                "Statut IDENTIS d'origine :"
                                f" {p.get('statut')}"
                            )

        else:
            st.info(
                "🔍 Aucun prestataire ne correspond au statut d'accès"
                " sélectionné."
            )
    else:
        st.info("🔍 Aucun prestataire trouvé dans la base.")