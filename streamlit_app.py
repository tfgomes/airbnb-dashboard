import calendar
from datetime import datetime
from zoneinfo import ZoneInfo
from supabase import create_client

import pandas as pd
import plotly.express as px
import streamlit as st


st.set_page_config(
    page_title="Airbnb Dashboard",
    page_icon="🏠",
    layout="wide",
)

# Testar a ligação à base de dados.
try:
    supabase = create_client(
        st.secrets["supabase"]["url"],
        st.secrets["supabase"]["key"],
    )

    resultado = (
        supabase.table("reservations")
        .select("confirmation_code", count="exact")
        .limit(1)
        .execute()
    )

    st.success(
        f"Ligação ao Supabase confirmada. "
        f"Reservas guardadas: {resultado.count}"
    )

except Exception:
    st.error(
        "Não foi possível ligar ao Supabase. "
        "Verifica os Secrets e as permissões da tabela."
    )
    st.stop()

MESES = [
    "Janeiro", "Fevereiro", "Março", "Abril",
    "Maio", "Junho", "Julho", "Agosto",
    "Setembro", "Outubro", "Novembro", "Dezembro",
]

HOJE = pd.Timestamp(datetime.now(ZoneInfo("Europe/Lisbon")).date())

ESTADOS_VALIDOS = {
    "Confirmed",
    "Past guest",
    "Review guest",
    "Review guest - Expires soon",
}


def euros(valor):
    texto = f"{valor:,.2f}"
    return texto.replace(",", "X").replace(".", ",").replace("X", ".") + " €"


def preparar_csv(ficheiro):
    dados = pd.read_csv(
        ficheiro,
        dtype=str,
        encoding="utf-8-sig",
        skipinitialspace=True,
    )
    dados.columns = dados.columns.str.strip()

    obrigatorias = [
        "Confirmation code", "Status", "Start date",
        "End date", "# of nights", "Earnings", "Listing",
    ]
    em_falta = [c for c in obrigatorias if c not in dados.columns]

    if em_falta:
        raise ValueError("Colunas em falta: " + ", ".join(em_falta))

    # Apenas estes campos entram na análise.
    dados = dados[obrigatorias].copy()

    for coluna in dados.columns:
        dados[coluna] = dados[coluna].str.strip()

    if dados["Confirmation code"].fillna("").eq("").any():
        raise ValueError("Existem reservas sem código de confirmação.")

    # Duplicados iguais são removidos; versões diferentes exigem revisão.
    dados = dados.drop_duplicates()

    if dados["Confirmation code"].duplicated().any():
        raise ValueError(
            "Existem versões diferentes da mesma reserva no ficheiro."
        )

    dados["Entrada"] = pd.to_datetime(
        dados["Start date"], format="%m/%d/%Y", errors="coerce"
    )
    dados["Saída"] = pd.to_datetime(
        dados["End date"], format="%m/%d/%Y", errors="coerce"
    )
    dados["Noites"] = pd.to_numeric(
        dados["# of nights"], errors="coerce"
    )

    # Formato do CSV enviado: €1,494.51
    montantes = (
        dados["Earnings"]
        .str.replace("€", "", regex=False)
        .str.replace(",", "", regex=False)
        .str.strip()
    )

    formato_valido = montantes.str.fullmatch(
        r"-?\d+(?:\.\d{1,2})?", na=False
    )
    if not formato_valido.all():
        raise ValueError(
            "Existem valores Earnings num formato diferente do esperado."
        )

    def para_centimos(texto):
        negativo = texto.startswith("-")
        partes = texto.lstrip("-").split(".")
        inteiro = int(partes[0])
        decimal = int(partes[1].ljust(2, "0")) if len(partes) == 2 else 0
        return (-1 if negativo else 1) * (inteiro * 100 + decimal)

    dados["Cêntimos"] = montantes.map(para_centimos)
    dados["Valor"] = dados["Cêntimos"] / 100

    noites_calculadas = (dados["Saída"] - dados["Entrada"]).dt.days

    invalidas = (
        dados["Entrada"].isna()
        | dados["Saída"].isna()
        | dados["Noites"].isna()
        | noites_calculadas.le(0)
        | dados["Noites"].ne(noites_calculadas)
        | dados["Listing"].fillna("").eq("")
    )

    if invalidas.any():
        raise ValueError(
            f"Existem {int(invalidas.sum())} reservas com datas, "
            "alojamento ou número de noites inválidos."
        )

    dados["Cancelada"] = dados["Status"].str.contains(
        r"cancel", case=False, na=False
    )

    desconhecidos = dados.loc[
        ~dados["Cancelada"] & ~dados["Status"].isin(ESTADOS_VALIDOS),
        "Status",
    ].unique()

    if len(desconhecidos):
        raise ValueError(
            "Estados ainda não classificados: "
            + ", ".join(desconhecidos)
        )

    return dados


