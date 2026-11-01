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

VALOR_TAXA_POR_PESSOA_NOITE = 2.00
MAXIMO_NOITES_TAXADAS_POR_RESERVA = 7


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
# FUNÇÕES DE FORMATAÇÃO
# =========================================================

def euros(valor):
    if valor is None or pd.isna(valor):
        return "—"

    texto = f"{float(valor):,.2f}"

    return (
        texto
        .replace(",", "X")
        .replace(".", ",")
        .replace("X", ".")
        + " €"
    )


def etiqueta_euros(valor):
    if valor is None or pd.isna(valor) or float(valor) == 0:
        return ""

    texto = f"{float(valor):,.0f}"

    return (
        texto
        .replace(",", ".")
        + " €"
    )


def converter_earnings_para_centimos(valor):
    texto = str(valor).strip()

    texto = (
        texto
        .replace("€", "")
        .replace(" ", "")
        .replace(",", "")
    )

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
# TAXA TURÍSTICA
# =========================================================

def data_tem_taxa_turistica(data):
    inicio = pd.Timestamp(
        year=int(data.year),
        month=4,
        day=1,
    )

    fim = pd.Timestamp(
        year=int(data.year),
        month=10,
        day=31,
    )

    return inicio <= data <= fim


# =========================================================
# PREPARAÇÃO DOS CSV
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
        "# of adults",
        "# of children",
        "# of infants",
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
            f"Colunas em falta em {ficheiro.name}: "
            + ", ".join(colunas_em_falta)
        )

    # Excluir nomes, contactos e outros dados pessoais.
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

    dados["Adultos"] = pd.to_numeric(
        dados["# of adults"],
        errors="coerce",
    ).fillna(0).astype(int)

    dados["Crianças"] = pd.to_numeric(
        dados["# of children"],
        errors="coerce",
    ).fillna(0).astype(int)

    dados["Bebés"] = pd.to_numeric(
        dados["# of infants"],
        errors="coerce",
    ).fillna(0).astype(int)

    dados["Total hóspedes"] = (
        dados["Adultos"]
        + dados["Crianças"]
        + dados["Bebés"]
    )

    contagens_invalidas = (
        dados["Adultos"].lt(0)
        | dados["Crianças"].lt(0)
        | dados["Bebés"].lt(0)
        | dados["Total hóspedes"].le(0)
    )

    if contagens_invalidas.any():
        raise ValueError(
            "Existem quantidades de hóspedes inválidas em "
            f"{ficheiro.name}."
        )

    dados["Cêntimos"] = dados["Earnings"].map(
        converter_earnings_para_centimos
    )

    dados["Valor bruto"] = dados["Cêntimos"] / 100

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
            f"Existem {quantidade} reservas com datas ou "
            f"número de noites inválidos em {ficheiro.name}."
        )

    dados["Noites"] = dados["Noites"].astype(int)

    dados["Cancelada"] = dados["Status"].str.contains(
        r"cancel",
        case=False,
        na=False,
    )

    dados["Ficheiro origem"] = ficheiro.name

    dados = dados.drop_duplicates()

    return dados


