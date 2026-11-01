import calendar
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.express as px
import streamlit as st
from supabase import create_client


# =========================================================
# CONFIGURAÇÃO
# =========================================================

st.set_page_config(
    page_title="Airbnb Dashboard",
    page_icon="🏠",
    layout="wide",
)

MESES = [
    "Janeiro",
    "Fevereiro",
    "Março",
    "Abril",
    "Maio",
    "Junho",
    "Julho",
    "Agosto",
    "Setembro",
    "Outubro",
    "Novembro",
    "Dezembro",
]

HOJE = pd.Timestamp(
    datetime.now(
        ZoneInfo("Europe/Lisbon")
    ).date()
)


# =========================================================
# LIGAÇÃO AO SUPABASE
# =========================================================

try:
    supabase = create_client(
        st.secrets["supabase"]["url"],
        st.secrets["supabase"]["key"],
    )

except Exception as erro:
    st.error("Não foi possível configurar a ligação ao Supabase.")
    st.code(str(erro))
    st.stop()


# =========================================================
# FUNÇÕES GERAIS
# =========================================================

def euros(valor):
    if pd.isna(valor):
        return "—"

    texto = f"{float(valor):,.2f}"

    return (
        texto
        .replace(",", "X")
        .replace(".", ",")
        .replace("X", ".")
        + " €"
    )


def converter_earnings_para_centimos(valor):
    texto = str(valor).strip()

    texto = (
        texto
        .replace("€", "")
        .replace(" ", "")
    )

    # Formato esperado no CSV Airbnb:
    # €1,494.51
    texto = texto.replace(",", "")

    if texto == "":
        raise ValueError(
            "Foi encontrado um valor Earnings vazio."
        )

    try:
        numero = float(texto)

    except ValueError as erro:
        raise ValueError(
            f"Valor Earnings inválido: {valor}"
        ) from erro

    return int(round(numero * 100))


# =========================================================
# PREPARAÇÃO E VALIDAÇÃO DOS CSV
# =========================================================

def preparar_csv(ficheiro):
    dados = pd.read_csv(
        ficheiro,
        dtype=str,
        encoding="utf-8-sig",
        skipinitialspace=True,
    )

    dados.columns = dados.columns.str.strip()

    colunas_obrigatorias = [
        "Confirmation code",
        "Status",
        "Start date",
        "End date",
        "# of nights",
        "Earnings",
        "Listing",
    ]

    colunas_em_falta = [
        coluna
        for coluna in colunas_obrigatorias
        if coluna not in dados.columns
    ]

    if colunas_em_falta:
        raise ValueError(
            "Colunas em falta no ficheiro "
            f"{ficheiro.name}: "
            + ", ".join(colunas_em_falta)
        )

    # Não guardar nomes, contactos ou outros dados pessoais.
    dados = dados[colunas_obrigatorias].copy()

    for coluna in dados.columns:
        dados[coluna] = (
            dados[coluna]
            .fillna("")
            .astype(str)
            .str.strip()
        )

    if dados["Listing"].eq("").any():
        raise ValueError(
            f"Existem registos sem Listing em {ficheiro.name}."
        )

    if dados["Confirmation code"].eq("").any():
        raise ValueError(
            "Existem reservas sem código de confirmação em "
            f"{ficheiro.name}."
        )

    if dados["Status"].eq("").any():
        raise ValueError(
            f"Existem reservas sem estado em {ficheiro.name}."
        )

    dados["Entrada"] = pd.to_datetime(
        dados["Start date"],
        format="%m/%d/%Y",
        errors="coerce",
    )

    dados["Saída"] = pd.to_datetime(
        dados["End date"],
        format="%m/%d/%Y",
        errors="coerce",
    )

    dados["Noites"] = pd.to_numeric(
        dados["# of nights"],
        errors="coerce",
    )

    dados["Cêntimos"] = dados["Earnings"].map(
        converter_earnings_para_centimos
    )

    dados["Valor"] = dados["Cêntimos"] / 100

    noites_calculadas = (
        dados["Saída"] - dados["Entrada"]
    ).dt.days

    linhas_invalidas = (
        dados["Entrada"].isna()
        | dados["Saída"].isna()
        | dados["Noites"].isna()
        | noites_calculadas.le(0)
        | dados["Noites"].ne(noites_calculadas)
    )

    if linhas_invalidas.any():
        quantidade = int(linhas_invalidas.sum())

        raise ValueError(
            f"Existem {quantidade} reservas com datas "
            "ou número de noites inválidos em "
            f"{ficheiro.name}."
        )

    dados["Noites"] = dados["Noites"].astype(int)

    dados["Cancelada"] = dados["Status"].str.contains(
        r"cancel",
        case=False,
        na=False,
    )

    dados["Ficheiro origem"] = ficheiro.name

    # Remover apenas linhas completamente iguais.
    dados = dados.drop_duplicates()

    return dados


