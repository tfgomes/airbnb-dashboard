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

# No nosso dashboard, a taxa só é aplicada a partir desta data.
INICIO_TAXA = pd.Timestamp("2026-04-01")


# =========================================================
# LIGAÇÃO AO SUPABASE
# =========================================================

try:
    supabase = create_client(
        st.secrets["supabase"]["url"],
        st.secrets["supabase"]["key"],
    )

except Exception as erro:
    st.error(
        "Não foi possível configurar a ligação ao Supabase."
    )
    st.code(str(erro))
    st.stop()


# =========================================================
# FORMATAÇÃO
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
    if (
        valor is None
        or pd.isna(valor)
        or abs(float(valor)) < 0.005
    ):
        return ""

    return (
        f"{float(valor):,.0f}"
        .replace(",", ".")
        + " €"
    )


def converter_earnings_para_centimos(valor):
    texto = (
        str(valor)
        .strip()
        .replace("€", "")
        .replace(" ", "")
        .replace(",", "")
    )

    if not texto:
        raise ValueError(
            "Foi encontrado um valor Earnings vazio."
        )

    try:
        return int(
            round(float(texto) * 100)
        )

    except ValueError as erro:
        raise ValueError(
            f"Valor Earnings inválido: {valor}"
        ) from erro


# =========================================================
# PREPARAR CSV AIRBNB
# =========================================================

def preparar_csv(ficheiro):

    dados = pd.read_csv(
        ficheiro,
        dtype=str,
        encoding="utf-8-sig",
        skipinitialspace=True,
    )

    dados.columns = (
        dados.columns
        .str.strip()
    )

    obrigatorias = [
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

    falta = [
        coluna
        for coluna in obrigatorias
        if coluna not in dados.columns
    ]

    if falta:
        raise ValueError(
            f"Colunas em falta em {ficheiro.name}: "
            + ", ".join(falta)
        )

    # Não guardamos nome/contacto do hóspede.
    dados = dados[
        obrigatorias
    ].copy()

    for coluna in dados.columns:
        dados[coluna] = (
            dados[coluna]
            .fillna("")
            .astype(str)
            .str.strip()
        )

    campos_vazios = (
        dados["Listing"].eq("")
        | dados["Confirmation code"].eq("")
        | dados["Status"].eq("")
    )

    if campos_vazios.any():
        raise ValueError(
            f"Existem registos sem Listing, "
            f"código ou estado em {ficheiro.name}."
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
        (
            dados[
                [
                    "Adultos",
                    "Crianças",
                    "Bebés",
                ]
            ] < 0
        )
        .any(axis=1)
        | dados["Total hóspedes"].le(0)
    )

    if contagens_invalidas.any():
        raise ValueError(
            f"Existem quantidades de hóspedes "
            f"inválidas em {ficheiro.name}."
        )

    dados["Cêntimos"] = (
        dados["Earnings"]
        .map(
            converter_earnings_para_centimos
        )
    )

    dados["Valor bruto"] = (
        dados["Cêntimos"] / 100
    )

    noites_calculadas = (
        dados["Saída"]
        - dados["Entrada"]
    ).dt.days

    invalidas = (
        dados["Entrada"].isna()
        | dados["Saída"].isna()
        | dados["Noites"].isna()
        | noites_calculadas.le(0)
        | dados["Noites"].ne(
            noites_calculadas
        )
    )

    if invalidas.any():
        raise ValueError(
            f"Existem {int(invalidas.sum())} "
            f"reservas com datas ou noites "
            f"inválidas em {ficheiro.name}."
        )

    dados["Noites"] = (
        dados["Noites"]
        .astype(int)
    )

    dados["Cancelada"] = (
        dados["Status"]
        .str.contains(
            r"cancel",
            case=False,
            na=False,
        )
    )

    return dados.drop_duplicates()


# =========================================================
# JUNTAR VÁRIOS CSV
# =========================================================

def preparar_lote_csv(ficheiros):

    tabelas = [
        preparar_csv(ficheiro)
        for ficheiro in ficheiros
    ]

    lote = pd.concat(
        tabelas,
        ignore_index=True,
    )

    chave = [
        "Listing",
        "Confirmation code",
    ]

    comparar = [
        "Status",
        "Start date",
        "End date",
        "# of nights",
        "# of adults",
        "# of children",
        "# of infants",
        "Earnings",
    ]

    repetidas = lote[
        lote.duplicated(
            subset=chave,
            keep=False,
        )
    ]

    if not repetidas.empty:

        conflitos = (
            repetidas
            .groupby(
                chave,
                dropna=False,
            )[comparar]
            .nunique(
                dropna=False
            )
            .gt(1)
            .any(axis=1)
        )

        if conflitos.any():

            exemplos = (
                conflitos[
                    conflitos
                ]
                .reset_index()
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
                "Foram encontradas versões "
                "diferentes da mesma reserva: "
                + ", ".join(exemplos)
            )

    return (
        lote
        .drop_duplicates(
            subset=chave,
            keep="last",
        )
        .reset_index(drop=True)
    )


# =========================================================
# CONVERTER PARA SUPABASE
# =========================================================

def dataframe_para_registos(dados):

    agora = datetime.now(
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

            "updated_at": agora,
        })

    return registos


