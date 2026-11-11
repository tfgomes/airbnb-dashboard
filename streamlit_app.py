import html
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from supabase import create_client

import core
from core import (
    MESES,
    MESES_CURTOS,
    euros,
    etiqueta_euros,
    percentagem,
    texto_variacao,
    variacao,
)


# =========================================================
# CONFIGURAÇÃO
# =========================================================

st.set_page_config(
    page_title="Painel de Alojamentos",
    page_icon="🏠",
    layout="wide",
)

HOJE = pd.Timestamp(datetime.now(ZoneInfo("Europe/Lisbon")).date())

PROPRIETARIOS = ["Tiago", "Guilhermino"]
TODOS = "Todos"
TODOS_ALOJAMENTOS = "Todos os alojamentos"

COR_PRINCIPAL = "#E61E4D"
COR_FUTURO = "#FFB8C6"
COR_ANTERIOR = "#92174D"
COR_NEUTRA = "#DDDDDD"
COR_TEXTO = "#222222"
COR_SUAVE = "#6A6A6A"
COR_GRELHA = "#EBEBEB"

COLUNAS_RESERVAS = (
    "listing,confirmation_code,status,start_date,end_date,"
    "nights,adults,children,infants,earnings_cents"
)

SQL_CONFIGURACAO = """-- Correr uma vez no Supabase: SQL Editor > New query > Run

create table if not exists public.properties (
    listing text primary key,
    display_name text,
    owner text,
    updated_at timestamptz not null default now()
);

create table if not exists public.monthly_adjustments (
    listing text not null,
    adj_year integer not null,
    adj_month integer not null check (adj_month between 1 and 12),
    refund_cents bigint not null default 0 check (refund_cents >= 0),
    notes text,
    updated_at timestamptz not null default now(),
    primary key (listing, adj_year, adj_month)
);

alter table public.properties enable row level security;
alter table public.monthly_adjustments enable row level security;

grant select, insert, update, delete on public.properties to service_role;
grant select, insert, update, delete on public.monthly_adjustments to service_role;
"""


# =========================================================
# ESTILO
# =========================================================

ESTILO = """
<style>
html, body, [class*="css"], .stMarkdown, .stApp {
    font-family: "Inter", "Helvetica Neue", Helvetica, Arial, sans-serif;
}
.block-container { padding-top: 2.2rem; padding-bottom: 4rem; max-width: 1280px; }
section[data-testid="stSidebar"] { background: #FAFAFA; border-right: 1px solid #EBEBEB; }
.ad-marca { font-size: 1.15rem; font-weight: 700; color: #E61E4D; letter-spacing: -0.01em; margin-bottom: 0.2rem; }
.ad-marca-nota { font-size: 0.78rem; color: #6A6A6A; margin-bottom: 1rem; }
.ad-titulo { font-size: 2rem; font-weight: 700; letter-spacing: -0.02em; color: #222222; line-height: 1.15; margin: 0; }
.ad-subtitulo { font-size: 0.95rem; color: #6A6A6A; margin: 0.35rem 0 1.2rem 0; }
.ad-seccao { font-size: 1.25rem; font-weight: 650; color: #222222; letter-spacing: -0.01em; margin: 1.8rem 0 0.2rem 0; }
.ad-seccao-nota { font-size: 0.86rem; color: #6A6A6A; margin: 0 0 0.8rem 0; }
.ad-grelha { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 14px; margin: 0.6rem 0 0.4rem 0; }
.ad-cartao { background: #FFFFFF; border: 1px solid #EBEBEB; border-radius: 18px; padding: 18px 20px; box-shadow: 0 1px 2px rgba(0,0,0,0.04); }
.ad-cartao.destaque { background: linear-gradient(135deg, #E61E4D 0%, #D70466 60%, #92174D 100%); border: none; }
.ad-cartao.destaque .ad-rotulo, .ad-cartao.destaque .ad-nota { color: rgba(255,255,255,0.85); }
.ad-cartao.destaque .ad-valor { color: #FFFFFF; }
.ad-cartao.destaque .ad-sobe, .ad-cartao.destaque .ad-desce { color: #FFFFFF; }
.ad-rotulo { font-size: 0.8rem; color: #6A6A6A; margin-bottom: 6px; }
.ad-valor { font-size: 1.65rem; font-weight: 700; color: #222222; letter-spacing: -0.02em; line-height: 1.15; font-variant-numeric: tabular-nums; }
.ad-nota { font-size: 0.8rem; color: #6A6A6A; margin-top: 6px; }
.ad-sobe { color: #008A05; font-weight: 600; }
.ad-desce { color: #C13515; font-weight: 600; }
.ad-linha { display: flex; align-items: center; gap: 14px; padding: 14px 0; border-bottom: 1px solid #EBEBEB; }
.ad-linha:last-child { border-bottom: none; }
.ad-linha-nome { flex: 0 0 34%; min-width: 0; }
.ad-linha-nome b { display: block; font-size: 0.95rem; color: #222222; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.ad-linha-nome span { font-size: 0.78rem; color: #6A6A6A; }
.ad-linha-barra { flex: 1 1 auto; height: 6px; background: #F0F0F0; border-radius: 999px; overflow: hidden; }
.ad-linha-barra i { display: block; height: 100%; border-radius: 999px; background: linear-gradient(90deg, #E61E4D, #D70466); }
.ad-linha-valor { flex: 0 0 auto; text-align: right; font-variant-numeric: tabular-nums; }
.ad-linha-valor b { display: block; font-size: 0.95rem; color: #222222; }
.ad-linha-valor span { font-size: 0.78rem; color: #6A6A6A; }
.ad-progresso { height: 8px; background: #F0F0F0; border-radius: 999px; overflow: hidden; margin-top: 10px; }
.ad-progresso i { display: block; height: 100%; border-radius: 999px; background: linear-gradient(90deg, #E61E4D, #D70466); }
.stTabs [data-baseweb="tab-list"] { gap: 6px; border-bottom: 1px solid #EBEBEB; }
.stTabs [data-baseweb="tab"] { font-weight: 600; padding: 10px 14px; }
div[data-testid="stDataFrame"], div[data-testid="stDataEditor"] { border-radius: 14px; }
</style>
"""

st.markdown(ESTILO, unsafe_allow_html=True)


def h(texto):
    return html.escape(str(texto))


def seccao(titulo, nota=None):
    bloco = f'<div class="ad-seccao">{h(titulo)}</div>'
    if nota:
        bloco += f'<div class="ad-seccao-nota">{h(nota)}</div>'
    st.markdown(bloco, unsafe_allow_html=True)


def cartoes(itens):
    """itens: lista de dicionários com rotulo, valor, nota (HTML já seguro) e destaque."""
    partes = []
    for item in itens:
        classe = "ad-cartao destaque" if item.get("destaque") else "ad-cartao"
        nota = item.get("nota") or ""
        partes.append(
            f'<div class="{classe}">'
            f'<div class="ad-rotulo">{h(item["rotulo"])}</div>'
            f'<div class="ad-valor">{h(item["valor"])}</div>'
            f'<div class="ad-nota">{nota}</div>'
            "</div>"
        )
    st.markdown(
        '<div class="ad-grelha">' + "".join(partes) + "</div>",
        unsafe_allow_html=True,
    )


