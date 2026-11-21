"""Leitura do tesauro (vocabulario/tesauro.csv) e consultas sobre ele."""
import csv
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from app.texto import tokens

CAMINHO = Path(__file__).resolve().parent.parent / "vocabulario" / "tesauro.csv"


@dataclass
class Termo:
    termo: str
    grupo: str  # categoria | tipo | faceta | caracteristica
    tipo_cnes: str | None
    nao_preferidos: list[str] = field(default_factory=list)
    tg: str | None = None
    tr: list[str] = field(default_factory=list)


def _lista(s: str) -> list[str]:
    return [x.strip() for x in (s or "").split("|") if x.strip()]


@lru_cache(maxsize=None)
def carregar(caminho: Path = CAMINHO) -> dict[str, Termo]:
    termos = {}
    with open(caminho, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            tipo = (r["tipo_cnes"] or "").strip()
            termos[r["termo"].strip()] = Termo(
                termo=r["termo"].strip(),
                grupo=r["grupo"].strip(),
                tipo_cnes=tipo.zfill(2) if tipo else None,
                nao_preferidos=_lista(r["nao_preferidos"]),
                tg=(r["tg"] or "").strip() or None,
                tr=_lista(r["tr"]),
            )
    return termos


def por_tipo_cnes(t: dict[str, Termo]) -> dict[str, Termo]:
    return {x.tipo_cnes: x for x in t.values() if x.grupo == "tipo" and x.tipo_cnes}


def tipos_da_categoria(t: dict[str, Termo], categoria: str) -> list[Termo]:
    return [x for x in t.values() if x.grupo == "tipo" and x.tg == categoria]


def rotulos(t: dict[str, Termo]) -> list[tuple[tuple[str, ...], str]]:
    """(tokens do rótulo, termo preferido), maiores primeiro (correspondência mais longa)."""
    out = []
    for x in t.values():
        if x.grupo == "faceta":
            continue
        for rot in [x.termo, *x.nao_preferidos]:
            tk = tuple(tokens(rot))
            if tk:
                out.append((tk, x.termo))
    out.sort(key=lambda p: -len(p[0]))
    return out
