"""Testes dos cálculos com os dados reais do backup (sem dados pessoais)."""

from pathlib import Path

import pandas as pd
import pytest

import core

RAIZ = Path(__file__).resolve().parents[1]
HOJE = pd.Timestamp("2026-11-11")
LISTING = "Apartamento Moderno c/Piscina, a 12 min da Praia"
TAXAS_2026 = {4: 44, 5: 134, 6: 158, 7: 84, 8: 240, 9: 126}


@pytest.fixture(scope="module")
def reservas():
    registos = pd.read_csv(RAIZ / "backups" / "reservations.csv").to_dict("records")
    return core.registos_para_dataframe(registos)


@pytest.fixture(scope="module")
def noites(reservas):
    return core.criar_noites(reservas[~reservas["Cancelada"]])


def ajustes():
    return {mes: {"valor": float(valor), "notes": ""} for mes, valor in TAXAS_2026.items()}


def test_noites_somam_o_valor_das_reservas(reservas, noites):
    ativas = reservas[~reservas["Cancelada"]]
    assert len(noites) == ativas["Noites"].sum()
    assert round(noites["Valor bruto"].sum() * 100) == ativas["Cêntimos"].sum()
    assert not noites.duplicated(subset=["Listing", "Data"]).any()


def test_resumo_2026_bate_com_o_dashboard_atual(reservas, noites):
    mensal, _ = core.resumo_mensal(reservas, noites, 2026, ajustes(), HOJE)
    anual = core.resumo_anual(mensal, 2026, HOJE)

    assert anual["noites"] == 298
    assert anual["taxa"] == pytest.approx(950.00, abs=0.005)
    assert anual["liquido"] == pytest.approx(30909.75, abs=0.005)
    assert anual["realizado"] == pytest.approx(30390.84, abs=0.011)
    assert anual["futuro"] == pytest.approx(518.91, abs=0.011)
    assert anual["media_noite"] == pytest.approx(103.72, abs=0.005)
    # 289 noites realizadas em 314 dias decorridos.
    assert anual["ocupacao"] == pytest.approx(100 * 289 / 314, abs=0.01)

    agosto = mensal.iloc[7]
    assert agosto["Earnings bruto (€)"] == pytest.approx(7160.30, abs=0.005)
    assert agosto["Total líquido (€)"] == pytest.approx(6920.30, abs=0.005)
    assert agosto["Ocupação (%)"] == 100


def test_cancelamento_retido_e_reembolso(reservas, noites):
    reembolsos = {9: {"valor": 240.0, "notes": "Matas"}}
    mensal, _ = core.resumo_mensal(reservas, noites, 2026, ajustes(), HOJE, reembolsos)
    setembro = mensal.iloc[8]

    assert setembro["Cancelamentos retidos (€)"] == pytest.approx(308.70)
    assert setembro["Reembolsos (€)"] == 240.0
    assert setembro["Total do mês (€)"] == pytest.approx(
        setembro["Total líquido (€)"] + 68.70
    )

    rec = core.reconciliacao(reservas, 2026, 950.0, 240.0)
    assert rec["total_csv"] == pytest.approx(32168.45, abs=0.005)
    assert rec["ativas"] == pytest.approx(31859.75, abs=0.005)
    assert rec["final"] == pytest.approx(32168.45 - 240 - 950, abs=0.005)


def test_2025_sem_taxa_e_capacidade_desde_a_primeira_noite(reservas, noites):
    mensal, _ = core.resumo_mensal(reservas, noites, 2025, {}, HOJE)
    assert mensal["Taxa utilizada (€)"].sum() == 0
    assert mensal.iloc[0]["Dias disponíveis"] == 0      # janeiro: ainda não existia
    assert mensal.iloc[6]["Dias disponíveis"] == 16     # julho: desde dia 16
    assert mensal.iloc[7]["Dias disponíveis"] == 31


def test_agregar_dois_alojamentos_duplica_os_totais(reservas, noites):
    mensal, _ = core.resumo_mensal(reservas, noites, 2026, ajustes(), HOJE)
    total = core.agregar_mensal([mensal, mensal])

    assert total["Total líquido (€)"].sum() == pytest.approx(2 * 30909.75, abs=0.01)
    assert total["Noites"].sum() == 2 * 298
    # Os rácios mantêm-se iguais aos de um só alojamento.
    assert total.iloc[7]["Ocupação (%)"] == 100
    assert total.iloc[7]["Média líquida/noite (€)"] == pytest.approx(
        mensal.iloc[7]["Média líquida/noite (€)"]
    )