def criar_noites(reservas):
    linhas = []

    for _, reserva in reservas.iterrows():
        datas = pd.date_range(
            reserva["Entrada"],
            reserva["Saída"],
            inclusive="left",
        )

        # Repartição proporcional, preservando exatamente o total em cêntimos.
        base, resto = divmod(int(reserva["Cêntimos"]), len(datas))

        for posicao, data in enumerate(datas):
            linhas.append({
                "Reserva": reserva["Confirmation code"],
                "Data": data,
                "Valor": (base + int(posicao < resto)) / 100,
                "Média reserva/noite": reserva["Valor"] / len(datas),
                "Duração reserva": len(datas),
            })

    return pd.DataFrame(
        linhas,
        columns=[
            "Reserva", "Data", "Valor",
            "Média reserva/noite", "Duração reserva",
        ],
    )


def resumo_mensal(noites, ano):
    linhas = []

    for mes in range(1, 13):
        inicio = pd.Timestamp(year=ano, month=mes, day=1)
        fim = inicio + pd.offsets.MonthBegin(1)
        dias = calendar.monthrange(ano, mes)[1]

        periodo = noites[
            (noites["Data"] >= inicio) & (noites["Data"] < fim)
        ]
        realizadas = periodo[periodo["Data"] < HOJE]
        futuras = periodo[periodo["Data"] >= HOJE]
        reservas_mes = periodo.drop_duplicates("Reserva")

        total = periodo["Valor"].sum()
        n_noites = len(periodo)

        linhas.append({
            "Mês": MESES[mes - 1],
            "Realizado (€)": realizadas["Valor"].sum(),
            "Futuro (€)": futuras["Valor"].sum(),
            "Total (€)": total,
            "Reservas com noites no mês": len(reservas_mes),
            "Noites": n_noites,
            "Dias do mês": dias,
            "Ocupação calendário (%)": 100 * n_noites / dias,
            "Duração média reserva": reservas_mes["Duração reserva"].mean(),
            "Mín. média/noite (€)": periodo["Média reserva/noite"].min(),
            "Máx. média/noite (€)": periodo["Média reserva/noite"].max(),
            "Média/noite (€)": total / n_noites if n_noites else None,
            "Valor/dia calendário (€)": total / dias,
        })

    return pd.DataFrame(linhas)


st.title("🏠 Airbnb Dashboard")
st.caption("Desempenho anual, análise mensal e planeamento de preços.")

with st.sidebar:
    st.header("Dados")
    ficheiro = st.file_uploader("CSV de reservas Airbnb", type=["csv"])
    st.caption(
        "Nesta versão, o ficheiro não é guardado numa base de dados. "
        "Uma nova sessão pode exigir novo upload."
    )

if ficheiro is None:
    st.info("Carrega o CSV na barra lateral para começar.")
    st.stop()

try:
    dados = preparar_csv(ficheiro)
except Exception as erro:
    st.error(f"Não foi possível importar o ficheiro: {erro}")
    st.stop()

with st.sidebar:
    alojamento = st.selectbox(
        "Alojamento",
        sorted(dados["Listing"].unique()),
    )

dados = dados[dados["Listing"] == alojamento].copy()
canceladas = dados[dados["Cancelada"]].copy()
ativas = dados[~dados["Cancelada"]].copy()

if ativas.empty:
    st.warning("Não existem reservas não canceladas para analisar.")
    st.stop()

noites = criar_noites(ativas)

if noites["Data"].duplicated().any():
    st.error(
        "Existem reservas sobrepostas neste alojamento. "
        "Revê os dados antes de calcular ocupação."
    )
    st.stop()

anos = sorted(noites["Data"].dt.year.unique(), reverse=True)

with st.sidebar:
    ano = st.selectbox("Ano", anos)
    st.caption(f"Data de referência: {HOJE:%d/%m/%Y}")
    st.caption(
        f"Intervalo de noites no CSV: "
        f"{noites['Data'].min():%d/%m/%Y} a "
        f"{noites['Data'].max():%d/%m/%Y}"
    )

