import sys
from pathlib import Path
import datetime
import zoneinfo
import streamlit as st
import pandas as pd
from utils.pdf_generator import generate_registre_pdf

# Fix pour assurer que Python trouve le dossier 'utils'
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from utils.db_client import supabase

# Fuseau horaire Nouvelle-Calédonie (UTC+11)
TZ_NC = zoneinfo.ZoneInfo("Pacific/Noumea")


@st.cache_data(ttl=600)
def fetch_sites_list() -> list[str]:
    """Récupère la liste dynamique des codes de sites depuis la table 'Sites' de Supabase."""
    try:
        res = supabase.table("Sites").select("nom_site").order("nom_site").execute()
        if res.data:
            sites_db = [item["nom_site"] for item in res.data if item.get("nom_site")]
            return ["Tous les sites"] + sites_db
    except Exception as e:
        st.warning(f"⚠️ Impossible de charger les sites depuis la BDD ({e}). Valeurs par défaut utilisées.")
    
    return ["Tous les sites", "DINUM", "DOUMER", "SITE OUEMO"]


def show(user_profile: dict = None):
    st.title("📖 Registre Général des Mains Courantes")

    # --- 1. RÉCUPÉRATION DU RÔLE ET PROFIL DEPUIS PARAMÈTRE OU SESSION ---
    if not user_profile:
        user_profile = st.session_state.get("user_profile", {})

    raw_role = user_profile.get("role") or st.session_state.get("role", "agent")
    user_site = user_profile.get("site_id") or st.session_state.get("site_actif", "DINUM")

    # Normalisation du rôle en minuscules et sans espaces superflus
    role_clean = str(raw_role).strip().lower()

    # Liste des rôles autorisés à consulter le registre
    roles_autorises = ["habilite", "charge_surete", "admin", "super_admin"]

    # --- 2. CONTRÔLE D'ACCÈS STRICT ---
    if role_clean not in roles_autorises:
        st.error(
            "⛔ Accès refusé : Vous n'avez pas les habilitations requises pour"
            " consulter le registre."
        )
        st.stop()

    # --- 3. SÉLECTION DU PÉRIMÈTRE DE CONSULTATION ---
    col_perm, _ = st.columns([2, 1])
    
    # Rôles ayant une vue globale / multi-sites
    roles_vue_globale = ["charge_surete", "admin", "super_admin"]

    # Chargement dynamique des codes de sites depuis la BDD
    liste_sites_disponibles = fetch_sites_list()

    with col_perm:
        if role_clean in roles_vue_globale:
            st.success("👤 **Supervision / Administration** — Vue globale multi-sites.")
            selected_site = st.selectbox(
                "📍 Périmètre d'observation :",
                liste_sites_disponibles,
            )
        else:
            st.info(
                "👤 **Personne Habilitée** — Consultation limitée au site"
                f" **{user_site}**."
            )
            selected_site = user_site

    st.markdown("---")

    # --- 4. BARRE DE FILTRES ET DE RECHERCHE ---
    aujourdhui_nc = datetime.datetime.now(TZ_NC).date()

    col_d1, col_d2, col_search = st.columns([1, 1, 2])
    with col_d1:
        date_debut = st.date_input(
            "Date de début",
            value=aujourdhui_nc - datetime.timedelta(days=7),
            format="DD/MM/YYYY",
        )
    with col_d2:
        date_fin = st.date_input(
            "Date de fin", 
            value=aujourdhui_nc,
            format="DD/MM/YYYY",
        )
    with col_search:
        search_query = st.text_input(
            "🔍 Recherche textuelle",
            placeholder="Ex: Fuite, Nom, Numéro MC...",
        )

    # Convertir en horodatages ISO avec fuseau horaire NC pour Supabase
    dt_start = datetime.datetime.combine(
        date_debut, datetime.time.min, tzinfo=TZ_NC
    ).isoformat()
    dt_end = datetime.datetime.combine(
        date_fin, datetime.time.max, tzinfo=TZ_NC
    ).isoformat()

    # --- 5. REQUÊTE SUPABASE ---
    try:
        query = (
            supabase.table("mc_evenements")
            .select("*")
            .gte("horodatage", dt_start)
            .lte("horodatage", dt_end)
            .order("horodatage", desc=True)
        )

        # Filtre de site si ce n'est pas "Tous les sites"
        if selected_site != "Tous les sites":
            query = query.eq("site_id", selected_site)

        response = query.execute()
        data = response.data

        if data:
            df = pd.DataFrame(data)

            # Filtre de recherche par mot-clé
            if search_query.strip():
                q = search_query.lower()
                df = df[
                    df["description"].astype(str).str.lower().str.contains(q, na=False)
                    | df["reference"].astype(str).str.lower().str.contains(q, na=False)
                    | df["agent_nom"].astype(str).str.lower().str.contains(q, na=False)
                    | df["type_evenement"].astype(str).str.lower().str.contains(q, na=False)
                ]

            if not df.empty:
                # Mise en forme du tableau de résultat
                st.subheader(
                    f"📊 Résultats de la recherche ({len(df)} événement(s))"
                )

                # Sélection et renommage des colonnes pour l'affichage
                df_display = df[
                    [
                        "horodatage",
                        "site_id",
                        "reference",
                        "agent_nom",
                        "type_evenement",
                        "description",
                        "actions_menees",
                        "notified_authority",
                    ]
                ].copy()

                df_display.columns = [
                    "Horodatage",
                    "Site",
                    "Référence",
                    "Agent",
                    "Type",
                    "Description",
                    "Actions",
                    "Alerte Émise",
                ]

                # Conversion flexible et tolérante des dates ISO vers l'heure NC
                df_display["Horodatage"] = (
                    pd.to_datetime(df_display["Horodatage"], errors="coerce")
                    .dt.tz_convert("Pacific/Noumea")
                    .dt.strftime("%d/%m/%Y %H:%M:%S")
                )

                st.dataframe(df_display, use_container_width=True)

                # --- 6. BOUTON D'EXPORTATION PDF ---
                st.markdown("---")

                # Formater les dates pour l'affichage
                d_start_str = date_debut.strftime("%d/%m/%Y")
                d_end_str = date_fin.strftime("%d/%m/%Y")

                # Génération du fichier PDF binaire à partir des données filtrées
                events_filtered = df.to_dict(orient="records")
                pdf_bytes = generate_registre_pdf(
                    events=events_filtered,
                    site_id=selected_site,
                    date_debut=d_start_str,
                    date_fin=d_end_str,
                )

                st.download_button(
                    label="📄 Exporter le registre au format PDF",
                    data=pdf_bytes,
                    file_name=(
                        f"registre_mc_{selected_site}_{date_debut}_au_{date_fin}.pdf"
                    ),
                    mime="application/pdf",
                    type="primary",
                )
            else:
                st.info("ℹ️ Aucun événement ne correspond à votre recherche textuelle.")
        else:
            st.info("ℹ️ Aucun événement trouvé pour la période sélectionnée.")

    except Exception as e:
        st.error(f"Erreur lors de la récupération du registre : {e}")