def test_plano_de_precos_mais_dez_por_cento(reservas, noites):
    base, _ = core.resumo_mensal(reservas, noites, 2026, ajustes(), HOJE)
    anterior, _ = core.resumo_mensal(reservas, noites, 2025, {}, HOJE)
    reservado, _ = core.resumo_mensal(reservas, noites, 2027, {}, HOJE)

    plano = core.plano_precos(
        base, anterior, reservado, 2027, HOJE,
        crescimento=0.10, comissao=0.03, desconto=0.10,
    )
    agosto = plano.iloc[7]

    assert agosto["Referência"] == "2026"
    assert agosto["Objetivo (€)"] == pytest.approx(6920.30 * 1.10, abs=0.01)
    # Ocupação já a 100 %: os 10 % têm de vir todos do preço.
    assert agosto["Variação do preço (%)"] == pytest.approx(10.0, abs=0.01)
    liquido = 6920.30 * 1.10 / 31
    assert agosto["Líquido/noite necessário (€)"] == pytest.approx(liquido, abs=0.01)
    assert agosto["Preço mínimo (€)"] == pytest.approx(liquido / 0.97, abs=0.01)
    assert agosto["Preço de tabela (€)"] == pytest.approx(liquido / 0.97 / 0.90, abs=0.01)

    # Dezembro de 2026 ainda não tem reservas: usa dezembro de 2025.
    dezembro = plano.iloc[11]
    assert dezembro["Referência"] == "2025"
    assert dezembro["Rendimento referência (€)"] == pytest.approx(604.21, abs=0.01)

    # Mais ocupação esperada => preço necessário mais baixo.
    plano_b = core.plano_precos(
        base, anterior, reservado, 2027, HOJE, ocupacoes={1: 90.0},
    )
    assert (
        plano_b.iloc[0]["Líquido/noite necessário (€)"]
        < plano.iloc[0]["Líquido/noite necessário (€)"]
    )

    cenarios = core.cenarios_desconto(plano)
    assert cenarios.iloc[7]["−10 %"] == pytest.approx(agosto["Preço mínimo (€)"], abs=0.01)


def test_minimo_media_maximo_por_noite(reservas, noites):
    mensal, _ = core.resumo_mensal(reservas, noites, 2026, ajustes(), HOJE)
    com_noites = mensal[mensal["Noites"] > 0]
    assert (com_noites["Mínimo/noite (€)"] <= com_noites["Média líquida/noite (€)"] + 0.01).all()
    assert (com_noites["Média líquida/noite (€)"] <= com_noites["Máximo/noite (€)"] + 0.01).all()
    # Potencial = melhor noite × dias do mês; nunca abaixo do que rendeu.
    agosto = mensal.iloc[7]
    assert agosto["Potencial ao máximo (€)"] == pytest.approx(agosto["Máximo/noite (€)"] * 31)
    assert (com_noites["Por captar (€)"] >= -0.01).all()
    assert pd.isna(mensal.iloc[11]["Mínimo/noite (€)"])  # dezembro sem noites

    total = core.agregar_mensal([mensal, mensal])
    assert total.iloc[7]["Máximo/noite (€)"] == pytest.approx(agosto["Máximo/noite (€)"])


def test_comissao_por_omissao_e_15_5(reservas, noites):
    base, _ = core.resumo_mensal(reservas, noites, 2026, ajustes(), HOJE)
    anterior, _ = core.resumo_mensal(reservas, noites, 2025, {}, HOJE)
    plano = core.plano_precos(base, anterior, None, 2027, HOJE, desconto=0.0)
    agosto = plano.iloc[7]
    assert agosto["Preço mínimo (€)"] == pytest.approx(
        agosto["Líquido/noite necessário (€)"] / 0.845, abs=0.01
    )
    assert agosto["Preço de tabela (€)"] == pytest.approx(agosto["Preço mínimo (€)"])


def test_euros_sinal():
    assert core.euros_sinal(1234.4) == "+1.234 €"
    assert core.euros_sinal(-746) == "−746 €"
    assert core.euros_sinal(None) == "—"


CABECALHO = (
    '"Confirmation code","Status","Guest name","Contact","# of adults",'
    '"# of children","# of infants","Start date","End date","# of nights",'
    '"Booked","Listing","Earnings"\n'
)


def _csv(tmp_path, nome, linhas):
    ficheiro = tmp_path / nome
    ficheiro.write_text(CABECALHO + "\n".join(linhas) + "\n", encoding="utf-8")
    return str(ficheiro)


