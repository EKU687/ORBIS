# =========================================================================
# APPLICATION : MAIN COURANTE V3 - PC GARDE (ORBIS)
# Inclus : Gestion SSO Portail HUB, Support YubiKey/Password via SDK,
#          Moniteur Mouvements direct, Horodatage Pacific/Noumea (UTC+11),
#          Module Présences sur site (AEOS + ORBIS), Déconnexion neutre,
#          Référentiel Documentaire OPERA, Messagerie Interne & Pop-up Alerte.
# =========================================================================
import datetime
from pathlib import Path
import sys
import zoneinfo
import cadre_entreprise.auth as auth
import cadre_entreprise.ui as ui
import pandas as pd
import streamlit as st
from streamlit_autorefresh import st_autorefresh
from config import APP_AUTHOR, APP_DATE, APP_ENV, APP_NAME, APP_SUBTITLE, APP_VERSION
from utils.opera_bridge import (
    afficher_section_deltas_opera_dans_modale,
    verifier_deltas_opera_non_lus,
)

# --- FIX DES CHEMINS PYTHON ET IMPORTS SOCLE ---
ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from utils.db_client import supabase

# --- CONFIGURATION DU FUSEAU HORAIRE NOUVELLE-CALÉDONIE (UTC+11) ---
TZ_NC = zoneinfo.ZoneInfo("Pacific/Noumea")

# Ping automatique toutes les 60 secondes pour maintenir la session et rafraîchir les alertes
st_autorefresh(interval=60 * 1000, key="keep_alive_main_courante")


def get_now_nc() -> datetime.datetime:
    """Retourne la date et l'heure actuelles en Nouvelle-Calédonie."""
    return datetime.datetime.now(TZ_NC)


