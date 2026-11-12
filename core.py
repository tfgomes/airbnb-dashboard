"""Cálculos do dashboard, sem dependência do Streamlit.

Tudo o que aqui está recebe e devolve dados simples (DataFrames, dicionários),
para poder ser testado com `pytest` sem abrir a aplicação.
"""

import calendar

import pandas as pd


MESES = [
    "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
]

MESES_CURTOS = [
    "jan.", "fev.", "mar.", "abr.", "mai.", "jun.",
    "jul.", "ago.", "set.", "out.", "nov.", "dez.",
]

VALOR_TAXA_POR_PESSOA_NOITE = 2.00
MAXIMO_NOITES_TAXADAS_POR_RESERVA = 7
INICIO_TAXA = pd.Timestamp("2026-04-01")

COLUNAS_CSV = [
    "Confirmation code", "Status", "Start date", "End date", "# of nights",
    "# of adults", "# of children", "# of infants", "Earnings", "Listing",
]

COLUNAS_NOITES = [
    "Listing", "Reserva", "Data", "Valor bruto", "Taxa automática",
    "Duração reserva", "Hóspedes",
]


# =========================================================
# FORMATAÇÃO
# =========================================================

def _vazio(valor):
    return valor is None or pd.isna(valor)


def euros(valor, casas=2):
    if _vazio(valor):
        return "—"
    texto = f"{float(valor):,.{casas}f}"
    return texto.replace(",", "X").replace(".", ",").replace("X", ".") + " €"


def euros_sinal(valor, casas=0):
    """Valor com sinal explícito, para diferenças: +1.234 € ou −746 €."""
    if _vazio(valor):
        return "—"
    if abs(float(valor)) < 0.005:
        return euros(0, casas)
    sinal = "+" if valor > 0 else "−"
    return sinal + euros(abs(float(valor)), casas)


def etiqueta_euros(valor):
    if _vazio(valor) or abs(float(valor)) < 0.5:
        return ""
    return f"{float(valor):,.0f}".replace(",", ".") + " €"


def percentagem(valor, casas=1):
    if _vazio(valor):
        return "—"
    return f"{float(valor):.{casas}f}".replace(".", ",") + " %"


def variacao(atual, anterior):
    """Variação percentual, ou None quando não há base de comparação."""
    if _vazio(atual) or _vazio(anterior) or abs(float(anterior)) < 0.005:
        return None
    return 100 * (float(atual) / float(anterior) - 1)


def texto_variacao(valor, casas=1):
    if _vazio(valor):
        return "—"
    sinal = "+" if valor >= 0 else "−"
    return f"{sinal}{abs(valor):.{casas}f}".replace(".", ",") + " %"


def converter_earnings_para_centimos(valor):
    texto = str(valor).strip().replace("€", "").replace(" ", "").replace(",", "")
    if not texto:
        raise ValueError("Foi encontrado um valor Earnings vazio.")
    try:
        return int(round(float(texto) * 100))
    except ValueError as erro:
        raise ValueError(f"Valor Earnings inválido: {valor}") from erro


# =========================================================
# IMPORTAÇÃO DE CSV
# =========================================================

def preparar_csv(ficheiro):
    nome = getattr(ficheiro, "name", str(ficheiro))

    dados = pd.read_csv(
        ficheiro, dtype=str, encoding="utf-8-sig", skipinitialspace=True,
    )
    dados.columns = dados.columns.str.strip()

    falta = [coluna for coluna in COLUNAS_CSV if coluna not in dados.columns]
    if falta:
        raise ValueError(f"Colunas em falta em {nome}: " + ", ".join(falta))

    # Excluir nomes, contactos e outros dados pessoais.
    dados = dados[COLUNAS_CSV].copy()

    for coluna in dados.columns:
        dados[coluna] = dados[coluna].fillna("").astype(str).str.strip()

    campos_vazios = (
        dados["Listing"].eq("")
        | dados["Confirmation code"].eq("")
        | dados["Status"].eq("")
    )
    if campos_vazios.any():
        raise ValueError(
            f"Existem registos sem Listing, código ou estado em {nome}."
        )

    # O Airbnb deixa de mostrar o valor nas reservas mais antigas de alguns
    # exports. Sem valor não há nada para analisar: ficam de fora e são contadas.
    sem_valor = dados["Earnings"].eq("")
    ignoradas = int(sem_valor.sum())
    dados = dados[~sem_valor].copy()

    dados["Noites"] = pd.to_numeric(dados["# of nights"], errors="coerce")
    dados["Entrada"], dados["Saída"] = _ler_datas(dados, nome)

    for origem, destino in [
        ("# of adults", "Adultos"),
        ("# of children", "Crianças"),
        ("# of infants", "Bebés"),
    ]:
        dados[destino] = (
            pd.to_numeric(dados[origem], errors="coerce").fillna(0).astype(int)
        )

    dados["Total hóspedes"] = (
        dados["Adultos"] + dados["Crianças"] + dados["Bebés"]
    )

    contagens_invalidas = (
        (dados[["Adultos", "Crianças", "Bebés"]] < 0).any(axis=1)
        | dados["Total hóspedes"].le(0)
    )
    if contagens_invalidas.any():
        raise ValueError(
            f"Existem quantidades de hóspedes inválidas em {nome}."
        )

    # astype explícito: num ficheiro em que nenhuma reserva tem valor a coluna
    # fica vazia e, sem isto, continuaria a ser texto.
    dados["Cêntimos"] = (
        dados["Earnings"].map(converter_earnings_para_centimos).astype("int64")
    )
    dados["Valor bruto"] = dados["Cêntimos"] / 100

    dados["Noites"] = dados["Noites"].astype(int)
    dados["Cancelada"] = dados["Status"].str.contains(
        r"cancel", case=False, na=False,
    )

    dados = dados.drop_duplicates()
    dados.attrs["ignoradas"] = ignoradas
    return dados


