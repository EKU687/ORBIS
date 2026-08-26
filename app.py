import datetime
from pathlib import Path
import sys
import zoneinfo
import streamlit as st

# Fuseau horaire Nouvelle-Calédonie (UTC+11)
TZ_NC = zoneinfo.ZoneInfo("Pacific/Noumea")


def get_now_nc() -> datetime.datetime:
    """Retourne la date et l'heure actuelles en Nouvelle-Calédonie."""
    return datetime.datetime.now(TZ_NC)


# --- FIX DES CHEMINS PYTHON ---
ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from utils.db_client import supabase
from views import login

# --- CONFIGURATION DE LA PAGE ---
st.set_page_config(
    page_title="ORBIS - Main Courante V3",
    page_icon="🌐",
    layout="wide",
    initial_sidebar_state="expanded",
)

# =========================================================================
# 1. VERROU D'AUTHENTIFICATION SÉCURISÉ
# =========================================================================
if not st.session_state.get("authenticated", False):
    login.show_login_page()
    st.stop()  # Interrompt l'exécution si non authentifié


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
# 3. RÉCUPÉRATION DU PROFIL & DÉTECTION HABILITATION MULTI-SITES
# =========================================================================
user = st.session_state.get(
    "user_profile",
    {
        "full_name": "KUTER ERIC",
        "role": "ADMIN",
        "site_defaut": "DINUM",
        "service": "Sécurité",
    },
)

# Normalisation du rôle
role_actif = str(user.get("role", "AGENT_SECU")).upper().strip()
site_defaut_user = user.get("site_defaut", "DINUM")

# Chargement de la liste dynamique des sites depuis la BDD 'Sites'
SITES_DISPONIBLES = charger_sites_actifs()

# Rôles ayant la capacité de basculer d'un site à l'autre
ROLES_MULTI_SITES = ["CHARGE_SURETE", "ADMIN", "COS", "SUPER_ADMIN"]
est_multi_sites = (role_actif in ROLES_MULTI_SITES) or (
    site_defaut_user in ["TOUS", "ALL"]
)

st.session_state["user_profile"]["role"] = role_actif


# =========================================================================
# 4. FONCTION DE CLÔTURE DE VACATION BDD
# =========================================================================
def executer_deconnexion_et_cloture():
    """Clôture la vacation 'EN_COURS' dans la table 'vacations' en renseignant 'fin_at' et 'statut' = 'CLOTUREE'."""
    vac_id = st.session_state.get("vacation_id")
    agent_nom = user.get("full_name", "KUTER ERIC")
    site_id = st.session_state.get("site_actif", "DINUM")
    now_dt = get_now_nc()

    try:
        # A. Clôture par UUID direct
        if vac_id and len(str(vac_id)) == 36:
            supabase.table("vacations").update({
                "statut": "CLOTUREE",
                "fin_at": now_dt.isoformat(),
            }).eq("id", vac_id).execute()

        # B. Fallback : Clôture globale des vacations 'EN_COURS' du site
        else:
            supabase.table("vacations").update({
                "statut": "CLOTUREE",
                "fin_at": now_dt.isoformat(),
            }).eq("site_id", site_id).eq("statut", "EN_COURS").execute()

        # C. Inscription de l'événement de fin de poste
        payload_fin = {
            "reference": f"REF-FIN-VAC-{now_dt.strftime('%Y%m%d-%H%M%S')}",
            "vacation_id": vac_id
            if (vac_id and len(str(vac_id)) == 36)
            else None,
            "site_id": site_id,
            "agent_nom": agent_nom,
            "horodatage": now_dt.isoformat(),
            "type_evenement": "FIN_VACATION",
            "description": (
                f"🚪 Déconnexion de {agent_nom} — Clôture automatique de la"
                " Main Courante."
            ),
            "actions_menees": (
                "Fin de poste enregistrée et vacation fermée (CLOTUREE)."
            ),
        }
        supabase.table("mc_evenements").insert(payload_fin).execute()

    except Exception as err:
        st.warning(f"Note lors de la déconnexion BDD : {err}")

    st.session_state.clear()
    st.rerun()


# =========================================================================
# 5. SIDEBAR : EN-TÊTE, FICHE AGENT & SÉLECTEUR DE SITE DYNAMIQUE
# =========================================================================
st.sidebar.markdown("## 🌐 **ORBIS**")
st.sidebar.caption("Main Courante V3")
st.sidebar.markdown("---")

st.sidebar.markdown(f"👤 **{user.get('full_name', 'AGENT')}**")
st.sidebar.caption(
    f"🏢 Service : {user.get('service', 'PC Garde')} | 🔑 Rôle :"
    f" `{role_actif}`"
)

# Branchement dynamique du sélecteur de site BDD
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

# Consultation du registre historique (Haute habilitation)
HAUTE_HABILITATION = ["HABI_ORBIS", "CHARGE_SURETE", "ADMIN", "COS", "SUPER_ADMIN"]
if role_actif in HAUTE_HABILITATION:
    menu_options["📖 Consulter Registre"] = "registre"

# Modules opérationnels communs à tous les agents (y compris AGENT_SECU)
menu_options.update({
    "✍️ Visiteur Imprévu": "visiteur_imprevu",
    "👥 Visiteurs Attendus": "visiteurs_attendus",
    "🔦 Suivi des Rondes": "suivi_rondes",
    "⚠️ Anomalies & Vigilance": "anomalies",
    label_badges: "badges",
    "🚗 Gestion des Permis": "permis",
})

# Modules réservés exclusivement à l'Administration et la Supervision
ROLES_ADMIN_ONLY = ["ADMIN", "SUPER_ADMIN", "CHARGE_SURETE", "COS"]
if role_actif in ROLES_ADMIN_ONLY:
    menu_options["⚙️ Consignes (Admin)"] = "consignes_admin"
    menu_options["🛡️ Hypervision COS"] = "hypervision"

# Recherche prestataires pour tous
menu_options["🔍 Recherche Prestataires"] = "recherche_prestataires"

selection_label = st.sidebar.radio("Navigation", list(menu_options.keys()))
module_actif = menu_options[selection_label]

st.sidebar.markdown("---")

# BOUTON DE DÉCONNEXION AVEC CLÔTURE AUTOMATIQUE
if st.sidebar.button(
    "🚪 Déconnecter & Clôturer Main Courante",
    type="primary",
    use_container_width=True,
):
    executer_deconnexion_et_cloture()

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