# --- CONFIGURATION DE LA PAGE STREAMLIT ---
st.set_page_config(
    page_title="ORBIS - Main Courante V3",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------
# CONTRÔLE CONTINU OPERA : AVERTIR L'AGENT EN COURS DE SERVICE
# ---------------------------------------------------------------------
if st.session_state.get("vacation_ouverte"):
    deltas_cours_de_poste = verifier_deltas_opera_non_lus(
        supabase_client=supabase,
        site_id=st.session_state.get("site_id"),
        agent_login=st.session_state.get("user_login"),
    )

    if deltas_cours_de_poste:
        st.error(
            f"🚨 **ALERTE SÛRETÉ URGENTE ({len(deltas_cours_de_poste)})** : "
            "Une nouvelle procédure ou consigne de sûreté a été publiée par la sûreté !"
        )

        with st.expander(
            "📋 PRENDRE CONNAISSANCE ET ÉMARGER LA NOUVELLE CONSIGNE IMMÉDIATEMENT",
            expanded=True,
        ):
            afficher_section_deltas_opera_dans_modale(
                supabase_client=supabase,
                deltas_non_lus=deltas_cours_de_poste,
                agent_login=st.session_state.get("user_login"),
                agent_nom=st.session_state.get(
                    "full_name", st.session_state.get("user_login")
                ),
                site_id=st.session_state.get("site_id"),
                vacation_ref=st.session_state.get("vacation_ref"),
            )

# =========================================================================
# 🎯 ACCÈS DIRECT MONITEUR MOUVEMENTS (SANS AUTHENTIFICATION OBLIGATOIRE)
# =========================================================================
query_params = st.query_params
view_param = query_params.get("view", None)

if view_param == "mouvements":
    from views import app_mouvements

    app_mouvements.show()
    st.stop()

# =========================================================================
# 1. STRATÉGIE D'AUTHENTIFICATION HYBRIDE (SSO PORTAIL + YUBIKEY LOCAL)
# =========================================================================
token_url = query_params.get("session_token")

if token_url and not auth.est_connecte():
    try:
        res_session = (
            supabase.table("Sessions_Portail")
            .select("*, Utilisateur(*)")
            .eq("token", token_url)
            .eq("actif", True)
            .execute()
        )
        if res_session.data:
            user_sso = res_session.data[0].get("Utilisateur")
            if user_sso:
                st.session_state["utilisateur"] = user_sso
                st.session_state["connecte"] = True
                st.session_state["session_token_actuel"] = token_url
                st.query_params.clear()
    except Exception as err:
        st.warning(f"⚠️ Validation du jeton SSO Portail échouée : {err}")

if not auth.est_connecte():
    ui.afficher_ecran_login(
        nom_application="ORBIS - Main Courante V3",
        icone="🛡️",
    )
    st.stop()


# =========================================================================
# 2. HELPER : CHARGEMENT DYNAMIQUE DE LA BASE DE SITES
# =========================================================================
def charger_sites_actifs() -> list[str]:
    """Récupère la liste dynamique des nom_site actifs depuis la table 'Sites' Supabase."""
    try:
        res = (
            supabase.table("Sites")
            .select("nom_site")
            .eq("actif", True)
            .order("nom_site")
            .execute()
        )
        sites = [row["nom_site"] for row in (res.data or []) if row.get("nom_site")]
        return sites if sites else ["DINUM", "SITE DOUMER", "SITE OUEMO"]
    except Exception as err:
        print(f"Erreur chargement table Sites : {err}")
        return ["DINUM", "SITE DOUMER", "SITE OUEMO"]


# =========================================================================
# 3. RÉCUPÉRATION DYNAMIQUE DU PROFIL COMPTE & PROMOTION DES DROITS
# =========================================================================
user_auth = auth.get_user_info()

st.session_state["user_profile"] = {
    "full_name": user_auth.get("nom", user_auth.get("login", "AGENT")),
    "role": str(user_auth.get("role", "AGENT_SECU")).upper().strip(),
    "site_defaut": user_auth.get("site_defaut", "DINUM"),
    "service": user_auth.get("service", "PC Garde"),
    "login": str(user_auth.get("login", "")).lower().strip(),
}

user = st.session_state["user_profile"]
role_actif = user["role"]
site_defaut_user = user["site_defaut"]

SITES_DISPONIBLES = charger_sites_actifs()

ROLES_MULTI_SITES = ["CHARGE_SURETE", "ADMIN", "COS", "SUPER_ADMIN"]
est_multi_sites = (role_actif in ROLES_MULTI_SITES) or (
    site_defaut_user in ["TOUS", "ALL"]
)


# =========================================================================
# 4. FONCTION UNIQUE DE DÉCONNEXION NEUTRE (CONSERVE LA VACATION EN BDD)
# =========================================================================
def executer_deconnexion_simple():
    """Déconnecte l'agent SANS clôturer la vacation active en base de données."""
    token_actuel = st.session_state.get("session_token_actuel")
    if token_actuel:
        try:
            supabase.table("Sessions_Portail").update({"actif": False}).eq(
                "token", token_actuel
            ).execute()
        except Exception:
            pass

    st.session_state.clear()
    url_portail = "https://portail-gnc.streamlit.app"

    st.markdown(
        f"""
        <script type="text/javascript">
            window.close();
            setTimeout(function() {{
                window.location.href = "{url_portail}";
            }}, 300);
        </script>
        """,
        unsafe_allow_html=True,
    )
    st.rerun()


# =========================================================================
# 5. SIDEBAR : EN-TÊTE DYNAMIQUE AVEC VERSIONNING
# =========================================================================
st.sidebar.markdown("## 🌐 **ORBIS**")

badge_env = "🟢 PROD" if APP_ENV == "PRODUCTION" else "🟠 BÊTA"

st.sidebar.caption(
    f"🛡️ **{APP_SUBTITLE}**\n\n"
    f"📌 Version : `{APP_VERSION}` | {badge_env}\n\n"
    f"📅 Mis à jour le : {APP_DATE}\n\n"
    f"👨‍💻 Auteur : **{APP_AUTHOR}**"
)
st.sidebar.markdown("---")

st.sidebar.markdown(f"👤 **{user.get('full_name', 'AGENT')}**")
st.sidebar.caption(
    f"🏢 Service : **{user.get('service', 'PC Garde')}** | 🔑 Rôle :" f" `{role_actif}`"
)

if est_multi_sites:
    idx_defaut = (
        SITES_DISPONIBLES.index(site_defaut_user)
        if site_defaut_user in SITES_DISPONIBLES
        else 0
    )
    site_selected = st.sidebar.selectbox(
        "📍 Site de Supervision / Garde :",
        SITES_DISPONIBLES,
        index=idx_defaut,
        help="Profil Administrateur / Sûreté : liste dynamique issue de la base 'Sites'.",
    )
else:
    site_selected = site_defaut_user
    st.sidebar.info(f"📍 Site de rattachement : **{site_selected}**")

st.session_state["site_actif"] = site_selected
st.sidebar.markdown("---")

# =========================================================================
# 6. CALCUL DYNAMIQUE ET ALERTES (BADGES & MESSAGES NON LUS)
# =========================================================================
# A. Badges temporaires
try:
    res_count = (
        supabase.table("badges_temporaires")
        .select("id", count="exact")
        .eq("site_id", site_selected)
        .eq("statut", "EN_COURS")
        .execute()
    )
    nb_badges_actifs = res_count.count if res_count.count else 0
except Exception:
    nb_badges_actifs = 0

label_badges = (
    f"🚨 🏷️ BADGES TEMPORAIRES ({nb_badges_actifs})"
    if nb_badges_actifs > 0
    else "🏷️ Badges Temporaires"
)

# B. Messagerie Interne (Messages non lus pour l'agent connecté)
nom_user_clean = str(user.get("full_name", "")).strip().upper()
try:
    dests_valides = [nom_user_clean, "TOUS"]
    if est_multi_sites or role_actif in [
        "ADMIN",
        "SUPER_ADMIN",
        "CHARGE_SURETE",
        "COS",
    ]:
        dests_valides.append("ADMIN_SURETE")

    res_msg_non_lus = (
        supabase.table("mc_discussion")
        .select("id", count="exact")
        .eq("site_id", site_selected)
        .eq("lu", False)
        .neq("expediteur_nom", nom_user_clean)
        .in_("destinataire_nom", dests_valides)
        .execute()
    )
    nb_msg_non_lus = res_msg_non_lus.count if res_msg_non_lus.count else 0
except Exception:
    nb_msg_non_lus = 0

label_messagerie = (
    f"🚨 💬 MESSAGERIE INTERNE ({nb_msg_non_lus})"
    if nb_msg_non_lus > 0
    else "💬 Messagerie Interne"
)

# =========================================================================
# 🎯 DÉTECTION INTELLIGENTE : OPTION B (POP-UP UNIQUEMENT SI NOUVEAU MESSAGE)
# =========================================================================
# 1. On récupère le nombre de messages non lus enregistré lors du dernier ping
ancien_nb_msg = st.session_state.get("anc_nb_msg_non_lus", 0)

# 2. Si le nombre a augmenté (ex: passage de 0 à 1, ou de 1 à 2), on autorise le pop-up
if nb_msg_non_lus > ancien_nb_msg:
    st.session_state["popup_msg_ignore"] = False

# 3. On sauvegarde le compte actuel pour le prochain ping de 60 secondes
st.session_state["anc_nb_msg_non_lus"] = nb_msg_non_lus


# =========================================================================
# 🔔 MODALE POP-UP D'ALERTE POUR NOUVEAU MESSAGE ENTRANT
# =========================================================================
@st.dialog("🔔 NOUVEAU MESSAGE DE SERVICE RECEIVED")
def afficher_modal_nouveau_message(nb_messages: int):
    st.warning(
        f"📩 **Vous avez {nb_messages} nouveau(x) message(s) non lu(s)** "
        "transmis par la Direction / Sûreté ou un autre poste de garde."
    )
    st.caption(
        "Consultez le fil d'échanges pour prendre connaissance des consignes ou questions."
    )

    col_go, col_close = st.columns([1.5, 1])

    with col_go:
        if st.button(
            "💬 Ouvrir la messagerie", type="primary", use_container_width=True
        ):
            st.session_state["navigue_vers_module"] = "discussion"
            st.session_state["popup_msg_ignore"] = True
            st.rerun()

    with col_close:
        if st.button("Fermer", use_container_width=True):
            st.session_state["popup_msg_ignore"] = True
            st.rerun()


# Affichage du pop-up uniquement s'il y a des messages non lus ET que l'autorisation est active
if nb_msg_non_lus > 0 and not st.session_state.get("popup_msg_ignore", False):
    afficher_modal_nouveau_message(nb_msg_non_lus)

# =========================================================================
# 7. CONSTRUCTION DYNAMIQUE DU MENU DE NAVIGATION SÉCURISÉ
# =========================================================================
NAVIGATION_MAP = {
    "main_courante": "📝 Main Courante",
    "discussion": label_messagerie,
    "referentiel_doc": "📂 Référentiel Documentaire",
}

ROLES_REGISTRE = ["CHARGE_SURETE", "ADMIN", "COS", "SUPER_ADMIN"]
if role_actif in ROLES_REGISTRE:
    NAVIGATION_MAP["registre"] = "📖 Consulter Registre"

NAVIGATION_MAP.update(
    {
        "visiteur_imprevu": "✍️ Visiteur Imprévu",
        "visiteurs_attendus": "👥 Visiteurs Attendus",
        "evacuation_incendie": "🏢 Présences sur site",
        "suivi_rondes": "🔦 Suivi des Rondes",
        "anomalies": "🚨 Anomalies & Consignes Générales",
        "badges": label_badges,
        "permis": "🚗 Gestion des Permis",
    }
)

ROLES_ADMIN_ONLY = ["ADMIN", "SUPER_ADMIN", "CHARGE_SURETE", "COS"]
if role_actif in ROLES_ADMIN_ONLY:
    NAVIGATION_MAP["consignes_admin"] = "🎯 Consignes Ciblées (Admin)"
    NAVIGATION_MAP["hypervision"] = "🛡️ Hypervision COS"

NAVIGATION_MAP["recherche_prestataires"] = "🔍 Recherche Prestataires"

if "module_actif" not in st.session_state:
    st.session_state["module_actif"] = "main_courante"

if st.session_state.get("navigue_vers_module"):
    st.session_state["module_actif"] = st.session_state.pop("navigue_vers_module")

module_actif = st.sidebar.radio(
    "Navigation",
    options=list(NAVIGATION_MAP.keys()),
    format_func=lambda key: NAVIGATION_MAP[key],
    key="module_actif",
)

# =========================================================================
# 7.1. ACCÈS DIRECT AU MONITEUR DES MOUVEMENTS (ONGLET DÉDIÉ)
# =========================================================================
st.sidebar.markdown("---")

nom_user_encoded = str(user.get("full_name", "")).replace(" ", "%20")
st.sidebar.link_button(
    "🚪 Moniteur Mouvements (Onglet Dédié)",
    url=(
        f"?site={site_selected}&role={role_actif}&user={nom_user_encoded}&view=mouvements"
    ),
    use_container_width=True,
    help="Ouvre la console des flux d'entrées/sorties en continu dans un nouvel onglet.",
)

st.sidebar.markdown("---")

# =========================================================================
# 7.2. BOUTON UNIQUE DE DÉCONNEXION NEUTRE
# =========================================================================
if st.sidebar.button(
    "🚪 Déconnexion",
    type="primary",
    use_container_width=True,
    help="Déconnecte l'agent du PC Garde sans fermer la vacation en cours.",
):
    executer_deconnexion_simple()

# =========================================================================
# 8. ROUTAGE DES MODULES MÉTIER
# =========================================================================
if module_actif == "main_courante":
    from views import main_courante

    main_courante.show()

elif module_actif == "discussion":
    from views import discussion

    discussion.show()

elif module_actif == "referentiel_doc":
    from views.procedures_view import afficher_page_procedures_opera

    afficher_page_procedures_opera(supabase_client=supabase, site_courant=site_selected)

elif module_actif == "registre":
    from views import registre

    registre.show(user)

elif module_actif == "visiteur_imprevu":
    from views import visiteur_imprevu

    visiteur_imprevu.show()

elif module_actif == "visiteurs_attendus":
    from views import visiteurs_attendus

    visiteurs_attendus.show()

elif module_actif == "evacuation_incendie":
    from views import evacuation_incendie

    evacuation_incendie.show()

elif module_actif == "suivi_rondes":
    from views import suivi_rondes

    suivi_rondes.show()

elif module_actif == "anomalies":
    from views import anomalies

    anomalies.show()

elif module_actif == "badges":
    from views import badges

    badges.show()

elif module_actif == "permis":
    from views import permis

    permis.show()

elif module_actif == "consignes_admin":
    from views import consignes_admin

    consignes_admin.show(user)

elif module_actif == "hypervision":
    from views import hypervision

    hypervision.show()

elif module_actif == "recherche_prestataires":
    from views import recherche_prestataires

    recherche_prestataires.show()

else:
    st.info(f"Le module sélectionné est en cours de construction.")
