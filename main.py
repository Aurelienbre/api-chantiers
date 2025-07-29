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
