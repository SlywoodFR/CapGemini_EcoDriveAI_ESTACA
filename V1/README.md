# CapGemini_EcoDriveAI_ESTACA :

P2I for studies at ESTACA in collaboration with CapGemini

# Génération BibTeX et Slides — EcoDriveAI (Phase 1) :

Ce dépôt contient :
- `references.bib` : bibliographie recommandée (BibTeX).
- `make_slides.py` : script Python pour générer un fichier PPTX de synthèse à partir de la bibliographie et d'un plan.

Remarque: le script Python lit `references.bib`, extrait les champs (author, title, year) et construit une présentation `.pptx` (python-pptx).

Générer les slides
- Lancer :
```bash
  python make_slides.py synthese_phase1.pptx
```
# Pré-requis pour les scripts

- Python 3.8+
- Installer dépendances :
  ```bash
  python3 -m pip install -r requirements.txt
  ```