# Phase 2 — Recherche du dataset et création du code

Ce document rassemble la deuxième phase du projet : recherche du dataset, analyse de celui-ci, détermination des features, création du code avec choix du type de machine learning et création du code principal avec ajout des API. Il sert de base à la création du code final et à l'interface utilisateur.

---

## 1. Recherche du dataset

Comme mentionné dans la partie 1, nous avons utiliser le site Kaggle pour trouver notre base de données. Nos critères principaux était bien sûr l'énergie consommée car il s'agit de notre objectif mais nous voulions aussi en priorité, la distance parcourue, la vitesse moyenne et le pourcentage de batterie au départ. Nous avons réussi à trouver une base de données très complète avec : la vitesse en km/h, l’accélération en m/s², l’état de la batterie en %, la tension de la batterie en V, la température de la batterie en °C, le mode de conduite, le type de route, les conditions de circulation, la pente en %, les conditions météorologiques, la température en °C, l’humidité en %, la vitesse du vent en m/s, la pression des pneus en psi, la masse du véhicule en kg, la distance parcourue en km et la consommation d’énergie en kWh

## 2. Nettoyage du dataset

Nous avons ensuite étudié quelle features serait possible à récupérer à partir uniquement des données véhicule et d'API avec le lieu de départ et le lieu d'arrivé, ce qui à donnée lieu à 7 features : la vitesse en km/h, l’état de la batterie en %, le type de route, les conditions de circulation, la température en °C, la masse du véhicule en kg et la distance parcourue en km.

Nous avons pu à partir de cela créer un logigramme :

<Attachements/P2I_Logigramme>


