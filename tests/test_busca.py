import sqlite3
from pathlib import Path

import pytest

from app.busca import buscar, haversine_km, interpretar

DB = Path(__file__).resolve().parent.parent / "data" / "buscasus.db"


@pytest.fixture(scope="module")
def con():
    if not DB.exists():
        pytest.skip("base não gerada")
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    yield c
    c.close()


def test_postinho_barreiro():
    i = interpretar("postinho no Barreiro")
    assert '"centro de saude unidade basica"' in i.expressao
    assert '"posto de saude"' in i.expressao
    assert '{nome endereco}:"barreiro"' in i.expressao
    assert i.aviso is None


def test_upa_inclui_tr():
    e = interpretar("UPA").expressao
    assert '"pronto atendimento"' in e and '"pronto socorro geral"' in e


def test_cersam():
    assert '"centro de atencao psicossocial"' in interpretar("cersam").expressao


def test_posto_categoria_e_termo_longo():
    e = interpretar("posto").expressao
    assert '"posto de saude"' in e and '"centro de saude unidade basica"' in e
    e2 = interpretar("posto de saúde").expressao
    assert e2.count("termos:") == 1  # um termo só, não "posto" + "saude"


def test_hospital_not_maternidade(con):
    i = interpretar("hospital NOT maternidade")
    assert 'NOT termos:("maternidade")' in i.expressao
    res, _ = buscar(con, "hospital NOT maternidade")
    assert res
    ids = [r["identifier"] for r in res]
    mat = {r[0] for r in con.execute("SELECT identifier FROM assunto WHERE termo='Maternidade'")}
    assert not mat & set(ids)


def test_caps_ou_policlinica_barreiro(con):
    i = interpretar("(caps OR policlínica) AND barreiro")
    assert i.aviso is None
    res, _ = buscar(con, "(caps OR policlínica) AND barreiro")
    assert all(r["type"] in ("Centro de Atenção Psicossocial", "Policlínica", "Clínica/Centro de Especialidade") for r in res)


def test_acento_e_caixa(con):
    a, _ = buscar(con, "saude")
    b, _ = buscar(con, "SAÚDE")
    assert a and [r["identifier"] for r in a] == [r["identifier"] for r in b]


@pytest.mark.parametrize("q", ["hospital (", "AND", "NOT x", "(((", '"', "", ")", "a OR", "( ) AND", "x* NEAR y", "a:b"])
def test_nao_quebra(con, q):
    res, i = buscar(con, q)
    assert isinstance(res, list)


def test_invalida_vira_simples():
    i = interpretar("hospital (")
    assert i.aviso and i.expressao


def test_filtros_sem_q(con):
    res, _ = buscar(con, None, categoria=["Urgência e emergência"], caracteristica=["Atendimento 24 horas"])
    assert res and all(r["categoria"] == "Urgência e emergência" for r in res)


def test_distancia(con):
    res, _ = buscar(con, "saude", ordem="distancia", lat=-19.92, lon=-43.94)
    d = [r["distancia_km"] for r in res]
    assert d == sorted(d)
    assert haversine_km(0, 0, 0, 0) == 0
