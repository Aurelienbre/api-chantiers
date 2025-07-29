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
    return {"message": "API fonctionne!", "database_url": bool(os.environ.get('DATABASE_URL'))}

@app.get("/chantiers")
def get_chantiers():
    return {"message": "Endpoint chantiers - en cours de migration vers PostgreSQL"}

@app.get("/preparateurs")
def get_preparateurs():
    return {"message": "Endpoint preparateurs - en cours de migration vers PostgreSQL"}

@app.get("/disponibilites")
def get_disponibilites():
    return {"message": "Endpoint disponibilites - en cours de migration vers PostgreSQL"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
