# Wetility HSE Installer Onboarding Portal

An automated, secure web portal built for Wetility to streamline the onboarding, vetting, and compliance tracking of solar EPC contractors and BESS installers. 

This tool enforces compliance with OHSA 85 of 1993, Construction Regulations 2014, and Wetility SHE Specifications through an automated gating system, replacing manual safety file reviews.

## 🚀 Key Features
* **Automated Workflow Gates:** 
  * **Gate 0:** Pre-qualification questionnaire with automated knock-out logic and NDA verification.
  * **Stage 1:** Statutory company compliance (CIPC, COIDA, Liability Insurance, Wireman's Licence, etc.).
  * **Stage 2:** Comprehensive 28-item HSE File and dynamic Personnel Roster tracking individual site worker compliance (Medical COFs, PV GreenCards, ID copies).
* **Automated Expiry Parsing:** Integrates Google Cloud Vision API to analyze document text and flag expiring certificates.
* **Relational Integrity:** Powered by Supabase PostgreSQL, ensuring clean document upserts separated by company-scope and person-scope requirements.
* **Secure Storage:** Private Supabase storage buckets segment documents by onboarding stage.

## 🛠️ Tech Stack
* **Frontend:** [Streamlit](https://streamlit.io/) (Python)
* **Backend & Database:** [Supabase](https://supabase.com/) (PostgreSQL & Storage)
* **OCR Verification:** Google Cloud Vision API

---

## 💻 Local Development Setup

**1. Clone the repository**
```bash
git clone [https://github.com/SelloP28/installer-onboarding-portal.git](https://github.com/SelloP28/installer-onboarding-portal.git)
cd installer-onboarding-portal