def nota_variacao(valor, sufixo):
    """Texto colorido para uma variação percentual."""
    if valor is None or pd.isna(valor):
        return h(sufixo)
    classe = "ad-sobe" if valor >= 0 else "ad-desce"
    return f'<span class="{classe}">{h(texto_variacao(valor))}</span> {h(sufixo)}'


def barras_alojamentos(linhas):
    """linhas: lista de (nome, legenda, valor). Barras proporcionais ao total."""
    total = sum(max(valor, 0) for _, _, valor in linhas)
    partes = []
    for nome, legenda, valor in linhas:
        quota = 100 * max(valor, 0) / total if total else 0
        partes.append(
            '<div class="ad-linha">'
            f'<div class="ad-linha-nome"><b>{h(nome)}</b><span>{h(legenda)}</span></div>'
            f'<div class="ad-linha-barra"><i style="width:{quota:.1f}%"></i></div>'
            f'<div class="ad-linha-valor"><b>{h(euros(valor))}</b>'
            f"<span>{h(percentagem(quota))}</span></div>"
            "</div>"
        )
    st.markdown(
        '<div class="ad-cartao">' + "".join(partes) + "</div>",
        unsafe_allow_html=True,
    )


def estilo_grafico(figura, altura=380):
    figura.update_layout(
        height=altura,
        margin=dict(t=30, r=10, b=10, l=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(
            family="Inter, Helvetica Neue, Arial, sans-serif",
            color=COR_TEXTO,
            size=13,
        ),
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0,
            title_text="",
        ),
        hovermode="x unified",
        bargap=0.28,
        separators=",.",
    )
    figura.update_xaxes(showgrid=False, linecolor=COR_GRELHA, tickfont=dict(color=COR_SUAVE))
    figura.update_yaxes(
        gridcolor=COR_GRELHA, zeroline=False, tickfont=dict(color=COR_SUAVE),
    )
    return figura


def mostrar_grafico(figura):
    st.plotly_chart(
        figura, use_container_width=True, config={"displayModeBar": False},
    )


def tabela_formatada(tabela, formatos):
    """Aplica formatos PT a uma cópia da tabela, para mostrar."""
    visivel = tabela.copy()
    for coluna, formato in formatos.items():
        if coluna in visivel.columns:
            visivel[coluna] = visivel[coluna].map(formato)
    return visivel


def inteiro(valor):
    if valor is None or pd.isna(valor):
        return "—"
    return f"{float(valor):.0f}"


def decimal(valor):
    if valor is None or pd.isna(valor):
        return "—"
    return f"{float(valor):.1f}".replace(".", ",")


# =========================================================
# SUPABASE
# =========================================================

@st.cache_resource
def ligar_supabase():
    return create_client(
        st.secrets["supabase"]["url"],
        st.secrets["supabase"]["key"],
    )


try:
    supabase = ligar_supabase()
except Exception as erro:
    st.error("Não foi possível configurar a ligação ao Supabase.")
    st.code(str(erro))
    st.stop()


def ler_paginas(nome, colunas):
    todos = []
    inicio = 0
    tamanho_pagina = 1000

    while True:
        resposta = (
            supabase.table(nome)
            .select(colunas)
            .range(inicio, inicio + tamanho_pagina - 1)
            .execute()
        )
        bloco = resposta.data or []
        todos.extend(bloco)
        if len(bloco) < tamanho_pagina:
            return todos
        inicio += tamanho_pagina


@st.cache_data(ttl=300, show_spinner=False)
def ler_tabela(nome, colunas):
    return ler_paginas(nome, colunas)


@st.cache_data(ttl=300, show_spinner=False)
def ler_tabela_opcional(nome, colunas):
    """Devolve None quando a tabela ainda não existe (ou não pôde ser lida)."""
    try:
        return ler_paginas(nome, colunas)
    except Exception:
        return None


def limpar_cache():
    st.cache_data.clear()


def agora_iso():
    return datetime.now(ZoneInfo("Europe/Lisbon")).isoformat()


def guardar_reservas(dados):
    novos_registos = core.dataframe_para_registos(dados, agora_iso())
    existentes = ler_paginas("reservations", COLUNAS_RESERVAS)

    indice = {
        (registo["listing"], registo["confirmation_code"]): registo
        for registo in existentes
    }
    campos = [
        "status", "start_date", "end_date", "nights",
        "adults", "children", "infants", "earnings_cents",
    ]

    novos, alterados, iguais = [], [], []

    for registo in novos_registos:
        atual = indice.get((registo["listing"], registo["confirmation_code"]))
        if atual is None:
            novos.append(registo)
        elif all(str(registo[campo]) == str(atual[campo]) for campo in campos):
            iguais.append(registo)
        else:
            alterados.append(registo)

    para_gravar = novos + alterados

    for inicio in range(0, len(para_gravar), 200):
        (
            supabase.table("reservations")
            .upsert(
                para_gravar[inicio:inicio + 200],
                on_conflict="listing,confirmation_code",
            )
            .execute()
        )

    return {
        "novos": len(novos),
        "alterados": len(alterados),
        "iguais": len(iguais),
    }


def guardar_ajustes_taxa(listing, ano, editor):
    agora = agora_iso()

    for indice, linha in editor.reset_index(drop=True).iterrows():
        mes = indice + 1
        valor = linha["Ajuste manual (€)"]

        if pd.isna(valor):
            (
                supabase.table("tourist_tax_monthly")
                .delete()
                .eq("listing", listing)
                .eq("tax_year", int(ano))
                .eq("tax_month", mes)
                .execute()
            )
        else:
            notas = linha.get("Notas", "")
            (
                supabase.table("tourist_tax_monthly")
                .upsert(
                    {
                        "listing": listing,
                        "tax_year": int(ano),
                        "tax_month": mes,
                        "manual_tax_cents": int(round(float(valor) * 100)),
                        "notes": "" if pd.isna(notas) else str(notas or ""),
                        "updated_at": agora,
                    },
                    on_conflict="listing,tax_year,tax_month",
                )
                .execute()
            )


def guardar_reembolsos(listing, ano, editor):
    agora = agora_iso()

    for indice, linha in editor.reset_index(drop=True).iterrows():
        mes = indice + 1
        valor = linha["Reembolso (€)"]

        if pd.isna(valor) or float(valor) <= 0:
            (
                supabase.table("monthly_adjustments")
                .delete()
                .eq("listing", listing)
                .eq("adj_year", int(ano))
                .eq("adj_month", mes)
                .execute()
            )
        else:
            notas = linha.get("Notas", "")
            (
                supabase.table("monthly_adjustments")
                .upsert(
                    {
                        "listing": listing,
                        "adj_year": int(ano),
                        "adj_month": mes,
                        "refund_cents": int(round(float(valor) * 100)),
                        "notes": "" if pd.isna(notas) else str(notas or ""),
                        "updated_at": agora,
                    },
                    on_conflict="listing,adj_year,adj_month",
                )
                .execute()
            )


def guardar_propriedades(editor):
    agora = agora_iso()
    registos = []

    for _, linha in editor.iterrows():
        nome = linha["Nome curto"]
        nome = "" if pd.isna(nome) else str(nome).strip()
        dono = linha["Proprietário"]
        dono = PROPRIETARIOS[0] if pd.isna(dono) or not str(dono).strip() else str(dono)
        registos.append({
            "listing": linha["Anúncio no Airbnb"],
            "display_name": nome or linha["Anúncio no Airbnb"],
            "owner": dono,
            "updated_at": agora,
        })

    supabase.table("properties").upsert(registos, on_conflict="listing").execute()