def preparar_lote_csv(ficheiros):
    tabelas = []

    for ficheiro in ficheiros:
        tabela = preparar_csv(ficheiro)
        tabelas.append(tabela)

    if not tabelas:
        return pd.DataFrame()

    lote = pd.concat(
        tabelas,
        ignore_index=True,
    )

    chave = [
        "Listing",
        "Confirmation code",
    ]

    colunas_comparacao = [
        "Status",
        "Start date",
        "End date",
        "# of nights",
        "Earnings",
    ]

    reservas_repetidas = lote[
        lote.duplicated(
            subset=chave,
            keep=False,
        )
    ].copy()

    if not reservas_repetidas.empty:
        conflitos = (
            reservas_repetidas
            .groupby(
                chave,
                dropna=False,
            )[colunas_comparacao]
            .nunique(dropna=False)
            .gt(1)
            .any(axis=1)
        )

        if conflitos.any():
            chaves_conflito = (
                conflitos[
                    conflitos
                ]
                .reset_index()
            )

            exemplos = (
                chaves_conflito
                .head(10)
                .apply(
                    lambda linha: (
                        f"{linha['Listing']} / "
                        f"{linha['Confirmation code']}"
                    ),
                    axis=1,
                )
                .tolist()
            )

            raise ValueError(
                "Os ficheiros selecionados contêm versões "
                "diferentes da mesma reserva: "
                + ", ".join(exemplos)
                + ". Remove o ficheiro antigo ou verifica "
                "qual é a versão mais recente."
            )

    lote = lote.drop_duplicates(
        subset=chave,
        keep="last",
    )

    return lote.reset_index(drop=True)


# =========================================================
# SUPABASE
# =========================================================

def dataframe_para_registos(dados):
    momento_atual = datetime.now(
        ZoneInfo("Europe/Lisbon")
    ).isoformat()

    registos = []

    for _, linha in dados.iterrows():
        registos.append({
            "listing": str(linha["Listing"]).strip(),
            "confirmation_code": str(
                linha["Confirmation code"]
            ).strip(),
            "status": str(linha["Status"]).strip(),
            "start_date": linha["Entrada"].date().isoformat(),
            "end_date": linha["Saída"].date().isoformat(),
            "nights": int(linha["Noites"]),
            "earnings_cents": int(linha["Cêntimos"]),
            "updated_at": momento_atual,
        })

    return registos


def carregar_registos_brutos_supabase():
    todos = []
    inicio = 0
    tamanho_pagina = 1000

    while True:
        fim = inicio + tamanho_pagina - 1

        resposta = (
            supabase
            .table("reservations")
            .select(
                "listing,"
                "confirmation_code,"
                "status,"
                "start_date,"
                "end_date,"
                "nights,"
                "earnings_cents,"
                "created_at,"
                "updated_at"
            )
            .range(inicio, fim)
            .execute()
        )

        pagina = resposta.data or []

        todos.extend(pagina)

        if len(pagina) < tamanho_pagina:
            break

        inicio += tamanho_pagina

    return todos


