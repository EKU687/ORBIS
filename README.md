# 🛡️ ORBIS — Main Courante Service Terrain (V3)

[![Version](https://img.shields.io/badge/Version-v3.3.0-blue.svg)](https://github.com/)
[![Environnement](https://img.shields.io/badge/Environnement-PRODUCTION-brightgreen.svg)](https://portail-gnc.streamlit.app)
[![Python](https://img.shields.io/badge/Python-3.14-blue.svg)](https://www.python.org/)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.x-red.svg)](https://streamlit.io/)
[![Database](https://img.shields.io/badge/Supabase-PostgreSQL-green.svg)](https://supabase.com/)

> **ORBIS Main Courante** est l'application métier dédiée à la traçabilité des événements de sécurité, à la gestion des vacations, au suivi des anomalies matérielles, à la communication inter-sites et à l'émargement obligatoire des consignes pour les Postes de Garde & Services Terrain.

---

## 📌 Fonctionnalités Principales

* 📝 **Main Courante & Journal de Bord :** Saisie d'événements horodatés en temps réel avec gestion stricte du fuseau horaire `Pacific/Noumea` (UTC+11).
* 💬 **Messagerie Interne & Notes de Service (v3.3.0) :** Canal d'échange asynchrone direct entre la Direction/Sûreté et les agents sur site, avec ciblage par agent (`AGENT_SECU`) ou par site, badge dynamique dans le menu et pop-up d'alerte modale intelligent (`@st.dialog`).
* 🔦 **Suivi & Émargement des Rondes (v3.2.1) :** Supervision des rondes de sûreté découplée en deux onglets distincts (*Rondes à venir* vs *Rondes effectuées*), avec décalage aléatoire déterministe (0 à 10 min) et fenêtre d'émargement active de 30 minutes.
* 🚪 **Moniteur des Mouvements & IDENTIS (v3.2.0) :** Console dédiée aux flux d'entrées/sorties interconnectée avec les tables IDENTIS (`Agents_Publics` & `Prestataires`), intégrant un contrôle d'accès à 2 niveaux (Poste de garde & Validation Sûreté) et un sélecteur de date francophone (`DD/MM/YYYY`).
* 📋 **Prise de Poste & Émargement Numérique :** Modale obligatoire de prise de connaissance des consignes et anomalies avec traçabilité juridique en base de données.
* 🚨 **Gestion des Anomalies & Directives Site :** Traçabilité des pannes matérielles et des consignes générales sans péremption automatique.
* 🎯 **Consignes Ciblées (Admin) :** Interface de création de consignes particulières temporaires attribuées spécifiquement à un agent ou un groupe d'agents.
* 🔑 **Authentification Hybride (SSO & SDK) :** Prise en charge du SSO Portail HUB et secours par clé matérielle **YubiKey** / Mot de passe.

---

## 🛠️ Stack Technique & Outils

* **Langage & Framework :** Python 3.14 / Streamlit
* **Backend :** Supabase (PostgreSQL 15+, RLS, Realtime)
* **Fuseau Horaire Applicatif :** `Pacific/Noumea` (UTC+11)
* **Qualité de code :** PEP 8 strict (Black Formatter & Linter Ruff)
* **CI/CD & Déploiement :** Streamlit Cloud (Déploiement automatique sur merge `main`) & Workflows GitHub Actions pour les rapports automatiques de rondes.

---

## 🚀 Installation & Lancement en Local

### 1. Prérequis
* Python 3.14+
* Git

### 2. Cloner le dépôt
```bash
git clone [https://github.com/votre-orga/main-courante.git](https://github.com/votre-orga/main-courante.git)
cd main-courante