def indexar_mensal(registos, ano_campo, mes_campo, valor_campo):
    """{(listing, ano): {mês: {"valor": euros, "notes": texto}}}"""
    indice = {}
    for registo in registos or []:
        chave = (registo["listing"], int(registo[ano_campo]))
        indice.setdefault(chave, {})[int(registo[mes_campo])] = {
            "valor": int(registo[valor_campo]) / 100,
            "notes": registo.get("notes") or "",
        }
    return indice


# =========================================================
# BARRA LATERAL: IMPORTAÇÃO
# =========================================================

def painel_importacao():
    with st.sidebar:
        with st.expander("Importar reservas (CSV)"):
            ficheiros = st.file_uploader(
                "CSV de reservas Airbnb",
                type=["csv"],
                accept_multiple_files=True,
            )
            if ficheiros and st.button(
                "Guardar ou atualizar reservas",
                type="primary",
                use_container_width=True,
            ):
                try:
                    lote = core.preparar_lote_csv(ficheiros)
                    st.session_state["importacao"] = guardar_reservas(lote)
                    limpar_cache()
                    st.rerun()
                except Exception as erro:
                    st.error("Não foi possível importar os ficheiros.")
                    st.code(str(erro))

        if st.button("Atualizar dados", use_container_width=True):
            limpar_cache()
            st.rerun()

        st.caption(f"Data de referência: {HOJE:%d/%m/%Y}")


with st.sidebar:
    st.markdown(
        '<div class="ad-marca">Painel de Alojamentos</div>'
        '<div class="ad-marca-nota">Rendimento, ocupação e preços</div>',
        unsafe_allow_html=True,
    )

if "importacao" in st.session_state:
    resultado = st.session_state.pop("importacao")
    st.success(
        f"Importação concluída: {resultado['novos']} novas, "
        f"{resultado['alterados']} atualizadas e {resultado['iguais']} iguais."
    )


# =========================================================
# CARREGAR DADOS
# =========================================================

try:
    dados = core.registos_para_dataframe(
        ler_tabela("reservations", COLUNAS_RESERVAS)
    )
    registos_taxa = ler_tabela(
        "tourist_tax_monthly",
        "listing,tax_year,tax_month,manual_tax_cents,notes",
    )
except Exception as erro:
    st.error("Não foi possível ler os dados.")
    st.code(str(erro))
    st.stop()

if dados.empty:
    painel_importacao()
    st.info(
        "Ainda não existem reservas guardadas. "
        "Importa os CSV do Airbnb na barra lateral."
    )
    st.stop()

registos_reembolsos = ler_tabela_opcional(
    "monthly_adjustments", "listing,adj_year,adj_month,refund_cents,notes",
)
registos_propriedades = ler_tabela_opcional(
    "properties", "listing,display_name,owner",
)

tem_reembolsos = registos_reembolsos is not None
tem_propriedades = registos_propriedades is not None

taxas = indexar_mensal(registos_taxa, "tax_year", "tax_month", "manual_tax_cents")
reembolsos = indexar_mensal(
    registos_reembolsos, "adj_year", "adj_month", "refund_cents",
)

listings = sorted(dados["Listing"].unique())


def montar_propriedades():
    """Nome curto e proprietário de cada anúncio (com valores por omissão)."""
    guardadas = {
        registo["listing"]: registo for registo in (registos_propriedades or [])
    }
    linhas = []
    usados = set()

    for listing in listings:
        registo = guardadas.get(listing, {})
        nome = (registo.get("display_name") or "").strip() or listing
        dono = (registo.get("owner") or "").strip() or PROPRIETARIOS[0]

        # Nomes curtos repetidos tornariam a escolha ambígua.
        candidato = nome
        numero = 2
        while candidato in usados:
            candidato = f"{nome} ({numero})"
            numero += 1
        usados.add(candidato)

        linhas.append({
            "Listing": listing,
            "Nome": candidato,
            "Proprietário": dono,
            "Configurado": listing in guardadas,
        })

    return pd.DataFrame(linhas).set_index("Listing")


propriedades = montar_propriedades()

reservas_por_listing = {
    listing: dados[dados["Listing"] == listing].copy() for listing in listings
}
noites_por_listing = {
    listing: core.criar_noites(
        reservas_por_listing[listing][~reservas_por_listing[listing]["Cancelada"]]
    )
    for listing in listings
}


# =========================================================
# FILTROS
# =========================================================

with st.sidebar:
    donos_presentes = [
        dono for dono in PROPRIETARIOS
        if (propriedades["Proprietário"] == dono).any()
    ]
    donos_presentes += sorted(
        set(propriedades["Proprietário"]) - set(PROPRIETARIOS)
    )

    if len(listings) > 1 and len(donos_presentes) > 1:
        carteira = st.radio("Carteira", [TODOS] + donos_presentes, horizontal=True)
    else:
        carteira = TODOS

    if carteira == TODOS:
        listings_carteira = listings
    else:
        listings_carteira = [
            listing for listing in listings
            if propriedades.loc[listing, "Proprietário"] == carteira
        ]

    nomes_carteira = [
        propriedades.loc[listing, "Nome"] for listing in listings_carteira
    ]

    if len(listings_carteira) > 1:
        escolha = st.selectbox("Alojamento", [TODOS_ALOJAMENTOS] + nomes_carteira)
    else:
        escolha = st.selectbox("Alojamento", nomes_carteira)

    if escolha == TODOS_ALOJAMENTOS:
        selecionados = listings_carteira
    else:
        selecionados = [listings_carteira[nomes_carteira.index(escolha)]]

    anos_disponiveis = sorted(
        {
            int(ano)
            for listing in selecionados
            for ano in noites_por_listing[listing]["Data"].dt.year.unique()
        },
        reverse=True,
    )

    if not anos_disponiveis:
        st.warning("Não existem reservas ativas nesta seleção.")
        painel_importacao()
        st.stop()

    ano = st.selectbox(
        "Ano",
        anos_disponiveis,
        index=(
            anos_disponiveis.index(HOJE.year)
            if HOJE.year in anos_disponiveis else 0
        ),
    )

painel_importacao()

alojamento_unico = selecionados[0] if len(selecionados) == 1 else None
ano = int(ano)
ano_anterior = ano - 1


# =========================================================
# CÁLCULOS
# =========================================================

_memoria_mensal = {}


def mensal_de(listing, ano_pedido):
    chave = (listing, int(ano_pedido))
    if chave not in _memoria_mensal:
        ajustes = taxas.get(chave, {}) if int(ano_pedido) >= 2026 else {}
        _memoria_mensal[chave], _ = core.resumo_mensal(
            reservas_por_listing[listing],
            noites_por_listing[listing],
            ano_pedido,
            ajustes,
            HOJE,
            reembolsos.get(chave, {}),
        )
    return _memoria_mensal[chave]


def mensal_selecao(ano_pedido):
    return core.agregar_mensal(
        [mensal_de(listing, ano_pedido) for listing in selecionados]
    )


mensal = mensal_selecao(ano)
mensal_anterior = mensal_selecao(ano_anterior)
anual = core.resumo_anual(mensal, ano, HOJE)

