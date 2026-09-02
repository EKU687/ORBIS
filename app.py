# =========================================================================
# APPLICATION : MAIN COURANTE V3 - PC GARDE (ORBIS)
# Inclus : Gestion SSO Portail HUB, Support YubiKey/Password via SDK,
#          Moniteur Mouvements direct, Horodatage Pacific/Noumea (UTC+11),
#          Déconnexion simple (vacation maintenue) ET Clôture explicite de poste.
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
from config import APP_AUTHOR, APP_DATE, APP_ENV, APP_NAME, APP_VERSION, APP_SUBTITLE

# --- CONFIGURATION DU FUSEAU HORAIRE NOUVELLE-CALÉDONIE (UTC+11) ---
TZ_NC = zoneinfo.ZoneInfo("Pacific/Noumea")

# Ping automatique toutes les 3 minutes (180 000 ms) pour maintenir la session
st_autorefresh(interval=180 * 1000, key="keep_alive_main_courante")


def get_now_nc() -> datetime.datetime:
    """Retourne la date et l'heure actuelles en Nouvelle-Calédonie."""
    return datetime.datetime.now(TZ_NC)


# --- FIX DES CHEMINS PYTHON ET IMPORTS SOCLE ---
ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from utils.db_client import supabase

# --- CONFIGURATION DE LA PAGE STREAMLIT ---
st.set_page_config(
    page_title="ORBIS - Main Courante V3",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# =========================================================================
# 🎯 ACCÈS DIRECT MONITEUR MOUVEMENTS (SANS AUTHENTIFICATION OBLIGATOIRE)
# =========================================================================
query_params = st.query_params
view_param = query_params.get("view", None)

if view_param == "mouvements":
    from views import app_mouvements

    app_mouvements.show()
    st.stop()  # Stoppe le script ici pour la console dédiée d'entrées/sorties

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
                st.query_params.clear()  # Nettoyage de la barre d'adresse URL
    except Exception as err:
        st.warning(f"⚠️ Validation du jeton SSO Portail échouée : {err}")

# Si non authentifié (accès URL direct) ➔ Mire Hybride SDK (Mot de passe + YubiKey)
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
        sites = [
            row["nom_site"] for row in (res.data or []) if row.get("nom_site")
        ]
        return (
            sites
            if sites
            else ["DINUM", "DOUMER", "GNC", "HÔTEL DU GOUVERNEMENT"]
        )
    except Exception as err:
        print(f"Erreur chargement table Sites : {err}")
        return ["DINUM", "DOUMER", "GNC", "HÔTEL DU GOUVERNEMENT"]


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
# 4. FONCTIONS SÉPARÉES : DÉCONNEXION SIMPLE VS CLÔTURE DE VACATION
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


def executer_cloture_vacation_explicite():
    """Effectue la clôture administrative officielle du poste en BDD (Fin de vacation)."""
    vac_id = st.session_state.get("vacation_id")
    agent_nom = user.get("full_name", "AGENT")
    site_id = st.session_state.get("site_actif", "DINUM")
    now_dt = get_now_nc()

    try:
        if vac_id and len(str(vac_id)) == 36:
            supabase.table("vacations").update({
                "statut": "CLOTUREE",
                "fin_at": now_dt.isoformat(),
            }).eq("id", vac_id).execute()
        else:
            supabase.table("vacations").update({
                "statut": "CLOTUREE",
                "fin_at": now_dt.isoformat(),
            }).eq("site_id", site_id).in_("statut", ["OUVERTE", "EN_COURS"]).execute()

        payload_fin = {
            "reference": f"REF-FIN-VAC-{now_dt.strftime('%Y%m%d-%H%M%S')}",
            "vacation_id": vac_id if (vac_id and len(str(vac_id)) == 36) else None,
            "site_id": site_id,
            "agent_nom": agent_nom,
            "horodatage": now_dt.isoformat(),
            "type_evenement": "FIN_VACATION",
            "description": f"🚪 Clôture explicite de vacation par {agent_nom} — Fin de service PC Garde.",
            "actions_menees": "Passation / Fin de poste enregistrée et vacation fermée (CLOTUREE).",
        }
        supabase.table("mc_evenements").insert(payload_fin).execute()
        st.toast("✅ Vacation clôturée avec succès en Base de Données !", icon="🚪")

    except Exception as err:
        st.warning(f"Note lors de la clôture BDD : {err}")

    executer_deconnexion_simple()


# =========================================================================
# 5. SIDEBAR : EN-TÊTE DYNAMIQUE AVEC VERSIONNING (SemVer)
# =========================================================================
st.sidebar.markdown("## 🌐 **ORBIS**")

# Badge d'environnement visuel (PROD ou BÊTA)
badge_env = "🟢 PROD" if APP_ENV == "PRODUCTION" else "🟠 BÊTA"

# Sous-titre dynamique combinant le nom du module, la version et le statut
st.sidebar.caption(
    f"🛡️ **{APP_SUBTITLE}**\n\n"
    f"📌 Version : `{APP_VERSION}` | {badge_env}\n\n"
    f"📅 Mis à jour le : {APP_DATE} | 📍 NC (UTC+11)"
    f"👨‍💻 Auteur : **{APP_AUTHOR}**"
)
st.sidebar.markdown("---")

st.sidebar.markdown(f"👤 **{user.get('full_name', 'AGENT')}**")
st.sidebar.caption(
    f"🏢 Service : **{user.get('service', 'PC Garde')}** | 🔑 Rôle :"
    f" `{role_actif}`"
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
# 6. CALCUL DYNAMIQUE ET ALERTE BADGES TEMPORAIRES
# =========================================================================
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

if nb_badges_actifs > 0:
    label_badges = f"🚨 🏷️ BADGES TEMPORAIRES ({nb_badges_actifs})"
else:
    label_badges = "🏷️ Badges Temporaires"

# =========================================================================
# 7. CONSTRUCTION DYNAMIQUE DU MENU DE NAVIGATION SELON LE RÔLE
# =========================================================================
menu_options = {
    "📝 Main Courante": "main_courante",
}

ROLES_REGISTRE = ["CHARGE_SURETE", "ADMIN", "COS", "SUPER_ADMIN"]
if role_actif in ROLES_REGISTRE:
    menu_options["📖 Consulter Registre"] = "registre"

menu_options.update({
    "✍️ Visiteur Imprévu": "visiteur_imprevu",
    "👥 Visiteurs Attendus": "visiteurs_attendus",
    "🔦 Suivi des Rondes": "suivi_rondes",
    "⚠️ Anomalies & Vigilance": "anomalies",
    label_badges: "badges",
    "🚗 Gestion des Permis": "permis",
})

ROLES_ADMIN_ONLY = ["ADMIN", "SUPER_ADMIN", "CHARGE_SURETE", "COS"]
if role_actif in ROLES_ADMIN_ONLY:
    menu_options["⚙️ Consignes (Admin)"] = "consignes_admin"
    menu_options["🛡️ Hypervision COS"] = "hypervision"

menu_options["🔍 Recherche Prestataires"] = "recherche_prestataires"

selection_label = st.sidebar.radio("Navigation", list(menu_options.keys()))
module_actif = menu_options[selection_label]

# =========================================================================
# 7.1. ACCÈS DIRECT AU MONITEUR DES MOUVEMENTS (DEUXIÈME ONGLET / ÉCRAN)
# =========================================================================
st.sidebar.markdown("---")
st.sidebar.link_button(
    "🚪 Moniteur Mouvements (Onglet Dédié)",
    url=f"?site={site_selected}&view=mouvements",
    use_container_width=True,
    help="Ouvre la console des flux d'entrées/sorties en continu dans un nouvel onglet.",
)

st.sidebar.markdown("---")

# =========================================================================
# 7.2. GESTION DISTINCTE DE LA DECONNEXION ET DE LA FIN DE POSTE
# =========================================================================
if st.sidebar.button(
    "🔒 Se Déconnecter (Maintenir Vacation)",
    use_container_width=True,
    help="Ferme l'accès applicatif sans fermer le registre de vacation du site.",
):
    executer_deconnexion_simple()

if st.sidebar.button(
    "🛑 Clôturer Vacation & Fin de Poste",
    type="primary",
    use_container_width=True,
    help="Réservé aux fins de poste : clôture la vacation sur le registre Supabase.",
):
    executer_cloture_vacation_explicite()

# =========================================================================
# 8. ROUTAGE DES MODULES MÉTIER
# =========================================================================
if module_actif == "main_courante":
    from views import main_courante
    main_courante.show()

elif module_actif == "registre":
    from views import registre
    registre.show(user)

elif module_actif == "visiteur_imprevu":
    from views import visiteur_imprevu
    visiteur_imprevu.show()

elif module_actif == "visiteurs_attendus":
    from views import visiteurs_attendus
    visiteurs_attendus.show()

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
    st.info(f"Le module **{selection_label}** est en cours de construction.")