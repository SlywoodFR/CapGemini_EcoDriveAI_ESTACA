import joblib
import pandas as pd
import numpy as np

# 1. Chargement du Cerveau
print("🧠 Chargement du modèle...")
try:
    brain = joblib.load('ev_brain_v1.pkl')
    model = brain['model']
    features = brain['features']
    print(f"✅ Modèle chargé. Il attend {len(features)} colonnes.")
except Exception as e:
    print(f"❌ Erreur : {e}")
    exit()

# 2. Test avec une ligne EXACTE du dataset
# On simule ce que 'Train_Model' a fait
print("\n🧪 TEST 1 : Donnée du CSV (Training)")
csv_row = {
    'Speed_kmh': 111.5,
    'Wind_Speed_ms': 7.8, # Value approx
    'Vehicle_Weight_kg': 1822.9,
    'Slope_%': 6.87,
    'Distance_Travelled_km': 20.75,
    'Tire_Pressure_psi': 31.1,
    'Battery_Temperature_C': 25.3,
    'Temperature_C': 0.74,
    'Humidity_%': 42.1,
    # Catégories (Mapping: 1->Highway, 2->Normal)
    'Driving_Mode_Normal': 1,
    'Road_Type_Highway': 1,
    'Traffic_Condition_Low': 1,
    'Weather_Condition_Snowy': 1 
}

# Création DataFrame
df_test = pd.DataFrame([csv_row])

# Ajout des colonnes manquantes avec 0
for col in features:
    if col not in df_test.columns:
        df_test[col] = 0.0

# Prédiction brute (sans le max(0))
raw_pred = model.predict(df_test[features])[0]
print(f"   -> Prédiction : {raw_pred:.4f} kWh")
print(f"   -> Attendu    : ~12.05 kWh")

if raw_pred < 0.1:
    print("⚠️  ALERTE : Le modèle a appris à prédire ZERO. Le dataset d'entraînement était probablement corrompu (tout à 0).")
else:
    print("✅  Le modèle fonctionne sur les données d'entraînement.")

# 3. Test avec le Contexte de Main.py
print("\n🧪 TEST 2 : Donnée de Main.py (Inférence)")
main_context = {
    'Speed_kmh': 110,
    'Wind_Speed_ms': 5.0,
    'Vehicle_Weight_kg': 1700,
    'Slope_%': 0.5,
    'Distance_Travelled_km': 5.1,
    'Tire_Pressure_psi': 40,
    'Battery_Temperature_C': 30,
    'Temperature_C': 7,
    'Humidity_%': 50,
    # Main.py active ces colonnes manuellement
    'Road_Type_Highway': 1,
    'Driving_Mode_Normal': 1,
    'Traffic_Condition_Low': 1,
    'Weather_Condition_Sunny': 1
}

df_main = pd.DataFrame([main_context])
for col in features:
    if col not in df_main.columns:
        df_main[col] = 0.0

# Feature Engineering manquant dans le test brut, on l'ajoute pour être juste
df_main['Effective_Air_Speed_Sq'] = (df_main['Speed_kmh'] + (df_main['Wind_Speed_ms'] * 3.6))**2
df_main['Elevation_Work_Proxy'] = df_main['Vehicle_Weight_kg'] * 9.81 * (df_main['Slope_%'] / 100) * df_main['Distance_Travelled_km']
df_main['Rolling_Resistance_Proxy'] = df_main['Vehicle_Weight_kg'] / df_main['Tire_Pressure_psi']
df_main['Battery_Thermal_Bias'] = (df_main['Battery_Temperature_C'] - 25).abs()

pred_main = model.predict(df_main[features])[0]
print(f"   -> Prédiction : {pred_main:.4f} kWh")