FORMATOS_DATA = ["%m/%d/%Y", "%d/%m/%Y", "%Y-%m-%d"]


def _datas_invalidas(dados, formato):
    entrada = pd.to_datetime(dados["Start date"], format=formato, errors="coerce")
    saida = pd.to_datetime(dados["End date"], format=formato, errors="coerce")
    noites = (saida - entrada).dt.days
    invalidas = (
        entrada.isna()
        | saida.isna()
        | dados["Noites"].isna()
        | noites.le(0)
        | dados["Noites"].ne(noites)
    )
    return entrada, saida, int(invalidas.sum())


def _ler_datas(dados, nome):
    """Descobre o formato das datas do ficheiro.

    O Airbnb exporta mês/dia/ano ou dia/mês/ano conforme o idioma da conta.
    O formato certo é o único em que todas as datas existem e a diferença
    entre saída e entrada bate com o número de noites.
    """
    resultados = [
        (formato, *_datas_invalidas(dados, formato)) for formato in FORMATOS_DATA
    ]
    validos = [r for r in resultados if r[3] == 0]

    if not validos:
        menos_mau = min(r[3] for r in resultados)
        raise ValueError(
            f"Existem {menos_mau} reservas com datas ou noites inválidas "
            f"em {nome}."
        )

    _, entrada, saida, _ = validos[0]
    for _, outra_entrada, outra_saida, _ in validos[1:]:
        if not (entrada.equals(outra_entrada) and saida.equals(outra_saida)):
            raise ValueError(
                f"Não foi possível distinguir dia e mês nas datas de {nome}."
            )
    return entrada, saida


def preparar_lote_csv(ficheiros):
    tabelas = [preparar_csv(ficheiro) for ficheiro in ficheiros]
    ignoradas = sum(tabela.attrs.get("ignoradas", 0) for tabela in tabelas)
    lote = pd.concat(tabelas, ignore_index=True)

    chave = ["Listing", "Confirmation code"]
    # Compara valores já interpretados: o mesmo registo pode vir de contas
    # com idiomas diferentes (datas e estados escritos de outra forma).
    comparar = [
        "Entrada", "Saída", "Noites", "Adultos", "Crianças", "Bebés",
        "Cêntimos", "Cancelada",
    ]

    repetidas = lote[lote.duplicated(subset=chave, keep=False)]

    if not repetidas.empty:
        conflitos = (
            repetidas.groupby(chave, dropna=False)[comparar]
            .nunique(dropna=False)
            .gt(1)
            .any(axis=1)
        )
        if conflitos.any():
            exemplos = [
                f"{listing} / {codigo}"
                for listing, codigo in conflitos[conflitos].index[:10]
            ]
            raise ValueError(
                "Foram encontradas versões diferentes da mesma reserva: "
                + ", ".join(exemplos)
            )

    lote = lote.drop_duplicates(subset=chave, keep="last").reset_index(drop=True)
    lote.attrs["ignoradas"] = ignoradas
    return lote


def dataframe_para_registos(dados, agora):
    registos = []
    for _, linha in dados.iterrows():
        registos.append({
            "listing": str(linha["Listing"]).strip(),
            "confirmation_code": str(linha["Confirmation code"]).strip(),
            "status": str(linha["Status"]).strip(),
            "start_date": linha["Entrada"].date().isoformat(),
            "end_date": linha["Saída"].date().isoformat(),
            "nights": int(linha["Noites"]),
            "adults": int(linha["Adultos"]),
            "children": int(linha["Crianças"]),
            "infants": int(linha["Bebés"]),
            "earnings_cents": int(linha["Cêntimos"]),
            "updated_at": agora,
        })
    return registos


def registos_para_dataframe(registos):
    """Converte as linhas da tabela `reservations` no formato usado nos cálculos."""
    if not registos:
        return pd.DataFrame()

    base = pd.DataFrame(registos)
    base["Listing"] = base["listing"].astype(str)
    base["Confirmation code"] = base["confirmation_code"].astype(str)
    base["Status"] = base["status"].astype(str)
    base["Entrada"] = pd.to_datetime(base["start_date"])
    base["Saída"] = pd.to_datetime(base["end_date"])
    base["Noites"] = pd.to_numeric(base["nights"]).astype(int)
    for origem, destino in [
        ("adults", "Adultos"), ("children", "Crianças"), ("infants", "Bebés"),
    ]:
        base[destino] = pd.to_numeric(base[origem]).fillna(0).astype(int)
    base["Total hóspedes"] = base["Adultos"] + base["Crianças"] + base["Bebés"]
    base["Cêntimos"] = pd.to_numeric(base["earnings_cents"]).astype(int)
    base["Valor bruto"] = base["Cêntimos"] / 100
    base["Cancelada"] = base["Status"].str.contains(
        r"cancel", case=False, na=False,
    )
    return base


# =========================================================
# NOITES E TAXA TURÍSTICA
# =========================================================

def data_tem_taxa(data):
    if data < INICIO_TAXA:
        return False
    return 4 <= data.month <= 10


