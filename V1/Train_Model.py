import time
import pandas as pd
import numpy as np
import pickle
from sklearn.model_selection import train_test_split, GridSearchCV
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_squared_error, r2_score

# Import different model types to compare
from sklearn.linear_model import LinearRegression
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.svm import SVR
from sklearn.neural_network import MLPRegressor  # Added Neural Network

start_time = time.time()

# Load the data
def load_data(filepath):
    try:
        df = pd.read_csv(filepath)
        return df
    except FileNotFoundError:
        print("Error: File not found")
        return None

# Preprocess the data
def preprocess_data(df):
    # Drop rows with missing values
    df = df.dropna()
    return df

# Compare multiple models and select the best one
def train_and_compare_models(X, y):
    # Split the data
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    
    # Scale the features
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)
    
    # Define a list of models to test with their specific hyperparameter grids
    model_candidates = [
        {
            'name': 'Linear Regression (Baseline)',
            'model': LinearRegression(),
            'params': {} 
        },
        {
            'name': 'Random Forest',
            'model': RandomForestRegressor(random_state=42),
            'params': {
                'n_estimators': [100, 200, 300],
                'max_depth': [None, 10, 20],
                'min_samples_split': [2, 5]
            }
        },
        {
            'name': 'Gradient Boosting',
            'model': GradientBoostingRegressor(random_state=42),
            'params': {
                'n_estimators': [200, 300, 500],
                'learning_rate': [0.05, 0.1, 0.2],
                'max_depth': [3, 4, 5]
            }
        },
        {
            'name': 'Support Vector Regression (SVR)',
            'model': SVR(),
            'params': {
                'C': [1, 10, 100],
                'kernel': ['rbf'], 
                'epsilon': [0.1, 0.2]
            }
        },
        {
            'name': 'Neural Network (MLP)',
            'model': MLPRegressor(random_state=42, max_iter=1000), # Increased max_iter for convergence
            'params': {
                'hidden_layer_sizes': [(50, 50), (100,), (100, 50)], # Deep vs Wide networks
                'activation': ['relu', 'tanh'],
                'alpha': [0.0001, 0.05] # Regularization to prevent overfitting
            }
        }
    ]

    best_model = None
    best_r2 = -np.inf
    best_name = ""
    best_mse = 0

    print(f"\n🚀 Starting Model Comparison with {len(model_candidates)} candidates...\n")
    print("You will see a log line for each test below. This confirms the program is running!")

    for candidate in model_candidates:
        print(f"--- Training {candidate['name']} ---")
        
        if candidate['params']:
            # verbose=3 ensures you see output for every step
            grid = GridSearchCV(estimator=candidate['model'], 
                                param_grid=candidate['params'], 
                                cv=5, n_jobs=-1, verbose=3, scoring='r2')
            grid.fit(X_train_scaled, y_train)
            current_model = grid.best_estimator_
            print(f"   Best Params: {grid.best_params_}")
        else:
            current_model = candidate['model']
            current_model.fit(X_train_scaled, y_train)
        
        # Evaluate on the Test Set
        y_pred = current_model.predict(X_test_scaled)
        r2 = r2_score(y_test, y_pred)
        mse = mean_squared_error(y_test, y_pred)
        
        print(f"   👉 Test R² Score: {r2:.4f} | MSE: {mse:.4f}")
        
        if r2 > best_r2:
            best_r2 = r2
            best_mse = mse
            best_model = current_model
            best_name = candidate['name']
            print(f"   🌟 New Leader!")
        
        print("") 

    return best_model, scaler, best_mse, best_r2, best_name

def main():
    # Load the data
    df = load_data('Datasets/EV_Energy_Consumption_Dataset.csv')
    
    if df is not None:
        # Preprocess the data (Original features only)
        df_processed = preprocess_data(df)
        
        # Original feature columns
        feature_columns = ['Speed_kmh','Temperature_C', 'Battery_State_%','Road_Type', 'Traffic_Condition', 'Vehicle_Weight_kg', 'Distance_Travelled_km','Driving_Mode', 'Slope_%']  
        target_column = 'Energy_Consumption_kWh'   
        
        actual_features = [col for col in feature_columns if col in df_processed.columns]
        X = df_processed[actual_features]
        y = df_processed[target_column]
        
        # Run the comparison
        model, scaler, mse, r2, model_name = train_and_compare_models(X, y)
        
        # Print Final Results
        print("=" * 40)
        print(f"🏆 BEST MODEL: {model_name}")
        print(f"Final Test Mean Squared Error: {mse:.4f}")
        print(f"Final Test R² Score: {r2:.4f}")
        print("=" * 40)

        print("Total execution time : --- %s seconds ---" % (time.time() - start_time))

        # --- SAVE THE BEST MODEL ---
        print(f"\nSaving {model_name} to 'ev_model_bundle.pkl'...")
        
        model_bundle = {
            'model': model,
            'scaler': scaler,
            'feature_names': actual_features,
            'model_type': model_name
        }
        
        with open('ev_model_bundle.pkl', 'wb') as f:
            pickle.dump(model_bundle, f)
            
        print("Model saved successfully!")

if __name__ == "__main__":
    main()