def registos_sao_iguais(novo, existente):
    campos = [
        "status",
        "start_date",
        "end_date",
        "nights",
        "earnings_cents",
    ]

    return all(
        str(novo[campo]) == str(existente[campo])
        for campo in campos
    )


def guardar_no_supabase(dados):
    novos_registos = dataframe_para_registos(dados)
    registos_existentes = carregar_registos_brutos_supabase()

    indice_existente = {
        (
            registo["listing"],
            registo["confirmation_code"],
        ): registo
        for registo in registos_existentes
    }

    novos = []
    alterados = []
    iguais = []

    for registo in novos_registos:
        chave = (
            registo["listing"],
            registo["confirmation_code"],
        )

        existente = indice_existente.get(chave)

        if existente is None:
            novos.append(registo)

        elif registos_sao_iguais(
            registo,
            existente,
        ):
            iguais.append(registo)

        else:
            alterados.append(registo)

    para_gravar = novos + alterados

    tamanho_lote = 200

    for inicio in range(
        0,
        len(para_gravar),
        tamanho_lote,
    ):
        fim = inicio + tamanho_lote
        bloco = para_gravar[inicio:fim]

        (
            supabase
            .table("reservations")
            .upsert(
                bloco,
                on_conflict=(
                    "listing,confirmation_code"
                ),
            )
            .execute()
        )

    return {
        "novos": len(novos),
        "alterados": len(alterados),
        "iguais": len(iguais),
        "total_ficheiros": len(novos_registos),
    }


def carregar_do_supabase():
    registos = carregar_registos_brutos_supabase()

    if not registos:
        return pd.DataFrame()

    base = pd.DataFrame(registos)

    base["Listing"] = base["listing"]
    base["Confirmation code"] = base["confirmation_code"]
    base["Status"] = base["status"]

    base["Entrada"] = pd.to_datetime(
        base["start_date"],
        errors="coerce",
    )

    base["Saída"] = pd.to_datetime(
        base["end_date"],
        errors="coerce",
    )

    base["Noites"] = pd.to_numeric(
        base["nights"],
        errors="coerce",
    ).astype(int)

    base["Cêntimos"] = pd.to_numeric(
        base["earnings_cents"],
        errors="coerce",
    ).astype(int)

    base["Valor"] = base["Cêntimos"] / 100

    base["Start date"] = (
        base["Entrada"]
        .dt.strftime("%m/%d/%Y")
    )

    base["End date"] = (
        base["Saída"]
        .dt.strftime("%m/%d/%Y")
    )

    base["# of nights"] = (
        base["Noites"]
        .astype(str)
    )

    base["Earnings"] = base["Valor"].map(
        lambda valor: f"€{valor:,.2f}"
    )

    base["Cancelada"] = base["Status"].str.contains(
        r"cancel",
        case=False,
        na=False,
    )

    return base


# =========================================================
# PREPARAÇÃO ANALÍTICA
# =========================================================

def criar_noites(reservas):
    linhas = []

    for _, reserva in reservas.iterrows():
        datas = pd.date_range(
            reserva["Entrada"],
            reserva["Saída"],
            inclusive="left",
        )

        if len(datas) == 0:
            continue

        centimos_totais = int(
            reserva["Cêntimos"]
        )

        sinal = -1 if centimos_totais < 0 else 1
        centimos_absolutos = abs(centimos_totais)

        base, resto = divmod(
            centimos_absolutos,
            len(datas),
        )

        for posicao, data in enumerate(datas):
            centimos_noite = (
                base
                + int(posicao < resto)
            ) * sinal

            linhas.append({
                "Listing": reserva["Listing"],
                "Reserva": reserva["Confirmation code"],
                "Data": data,
                "Valor": centimos_noite / 100,
                "Média reserva/noite": (
                    reserva["Valor"] / len(datas)
                ),
                "Duração reserva": len(datas),
            })

    return pd.DataFrame(
        linhas,
        columns=[
            "Listing",
            "Reserva",
            "Data",
            "Valor",
            "Média reserva/noite",
            "Duração reserva",
        ],
    )


