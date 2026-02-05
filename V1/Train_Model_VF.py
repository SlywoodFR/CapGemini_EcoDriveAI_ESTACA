import pandas as pd
import xgboost as xgb
import joblib
import numpy as np
import warnings
from sklearn.model_selection import train_test_split, KFold, cross_val_score
from sklearn.metrics import r2_score

warnings.filterwarnings('ignore')

# ==========================================
# 1. CHARGEMENT
# ==========================================
FILE_PATH = 'Datasets/EV_Energy_Consumption_Dataset.csv'
COLUMN_NAMES = [
    "Vehicle_ID", "Timestamp", "Speed_kmh", "Acceleration_ms2", 
    "Battery_State_%", "Battery_Voltage_V", "Battery_Temperature_C", 
    "Driving_Mode", "Road_Type", "Traffic_Condition", "Slope_%", 
    "Weather_Condition", "Temperature_C", "Humidity_%", "Wind_Speed_ms", 
    "Tire_Pressure_psi", "Vehicle_Weight_kg", "Distance_Travelled_km", 
    "Energy_Consumption_kWh"
]

print("📂 Chargement du dataset...")
try:
    with open(FILE_PATH, 'r') as f:
        first_line = f.readline()
    if "Vehicle_ID" in first_line:
        df = pd.read_csv(FILE_PATH, header=0)
        df.columns = COLUMN_NAMES 
    else:
        df = pd.read_csv(FILE_PATH, header=None, names=COLUMN_NAMES)
except Exception as e:
    print(f"❌ Erreur : {e}")
    exit()

# ==========================================
# 2. NETTOYAGE
# ==========================================
print("🛠️  Préparation & Physique (P = F * v)...")

def clean_numeric(x):
    if isinstance(x, str): x = x.replace(',', '.').strip()
    return pd.to_numeric(x, errors='coerce')

# Cible
df['Energy_Consumption_kWh'] = df['Energy_Consumption_kWh'].apply(clean_numeric)
df = df.dropna(subset=['Energy_Consumption_kWh'])
df = df[df['Energy_Consumption_kWh'] > 0.01]

# Features
numeric_cols = [
    'Speed_kmh', 'Acceleration_ms2', 'Wind_Speed_ms', 'Vehicle_Weight_kg', 
    'Slope_%', 'Distance_Travelled_km', 'Tire_Pressure_psi', 
    'Battery_Temperature_C', 'Temperature_C', 'Humidity_%', 'Battery_State_%'
]
for col in numeric_cols:
    df[col] = df[col].apply(clean_numeric).fillna(0)

# Mappings
maps = {
    'Road_Type': {'1': 'Highway', '2': 'City', '3': 'Rural'},
    'Driving_Mode': {'1': 'Eco', '2': 'Normal', '3': 'Sport'},
    'Traffic_Condition': {'1': 'Low', '2': 'Medium', '3': 'High'},
    'Weather_Condition': {'1': 'Sunny', '2': 'Cloudy', '3': 'Rainy', '4': 'Snowy'}
}
for col in maps.keys():
    df[col] = df[col].astype(str).str.strip().map(maps[col]).fillna(df[col])

# ==========================================
# 3. FEATURE ENGINEERING (La formule gagnante)
# ==========================================
# 1. Puissance Drag (Cube)
df['Power_Drag'] = (df['Speed_kmh'] + df['Wind_Speed_ms']*3.6) ** 3
# 2. Puissance Inertie
df['Power_Inertia'] = df['Vehicle_Weight_kg'] * df['Acceleration_ms2'] * df['Speed_kmh']
# 3. Puissance Gravité
df['Power_Gravity'] = df['Vehicle_Weight_kg'] * df['Slope_%'] * df['Speed_kmh']
# 4. Puissance Thermique
df['Power_HVAC'] = (df['Temperature_C'] - 21).abs()

# One-Hot
df = pd.get_dummies(df, columns=['Driving_Mode', 'Road_Type', 'Traffic_Condition', 'Weather_Condition'])

# X / y
drop_cols = ['Vehicle_ID', 'Timestamp', 'Battery_Voltage_V', 'Energy_Consumption_kWh']
X = df.drop(columns=[c for c in drop_cols if c in df.columns])
y = df['Energy_Consumption_kWh']
X = X.apply(pd.to_numeric, errors='coerce').fillna(0)

# ==========================================
# 4. CROSS-VALIDATION (5-FOLD)
# ==========================================
print("\n🔄 Démarrage de la Cross-Validation (5 Folds)...")
# On utilise la config "Physique Augmentée" qui marchait bien
model_cv = xgb.XGBRegressor(
    objective='reg:squarederror',
    n_estimators=4000,
    learning_rate=0.01, 
    max_depth=8,
    subsample=0.8,
    colsample_bytree=0.8,
    random_state=42,
    n_jobs=-1
)

kfold = KFold(n_splits=5, shuffle=True, random_state=42)
cv_scores = cross_val_score(model_cv, X, y, cv=kfold, scoring='r2')

print(f"📊 Scores des 5 tests : {cv_scores}")
print(f"🏆 MOYENNE R² : {cv_scores.mean():.4f} (+/- {cv_scores.std():.4f})")

# ==========================================
# 5. ENTRAÎNEMENT FINAL
# ==========================================
print("\n🔄 Entraînement Final pour sauvegarde...")

X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.15, random_state=42)

final_model = xgb.XGBRegressor(
    objective='reg:squarederror',
    n_estimators=4000,
    learning_rate=0.01,
    max_depth=8,
    subsample=0.8,
    colsample_bytree=0.8,
    random_state=42,
    n_jobs=-1,
    early_stopping_rounds=100
)

final_model.fit(
    X_train, y_train,
    eval_set=[(X_test, y_test)],
    verbose=False
)

final_score = r2_score(y_test, final_model.predict(X_test))

print("="*40)
print(f"🚀 SCORE FINAL R² (Test Set) : {final_score:.4f}")
print("="*40)

# Sauvegarde
joblib.dump({'model': final_model, 'features': X.columns.tolist()}, 'ev_brain_v1.pkl')
print("💾 Cerveau sauvegardé : 'ev_brain_v1.pkl'")