sobrepostos = [
    propriedades.loc[listing, "Nome"]
    for listing in selecionados
    if noites_por_listing[listing].duplicated(subset=["Listing", "Data"]).any()
]


def meses_comparaveis():
    """Meses fechados em que o ano anterior esteve à venda o mês inteiro."""
    meses = []
    for indice in range(12):
        mes = indice + 1
        fechado = (ano, mes) < (HOJE.year, HOJE.month)
        antes = mensal_anterior.iloc[indice]
        completo = (
            antes["Dias disponíveis"] >= antes["Dias do mês"] * len(selecionados)
        )
        if fechado and completo and antes["Total líquido (€)"] > 0:
            meses.append(indice)
    return meses


comparaveis = meses_comparaveis()

if comparaveis:
    base_atual = float(mensal.iloc[comparaveis]["Total líquido (€)"].sum())
    base_antes = float(mensal_anterior.iloc[comparaveis]["Total líquido (€)"].sum())
    crescimento_ano = variacao(base_atual, base_antes)
    periodo_comparavel = (
        MESES_CURTOS[comparaveis[0]]
        if len(comparaveis) == 1
        else f"{MESES_CURTOS[comparaveis[0]]}–{MESES_CURTOS[comparaveis[-1]]}"
    )
else:
    crescimento_ano = None
    periodo_comparavel = ""


# =========================================================
# CABEÇALHO
# =========================================================

if alojamento_unico:
    titulo = propriedades.loc[alojamento_unico, "Nome"]
    subtitulo = (
        f"{propriedades.loc[alojamento_unico, 'Proprietário']} · {ano} · "
        "valores sem taxa turística"
    )
else:
    titulo = (
        "Todos os alojamentos" if carteira == TODOS
        else f"Alojamentos de {carteira}"
    )
    subtitulo = (
        f"{len(selecionados)} alojamentos · {ano} · valores sem taxa turística"
    )

st.markdown(
    f'<p class="ad-titulo">{h(titulo)}</p>'
    f'<p class="ad-subtitulo">{h(subtitulo)}</p>',
    unsafe_allow_html=True,
)

if sobrepostos:
    st.warning(
        "Existem reservas sobrepostas em: " + ", ".join(sobrepostos)
        + ". As noites em causa estão a contar a dobrar; confirma os CSV."
    )

por_configurar = [
    propriedades.loc[listing, "Nome"]
    for listing in listings
    if not propriedades.loc[listing, "Configurado"]
]
if tem_propriedades and por_configurar and len(listings) > 1:
    st.info(
        "Alojamentos sem proprietário definido (a contar como "
        f"{PROPRIETARIOS[0]}): " + ", ".join(por_configurar)
        + ". Define-os no separador Dados."
    )

(
    aba_desempenho,
    aba_mensal,
    aba_precos,
    aba_reconciliacao,
    aba_taxa,
    aba_dados,
) = st.tabs([
    "Desempenho",
    "Mensal",
    "Plano de preços",
    "Reconciliação",
    "Taxa turística",
    "Dados",
])


# =========================================================
# DESEMPENHO
# =========================================================

with aba_desempenho:

    if crescimento_ano is None:
        nota_crescimento = h(f"sem meses comparáveis em {ano_anterior}")
    else:
        nota_crescimento = nota_variacao(
            crescimento_ano,
            f"vs {ano_anterior} ({periodo_comparavel}) · objetivo +10 %",
        )

    duracao = (
        mensal["Soma durações"].sum() / anual["reservas"]
        if anual["reservas"] else None
    )

    media_antes = core.resumo_anual(mensal_anterior, ano_anterior, HOJE)["media_noite"]

    cartoes([
        {
            "rotulo": f"Rendimento líquido {ano}",
            "valor": euros(anual["liquido"]),
            "nota": nota_crescimento,
            "destaque": True,
        },
        {
            "rotulo": "Já realizado",
            "valor": euros(anual["realizado"]),
            "nota": h(f"Reservas futuras: {euros(anual['futuro'])}"),
        },
        {
            "rotulo": "Noites reservadas",
            "valor": inteiro(anual["noites"]),
            "nota": h(
                f"{inteiro(anual['reservas'])} reservas · "
                f"estadia média {decimal(duracao)} noites"
            ),
        },
        {
            "rotulo": anual["ocupacao_rotulo"],
            "valor": percentagem(anual["ocupacao"]),
            "nota": h("noites ocupadas ÷ dias disponíveis"),
        },
        {
            "rotulo": "Média líquida por noite",
            "valor": euros(anual["media_noite"]),
            "nota": nota_variacao(
                variacao(anual["media_noite"], media_antes),
                f"vs {ano_anterior}",
            ),
        },
    ])

    if anual["cancelamentos"] or anual["reembolsos"]:
        st.caption(
            f"Fora das estadias: cancelamentos retidos {euros(anual['cancelamentos'])}, "
            f"reembolsos enviados {euros(anual['reembolsos'])}. "
            f"Total do ano com estes movimentos: {euros(anual['total'])}."
        )

    seccao(
        "Rendimento por mês",
        "Cada noite conta no mês em que acontece, mesmo que a reserva "
        "comece ou acabe noutro mês.",
    )

    figura = go.Figure()
    figura.add_bar(
        x=MESES_CURTOS,
        y=mensal["Realizado líquido (€)"],
        name="Realizado",
        marker_color=COR_PRINCIPAL,
        hovertemplate="%{y:,.0f} €<extra>Realizado</extra>",
    )
    figura.add_bar(
        x=MESES_CURTOS,
        y=mensal["Futuro líquido (€)"],
        name="Reservas futuras",
        marker_color=COR_FUTURO,
        hovertemplate="%{y:,.0f} €<extra>Reservas futuras</extra>",
    )
    figura.add_scatter(
        x=MESES_CURTOS,
        y=mensal["Total líquido (€)"],
        mode="text",
        text=mensal["Total líquido (€)"].map(etiqueta_euros),
        textposition="top center",
        textfont=dict(size=11, color=COR_SUAVE),
        showlegend=False,
        hoverinfo="skip",
        cliponaxis=False,
    )
    if mensal_anterior["Total líquido (€)"].sum() > 0:
        figura.add_scatter(
            x=MESES_CURTOS,
            y=mensal_anterior["Total líquido (€)"],
            name=str(ano_anterior),
            mode="lines+markers",
            line=dict(color=COR_ANTERIOR, width=2.5, shape="spline", smoothing=0.6),
            marker=dict(size=6),
            hovertemplate="%{y:,.0f} €<extra>" + str(ano_anterior) + "</extra>",
        )
    figura.update_layout(barmode="stack")
    mostrar_grafico(estilo_grafico(figura, altura=400))

    if len(selecionados) > 1:
        seccao("Rendimento por alojamento", f"Rendimento líquido de {ano}.")

        linhas_alojamentos = []
        for listing in selecionados:
            resumo_listing = core.resumo_anual(mensal_de(listing, ano), ano, HOJE)
            linhas_alojamentos.append((
                propriedades.loc[listing, "Nome"],
                f"{propriedades.loc[listing, 'Proprietário']} · "
                f"{inteiro(resumo_listing['noites'])} noites · "
                f"ocupação {percentagem(resumo_listing['ocupacao'])}",
                resumo_listing["liquido"],
            ))
        linhas_alojamentos.sort(key=lambda linha: linha[2], reverse=True)
        barras_alojamentos(linhas_alojamentos)

        if carteira == TODOS and len(donos_presentes) > 1:
            seccao("Rendimento por proprietário")
            linhas_donos = []
            for dono in donos_presentes:
                do_dono = [
                    listing for listing in selecionados
                    if propriedades.loc[listing, "Proprietário"] == dono
                ]
                if not do_dono:
                    continue
                resumo_dono = core.resumo_anual(
                    core.agregar_mensal([mensal_de(l, ano) for l in do_dono]),
                    ano, HOJE,
                )
                linhas_donos.append((
                    dono,
                    f"{len(do_dono)} alojamento(s) · "
                    f"{inteiro(resumo_dono['noites'])} noites",
                    resumo_dono["liquido"],
                ))
            barras_alojamentos(linhas_donos)

    seccao("Ocupação por mês", "Noites ocupadas em cada mês, em percentagem.")

    figura_ocupacao = go.Figure()
    figura_ocupacao.add_bar(
        x=MESES_CURTOS,
        y=mensal["Ocupação (%)"],
        name=str(ano),
        marker_color=COR_TEXTO,
        text=mensal["Ocupação (%)"].map(
            lambda valor: "" if pd.isna(valor) or valor == 0 else f"{valor:.0f}%"
        ),
        textposition="outside",
        cliponaxis=False,
        hovertemplate="%{y:.1f} %<extra>" + str(ano) + "</extra>",
    )
    if mensal_anterior["Noites"].sum() > 0:
        figura_ocupacao.add_scatter(
            x=MESES_CURTOS,
            y=mensal_anterior["Ocupação (%)"],
            name=str(ano_anterior),
            mode="lines+markers",
            line=dict(color=COR_ANTERIOR, width=2, dash="dot"),
            hovertemplate="%{y:.1f} %<extra>" + str(ano_anterior) + "</extra>",
        )
    figura_ocupacao.update_yaxes(range=[0, 115], ticksuffix=" %")
    mostrar_grafico(estilo_grafico(figura_ocupacao, altura=300))