def criar_noites(reservas):
    """Uma linha por noite ocupada. O dia de saída não conta.

    O valor da reserva é repartido de forma igual pelas noites, com os
    cêntimos de resto atribuídos às primeiras, para a soma bater sempre certo.
    """
    linhas = []

    for _, reserva in reservas.iterrows():
        datas = pd.date_range(
            reserva["Entrada"], reserva["Saída"], inclusive="left",
        )
        if len(datas) == 0:
            continue

        total_centimos = int(reserva["Cêntimos"])
        sinal = -1 if total_centimos < 0 else 1
        base_centimos, resto = divmod(abs(total_centimos), len(datas))
        hospedes = int(reserva["Total hóspedes"])
        noites_taxadas = 0

        for posicao, data in enumerate(datas):
            valor_bruto = (base_centimos + int(posicao < resto)) * sinal / 100

            if (
                data_tem_taxa(data)
                and noites_taxadas < MAXIMO_NOITES_TAXADAS_POR_RESERVA
            ):
                taxa_automatica = hospedes * VALOR_TAXA_POR_PESSOA_NOITE
                noites_taxadas += 1
            else:
                taxa_automatica = 0.0

            linhas.append({
                "Listing": reserva["Listing"],
                "Reserva": reserva["Confirmation code"],
                "Data": data,
                "Valor bruto": valor_bruto,
                "Taxa automática": taxa_automatica,
                "Duração reserva": len(datas),
                "Hóspedes": hospedes,
            })

    if not linhas:
        vazio = pd.DataFrame(columns=COLUNAS_NOITES)
        vazio["Data"] = pd.to_datetime(vazio["Data"])
        return vazio

    return pd.DataFrame(linhas)


def aplicar_taxa_mensal(noites, ano, ajustes):
    """Desconta a taxa turística de cada mês (manual se existir, senão automática)."""
    resultado = noites.copy()
    resultado["Taxa final"] = 0.0
    resultado["Origem taxa"] = "Não aplicável"

    if int(ano) < 2026:
        resultado["Valor líquido"] = resultado["Valor bruto"]
        return resultado

    for mes in range(1, 13):
        mascara = (
            (resultado["Data"].dt.year == int(ano))
            & (resultado["Data"].dt.month == mes)
        )
        quantidade_noites = int(mascara.sum())
        if quantidade_noites == 0:
            continue

        valor_automatico = float(resultado.loc[mascara, "Taxa automática"].sum())

        if mes in ajustes:
            taxa_final = float(ajustes[mes]["valor"])
            origem = "Manual"
        else:
            taxa_final = valor_automatico
            origem = "Automático" if valor_automatico > 0 else "Não aplicável"

        centimos_taxa = int(round(taxa_final * 100))
        base_centimos, resto = divmod(centimos_taxa, quantidade_noites)
        resultado.loc[mascara, "Taxa final"] = [
            (base_centimos + int(indice < resto)) / 100
            for indice in range(quantidade_noites)
        ]
        resultado.loc[mascara, "Origem taxa"] = origem

    resultado["Valor líquido"] = resultado["Valor bruto"] - resultado["Taxa final"]
    return resultado


# =========================================================
# RESUMO MENSAL DE UM ALOJAMENTO
# =========================================================

def dias_disponiveis(ano, mes, primeira_noite):
    """Dias do mês em que o alojamento já estava à venda."""
    dias_mes = calendar.monthrange(int(ano), mes)[1]
    if primeira_noite is None or pd.isna(primeira_noite):
        return dias_mes
    inicio = pd.Timestamp(int(ano), mes, 1)
    fim = pd.Timestamp(int(ano), mes, dias_mes)
    if primeira_noite > fim:
        return 0
    if primeira_noite <= inicio:
        return dias_mes
    return (fim - primeira_noite).days + 1


def resumo_mensal(
    reservas, noites, ano, ajustes, hoje, reembolsos=None,
):
    """Resumo dos 12 meses de um alojamento.

    reservas   todas as reservas do alojamento (inclui canceladas)
    noites     noites das reservas não canceladas (`criar_noites`)
    ajustes    {mês: {"valor": taxa turística manual, "notes": ...}}
    reembolsos {mês: {"valor": reembolso manual, "outros": outros
               rendimentos (ex.: AirCover), "notes": ...}}
    """
    reembolsos = reembolsos or {}
    ano = int(ano)

    ano_noites = noites[noites["Data"].dt.year == ano].copy()
    ano_noites = aplicar_taxa_mensal(ano_noites, ano, ajustes)

    primeira_noite = noites["Data"].min() if len(noites) else None

    if len(reservas):
        canceladas = reservas[
            reservas["Cancelada"] & (reservas["Entrada"].dt.year == ano)
        ]
    else:
        canceladas = reservas

    linhas = []

    for mes in range(1, 13):
        periodo = ano_noites[ano_noites["Data"].dt.month == mes]
        dias_mes = calendar.monthrange(ano, mes)[1]
        # Um alojamento sem uma única noite no ano não conta como estando
        # à venda nesse ano (por exemplo, um anúncio antigo já desativado).
        disponiveis = (
            dias_disponiveis(ano, mes, primeira_noite) if len(ano_noites) else 0
        )

        realizadas = periodo[periodo["Data"] < hoje]
        futuras = periodo[periodo["Data"] >= hoje]

        valor_liquido = periodo["Valor líquido"].sum()
        noites_mes = len(periodo)

        if noites_mes:
            origem = periodo["Origem taxa"].iloc[0]
        elif ano < 2026 or mes < 4 or mes > 10:
            origem = "Não aplicável"
        elif mes in ajustes:
            origem = "Manual"
        else:
            origem = "Automático"

        if len(canceladas):
            cancelamentos = float(
                canceladas.loc[
                    canceladas["Entrada"].dt.month == mes, "Valor bruto",
                ].sum()
            )
        else:
            cancelamentos = 0.0

        reembolso = float(reembolsos.get(mes, {}).get("valor", 0.0) or 0.0)
        # Pagamentos do Airbnb fora das reservas (por exemplo AirCover).
        outros = float(reembolsos.get(mes, {}).get("outros", 0.0) or 0.0)

        linhas.append({
            "Mês nº": mes,
            "Mês": MESES[mes - 1],
            "Earnings bruto (€)": periodo["Valor bruto"].sum(),
            "Taxa automática (€)": periodo["Taxa automática"].sum(),
            "Ajuste manual (€)": ajustes.get(mes, {}).get("valor", None),
            "Taxa utilizada (€)": periodo["Taxa final"].sum(),
            "Origem": origem,
            "Realizado líquido (€)": realizadas["Valor líquido"].sum(),
            "Futuro líquido (€)": futuras["Valor líquido"].sum(),
            "Total líquido (€)": valor_liquido,
            "Cancelamentos retidos (€)": cancelamentos,
            "Reembolsos (€)": reembolso,
            "Outros rendimentos (€)": outros,
            "Total do mês (€)": valor_liquido + cancelamentos - reembolso + outros,
            "Reservas": periodo["Reserva"].nunique(),
            "Noites": noites_mes,
            "Noites realizadas": len(realizadas),
            "Dias do mês": dias_mes,
            "Dias disponíveis": disponiveis,
            "Soma durações": float(
                periodo.drop_duplicates("Reserva")["Duração reserva"].sum()
            ),
            "Mínimo/noite (€)": (
                float(periodo["Valor líquido"].min()) if noites_mes else None
            ),
            "Máximo/noite (€)": (
                float(periodo["Valor líquido"].max()) if noites_mes else None
            ),
        })

    return _indicadores(pd.DataFrame(linhas)), ano_noites


