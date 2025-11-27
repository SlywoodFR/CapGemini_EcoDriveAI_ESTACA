import time
import pandas as pd
import numpy as np
import pickle  # <--- Added pickle
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_squared_error, r2_score

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

# Train model
def train_model(X, y):
    # Split the data
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    
    # Scale the features
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)
    
    # Create and train the model
    model = RandomForestRegressor(n_estimators=100, random_state=42)
    model.fit(X_train_scaled, y_train)
    
    # Make predictions
    y_pred = model.predict(X_test_scaled)
    
    # Calculate metrics
    mse = mean_squared_error(y_test, y_pred)
    r2 = r2_score(y_test, y_pred)
    
    return model, scaler, mse, r2, X_test, y_test, y_pred

def main():
    # Load the data
    # Make sure this path points to your actual CSV file
    df = load_data('Datasets/EV_Energy_Consumption_Dataset.csv')
    
    if df is not None:
        # Preprocess the data
        df_processed = preprocess_data(df)
        
        # Specify your feature columns and target variable
        feature_columns = ['Speed_kmh','Temperature_C', 'Battery_State_%','Road_Type', 'Traffic_Condition', 'Vehicle_Weight_kg', 'Distance_Travelled_km','Driving_Mode', 'Slope_%']  
        target_column = 'Energy_Consumption_kWh'   
        
        X = df_processed[feature_columns]
        y = df_processed[target_column]
        
        # Train the model
        model, scaler, mse, r2, X_test, y_test, y_pred = train_model(X, y)
        
        # Print results
        print(f"Mean Squared Error: {mse:.2f}")
        print(f"R² Score: {r2:.2f}")
        print("Time of creation of AI : --- %s seconds ---" % (time.time() - start_time))

        # --- SAVE THE MODEL AND SCALER ---
        print("Saving model to 'ev_model_bundle.pkl'...")
        
        # We create a dictionary to store both the model and the scaler
        model_bundle = {
            'model': model,
            'scaler': scaler,
            'feature_names': feature_columns # Optional: helpful to remember the input order
        }
        
        with open('ev_model_bundle.pkl', 'wb') as f:
            pickle.dump(model_bundle, f)
            
        print("Model saved successfully!")

if __name__ == "__main__":
    main()