# =========================================================
# MENSAL
# =========================================================

with aba_mensal:

    seccao(
        f"Análise mensal · {ano}",
        "Valores sem taxa turística. A última coluna compara com o mesmo mês "
        f"de {ano_anterior}.",
    )

    analise = mensal[[
        "Mês", "Total líquido (€)", "Noites", "Ocupação (%)",
        "Média líquida/noite (€)", "Reservas", "Duração média",
        "Taxa utilizada (€)", "Cancelamentos retidos (€)", "Reembolsos (€)",
        "Total do mês (€)",
    ]].copy()

    analise[f"vs {ano_anterior}"] = [
        variacao(atual, antes)
        for atual, antes in zip(
            mensal["Total líquido (€)"], mensal_anterior["Total líquido (€)"],
        )
    ]

    st.dataframe(
        tabela_formatada(analise, {
            "Total líquido (€)": euros,
            "Noites": inteiro,
            "Ocupação (%)": percentagem,
            "Média líquida/noite (€)": euros,
            "Reservas": inteiro,
            "Duração média": decimal,
            "Taxa utilizada (€)": euros,
            "Cancelamentos retidos (€)": euros,
            "Reembolsos (€)": euros,
            "Total do mês (€)": euros,
            f"vs {ano_anterior}": texto_variacao,
        }),
        hide_index=True,
        use_container_width=True,
    )

    st.caption(
        "Total do mês = total líquido das estadias + cancelamentos retidos "
        "− reembolsos enviados."
    )

    st.download_button(
        "Descarregar resumo mensal (CSV)",
        mensal.drop(columns=["Soma durações"]).round(2).to_csv(
            index=False, sep=";", decimal=",",
        ).encode("utf-8-sig"),
        file_name=f"resumo_{ano}.csv",
        mime="text/csv",
    )

    seccao("Média líquida por noite", "O valor que cada noite ocupada rendeu.")

    figura_media = go.Figure()
    figura_media.add_bar(
        x=MESES_CURTOS,
        y=mensal["Média líquida/noite (€)"],
        name=str(ano),
        marker_color=COR_PRINCIPAL,
        text=mensal["Média líquida/noite (€)"].map(etiqueta_euros),
        textposition="outside",
        cliponaxis=False,
        hovertemplate="%{y:,.2f} €<extra>" + str(ano) + "</extra>",
    )
    if mensal_anterior["Noites"].sum() > 0:
        figura_media.add_scatter(
            x=MESES_CURTOS,
            y=mensal_anterior["Média líquida/noite (€)"],
            name=str(ano_anterior),
            mode="lines+markers",
            line=dict(color=COR_ANTERIOR, width=2.5),
            hovertemplate="%{y:,.2f} €<extra>" + str(ano_anterior) + "</extra>",
        )
    mostrar_grafico(estilo_grafico(figura_media, altura=320))


# =========================================================
# PLANO DE PREÇOS
# =========================================================

