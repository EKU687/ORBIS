# =========================================================================
# MODULE : ADMINISTRATION DES CONSIGNES (views/consignes_admin.py)
# Inclus : Publication globale ou ciblée par agent, gestion des priorités,
#          dates de validité et archivage BDD Supabase.
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

# Fuseau horaire Nouvelle-Calédonie (UTC+11)
TZ_NC = zoneinfo.ZoneInfo("Pacific/Noumea")


def get_now_nc() -> datetime.datetime:
    """Retourne la date et l'heure actuelles en Nouvelle-Calédonie."""
    return datetime.datetime.now(TZ_NC)


def generate_id(prefix: str) -> str:
    """Génère un identifiant horodaté unique basé sur l'heure locale NC."""
    now = get_now_nc()
    return f"{prefix}-{now.strftime('%Y%m%d-%H%M%S')}"


@st.cache_data(ttl=300)
def fetch_liste_utilisateurs() -> list[dict]:
    """Récupère la liste des agents/utilisateurs enregistrés dans Supabase pour le ciblage."""
    try:
        res = (
            supabase.table("Utilisateur")
            .select("login, nom")
            .order("nom")
            .execute()
        )
        return res.data or []
    except Exception as e:
        print(f"⚠️ Erreur chargement liste Utilisateurs : {e}")
        return []


