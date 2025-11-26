# Phase 2 — Recherche du dataset et création du code

Ce document rassemble la deuxième phase du projet : recherche du dataset, analyse de celui-ci, détermination des features, création du code avec choix du type de machine learning et création du code principal avec ajout des API. Il sert de base à la création du code final et à l'interface utilisateur.

---

## 1. Recherche du dataset

Comme mentionné dans la partie 1, nous avons utiliser le site Kaggle pour trouver notre base de données. Nos critères principaux était bien sûr l'énergie consommée car il s'agit de notre objectif mais nous voulions aussi en priorité, la distance parcourue, la vitesse moyenne et le pourcentage de batterie au départ. Nous avons réussi à trouver une base de données très complète avec : la vitesse en km/h, l’accélération en m/s², l’état de la batterie en %, la tension de la batterie en V, la température de la batterie en °C, le mode de conduite, le type de route, les conditions de circulation, la pente en %, les conditions météorologiques, la température en °C, l’humidité en %, la vitesse du vent en m/s, la pression des pneus en psi, la masse du véhicule en kg, la distance parcourue en km et la consommation d’énergie en kWh

## 2. Nettoyage du dataset et création du model de machinelearning

Nous avons ensuite étudié quelle features serait possible à récupérer à partir uniquement des données véhicule et d'APIs avec le lieu de départ et le lieu d'arrivé, ce qui à donnée lieu à 7 features : la vitesse en km/h, l’état de la batterie en %, le type de route, les conditions de circulation, la température en °C, la masse du véhicule en kg et la distance parcourue en km.

Nous avons pu à partir de cela créer un logigramme :

![alt text](Attachements/P2I_Logigramme.png)

Nous avons converti ce logigramme en code dans le fichier **data.py**.

## 3. Création du code principal

Pour ce code nous avons choisi les APIs que nous allions devoir utiliser et après reflexion nous aurons :

- Traffic API de Tomtom : Récupère la vitesse moyenne d'un endroit en temps réel à partir des coordonées lat/long
- Matrix Routing v2 API de Tomtom : Récupère le chemin entre deux points à partir des coordonées lat/long de ces points
- Geocoding API de Tomtom : Récupère les coordonées lat/long à partir d'une adresse
- OpenMeteo : Récupère la température d'un endroit en temps réel à partir des coordonées lat/long