with aba_precos:

    c1, c2, c3, c4 = st.columns(4)

    with c1:
        ano_plano = st.selectbox(
            "Ano a planear", [HOJE.year + 1, HOJE.year], key="ano_plano",
        )
    with c2:
        crescimento_pct = st.slider(
            "Objetivo de crescimento (%)", 0, 30, 10, key="crescimento_pct",
        )
    with c3:
        desconto_pct = st.slider(
            "Desconto médio que vais dar (%)", 0, 30, 10, key="desconto_pct",
            help=(
                "Descontos semanais, de última hora, promoções. O preço de "
                "tabela sobe o necessário para, depois deste desconto, "
                "ainda atingires o objetivo."
            ),
        )
    with c4:
        comissao_pct = st.number_input(
            "Comissão Airbnb (%)", min_value=0.0, max_value=20.0, value=3.0,
            step=0.5, key="comissao_pct",
            help="Comissão de anfitrião descontada pelo Airbnb.",
        )

    ano_plano = int(ano_plano)
    ano_referencia = ano_plano - 1

    def plano_de(listing, ocupacoes=None):
        return core.plano_precos(
            mensal_de(listing, ano_referencia),
            mensal_de(listing, ano_referencia - 1),
            mensal_de(listing, ano_plano),
            ano_plano,
            HOJE,
            crescimento=crescimento_pct / 100,
            comissao=comissao_pct / 100,
            desconto=desconto_pct / 100,
            ocupacoes=ocupacoes,
        )

    ocupacoes_editadas = None

    if alojamento_unico:
        plano_inicial = plano_de(alojamento_unico)

        seccao(
            "1. Ocupação que esperas",
            f"Por omissão é a ocupação de {ano_referencia}. Muda a última "
            "coluna se contas ocupar mais ou menos noites.",
        )

        editor_ocupacao = st.data_editor(
            plano_inicial[[
                "Mês", "Referência", "Rendimento referência (€)",
                "Ocupação referência (%)", "Líquido/noite referência (€)",
                "Ocupação esperada (%)",
            ]].round(2),
            disabled=[
                "Mês", "Referência", "Rendimento referência (€)",
                "Ocupação referência (%)", "Líquido/noite referência (€)",
            ],
            hide_index=True,
            use_container_width=True,
            key=f"ocupacao_{alojamento_unico}_{ano_plano}",
            column_config={
                "Rendimento referência (€)": st.column_config.NumberColumn(
                    format="%.2f €",
                ),
                "Ocupação referência (%)": st.column_config.NumberColumn(
                    format="%.1f %%",
                ),
                "Líquido/noite referência (€)": st.column_config.NumberColumn(
                    format="%.2f €",
                ),
                "Ocupação esperada (%)": st.column_config.NumberColumn(
                    min_value=1.0, max_value=100.0, step=1.0, format="%.1f %%",
                ),
            },
        )

        ocupacoes_editadas = {
            indice + 1: float(valor)
            for indice, valor in enumerate(
                editor_ocupacao["Ocupação esperada (%)"]
            )
            if not pd.isna(valor)
        }

        plano = plano_de(alojamento_unico, ocupacoes_editadas)
        planos = {alojamento_unico: plano}
    else:
        planos = {listing: plano_de(listing) for listing in selecionados}
        plano = None

    objetivo_total = sum(
        float(p["Objetivo (€)"].sum()) for p in planos.values()
    )
    referencia_total = sum(
        float(p["Rendimento referência (€)"].sum()) for p in planos.values()
    )
    reservado_total = sum(
        float(p["Já reservado (€)"].sum()) for p in planos.values()
    )
    atingido = 100 * reservado_total / objetivo_total if objetivo_total else None

    seccao(
        f"Objetivo {ano_plano}" if not alojamento_unico
        else f"2. Objetivo e preços para {ano_plano}",
        f"Cada mês tem de render +{crescimento_pct} % face ao mês de referência.",
    )

    itens_plano = [
        {
            "rotulo": f"Objetivo {ano_plano}",
            "valor": euros(objetivo_total),
            "nota": h(f"+{crescimento_pct} % sobre {euros(referencia_total)}"),
            "destaque": True,
        },
        {
            "rotulo": "Já reservado",
            "valor": euros(reservado_total),
            "nota": (
                h(f"{percentagem(atingido)} do objetivo")
                + '<div class="ad-progresso"><i style="width:'
                + f"{min(100.0, atingido or 0):.1f}%"
                + '"></i></div>'
            ),
        },
        {
            "rotulo": "Falta reservar",
            "valor": euros(max(0.0, objetivo_total - reservado_total)),
            "nota": h("para atingir o objetivo do ano"),
        },
    ]

    if plano is not None:
        noites_precisas = plano["Noites necessárias"].sum()
        itens_plano.append({
            "rotulo": "Líquido médio por noite necessário",
            "valor": euros(
                objetivo_total / noites_precisas if noites_precisas else None
            ),
            "nota": h(f"em {inteiro(noites_precisas)} noites ocupadas"),
        })

    cartoes(itens_plano)

    objetivo_mensal = sum(p["Objetivo (€)"].fillna(0).to_numpy() for p in planos.values())
    referencia_mensal = sum(
        p["Rendimento referência (€)"].fillna(0).to_numpy() for p in planos.values()
    )
    reservado_mensal = sum(p["Já reservado (€)"].to_numpy() for p in planos.values())

    figura_plano = go.Figure()
    figura_plano.add_bar(
        x=MESES_CURTOS, y=referencia_mensal, name="Referência",
        marker_color=COR_NEUTRA,
        hovertemplate="%{y:,.0f} €<extra>Referência</extra>",
    )
    figura_plano.add_bar(
        x=MESES_CURTOS, y=objetivo_mensal, name=f"Objetivo {ano_plano}",
        marker_color=COR_PRINCIPAL,
        text=[etiqueta_euros(valor) for valor in objetivo_mensal],
        textposition="outside", cliponaxis=False,
        hovertemplate="%{y:,.0f} €<extra>Objetivo</extra>",
    )
    figura_plano.add_scatter(
        x=MESES_CURTOS, y=reservado_mensal, name="Já reservado",
        mode="markers",
        marker=dict(color=COR_TEXTO, size=11, symbol="line-ew", line=dict(width=3, color=COR_TEXTO)),
        hovertemplate="%{y:,.0f} €<extra>Já reservado</extra>",
    )
    figura_plano.update_layout(barmode="group")
    mostrar_grafico(estilo_grafico(figura_plano, altura=380))

    if plano is not None:
        tabela_plano = plano[[
            "Mês", "Objetivo (€)", "Ocupação esperada (%)",
            "Líquido/noite necessário (€)", "Variação do preço (%)",
            "Preço mínimo (€)", "Preço de tabela (€)", "Já reservado (€)",
            "Objetivo atingido (%)",
        ]]

        st.dataframe(
            tabela_formatada(tabela_plano, {
                "Objetivo (€)": euros,
                "Ocupação esperada (%)": percentagem,
                "Líquido/noite necessário (€)": euros,
                "Variação do preço (%)": texto_variacao,
                "Preço mínimo (€)": euros,
                "Preço de tabela (€)": euros,
                "Já reservado (€)": euros,
                "Objetivo atingido (%)": percentagem,
            }),
            hide_index=True,
            use_container_width=True,
        )

        st.caption(
            "Líquido/noite necessário = objetivo ÷ noites esperadas. "
            f"Preço mínimo = esse valor antes da comissão de {decimal(comissao_pct)} % "
            "(abaixo disto o mês não atinge o objetivo). "
            f"Preço de tabela = preço a publicar para que, com {desconto_pct} % "
            "de desconto, ainda fiques no preço mínimo. "
            "A taxa turística não está incluída em nenhum destes preços."
        )

        seccao(
            "3. O que o hóspede paga com cada desconto",
            "Preço por noite depois de aplicar o desconto ao preço de tabela. "
            "Os valores com ⚠ ficam abaixo do preço mínimo.",
        )

        cenarios = core.cenarios_desconto(plano)
        visivel = cenarios[["Mês"]].copy()
        visivel["Preço de tabela"] = cenarios["Preço de tabela (€)"].map(euros)
        for coluna in cenarios.columns:
            if not coluna.startswith("−"):
                continue
            visivel[coluna] = [
                "—" if pd.isna(valor)
                else euros(valor) + (" ⚠" if valor < minimo - 0.005 else "")
                for valor, minimo in zip(
                    cenarios[coluna], cenarios["Preço mínimo (€)"],
                )
            ]
        visivel["Preço mínimo"] = cenarios["Preço mínimo (€)"].map(euros)

        st.dataframe(visivel, hide_index=True, use_container_width=True)

        st.download_button(
            f"Descarregar plano {ano_plano} (CSV)",
            plano.round(2).to_csv(
                index=False, sep=";", decimal=",",
            ).encode("utf-8-sig"),
            file_name=f"plano_precos_{ano_plano}.csv",
            mime="text/csv",
        )
    else:
        seccao("Objetivo por alojamento")

        linhas_objetivo = []
        for listing, plano_listing in planos.items():
            objetivo = float(plano_listing["Objetivo (€)"].sum())
            reservado = float(plano_listing["Já reservado (€)"].sum())
            linhas_objetivo.append({
                "Alojamento": propriedades.loc[listing, "Nome"],
                "Proprietário": propriedades.loc[listing, "Proprietário"],
                "Referência": euros(
                    float(plano_listing["Rendimento referência (€)"].sum())
                ),
                f"Objetivo {ano_plano}": euros(objetivo),
                "Já reservado": euros(reservado),
                "Atingido": percentagem(
                    100 * reservado / objetivo if objetivo else None
                ),
            })

        st.dataframe(
            pd.DataFrame(linhas_objetivo),
            hide_index=True,
            use_container_width=True,
        )
        st.info(
            "Escolhe um alojamento na barra lateral para ver os preços por "
            "noite e ajustar a ocupação esperada."
        )


