# =========================================================================
# MODULE : MESSAGERIE INTERNE & ÉCHANGES (views/discussion.py)
# Description : Canal de communication asynchrone sécurisé inter-sites
#               avec ciblage précis par site et par destinataire.
# =========================================================================
import datetime
from pathlib import Path
import sys
import zoneinfo
import streamlit as st

# --- FIX DES CHEMINS ---
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from utils.db_client import supabase

TZ_NC = zoneinfo.ZoneInfo("Pacific/Noumea")


def get_now_nc() -> datetime.datetime:
    """Retourne la date et l'heure actuelles en Nouvelle-Calédonie."""
    return datetime.datetime.now(TZ_NC)


def formatter_horodatage_nc(iso_str: str) -> str:
    """Formate une date ISO BDD en format francophone lisible (DD/MM/YYYY à HH:MM)."""
    if not iso_str:
        return "--/--/---- --:--"
    try:
        dt = datetime.datetime.fromisoformat(str(iso_str))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        dt_nc = dt.astimezone(TZ_NC)
        return dt_nc.strftime("%d/%m/%Y à %H:%M")
    except Exception:
        return str(iso_str)


def fetch_sites_liste() -> list[str]:
    """Récupère la liste des sites actifs depuis Supabase."""
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
    except Exception:
        return ["DINUM", "SITE DOUMER", "SITE OUEMO"]


def fetch_utilisateurs_par_site(site_nom: str) -> list[str]:
    """Récupère dynamiquement les noms des utilisateurs (AGENT_SECU & HABI_ORBIS)."""
    agents = []
    try:
        res_users = (
            supabase.table("Utilisateur")
            .select("nom, login, role")
            .in_("role", ["AGENT_SECU", "HABI_ORBIS"])
            .order("nom")
            .execute()
        )

        if res_users.data:
            for u in res_users.data:
                nom_agent = str(u.get("nom") or u.get("login") or "").strip().upper()
                if nom_agent and nom_agent not in agents:
                    agents.append(nom_agent)

    except Exception as err:
        print(f"⚠️ Erreur chargement Utilisateur : {err}")

    return agents


