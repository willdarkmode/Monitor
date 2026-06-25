import json
import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from sankhya_reporter import SankhyaReporter, gerar_mock

load_dotenv()

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
CACHE_FILE = DATA_DIR / "dashboard_cache.json"
DATA_DIR.mkdir(exist_ok=True)

app = FastAPI(title="Sankhya Dashboard Comercial")
reporter = SankhyaReporter()

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


def carregar_cache():
    if CACHE_FILE.exists():
        with open(CACHE_FILE, "r", encoding="utf-8") as arquivo:
            return json.load(arquivo)
    return None


def salvar_cache(dados):
    with open(CACHE_FILE, "w", encoding="utf-8") as arquivo:
        json.dump(dados, arquivo, ensure_ascii=False, indent=2)


def coletar_dashboard(forcar=False):
    usar_mock = os.getenv("DASHBOARD_USAR_MOCK", "true").lower() == "true"

    if usar_mock:
        dados = gerar_mock()
        salvar_cache(dados)
        return dados

    if not forcar:
        cache = carregar_cache()
        if cache:
            try:
                atualizado = datetime.fromisoformat(cache.get("atualizado_em"))
                idade_segundos = (datetime.now() - atualizado).total_seconds()
                if idade_segundos < 60:
                    return cache
            except Exception:
                pass

    dados = reporter.gerar_dashboard()
    if dados:
        salvar_cache(dados)
        return dados

    cache = carregar_cache()
    if cache:
        cache["aviso"] = "Exibindo último cache disponível. Falha ao atualizar Sankhya."
        return cache

    dados = gerar_mock()
    dados["aviso"] = "Dados mockados. Configure o .env para usar Sankhya real."
    return dados


@app.get("/")
def home():
    return FileResponse(BASE_DIR / "static" / "tv.html")


@app.get("/tv")
def tv():
    return FileResponse(BASE_DIR / "static" / "tv.html")

@app.get("/mobile")
def mobile():
    return FileResponse(BASE_DIR / "static" / "mobile.html")

@app.get("/api/dashboard")
def api_dashboard():
    return JSONResponse(coletar_dashboard())


@app.get("/api/refresh")
def api_refresh():
    return JSONResponse(coletar_dashboard(forcar=True))
