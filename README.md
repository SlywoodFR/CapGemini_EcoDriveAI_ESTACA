# CapGemini_EcoDriveAI_ESTACA
P2I for studies at ESTACA in collaboration with CapGemini

# Génération BibTeX et Slides — EcoDriveAI (Phase 1)

Ce dépôt contient :
- `references.bib` : bibliographie recommandée (BibTeX).
- `make_slides.py` : script Python pour générer un fichier PPTX de synthèse à partir de la bibliographie et d'un plan.
- `requirements.txt` : dépendances Python nécessaires.

But: the Python script reads `references.bib`, extrait les champs (author, title, year) et construit une présentation `.pptx` (python-pptx).

Pré-requis
- Python 3.8+
- Installer dépendances :
  ```bash
  pip install python-pptx bibtexparser