COLUNAS_SOMA = [
    "Earnings bruto (€)", "Taxa automática (€)", "Taxa utilizada (€)",
    "Realizado líquido (€)", "Futuro líquido (€)", "Total líquido (€)",
    "Cancelamentos retidos (€)", "Reembolsos (€)", "Outros rendimentos (€)",
    "Total do mês (€)", "Reservas", "Noites", "Noites realizadas", "Dias disponíveis",
    "Soma durações",
]


def _indicadores(mensal):
    """Calcula os rácios a partir das colunas somáveis."""
    mensal = mensal.copy()
    noites = mensal["Noites"].astype(float)
    disponiveis = mensal["Dias disponíveis"].astype(float)
    reservas = mensal["Reservas"].astype(float)

    mensal["Ocupação (%)"] = (
        (100 * noites / disponiveis.where(disponiveis > 0)).clip(upper=100)
    )
    mensal["Duração média"] = mensal["Soma durações"] / reservas.where(reservas > 0)
    mensal["Média líquida/noite (€)"] = (
        mensal["Total líquido (€)"] / noites.where(noites > 0)
    )
    mensal["Valor líquido/dia disponível (€)"] = (
        mensal["Total líquido (€)"] / disponiveis.where(disponiveis > 0)
    )
    # Quanto renderia o mês se todas as noites fossem vendidas ao preço
    # da melhor noite, e quanto ficou por captar face a isso.
    maximo = mensal["Máximo/noite (€)"].astype(float)
    mensal["Potencial ao máximo (€)"] = maximo * disponiveis.where(disponiveis > 0)
    mensal["Por captar (€)"] = (
        mensal["Potencial ao máximo (€)"] - mensal["Total líquido (€)"]
    )
    return mensal


def agregar_mensal(mensais):
    """Soma os resumos mensais de vários alojamentos num só."""
    mensais = list(mensais)
    if len(mensais) == 1:
        return mensais[0].copy()

    total = mensais[0][["Mês nº", "Mês", "Dias do mês"]].copy()
    for coluna in COLUNAS_SOMA:
        total[coluna] = sum(mensal[coluna].to_numpy() for mensal in mensais)

    origens = pd.concat([mensal["Origem"] for mensal in mensais], axis=1)

    def juntar_origem(linha):
        valores = {valor for valor in linha if valor != "Não aplicável"}
        if not valores:
            return "Não aplicável"
        return valores.pop() if len(valores) == 1 else "Misto"

    total["Origem"] = origens.apply(juntar_origem, axis=1).to_numpy()
    total["Ajuste manual (€)"] = None
    total["Mínimo/noite (€)"] = pd.concat(
        [mensal["Mínimo/noite (€)"].astype(float) for mensal in mensais], axis=1,
    ).min(axis=1).to_numpy()
    total["Máximo/noite (€)"] = pd.concat(
        [mensal["Máximo/noite (€)"].astype(float) for mensal in mensais], axis=1,
    ).max(axis=1).to_numpy()
    return _indicadores(total)


