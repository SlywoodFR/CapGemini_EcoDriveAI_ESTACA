import smartcar
import webbrowser

# --- CONFIGURATION ---
CLIENT_ID = '474fb84e-7dad-49d9-af3d-b82727c213db'
CLIENT_SECRET = '2c9940fb-3997-4b0e-b57b-6f3f521df2eb'
REDIRECT_URI = 'http://localhost:8501'

# 1. Initialisation du client (test_mode=True conservé comme demandé)
client = smartcar.AuthClient(
    client_id=CLIENT_ID,
    client_secret=CLIENT_SECRET,
    redirect_uri=REDIRECT_URI,
    test_mode=True
)

# 2. GÉNÉRATION DE L'URL
# On demande la batterie et les infos de base
scope = ['read_battery', 'read_vehicle_info']
options = {'mode': 'simulated', 'force_prompt': True}
auth_url = client.get_auth_url(scope, options)

# Correction manuelle si nécessaire (ton hack efficace)
if "mode=test" in auth_url:
    auth_url = auth_url.replace("mode=test", "mode=simulated")

print("="*60)
print("🔌 SMARTCAR - TEST MODE SIMULÉ")
print("="*60)
print(f"URL à ouvrir : {auth_url}")
webbrowser.open(auth_url)

# 3. RÉCUPÉRATION DU CODE
raw_url = input("\n👉 Copiez l'URL de retour complète : ")
auth_code = raw_url.split('code=')[-1].split('&')[0]

try:
    # 4. ÉCHANGE DU CODE (Code à usage unique, expire après 10 min)
    access = client.exchange_code(auth_code)
    token = access.access_token 
    
    print("\n✅ Jeton d'accès récupéré.")

    # 5. RÉCUPÉRATION DES DONNÉES
    res_vehicles = smartcar.get_vehicles(token)
    
    # On vérifie qu'un véhicule est bien présent
    if not res_vehicles.vehicles:
        print("❌ Aucun véhicule trouvé sur ce compte.")
    else:
        vehicle = smartcar.Vehicle(res_vehicles.vehicles[0], token)
        
        # Récupération des attributs et de la batterie
        info = vehicle.attributes()
        battery_data = vehicle.battery() 
        
        print("\n" + "-"*30)
        print(f"🚗 VÉHICULE CONNECTÉ : {info.make} {info.model}")
        # percent_remaining est la valeur standard pour 2026
        print(f"🔋 NIVEAU DE BATTERIE : {battery_data.percent_remaining * 100}%")
        print("-" * 30)

except smartcar.SmartcarException as e:
    # Gestion spécifique des erreurs de permission
    print(f"\n❌ Erreur Smartcar : {e.message}")
    print("Vérifiez que le véhicule simulé choisi supporte bien la lecture de batterie.")
except Exception as e:
    print(f"\n❌ Autre erreur : {e}")