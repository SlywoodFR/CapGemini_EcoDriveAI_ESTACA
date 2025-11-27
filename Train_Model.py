import time
import pandas as pd
import numpy as np
import pickle
from sklearn.model_selection import train_test_split, GridSearchCV
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

# Train model with Cross-Validation (Grid Search)
def train_model(X, y):
    # Split the data
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    
    # Scale the features
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)
    
    # Define the parameter grid to search
    # This tries different combinations to find the best "settings" for the AI
    param_grid = {
        'n_estimators': [100, 200, 300],      # Number of trees
        'max_depth': [None, 10, 20, 30],      # Max depth of trees
        'min_samples_split': [2, 5, 10],      # Min samples to split a node
        'min_samples_leaf': [1, 2, 4]         # Min samples at a leaf node
    }
    
    # Initialize base model
    rf = RandomForestRegressor(random_state=42)
    
    # Initialize GridSearchCV
    # cv=5 means "5-Fold Cross Validation" (Train on 4 parts, test on 1, repeat 5 times)
    # n_jobs=-1 means use all computer processors to go faster
    print("Starting Hyperparameter Tuning (this may take a minute)...")
    grid_search = GridSearchCV(estimator=rf, param_grid=param_grid, 
                               cv=5, n_jobs=-1, verbose=1, scoring='r2')
    
    # Fit the grid search
    grid_search.fit(X_train_scaled, y_train)
    
    # Get the best model found
    best_model = grid_search.best_estimator_
    
    print(f"\n✅ Best Parameters found: {grid_search.best_params_}")
    print(f"Best Cross-Validation R2 Score: {grid_search.best_score_:.4f}")
    
    # Make predictions using the best model
    y_pred = best_model.predict(X_test_scaled)
    
    # Calculate metrics on the test set
    mse = mean_squared_error(y_test, y_pred)
    r2 = r2_score(y_test, y_pred)
    
    return best_model, scaler, mse, r2, X_test, y_test, y_pred

def main():
    # Load the data
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
        print("-" * 30)
        print(f"Final Test Mean Squared Error: {mse:.4f}")
        print(f"Final Test R² Score: {r2:.4f}")
        print("-" * 30)

        print("Total execution time : --- %s seconds ---" % (time.time() - start_time))

        # Example prediction
        print("\nRunning test prediction...")
        start_time_prediction = time.time()
        example_data = np.array([[111.5, 0, 30, 1, 1, 1823, 21, 2, 6.9]])
        example_data_scaled = scaler.transform(example_data)
        prediction = model.predict(example_data_scaled)
        
        print(f"Example Prediction: E = {prediction[0]:.2f} kWh")
        print(f"Real Value: E = 12.0 kWh")
        print("Prediction time : --- %s seconds ---" % (time.time() - start_time_prediction))

        # --- SAVE THE MODEL AND SCALER ---
        # We save it so predict_app.py and geo_weather_app.py can use the IMPROVED model
        print("\nSaving improved model to 'ev_model_bundle.pkl'...")
        
        model_bundle = {
            'model': model,
            'scaler': scaler,
            'feature_names': feature_columns
        }
        
        with open('ev_model_bundle.pkl', 'wb') as f:
            pickle.dump(model_bundle, f)
            
        print("Model saved successfully!")

if __name__ == "__main__":
    main()