def resumo_anual(mensal, ano, hoje):
    """Indicadores de topo de um resumo mensal (um alojamento ou vários)."""
    ano = int(ano)
    noites = float(mensal["Noites"].sum())
    liquido = float(mensal["Total líquido (€)"].sum())

    if ano == hoje.year:
        # Ocupação até ontem: só conta os dias que já passaram.
        realizadas = float(mensal["Noites realizadas"].sum())
        decorridos = 0.0
        for _, linha in mensal.iterrows():
            mes = int(linha["Mês nº"])
            if mes < hoje.month:
                decorridos += linha["Dias disponíveis"]
            elif mes == hoje.month:
                parte = (hoje.day - 1) / linha["Dias do mês"]
                decorridos += linha["Dias disponíveis"] * parte
        ocupacao = 100 * realizadas / decorridos if decorridos else None
        ocupacao_rotulo = "Ocupação até hoje"
    else:
        disponiveis = float(mensal["Dias disponíveis"].sum())
        ocupacao = 100 * noites / disponiveis if disponiveis else None
        ocupacao_rotulo = "Ocupação"

    if ocupacao is not None:
        ocupacao = min(ocupacao, 100.0)

    return {
        "realizado": float(mensal["Realizado líquido (€)"].sum()),
        "futuro": float(mensal["Futuro líquido (€)"].sum()),
        "liquido": liquido,
        "cancelamentos": float(mensal["Cancelamentos retidos (€)"].sum()),
        "reembolsos": float(mensal["Reembolsos (€)"].sum()),
        "outros": float(mensal["Outros rendimentos (€)"].sum()),
        "total": float(mensal["Total do mês (€)"].sum()),
        "taxa": float(mensal["Taxa utilizada (€)"].sum()),
        "noites": noites,
        "reservas": float(mensal["Reservas"].sum()),
        "ocupacao": ocupacao,
        "ocupacao_rotulo": ocupacao_rotulo,
        "media_noite": liquido / noites if noites else None,
    }


# =========================================================
# RECONCILIAÇÃO
# =========================================================

def reconciliacao(
    reservas, ano, taxa_turistica, reembolsos_manuais, outros_rendimentos=0.0,
):
    """Componentes financeiros de um alojamento (ano = ano de entrada)."""
    dados_ano = reservas[reservas["Entrada"].dt.year == int(ano)]
    valor = dados_ano["Valor bruto"]
    cancelada = dados_ano["Cancelada"]

    total_csv = float(valor.sum())

    return {
        "registos": dados_ano,
        "positivos": float(valor[valor > 0].sum()),
        "negativos": float(abs(valor[valor < 0].sum())),
        "total_csv": total_csv,
        "ativas": float(valor[~cancelada].sum()),
        "canceladas": float(valor[cancelada].sum()),
        "cancelamentos_positivos": float(valor[cancelada & (valor > 0)].sum()),
        "cancelamentos_negativos": float(abs(valor[cancelada & (valor < 0)].sum())),
        "reembolsos_manuais": float(reembolsos_manuais),
        "outros_rendimentos": float(outros_rendimentos),
        "taxa": float(taxa_turistica),
        "final": (
            total_csv + float(outros_rendimentos)
            - float(reembolsos_manuais) - float(taxa_turistica)
        ),
    }


def pagamentos_mensais(reservas, ano):
    """Valores por mês como o Airbnb os mostra na página de rendimentos.

    O Airbnb paga cada reserva no dia a seguir à entrada e soma tudo (com
    taxa turística e cancelamentos) no mês desse pagamento.
    """
    if not len(reservas):
        return [0.0] * 12
    pagamento = reservas["Entrada"] + pd.Timedelta(days=1)
    do_ano = reservas[pagamento.dt.year == int(ano)]
    meses = pagamento[pagamento.dt.year == int(ano)].dt.month
    somas = do_ano.groupby(meses)["Valor bruto"].sum()
    return [float(somas.get(mes, 0.0)) for mes in range(1, 13)]


def pagamentos_estado(reservas, ano, hoje):
    """(já pago, por pagar) no ano, pela regra do Airbnb.

    Cada reserva é paga no dia a seguir à entrada; conta como paga se esse
    dia já chegou.
    """
    if not len(reservas):
        return 0.0, 0.0
    pagamento = reservas["Entrada"] + pd.Timedelta(days=1)
    do_ano = pagamento.dt.year == int(ano)
    pago = reservas.loc[do_ano & (pagamento <= hoje), "Valor bruto"].sum()
    por_pagar = reservas.loc[do_ano & (pagamento > hoje), "Valor bruto"].sum()
    return float(pago), float(por_pagar)


# =========================================================
# PLANO DE PREÇOS
# =========================================================

