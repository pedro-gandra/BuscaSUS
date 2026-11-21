"""Tratamento da consulta (tesauro + operadores) e execução no SQLite/FTS5."""
import math
import re
import sqlite3
from dataclasses import dataclass

from app import tesauro as T
from app.texto import frase, tokens

OPS = {"AND", "OR", "NOT"}
LEX = re.compile(r'"[^"]*"|\(|\)|[^\s()"]+')
AVISO_SIMPLES = "Não entendemos os operadores; fizemos uma busca simples."


@dataclass
class Interpretacao:
    expressao: str | None
    buscou: str
    mostrando: str
    aviso: str | None = None


def _preferidos(nome, tes):
    """Termos preferidos que um termo reconhecido representa (TR só para tipos)."""
    t = tes[nome]
    if t.grupo == "categoria":
        return [x.termo for x in T.tipos_da_categoria(tes, nome)] or [nome]
    if t.grupo == "tipo":
        return [nome] + [r for r in t.tr if r in tes and tes[r].grupo == "tipo"]
    return [nome]


def _operando_termo(nome, tes):
    prefs = _preferidos(nome, tes)
    fts = "termos:(" + " OR ".join(f'"{frase(p)}"' for p in prefs) + ")"
    return fts, " ou ".join(prefs)


def _operando_palavra(frase_tokens):
    f = " ".join(frase_tokens)
    return '{nome endereco}:"%s"' % f, f'"{f}"'


def _reconhecer(toks, rot, tes):
    """Lista de operandos (fts, legível) para uma sequência de tokens."""
    out, i = [], 0
    while i < len(toks):
        for tk, nome in rot:
            if tuple(toks[i:i + len(tk)]) == tk:
                out.append(_operando_termo(nome, tes))
                i += len(tk)
                break
        else:
            out.append(_operando_palavra([toks[i]]))
            i += 1
    return out


def _elementos(q, tes, rot):
    """Converte o texto em elementos: ('op', X) | ('(',) | (')',) | ('opd', fts, legivel)."""
    els, corrida = [], []

    def descarrega():
        for fts, leg in _reconhecer(tokens(" ".join(corrida)), rot, tes):
            els.append(("opd", fts, leg))
        corrida.clear()

    for m in LEX.findall(q):
        if m in OPS:
            descarrega(); els.append(("op", m))
        elif m in "()":
            descarrega(); els.append((m,))
        elif m.startswith('"'):
            descarrega()
            tk = tokens(m.strip('"'))
            if not tk:
                continue
            nome = next((n for t, n in rot if t == tuple(tk)), None)
            els.append(("opd", *(_operando_termo(nome, tes) if nome else _operando_palavra(tk))))
        else:
            corrida.append(m)
    descarrega()
    return els


def _com_and_implicito(els):
    out = []
    for e in els:
        if out:
            ant = out[-1]
            fecha = ant[0] in ("opd", ")")
            abre = e[0] in ("opd", "(")
            if fecha and abre:
                out.append(("op", "AND"))
        out.append(e)
    return out


def _valido(els):
    prof, ant = 0, None  # ant: tipo do elemento anterior
    for e in els:
        k = e[0]
        if k == "(":
            if ant in ("opd", ")"):
                return False
            prof += 1
        elif k == ")":
            prof -= 1
            if prof < 0 or ant in (None, "op", "("):
                return False
        elif k == "op":
            if ant not in ("opd", ")"):
                return False
        elif ant in ("opd", ")"):
            return False
        ant = k
    return prof == 0 and ant in ("opd", ")")


def _texto(els):
    partes = []
    for e in els:
        if e[0] == "opd":
            partes.append(e[1])
        elif e[0] == "op":
            partes.append(e[1])
        else:
            partes.append(e[0])
    return " ".join(partes).replace("( ", "(").replace(" )", ")")


def _legivel(els):
    nomes = {"AND": "e", "OR": "ou", "NOT": "não"}
    partes = [e[2] if e[0] == "opd" else nomes[e[1]] if e[0] == "op" else e[0] for e in els]
    return " ".join(partes).replace("( ", "(").replace(" )", ")")


def interpretar(q: str | None) -> Interpretacao:
    q = (q or "").strip()
    tes = T.carregar()
    rot = T.rotulos(tes)
    els = _elementos(q, tes, rot)
    if not any(e[0] == "opd" for e in els):
        return Interpretacao(None, q, "todos os estabelecimentos")
    com_and = _com_and_implicito(els)
    if _valido(com_and):
        return Interpretacao(_texto(com_and), q, _legivel(com_and))
    simples = []
    for e in els:
        if e[0] == "opd":
            simples += [("op", "AND"), e] if simples else [e]
    return Interpretacao(_texto(simples), q, _legivel(simples), AVISO_SIMPLES)


def haversine_km(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return 6371.0 * 2 * math.asin(math.sqrt(a))


def _filtros(categoria, tipo, caracteristica, esfera):
    sql, par = [], []
    for col, vals in (("e.categoria", categoria), ("e.type", tipo), ("e.esfera", esfera)):
        if vals:
            sql.append(f"{col} IN ({','.join('?' * len(vals))})")
            par += list(vals)
    if caracteristica:
        sql.append("EXISTS (SELECT 1 FROM assunto a WHERE a.identifier = e.identifier "
                   f"AND a.termo IN ({','.join('?' * len(caracteristica))}))")
        par += list(caracteristica)
    return sql, par


def buscar(con, q=None, categoria=(), tipo=(), caracteristica=(), esfera=(),
           ordem="relevancia", lat=None, lon=None):
    """Devolve (lista de dicts, Interpretacao). Nunca levanta erro por consulta malformada."""
    interp = interpretar(q)
    sql_f, par_f = _filtros(categoria, tipo, caracteristica, esfera)

    def executa(expressao):
        if expressao:
            sql = ("SELECT e.*, bm25(busca, 0.0, 10.0, 5.0, 1.0) AS r FROM busca "
                   "JOIN estabelecimento e ON e.identifier = busca.identifier "
                   "WHERE busca MATCH ?")
            par = [expressao]
        else:
            sql = "SELECT e.*, 0.0 AS r FROM estabelecimento e WHERE 1=1"
            par = []
        for f in sql_f:
            sql += " AND " + f
        return con.execute(sql, par + par_f).fetchall()

    try:
        linhas = executa(interp.expressao)
    except sqlite3.OperationalError:
        simples = " AND ".join(p for p in re.findall(r'\{nome endereco\}:"[^"]*"|termos:\([^)]*\)',
                                                    interp.expressao or ""))
        interp.aviso = AVISO_SIMPLES
        try:
            linhas = executa(simples or None)
        except sqlite3.OperationalError:
            linhas = []
    res = [dict(l) for l in linhas]
    if lat is not None and lon is not None:
        for r in res:
            r["distancia_km"] = (haversine_km(lat, lon, r["latitude"], r["longitude"])
                                 if r["latitude"] is not None else None)
    if ordem == "distancia" and lat is not None and lon is not None:
        res.sort(key=lambda r: (r["distancia_km"] is None, r["distancia_km"] or 0))
    elif ordem == "nome" or not interp.expressao:
        res.sort(key=lambda r: r["title"].lower())
    else:
        res.sort(key=lambda r: (r["r"], r["title"].lower()))
    return res, interp