def preparar_lote_csv(ficheiros):
    tabelas = []

    for ficheiro in ficheiros:
        tabelas.append(
            preparar_csv(ficheiro)
        )

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
        "# of adults",
        "# of children",
        "# of infants",
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
                "Os ficheiros selecionados têm versões diferentes "
                "da mesma reserva: "
                + ", ".join(exemplos)
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
            "listing": str(
                linha["Listing"]
            ).strip(),
            "confirmation_code": str(
                linha["Confirmation code"]
            ).strip(),
            "status": str(
                linha["Status"]
            ).strip(),
            "start_date": (
                linha["Entrada"]
                .date()
                .isoformat()
            ),
            "end_date": (
                linha["Saída"]
                .date()
                .isoformat()
            ),
            "nights": int(
                linha["Noites"]
            ),
            "adults": int(
                linha["Adultos"]
            ),
            "children": int(
                linha["Crianças"]
            ),
            "infants": int(
                linha["Bebés"]
            ),
            "earnings_cents": int(
                linha["Cêntimos"]
            ),
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
                "adults,"
                "children,"
                "infants,"
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
        "adults",
        "children",
        "infants",
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
        bloco = para_gravar[
            inicio:inicio + tamanho_lote
        ]

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
    ).fillna(0).astype(int)

    base["Adultos"] = pd.to_numeric(
        base["adults"],
        errors="coerce",
    ).fillna(0).astype(int)

    base["Crianças"] = pd.to_numeric(
        base["children"],
        errors="coerce",
    ).fillna(0).astype(int)

    base["Bebés"] = pd.to_numeric(
        base["infants"],
        errors="coerce",
    ).fillna(0).astype(int)

    base["Total hóspedes"] = (
        base["Adultos"]
        + base["Crianças"]
        + base["Bebés"]
    )

    base["Cêntimos"] = pd.to_numeric(
        base["earnings_cents"],
        errors="coerce",
    ).fillna(0).astype(int)

    base["Valor bruto"] = (
        base["Cêntimos"] / 100
    )

    base["Cancelada"] = (
        base["Status"]
        .str.contains(
            r"cancel",
            case=False,
            na=False,
        )
    )

    return base


# =========================================================
# CRIAÇÃO DA TABELA DE NOITES
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

        sinal = (
            -1
            if centimos_totais < 0
            else 1
        )

        centimos_absolutos = abs(
            centimos_totais
        )

        base_noite, resto = divmod(
            centimos_absolutos,
            len(datas),
        )

        total_hospedes = int(
            reserva["Total hóspedes"]
        )

        noites_taxadas = 0

        for posicao, data in enumerate(datas):
            centimos_brutos = (
                base_noite
                + int(posicao < resto)
            ) * sinal

            noite_elegivel = (
                data_tem_taxa_turistica(data)
                and noites_taxadas
                < MAXIMO_NOITES_TAXADAS_POR_RESERVA
            )

            if noite_elegivel:
                taxa_centimos = int(
                    round(
                        total_hospedes
                        * VALOR_TAXA_POR_PESSOA_NOITE
                        * 100
                    )
                )

                noites_taxadas += 1

                dormidas_taxadas = (
                    total_hospedes
                )

            else:
                taxa_centimos = 0
                dormidas_taxadas = 0

            centimos_liquidos = (
                centimos_brutos
                - taxa_centimos
            )

            linhas.append({
                "Listing": reserva["Listing"],
                "Reserva": (
                    reserva["Confirmation code"]
                ),
                "Data": data,
                "Valor bruto": (
                    centimos_brutos / 100
                ),
                "Taxa turística": (
                    taxa_centimos / 100
                ),
                "Valor líquido": (
                    centimos_liquidos / 100
                ),
                "Dormidas taxadas": (
                    dormidas_taxadas
                ),
                "Total hóspedes": (
                    total_hospedes
                ),
                "Duração reserva": (
                    len(datas)
                ),
            })

    noites = pd.DataFrame(
        linhas,
        columns=[
            "Listing",
            "Reserva",
            "Data",
            "Valor bruto",
            "Taxa turística",
            "Valor líquido",
            "Dormidas taxadas",
            "Total hóspedes",
            "Duração reserva",
        ],
    )

    if noites.empty:
        return noites

    resumo_reserva = (
        noites
        .groupby(
            [
                "Listing",
                "Reserva",
            ],
            as_index=False,
        )
        .agg(
            Valor_bruto_reserva=(
                "Valor bruto",
                "sum",
            ),
            Taxa_reserva=(
                "Taxa turística",
                "sum",
            ),
            Valor_liquido_reserva=(
                "Valor líquido",
                "sum",
            ),
            Duracao_reserva=(
                "Duração reserva",
                "first",
            ),
        )
    )

    resumo_reserva[
        "Média líquida reserva/noite"
    ] = (
        resumo_reserva[
            "Valor_liquido_reserva"
        ]
        / resumo_reserva[
            "Duracao_reserva"
        ]
    )

    noites = noites.merge(
        resumo_reserva[
            [
                "Listing",
                "Reserva",
                "Média líquida reserva/noite",
            ]
        ],
        on=[
            "Listing",
            "Reserva",
        ],
        how="left",
        validate="many_to_one",
    )

    return noites


