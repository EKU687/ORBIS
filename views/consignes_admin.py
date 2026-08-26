import sys
from pathlib import Path
import datetime
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
    ROLES_AUTORISES = ["ADMIN", "SUPER_ADMIN"]

    if role not in ROLES_AUTORISES:
        st.error(
            "⛔ Accès restreint : Seuls les administrateurs "
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

        # Hauteur bloquée à 320px pour un rendu compact et propre
        with st.container(height=320):
            for csg in consignes_actives:
                prio = csg.get("priorite", "NORMALE")
                badge = "🔴 URGENT" if prio == "URGENTE" else "🔵 CONSIGNE"

                col_txt, col_act = st.columns([4, 1])
                with col_txt:
                    st.markdown(
                        f"**{badge} [{csg['reference']}] {csg['titre']}**"
                    )
                    st.write(f"└ {csg['description']}")
                    st.caption(
                        f"Créée par **{csg['cree_par']}** le"
                        f" {csg['created_at'][:10]} | Expire le :"
                        f" **{csg['fin_at'][:10]}**"
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

    # --- 4. FORMULAIRE DE CRÉATION D'UNE CONSIGNE ---
    st.subheader("➕ Rédiger une nouvelle consigne temporaire")

    aujourdhui_nc = get_now_nc().date()

    with st.form("form_add_consigne", clear_on_submit=True):
        titre = st.text_input(
            "Titre de la consigne *",
            placeholder=(
                "Ex: Livraison d'équipement zone Nord, Présence VIP..."
            ),
        )

        col_prio, col_d1, col_d2 = st.columns([1, 1, 1])
        with col_prio:
            priorite = st.selectbox("Priorité", ["NORMALE", "URGENTE"])
        with col_d1:
            date_debut = st.date_input(
                "Date de début",
                value=aujourdhui_nc,
                format="DD/MM/YYYY",  # Format Français
            )
        with col_d2:
            date_fin = st.date_input(
                "Date de fin (Expiration)",
                value=aujourdhui_nc + datetime.timedelta(days=7),
                format="DD/MM/YYYY",  # Format Français
            )

        description = st.text_area(
            "Consigne détaillée pour les agents *",
            placeholder=(
                "Précisez les conduites à tenir, contacts utiles, contrôles"
                " spécifiques..."
            ),
        )

        submitted = st.form_submit_button(
            "💾 Publier la consigne site", use_container_width=True
        )

        if submitted:
            if not titre.strip() or not description.strip():
                st.error(
                    "Le titre et le texte de la consigne sont obligatoires."
                )
            elif date_fin < date_debut:
                st.error(
                    "La date de fin ne peut pas être antérieure à la date de"
                    " début."
                )
            else:
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
                }

                try:
                    supabase.table("consignes").insert(payload).execute()
                    st.success(
                        f"Consigne **{csg_ref}** enregistrée et publiée pour"
                        f" le site {site_actuel} !"
                    )
                    st.rerun()
                except Exception as e:
                    st.error(f"Erreur d'enregistrement : {e}")