mensal = resumo_mensal(noites, int(ano))
anterior = resumo_mensal(noites, int(ano) - 1)
ano_noites = noites[noites["Data"].dt.year == ano]

st.warning(
    "Valores baseados em Earnings: não representam necessariamente "
    "faturação, tarifa anunciada ou lucro. Meses sem registos aparecem "
    "a zero, mas isso não comprova que o histórico esteja completo."
)

resumo, detalhe, precos, qualidade = st.tabs([
    "Resumo anual",
    "Análise mensal",
    "Planeamento de preços",
    "Dados e regras",
])

with resumo:
    realizado = mensal["Realizado (€)"].sum()
    futuro = mensal["Futuro (€)"].sum()
    total = realizado + futuro
    n_noites = len(ano_noites)
    dias_ano = 366 if calendar.isleap(int(ano)) else 365

    c1, c2, c3 = st.columns(3)
    c1.metric("Realizado · noites decorridas", euros(realizado))
    c2.metric("Reservas futuras", euros(futuro))
    c3.metric("Total anual assegurado*", euros(total))

    c1, c2, c3 = st.columns(3)
    c1.metric("Noites reservadas", n_noites)
    c2.metric("Ocupação do calendário anual", f"{n_noites / dias_ano:.1%}")
    c3.metric(
        "Earnings médio / noite",
        euros(total / n_noites) if n_noites else "—",
    )

    st.caption(
        "*Inclui reservas futuras sujeitas a alteração/cancelamento. "
        "Não inclui previsão para noites ainda livres."
    )

    distribuicao = mensal.melt(
        id_vars="Mês",
        value_vars=["Realizado (€)", "Futuro (€)"],
        var_name="Tipo",
        value_name="Valor (€)",
    )
    fig = px.bar(
        distribuicao,
        x="Mês",
        y="Valor (€)",
        color="Tipo",
        barmode="stack",
        title=f"{ano} · realizado e reservas futuras",
        category_orders={"Mês": MESES},
        color_discrete_sequence=["#2563EB", "#93C5FD"],
    )
    st.plotly_chart(fig, width="stretch")

    tem_anterior = (noites["Data"].dt.year == ano - 1).any()

    if tem_anterior:
        comparacao = pd.concat([
            mensal[["Mês", "Total (€)"]].assign(Ano=str(ano)),
            anterior[["Mês", "Total (€)"]].assign(Ano=str(ano - 1)),
        ])
        fig = px.bar(
            comparacao,
            x="Mês",
            y="Total (€)",
            color="Ano",
            barmode="group",
            title="Comparação mensal · ano selecionado vs. anterior",
            category_orders={"Mês": MESES},
            color_discrete_sequence=["#2563EB", "#CBD5E1"],
        )
        st.plotly_chart(fig, width="stretch")

        anual = pd.DataFrame({
            "Ano": [str(ano - 1), str(ano)],
            "Valor (€)": [
                anterior["Total (€)"].sum(),
                mensal["Total (€)"].sum(),
            ],
        })
        st.plotly_chart(
            px.bar(
                anual,
                x="Ano",
                y="Valor (€)",
                title="Total anual presente no CSV",
            ),
            width="stretch",
        )
        st.caption(
            "Comparação do total disponível no ficheiro, incluindo futuro. "
            "Não é uma comparação à mesma antecedência."
        )
    else:
        st.info(
            "Importa um CSV que também inclua o ano anterior "
            "para ativar as comparações."
        )

with detalhe:
    st.subheader(f"Análise mensal · {ano}")

    st.dataframe(
        mensal.round(2),
        hide_index=True,
        width="stretch",
    )

    st.caption(
        "Uma reserva que atravessa meses conta em cada mês com noites. "
        "Por isso, a soma das reservas mensais não é o total anual único. "
        "Mínimo/máximo são médias por noite das reservas, não tarifas diárias."
    )

    st.download_button(
        "Descarregar resumo mensal",
        mensal.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"),
        file_name=f"resumo_{ano}.csv",
        mime="text/csv",
    )