def resumo_mensal(noites, ano):
    linhas = []

    for mes in range(1, 13):
        inicio = pd.Timestamp(
            year=int(ano),
            month=mes,
            day=1,
        )

        fim = inicio + pd.offsets.MonthBegin(1)

        dias_mes = calendar.monthrange(
            int(ano),
            mes,
        )[1]

        periodo = noites[
            (noites["Data"] >= inicio)
            & (noites["Data"] < fim)
        ]

        realizadas = periodo[
            periodo["Data"] < HOJE
        ]

        futuras = periodo[
            periodo["Data"] >= HOJE
        ]

        reservas_mes = periodo.drop_duplicates(
            subset=["Reserva"]
        )

        total = periodo["Valor"].sum()
        numero_noites = len(periodo)

        linhas.append({
            "Mês": MESES[mes - 1],
            "Realizado (€)": realizadas["Valor"].sum(),
            "Futuro (€)": futuras["Valor"].sum(),
            "Total (€)": total,
            "Reservas com noites no mês": len(
                reservas_mes
            ),
            "Noites": numero_noites,
            "Dias do mês": dias_mes,
            "Ocupação calendário (%)": (
                100 * numero_noites / dias_mes
            ),
            "Duração média reserva": (
                reservas_mes[
                    "Duração reserva"
                ].mean()
            ),
            "Mín. média/noite (€)": (
                periodo[
                    "Média reserva/noite"
                ].min()
            ),
            "Máx. média/noite (€)": (
                periodo[
                    "Média reserva/noite"
                ].max()
            ),
            "Média/noite (€)": (
                total / numero_noites
                if numero_noites
                else None
            ),
            "Valor/dia calendário (€)": (
                total / dias_mes
            ),
        })

    return pd.DataFrame(linhas)


# =========================================================
# CABEÇALHO
# =========================================================

st.title("🏠 Airbnb Dashboard")

st.caption(
    "Desempenho anual, análise mensal "
    "e planeamento de preços."
)


# =========================================================
# IMPORTAÇÃO
# =========================================================

with st.sidebar:
    st.header("Dados")

    ficheiros = st.file_uploader(
        "CSV de reservas Airbnb",
        type=["csv"],
        accept_multiple_files=True,
        help=(
            "Seleciona uma ou várias páginas "
            "exportadas do Airbnb."
        ),
    )

    if ficheiros:
        st.caption(
            f"{len(ficheiros)} ficheiro(s) selecionado(s)."
        )

        if st.button(
            "Guardar ou atualizar reservas",
            type="primary",
            use_container_width=True,
        ):
            try:
                lote = preparar_lote_csv(
                    ficheiros
                )

                resultado_importacao = (
                    guardar_no_supabase(lote)
                )

                st.session_state[
                    "mensagem_importacao"
                ] = resultado_importacao

                st.rerun()

            except Exception as erro:
                st.error(
                    "Não foi possível importar "
                    "os ficheiros."
                )

                st.code(str(erro))


# =========================================================
# MENSAGEM APÓS IMPORTAÇÃO
# =========================================================

if "mensagem_importacao" in st.session_state:
    resultado = st.session_state.pop(
        "mensagem_importacao"
    )

    st.success(
        "Importação concluída: "
        f"{resultado['novos']} novas, "
        f"{resultado['alterados']} atualizadas "
        f"e {resultado['iguais']} sem alterações."
    )


# =========================================================
# LEITURA DA BASE DE DADOS
# =========================================================

try:
    dados = carregar_do_supabase()

except Exception as erro:
    st.error(
        "Não foi possível ler as reservas "
        "guardadas no Supabase."
    )

    st.code(str(erro))
    st.stop()


if dados.empty:
    st.info(
        "Ainda não existem reservas guardadas. "
        "Seleciona os CSV na barra lateral e carrega "
        "em 'Guardar ou atualizar reservas'."
    )

    st.stop()


