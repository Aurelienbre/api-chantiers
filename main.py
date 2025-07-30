#!/usr/bin/env python3
"""
Script de test pour valider les endpoints de synchronisation
Utilisez ce script pour tester votre API avant déploiement
"""

import requests
import json
from datetime import datetime

# Configuration
API_BASE_URL = "https://api-chantiers.onrender.com"  # À modifier pour votre URL Render
# API_BASE_URL = "https://votre-app-render.onrender.com"

def test_endpoint(method, endpoint, data=None, description=""):
    """Test un endpoint et affiche le résultat"""
    print(f"\n🔍 {description}")
    print(f"   {method} {endpoint}")
    
    try:
        if method == "GET":
            response = requests.get(f"{API_BASE_URL}{endpoint}")
        elif method == "POST":
            response = requests.post(
                f"{API_BASE_URL}{endpoint}", 
                json=data,
                headers={'Content-Type': 'application/json'}
            )
        elif method == "PUT":
            response = requests.put(
                f"{API_BASE_URL}{endpoint}", 
                json=data,
                headers={'Content-Type': 'application/json'}
            )
        
        if response.status_code == 200:
            result = response.json()
            print(f"   ✅ Succès : {result}")
            return result
        else:
            print(f"   ❌ Erreur {response.status_code} : {response.text}")
            return None
            
    except requests.exceptions.ConnectionError:
        print(f"   ❌ Erreur de connexion - Vérifiez que l'API fonctionne sur {API_BASE_URL}")
        return None
    except Exception as e:
        print(f"   ❌ Erreur : {e}")
        return None

def run_tests():
    """Lance une série de tests complets"""
    print("🚀 Tests des endpoints de synchronisation")
    print("=" * 50)
    
    # 1. Test de la connexion de base
    test_endpoint("GET", "/", description="Test de connexion de base")
    
    # 2. Test de la base de données
    test_endpoint("GET", "/test-database", description="Test de connexion PostgreSQL")
    
    # 3. Migration des données
    test_endpoint("GET", "/migrate-data", description="Migration des données initiales")
    
    # 4. Récupération des données existantes
    chantiers = test_endpoint("GET", "/chantiers", description="Récupération des chantiers")
    preparateurs = test_endpoint("GET", "/preparateurs", description="Récupération des préparateurs")
    disponibilites = test_endpoint("GET", "/disponibilites", description="Récupération des disponibilités")
    
    # 5. Création d'un chantier de test
    chantier_test = {
        "id": "CH-TEST-001",
        "label": "Chantier de test API",
        "status": "Nouveau",
        "prepTime": 120,  # 2 heures en minutes
        "endDate": "31/08/2025",
        "preparateur": "Eric CHAPUIS",
        "ChargeRestante": 120
    }
    
    test_endpoint("POST", "/chantiers", chantier_test, "Création d'un chantier de test")
    
    # 6. Mise à jour du chantier
    chantier_update = {
        "status": "Prépa. en cours",
        "preparateur": "Sylvain MATHAIS",
        "ChargeRestante": 90
    }
    
    test_endpoint("PUT", "/chantiers/CH-TEST-001", chantier_update, "Mise à jour du chantier de test")
    
    # 7. Test de planification
    planification_test = {
        "chantier_id": "CH-TEST-001",
        "planifications": {
            "2025-W31-1": 60,
            "2025-W32-1": 30,
            "2025-W33-1": 30
        }
    }
    
    test_endpoint("PUT", "/planification", planification_test, "Mise à jour de la planification")
    
    # 8. Test de disponibilités
    disponibilites_test = {
        "preparateur_nom": "Eric CHAPUIS",
        "disponibilites": {
            "2025-W31-1": {"minutes": 480, "updatedAt": datetime.now().isoformat()},
            "2025-W32-1": {"minutes": 480, "updatedAt": datetime.now().isoformat()},
            "2025-W33-1": {"minutes": 240, "updatedAt": datetime.now().isoformat()}
        }
    }
    
    test_endpoint("PUT", "/disponibilites", disponibilites_test, "Mise à jour des disponibilités")
    
    # 9. Test de synchronisation complète
    sync_data = {
        "chantiers": {
            "CH-TEST-001": {
                "id": "CH-TEST-001",
                "label": "Chantier sync complet",
                "status": "Prépa. en cours",
                "prepTime": 180,
                "endDate": "31/08/2025",
                "preparateur": "Eric CHAPUIS",
                "ChargeRestante": 60,
                "planification": {
                    "2025-W31-1": 90,
                    "2025-W32-1": 90
                }
            }
        },
        "data": {
            "Eric CHAPUIS": {
                "2025-W31-1": {"minutes": 480, "updatedAt": datetime.now().isoformat()},
                "2025-W32-1": {"minutes": 480, "updatedAt": datetime.now().isoformat()}
            }
        }
    }
    
    test_endpoint("PUT", "/sync-planning", sync_data, "Synchronisation complète de test")
    
    # 10. Vérification finale
    print(f"\n📊 Vérification finale des données")
    final_chantiers = test_endpoint("GET", "/chantiers", description="Chantiers après tests")
    
    if final_chantiers and "CH-TEST-001" in final_chantiers:
        print("   ✅ Chantier de test trouvé dans la base")
        print(f"   📋 Données : {final_chantiers['CH-TEST-001']}")
    else:
        print("   ❌ Chantier de test non trouvé")
    
    print(f"\n🎉 Tests terminés ! Vérifiez les résultats ci-dessus.")
    print(f"💡 Si tous les tests sont ✅, votre API est prête pour la synchronisation.")

if __name__ == "__main__":
    run_tests()