# =========================================================
# LEITURA GENERICA SUPABASE
# =========================================================

def ler_tabela(
    nome,
    colunas,
):

    todos = []
    inicio = 0
    tamanho_pagina = 1000

    while True:

        resposta = (
            supabase
            .table(nome)
            .select(colunas)
            .range(
                inicio,
                inicio
                + tamanho_pagina
                - 1,
            )
            .execute()
        )

        bloco = (
            resposta.data
            or []
        )

        todos.extend(
            bloco
        )

        if len(bloco) < tamanho_pagina:
            return todos

        inicio += tamanho_pagina


# =========================================================
# GUARDAR RESERVAS
# =========================================================

def guardar_reservas(dados):

    novos_registos = (
        dataframe_para_registos(
            dados
        )
    )

    existentes = ler_tabela(
        "reservations",
        (
            "listing,"
            "confirmation_code,"
            "status,"
            "start_date,"
            "end_date,"
            "nights,"
            "adults,"
            "children,"
            "infants,"
            "earnings_cents"
        ),
    )

    indice = {
        (
            registo["listing"],
            registo["confirmation_code"],
        ): registo
        for registo in existentes
    }

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

    novos = []
    alterados = []
    iguais = []

    for registo in novos_registos:

        chave = (
            registo["listing"],
            registo["confirmation_code"],
        )

        atual = indice.get(
            chave
        )

        if atual is None:

            novos.append(
                registo
            )

        elif all(
            str(registo[campo])
            == str(atual[campo])
            for campo in campos
        ):

            iguais.append(
                registo
            )

        else:

            alterados.append(
                registo
            )

    para_gravar = (
        novos
        + alterados
    )

    for inicio in range(
        0,
        len(para_gravar),
        200,
    ):

        bloco = para_gravar[
            inicio:
            inicio + 200
        ]

        (
            supabase
            .table("reservations")
            .upsert(
                bloco,
                on_conflict=(
                    "listing,"
                    "confirmation_code"
                ),
            )
            .execute()
        )

    return {
        "novos": len(novos),
        "alterados": len(alterados),
        "iguais": len(iguais),
    }


# =========================================================
# CARREGAR RESERVAS
# =========================================================