with st.sidebar:
    st.success(
        f"Reservas guardadas: {len(dados)}"
    )


# =========================================================
# FILTROS
# =========================================================

alojamentos = sorted(
    dados["Listing"]
    .dropna()
    .unique()
)

with st.sidebar:
    alojamento = st.selectbox(
        "Alojamento",
        alojamentos,
    )


dados_alojamento = dados[
    dados["Listing"] == alojamento
].copy()

canceladas = dados_alojamento[
    dados_alojamento["Cancelada"]
].copy()

ativas = dados_alojamento[
    ~dados_alojamento["Cancelada"]
].copy()


if ativas.empty:
    st.warning(
        "Não existem reservas não canceladas "
        "para este alojamento."
    )

    st.stop()


noites = criar_noites(ativas)


# Verificar reservas sobrepostas apenas dentro
# do alojamento selecionado.
if noites.duplicated(
    subset=["Listing", "Data"]
).any():
    st.error(
        "Existem reservas sobrepostas neste alojamento. "
        "Revê os dados antes de calcular a ocupação."
    )

    st.stop()


anos = sorted(
    noites["Data"]
    .dt.year
    .unique(),
    reverse=True,
)


with st.sidebar:
    ano = st.selectbox(
        "Ano",
        anos,
    )

    st.caption(
        f"Data de referência: {HOJE:%d/%m/%Y}"
    )

    st.caption(
        "Intervalo de noites guardadas: "
        f"{noites['Data'].min():%d/%m/%Y} a "
        f"{noites['Data'].max():%d/%m/%Y}"
    )


# =========================================================
# RESUMOS
# =========================================================

mensal = resumo_mensal(
    noites,
    int(ano),
)

anterior = resumo_mensal(
    noites,
    int(ano) - 1,
)

ano_noites = noites[
    noites["Data"].dt.year == int(ano)
].copy()


st.warning(
    "Valores baseados em Earnings: não representam "
    "necessariamente faturação, tarifa anunciada ou lucro. "
    "Meses sem registos aparecem a zero, mas isso não "
    "comprova que o histórico esteja completo."
)


resumo, detalhe, precos, qualidade = st.tabs([
    "Resumo anual",
    "Análise mensal",
    "Planeamento de preços",
    "Dados e regras",
])


# =========================================================
# RESUMO ANUAL
# =========================================================