def test_importa_datas_americanas_e_europeias(tmp_path):
    americano = _csv(tmp_path, "us.csv", [
        '"HMAAA","Canceled by guest","X","","2","0","0","4/3/2027","4/10/2027","7","2026-10-29","Casa","€1,596.88"',
    ])
    europeu = _csv(tmp_path, "pt.csv", [
        '"HMAAA","Cancelled by guest","X","","2","0","0","03/04/2027","10/04/2027","7","2026-10-29","Casa","€1,596.88"',
        '"HMBBB","Past guest","Y","","0","0","0","03/03/2026","05/03/2026","2","","Casa",""',
    ])

    lote = core.preparar_lote_csv([americano, europeu])

    # A mesma reserva vinda das duas contas não é um conflito.
    assert len(lote) == 1
    reserva = lote.iloc[0]
    assert reserva["Entrada"] == pd.Timestamp("2027-04-03")
    assert reserva["Saída"] == pd.Timestamp("2027-04-10")
    assert reserva["Cêntimos"] == 159688
    assert reserva["Cancelada"]
    # A reserva antiga sem valor fica de fora e é contada.
    assert lote.attrs["ignoradas"] == 1
    assert "Guest name" not in lote.columns


def test_conflito_real_continua_a_ser_recusado(tmp_path):
    a = _csv(tmp_path, "a.csv", [
        '"HMAAA","Confirmed","X","","2","0","0","4/3/2027","4/10/2027","7","","Casa","€500.00"',
    ])
    b = _csv(tmp_path, "b.csv", [
        '"HMAAA","Confirmed","X","","2","0","0","4/3/2027","4/10/2027","7","","Casa","€450.00"',
    ])
    with pytest.raises(ValueError, match="versões diferentes"):
        core.preparar_lote_csv([a, b])


def test_datas_impossiveis_sao_recusadas(tmp_path):
    mau = _csv(tmp_path, "mau.csv", [
        '"HMAAA","Confirmed","X","","2","0","0","4/3/2027","4/10/2027","3","","Casa","€500.00"',
    ])
    with pytest.raises(ValueError, match="datas ou noites inválidas"):
        core.preparar_csv(mau)


def test_ficheiro_so_com_reservas_sem_valor(tmp_path):
    vazio = _csv(tmp_path, "antigas.csv", [
        '"HMAAA","Past guest","X","","0","0","0","03/01/2026","05/01/2026","2","","Casa",""',
        '"HMBBB","Past guest","Y","","0","0","0","06/01/2026","09/01/2026","3","","Casa",""',
    ])
    bom = _csv(tmp_path, "bom.csv", [
        '"HMCCC","Confirmed","Z","","2","0","0","4/3/2027","4/10/2027","7","","Casa","€500.00"',
    ])

    so_vazio = core.preparar_lote_csv([vazio])
    assert len(so_vazio) == 0 and so_vazio.attrs["ignoradas"] == 2
    assert core.dataframe_para_registos(so_vazio, "x") == []

    lote = core.preparar_lote_csv([vazio, bom])
    assert len(lote) == 1 and lote.attrs["ignoradas"] == 2
    assert lote.iloc[0]["Valor bruto"] == 500.0


ICAL = (
    "BEGIN:VCALENDAR\r\nVERSION:2.0\r\n"
    "BEGIN:VEVENT\r\nDTEND;VALUE=DATE:20261116\r\nDTSTART;VALUE=DATE:20261110\r\n"
    "UID:1@airbnb.com\r\n"
    "DESCRIPTION:Reservation URL: https://www.airbnb.com/hosting/reservations/de\r\n"
    " tails/HMA3A3TEJW\\nPhone Number (Last 4 Digits): 0000\r\n"
    "SUMMARY:Reserved\r\nEND:VEVENT\r\n"
    "BEGIN:VEVENT\r\nDTEND;VALUE=DATE:20261125\r\nDTSTART;VALUE=DATE:20261121\r\n"
    "UID:2@airbnb.com\r\nSUMMARY:Airbnb (Not available)\r\nEND:VEVENT\r\n"
    "BEGIN:VEVENT\r\nDTEND;VALUE=DATE:20261205\r\nDTSTART;VALUE=DATE:20261201\r\n"
    "UID:3@airbnb.com\r\n"
    "DESCRIPTION:Reservation URL: https://www.airbnb.com/hosting/reservations/details/HMNOVA0001\r\n"
    "SUMMARY:Reserved\r\nEND:VEVENT\r\n"
    "END:VCALENDAR\r\n"
)


def test_ler_ical():
    eventos = core.ler_ical(ICAL)
    assert [e["tipo"] for e in eventos] == ["reserva", "bloqueio", "reserva"]
    assert eventos[0]["codigo"] == "HMA3A3TEJW"      # linha partida em duas
    assert eventos[0]["inicio"] == pd.Timestamp("2026-11-10")
    assert eventos[0]["fim"] == pd.Timestamp("2026-11-16")
    assert eventos[1]["codigo"] is None
    assert core.ler_ical("") == [] and core.ler_ical("lixo") == []


