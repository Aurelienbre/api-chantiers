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

@app.get("/chantiers")
def get_chantiers():
    return {"message": "Endpoint chantiers - temporaire sans base de données"}

@app.get("/preparateurs")
def get_preparateurs():
    return {"message": "Endpoint preparateurs - temporaire sans base de données"}

@app.get("/disponibilites")
def get_disponibilites():
    return {"message": "Endpoint disponibilites - temporaire sans base de données"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
