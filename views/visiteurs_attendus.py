# =========================================================================
# MODULE : SUIVI GÉNÉRAL ET VISITEURS ATTENDUS (views/visiteurs_attendus.py)
# Inclus : Synchronisation BDD, Gestion des imprévus, Planning ASAP,
#          et Mode Livraison Quai / Sans Badge physique.
# =========================================================================
import re
import datetime
import io
from pathlib import Path
import sys
import urllib.request
import uuid
import zoneinfo
import pandas as pd
import streamlit as st

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from utils.db_client import supabase

URL_ASAP_CSV = "https://docs.google.com/spreadsheets/d/1cKIlYixzeFtJSO3hVQKjkSv_GRPPqEqkzA7zUbSNyKo/gviz/tq?tqx=out:csv&sheet=RendezVous"

# Definition du fuseau horaire Nouvelle-Caledonie (UTC+11)
TZ_NC = zoneinfo.ZoneInfo("Pacific/Noumea")


@st.cache_data(ttl=180)
def fetch_asap_data(url: str) -> pd.DataFrame:
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "Mozilla/5.0"}
        )
        with urllib.request.urlopen(req, timeout=8) as response:
            csv_data = response.read().decode("utf-8")

        df = pd.read_csv(io.StringIO(csv_data))
        df.columns = [str(col).strip() for col in df.columns]
        return df
    except Exception as e:
        st.error(f"⚠️ Erreur de chargement du fichier CSV : {e}")
        return pd.DataFrame()


def clean_organisateur(val: str) -> str:
    if not val or pd.isna(val):
        return "Non précisé"
    return str(val).replace("(undefined)", "").strip()


