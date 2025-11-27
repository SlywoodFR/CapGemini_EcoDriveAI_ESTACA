import pickle
import numpy as np
from APIs import *

def load_ai_model(filename):
    """
    Loads the dictionary containing the model and scaler.
    """
    try:
        with open(filename, 'rb') as f:
            data = pickle.load(f)
        return data
    except FileNotFoundError:
        print(f"Error: {filename} not found.")
        return None

def main():
    print("Loading AI model...")
    ai_bundle = load_ai_model('ev_model_bundle.pkl')
    
    if ai_bundle is not None:
        model = ai_bundle['model']
        scaler = ai_bundle['scaler']
        
        print("Model loaded successfully.")
        
        new_data = np.array([[111.5, 0, 30, 1, 1, 1823, 21, 2, 6.9]])
        new_data_scaled = scaler.transform(new_data)
        prediction = model.predict(new_data_scaled)

        print("-" * 30)
        print(f"Predicted Energy Consumption: {prediction[0]:.2f} kWh")
        print("-" * 30)

if __name__ == "__main__":
    main()