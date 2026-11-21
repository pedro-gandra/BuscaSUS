import sqlite3
from pathlib import Path

from fastapi import FastAPI, Query, Request
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import tesauro as T
from app.busca import buscar

BASE = Path(__file__).resolve().parent
DB = BASE.parent / "data" / "buscasus.db"

app = FastAPI(title="BuscaSUS")
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
templates = Jinja2Templates(directory=BASE / "templates")


def conectar():
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def info():
    con = conectar()
    try:
        return dict(con.execute("SELECT chave, valor FROM info").fetchall())
    finally:
        con.close()


INFO = info()
TES = T.carregar()
CATEGORIAS = [t.termo for t in TES.values() if t.grupo == "categoria"]
TIPOS = [t.termo for t in TES.values() if t.grupo == "tipo"]
CARACTERISTICAS = [t.termo for t in TES.values() if t.grupo == "caracteristica"]
EXEMPLOS = ["postinho", "UPA", "CERSAM", "hospital NOT maternidade"]


def render(request, nome, contexto, status=200):
    return templates.TemplateResponse(request, nome, {"info": INFO, **contexto}, status_code=status)


@app.get("/saude")
def saude():
    return PlainTextResponse("ok")


@app.get("/")
def inicio(request: Request):
    return render(request, "inicio.html", {"exemplos": EXEMPLOS, "categorias": CATEGORIAS, "q": ""})


@app.get("/busca")
def busca(request: Request, q: str = "",
          categoria: list[str] = Query([]), tipo: list[str] = Query([]),
          caracteristica: list[str] = Query([]), esfera: list[str] = Query([]),
          ordem: str = "relevancia", lat: float | None = None, lon: float | None = None):
    con = conectar()
    try:
        resultados, interp = buscar(con, q, categoria, tipo, caracteristica, esfera, ordem, lat, lon)
        esferas = [r[0] for r in con.execute(
            "SELECT DISTINCT esfera FROM estabelecimento WHERE esfera IS NOT NULL ORDER BY 1")]
    finally:
        con.close()
    pontos = [{"id": r["identifier"], "nome": r["title"], "lat": r["latitude"], "lon": r["longitude"]}
              for r in resultados if r["latitude"] is not None]
    filtros_ativos = bool(categoria or tipo or caracteristica or esfera)
    return render(request, "resultados.html", {
        "q": q, "interp": interp, "resultados": resultados, "pontos": pontos,
        "categorias": CATEGORIAS, "tipos": TIPOS, "caracteristicas": CARACTERISTICAS, "esferas": esferas,
        "sel": {"categoria": categoria, "tipo": tipo, "caracteristica": caracteristica, "esfera": esfera},
        "filtros_ativos": filtros_ativos, "ordem": ordem, "lat": lat, "lon": lon,
        "usuario": {"lat": lat, "lon": lon} if lat is not None and lon is not None else None,
    })


@app.get("/estabelecimento/{cnes}")
def estabelecimento(request: Request, cnes: str):
    con = conectar()
    try:
        est = con.execute("SELECT * FROM estabelecimento WHERE identifier = ?", (cnes,)).fetchone()
        termos = [r[0] for r in con.execute("SELECT termo FROM assunto WHERE identifier = ?", (cnes,))] if est else []
    finally:
        con.close()
    if est is None:
        return render(request, "nao_encontrado.html", {"q": ""}, status=404)
    est = dict(est)
    ponto = ({"id": est["identifier"], "nome": est["title"], "lat": est["latitude"], "lon": est["longitude"]}
             if est["latitude"] is not None else None)
    return render(request, "estabelecimento.html", {
        "e": est, "termos": termos, "ponto": ponto, "q": "",
        "tipos": set(TIPOS), "categorias": set(CATEGORIAS), "caracteristicas": set(CARACTERISTICAS)})