def get_or_create_vacation_id(site_id: str, agent_nom: str) -> str:
    if st.session_state.get("vacation_id"):
        return st.session_state["vacation_id"]

    try:
        res = (
            supabase.table("vacations")
            .select("id")
            .eq("site_id", site_id)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if res.data and len(res.data) > 0:
            vac_id = res.data[0]["id"]
            st.session_state["vacation_id"] = vac_id
            return vac_id
    except Exception:
        pass

    now_nc = datetime.datetime.now(TZ_NC)
    new_id = str(uuid.uuid4())
    payload_vacation = {
        "id": new_id,
        "site_id": site_id,
        "agent_nom": agent_nom,
        "statut": "OUVERTE",
        "created_at": now_nc.isoformat(),
    }
    try:
        supabase.table("vacations").insert(payload_vacation).execute()
        st.session_state["vacation_id"] = new_id
        return new_id
    except Exception:
        return new_id


def fetch_badges_temporaires_actifs(site_id: str) -> dict[str, str]:
    """Récupère une table de correspondance Nom du porteur -> Numéro de badge depuis badges_temporaires."""
    badge_map = {}
    try:
        res = (
            supabase.table("badges_temporaires")
            .select("nom_porteur, num_badge")
            .eq("site_id", str(site_id))
            .eq("statut", "EN_COURS")
            .execute()
        )
        for row in (res.data or []):
            nom = str(row.get("nom_porteur", "")).strip().upper()
            bdg = row.get("num_badge")
            if nom and bdg:
                badge_map[nom] = bdg
    except Exception as e:
        print(f"Note lecture badges_temporaires : {e}")
    return badge_map


def get_visiteurs_presents_bdd(site_id: str, target_date: datetime.date) -> tuple[dict, set, set, set]:
    """Interroge Supabase pour déterminer la présence réelle et les absences/annulations à une date cible."""
    dt_start = datetime.datetime.combine(
        target_date, datetime.time.min, tzinfo=TZ_NC
    ).isoformat()
    dt_end = datetime.datetime.combine(
        target_date, datetime.time.max, tzinfo=TZ_NC
    ).isoformat()

    presents_dict = {}
    sortis_set = set()
    absents_set = set()
    badges_occupes = set()

    map_badges_bdd = fetch_badges_temporaires_actifs(site_id)

    try:
        res = (
            supabase.table("mc_evenements")
            .select("*")
            .eq("site_id", site_id)
            .eq("type_evenement", "VISITEUR")
            .gte("horodatage", dt_start)
            .lte("horodatage", dt_end)
            .order("horodatage", desc=False)
            .execute()
        )

        for ev in res.data:
            ref = ev.get("reference", "")
            desc = ev.get("description", "")

            # Détection entrée
            if "-IN-" in ref:
                badge = "Aucun"

                # 🎯 EXTRACTION PAR REGEX PARFAITE (Ex: V.001, T.015, LIVRAISON)
                match_badge = re.search(r"Badge\s+([VTL]\.?[0-9A-Z_]+)", desc, re.IGNORECASE)
                if match_badge:
                    badge = match_badge.group(1).upper()
                elif "LIVRAISON" in desc.upper():
                    badge = "LIVRAISON"

                nom_key = (
                    desc.split(":")[1].split("(")[0].strip().upper()
                    if ":" in desc
                    else desc.strip().upper()
                )

                # RECOURS BDD (badges_temporaires) si la description ne contient pas le format exact
                if badge in ["Aucun", "", "V"] and nom_key in map_badges_bdd:
                    badge = map_badges_bdd[nom_key]

                presents_dict[nom_key] = {
                    "badge": badge,
                    "description": desc,
                    "ref_in": ref,
                }
                if badge.startswith("V.") or badge.startswith("T."):
                    badges_occupes.add(badge)

            # Détection sortie
            elif "-OUT-" in ref:
                nom_key = (
                    desc.split(":")[1].split("(")[0].strip().upper()
                    if ":" in desc
                    else desc.strip().upper()
                )
                if nom_key in presents_dict:
                    badge_lib = presents_dict[nom_key]["badge"]
                    presents_dict.pop(nom_key, None)
                    if badge_lib in badges_occupes:
                        badges_occupes.remove(badge_lib)
                sortis_set.add(nom_key)

            # Détection absence / annulation
            elif "-ABS-" in ref:
                nom_key = (
                    desc.split(":")[1].split("(")[0].strip().upper()
                    if ":" in desc
                    else desc.strip().upper()
                )
                absents_set.add(nom_key)

    except Exception as e:
        st.error(f"Erreur de lecture BDD présence : {e}")

    return presents_dict, sortis_set, absents_set, badges_occupes


def show():
    st.title("👥 Suivi Général des Visiteurs (Persistance BDD)")
    st.caption(
        "Registre d'accueil synchronisé en temps réel avec la base de données Supabase."
    )

    site_actuel = st.session_state.get("site_actif", "DINUM")
    user_info = st.session_state.get(
        "user_profile", {"full_name": "Éric KUTER"}
    )
    agent_connecte = user_info.get("full_name", "Éric KUTER")

    # 1. Date courante en Nouvelle-Calédonie
    aujourdhui_nc = datetime.datetime.now(TZ_NC).date()

    # 2. En-tête avec Sélecteur de date et Bouton d'actualisation
    c_head1, c_head2, c_head3 = st.columns([2, 1.5, 1])
    
    with c_head1:
        selected_date = st.date_input(
            "📅 Date de consultation :",
            value=aujourdhui_nc,
            format="DD/MM/YYYY",
        )
    
    with c_head2:
        st.write("")  # Espaceur d'alignement
        st.write("")
        if selected_date == aujourdhui_nc:
            st.caption("🟢 Temps réel (Aujourd'hui)")
        elif selected_date > aujourdhui_nc:
            st.caption("🔵 Planning prévisionnel")
        else:
            st.caption("🟠 Historique / Archives")

    with c_head3:
        st.write("")  # Espaceur d'alignement
        st.write("")
        if st.button("🔄 Actualiser", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    selected_str_fr = selected_date.strftime("%d/%m/%Y")
    selected_str_iso = selected_date.strftime("%Y-%m-%d")

    # --- LECTURE BDD POUR LA DATE SÉLECTIONNÉE ---
    presents_bdd, sortis_bdd, absents_bdd, badges_occupes = (
        get_visiteurs_presents_bdd(site_actuel, selected_date)
    )

    tous_badges = [f"V.{i:03d}" for i in range(1, 31)]
    
    # INTÉGRATION DU MODE LIVRAISON DANS LA LISTE DÉROULANTE
    badges_disponibles = (
        ["Sélectionner un badge...", "📦 LIVRAISON (Sans badge)"] 
        + [b for b in tous_badges if b not in badges_occupes]
    )

    vac_id = get_or_create_vacation_id(site_actuel, agent_connecte)

    # --- 1. VISITEURS IMPRÉVUS SUR SITE (BDD) ---
    st.markdown("### ✍️ Visiteurs Imprévus sur Site")
    imprevus_sur_site = {
        k: v
        for k, v in presents_bdd.items()
        if "REF-VIS-IMP-IN" in v.get("ref_in", "")
    }

    if imprevus_sur_site:
        with st.container(height=280):
            for nom_key, info in imprevus_sur_site.items():
                badge_imp = info["badge"]

                col_time, col_info, col_action = st.columns([1, 2.2, 1.8])

                with col_time:
                    st.success("✅ Sur site")

                with col_info:
                    st.markdown(f"👤 **{nom_key}** (Visiteur Imprévu)")

                with col_action:
                    st.info(f"Badge affecté : **{badge_imp}**")
                    if st.button(
                        "🚪 Signaler Sortie",
                        key=f"btn_out_imp_{nom_key}",
                        use_container_width=True,
                        type="secondary",
                    ):
                        now_nc = datetime.datetime.now(TZ_NC)
                        ref_time = now_nc.strftime("%Y%m%d-%H%M%S")

                        # Libération du badge dans badges_temporaires si présent
                        try:
                            supabase.table("badges_temporaires").update(
                                {
                                    "statut": "RESTITUE",
                                    "heure_restitution": now_nc.isoformat(),
                                }
                            ).eq("site_id", str(site_actuel)).eq("nom_porteur", nom_key).eq("statut", "EN_COURS").execute()
                        except Exception as err_rest:
                            print(f"Note libération badge_temporaire : {err_rest}")

                        payload_sortie = {
                            "reference": f"REF-VIS-IMP-OUT-{ref_time}",
                            "vacation_id": vac_id,
                            "site_id": site_actuel,
                            "agent_nom": agent_connecte,
                            "horodatage": now_nc.isoformat(),
                            "type_evenement": "VISITEUR",
                            "description": (
                                f"Sortie visiteur imprévu : {nom_key} (Badge"
                                f" {badge_imp} restitué)."
                            ),
                            "actions_menees": (
                                "Départ consigné et badge réintégré."
                            ),
                        }
                        try:
                            supabase.table("mc_evenements").insert(
                                payload_sortie
                            ).execute()
                            st.toast(
                                f"Sortie de {nom_key} enregistrée !", icon="🚪"
                            )
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erreur enregistrement MC : {e}")

                st.markdown("---")
    else:
        st.info("ℹ️ Aucun visiteur imprévu actuellement présent sur site.")

    # --- 2. VISITEURS ATTENDUS (ASAP) ---
    st.markdown(f"### 👥 Visiteurs Attendus (Planning ASAP du {selected_str_fr})")
    df_raw = fetch_asap_data(URL_ASAP_CSV)

    if not df_raw.empty:
        if "statut" in df_raw.columns:
            df_filtered = df_raw[
                ~df_raw["statut"]
                .astype(str)
                .str.upper()
                .str.contains("REFUS")
            ].copy()
        else:
            df_filtered = df_raw.copy()

        if "date" in df_filtered.columns:
            df_filtered["date_str"] = (
                df_filtered["date"].astype(str).str.strip()
            )
            df_target_date = df_filtered[
                (df_filtered["date_str"] == selected_str_fr)
                | (df_filtered["date_str"] == selected_str_iso)
            ].copy()
        else:
            df_target_date = df_filtered.copy()

        # Filtrer ceux déjà sortis ET ceux déclarés non présentés / annulés
        if not df_target_date.empty:
            df_target_date["nom_clean"] = df_target_date["nom"].astype(str).str.strip().str.upper()
            df_target_date = df_target_date[
                (~df_target_date["nom_clean"].isin(sortis_bdd))
                & (~df_target_date["nom_clean"].isin(absents_bdd))
            ].copy()

        if not df_target_date.empty:
            with st.container(height=450):
                for idx, row in df_target_date.iterrows():
                    h_arr = (
                        row.get("Heure Arrivée")
                        or row.get("Heure Arrivee")
                        or "--:--"
                    )
                    h_dep = (
                        row.get("Heure Départ")
                        or row.get("Heure Depart")
                        or "--:--"
                    )
                    nom_visiteur = str(row.get("nom") or "Inconnu").strip().upper()
                    email_visiteur = row.get("email") or "N/A"
                    organisateur = clean_organisateur(
                        row.get("organisateur(s)")
                    )

                    est_present = nom_visiteur in presents_bdd

                    col_time, col_info, col_action = st.columns([1, 2.2, 1.8])

                    with col_time:
                        st.markdown(f"🕒 **{h_arr}** ➔ `{h_dep}`")
                        if est_present:
                            st.success("✅ Sur site")
                        else:
                            st.caption("⏳ Attendu")

                    with col_info:
                        st.markdown(
                            f"👤 **{nom_visiteur}** (`{email_visiteur}`)"
                        )
                        st.write(f"🏢 **Hôte :** {organisateur}")

                    with col_action:
                        now_nc = datetime.datetime.now(TZ_NC)
                        ref_time = now_nc.strftime("%Y%m%d-%H%M%S")

                        if est_present:
                            badge_attribue = presents_bdd[nom_visiteur]["badge"]
                            
                            if badge_attribue == "LIVRAISON":
                                st.warning("📦 **Livraison en cours (Quai)**")
                            else:
                                st.info(f"Badge affecté : **{badge_attribue}**")

                            if st.button(
                                "🚪 Signaler Sortie",
                                key=f"btn_srt_{idx}",
                                use_container_width=True,
                                type="secondary",
                            ):
                                # Libération du badge dans badges_temporaires si présent
                                try:
                                    supabase.table("badges_temporaires").update(
                                        {
                                            "statut": "RESTITUE",
                                            "heure_restitution": now_nc.isoformat(),
                                        }
                                    ).eq("site_id", str(site_actuel)).eq("nom_porteur", nom_visiteur).eq("statut", "EN_COURS").execute()
                                except Exception as err_rest:
                                    print(f"Note libération badge_temporaire : {err_rest}")

                                desc_sortie = (
                                    f"Départ Livraison / Camion : {nom_visiteur} (Quai déchargement libéré)."
                                    if badge_attribue == "LIVRAISON"
                                    else f"Sortie visiteur attendu : {nom_visiteur} (Badge {badge_attribue} restitué). Visite de {organisateur}."
                                )
                                payload_mc_sortie = {
                                    "reference": f"REF-VIS-OUT-{ref_time}",
                                    "vacation_id": vac_id,
                                    "site_id": site_actuel,
                                    "agent_nom": agent_connecte,
                                    "horodatage": now_nc.isoformat(),
                                    "type_evenement": "VISITEUR",
                                    "description": desc_sortie,
                                    "actions_menees": (
                                        "Fin de présence consignée en Main Courante."
                                    ),
                                }
                                try:
                                    supabase.table("mc_evenements").insert(
                                        payload_mc_sortie
                                    ).execute()
                                    st.toast(
                                        f"Départ de {nom_visiteur} enregistré !",
                                        icon="🚪",
                                    )
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Erreur enregistrement MC : {e}")

                        else:
                            badge_sel = st.selectbox(
                                "Badge Visiteur :",
                                badges_disponibles,
                                key=f"sel_bdg_{idx}",
                            )
                            
                            badge_valide = (
                                badge_sel != "Sélectionner un badge..."
                            )

                            c_btn_arr, c_btn_abs = st.columns([1.5, 1])

                            with c_btn_arr:
                                if st.button(
                                    "✅ Arrivé sur site",
                                    key=f"btn_arr_{idx}",
                                    use_container_width=True,
                                    type="primary",
                                    disabled=not badge_valide,
                                ):
                                    est_livraison = (badge_sel == "📦 LIVRAISON (Sans badge)")
                                    valeur_badge = "LIVRAISON" if est_livraison else badge_sel
                                    ref_entree = "REF-VIS-LIV-IN" if est_livraison else "REF-VIS-IN"
                                    
                                    # Enregistrement dans badges_temporaires
                                    payload_badge_asap = {
                                        "site_id": site_actuel,
                                        "num_badge": valeur_badge,
                                        "nom_porteur": nom_visiteur,
                                        "type_porteur": "VISITEUR_ATTENDU",
                                        "hote_referent": organisateur,
                                        "statut": "EN_COURS",
                                        "heure_attribution": now_nc.isoformat(),
                                    }
                                    try:
                                        supabase.table("badges_temporaires").upsert(
                                            payload_badge_asap, on_conflict="site_id,num_badge"
                                        ).execute()
                                    except Exception as err_b:
                                        print(f"Note enregistrement badge ASAP : {err_b}")

                                    desc_entree = (
                                        f"Arrivée Livraison / Quai : {nom_visiteur} (Société / Livreurs) pour {organisateur} (Badge LIVRAISON)."
                                        if est_livraison
                                        else f"Arrivée visiteur attendu : {nom_visiteur} (Badge {badge_sel}) pour {organisateur} ({email_visiteur})."
                                    )

                                    payload_mc = {
                                        "reference": f"{ref_entree}-{ref_time}",
                                        "vacation_id": vac_id,
                                        "site_id": site_actuel,
                                        "agent_nom": agent_connecte,
                                        "horodatage": now_nc.isoformat(),
                                        "type_evenement": "VISITEUR",
                                        "description": desc_entree,
                                        "actions_menees": (
                                            "Accès quai enregistré (Livraison)."
                                            if est_livraison
                                            else "Accueil effectué et badge remis."
                                        ),
                                    }
                                    try:
                                        supabase.table("mc_evenements").insert(
                                            payload_mc
                                        ).execute()
                                        st.toast(
                                            f"Arrivée de {nom_visiteur} enregistrée !",
                                            icon="✅",
                                        )
                                        st.rerun()
                                    except Exception as e:
                                        st.error(
                                            f"Erreur enregistrement MC : {e}"
                                        )

                            with c_btn_abs:
                                if st.button(
                                    "❌ Absent / Annulé",
                                    key=f"btn_abs_{idx}",
                                    use_container_width=True,
                                    help=(
                                        "Consigner l'absence et retirer de la"
                                        " liste d'attente"
                                    ),
                                ):
                                    payload_mc_absent = {
                                        "reference": (
                                            f"REF-VIS-ABS-{ref_time}"
                                        ),
                                        "vacation_id": vac_id,
                                        "site_id": site_actuel,
                                        "agent_nom": agent_connecte,
                                        "horodatage": now_nc.isoformat(),
                                        "type_evenement": "VISITEUR",
                                        "description": (
                                            "Visiteur non présenté :"
                                            f" {nom_visiteur} ({email_visiteur})"
                                            f" pour {organisateur}."
                                        ),
                                        "actions_menees": (
                                            "Absence consignée en Main Courante."
                                        ),
                                    }
                                    try:
                                        supabase.table("mc_evenements").insert(
                                            payload_mc_absent
                                        ).execute()
                                        st.toast(
                                            f"Absence de {nom_visiteur}"
                                            " consignée !",
                                            icon="🚫",
                                        )
                                        st.rerun()
                                    except Exception as e:
                                        st.error(
                                            f"Erreur enregistrement MC : {e}"
                                        )

                    st.markdown("---")
        else:
            st.info(
                f"ℹ️ Aucun visiteur attendu le {selected_str_fr} dans le planning ASAP."
            )