with resumo:
    realizado = mensal[
        "Realizado (€)"
    ].sum()

    futuro = mensal[
        "Futuro (€)"
    ].sum()

    total = realizado + futuro

    numero_noites = len(ano_noites)

    dias_ano = (
        366
        if calendar.isleap(int(ano))
        else 365
    )

    coluna1, coluna2, coluna3 = st.columns(3)

    coluna1.metric(
        "Realizado · noites decorridas",
        euros(realizado),
    )

    coluna2.metric(
        "Reservas futuras",
        euros(futuro),
    )

    coluna3.metric(
        "Total anual assegurado*",
        euros(total),
    )

    coluna1, coluna2, coluna3 = st.columns(3)

    coluna1.metric(
        "Noites reservadas",
        numero_noites,
    )

    coluna2.metric(
        "Ocupação do calendário anual",
        (
            f"{numero_noites / dias_ano:.1%}"
            if dias_ano
            else "—"
        ),
    )

    coluna3.metric(
        "Earnings médio / noite",
        (
            euros(total / numero_noites)
            if numero_noites
            else "—"
        ),
    )

    st.caption(
        "*Inclui reservas futuras sujeitas a "
        "alteração ou cancelamento. "
        "Não inclui previsão para noites ainda livres."
    )

    distribuicao = mensal.melt(
        id_vars="Mês",
        value_vars=[
            "Realizado (€)",
            "Futuro (€)",
        ],
        var_name="Tipo",
        value_name="Valor (€)",
    )

    figura = px.bar(
        distribuicao,
        x="Mês",
        y="Valor (€)",
        color="Tipo",
        barmode="stack",
        title=(
            f"{ano} · realizado e reservas futuras"
        ),
        category_orders={
            "Mês": MESES
        },
        color_discrete_sequence=[
            "#2563EB",
            "#93C5FD",
        ],
    )

    figura.update_traces(
        texttemplate="%{y:.0f} €",
        textposition="outside",
    )

    st.plotly_chart(
        figura,
        use_container_width=True,
    )

    tem_ano_anterior = (
        noites["Data"].dt.year
        == int(ano) - 1
    ).any()

    if tem_ano_anterior:
        comparacao = pd.concat([
            mensal[
                ["Mês", "Total (€)"]
            ].assign(
                Ano=str(ano)
            ),
            anterior[
                ["Mês", "Total (€)"]
            ].assign(
                Ano=str(int(ano) - 1)
            ),
        ])

        figura_comparacao = px.bar(
            comparacao,
            x="Mês",
            y="Total (€)",
            color="Ano",
            barmode="group",
            title=(
                "Comparação mensal · "
                "ano selecionado vs. anterior"
            ),
            category_orders={
                "Mês": MESES
            },
            color_discrete_sequence=[
                "#2563EB",
                "#CBD5E1",
            ],
        )

        figura_comparacao.update_traces(
            texttemplate="%{y:.0f} €",
            textposition="outside",
        )

        st.plotly_chart(
            figura_comparacao,
            use_container_width=True,
        )

        comparacao_anual = pd.DataFrame({
            "Ano": [
                str(int(ano) - 1),
                str(ano),
            ],
            "Valor (€)": [
                anterior["Total (€)"].sum(),
                mensal["Total (€)"].sum(),
            ],
        })

        figura_anual = px.bar(
            comparacao_anual,
            x="Ano",
            y="Valor (€)",
            title=(
                "Total anual presente "
                "na base de dados"
            ),
            color="Ano",
        )

        figura_anual.update_traces(
            texttemplate="%{y:.0f} €",
            textposition="outside",
        )

        st.plotly_chart(
            figura_anual,
            use_container_width=True,
        )

        st.caption(
            "Comparação do total disponível na base "
            "de dados, incluindo reservas futuras. "
            "Ainda não é uma comparação à mesma "
            "antecedência."
        )

    else:
        st.info(
            "Ainda não existem dados do ano anterior "
            "para ativar a comparação homóloga."
        )


# =========================================================
# ANÁLISE MENSAL
# =========================================================

with detalhe:
    st.subheader(
        f"Análise mensal · {ano}"
    )

    mensal_apresentacao = mensal.copy()

    colunas_percentagem = [
        "Ocupação calendário (%)",
    ]

    colunas_decimais = [
        "Realizado (€)",
        "Futuro (€)",
        "Total (€)",
        "Duração média reserva",
        "Mín. média/noite (€)",
        "Máx. média/noite (€)",
        "Média/noite (€)",
        "Valor/dia calendário (€)",
    ]

    mensal_apresentacao[
        colunas_percentagem
    ] = mensal_apresentacao[
        colunas_percentagem
    ].round(1)

    mensal_apresentacao[
        colunas_decimais
    ] = mensal_apresentacao[
        colunas_decimais
    ].round(2)

    st.dataframe(
        mensal_apresentacao,
        hide_index=True,
        use_container_width=True,
    )

    figura_ocupacao = px.bar(
        mensal,
        x="Mês",
        y="Ocupação calendário (%)",
        title=f"Ocupação mensal · {ano}",
        category_orders={
            "Mês": MESES
        },
        color_discrete_sequence=[
            "#2563EB"
        ],
    )

    figura_ocupacao.update_traces(
        texttemplate="%{y:.1f}%",
        textposition="outside",
    )

    st.plotly_chart(
        figura_ocupacao,
        use_container_width=True,
    )

    st.caption(
        "Uma reserva que atravessa meses conta em "
        "cada mês onde tem noites. Por isso, a soma "
        "das reservas mensais não corresponde ao "
        "número anual de reservas únicas. "
        "Os valores mínimo e máximo representam "
        "médias por noite das reservas."
    )

    st.download_button(
        "Descarregar resumo mensal",
        mensal.to_csv(
            index=False,
            sep=";",
            decimal=",",
        ).encode("utf-8-sig"),
        file_name=f"resumo_{ano}.csv",
        mime="text/csv",
    )