# =========================================================
# RECONCILIAÇÃO
# =========================================================

with aba_reconciliacao:

    def reconciliacao_de(listing):
        chave = (listing, ano)
        resumo = mensal_de(listing, ano)
        return core.reconciliacao(
            reservas_por_listing[listing],
            ano,
            resumo["Taxa utilizada (€)"].sum(),
            sum(item["valor"] for item in reembolsos.get(chave, {}).values()),
        )

    seccao(
        f"Reconciliação financeira · {ano}",
        "Soma de todos os registos dos CSV com entrada neste ano, incluindo "
        "cancelamentos, menos reembolsos e taxa turística.",
    )

    if alojamento_unico:
        rec = reconciliacao_de(alojamento_unico)

        cartoes([
            {
                "rotulo": "Total dos CSV",
                "valor": euros(rec["total_csv"]),
                "nota": h(
                    f"Reservas ativas {euros(rec['ativas'])} + "
                    f"cancelamentos {euros(rec['canceladas'])}"
                ),
            },
            {
                "rotulo": "Reembolsos enviados",
                "valor": euros(rec["reembolsos_manuais"]),
                "nota": h("ajuste manual por mês"),
            },
            {
                "rotulo": "Taxa turística",
                "valor": euros(rec["taxa"]),
                "nota": h("a entregar ao município"),
            },
            {
                "rotulo": "Total final líquido",
                "valor": euros(rec["final"]),
                "nota": h("CSV − reembolsos − taxa turística"),
                "destaque": True,
            },
        ])

        if rec["negativos"]:
            st.caption(
                f"Os CSV já incluem {euros(rec['negativos'])} em valores "
                "negativos; não são subtraídos uma segunda vez."
            )

        seccao(
            "Reembolsos enviados aos hóspedes",
            "Valores que devolveste (por exemplo pelo centro de resoluções do "
            "Airbnb) e que não aparecem nos CSV de reservas.",
        )

        if tem_reembolsos:
            guardados = reembolsos.get((alojamento_unico, ano), {})
            base_reembolsos = pd.DataFrame({
                "Mês": MESES,
                "Cancelamentos retidos (€)": mensal_de(alojamento_unico, ano)[
                    "Cancelamentos retidos (€)"
                ].round(2),
                "Reembolso (€)": [
                    guardados.get(mes, {}).get("valor") for mes in range(1, 13)
                ],
                "Notas": [
                    guardados.get(mes, {}).get("notes", "")
                    for mes in range(1, 13)
                ],
            })
            base_reembolsos["Reembolso (€)"] = pd.to_numeric(
                base_reembolsos["Reembolso (€)"]
            )

            editor_reembolsos = st.data_editor(
                base_reembolsos,
                disabled=["Mês", "Cancelamentos retidos (€)"],
                hide_index=True,
                use_container_width=True,
                key=f"reembolsos_{alojamento_unico}_{ano}",
                column_config={
                    "Cancelamentos retidos (€)": st.column_config.NumberColumn(
                        format="%.2f €",
                    ),
                    "Reembolso (€)": st.column_config.NumberColumn(
                        min_value=0.0, step=1.0, format="%.2f €",
                    ),
                    "Notas": st.column_config.TextColumn(),
                },
            )

            if st.button("Guardar reembolsos", type="primary"):
                try:
                    guardar_reembolsos(alojamento_unico, ano, editor_reembolsos)
                    limpar_cache()
                    st.rerun()
                except Exception as erro:
                    st.error("Não foi possível guardar os reembolsos.")
                    st.code(str(erro))
        else:
            st.info(
                "Para registar reembolsos é preciso criar a tabela "
                "`monthly_adjustments` no Supabase. O SQL está no separador Dados."
            )

        seccao(
            "Comparar com o Airbnb",
            "Escreve o total que o painel do Airbnb mostra para este ano.",
        )

        total_airbnb = st.number_input(
            "Total apresentado no Airbnb (€)",
            min_value=0.0, value=0.0, step=0.01, format="%.2f",
            key=f"total_airbnb_{alojamento_unico}_{ano}",
        )

        if total_airbnb > 0:
            diferenca = total_airbnb - rec["total_csv"]
            cartoes([
                {"rotulo": "Airbnb", "valor": euros(total_airbnb), "nota": ""},
                {"rotulo": "Total dos CSV", "valor": euros(rec["total_csv"]), "nota": ""},
                {
                    "rotulo": "Diferença por explicar",
                    "valor": euros(diferenca),
                    "nota": h(
                        "O Airbnb soma por data de pagamento e inclui ajustes "
                        "que não vêm nos CSV de reservas."
                    ),
                },
            ])

        registos_cancelados = rec["registos"][rec["registos"]["Cancelada"]]
        if len(registos_cancelados):
            seccao("Registos cancelados")
            st.dataframe(
                pd.DataFrame({
                    "Código": registos_cancelados["Confirmation code"],
                    "Estado": registos_cancelados["Status"],
                    "Entrada": registos_cancelados["Entrada"].dt.strftime("%d/%m/%Y"),
                    "Saída": registos_cancelados["Saída"].dt.strftime("%d/%m/%Y"),
                    "Noites": registos_cancelados["Noites"],
                    "Valor retido": registos_cancelados["Valor bruto"].map(euros),
                }),
                hide_index=True,
                use_container_width=True,
            )
    else:
        linhas_rec = []
        for listing in selecionados:
            rec = reconciliacao_de(listing)
            linhas_rec.append({
                "Alojamento": propriedades.loc[listing, "Nome"],
                "Proprietário": propriedades.loc[listing, "Proprietário"],
                "Reservas ativas": rec["ativas"],
                "Cancelamentos": rec["canceladas"],
                "Total dos CSV": rec["total_csv"],
                "Reembolsos": rec["reembolsos_manuais"],
                "Taxa turística": rec["taxa"],
                "Total final líquido": rec["final"],
            })

        tabela_rec = pd.DataFrame(linhas_rec)
        colunas_valor = [
            "Reservas ativas", "Cancelamentos", "Total dos CSV", "Reembolsos",
            "Taxa turística", "Total final líquido",
        ]

        cartoes([
            {
                "rotulo": "Total dos CSV",
                "valor": euros(tabela_rec["Total dos CSV"].sum()),
                "nota": "",
            },
            {
                "rotulo": "Reembolsos enviados",
                "valor": euros(tabela_rec["Reembolsos"].sum()),
                "nota": "",
            },
            {
                "rotulo": "Taxa turística",
                "valor": euros(tabela_rec["Taxa turística"].sum()),
                "nota": "",
            },
            {
                "rotulo": "Total final líquido",
                "valor": euros(tabela_rec["Total final líquido"].sum()),
                "nota": "",
                "destaque": True,
            },
        ])

        st.dataframe(
            tabela_formatada(
                tabela_rec, {coluna: euros for coluna in colunas_valor},
            ),
            hide_index=True,
            use_container_width=True,
        )
        st.info(
            "Escolhe um alojamento na barra lateral para registar reembolsos "
            "ou comparar com o total do Airbnb."
        )


# =========================================================
# TAXA TURÍSTICA
# =========================================================