def plano_precos(
    base, anterior, reservado, ano_plano, hoje,
    crescimento=0.10, comissao=0.155, desconto=0.10, ocupacoes=None,
    numero_alojamentos=1, taxa_limpeza=0.0,
):
    """Plano mensal de preços para `ano_plano`.

    base       resumo mensal do ano de referência (ano_plano - 1)
    anterior   resumo mensal do ano antes desse (usado quando o mês de
               referência ainda não acabou)
    reservado  resumo mensal das reservas já existentes para ano_plano
    crescimento  objetivo de crescimento do rendimento (0.10 = +10 %)
    comissao     comissão do Airbnb incluída no preço publicado (0.155 = 15,5 %)
    desconto     desconto médio que conta dar (semanal, última hora, etc.)
    ocupacoes    {mês: ocupação esperada em %} para substituir a histórica
    numero_alojamentos  quantos alojamentos o resumo `base` agrega
    taxa_limpeza  taxa de limpeza cobrada por reserva, à parte do preço por
                  noite. Parte do objetivo vem dela, por isso o preço por
                  noite a publicar desce taxa ÷ estadia média.

    Devolve por mês: a referência, o objetivo, o líquido por noite necessário,
    o preço mínimo (depois de descontos) e o preço de tabela a publicar.
    """
    ocupacoes = ocupacoes or {}
    ano_plano = int(ano_plano)
    ano_base = ano_plano - 1
    linhas = []

    for indice in range(12):
        mes = indice + 1
        linha_base = base.iloc[indice]
        linha_anterior = anterior.iloc[indice] if anterior is not None else None

        mes_fechado = (ano_base, mes) < (hoje.year, hoje.month)

        referencia = linha_base
        origem = str(ano_base)

        if not mes_fechado:
            origem = f"{ano_base} (parcial)"
            if (
                linha_anterior is not None
                and linha_anterior["Total líquido (€)"]
                > linha_base["Total líquido (€)"]
            ):
                referencia = linha_anterior
                origem = str(ano_base - 1)

        rendimento = float(referencia["Total líquido (€)"])
        noites = float(referencia["Noites"])
        disponiveis = float(referencia["Dias disponíveis"])

        ocupacao_ref = (
            min(100.0, 100 * noites / disponiveis) if disponiveis else None
        )
        media_ref = rendimento / noites if noites else None

        # Capacidade do ano do plano: mesmos alojamentos, mês completo.
        dias_plano = (
            calendar.monthrange(ano_plano, mes)[1] * int(numero_alojamentos)
        )

        objetivo = rendimento * (1 + crescimento) if rendimento > 0 else None

        ocupacao = ocupacoes.get(mes)
        if ocupacao is None or pd.isna(ocupacao) or ocupacao <= 0:
            ocupacao = ocupacao_ref
        ocupacao = min(100.0, float(ocupacao)) if ocupacao else None

        # Quanto da taxa de limpeza cabe a cada noite: uma reserva paga a
        # taxa uma vez e fica, em média, `estadia` noites.
        reservas_ref = float(referencia["Reservas"])
        estadia = (
            float(referencia["Soma durações"]) / reservas_ref
            if reservas_ref else None
        )
        limpeza_noite = (
            float(taxa_limpeza) / estadia if taxa_limpeza and estadia else 0.0
        )

        if objetivo and ocupacao and dias_plano:
            noites_plano = dias_plano * ocupacao / 100
            liquido_noite = objetivo / noites_plano
            # O que o hóspede tem de pagar por noite no total (noite + parte
            # da limpeza), menos a parte que já vem da taxa de limpeza.
            preco_minimo = max(0.0, liquido_noite / (1 - comissao) - limpeza_noite)
            preco_tabela = preco_minimo / (1 - desconto)
        else:
            noites_plano = None
            liquido_noite = None
            preco_minimo = None
            preco_tabela = None

        ja_reservado = (
            float(reservado.iloc[indice]["Total líquido (€)"])
            if reservado is not None else 0.0
        )
        noites_reservadas = (
            float(reservado.iloc[indice]["Noites"])
            if reservado is not None else 0.0
        )

        linhas.append({
            "Mês nº": mes,
            "Mês": MESES[indice],
            "Referência": origem,
            "Rendimento referência (€)": rendimento if rendimento > 0 else None,
            "Ocupação referência (%)": ocupacao_ref,
            "Líquido/noite referência (€)": media_ref,
            "Máximo/noite referência (€)": referencia["Máximo/noite (€)"],
            "Objetivo (€)": objetivo,
            "Ocupação esperada (%)": ocupacao,
            "Noites necessárias": noites_plano,
            "Líquido/noite necessário (€)": liquido_noite,
            "Variação do preço (%)": variacao(liquido_noite, media_ref),
            "Estadia média referência": estadia,
            "Limpeza por noite (€)": limpeza_noite if preco_minimo is not None else None,
            "Preço mínimo (€)": preco_minimo,
            "Preço de tabela (€)": preco_tabela,
            "Já reservado (€)": ja_reservado,
            "Noites já reservadas": noites_reservadas,
            "Objetivo atingido (%)": (
                100 * ja_reservado / objetivo if objetivo else None
            ),
        })

    return pd.DataFrame(linhas)


def cenarios_desconto(plano, descontos=(5, 7, 10, 15, 20)):
    """Preço que o hóspede paga com cada desconto sobre o preço de tabela."""
    tabela = plano[["Mês", "Preço mínimo (€)", "Preço de tabela (€)"]].copy()
    for desconto in descontos:
        tabela[f"−{desconto} %"] = (
            plano["Preço de tabela (€)"] * (1 - desconto / 100)
        )
    return tabela


# =========================================================
# CALENDÁRIO (iCal + reservas guardadas)
# =========================================================

def ler_ical(texto):
    """Lê um calendário iCal do Airbnb.

    Devolve uma lista de eventos com início, fim (dia de saída), tipo
    ("reserva" ou "bloqueio") e o código da reserva quando existe.
    """
    import re

    # Linhas longas vêm partidas; a continuação começa por espaço ou tab.
    texto = re.sub(r"\r?\n[ \t]", "", texto or "")
    eventos = []
    atual = None

    for linha in texto.splitlines():
        linha = linha.strip()
        if linha == "BEGIN:VEVENT":
            atual = {}
            continue
        if linha == "END:VEVENT":
            if atual is not None and "DTSTART" in atual and "DTEND" in atual:
                inicio = _data_ical(atual["DTSTART"])
                fim = _data_ical(atual["DTEND"])
                if inicio is not None and fim is not None and fim > inicio:
                    resumo = atual.get("SUMMARY", "")
                    descricao = atual.get("DESCRIPTION", "").replace("\\n", "\n")
                    codigo = re.search(r"details/([A-Z0-9]{6,})", descricao)
                    reserva = bool(codigo) or resumo.lower().startswith("reserved")
                    eventos.append({
                        "inicio": inicio,
                        "fim": fim,
                        "tipo": "reserva" if reserva else "bloqueio",
                        "codigo": codigo.group(1) if codigo else None,
                        "resumo": resumo,
                    })
            atual = None
            continue
        if atual is not None and ":" in linha:
            nome, valor = linha.split(":", 1)
            atual[nome.split(";", 1)[0].upper()] = valor

    return eventos


def _data_ical(valor):
    digitos = "".join(caracter for caracter in valor if caracter.isdigit())[:8]
    if len(digitos) < 8:
        return None
    return pd.to_datetime(digitos, format="%Y%m%d", errors="coerce")