# =========================================================
# PLANEAMENTO DE PREÇOS
# =========================================================

with precos:
    st.subheader(
        f"Planeamento · {int(ano) + 1}"
    )

    st.caption(
        "Simulador manual de preços por noite. "
        "O histórico Earnings/noite é apenas uma "
        "referência e não uma tarifa anunciada."
    )

    base_plano = pd.DataFrame({
        "Mês": MESES,
        "Histórico Earnings/noite (€)": (
            mensal["Média/noite (€)"]
            .round(2)
        ),
        "Preço base (€)": [0.0] * 12,
        "Preço mínimo (€)": [0.0] * 12,
        "Ocupação objetivo (%)": [0.0] * 12,
    })

    plano = st.data_editor(
        base_plano,
        disabled=[
            "Mês",
            "Histórico Earnings/noite (€)",
        ],
        hide_index=True,
        use_container_width=True,
        key=(
            f"plano_{alojamento}_{ano}"
        ),
        column_config={
            "Preço base (€)": (
                st.column_config.NumberColumn(
                    min_value=0.0,
                    step=1.0,
                    format="%.2f",
                )
            ),
            "Preço mínimo (€)": (
                st.column_config.NumberColumn(
                    min_value=0.0,
                    step=1.0,
                    format="%.2f",
                )
            ),
            "Ocupação objetivo (%)": (
                st.column_config.NumberColumn(
                    min_value=0.0,
                    max_value=100.0,
                    step=1.0,
                    format="%.1f",
                )
            ),
        },
    )

    colunas_editaveis = [
        "Preço base (€)",
        "Preço mínimo (€)",
        "Ocupação objetivo (%)",
    ]

    for coluna in colunas_editaveis:
        plano[coluna] = pd.to_numeric(
            plano[coluna],
            errors="coerce",
        ).fillna(0.0)

    st.subheader("Preços após desconto")

    cenarios = plano[
        ["Mês", "Preço base (€)"]
    ].copy()

    for desconto in [
        5,
        7,
        10,
        15,
        20,
    ]:
        cenarios[
            f"−{desconto}% (€)"
        ] = (
            plano["Preço base (€)"]
            * (1 - desconto / 100)
        ).round(2)

    st.dataframe(
        cenarios,
        hide_index=True,
        use_container_width=True,
    )

    st.subheader("Simulação de receita")

    desconto_selecionado = st.selectbox(
        "Desconto para a simulação",
        options=[
            0,
            5,
            7,
            10,
            15,
            20,
        ],
        format_func=(
            lambda valor: f"{valor}%"
        ),
    )

    precos_finais = (
        plano["Preço base (€)"]
        * (
            1
            - desconto_selecionado / 100
        )
    ).round(2)

    dias_proximo_ano = pd.Series(
        [
            calendar.monthrange(
                int(ano) + 1,
                mes,
            )[1]
            for mes in range(1, 13)
        ],
        index=plano.index,
    )

    noites_estimadas = (
        dias_proximo_ano
        * plano["Ocupação objetivo (%)"]
        / 100
    )

    receita_simulada = (
        precos_finais
        * noites_estimadas
    )

    simulacao = pd.DataFrame({
        "Mês": plano["Mês"],
        "Dias do mês": dias_proximo_ano,
        "Preço após desconto (€)": (
            precos_finais
        ),
        "Ocupação objetivo (%)": (
            plano["Ocupação objetivo (%)"]
        ),
        "Noites estimadas": (
            noites_estimadas.round(1)
        ),
        "Receita bruta simulada (€)": (
            receita_simulada.round(2)
        ),
    })

    st.metric(
        "Receita bruta simulada anual",
        euros(receita_simulada.sum()),
    )

    st.caption(
        "Preço após desconto × dias do mês × "
        "ocupação objetivo. Sem dedução de "
        "comissões, despesas, impostos ou bloqueios "
        "pessoais. Os descontos são alternativos."
    )

    st.dataframe(
        simulacao,
        hide_index=True,
        use_container_width=True,
    )

    abaixo_do_minimo = plano.loc[
        (
            precos_finais
            < plano["Preço mínimo (€)"]
        )
        & (
            plano["Preço mínimo (€)"] > 0
        ),
        "Mês",
    ].tolist()

    if abaixo_do_minimo:
        st.warning(
            "Preço abaixo do mínimo em: "
            + ", ".join(abaixo_do_minimo)
        )

    exportacao_plano = plano.merge(
        cenarios,
        on=[
            "Mês",
            "Preço base (€)",
        ],
        how="left",
        validate="one_to_one",
    )

    st.download_button(
        "Descarregar plano e descontos",
        exportacao_plano.to_csv(
            index=False,
            sep=";",
            decimal=",",
        ).encode("utf-8-sig"),
        file_name=(
            f"plano_precos_"
            f"{int(ano) + 1}.csv"
        ),
        mime="text/csv",
    )

    st.info(
        "O plano de preços ainda não fica guardado "
        "na base de dados. Descarrega o CSV para "
        "conservar as alterações."
    )