# =========================================================
# RESUMO MENSAL
# =========================================================

def resumo_mensal(noites, ano):
    linhas = []

    for mes in range(1, 13):
        inicio = pd.Timestamp(
            year=int(ano),
            month=mes,
            day=1,
        )

        fim = (
            inicio
            + pd.offsets.MonthBegin(1)
        )

        dias_mes = calendar.monthrange(
            int(ano),
            mes,
        )[1]

        periodo = noites[
            (noites["Data"] >= inicio)
            & (noites["Data"] < fim)
        ].copy()

        realizadas = periodo[
            periodo["Data"] < HOJE
        ]

        futuras = periodo[
            periodo["Data"] >= HOJE
        ]

        reservas_mes = (
            periodo
            .drop_duplicates(
                subset=[
                    "Listing",
                    "Reserva",
                ]
            )
        )

        total_bruto = (
            periodo["Valor bruto"].sum()
        )

        taxa_turistica = (
            periodo["Taxa turística"].sum()
        )

        total_liquido = (
            periodo["Valor líquido"].sum()
        )

        realizado_liquido = (
            realizadas[
                "Valor líquido"
            ].sum()
        )

        futuro_liquido = (
            futuras[
                "Valor líquido"
            ].sum()
        )

        numero_noites = len(periodo)

        linhas.append({
            "Mês": MESES[mes - 1],
            "Earnings bruto (€)": (
                total_bruto
            ),
            "Taxa turística (€)": (
                taxa_turistica
            ),
            "Realizado líquido (€)": (
                realizado_liquido
            ),
            "Futuro líquido (€)": (
                futuro_liquido
            ),
            "Total líquido (€)": (
                total_liquido
            ),
            "Reservas com noites no mês": (
                len(reservas_mes)
            ),
            "Noites": numero_noites,
            "Dias do mês": dias_mes,
            "Ocupação calendário (%)": (
                100
                * numero_noites
                / dias_mes
            ),
            "Duração média reserva": (
                reservas_mes[
                    "Duração reserva"
                ].mean()
            ),
            "Mín. líquido/noite (€)": (
                periodo[
                    "Média líquida reserva/noite"
                ].min()
            ),
            "Máx. líquido/noite (€)": (
                periodo[
                    "Média líquida reserva/noite"
                ].max()
            ),
            "Média líquida/noite (€)": (
                total_liquido
                / numero_noites
                if numero_noites
                else None
            ),
            "Valor líquido/dia calendário (€)": (
                total_liquido
                / dias_mes
            ),
            "Dormidas taxadas": (
                periodo[
                    "Dormidas taxadas"
                ].sum()
            ),
        })

    return pd.DataFrame(linhas)


# =========================================================
# CABEÇALHO E IMPORTAÇÃO
# =========================================================

st.title("🏠 Airbnb Dashboard")

st.caption(
    "Desempenho anual, análise mensal, "
    "taxa turística e planeamento de preços."
)


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
                    guardar_no_supabase(
                        lote
                    )
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
        "Seleciona os CSV na barra lateral."
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


noites = criar_noites(
    ativas
)


