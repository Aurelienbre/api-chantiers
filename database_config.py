# Configuration pour base de données persistante
import os
import sqlite3
from urllib.parse import urlparse

def get_database_connection():
    """Retourne une connexion à la base de données (PostgreSQL sur Render, SQLite en local)"""
    database_url = os.environ.get('DATABASE_URL')
    
    if database_url:
        # Production avec PostgreSQL sur Render
        try:
            import psycopg2
        except ImportError:
            print("psycopg2 non installé, utilisation de SQLite")
            return sqlite3.connect("db.sqlite3")
            
        url = urlparse(database_url)
        return psycopg2.connect(
            database=url.path[1:],
            user=url.username,
            password=url.password,
            host=url.hostname,
            port=url.port
        )
    else:
        # Développement local avec SQLite
        return sqlite3.connect("db.sqlite3")

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