def show(user_profile: dict | None = None):
    st.title("⚙️ Consignes Particulières & Temporaires (Admin)")

    # Récupération sécurisée du profil utilisateur
    if not user_profile:
        user_profile = st.session_state.get("user_profile", {})

    site_actuel = st.session_state.get("site_actif", "DINUM")
    raw_role = user_profile.get("role") or st.session_state.get("role", "AGENT_SECU")
    role = str(raw_role).upper().strip()
    agent_nom = user_profile.get("full_name") or st.session_state.get("full_name", "Responsable")

    # --- 1. CONTRÔLE D'ACCÈS (RESTRICTION STRICTE ADMIN) ---
    ROLES_AUTORISES = ["ADMIN", "SUPER_ADMIN", "CHARGE_SURETE", "COS"]

    if role not in ROLES_AUTORISES:
        st.error(
            "⛔ Accès restreint : Seuls les administrateurs et responsables de sûreté "
            "peuvent gérer les consignes particulières du site."
        )
        st.stop()

    st.markdown(f"### 📍 Consignes en cours sur le site **{site_actuel}**")

    # --- 2. LECTURE DES CONSIGNES ACTIVES ---
    now_iso = get_now_nc().isoformat()
    try:
        res = (
            supabase.table("consignes")
            .select("*")
            .eq("site_id", site_actuel)
            .eq("statut", "ACTIVE")
            .gte("fin_at", now_iso)
            .order("created_at", desc=True)
            .execute()
        )

        consignes_actives = res.data if res.data else []
    except Exception as e:
        st.error(f"Erreur de chargement des consignes : {e}")
        consignes_actives = []

    # --- 3. AFFICHAGE DANS UN CONTENEUR À HAUTEUR FIXE (ASCENSEUR) ---
    if consignes_actives:
        st.info(
            f"📋 **{len(consignes_actives)} consigne(s) temporaire(s)"
            f" active(s)** sur ce site."
        )

        with st.container(height=320):
            for csg in consignes_actives:
                prio = csg.get("priorite", "NORMALE")
                badge = "🔴 URGENT" if prio == "URGENTE" else "🔵 CONSIGNE"

                # Détermination du libellé de ciblage
                destinataires = csg.get("destinataires") or ["TOUS"]
                if "TOUS" in destinataires:
                    cible_txt = "📢 Tous les agents"
                else:
                    cible_txt = f"🎯 {len(destinataires)} agent(s) spécifique(s) ({', '.join(destinataires)})"

                col_txt, col_act = st.columns([4, 1])
                with col_txt:
                    st.markdown(
                        f"**{badge} [{csg['reference']}] {csg['titre']}**"
                    )
                    st.write(f"└ {csg['description']}")
                    st.caption(
                        f"Créée par **{csg['cree_par']}** le"
                        f" {csg['created_at'][:10]} | Expire le :"
                        f" **{csg['fin_at'][:10]}** | **Cible :** `{cible_txt}`"
                    )

                with col_act:
                    if st.button(
                        "📥 Archiver",
                        key=f"btn_arch_{csg['id']}",
                        use_container_width=True,
                    ):
                        try:
                            supabase.table("consignes").update(
                                {"statut": "ARCHIVEE"}
                            ).eq("id", csg["id"]).execute()
                            st.toast("Consigne archivée !", icon="✅")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erreur : {e}")
                st.markdown("---")
    else:
        st.success("✅ Aucune consigne particulière active sur ce site.")

    st.markdown("---")

    # --- 4. FORMULAIRE DE CRÉATION D'UNE CONSIGNE CIBLÉE ---
    st.subheader("➕ Rédiger une nouvelle consigne temporaire")

    aujourdhui_nc = get_now_nc().date()
    liste_utilisateurs = fetch_liste_utilisateurs()

    # Formattage des options pour le multiselect (Nom + Login)
    options_agents = ["📢 TOUS LES AGENTS"] + [
        f"{u.get('nom', 'Agent')} ({u.get('login')})"
        for u in liste_utilisateurs
        if u.get("login")
    ]

    with st.form("form_add_consigne", clear_on_submit=True):
        titre = st.text_input(
            "Titre de la consigne *",
            placeholder=(
                "Ex: Livraison d'équipement zone Nord, Consigne Poste Après-Midi..."
            ),
        )

        col_prio, col_d1, col_d2 = st.columns([1, 1, 1])
        with col_prio:
            priorite = st.selectbox("Priorité", ["NORMALE", "URGENTE"])
        with col_d1:
            date_debut = st.date_input(
                "Date de début",
                value=aujourdhui_nc,
                format="DD/MM/YYYY",
            )
        with col_d2:
            date_fin = st.date_input(
                "Date de fin (Expiration)",
                value=aujourdhui_nc + datetime.timedelta(days=7),
                format="DD/MM/YYYY",
            )

        # 🎯 SÉLECTEUR DE DESTINATAIRES (GLOBAL OU AGENT(S) SPÉCIFIQUE(S))
        destinataires_selectionnes = st.multiselect(
            "🎯 Destinataire(s) de la consigne :",
            options=options_agents,
            default=["📢 TOUS LES AGENTS"],
            help="Sélectionnez 'TOUS LES AGENTS' pour une consigne globale site, ou désélectionnez pour cibler des agents spécifiques.",
        )

        description = st.text_area(
            "Consigne détaillée pour les agents *",
            placeholder=(
                "Précisez les conduites à tenir, contacts utiles, contrôles"
                " spécifiques..."
            ),
        )

        submitted = st.form_submit_button(
            "💾 Publier la consigne", use_container_width=True, type="primary"
        )

        if submitted:
            if not titre.strip() or not description.strip():
                st.error(
                    "Le titre et le texte de la consigne sont obligatoires."
                )
            elif date_fin < date_debut:
                st.error(
                    "La date de fin ne peut pas être antérieure à la date de début."
                )
            elif not destinataires_selectionnes:
                st.error(
                    "⚠️ Veuillez sélectionner au moins un destinataire (ou 'TOUS LES AGENTS')."
                )
            else:
                # Traitement et extraction des logins cibles
                if "📢 TOUS LES AGENTS" in destinataires_selectionnes:
                    destinataires_final = ["TOUS"]
                else:
                    # Extraction du login situé entre parenthèses
                    destinataires_final = [
                        item.split("(")[-1].replace(")", "").strip().lower()
                        for item in destinataires_selectionnes
                        if "(" in item
                    ]

                csg_ref = generate_id("CSG")
                dt_start = datetime.datetime.combine(
                    date_debut, datetime.time.min, tzinfo=TZ_NC
                ).isoformat()
                dt_end = datetime.datetime.combine(
                    date_fin, datetime.time.max, tzinfo=TZ_NC
                ).isoformat()

                payload = {
                    "reference": csg_ref,
                    "site_id": site_actuel,
                    "titre": titre,
                    "description": description,
                    "debut_at": dt_start,
                    "fin_at": dt_end,
                    "priorite": priorite,
                    "statut": "ACTIVE",
                    "cree_par": agent_nom,
                    "destinataires": destinataires_final,  # Enregistré dans Supabase
                }

                try:
                    supabase.table("consignes").insert(payload).execute()
                    st.success(
                        f"Consigne **{csg_ref}** enregistrée et publiée avec succès !"
                    )
                    st.rerun()
                except Exception as e:
                    st.error(f"Erreur d'enregistrement Supabase : {e}")