def carregar_reservas():

    registos = ler_tabela(
        "reservations",
        (
            "listing,"
            "confirmation_code,"
            "status,"
            "start_date,"
            "end_date,"
            "nights,"
            "adults,"
            "children,"
            "infants,"
            "earnings_cents"
        ),
    )

    if not registos:
        return pd.DataFrame()

    base = pd.DataFrame(
        registos
    )

    base["Listing"] = (
        base["listing"]
    )

    base["Confirmation code"] = (
        base["confirmation_code"]
    )

    base["Status"] = (
        base["status"]
    )

    base["Entrada"] = pd.to_datetime(
        base["start_date"]
    )

    base["Saída"] = pd.to_datetime(
        base["end_date"]
    )

    base["Noites"] = pd.to_numeric(
        base["nights"]
    ).astype(int)

    base["Adultos"] = pd.to_numeric(
        base["adults"]
    ).fillna(0).astype(int)

    base["Crianças"] = pd.to_numeric(
        base["children"]
    ).fillna(0).astype(int)

    base["Bebés"] = pd.to_numeric(
        base["infants"]
    ).fillna(0).astype(int)

    base["Total hóspedes"] = (
        base["Adultos"]
        + base["Crianças"]
        + base["Bebés"]
    )

    base["Cêntimos"] = pd.to_numeric(
        base["earnings_cents"]
    ).astype(int)

    base["Valor bruto"] = (
        base["Cêntimos"]
        / 100
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
# AJUSTES MANUAIS TAXA TURISTICA
# =========================================================

def carregar_ajustes(
    listing,
    ano,
):

    resposta = (
        supabase
        .table(
            "tourist_tax_monthly"
        )
        .select(
            "tax_month,"
            "manual_tax_cents,"
            "notes"
        )
        .eq(
            "listing",
            listing,
        )
        .eq(
            "tax_year",
            int(ano),
        )
        .execute()
    )

    return {
        int(registo["tax_month"]): {
            "valor": (
                int(
                    registo[
                        "manual_tax_cents"
                    ]
                )
                / 100
            ),
            "notes": (
                registo.get(
                    "notes"
                )
                or ""
            ),
        }
        for registo
        in (
            resposta.data
            or []
        )
    }


# =========================================================
# GUARDAR AJUSTES MANUAIS
# =========================================================

def guardar_ajustes(
    listing,
    ano,
    editor,
):

    agora = datetime.now(
        ZoneInfo("Europe/Lisbon")
    ).isoformat()

    for indice, linha in (
        editor.iterrows()
    ):

        mes = indice + 1

        valor = linha[
            "Ajuste manual (€)"
        ]

        if pd.isna(valor):

            (
                supabase
                .table(
                    "tourist_tax_monthly"
                )
                .delete()
                .eq(
                    "listing",
                    listing,
                )
                .eq(
                    "tax_year",
                    int(ano),
                )
                .eq(
                    "tax_month",
                    mes,
                )
                .execute()
            )

        else:

            (
                supabase
                .table(
                    "tourist_tax_monthly"
                )
                .upsert(
                    {
                        "listing": listing,
                        "tax_year": int(ano),
                        "tax_month": mes,
                        "manual_tax_cents": int(
                            round(
                                float(valor)
                                * 100
                            )
                        ),
                        "notes": str(
                            linha.get(
                                "Notas",
                                "",
                            )
                            or ""
                        ),
                        "updated_at": agora,
                    },
                    on_conflict=(
                        "listing,"
                        "tax_year,"
                        "tax_month"
                    ),
                )
                .execute()
            )


# =========================================================
# REGRA AUTOMATICA DA TAXA
# =========================================================

def data_tem_taxa(
    data,
):

    # Antes de abril de 2026:
    # zero no nosso modelo.
    if data < INICIO_TAXA:
        return False

    return (
        4
        <= data.month
        <= 10
    )


# =========================================================
# CRIAR GRAO DIARIO
# =========================================================

def criar_noites(
    reservas,
):

    linhas = []

    for _, reserva in (
        reservas.iterrows()
    ):

        datas = pd.date_range(
            reserva["Entrada"],
            reserva["Saída"],
            inclusive="left",
        )

        if len(datas) == 0:
            continue

        total_centimos = int(
            reserva["Cêntimos"]
        )

        sinal = (
            -1
            if total_centimos < 0
            else 1
        )

        base_centimos, resto = divmod(
            abs(total_centimos),
            len(datas),
        )

        hospedes = int(
            reserva[
                "Total hóspedes"
            ]
        )

        noites_taxadas = 0

        for posicao, data in (
            enumerate(datas)
        ):

            valor_bruto = (
                (
                    base_centimos
                    + int(
                        posicao < resto
                    )
                )
                * sinal
                / 100
            )

            elegivel = (
                data_tem_taxa(
                    data
                )
                and noites_taxadas
                < MAXIMO_NOITES_TAXADAS_POR_RESERVA
            )

            if elegivel:

                taxa_automatica = (
                    hospedes
                    * VALOR_TAXA_POR_PESSOA_NOITE
                )

                noites_taxadas += 1

            else:

                taxa_automatica = 0.0

            linhas.append({
                "Listing": (
                    reserva["Listing"]
                ),
                "Reserva": (
                    reserva[
                        "Confirmation code"
                    ]
                ),
                "Data": data,
                "Valor bruto": (
                    valor_bruto
                ),
                "Taxa automática": (
                    taxa_automatica
                ),
                "Duração reserva": (
                    len(datas)
                ),
                "Hóspedes": hospedes,
            })

    return pd.DataFrame(
        linhas
    )


# =========================================================
# APLICAR TAXA FINAL
# =========================================================

def aplicar_taxa_mensal(
    noites,
    ano,
    ajustes,
):

    resultado = noites.copy()

    resultado[
        "Taxa final"
    ] = 0.0

    resultado[
        "Origem taxa"
    ] = "Não aplicável"

    # 2025 e anos anteriores:
    # nunca têm taxa.
    if int(ano) < 2026:

        resultado[
            "Valor líquido"
        ] = resultado[
            "Valor bruto"
        ]

        return resultado

    for mes in range(
        1,
        13,
    ):

        mascara = (
            (
                resultado["Data"]
                .dt.year
                == int(ano)
            )
            &
            (
                resultado["Data"]
                .dt.month
                == mes
            )
        )

        quantidade_noites = int(
            mascara.sum()
        )

        if quantidade_noites == 0:
            continue

        valor_automatico = float(
            resultado.loc[
                mascara,
                "Taxa automática",
            ].sum()
        )

        if mes in ajustes:

            taxa_final = float(
                ajustes[mes][
                    "valor"
                ]
            )

            origem = "Manual"

        else:

            taxa_final = (
                valor_automatico
            )

            origem = (
                "Automático"
                if valor_automatico > 0
                else "Não aplicável"
            )

        # Distribuímos o ajuste mensal pelas
        # noites apenas para que os totais,
        # realizado/futuro e médias fechem.
        centimos_taxa = int(
            round(
                taxa_final
                * 100
            )
        )

        base_centimos, resto = (
            divmod(
                centimos_taxa,
                quantidade_noites,
            )
        )

        valores_distribuidos = [
            (
                base_centimos
                + int(
                    indice < resto
                )
            )
            / 100
            for indice
            in range(
                quantidade_noites
            )
        ]

        resultado.loc[
            mascara,
            "Taxa final",
        ] = valores_distribuidos

        resultado.loc[
            mascara,
            "Origem taxa",
        ] = origem

    resultado[
        "Valor líquido"
    ] = (
        resultado[
            "Valor bruto"
        ]
        - resultado[
            "Taxa final"
        ]
    )

    return resultado


# =========================================================
# RESUMO MENSAL
# =========================================================

def resumo_mensal(
    noites,
    ano,
    ajustes,
):

    ano_noites = noites[
        noites["Data"]
        .dt.year
        == int(ano)
    ].copy()

    ano_noites = aplicar_taxa_mensal(
        ano_noites,
        ano,
        ajustes,
    )

    linhas = []

    for mes in range(
        1,
        13,
    ):

        periodo = ano_noites[
            ano_noites["Data"]
            .dt.month
            == mes
        ]

        dias_mes = calendar.monthrange(
            int(ano),
            mes,
        )[1]

        realizadas = periodo[
            periodo["Data"]
            < HOJE
        ]

        futuras = periodo[
            periodo["Data"]
            >= HOJE
        ]

        valor_bruto = (
            periodo[
                "Valor bruto"
            ].sum()
        )

        taxa_automatica = (
            periodo[
                "Taxa automática"
            ].sum()
        )

        taxa_utilizada = (
            periodo[
                "Taxa final"
            ].sum()
        )

        valor_liquido = (
            periodo[
                "Valor líquido"
            ].sum()
        )

        noites_mes = len(
            periodo
        )

        reservas_mes = (
            periodo[
                "Reserva"
            ]
            .nunique()
        )

        if noites_mes:

            origem = (
                periodo[
                    "Origem taxa"
                ]
                .iloc[0]
            )

        elif (
            int(ano) < 2026
            or mes < 4
            or mes > 10
        ):

            origem = (
                "Não aplicável"
            )

        elif mes in ajustes:

            origem = "Manual"

        else:

            origem = "Automático"

        linhas.append({

            "Mês": (
                MESES[
                    mes - 1
                ]
            ),

            "Earnings bruto (€)": (
                valor_bruto
            ),

            "Taxa automática (€)": (
                taxa_automatica
            ),

            "Ajuste manual (€)": (
                ajustes
                .get(
                    mes,
                    {},
                )
                .get(
                    "valor",
                    None,
                )
            ),

            "Taxa utilizada (€)": (
                taxa_utilizada
            ),

            "Origem": origem,

            "Realizado líquido (€)": (
                realizadas[
                    "Valor líquido"
                ].sum()
            ),

            "Futuro líquido (€)": (
                futuras[
                    "Valor líquido"
                ].sum()
            ),

            "Total líquido (€)": (
                valor_liquido
            ),

            "Reservas": (
                reservas_mes
            ),

            "Noites": (
                noites_mes
            ),

            "Dias do mês": (
                dias_mes
            ),

            "Ocupação (%)": (
                100
                * noites_mes
                / dias_mes
            ),

            "Duração média": (
                periodo
                .drop_duplicates(
                    "Reserva"
                )[
                    "Duração reserva"
                ]
                .mean()
            ),

            "Média líquida/noite (€)": (
                valor_liquido
                / noites_mes
                if noites_mes
                else None
            ),

            "Valor líquido/dia calendário (€)": (
                valor_liquido
                / dias_mes
            ),
        })

    return (
        pd.DataFrame(
            linhas
        ),
        ano_noites,
    )


# =========================================================
# CABEÇALHO
# =========================================================

st.title(
    "🏠 Airbnb Dashboard"
)

st.caption(
    "Desempenho, taxa turística "
    "e planeamento de preços."
)


# =========================================================
# IMPORTAÇÃO
# =========================================================

with st.sidebar:

    st.header(
        "Dados"
    )

    ficheiros = st.file_uploader(
        "CSV de reservas Airbnb",
        type=[
            "csv",
        ],
        accept_multiple_files=True,
    )

    if (
        ficheiros
        and st.button(
            "Guardar ou atualizar reservas",
            type="primary",
            use_container_width=True,
        )
    ):

        try:

            lote = (
                preparar_lote_csv(
                    ficheiros
                )
            )

            resultado_importacao = (
                guardar_reservas(
                    lote
                )
            )

            st.session_state[
                "importacao"
            ] = (
                resultado_importacao
            )

            st.rerun()

        except Exception as erro:

            st.error(
                "Não foi possível "
                "importar os ficheiros."
            )

            st.code(
                str(erro)
            )


if (
    "importacao"
    in st.session_state
):

    resultado = (
        st.session_state
        .pop(
            "importacao"
        )
    )

    st.success(
        "Importação concluída: "
        f"{resultado['novos']} novas, "
        f"{resultado['alterados']} atualizadas "
        f"e {resultado['iguais']} iguais."
    )


# =========================================================
# CARREGAR DADOS
# =========================================================

try:

    dados = (
        carregar_reservas()
    )

except Exception as erro:

    st.error(
        "Não foi possível "
        "ler os dados."
    )

    st.code(
        str(erro)
    )

    st.stop()


if dados.empty:

    st.info(
        "Ainda não existem "
        "reservas guardadas."
    )

    st.stop()


# =========================================================
# FILTROS
# =========================================================

with st.sidebar:

    st.success(
        f"Reservas guardadas: "
        f"{len(dados)}"
    )

    alojamento = (
        st.selectbox(
            "Alojamento",
            sorted(
                dados[
                    "Listing"
                ].unique()
            ),
        )
    )


dados_alojamento = dados[
    dados["Listing"]
    == alojamento
].copy()


ativas = dados_alojamento[
    ~dados_alojamento[
        "Cancelada"
    ]
].copy()


canceladas = dados_alojamento[
    dados_alojamento[
        "Cancelada"
    ]
].copy()


if ativas.empty:

    st.warning(
        "Não existem reservas "
        "ativas para este alojamento."
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
        "Existem reservas "
        "sobrepostas neste alojamento."
    )

    st.stop()


with st.sidebar:

    ano = st.selectbox(
        "Ano",
        sorted(
            noites["Data"]
            .dt.year
            .unique(),
            reverse=True,
        ),
    )

    st.caption(
        f"Data de referência: "
        f"{HOJE:%d/%m/%Y}"
    )


# =========================================================
# TAXA / RESUMOS
# =========================================================

if int(ano) >= 2026:

    ajustes = (
        carregar_ajustes(
            alojamento,
            ano,
        )
    )

else:

    ajustes = {}


mensal, ano_noites = (
    resumo_mensal(
        noites,
        ano,
        ajustes,
    )
)


ano_anterior = (
    int(ano) - 1
)


if ano_anterior >= 2026:

    ajustes_anterior = (
        carregar_ajustes(
            alojamento,
            ano_anterior,
        )
    )

else:

    ajustes_anterior = {}


mensal_anterior, _ = (
    resumo_mensal(
        noites,
        ano_anterior,
        ajustes_anterior,
    )
)


st.info(
    "Os indicadores excluem a taxa turística "
    "utilizada. Em 2025 e anos anteriores, "
    "a taxa turística considerada é zero."
)


# =========================================================
# TABS
# =========================================================

(
    resumo,
    detalhe,
    impostos,
    precos,
    qualidade,
) = st.tabs(
    [
        "Resumo anual",
        "Análise mensal",
        "Taxa turística",
        "Planeamento de preços",
        "Dados e regras",
    ]
)


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

    total = mensal[
        "Total líquido (€)"
    ].sum()

    bruto = mensal[
        "Earnings bruto (€)"
    ].sum()

    taxa = mensal[
        "Taxa utilizada (€)"
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

    c1, c2, c3 = (
        st.columns(3)
    )

    c1.metric(
        "Realizado sem taxa",
        euros(
            realizado
        ),
    )

    c2.metric(
        "Reservas futuras sem taxa",
        euros(
            futuro
        ),
    )

    c3.metric(
        "Total líquido assegurado",
        euros(
            total
        ),
    )

    c1, c2, c3 = (
        st.columns(3)
    )

    c1.metric(
        "Noites reservadas",
        numero_noites,
    )

    c2.metric(
        "Ocupação anual",
        f"{numero_noites / dias_ano:.1%}",
    )

    c3.metric(
        "Média líquida/noite",
        (
            euros(
                total
                / numero_noites
            )
            if numero_noites
            else "—"
        ),
    )

    c1, c2 = (
        st.columns(2)
    )

    c1.metric(
        "Earnings bruto Airbnb",
        euros(
            bruto
        ),
    )

    c2.metric(
        "Taxa turística excluída",
        euros(
            taxa
        ),
    )


    # -------------------------
    # GRÁFICO REALIZADO/FUTURO
    # -------------------------

    distribuicao = (
        mensal.melt(
            id_vars="Mês",
            value_vars=[
                "Realizado líquido (€)",
                "Futuro líquido (€)",
            ],
            var_name="Tipo",
            value_name="Valor (€)",
        )
    )

    distribuicao[
        "Etiqueta"
    ] = (
        distribuicao[
            "Valor (€)"
        ].map(
            etiqueta_euros
        )
    )

    figura = px.bar(
        distribuicao,
        x="Mês",
        y="Valor (€)",
        color="Tipo",
        text="Etiqueta",
        barmode="stack",
        title=(
            f"{ano} · realizado "
            "e futuro sem taxa"
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


    # -------------------------
    # COMPARAÇÃO ANO ANTERIOR
    # -------------------------

    tem_ano_anterior = (
        noites["Data"]
        .dt.year
        .eq(
            int(ano) - 1
        )
        .any()
    )

    if tem_ano_anterior:

        comparacao = pd.concat(
            [
                mensal[
                    [
                        "Mês",
                        "Total líquido (€)",
                    ]
                ]
                .rename(
                    columns={
                        "Total líquido (€)":
                            "Valor (€)"
                    }
                )
                .assign(
                    Ano=str(
                        ano
                    )
                ),

                mensal_anterior[
                    [
                        "Mês",
                        "Total líquido (€)",
                    ]
                ]
                .rename(
                    columns={
                        "Total líquido (€)":
                            "Valor (€)"
                    }
                )
                .assign(
                    Ano=str(
                        int(ano)
                        - 1
                    )
                ),
            ],
            ignore_index=True,
        )

        comparacao[
            "Etiqueta"
        ] = (
            comparacao[
                "Valor (€)"
            ].map(
                etiqueta_euros
            )
        )

        figura_comparacao = (
            px.bar(
                comparacao,
                x="Mês",
                y="Valor (€)",
                color="Ano",
                text="Etiqueta",
                barmode="group",
                title=(
                    "Comparação "
                    "mensal líquida"
                ),
                category_orders={
                    "Mês": MESES
                },
                color_discrete_sequence=[
                    "#2563EB",
                    "#CBD5E1",
                ],
            )
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


# =========================================================
# ANÁLISE MENSAL
# =========================================================

with detalhe:

    st.subheader(
        f"Análise mensal líquida · {ano}"
    )

    colunas = [
        "Mês",
        "Earnings bruto (€)",
        "Taxa utilizada (€)",
        "Total líquido (€)",
        "Reservas",
        "Noites",
        "Dias do mês",
        "Ocupação (%)",
        "Duração média",
        "Média líquida/noite (€)",
        "Valor líquido/dia calendário (€)",
    ]

    st.dataframe(
        mensal[
            colunas
        ].round(2),
        hide_index=True,
        use_container_width=True,
    )


    figura_ocupacao = (
        px.bar(
            mensal,
            x="Mês",
            y="Ocupação (%)",
            title=(
                f"Ocupação mensal · {ano}"
            ),
            category_orders={
                "Mês": MESES
            },
            color_discrete_sequence=[
                "#2563EB"
            ],
        )
    )

    figura_ocupacao.update_traces(
        text=mensal[
            "Ocupação (%)"
        ].map(
            lambda valor: (
                f"{valor:.1f}%"
                if valor
                else ""
            )
        ),
        textposition="outside",
        cliponaxis=False,
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
        ).encode(
            "utf-8-sig"
        ),
        file_name=(
            f"resumo_{ano}.csv"
        ),
        mime="text/csv",
    )


# =========================================================
# TAXA TURÍSTICA
# =========================================================

with impostos:

    st.subheader(
        f"Taxa turística · {ano}"
    )


    if int(ano) < 2026:

        st.info(
            "A taxa turística não é "
            "aplicada no dashboard "
            "antes de 2026."
        )


    editor_base = mensal[
        [
            "Mês",
            "Taxa automática (€)",
            "Taxa utilizada (€)",
            "Origem",
        ]
    ].copy()


    editor_base[
        "Ajuste manual (€)"
    ] = [
        ajustes
        .get(
            mes,
            {},
        )
        .get(
            "valor",
            None,
        )
        for mes
        in range(
            1,
            13,
        )
    ]


    editor_base[
        "Notas"
    ] = [
        ajustes
        .get(
            mes,
            {},
        )
        .get(
            "notes",
            "",
        )
        for mes
        in range(
            1,
            13,
        )
    ]


    editor = st.data_editor(
        editor_base[
            [
                "Mês",
                "Taxa automática (€)",
                "Ajuste manual (€)",
                "Taxa utilizada (€)",
                "Origem",
                "Notas",
            ]
        ],
        disabled=[
            "Mês",
            "Taxa automática (€)",
            "Taxa utilizada (€)",
            "Origem",
        ],
        hide_index=True,
        use_container_width=True,
        key=(
            f"taxa_"
            f"{alojamento}_"
            f"{ano}"
        ),
        column_config={
            "Ajuste manual (€)":
                st.column_config.NumberColumn(
                    min_value=0.0,
                    step=1.0,
                    format="%.2f",
                )
        },
    )


    if (
        int(ano) >= 2026
        and st.button(
            "Guardar ajustes mensais",
            type="primary",
        )
    ):

        try:

            guardar_ajustes(
                alojamento,
                ano,
                editor,
            )

            st.success(
                "Ajustes guardados."
            )

            st.rerun()

        except Exception as erro:

            st.error(
                "Não foi possível "
                "guardar os ajustes."
            )

            st.code(
                str(erro)
            )


    st.metric(
        "Taxa utilizada no ano",
        euros(
            mensal[
                "Taxa utilizada (€)"
            ].sum()
        ),
    )


    mapa = mensal[
        [
            "Mês",
            "Taxa automática (€)",
            "Ajuste manual (€)",
            "Taxa utilizada (€)",
            "Origem",
        ]
    ].copy()


    mapa[
        "Etiqueta"
    ] = (
        mapa[
            "Taxa utilizada (€)"
        ].map(
            etiqueta_euros
        )
    )


    figura_taxa = px.bar(
        mapa,
        x="Mês",
        y="Taxa utilizada (€)",
        text="Etiqueta",
        color="Origem",
        title=(
            f"Taxa mensal "
            f"utilizada · {ano}"
        ),
        category_orders={
            "Mês": MESES
        },
        color_discrete_map={
            "Manual":
                "#F59E0B",

            "Automático":
                "#60A5FA",

            "Não aplicável":
                "#CBD5E1",
        },
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


    st.caption(
        "Um valor manual substitui "
        "integralmente o cálculo automático "
        "desse mês. Se apagares o ajuste "
        "manual e guardares, o mês volta "
        "ao cálculo automático."
    )


# =========================================================
# PLANEAMENTO DE PREÇOS
# =========================================================

with precos:

    st.subheader(
        f"Planeamento · "
        f"{int(ano) + 1}"
    )


    base_plano = pd.DataFrame({

        "Mês":
            MESES,

        "Histórico líquido/noite (€)":
            mensal[
                "Média líquida/noite (€)"
            ].round(2),

        "Preço base (€)":
            [0.0] * 12,

        "Preço mínimo (€)":
            [0.0] * 12,

        "Ocupação objetivo (%)":
            [0.0] * 12,
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
            f"plano_"
            f"{alojamento}_"
            f"{ano}"
        ),
        column_config={
            "Preço base (€)":
                st.column_config.NumberColumn(
                    min_value=0.0,
                    step=1.0,
                    format="%.2f",
                ),

            "Preço mínimo (€)":
                st.column_config.NumberColumn(
                    min_value=0.0,
                    step=1.0,
                    format="%.2f",
                ),

            "Ocupação objetivo (%)":
                st.column_config.NumberColumn(
                    min_value=0.0,
                    max_value=100.0,
                    step=1.0,
                    format="%.1f",
                ),
        },
    )


    for coluna in [
        "Preço base (€)",
        "Preço mínimo (€)",
        "Ocupação objetivo (%)",
    ]:

        plano[coluna] = (
            pd.to_numeric(
                plano[coluna],
                errors="coerce",
            )
            .fillna(0.0)
        )


    st.subheader(
        "Preços após desconto"
    )


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
            plano[
                "Preço base (€)"
            ]
            * (
                1
                - desconto
                / 100
            )
        ).round(2)


    st.dataframe(
        cenarios,
        hide_index=True,
        use_container_width=True,
    )


    desconto = st.selectbox(
        "Desconto para a simulação",
        [
            0,
            5,
            7,
            10,
            15,
            20,
        ],
        format_func=(
            lambda valor:
                f"{valor}%"
        ),
    )


    precos_finais = (
        plano[
            "Preço base (€)"
        ]
        * (
            1
            - desconto
            / 100
        )
    )


    dias_proximo_ano = (
        pd.Series(
            [
                calendar.monthrange(
                    int(ano) + 1,
                    mes,
                )[1]
                for mes
                in range(
                    1,
                    13,
                )
            ],
            index=plano.index,
        )
    )


    noites_estimadas = (
        dias_proximo_ano
        * plano[
            "Ocupação objetivo (%)"
        ]
        / 100
    )


    receita_simulada = (
        precos_finais
        * noites_estimadas
    )


    st.metric(
        "Receita líquida "
        "simulada anual",
        euros(
            receita_simulada.sum()
        ),
    )


    simulacao = pd.DataFrame({

        "Mês":
            plano["Mês"],

        "Preço após desconto (€)":
            precos_finais.round(2),

        "Noites estimadas":
            noites_estimadas.round(1),

        "Receita líquida simulada (€)":
            receita_simulada.round(2),
    })


    st.dataframe(
        simulacao,
        hide_index=True,
        use_container_width=True,
    )


# =========================================================
# DADOS E REGRAS
# =========================================================

with qualidade:

    st.subheader(
        "Estado dos dados"
    )


    c1, c2, c3 = (
        st.columns(3)
    )


    c1.metric(
        "Reservas guardadas",
        len(dados),
    )


    c2.metric(
        "Reservas neste alojamento",
        len(
            dados_alojamento
        ),
    )


    c3.metric(
        "Alojamentos",
        dados[
            "Listing"
        ].nunique(),
    )


    st.subheader(
        "Regras aplicadas"
    )


    st.markdown(
        """
- Chave única: `Listing + Confirmation code`.
- Reservas canceladas não entram na receita nem na taxa turística.
- Antes de 2026, a taxa turística considerada é 0 €.
- A partir de 1 de abril de 2026, o cálculo automático usa 2 € por hóspede/noite.
- O cálculo automático usa no máximo 7 noites tributáveis por reserva.
- O período automático termina em 31 de outubro.
- Um ajuste manual mensal substitui integralmente o cálculo automático desse mês.
- `Earnings bruto` é sempre preservado.
- Receita, realizado, futuro e médias usam o valor após retirada da taxa turística.
- Os ajustes mensais são guardados separadamente no Supabase.
- Nomes e contactos dos hóspedes não são guardados.
        """
    )


    st.subheader(
        "Cancelamentos"
    )


    st.metric(
        "Earnings bruto "
        "em cancelamentos",
        euros(
            canceladas[
                "Valor bruto"
            ].sum()
        ),
    )


    st.caption(
        "Cancelamentos são apresentados "
        "separadamente e não entram nos "
        "indicadores normais de desempenho."
    )