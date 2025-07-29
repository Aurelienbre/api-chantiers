# Configuration pour PostgreSQL sur Render
import os
from urllib.parse import urlparse

def get_database_connection():
    """Retourne une connexion PostgreSQL"""
    database_url = os.environ.get('DATABASE_URL')
    
    if not database_url:
        raise Exception("DATABASE_URL non définie. Cette application nécessite PostgreSQL.")
        
    try:
        import psycopg2
    except ImportError:
        raise Exception("psycopg2 non installé. Installez-le avec: pip install psycopg2-binary")
        
    url = urlparse(database_url)
    return psycopg2.connect(
        database=url.path[1:],
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
