from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "API Pilotage RIP fonctionne!", "status": "✅ Version temporaire sans base de données"}

@app.get("/test-database")
def test_database():
    """Test de connexion à la base PostgreSQL"""
    database_url = os.environ.get('DATABASE_URL')
    
    if not database_url:
        return {
            "status": "❌ Échec",
            "error": "DATABASE_URL non définie",
            "solution": "Vérifiez la variable d'environnement sur Render"
        }
    
    try:
        # Test d'import psycopg3 (ou psycopg2 en fallback)
        try:
            import psycopg
            psycopg_status = f"✅ psycopg3 v{psycopg.__version__}"
            psycopg_module = psycopg
        except ImportError:
            import psycopg2
            psycopg_status = f"✅ psycopg2 v{psycopg2.__version__}"
            psycopg_module = psycopg2
    except ImportError as e:
        return {
            "status": "❌ Échec", 
            "error": f"Aucun module psycopg disponible: {e}",
            "database_url_present": True,
            "solution": "Installer psycopg[binary] ou psycopg2-binary"
        }
    
    try:
        # Test de connexion
        from urllib.parse import urlparse
        url = urlparse(database_url)
        
        # Adapter les paramètres selon la version psycopg
        if 'psycopg3' in psycopg_status:
            # psycopg3 utilise 'dbname' au lieu de 'database'
            conn = psycopg_module.connect(
                dbname=url.path[1:],
                user=url.username,
                password=url.password,
                host=url.hostname,
                port=url.port
            )
        else:
            # psycopg2 utilise 'database'
            conn = psycopg_module.connect(
                database=url.path[1:],
                user=url.username,
                password=url.password,
                host=url.hostname,
                port=url.port
            )
        
        # Test d'une requête simple
        cur = conn.cursor()
        cur.execute("SELECT version();")
        db_version = cur.fetchone()[0]
        
        cur.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';")
        table_count = cur.fetchone()[0]
        
        conn.close()
        
        return {
            "status": "✅ Succès complet !",
            "psycopg": psycopg_status,
            "database_url": "✅ Présente",
            "connection": "✅ Réussie",
            "database_version": db_version[:50] + "...",
            "tables_count": f"{table_count} tables publiques",
            "next_step": "Base prête pour la migration des données !"
        }
        
    except Exception as e:
        return {
            "status": "❌ Échec connexion",
            "psycopg": psycopg_status,
            "database_url": "✅ Présente", 
            "connection_error": str(e),
            "solution": "Vérifiez les paramètres de la base PostgreSQL"
        }

@app.get("/migrate-data")
def migrate_data():
    """Migration des données db.json vers PostgreSQL"""
    try:
        from database_config import get_database_connection
        import json
        
        # Vérifier si les tables existent déjà
        conn = get_database_connection()
        cur = conn.cursor()
        
        # Vérifier si les données sont déjà migrées
        cur.execute("SELECT COUNT(*) FROM preparateurs")
        data_count = cur.fetchone()[0]
        
        if data_count > 0:
            conn.close()
            return {"status": "✅ Données déjà migrées", "message": f"{data_count} préparateurs trouvés"}
        
        # Créer les tables PostgreSQL si elles n'existent pas
        cur.execute("SELECT EXISTS (SELECT FROM pg_tables WHERE tablename = 'preparateurs')")
        tables_exist = cur.fetchone()[0]
        
        if not tables_exist:
            cur.execute("""
            CREATE TABLE preparateurs (
                nom TEXT PRIMARY KEY,
                nni TEXT
            );

            CREATE TABLE disponibilites (
                id SERIAL PRIMARY KEY,
                preparateur_nom TEXT,
                semaine TEXT,
                minutes INTEGER,
                updatedAt TEXT,
                FOREIGN KEY (preparateur_nom) REFERENCES preparateurs(nom)
            );

            CREATE TABLE chantiers (
                id TEXT PRIMARY KEY,
                label TEXT,
                status TEXT,
                prepTime INTEGER,
                endDate TEXT,
                preparateur_nom TEXT,
                ChargeRestante INTEGER,
                FOREIGN KEY (preparateur_nom) REFERENCES preparateurs(nom)
            );

            CREATE TABLE planifications (
                id SERIAL PRIMARY KEY,
                chantier_id TEXT,
                semaine TEXT,
                minutes INTEGER,
                FOREIGN KEY (chantier_id) REFERENCES chantiers(id)
            );
            """)
            conn.commit()
        
        # Charger et migrer les données db.json
        try:
            # Essayer plusieurs chemins possibles pour db.json
            json_paths = ['db.json', 'API/db.json', './db.json']
            data = None
            
            for path in json_paths:
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        break
                except FileNotFoundError:
                    continue
            
            if data is None:
                raise FileNotFoundError("db.json non trouvé")
                
        except FileNotFoundError:
            # Si db.json n'existe pas, créer des données de test
            data = {
                "preparateurs": {
                    "Eric CHAPUIS": "F51742",
                    "Sylvain MATHAIS": "H13773"
                },
                "chantiers": {},
                "data": {}
            }
        
        # Insérer les préparateurs
        for nom, nni in data.get('preparateurs', {}).items():
            cur.execute("INSERT INTO preparateurs (nom, nni) VALUES (%s, %s) ON CONFLICT (nom) DO NOTHING", (nom, nni))
        
        # Insérer les chantiers
        for chantier_id, chantier in data.get('chantiers', {}).items():
            cur.execute("""
                INSERT INTO chantiers (id, label, status, prepTime, endDate, preparateur_nom, ChargeRestante) 
                VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING
            """, (
                chantier['id'],
                chantier['label'],
                chantier['status'],
                chantier['prepTime'],
                chantier['endDate'],
                chantier['preparateur'],
                chantier['ChargeRestante']
            ))
            
            # Insérer les planifications du chantier
            for semaine, minutes in chantier.get('planification', {}).items():
                cur.execute("""
                    INSERT INTO planifications (chantier_id, semaine, minutes) 
                    VALUES (%s, %s, %s)
                """, (chantier['id'], semaine, minutes))
        
        # Insérer les disponibilités (data)
        for preparateur_nom, disponibilites in data.get('data', {}).items():
            for semaine, info in disponibilites.items():
                cur.execute("""
                    INSERT INTO disponibilites (preparateur_nom, semaine, minutes, updatedAt) 
                    VALUES (%s, %s, %s, %s)
                """, (preparateur_nom, semaine, info['minutes'], info['updatedAt']))
        
        conn.commit()
        conn.close()
        
        return {
            "status": "✅ Migration complète !",
            "message": "Tables créées et données migrées",
            "preparateurs": len(data.get('preparateurs', {})),
            "chantiers": len(data.get('chantiers', {})),
            "next_step": "API prête à fonctionner !"
        }
        
    except Exception as e:
        return {"status": "❌ Erreur", "error": str(e)}