# =========================================================
# DADOS E REGRAS
# =========================================================

with qualidade:
    st.subheader("Estado dos dados")

    coluna1, coluna2, coluna3 = st.columns(3)

    coluna1.metric(
        "Reservas guardadas · todos os alojamentos",
        len(dados),
    )

    coluna2.metric(
        "Reservas · alojamento selecionado",
        len(dados_alojamento),
    )

    coluna3.metric(
        "Alojamentos guardados",
        dados["Listing"].nunique(),
    )

    st.subheader("Regras de cálculo")

    st.markdown(
        """
- A chave de cada reserva é `Listing + Confirmation code`.
- Reservas novas são inseridas.
- Reservas existentes com alterações são atualizadas.
- Reservas iguais são ignoradas.
- A ausência de uma reserva num CSV posterior não elimina o histórico.
- O dia do check-out não conta como noite.
- Earnings é repartido proporcionalmente pelas noites.
- A repartição proporcional é uma aproximação analítica.
- A noite de hoje e as noites seguintes são classificadas como futuras.
- Ocupação é calculada sobre todos os dias do calendário.
- Bloqueios pessoais ainda não são descontados.
- Cancelamentos não contam como noites ocupadas.
- Nomes e contactos não são guardados na base analítica.
        """
    )

    st.subheader(
        "Reservas do alojamento selecionado"
    )

    reservas_apresentacao = dados_alojamento[
        [
            "Confirmation code",
            "Status",
            "Entrada",
            "Saída",
            "Noites",
            "Valor",
        ]
    ].copy()

    reservas_apresentacao = (
        reservas_apresentacao
        .sort_values(
            "Entrada",
            ascending=False,
        )
    )

    st.dataframe(
        reservas_apresentacao,
        hide_index=True,
        use_container_width=True,
    )

    st.subheader(
        "Cancelamentos · alojamento selecionado"
    )

    st.metric(
        "Earnings em cancelamentos · separado",
        euros(canceladas["Valor"].sum()),
    )

    st.caption(
        "Este valor não está incluído nos totais "
        "das estadias. O CSV atual não fornece uma "
        "data financeira adequada para atribuir o "
        "valor a um mês de recebimento."
    )

    if not canceladas.empty:
        st.dataframe(
            canceladas[
                [
                    "Confirmation code",
                    "Status",
                    "Entrada",
                    "Saída",
                    "Valor",
                ]
            ],
            hide_index=True,
            use_container_width=True,
        )