def eventos_calendario(reservas, eventos_ical, hoje):
    """Junta as reservas guardadas com o iCal de um alojamento.

    reservas      reservas do alojamento (da base de dados, inclui canceladas)
    eventos_ical  resultado de `ler_ical`, ou None se não houver iCal

    Cada evento tem: inicio, fim, tipo, codigo, noites, hospedes, valor e
    origem ("csv", "ical"). As reservas futuras guardadas que já não aparecem
    no iCal ficam com `em_duvida=True` (podem ter sido canceladas).
    """
    eventos = []
    ativas = reservas[~reservas["Cancelada"]] if len(reservas) else reservas

    codigos_ical = {
        evento["codigo"] for evento in (eventos_ical or []) if evento["codigo"]
    }
    # Só se pode desconfiar de uma reserva se o iCal traz códigos.
    pode_duvidar = bool(codigos_ical)

    codigos_guardados = set()
    periodos_guardados = set()

    for _, reserva in ativas.iterrows():
        codigo = reserva["Confirmation code"]
        codigos_guardados.add(codigo)
        periodos_guardados.add((reserva["Entrada"], reserva["Saída"]))
        eventos.append({
            "inicio": reserva["Entrada"],
            "fim": reserva["Saída"],
            "tipo": "reserva",
            "codigo": codigo,
            "noites": int(reserva["Noites"]),
            "hospedes": int(reserva["Total hóspedes"]),
            "valor": float(reserva["Valor bruto"]),
            "origem": "csv",
            "em_duvida": bool(
                pode_duvidar
                and reserva["Saída"] > hoje
                and codigo not in codigos_ical
            ),
        })

    for evento in eventos_ical or []:
        if evento["tipo"] == "reserva":
            if evento["codigo"] in codigos_guardados:
                continue
            if (evento["inicio"], evento["fim"]) in periodos_guardados:
                continue
        eventos.append({
            "inicio": evento["inicio"],
            "fim": evento["fim"],
            "tipo": evento["tipo"],
            "codigo": evento["codigo"],
            "noites": int((evento["fim"] - evento["inicio"]).days),
            "hospedes": None,
            "valor": None,
            "origem": "ical",
            "em_duvida": False,
        })

    return sorted(eventos, key=lambda evento: (evento["inicio"], evento["fim"]))


def noites_ocupadas(eventos):
    """Conjunto dos dias (noites) ocupados por reservas ou bloqueios."""
    ocupadas = set()
    for evento in eventos:
        ocupadas.update(
            pd.date_range(evento["inicio"], evento["fim"], inclusive="left")
        )
    return ocupadas


def periodos_livres(eventos, inicio, dias):
    """Períodos sem reserva nem bloqueio nos `dias` a partir de `inicio`.

    Devolve uma lista de (primeira noite livre, última noite livre, noites).
    """
    ocupadas = noites_ocupadas(eventos)
    periodos = []
    aberto = None

    for data in pd.date_range(inicio, periods=dias):
        if data in ocupadas:
            if aberto is not None:
                periodos.append((aberto[0], aberto[1], (aberto[1] - aberto[0]).days + 1))
                aberto = None
        elif aberto is None:
            aberto = [data, data]
        else:
            aberto[1] = data

    if aberto is not None:
        periodos.append((aberto[0], aberto[1], (aberto[1] - aberto[0]).days + 1))
    return periodos


def movimentos(eventos_por_alojamento, inicio, dias):
    """Entradas e saídas dos próximos dias, para planear limpezas.

    eventos_por_alojamento  {nome: lista de eventos}
    Devolve linhas ordenadas por data com o tipo "Entrada", "Saída" ou
    "Troca" (saída e entrada no mesmo dia, no mesmo alojamento).
    """
    fim = inicio + pd.Timedelta(days=dias)
    por_dia = {}

    for nome, eventos in eventos_por_alojamento.items():
        for evento in eventos:
            if evento["tipo"] != "reserva":
                continue
            if inicio <= evento["inicio"] < fim:
                por_dia.setdefault((evento["inicio"], nome), {})["entrada"] = evento
            if inicio <= evento["fim"] < fim:
                por_dia.setdefault((evento["fim"], nome), {})["saida"] = evento

    linhas = []
    for (data, nome), partes in sorted(por_dia.items(), key=lambda item: item[0]):
        if "entrada" in partes and "saida" in partes:
            tipo = "Troca"
        elif "entrada" in partes:
            tipo = "Entrada"
        else:
            tipo = "Saída"
        linhas.append({
            "data": data,
            "alojamento": nome,
            "tipo": tipo,
            "entrada": partes.get("entrada"),
            "saida": partes.get("saida"),
        })
    return linhas


# =========================================================
# CUSTOS E RETORNO DO INVESTIMENTO
# =========================================================

TIPOS_CUSTO = [
    "Operacional",
    "Impostos e taxas",
    "Juros do crédito",
    "Amortização de capital",
]

# A comissão do Airbnb não está aqui: a receita usada já vem depois dela.
# (categoria, tipo, anualizar). "Anualizar" é para despesas que caem num ou
# dois meses mas dizem respeito ao ano inteiro: o custo é repartido por 12.
CUSTOS_SUGERIDOS = [
    ("Crédito: juros", "Juros do crédito", False),
    ("Crédito: amortização de capital", "Amortização de capital", False),
    ("Comissão de conta bancária", "Operacional", False),
    ("Seguro de vida", "Operacional", True),
    ("Seguro multirriscos", "Operacional", True),
    ("Seguro de responsabilidade civil", "Operacional", True),
    ("Condomínio", "Operacional", True),
    ("Extra condomínio", "Operacional", True),
    ("IMI", "Impostos e taxas", True),
    ("IVA das estadias", "Impostos e taxas", False),
    ("IVA da comissão da plataforma", "Impostos e taxas", False),
    ("Limpezas", "Operacional", False),
    ("Consumíveis e loiça", "Operacional", False),
    ("Internet e TV", "Operacional", False),
    ("Água", "Operacional", False),
    ("Gás", "Operacional", False),
    ("Eletricidade", "Operacional", False),
    ("Obras e reparações", "Operacional", True),
]


