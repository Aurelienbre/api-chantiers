import os
import json
from database_config import get_database_connection

def create_tables():
    """Crée les tables PostgreSQL"""
    conn = get_database_connection()
    cur = conn.cursor()
    
    cur.execute("""
    DROP TABLE IF EXISTS planifications CASCADE;
    DROP TABLE IF EXISTS chantiers CASCADE;
    DROP TABLE IF EXISTS disponibilites CASCADE;
    DROP TABLE IF EXISTS preparateurs CASCADE;

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
    conn.close()
    print("Tables PostgreSQL créées avec succès")

def migrate_json_to_db():
    """Migration des données JSON vers la base (PostgreSQL ou SQLite)"""
    # Données par défaut si db.json n'existe pas
    default_data = {
        "preparateurs": {},
        "data": {},
        "chantiers": {}
    }
    
    if os.path.exists("db.json"):
        print("Migration JSON -> Base de données...")
        with open("db.json", encoding="utf-8") as f:
            db = json.load(f)
    else:
        print("db.json introuvable, utilisation des données par défaut.")
        db = default_data

    conn = get_database_connection()
    cur = conn.cursor()

    # Créer les tables
    create_tables()
    
    # Reconnecter après création des tables
    conn = get_database_connection()
    cur = conn.cursor()

    # Remplir preparateurs
    for nom, nni in db.get("preparateurs", {}).items():
        cur.execute("INSERT INTO preparateurs (nom, nni) VALUES (%s, %s)", (nom, nni))

    # Remplir disponibilites
    for nom, semaines in db.get("data", {}).items():
        for semaine, val in semaines.items():
            if isinstance(val, dict):
                cur.execute(
                    "INSERT INTO disponibilites (preparateur_nom, semaine, minutes, updatedAt) VALUES (%s, %s, %s, %s)",
                    (nom, semaine, val.get("minutes", 0), val.get("updatedAt"))
                )

    # Remplir chantiers et planifications
    for ch_id, ch in db.get("chantiers", {}).items():
        cur.execute(
            "INSERT INTO chantiers (id, label, status, prepTime, endDate, preparateur_nom, ChargeRestante) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (
                ch.get("id", ch_id),
                ch.get("label"),
                ch.get("status"),
                ch.get("prepTime"),
                ch.get("endDate"),
                ch.get("preparateur"),
                ch.get("ChargeRestante")
            )
        )
        
        # Planification
        for semaine, minutes in (ch.get("planification") or {}).items():
            cur.execute(
                "INSERT INTO planifications (chantier_id, semaine, minutes) VALUES (%s, %s, %s)",
                (ch.get("id", ch_id), semaine, minutes)
            )

    conn.commit()
    conn.close()
    print("Migration terminée avec succès")

def check_tables_exist():
    """Vérifie si les tables PostgreSQL existent déjà"""
    conn = get_database_connection()
    cur = conn.cursor()
    
    try:
        cur.execute("SELECT EXISTS (SELECT FROM pg_tables WHERE tablename = 'preparateurs')")
        result = cur.fetchone()
        conn.close()
        return bool(result and result[0])
    except:
        conn.close()
        return False

if __name__ == "__main__":
    if not check_tables_exist():
        migrate_json_to_db()
    else:
        print("Tables déjà existantes, migration ignorée")