def show():
    st.title("💬 Fil d'Échanges & Notes de Service")

    site_session = st.session_state.get("site_actif", "DINUM")
    user_info = st.session_state.get("user_profile", {"full_name": "Agent PC Security"})
    user_nom = str(user_info.get("full_name", "Agent PC")).strip().upper()
    role_user = str(user_info.get("role", "AGENT_SECU")).upper().strip()

    # Détection des privilèges d'administration
    is_user_admin = any(
        k in role_user for k in ["ADMIN", "SUPER_ADMIN", "CHARGE_SURETE", "COS"]
    ) or any(k in user_nom for k in ["KUTER", "ADMIN", "SURETE"])

    st.caption(
        f"Espace de communication sécurisé | Site actif : **{site_session}** | Connecté : **{user_nom}**"
    )

    liste_sites = fetch_sites_liste()

    # 1. FORMULAIRE D'ENVOI DE MESSAGE
    with st.container(border=True):
        st.markdown("**✍️ Transmettre une question ou un message ciblé :**")

        c_site, c_agent, c_msg = st.columns([1.5, 1.5, 3])

        idx_site = liste_sites.index(site_session) if site_session in liste_sites else 0

        with c_site:
            site_destinataire = st.selectbox(
                "📍 Site destinataire :",
                options=liste_sites,
                index=idx_site,
                key="select_site_dest",
            )

        liste_agents = fetch_utilisateurs_par_site(site_destinataire)
        options_destinataires = [
            "TOUS (Diffusion Générale)",
            "🛡️ ADMIN / SURETE (Direction)",
        ] + [ag for ag in liste_agents if ag != user_nom]

        with c_agent:
            agent_destinataire = st.selectbox(
                "👤 Destinataire :",
                options=options_destinataires,
                key="select_agent_dest",
            )

        with c_msg:
            message_text = st.text_area(
                "Votre message :",
                placeholder="Ex: Concernant la ronde de 03:00...",
                height=80,
                key="input_text_msg",
            )

        if st.button("📤 Envoyer le message", type="primary", use_container_width=True):
            if message_text.strip():
                if agent_destinataire == "TOUS (Diffusion Générale)":
                    dest_final = "TOUS"
                elif agent_destinataire == "🛡️ ADMIN / SURETE (Direction)":
                    dest_final = "ADMIN_SURETE"
                else:
                    dest_final = agent_destinataire

                payload = {
                    "site_id": site_destinataire,
                    "expediteur_nom": user_nom,
                    "destinataire_nom": dest_final,
                    "message": message_text.strip(),
                    "lu": False,
                }
                try:
                    supabase.table("mc_discussion").insert(payload).execute()
                    st.toast(
                        f"Message transmis à **{dest_final}** sur **{site_destinataire}** !",
                        icon="✅",
                    )
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Erreur lors de l'envoi : {e}")
            else:
                st.warning("⚠️ Veuillez saisir un message avant d'envoyer.")

    st.markdown("---")

    # 2. FILTRES ET HISTORIQUE DES MESSAGES
    col_h_title, col_h_filter = st.columns([2, 1.5])
    with col_h_title:
        st.subheader(f"📜 Historique des messages — {site_session}")
    with col_h_filter:
        voir_tous_sites = st.checkbox(
            "🌐 Afficher tous les sites (Vue Supervision)",
            value=False,
            disabled=not is_user_admin,
            help="Réservé aux Administrateurs et Sûreté",
        )

    try:
        query = supabase.table("mc_discussion").select("*")
        if not voir_tous_sites:
            query = query.eq("site_id", site_session)

        res = query.order("created_at", desc=True).limit(50).execute()

        if res.data:
            nb_msg_affiches = 0
            ids_a_marquer_lus = []

            for msg in res.data:
                msg_id = msg.get("id")
                exp = str(msg.get("expediteur_nom", "INCONNU")).strip().upper()
                dest = str(msg.get("destinataire_nom", "TOUS")).strip().upper()
                est_lu = msg.get("lu", False)
                site_msg = msg.get("site_id", site_session)
                txt = msg.get("message", "")
                dt_str = formatter_horodatage_nc(msg.get("created_at"))

                # Règle de confidentialité
                est_pour_moi = (
                    (dest == user_nom)
                    or (dest == "TOUS")
                    or (dest == "ADMIN_SURETE" and is_user_admin)
                )
                est_de_moi = exp == user_nom

                if is_user_admin or est_pour_moi or est_de_moi:
                    nb_msg_affiches += 1

                    if not est_lu and est_pour_moi and not est_de_moi and msg_id:
                        ids_a_marquer_lus.append(msg_id)

                    msg_from_admin = any(
                        k in exp for k in ["KUTER", "ADMIN", "SURETE", "COS"]
                    )
                    avatar_icon = "🛡️" if msg_from_admin else "👮‍♂️"

                    with st.chat_message(
                        "assistant" if msg_from_admin else "user", avatar=avatar_icon
                    ):
                        if dest == "TOUS":
                            badge_dest = "🌐 **Tous**"
                        elif dest == "ADMIN_SURETE":
                            badge_dest = "🔒 **@ADMIN / SÛRETÉ (Message Privé)**"
                        else:
                            badge_dest = (
                                f"🔒 **@{dest} (Message Privé)**"
                                if dest != user_nom
                                else f"➡️ **@{dest}**"
                            )

                        if is_user_admin and not est_pour_moi and not est_de_moi:
                            badge_dest += " *(👁️ Vue Supervision)*"

                        st.markdown(
                            f"**{exp}** ({site_msg}) {badge_dest}  \n"
                            f"<small style='color: #888;'>📅 {dt_str}</small>",
                            unsafe_allow_html=True,
                        )
                        st.write(txt)

            # Passage automatique en "lu = True"
            if ids_a_marquer_lus:
                try:
                    supabase.table("mc_discussion").update({"lu": True}).in_(
                        "id", ids_a_marquer_lus
                    ).execute()
                except Exception as err_lu:
                    print(f"Note mise à jour statut lu : {err_lu}")

            if nb_msg_affiches == 0:
                st.info("ℹ️ Aucun message vous concernant n'a été trouvé dans le fil.")
        else:
            st.info(
                f"ℹ️ Aucun message enregistré pour le moment pour le site {site_session}."
            )

    except Exception as e:
        st.error(f"❌ Erreur de chargement de la BDD : {e}")


if __name__ == "__main__":
    show()
