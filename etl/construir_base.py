"""Constrói data/buscasus.db a partir do CSV do CNES.

Uso: python -m etl.construir_base --csv <zip ou csv> --municipio 310620
"""
import argparse
import csv
import datetime as dt
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

from app import tesauro as T

RAIZ = Path(__file__).resolve().parent.parent
COLUNAS = [
    "CO_CNES", "NO_FANTASIA", "NO_RAZAO_SOCIAL", "CO_UF", "CO_IBGE", "CO_CEP",
    "NO_LOGRADOURO", "NU_ENDERECO", "NO_BAIRRO", "NU_LATITUDE", "NU_LONGITUDE",
    "TP_UNIDADE", "DS_ESFERA_ADMINISTRATIVA", "DS_TURNO_ATENDIMENTO",
    "CO_AMBULATORIAL_SUS", "ST_CENTRO_OBSTETRICO", "ST_ATEND_HOSPITALAR",
    "CO_MOTIVO_DESAB", "NU_TELEFONE",
]  # sem CNPJ e sem e-mail, de propósito
SIGLAS = {"UPA", "UBS", "CAPS", "CERSAM", "SUS", "CEO", "PSF", "ESF", "SADT", "BH",
          "AD", "UFMG", "HC", "II", "III", "IV", "CTI", "UTI", "SAMU", "ONG"}
MINUSCULAS = {"de", "da", "do", "das", "dos", "e", "em", "a", "o"}

SCHEMA = """
CREATE TABLE estabelecimento (
  identifier TEXT PRIMARY KEY, title TEXT NOT NULL, alternative TEXT,
  type TEXT NOT NULL, tipo_cnes TEXT NOT NULL, categoria TEXT NOT NULL,
  logradouro TEXT, numero TEXT, bairro TEXT, cep TEXT,
  municipio TEXT, municipio_nome TEXT, uf TEXT,
  latitude REAL, longitude REAL,
  turno TEXT, esfera TEXT, telefone TEXT
);
CREATE TABLE assunto (identifier TEXT, termo TEXT NOT NULL);
CREATE TABLE info (chave TEXT PRIMARY KEY, valor TEXT);
CREATE VIRTUAL TABLE busca USING fts5(
  identifier UNINDEXED, nome, termos, endereco,
  tokenize = 'unicode61 remove_diacritics 2'
);
"""


def caixa_mista(s):
    if not s:
        return s
    out = []
    for i, p in enumerate(s.split()):
        if p.upper() in SIGLAS or any(c.isdigit() for c in p):
            out.append(p.upper())
        elif i > 0 and p.lower() in MINUSCULAS:
            out.append(p.lower())
        else:
            out.append(p.capitalize())
    return " ".join(out)


def vazio_none(v):
    v = (v or "").strip()
    return v or None


def num(v, lo, hi):
    try:
        x = float(str(v).strip().replace(",", "."))
    except ValueError:
        return None
    return x if lo <= x <= hi else None


def flag(v):
    return 1 if str(v).strip() in ("1", "1.0") else 0


def cep(v):
    d = re.sub(r"\D", "", v or "")
    return d.zfill(8) if 0 < len(d) <= 8 else None