def valor_anual(mensal, anual):
    """O valor anual escrito ganha; senão usa o mensal × 12."""
    if not _vazio(anual) and float(anual) > 0:
        return float(anual)
    if not _vazio(mensal) and float(mensal) > 0:
        return float(mensal) * 12
    return 0.0


def meses_do_registo(registo):
    """Valores mensais (em euros) e opção de anualizar de uma linha guardada.

    Aceita também o formato antigo, em que só havia um valor mensal ou anual.
    """
    guardados = registo.get("month_cents")
    if isinstance(guardados, (list, tuple)) and len(guardados) == 12:
        meses = [
            None if valor is None or pd.isna(valor) else int(valor) / 100
            for valor in guardados
        ]
        return meses, bool(registo.get("annualize"))

    mensal = registo.get("monthly_cents")
    anual = registo.get("annual_cents")
    if not _vazio(anual) and int(anual) > 0:
        # Um valor anual único: fica em janeiro e é repartido pelo ano.
        return [int(anual) / 100] + [None] * 11, True
    if not _vazio(mensal) and int(mensal) > 0:
        return [int(mensal) / 100] * 12, False
    return [None] * 12, bool(registo.get("annualize"))


def custos_por_mes(custos):
    """Totais mensais dos custos.

    custos  lista de dicionários com "anualizar" e "meses" (12 valores)

    Devolve "pago" (o que foi pago em cada mês, como está nas faturas) e
    "custo" (o mesmo, mas com as linhas anualizadas repartidas por 12), e
    acrescenta a cada linha o seu total "anual".
    """
    pago = [0.0] * 12
    custo = [0.0] * 12

    for linha in custos:
        meses = [
            0.0 if _vazio(valor) else float(valor) for valor in linha["meses"]
        ]
        total = sum(meses)
        linha["anual"] = total
        for indice in range(12):
            pago[indice] += meses[indice]
            custo[indice] += total / 12 if linha.get("anualizar") else meses[indice]

    return {"pago": pago, "custo": custo}


def resultado_financeiro(
    receita, custos, capital_investido=0.0, valor_imovel=0.0,
    coeficiente=0.35, taxa_irs=0.28, irs_real=None,
    noites=0.0, media_noite=None, dias_ano=365,
):
    """Conta de exploração anual de um alojamento.

    receita   receita líquida do ano (depois da comissão do Airbnb e sem
              taxa turística)
    custos    lista de dicionários com "tipo" e "anual"
    coeficiente, taxa_irs   estimativa de IRS: receita × coeficiente × taxa
    irs_real  IRS efetivamente pago; se indicado, substitui a estimativa
    """
    por_tipo = {tipo: 0.0 for tipo in TIPOS_CUSTO}
    for custo in custos:
        tipo = custo.get("tipo")
        if tipo not in por_tipo:
            tipo = "Operacional"
        por_tipo[tipo] += float(custo.get("anual") or 0.0)

    operacionais = por_tipo["Operacional"]
    impostos = por_tipo["Impostos e taxas"]
    juros = por_tipo["Juros do crédito"]
    amortizacao = por_tipo["Amortização de capital"]
    despesas = operacionais + impostos + juros + amortizacao

    irs_estimado = max(0.0, receita) * coeficiente * taxa_irs
    usa_irs_real = not _vazio(irs_real) and float(irs_real) > 0
    irs = float(irs_real) if usa_irs_real else irs_estimado

    sobra = receita - despesas
    resultado = sobra - irs
    com_amortizacao = resultado + amortizacao

    # Receita que cobre todas as despesas e o IRS que ela própria gera.
    fator = 1 - coeficiente * taxa_irs
    receita_equilibrio = despesas / fator if fator > 0 else None
    noites_equilibrio = (
        receita_equilibrio / media_noite
        if receita_equilibrio is not None and media_noite else None
    )

    def racio(valor, base):
        return 100 * valor / base if base else None

    return {
        "receita": receita,
        "operacionais": operacionais,
        "impostos": impostos,
        "juros": juros,
        "amortizacao": amortizacao,
        "despesas": despesas,
        "sobra": sobra,
        "irs": irs,
        "irs_estimado": irs_estimado,
        "usa_irs_real": usa_irs_real,
        "resultado": resultado,
        "com_amortizacao": com_amortizacao,
        "margem": racio(resultado, receita),
        "peso_despesas": racio(despesas, receita),
        "roi": racio(resultado, capital_investido),
        "roi_com_amortizacao": racio(com_amortizacao, capital_investido),
        "rendimento_bruto_imovel": racio(receita, valor_imovel),
        "anos_retorno": (
            capital_investido / com_amortizacao
            if capital_investido and com_amortizacao > 0 else None
        ),
        "custo_por_noite": (despesas + irs) / noites if noites else None,
        "receita_equilibrio": receita_equilibrio,
        "noites_equilibrio": noites_equilibrio,
        "ocupacao_equilibrio": (
            min(100.0, 100 * noites_equilibrio / dias_ano)
            if noites_equilibrio is not None else None
        ),
    }