@app.get("/chantiers")
def get_chantiers():
    """Récupérer tous les chantiers depuis PostgreSQL"""
    try:
        from database_config import get_database_connection
        
        conn = get_database_connection()
        cur = conn.cursor()
        
        cur.execute("""
            SELECT c.id, c.label, c.status, c.prepTime, c.endDate, c.preparateur_nom, c.ChargeRestante,
                   p.chantier_id, p.semaine, p.minutes
            FROM chantiers c
            LEFT JOIN planifications p ON c.id = p.chantier_id
            ORDER BY c.id, p.semaine
        """)
        
        rows = cur.fetchall()
        conn.close()
        
        # Regrouper les résultats par chantier
        chantiers = {}
        for row in rows:
            chantier_id = row[0]
            if chantier_id not in chantiers:
                chantiers[chantier_id] = {
                    "id": row[0],
                    "label": row[1],
                    "status": row[2],
                    "prepTime": row[3],
                    "endDate": row[4],
                    "preparateur": row[5],
                    "ChargeRestante": row[6],
                    "planification": {}
                }
            
            # Ajouter la planification si elle existe
            if row[8] and row[9]:  # semaine et minutes
                chantiers[chantier_id]["planification"][row[8]] = row[9]
        
        return chantiers
        
    except Exception as e:
        return {"error": f"Erreur base de données: {str(e)}"}

@app.get("/preparateurs")
def get_preparateurs():
    """Récupérer tous les préparateurs depuis PostgreSQL"""
    try:
        from database_config import get_database_connection
        
        conn = get_database_connection()
        cur = conn.cursor()
        
        cur.execute("SELECT nom, nni FROM preparateurs ORDER BY nom")
        rows = cur.fetchall()
        conn.close()
        
        # Convertir en dictionnaire nom -> nni
        preparateurs = {row[0]: row[1] for row in rows}
        
        return preparateurs
        
    except Exception as e:
        return {"error": f"Erreur base de données: {str(e)}"}

@app.get("/disponibilites")
def get_disponibilites():
    """Récupérer toutes les disponibilités depuis PostgreSQL"""
    try:
        from database_config import get_database_connection
        
        conn = get_database_connection()
        cur = conn.cursor()
        
        cur.execute("""
            SELECT preparateur_nom, semaine, minutes, updatedAt 
            FROM disponibilites 
            ORDER BY preparateur_nom, semaine
        """)
        
        rows = cur.fetchall()
        conn.close()
        
        # Regrouper par préparateur
        disponibilites = {}
        for row in rows:
            preparateur = row[0]
            if preparateur not in disponibilites:
                disponibilites[preparateur] = {}
            
            disponibilites[preparateur][row[1]] = {
                "minutes": row[2],
                "updatedAt": row[3]
            }
        
        return {"data": disponibilites}
        
    except Exception as e:
        return {"error": f"Erreur base de données: {str(e)}"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
