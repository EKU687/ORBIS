import sys
from pathlib import Path
import datetime
import streamlit as st
import pandas as pd
from utils.pdf_generator import generate_registre_pdf

# Fix pour assurer que Python trouve le dossier 'utils'
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from utils.db_client import supabase


def show(user_profile: dict):
    st.title("📖 Registre Général des Mains Courantes")

    role = user_profile.get("role", "agent")
    user_site = user_profile.get("site_id", "DINUM")

    # --- 1. CONTRÔLE D'ACCÈS STRICT ---
    if role not in ["habilite", "charge_surete"]:
        st.error(
            "⛔ Accès refusé : Vous n'avez pas les habilitations requises pour"
            " consulter le registre."
        )
        st.stop()

    # --- 2. SÉLECTION DU PÉRIMÈTRE DE CONSULTATION ---
    col_perm, _ = st.columns([2, 1])
    with col_perm:
        if role == "charge_surete":
            st.success("👤 **Chargé de Sûreté** — Vue globale multi-sites.")
            selected_site = st.selectbox(
                "📍 Périmètre d'observation :",
                ["Tous les sites", "DINUM", "DOUMER"],
            )
        else:
            st.info(
                "👤 **Personne Habilitée** — Consultation limitée au site"
                f" **{user_site}**."
            )
            selected_site = user_site

    st.markdown("---")

    # --- 3. BARRE DE FILTRES ET DE RECHERCHE ---
    col_d1, col_d2, col_search = st.columns([1, 1, 2])
    with col_d1:
        date_debut = st.date_input(
            "Date de début",
            value=datetime.date.today() - datetime.timedelta(days=7),
        )
    with col_d2:
        date_fin = st.date_input("Date de fin", value=datetime.date.today())
    with col_search:
        search_query = st.text_input(
            "🔍 Recherche textuelle",
            placeholder="Ex: Fuite, Nom, Numéro MC...",
        )

    # Convertir en horodatages ISO pour Supabase
    dt_start = datetime.datetime.combine(
        date_debut, datetime.time.min
    ).isoformat()
    dt_end = datetime.datetime.combine(
        date_fin, datetime.time.max
    ).isoformat()

    # --- 4. REQUÊTE SUPABASE ---
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
                    df["description"].str.lower().str.contains(q, na=False)
                    | df["reference"].str.lower().str.contains(q, na=False)
                    | df["agent_nom"].str.lower().str.contains(q, na=False)
                    | df["type_evenement"].str.lower().str.contains(q, na=False)
                ]

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

            # Conversion flexible et tolérante des dates ISO
            df_display["Horodatage"] = pd.to_datetime(
                df_display["Horodatage"], format="ISO8601", errors="coerce"
            ).dt.strftime("%d/%m/%Y %H:%M:%S")

            st.dataframe(df_display, use_container_width=True)

            # --- 5. BOUTON D'EXPORTATION PDF ---
            st.markdown("---")

            # Formater les dates pour l'affichage
            d_start_str = date_debut.strftime("%d/%m/%Y")
            d_end_str = date_fin.strftime("%d/%m/%Y")

            # Génération du fichier PDF binaire
            pdf_bytes = generate_registre_pdf(
                events=data,
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
            st.info("ℹ️ Aucun événement trouvé pour la période sélectionnée.")

    except Exception as e:
        st.error(f"Erreur lors de la récupération du registre : {e}")