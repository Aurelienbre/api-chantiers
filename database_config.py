# Configuration pour PostgreSQL sur Render
import os
from urllib.parse import urlparse

def get_database_connection():
    """Retourne une connexion PostgreSQL"""
    database_url = os.environ.get('DATABASE_URL')
    
    if not database_url:
        raise Exception("❌ DATABASE_URL non définie. Vérifiez la variable d'environnement sur Render.")
        
    print(f"✅ DATABASE_URL détectée: {database_url[:20]}...")
    
    try:
        import psycopg2
        print("✅ psycopg2 importé avec succès")
    except ImportError as e:
        print(f"❌ Erreur import psycopg2: {e}")
        raise Exception("psycopg2-binary non installé. Vérifiez requirements.txt et les logs de build Render.")
        
    try:
        url = urlparse(database_url)
        conn = psycopg2.connect(
            database=url.path[1:],
            user=url.username,
            password=url.password,
            host=url.hostname,
            port=url.port
        )
        print("✅ Connexion PostgreSQL réussie")
        return conn
    except Exception as e:
        print(f"❌ Erreur connexion PostgreSQL: {e}")
        raise

def execute_query(query, params=None, fetch=False):
    """Exécute une requête avec gestion des différences PostgreSQL/SQLite"""
    conn = get_database_connection()
    database_url = os.environ.get('DATABASE_URL')
    
    try:
        if database_url:  # PostgreSQL
            cur = conn.cursor()
            if params:
                cur.execute(query, params)
            else:
                cur.execute(query)
        else:  # SQLite
            cur = conn.cursor()
            if params:
                cur.execute(query, params)
            else:
                cur.execute(query)
        
        if fetch:
            result = cur.fetchall()
            conn.close()
            return result
        else:
            conn.commit()
            conn.close()
            return True
            
    except Exception as e:
        conn.close()
        raise e