with precos:
    st.subheader(f"Planeamento · {ano + 1}")

    st.caption(
        "Simulador manual de preços por noite. "
        "O histórico Earnings/noite é apenas uma referência, "
        "não uma tarifa anunciada comparável."
    )

    base = pd.DataFrame({
        "Mês": MESES,
        "Histórico Earnings/noite (€)": (
            mensal["Média/noite (€)"].round(2)
        ),
        "Preço base (€)": [0.0] * 12,
        "Preço mínimo (€)": [0.0] * 12,
        "Ocupação objetivo (%)": [0.0] * 12,
    })

    plano = st.data_editor(
        base,
        disabled=[
            "Mês",
            "Histórico Earnings/noite (€)",
        ],
        hide_index=True,
        width="stretch",
        key=f"plano_{alojamento}_{ano}",
        column_config={
            "Preço base (€)": st.column_config.NumberColumn(
                min_value=0.0,
                step=1.0,
                format="%.2f",
            ),
            "Preço mínimo (€)": st.column_config.NumberColumn(
                min_value=0.0,
                step=1.0,
                format="%.2f",
            ),
            "Ocupação objetivo (%)": st.column_config.NumberColumn(
                min_value=0.0,
                max_value=100.0,
                step=1.0,
                format="%.1f",
            ),
        },
    )

    # Tratar células apagadas como zero.
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

    for desconto in [5, 7, 10, 15, 20]:
        cenarios[f"−{desconto}% (€)"] = (
            plano["Preço base (€)"]
            * (1 - desconto / 100)
        ).round(2)

    st.dataframe(
        cenarios,
        hide_index=True,
        width="stretch",
    )

    st.subheader("Simulação de receita")

    desconto = st.selectbox(
        "Desconto para a simulação",
        options=[0, 5, 7, 10, 15, 20],
        format_func=lambda valor: f"{valor}%",
    )

    finais = (
        plano["Preço base (€)"]
        * (1 - desconto / 100)
    ).round(2)

    dias = pd.Series(
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
        dias
        * plano["Ocupação objetivo (%)"]
        / 100
    )

    receita = finais * noites_estimadas

    simulacao = pd.DataFrame({
        "Mês": plano["Mês"],
        "Dias do mês": dias,
        "Preço após desconto (€)": finais,
        "Ocupação objetivo (%)": plano["Ocupação objetivo (%)"],
        "Noites estimadas": noites_estimadas.round(1),
        "Receita bruta simulada (€)": receita.round(2),
    })

    st.metric(
        "Receita bruta simulada anual",
        euros(receita.sum()),
    )

    st.caption(
        "Preço após desconto × dias do mês × ocupação objetivo. "
        "Sem dedução de comissões, despesas ou impostos. "
        "Os descontos são alternativos, não acumulados. "
        "Esta simulação não desconta bloqueios pessoais."
    )

    st.dataframe(
        simulacao,
        hide_index=True,
        width="stretch",
    )

    abaixo = plano.loc[
        finais < plano["Preço mínimo (€)"],
        "Mês",
    ].tolist()

    if abaixo:
        st.warning(
            "Preço abaixo do mínimo em: "
            + ", ".join(abaixo)
        )

    exportacao = plano.merge(
        cenarios,
        on=["Mês", "Preço base (€)"],
        how="left",
        validate="one_to_one",
    )

    st.download_button(
        label="Descarregar plano e descontos",
        data=exportacao.to_csv(
            index=False,
            sep=";",
            decimal=",",
        ).encode("utf-8-sig"),
        file_name=f"plano_precos_{ano + 1}.csv",
        mime="text/csv",
    )

    st.info(
        "O plano ainda não é guardado entre sessões. "
        "Descarrega o CSV para conservar as alterações."
    )


with qualidade:
    st.subheader("Regras de cálculo")

    st.markdown(
        """
        - Noites anteriores à data de referência: realizado.
        - A noite de hoje e seguintes: futuro.
        - O dia do check-out não conta como noite.
        - Earnings repartido proporcionalmente pelas noites.
        - Ocupação calculada sobre todos os dias do calendário.
        - Bloqueios pessoais ainda não são descontados.
        - Cancelamentos não contam como noites nem como receita de estadias.
        - Nomes e contactos não entram na tabela analítica.
        """
    )

    st.write(
        "Reservas únicas não canceladas com noites no ano:",
        ano_noites["Reserva"].nunique(),
    )

    st.subheader("Cancelamentos · todo o ficheiro")

    st.metric(
        "Earnings em cancelamentos · separado",
        euros(canceladas["Valor"].sum()),
    )

    st.caption(
        "Não incluído nos totais de estadias. "
        "O CSV não fornece uma data financeira que permita "
        "atribuir estes valores com segurança "
        "a um mês de recebimento."
    )

    if not canceladas.empty:
        st.dataframe(
            canceladas[
                [
                    "Status",
                    "Entrada",
                    "Saída",
                    "Valor",
                ]
            ],
            hide_index=True,
            width="stretch",
        )