def test_calendario_junta_reservas_e_ical(reservas):
    eventos = core.eventos_calendario(reservas, core.ler_ical(ICAL), HOJE)
    por_codigo = {e["codigo"]: e for e in eventos if e["codigo"]}

    # Reserva guardada e presente no iCal: aparece uma vez, com valor.
    olivier = por_codigo["HMA3A3TEJW"]
    assert olivier["origem"] == "csv" and olivier["valor"] == pytest.approx(327.63)
    assert not olivier["em_duvida"]
    # Reserva guardada, futura, que o iCal já não tem: fica em dúvida.
    assert por_codigo["HM2SBCPMPD"]["em_duvida"]
    # Reserva só no iCal (ainda sem CSV) e bloqueio entram sem valor.
    assert por_codigo["HMNOVA0001"]["origem"] == "ical"
    assert sum(e["tipo"] == "bloqueio" for e in eventos) == 1
    # Canceladas não entram; passadas nunca ficam em dúvida.
    assert "HMTZARSW2K" not in por_codigo
    assert not any(e["em_duvida"] for e in eventos if e["fim"] <= HOJE)

    # Sem iCal não há dúvidas nem eventos extra.
    so_csv = core.eventos_calendario(reservas, None, HOJE)
    assert not any(e["em_duvida"] for e in so_csv)
    assert all(e["origem"] == "csv" for e in so_csv)


def test_periodos_livres_e_movimentos(reservas):
    eventos = core.eventos_calendario(reservas, None, HOJE)
    livres = core.periodos_livres(eventos, HOJE, 30)
    # Olivier sai a 16, Marc entra a 17: só a noite de 16 fica livre entre os dois.
    assert (pd.Timestamp("2026-11-16"), pd.Timestamp("2026-11-16"), 1) in livres
    assert livres[-1][0] == pd.Timestamp("2026-11-21")   # depois do Marc, tudo livre

    linhas = core.movimentos({"T1+1": eventos}, HOJE, 14)
    resumo = [(l["data"].day, l["tipo"]) for l in linhas]
    assert resumo == [(16, "Saída"), (17, "Entrada"), (21, "Saída")]

    # Saída e entrada no mesmo dia contam como troca.
    extra = eventos + [{
        "inicio": pd.Timestamp("2026-11-21"), "fim": pd.Timestamp("2026-11-23"),
        "tipo": "reserva", "codigo": "X", "noites": 2, "hospedes": 2,
        "valor": 100.0, "origem": "csv", "em_duvida": False,
    }]
    linhas = core.movimentos({"T1+1": extra}, HOJE, 14)
    assert (21, "Troca") in [(l["data"].day, l["tipo"]) for l in linhas]


def test_resultado_financeiro_reproduz_a_folha_de_calculo():
    # Cenário 5 da folha: 30.000 € de receita, 19.855 € de despesas
    # (inclui 3.420 € de amortização de capital) e IRS de 35 % × 28 %.
    # A comissão da plataforma (900 €) fica aqui como custo porque a folha
    # parte da receita antes da comissão.
    custos = [
        {"tipo": "Juros do crédito", "anual": 8424 - 3420},
        {"tipo": "Amortização de capital", "anual": 3420},
        {"tipo": "Operacional", "anual": 60 + 240 + 216 + 67 + 792 + 360 + 900 + 4800 + 600 + 300 + 480 + 420 + 720},
        {"tipo": "Impostos e taxas", "anual": 276 + 1200},
    ]
    r = core.resultado_financeiro(
        30000, custos, capital_investido=65000, noites=298, media_noite=100.0,
    )
    assert r["despesas"] == pytest.approx(19855)
    assert r["sobra"] == pytest.approx(10145)
    assert r["irs"] == pytest.approx(2940)
    assert r["resultado"] == pytest.approx(7205)
    assert r["com_amortizacao"] == pytest.approx(10625)
    assert r["roi"] == pytest.approx(11.08, abs=0.01)
    assert r["roi_com_amortizacao"] == pytest.approx(16.35, abs=0.01)
    # No ponto de equilíbrio o resultado é zero.
    equilibrio = core.resultado_financeiro(r["receita_equilibrio"], custos)
    assert equilibrio["resultado"] == pytest.approx(0, abs=0.01)

    real = core.resultado_financeiro(30000, custos, irs_real=1500)
    assert real["irs"] == 1500 and real["usa_irs_real"]
    assert core.valor_anual(400, None) == 4800 and core.valor_anual(400, 5000) == 5000
    assert core.valor_anual(None, None) == 0