with aba_taxa:

    seccao(
        f"Taxa turística · {ano}",
        "2 € por hóspede e por noite, de abril a outubro, até 7 noites por "
        "reserva. O valor manual de um mês substitui o cálculo automático.",
    )

    if alojamento_unico:
        resumo_taxa = mensal_de(alojamento_unico, ano)
        guardados = taxas.get((alojamento_unico, ano), {})

        base_taxa = pd.DataFrame({
            "Mês": MESES,
            "Taxa automática (€)": resumo_taxa["Taxa automática (€)"].round(2),
            "Ajuste manual (€)": pd.to_numeric(
                pd.Series(
                    [guardados.get(mes, {}).get("valor") for mes in range(1, 13)]
                )
            ),
            "Taxa utilizada (€)": resumo_taxa["Taxa utilizada (€)"].round(2),
            "Origem": resumo_taxa["Origem"],
            "Notas": [
                guardados.get(mes, {}).get("notes", "") for mes in range(1, 13)
            ],
        })

        editor_taxa = st.data_editor(
            base_taxa,
            disabled=[
                "Mês", "Taxa automática (€)", "Taxa utilizada (€)", "Origem",
            ],
            hide_index=True,
            use_container_width=True,
            key=f"taxa_{alojamento_unico}_{ano}",
            column_config={
                "Taxa automática (€)": st.column_config.NumberColumn(
                    format="%.2f €",
                ),
                "Ajuste manual (€)": st.column_config.NumberColumn(
                    min_value=0.0, step=1.0, format="%.2f €",
                ),
                "Taxa utilizada (€)": st.column_config.NumberColumn(
                    format="%.2f €",
                ),
                "Notas": st.column_config.TextColumn(),
            },
        )

        st.caption(
            "O valor certo de cada mês está no relatório de rendimentos do "
            "Airbnb, na linha \"Impostos remetidos\"."
        )

        if ano >= 2026:
            if st.button("Guardar ajustes da taxa", type="primary"):
                try:
                    guardar_ajustes_taxa(alojamento_unico, ano, editor_taxa)
                    limpar_cache()
                    st.rerun()
                except Exception as erro:
                    st.error("Não foi possível guardar os ajustes.")
                    st.code(str(erro))
        else:
            st.caption("Antes de 2026 a taxa turística considerada é 0 €.")

        cartoes([
            {
                "rotulo": f"Taxa utilizada em {ano}",
                "valor": euros(resumo_taxa["Taxa utilizada (€)"].sum()),
                "nota": h(
                    "Estimativa automática: "
                    + euros(resumo_taxa["Taxa automática (€)"].sum())
                ),
            },
        ])
    else:
        linhas_taxa = []
        for listing in selecionados:
            resumo_taxa = mensal_de(listing, ano)
            linhas_taxa.append({
                "Alojamento": propriedades.loc[listing, "Nome"],
                "Proprietário": propriedades.loc[listing, "Proprietário"],
                "Taxa automática": euros(resumo_taxa["Taxa automática (€)"].sum()),
                "Taxa utilizada": euros(resumo_taxa["Taxa utilizada (€)"].sum()),
            })

        cartoes([
            {
                "rotulo": f"Taxa utilizada em {ano}",
                "valor": euros(anual["taxa"]),
                "nota": h(f"{len(selecionados)} alojamentos"),
            },
        ])
        st.dataframe(
            pd.DataFrame(linhas_taxa), hide_index=True, use_container_width=True,
        )
        st.info(
            "Escolhe um alojamento na barra lateral para editar os valores "
            "mensais da taxa."
        )

    figura_taxa = go.Figure()
    figura_taxa.add_bar(
        x=MESES_CURTOS,
        y=mensal["Taxa utilizada (€)"],
        marker_color=COR_ANTERIOR,
        text=mensal["Taxa utilizada (€)"].map(etiqueta_euros),
        textposition="outside",
        cliponaxis=False,
        hovertemplate="%{y:,.0f} €<extra>Taxa utilizada</extra>",
    )
    mostrar_grafico(estilo_grafico(figura_taxa, altura=280))


# =========================================================
# DADOS
# =========================================================

with aba_dados:

    seccao("Alojamentos", "Dá um nome curto a cada anúncio e indica de quem é.")

    cartoes([
        {"rotulo": "Reservas guardadas", "valor": inteiro(len(dados)), "nota": ""},
        {"rotulo": "Alojamentos", "valor": inteiro(len(listings)), "nota": ""},
        {
            "rotulo": "Proprietários",
            "valor": inteiro(propriedades["Proprietário"].nunique()),
            "nota": h(" · ".join(sorted(set(propriedades["Proprietário"])))),
        },
    ])

    base_propriedades = pd.DataFrame({
        "Anúncio no Airbnb": listings,
        "Nome curto": [propriedades.loc[l, "Nome"] for l in listings],
        "Proprietário": [propriedades.loc[l, "Proprietário"] for l in listings],
        "Reservas": [len(reservas_por_listing[l]) for l in listings],
    })

    if tem_propriedades:
        editor_propriedades = st.data_editor(
            base_propriedades,
            disabled=["Anúncio no Airbnb", "Reservas"],
            hide_index=True,
            use_container_width=True,
            key="propriedades",
            column_config={
                "Nome curto": st.column_config.TextColumn(
                    help="Por exemplo: T1+1 - Almeida Garrett",
                ),
                "Proprietário": st.column_config.SelectboxColumn(
                    options=PROPRIETARIOS, required=True,
                ),
            },
        )
        if st.button("Guardar alojamentos", type="primary"):
            try:
                guardar_propriedades(editor_propriedades)
                limpar_cache()
                st.rerun()
            except Exception as erro:
                st.error("Não foi possível guardar os alojamentos.")
                st.code(str(erro))
    else:
        st.dataframe(base_propriedades, hide_index=True, use_container_width=True)

    em_falta = [
        nome for nome, existe in [
            ("properties", tem_propriedades),
            ("monthly_adjustments", tem_reembolsos),
        ] if not existe
    ]

    if em_falta:
        seccao(
            "Configuração em falta no Supabase",
            "Sem estas tabelas a aplicação funciona, mas não guarda nomes "
            "curtos, proprietários nem reembolsos: " + ", ".join(em_falta) + ".",
        )
        st.code(SQL_CONFIGURACAO, language="sql")
        st.caption(
            "Depois de correr o SQL, carrega em \"Atualizar dados\" na barra lateral."
        )

    seccao("Regras aplicadas")
    st.markdown(
        """
- Cada reserva é identificada por anúncio + código de confirmação.
- O valor de uma reserva é repartido de forma igual pelas suas noites; cada noite conta no mês em que acontece. O dia de saída não conta.
- Os indicadores usam apenas reservas não canceladas e excluem a taxa turística.
- Os cancelamentos que ficaram com valor e os reembolsos enviados aparecem à parte, no total do mês e na reconciliação.
- A ocupação divide as noites ocupadas pelos dias em que o alojamento já estava à venda (desde a primeira noite reservada).
- Antes de 2026 a taxa turística considerada é 0 €. O ajuste manual de um mês substitui o cálculo automático.
- O plano de preços usa como referência o mesmo mês do ano anterior; se esse mês ainda não acabou, usa o do ano antes quando rendeu mais.
- Nomes e contactos dos hóspedes não são guardados.
"""
    )
