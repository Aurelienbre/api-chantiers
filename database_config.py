# Configuration pour PostgreSQL sur Render avec psycopg3
import os
from urllib.parse import urlparse

def get_database_connection():
    """Retourne une connexion PostgreSQL avec psycopg3"""
    database_url = os.environ.get('DATABASE_URL')
    
    if not database_url:
        raise Exception("❌ DATABASE_URL non définie.")
        
    # Utiliser psycopg3 (déjà testé et fonctionnel)
    import psycopg
    
    url = urlparse(database_url)
    return psycopg.connect(
        dbname=url.path[1:],
        user=url.username,
        password=url.password,
        host=url.hostname,
        port=url.port
    )

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