if noites.duplicated(
    subset=[
        "Listing",
        "Data",
    ]
).any():
    st.error(
        "Existem reservas sobrepostas neste alojamento."
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


st.info(
    "Os indicadores de desempenho excluem a taxa turística. "
    "O valor original do Airbnb é mantido como Earnings bruto "
    "para reconciliação."
)


resumo, detalhe, impostos, precos, qualidade = st.tabs([
    "Resumo anual",
    "Análise mensal",
    "Taxa turística",
    "Planeamento de preços",
    "Dados e regras",
])


# =========================================================
# RESUMO ANUAL
# =========================================================

with resumo:
    realizado = mensal[
        "Realizado líquido (€)"
    ].sum()

    futuro = mensal[
        "Futuro líquido (€)"
    ].sum()

    total_liquido = (
        realizado + futuro
    )

    total_bruto = mensal[
        "Earnings bruto (€)"
    ].sum()

    taxa_total = mensal[
        "Taxa turística (€)"
    ].sum()

    numero_noites = len(
        ano_noites
    )

    dias_ano = (
        366
        if calendar.isleap(
            int(ano)
        )
        else 365
    )

    coluna1, coluna2, coluna3 = st.columns(3)

    coluna1.metric(
        "Realizado sem taxa turística",
        euros(realizado),
    )

    coluna2.metric(
        "Reservas futuras sem taxa",
        euros(futuro),
    )

    coluna3.metric(
        "Total anual líquido assegurado*",
        euros(total_liquido),
    )

    coluna1, coluna2, coluna3 = st.columns(3)

    coluna1.metric(
        "Noites reservadas",
        numero_noites,
    )

    coluna2.metric(
        "Ocupação do calendário anual",
        f"{numero_noites / dias_ano:.1%}",
    )

    coluna3.metric(
        "Valor médio líquido / noite",
        (
            euros(
                total_liquido
                / numero_noites
            )
            if numero_noites
            else "—"
        ),
    )

    coluna1, coluna2 = st.columns(2)

    coluna1.metric(
        "Earnings bruto Airbnb",
        euros(total_bruto),
    )

    coluna2.metric(
        "Taxa turística excluída",
        euros(taxa_total),
    )

    st.caption(
        "*Inclui reservas futuras sujeitas a alteração "
        "ou cancelamento. A taxa turística foi retirada "
        "dos indicadores de desempenho."
    )

    distribuicao = mensal.melt(
        id_vars="Mês",
        value_vars=[
            "Realizado líquido (€)",
            "Futuro líquido (€)",
        ],
        var_name="Tipo",
        value_name="Valor (€)",
    )

    distribuicao["Etiqueta"] = (
        distribuicao["Valor (€)"]
        .map(etiqueta_euros)
    )

    figura = px.bar(
        distribuicao,
        x="Mês",
        y="Valor (€)",
        color="Tipo",
        text="Etiqueta",
        barmode="stack",
        title=(
            f"{ano} · realizado e futuro "
            "sem taxa turística"
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
        textposition="outside",
        cliponaxis=False,
    )

    figura.update_layout(
        uniformtext_minsize=9,
        uniformtext_mode="hide",
        margin=dict(
            t=80,
            r=30,
            b=50,
            l=50,
        ),
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
                [
                    "Mês",
                    "Total líquido (€)",
                ]
            ]
            .rename(
                columns={
                    "Total líquido (€)": "Valor (€)"
                }
            )
            .assign(
                Ano=str(ano)
            ),
            anterior[
                [
                    "Mês",
                    "Total líquido (€)",
                ]
            ]
            .rename(
                columns={
                    "Total líquido (€)": "Valor (€)"
                }
            )
            .assign(
                Ano=str(
                    int(ano) - 1
                )
            ),
        ])

        comparacao["Etiqueta"] = (
            comparacao["Valor (€)"]
            .map(etiqueta_euros)
        )

        figura_comparacao = px.bar(
            comparacao,
            x="Mês",
            y="Valor (€)",
            color="Ano",
            text="Etiqueta",
            barmode="group",
            title=(
                "Comparação mensal líquida "
                "com o ano anterior"
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
            textposition="outside",
            cliponaxis=False,
        )

        figura_comparacao.update_layout(
            uniformtext_minsize=9,
            uniformtext_mode="hide",
            margin=dict(
                t=80,
                r=30,
                b=50,
                l=50,
            ),
        )

        st.plotly_chart(
            figura_comparacao,
            use_container_width=True,
        )

    else:
        st.info(
            "Ainda não há dados suficientes do ano "
            "anterior para a comparação homóloga."
        )


# =========================================================
# ANÁLISE MENSAL
# =========================================================

with detalhe:
    st.subheader(
        f"Análise mensal líquida · {ano}"
    )

    colunas_mensais = [
        "Mês",
        "Earnings bruto (€)",
        "Taxa turística (€)",
        "Total líquido (€)",
        "Reservas com noites no mês",
        "Noites",
        "Dias do mês",
        "Ocupação calendário (%)",
        "Duração média reserva",
        "Mín. líquido/noite (€)",
        "Máx. líquido/noite (€)",
        "Média líquida/noite (€)",
        "Valor líquido/dia calendário (€)",
    ]

    mensal_apresentacao = mensal[
        colunas_mensais
    ].copy()

    st.dataframe(
        mensal_apresentacao.round(2),
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
        text=mensal[
            "Ocupação calendário (%)"
        ].map(
            lambda valor: (
                f"{valor:.1f}%"
                if valor > 0
                else ""
            )
        ),
        textposition="outside",
        cliponaxis=False,
    )

    figura_ocupacao.update_layout(
        uniformtext_minsize=9,
        uniformtext_mode="hide",
    )

    st.plotly_chart(
        figura_ocupacao,
        use_container_width=True,
    )

    st.download_button(
        "Descarregar resumo mensal",
        mensal.to_csv(
            index=False,
            sep=";",
            decimal=",",
        ).encode("utf-8-sig"),
        file_name=(
            f"resumo_{alojamento}_{ano}.csv"
        ),
        mime="text/csv",
    )


# =========================================================
# TAXA TURÍSTICA
# =========================================================

with impostos:
    st.subheader(
        f"Mapa da taxa turística · {ano}"
    )

    taxa_total = mensal[
        "Taxa turística (€)"
    ].sum()

    dormidas_taxadas = mensal[
        "Dormidas taxadas"
    ].sum()

    coluna1, coluna2 = st.columns(2)

    coluna1.metric(
        "Total calculado a repassar",
        euros(taxa_total),
    )

    coluna2.metric(
        "Dormidas taxadas",
        int(dormidas_taxadas),
    )

    mapa_impostos = mensal[
        [
            "Mês",
            "Dormidas taxadas",
            "Taxa turística (€)",
        ]
    ].copy()

    st.dataframe(
        mapa_impostos.round(2),
        hide_index=True,
        use_container_width=True,
    )

    mapa_impostos[
        "Etiqueta"
    ] = mapa_impostos[
        "Taxa turística (€)"
    ].map(etiqueta_euros)

    figura_taxa = px.bar(
        mapa_impostos,
        x="Mês",
        y="Taxa turística (€)",
        text="Etiqueta",
        title=(
            f"Taxa turística mensal · {ano}"
        ),
        category_orders={
            "Mês": MESES
        },
        color_discrete_sequence=[
            "#F59E0B"
        ],
    )

    figura_taxa.update_traces(
        textposition="outside",
        cliponaxis=False,
    )

    figura_taxa.update_layout(
        uniformtext_minsize=9,
        uniformtext_mode="hide",
        margin=dict(
            t=80,
            r=30,
            b=50,
            l=50,
        ),
    )

    st.plotly_chart(
        figura_taxa,
        use_container_width=True,
    )

    st.info(
        "Cálculo operacional utilizado no dashboard: "
        "2 € por noite por cada adulto, criança e bebé "
        "registado no CSV, entre 1 de abril e 31 de outubro, "
        "até sete noites tributáveis por reserva."
    )

    st.caption(
        "Este mapa serve para gestão e reconciliação. "
        "O cálculo usa a forma de cobrança descrita para "
        "as reservas Airbnb e não identifica automaticamente "
        "isenções ou correções posteriores."
    )

    st.download_button(
        "Descarregar mapa mensal da taxa",
        mapa_impostos.to_csv(
            index=False,
            sep=";",
            decimal=",",
        ).encode("utf-8-sig"),
        file_name=(
            f"taxa_turistica_"
            f"{alojamento}_{ano}.csv"
        ),
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
        "O histórico apresentado utiliza o valor líquido "
        "por noite, já sem a taxa turística."
    )

    base_plano = pd.DataFrame({
        "Mês": MESES,
        "Histórico líquido/noite (€)": (
            mensal[
                "Média líquida/noite (€)"
            ].round(2)
        ),
        "Preço base (€)": [0.0] * 12,
        "Preço mínimo (€)": [0.0] * 12,
        "Ocupação objetivo (%)": [0.0] * 12,
    })

    plano = st.data_editor(
        base_plano,
        disabled=[
            "Mês",
            "Histórico líquido/noite (€)",
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

    for coluna in [
        "Preço base (€)",
        "Preço mínimo (€)",
        "Ocupação objetivo (%)",
    ]:
        plano[coluna] = pd.to_numeric(
            plano[coluna],
            errors="coerce",
        ).fillna(0.0)

    cenarios = plano[
        [
            "Mês",
            "Preço base (€)",
        ]
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
            * (
                1
                - desconto / 100
            )
        ).round(2)

    st.subheader(
        "Preços após desconto"
    )

    st.dataframe(
        cenarios,
        hide_index=True,
        use_container_width=True,
    )

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
            plano[
                "Ocupação objetivo (%)"
            ]
        ),
        "Noites estimadas": (
            noites_estimadas.round(1)
        ),
        "Receita líquida simulada (€)": (
            receita_simulada.round(2)
        ),
    })

    st.metric(
        "Receita líquida simulada anual",
        euros(
            receita_simulada.sum()
        ),
    )

    st.caption(
        "Esta simulação assume que os preços introduzidos "
        "já são valores líquidos sem taxa turística."
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


# =========================================================
# DADOS E REGRAS
# =========================================================

with qualidade:
    st.subheader(
        "Estado dos dados"
    )

    coluna1, coluna2, coluna3 = st.columns(3)

    coluna1.metric(
        "Reservas guardadas",
        len(dados),
    )

    coluna2.metric(
        "Reservas neste alojamento",
        len(dados_alojamento),
    )

    coluna3.metric(
        "Alojamentos guardados",
        dados["Listing"].nunique(),
    )

    st.subheader(
        "Regras aplicadas"
    )

    st.markdown(
        """
- Chave única: `Listing + Confirmation code`.
- Reservas novas são inseridas.
- Reservas alteradas são atualizadas.
- Reservas iguais são ignoradas.
- Registos ausentes de novos CSV não são eliminados.
- O dia do check-out não conta como noite.
- Earnings bruto é preservado.
- A taxa turística é retirada do realizado, futuro, totais e médias.
- A taxa operacional usa adultos, crianças e bebés.
- Taxa de 2 € por pessoa/noite.
- Período considerado: 1 de abril a 31 de outubro.
- Máximo de sete noites tributáveis por reserva.
- Cancelamentos não contam para ocupação nem receita normal.
- Nomes e contactos não são guardados.
        """
    )

    reservas_apresentacao = (
        dados_alojamento[
            [
                "Confirmation code",
                "Status",
                "Entrada",
                "Saída",
                "Noites",
                "Adultos",
                "Crianças",
                "Bebés",
                "Valor bruto",
            ]
        ]
        .sort_values(
            "Entrada",
            ascending=False,
        )
    )

    st.subheader(
        "Reservas do alojamento"
    )

    st.dataframe(
        reservas_apresentacao,
        hide_index=True,
        use_container_width=True,
    )

    st.subheader(
        "Cancelamentos"
    )

    st.metric(
        "Earnings bruto em cancelamentos",
        euros(
            canceladas[
                "Valor bruto"
            ].sum()
        ),
    )

    st.caption(
        "Os cancelamentos não entram nos indicadores "
        "normais de estadias."
    )