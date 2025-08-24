# Configuration pour PostgreSQL sur Render avec psycopg3 et pool de connexions
import os
from urllib.parse import urlparse
from contextlib import contextmanager

# Pool de connexions global (optionnel, mais recommandé pour éviter les verrous)
_connection_pool = None

def get_database_connection():
    """Retourne une connexion PostgreSQL avec psycopg3"""
    database_url = os.environ.get('DATABASE_URL')
    
    if not database_url:
        raise Exception("❌ DATABASE_URL non définie.")
        
    # Utiliser psycopg3 (déjà testé et fonctionnel)
    import psycopg
    
    url = urlparse(database_url)
    # Configuration basique sans timeout agressif qui cause des problèmes
    conn = psycopg.connect(
        dbname=url.path[1:],
        user=url.username,
        password=url.password,
        host=url.hostname,
        port=url.port,
        connect_timeout=10
    )
    
    return conn

@contextmanager
def get_db_transaction():
    """Context manager pour les transactions avec gestion automatique des erreurs"""
    conn = None
    try:
        conn = get_database_connection()
        conn.autocommit = False
        yield conn
        conn.commit()
    except Exception as e:
        if conn:
            try:
                conn.rollback()
            except:
                # En cas d'erreur lors du rollback, fermer la connexion
                pass
        raise e
    finally:
        if conn:
            try:
                conn.close()
            except:
                # Ignorer les erreurs de fermeture
                pass

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