def ler(caminho, municipio):
    """Lê em blocos; devolve (DataFrame do município, total de linhas lidas)."""
    for enc in ("utf-8", "latin-1"):
        try:
            partes, lidos = [], 0
            for ch in pd.read_csv(caminho, sep=";", dtype=str, keep_default_na=False,
                                  usecols=COLUNAS, encoding=enc, chunksize=100_000):
                lidos += len(ch)
                partes.append(ch[ch["CO_IBGE"].str.strip().str[:6] == municipio[:6]])
            return pd.concat(partes), lidos
        except UnicodeDecodeError:
            print(f"{enc} falhou, tentando latin-1", file=sys.stderr)
    raise SystemExit("Não foi possível ler o CSV")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--municipio", default="310620")
    ap.add_argument("--municipio-nome")
    ap.add_argument("--data-fonte")
    ap.add_argument("--saida", default=str(RAIZ / "data" / "buscasus.db"))
    a = ap.parse_args()

    nome_mun = a.municipio_nome or ("Belo Horizonte" if a.municipio == "310620" else a.municipio)
    data_fonte = a.data_fonte or dt.date.fromtimestamp(Path(a.csv).stat().st_mtime).strftime("%d/%m/%Y")
    with open(RAIZ / "vocabulario" / "ufs.csv", encoding="utf-8", newline="") as f:
        ufs = {r["co_uf"]: r["sigla"] for r in csv.DictReader(f)}

    tes = T.carregar()
    tipos = T.por_tipo_cnes(tes)

    df, lidos = ler(a.csv, a.municipio)
    n_mun = len(df)
    df = df.apply(lambda c: c.str.strip())
    df["CO_CNES"] = df["CO_CNES"].str.zfill(7)
    df["TP_UNIDADE"] = df["TP_UNIDADE"].str.zfill(2)
    df = df[(df["CO_MOTIVO_DESAB"] == "")
            & (df["CO_AMBULATORIAL_SUS"] == "SIM")
            & (df["TP_UNIDADE"].isin(tipos))].drop_duplicates("CO_CNES")

    saida = Path(a.saida)
    saida.parent.mkdir(parents=True, exist_ok=True)
    saida.unlink(missing_ok=True)
    con = sqlite3.connect(saida)
    con.executescript(SCHEMA)

    sem_coord, por_tipo = 0, Counter()
    for r in df.to_dict("records"):
        tp = tipos[r["TP_UNIDADE"]]
        lat = num(r["NU_LATITUDE"], -35, 6)
        lon = num(r["NU_LONGITUDE"], -75, -30)
        if lat is None or lon is None:
            lat = lon = None
            sem_coord += 1
        turno = vazio_none(r["DS_TURNO_ATENDIMENTO"])
        title = caixa_mista(vazio_none(r["NO_FANTASIA"]) or vazio_none(r["NO_RAZAO_SOCIAL"]) or "Sem nome")
        alt = caixa_mista(vazio_none(r["NO_RAZAO_SOCIAL"]))
        logr, bairro = caixa_mista(vazio_none(r["NO_LOGRADOURO"])), caixa_mista(vazio_none(r["NO_BAIRRO"]))
        num_end, cep_ = vazio_none(r["NU_ENDERECO"]), cep(r["CO_CEP"])
        cnes = r["CO_CNES"]

        assuntos = [tp.termo, tp.tg]
        if turno and turno.upper().startswith("ATENDIMENTO CONTINUO DE 24 HORAS"):
            assuntos.append("Atendimento 24 horas")
        if flag(r["ST_CENTRO_OBSTETRICO"]):
            assuntos.append("Maternidade")
        if flag(r["ST_ATEND_HOSPITALAR"]):
            assuntos.append("Internação")

        termos_busca = []
        for t in assuntos:
            termos_busca.append(t)
            if t in tes:
                termos_busca.extend(tes[t].nao_preferidos)

        con.execute("INSERT INTO estabelecimento VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
            cnes, title, alt, tp.termo, tp.tipo_cnes, tp.tg, logr, num_end, bairro, cep_,
            a.municipio, nome_mun, ufs.get(r["CO_UF"]), lat, lon,
            caixa_mista(turno), caixa_mista(vazio_none(r["DS_ESFERA_ADMINISTRATIVA"])),
            vazio_none(r["NU_TELEFONE"])))
        con.executemany("INSERT INTO assunto VALUES (?,?)", [(cnes, t) for t in assuntos])
        con.execute("INSERT INTO busca (identifier, nome, termos, endereco) VALUES (?,?,?,?)", (
            cnes, " ".join(x for x in (title, alt) if x), " ; ".join(termos_busca),
            " ".join(str(x) for x in (logr, num_end, bairro, cep_) if x)))
        por_tipo[f"{tp.tipo_cnes} {tp.termo}"] += 1

    con.executemany("INSERT INTO info VALUES (?,?)", [
        ("fonte", "CNES – Estabelecimentos, Ministério da Saúde"),
        ("data_fonte", data_fonte), ("municipio_nome", nome_mun),
        ("gerado_em", dt.datetime.now().isoformat(timespec="seconds"))])
    con.execute("CREATE INDEX ix_assunto_id ON assunto(identifier)")
    con.execute("CREATE INDEX ix_assunto_termo ON assunto(termo)")
    con.commit()
    con.execute("VACUUM")
    con.close()

    print(f"Lidos: {lidos}\nDo município {a.municipio}: {n_mun}\nSelecionados: {len(df)}\nSem coordenadas: {sem_coord}")
    for k, v in sorted(por_tipo.items()):
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
