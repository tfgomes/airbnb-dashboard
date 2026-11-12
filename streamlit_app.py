import base64
import html
import importlib
import re
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from supabase import create_client

import core

# Depois de um deploy, o Streamlit pode manter em memória a versão antiga de
# core.py. Recarregar aqui garante que a app usa sempre a versão atual.
core = importlib.reload(core)

from core import (
    MESES,
    MESES_CURTOS,
    euros,
    euros_sinal,
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
# Proprietário especial: o anúncio fica fora de todos os relatórios.
IGNORAR = "Ignorar"
PASTA_FOTOS = Path(__file__).parent / "assets"

# Taxa de limpeza cobrada por reserva, por anúncio (valor inicial do campo
# no plano de preços; os que não estão aqui começam em 0).
TAXAS_LIMPEZA = {
    "Apartamento Moderno c/Piscina, a 12 min da Praia": 50.0,
}

# Nome curto e proprietário sugeridos para os anúncios conhecidos. Valem
# enquanto não houver outra escolha guardada no separador Dados.
SUGESTOES = {
    "Apartamento Moderno c/Piscina, a 12 min da Praia": (
        "T1+1 - Almeida Garrett", "Tiago",
    ),
    "Apartamento com dois quartos perto da praia 550m": (
        "T2 - Gil Vicente", "Guilhermino",
    ),
    "Charme Studio with Pool, Oldtown - 300m to Beach": (
        "T0 - Bayview", "Guilhermino",
    ),
    "Magnifico Apto renovado c/piscina 12 min da praia": (
        "T1 - Dunfermline", "Guilhermino",
    ),
}
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
    "nights,adults,children,infants,earnings_cents,updated_at"
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
    other_income_cents bigint not null default 0,
    notes text,
    updated_at timestamptz not null default now(),
    primary key (listing, adj_year, adj_month)
);

-- Para quem criou a tabela antes de existir esta coluna.
alter table public.monthly_adjustments
    add column if not exists other_income_cents bigint not null default 0;

alter table public.properties enable row level security;
alter table public.monthly_adjustments enable row level security;

grant select, insert, update, delete on public.properties to service_role;
grant select, insert, update, delete on public.monthly_adjustments to service_role;

create table if not exists public.cost_items (
    listing text not null,
    cost_year integer not null,
    category text not null,
    kind text not null default 'Operacional',
    monthly_cents bigint,
    annual_cents bigint,
    month_cents jsonb,
    annualize boolean not null default false,
    notes text,
    updated_at timestamptz not null default now(),
    primary key (listing, cost_year, category)
);

create table if not exists public.cost_settings (
    listing text not null,
    cost_year integer not null,
    invested_cents bigint not null default 0,
    property_value_cents bigint not null default 0,
    taxable_pct numeric not null default 35,
    tax_rate_pct numeric not null default 28,
    tax_paid_cents bigint not null default 0,
    updated_at timestamptz not null default now(),
    primary key (listing, cost_year)
);

-- Para quem criou a tabela antes dos custos mês a mês.
alter table public.cost_items add column if not exists month_cents jsonb;
alter table public.cost_items
    add column if not exists annualize boolean not null default false;

alter table public.cost_items enable row level security;
alter table public.cost_settings enable row level security;

grant select, insert, update, delete on public.cost_items to service_role;
grant select, insert, update, delete on public.cost_settings to service_role;
"""

DIAS_SEMANA = ["S", "T", "Q", "Q", "S", "S", "D"]


# =========================================================
# ESTILO
# =========================================================

ESTILO = """
<style>
html, body, [class*="css"], .stMarkdown, .stApp {
    font-family: "Inter", "Helvetica Neue", Helvetica, Arial, sans-serif;
}
.block-container { padding-top: 5rem; padding-bottom: 4rem; max-width: 1280px; }
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
.ad-cabecalho { display: flex; align-items: center; gap: 18px; margin-bottom: 1.2rem; }
.ad-cabecalho img.ad-foto { width: 132px; height: 88px; object-fit: cover; border-radius: 16px; flex: 0 0 auto; box-shadow: 0 2px 8px rgba(0,0,0,0.10); }
.ad-cabecalho .ad-subtitulo { margin-bottom: 0; }
.ad-miniatura { width: 56px; height: 40px; object-fit: cover; border-radius: 10px; flex: 0 0 auto; }
.ad-atualizacao { display: flex; justify-content: space-between; align-items: center; gap: 8px; font-size: 0.8rem; color: #222222; padding: 5px 0; }
.ad-atualizacao span:first-child { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.ad-celula-foto { display: inline-flex; align-items: center; gap: 10px; }
.ad-tabela-caixa { border: 1px solid #EBEBEB; border-radius: 18px; overflow-x: auto; background: #FFFFFF; margin: 0.4rem 0 0.7rem 0; box-shadow: 0 1px 2px rgba(0,0,0,0.04); }
.ad-tabela-caixa table.ad-tabela { width: 100%; border-collapse: collapse; font-size: 0.9rem; font-variant-numeric: tabular-nums; margin: 0; }
.ad-tabela-caixa table.ad-tabela th { text-align: right; font-weight: 600; font-size: 0.7rem; letter-spacing: 0.04em; text-transform: uppercase; color: #6A6A6A; padding: 12px 12px; border: none !important; border-bottom: 1px solid #EBEBEB !important; white-space: nowrap; background: #FAFAFA; }
.ad-tabela-caixa table.ad-tabela td { text-align: right; padding: 10px 12px; border: none !important; border-bottom: 1px solid #F2F2F2 !important; white-space: nowrap; color: #222222; }
.ad-tabela-caixa table.ad-tabela th.esq, .ad-tabela-caixa table.ad-tabela td.esq { text-align: left; }
.ad-tabela-caixa table.ad-tabela td.esq { font-weight: 600; }
.ad-tabela-caixa table.ad-tabela tr:hover td { background-color: #FAFAFA; }
.ad-tabela-caixa table.ad-tabela tr.total td { font-weight: 700; border-top: 2px solid #222222 !important; border-bottom: none !important; background: #FAFAFA; }
.ad-tabela-caixa table.ad-tabela tr.apagada td { color: #B0B0B0; }
.ad-pill { display: inline-block; padding: 2px 9px; border-radius: 999px; font-size: 0.78rem; font-weight: 600; }
.ad-pill.sobe { background: #E6F4E6; color: #00710A; }
.ad-pill.desce { background: #FBE9E6; color: #B32505; }
.ad-pill.neutro { background: #F0F0F0; color: #6A6A6A; }
.ad-mais { color: #00710A; font-weight: 600; }
.ad-menos { color: #B32505; font-weight: 600; }
.ad-forte { font-weight: 700; }
.ad-mini { display: inline-flex; align-items: center; gap: 8px; justify-content: flex-end; }
.ad-mini i { display: inline-block; width: 60px; height: 6px; border-radius: 999px; background: #EDEDED; overflow: hidden; }
.ad-mini i b { display: block; height: 100%; border-radius: 999px; background: #222222; }
.ad-mini.rosa i b { background: linear-gradient(90deg, #E61E4D, #D70466); }
.ad-cal-caixa { border: 1px solid #EBEBEB; border-radius: 18px; overflow-x: auto; background: #FFFFFF; margin: 0.4rem 0 0.7rem 0; box-shadow: 0 1px 2px rgba(0,0,0,0.04); }
.ad-cal { min-width: 1040px; }
.ad-cal-linha { display: flex; align-items: stretch; border-bottom: 1px solid #F2F2F2; }
.ad-cal-linha:last-child { border-bottom: none; }
.ad-cal-nome { flex: 0 0 210px; display: flex; align-items: center; gap: 10px; padding: 10px 14px; border-right: 1px solid #EBEBEB; min-width: 0; }
.ad-cal-nome b { display: block; font-size: 0.86rem; color: #222222; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.ad-cal-nome span { display: block; font-size: 0.72rem; color: #6A6A6A; }
.ad-cal-pista { flex: 1 1 auto; position: relative; min-height: 60px; }
.ad-cal-fundo, .ad-cal-eventos, .ad-cal-dias { display: grid; position: absolute; inset: 0; }
.ad-cal-dias { position: relative; flex: 1 1 auto; }
.ad-cal-celula { border-right: 1px solid #F4F4F4; }
.ad-cal-celula.fds { background: #FAFAFA; }
.ad-cal-celula.hoje { background: #FFF0F3; }
.ad-cal-dia { text-align: center; padding: 8px 0 6px 0; font-size: 0.68rem; color: #6A6A6A; border-right: 1px solid #F4F4F4; background: #FAFAFA; }
.ad-cal-dia b { display: block; font-size: 0.86rem; color: #222222; font-weight: 600; }
.ad-cal-dia.hoje b { background: #E61E4D; color: #FFFFFF; border-radius: 999px; width: 24px; height: 24px; line-height: 24px; margin: 0 auto; }
.ad-cal-eventos { align-items: center; }
.ad-cal-ev { grid-row: 1; height: 30px; margin: 0 2px; border-radius: 999px; padding: 0 10px; font-size: 0.74rem; font-weight: 600; line-height: 30px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; color: #FFFFFF; background: linear-gradient(90deg, #E61E4D, #D70466); }
.ad-cal-ev.passada { background: #B0B0B0; }
.ad-cal-ev.atual { background: #222222; }
.ad-cal-ev.ical { background: #FFFFFF; color: #D70466; border: 2px solid #E61E4D; line-height: 26px; }
.ad-cal-ev.duvida { background: #FFFFFF; color: #B32505; border: 2px dashed #B32505; line-height: 26px; }
.ad-cal-ev.bloqueio { background: repeating-linear-gradient(45deg, #EDEDED, #EDEDED 6px, #F8F8F8 6px, #F8F8F8 12px); color: #6A6A6A; font-weight: 500; }
.ad-legenda { display: flex; flex-wrap: wrap; gap: 14px; font-size: 0.78rem; color: #6A6A6A; margin: 0.2rem 0 0.8rem 0; }
.ad-legenda span { display: inline-flex; align-items: center; gap: 6px; }
.ad-legenda .ad-cal-ev { display: inline-block; height: 14px; width: 30px; margin: 0; padding: 0; line-height: 10px; }
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
            + imagem_html(nome, "ad-miniatura")
            + f'<div class="ad-linha-nome"><b>{h(nome)}</b><span>{h(legenda)}</span></div>'
            f'<div class="ad-linha-barra"><i style="width:{quota:.1f}%"></i></div>'
            f'<div class="ad-linha-valor"><b>{h(euros(valor))}</b>'
            f"<span>{h(percentagem(quota))}</span></div>"
            "</div>"
        )
    st.markdown(
        '<div class="ad-cartao">' + "".join(partes) + "</div>",
        unsafe_allow_html=True,
    )


def tabela_html(cabecalhos, linhas, total=None, apagadas=()):
    """Tabela com o estilo do painel.

    cabecalhos  lista de títulos; a primeira coluna fica alinhada à esquerda
    linhas      lista de linhas; cada célula é HTML já seguro, ou um par
                (HTML, estilo CSS) para pintar o fundo da célula
    total       linha final em destaque (opcional)
    apagadas    índices das linhas a mostrar a cinzento (meses sem dados)
    """
    def celulas(linha):
        partes = []
        linha = [celula for celula in linha if celula is not None]
        for posicao, celula in enumerate(linha):
            estilo = ""
            if isinstance(celula, tuple):
                celula, estilo = celula
            classe = ' class="esq"' if posicao == 0 else ""
            atributo = f' style="{estilo}"' if estilo else ""
            partes.append(f"<td{classe}{atributo}>{celula}</td>")
        return "".join(partes)

    topo = "".join(
        f'<th{" class=esq" if posicao == 0 else ""}>{h(titulo)}</th>'
        for posicao, titulo in enumerate(
            [titulo for titulo in cabecalhos if titulo is not None]
        )
    )
    corpo = "".join(
        f'<tr{" class=apagada" if indice in apagadas else ""}>{celulas(linha)}</tr>'
        for indice, linha in enumerate(linhas)
    )
    if total is not None:
        corpo += f'<tr class="total">{celulas(total)}</tr>'

    st.markdown(
        '<div class="ad-tabela-caixa"><table class="ad-tabela">'
        f"<thead><tr>{topo}</tr></thead><tbody>{corpo}</tbody></table></div>",
        unsafe_allow_html=True,
    )


def c_euros(valor, casas=2, zero_vazio=True):
    if valor is None or pd.isna(valor) or (zero_vazio and abs(valor) < 0.005):
        return "—"
    return h(euros(valor, casas))


def c_diferenca(valor):
    """Diferença em euros, verde se positiva e vermelha se negativa."""
    if valor is None or pd.isna(valor) or abs(valor) < 0.005:
        return "—"
    classe = "ad-mais" if valor > 0 else "ad-menos"
    return f'<span class="{classe}">{h(euros_sinal(valor))}</span>'


def c_variacao(valor):
    """Variação percentual dentro de uma etiqueta colorida."""
    if valor is None or pd.isna(valor):
        return "—"
    classe = "sobe" if valor >= 0 else "desce"
    return f'<span class="ad-pill {classe}">{h(texto_variacao(valor))}</span>'


def c_barra(valor, rosa=False):
    """Percentagem com uma barra pequena ao lado."""
    if valor is None or pd.isna(valor):
        return "—"
    largura = max(0.0, min(100.0, float(valor)))
    classe = "ad-mini rosa" if rosa else "ad-mini"
    return (
        f'<span class="{classe}">{h(percentagem(valor, 0))}'
        f'<i><b style="width:{largura:.0f}%"></b></i></span>'
    )


def c_calor(valor, maximo, casas=2):
    """Valor em euros com fundo mais intenso quanto maior for."""
    if valor is None or pd.isna(valor) or abs(valor) < 0.005:
        return "—"
    intensidade = 0.20 * max(0.0, float(valor)) / maximo if maximo else 0
    return (h(euros(valor, casas)), f"background:rgba(230,30,77,{intensidade:.3f})")


def codigo_foto(nome):
    """'T1+1 - Almeida Garrett' -> 't1+1' (nome do ficheiro em assets/)."""
    palavras = str(nome).strip().split()
    return re.sub(r"[^a-z0-9+]", "", palavras[0].lower()) if palavras else ""


@st.cache_data(show_spinner=False)
def foto_base64(codigo):
    ficheiro = PASTA_FOTOS / f"{codigo}.jpg"
    if not codigo or not ficheiro.is_file():
        return None
    return base64.b64encode(ficheiro.read_bytes()).decode("ascii")


def imagem_html(nome, classe):
    dados_foto = foto_base64(codigo_foto(nome))
    if not dados_foto:
        return ""
    return (
        f'<img class="{classe}" alt="{h(nome)}" '
        f'src="data:image/jpeg;base64,{dados_foto}">'
    )


def c_alojamento(nome):
    """Miniatura e nome do alojamento, alinhados, para a primeira coluna."""
    return (
        '<span class="ad-celula-foto">'
        + imagem_html(nome, "ad-miniatura") + h(nome) + "</span>"
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

    # As reservas iguais também são gravadas, só para ficarem com a data
    # desta importação: é assim que a app sabe quando cada alojamento foi
    # atualizado pela última vez.
    para_gravar = novos + alterados + iguais

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


def guardar_reembolsos(listing, ano, editor, com_outros):
    agora = agora_iso()

    def valor_positivo(valor):
        return 0.0 if pd.isna(valor) or float(valor) <= 0 else float(valor)

    for indice, linha in editor.reset_index(drop=True).iterrows():
        mes = indice + 1
        reembolso = valor_positivo(linha["Reembolso (€)"])
        outros = (
            valor_positivo(linha["Outros rendimentos (€)"]) if com_outros else 0.0
        )

        if reembolso == 0 and outros == 0:
            (
                supabase.table("monthly_adjustments")
                .delete()
                .eq("listing", listing)
                .eq("adj_year", int(ano))
                .eq("adj_month", mes)
                .execute()
            )
            continue

        notas = linha.get("Notas", "")
        registo = {
            "listing": listing,
            "adj_year": int(ano),
            "adj_month": mes,
            "refund_cents": int(round(reembolso * 100)),
            "notes": "" if pd.isna(notas) else str(notas or ""),
            "updated_at": agora,
        }
        if com_outros:
            registo["other_income_cents"] = int(round(outros * 100))

        (
            supabase.table("monthly_adjustments")
            .upsert(registo, on_conflict="listing,adj_year,adj_month")
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


def guardar_custos(listing, ano, editor, definicoes):
    agora = agora_iso()

    def centimos(valor):
        if valor is None or pd.isna(valor) or float(valor) <= 0:
            return None
        return int(round(float(valor) * 100))

    linhas = {}
    for _, linha in editor.iterrows():
        categoria = linha["Categoria"]
        categoria = "" if pd.isna(categoria) else str(categoria).strip()
        if not categoria:
            continue
        tipo = linha["Tipo"]
        notas = linha.get("Notas", "")
        anualizar = linha.get("Anualizar", False)
        meses = [centimos(linha[mes]) for mes in MESES_CURTOS]
        linhas[categoria] = {
            "listing": listing,
            "cost_year": int(ano),
            "category": categoria,
            "kind": core.TIPOS_CUSTO[0] if pd.isna(tipo) or not tipo else str(tipo),
            "monthly_cents": None,
            "annual_cents": sum(valor or 0 for valor in meses) or None,
            "month_cents": meses,
            "annualize": False if pd.isna(anualizar) else bool(anualizar),
            "notes": "" if pd.isna(notas) else str(notas or ""),
            "updated_at": agora,
        }

    # Apaga primeiro as linhas do ano, para as removidas no editor saírem.
    (
        supabase.table("cost_items")
        .delete()
        .eq("listing", listing)
        .eq("cost_year", int(ano))
        .execute()
    )
    if linhas:
        (
            supabase.table("cost_items")
            .upsert(list(linhas.values()), on_conflict="listing,cost_year,category")
            .execute()
        )

    (
        supabase.table("cost_settings")
        .upsert(
            {
                "listing": listing,
                "cost_year": int(ano),
                "invested_cents": int(round(definicoes["capital"] * 100)),
                "property_value_cents": int(round(definicoes["imovel"] * 100)),
                "taxable_pct": float(definicoes["coeficiente"]),
                "tax_rate_pct": float(definicoes["taxa"]),
                "tax_paid_cents": int(round(definicoes["irs_real"] * 100)),
                "updated_at": agora,
            },
            on_conflict="listing,cost_year",
        )
        .execute()
    )


@st.cache_data(ttl=900, show_spinner=False)
def descarregar_ical(url):
    """Lê o calendário iCal de um alojamento. Devolve None se falhar."""
    try:
        pedido = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(pedido, timeout=10) as resposta:
            texto = resposta.read().decode("utf-8", errors="replace")
    except Exception:
        return None
    if "BEGIN:VCALENDAR" not in texto:
        return None
    return core.ler_ical(texto)


def ligacoes_ical():
    """Ligações iCal guardadas nos Secrets, por código (t0, t1, t1+1, t2)."""
    try:
        return {
            str(chave).strip().lower(): str(valor).strip()
            for chave, valor in dict(st.secrets["ical"]).items()
        }
    except Exception:
        return {}


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
            # A chave muda depois de cada importação, para a lista de
            # ficheiros ficar vazia e pronta para os seguintes.
            ficheiros = st.file_uploader(
                "CSV de reservas Airbnb",
                type=["csv"],
                accept_multiple_files=True,
                key=f"csv_{st.session_state.get('versao_upload', 0)}",
            )
            if ficheiros and st.button(
                "Guardar ou atualizar reservas",
                type="primary",
                use_container_width=True,
            ):
                try:
                    lote = core.preparar_lote_csv(ficheiros)
                    resultado_importacao = guardar_reservas(lote)
                    resultado_importacao["ignoradas"] = lote.attrs.get(
                        "ignoradas", 0,
                    )
                    st.session_state["importacao"] = resultado_importacao
                    st.session_state["versao_upload"] = (
                        st.session_state.get("versao_upload", 0) + 1
                    )
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
    if resultado.get("ignoradas"):
        st.warning(
            f"{resultado['ignoradas']} reservas antigas vinham sem valor "
            "(coluna Earnings vazia) e não foram importadas. Exporta esses "
            "meses a partir da conta do proprietário para as incluir."
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
    "monthly_adjustments",
    "listing,adj_year,adj_month,refund_cents,other_income_cents,notes",
)
# A coluna dos outros rendimentos pode ainda não existir numa tabela antiga.
tem_outros = registos_reembolsos is not None
if registos_reembolsos is None:
    registos_reembolsos = ler_tabela_opcional(
        "monthly_adjustments", "listing,adj_year,adj_month,refund_cents,notes",
    )
registos_propriedades = ler_tabela_opcional(
    "properties", "listing,display_name,owner",
)

registos_custos = ler_tabela_opcional(
    "cost_items",
    "listing,cost_year,category,kind,monthly_cents,annual_cents,"
    "month_cents,annualize,notes",
)
# As colunas dos custos mês a mês podem ainda não existir numa tabela antiga.
tem_custos_mensais = registos_custos is not None
if registos_custos is None:
    registos_custos = ler_tabela_opcional(
        "cost_items",
        "listing,cost_year,category,kind,monthly_cents,annual_cents,notes",
    )
registos_definicoes = ler_tabela_opcional(
    "cost_settings",
    "listing,cost_year,invested_cents,property_value_cents,"
    "taxable_pct,tax_rate_pct,tax_paid_cents",
)

tem_reembolsos = registos_reembolsos is not None
tem_propriedades = registos_propriedades is not None
tem_custos = registos_custos is not None and registos_definicoes is not None

taxas = indexar_mensal(registos_taxa, "tax_year", "tax_month", "manual_tax_cents")
reembolsos = indexar_mensal(
    registos_reembolsos, "adj_year", "adj_month", "refund_cents",
)
for registo in registos_reembolsos or []:
    chave_registo = (registo["listing"], int(registo["adj_year"]))
    reembolsos[chave_registo][int(registo["adj_month"])]["outros"] = (
        int(registo.get("other_income_cents") or 0) / 100
    )

todos_listings = sorted(dados["Listing"].unique())


def montar_propriedades():
    """Nome curto e proprietário de cada anúncio (com valores por omissão)."""
    guardadas = {
        registo["listing"]: registo for registo in (registos_propriedades or [])
    }
    linhas = []
    usados = set()

    for listing in todos_listings:
        registo = guardadas.get(listing, {})
        nome_sugerido, dono_sugerido = SUGESTOES.get(
            listing,
            # Um anúncio chamado "outro" é um anúncio de teste: fica de fora.
            (listing, IGNORAR if listing.strip().lower() == "outro" else PROPRIETARIOS[0]),
        )
        nome = (registo.get("display_name") or "").strip() or nome_sugerido
        dono = (registo.get("owner") or "").strip() or dono_sugerido

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
            "Configurado": listing in guardadas or listing in SUGESTOES,
        })

    return pd.DataFrame(linhas).set_index("Listing")


propriedades = montar_propriedades()

reservas_por_listing = {
    listing: dados[dados["Listing"] == listing].copy()
    for listing in todos_listings
}
noites_por_listing = {
    listing: core.criar_noites(
        reservas_por_listing[listing][~reservas_por_listing[listing]["Cancelada"]]
    )
    for listing in todos_listings
}


def estado_listing(listing):
    if propriedades.loc[listing, "Proprietário"] == IGNORAR:
        return "Ignorado"
    if not len(noites_por_listing[listing]):
        return "Sem estadias"
    return "Em uso"


# Só entram nos relatórios os anúncios em uso: os ignorados e os que nunca
# tiveram uma estadia (anúncios de teste ou desativados) ficam de fora.
listings = [
    listing for listing in todos_listings if estado_listing(listing) == "Em uso"
]

def calcular_ultimas_atualizacoes():
    """Data da última importação de CSV de cada anúncio."""
    if "updated_at" not in dados.columns:
        return {}
    momentos = pd.to_datetime(dados["updated_at"], utc=True, errors="coerce")
    momentos = momentos.dt.tz_convert("Europe/Lisbon").dt.tz_localize(None)
    ultimas = momentos.groupby(dados["Listing"]).max()
    return {
        listing: momento.normalize()
        for listing, momento in ultimas.items() if not pd.isna(momento)
    }


ultimas_atualizacoes = calcular_ultimas_atualizacoes()


def dias_desde_atualizacao(listing):
    data = ultimas_atualizacoes.get(listing)
    return None if data is None else max(0, int((HOJE - data).days))


def texto_dias(dias):
    if dias is None:
        return "sem data"
    if dias == 0:
        return "hoje"
    return "ontem" if dias == 1 else f"há {dias} dias"


def etiqueta_atualizacao(listing):
    """Etiqueta colorida: verde até 7 dias, cinzenta até 14, vermelha depois."""
    dias = dias_desde_atualizacao(listing)
    if dias is None:
        classe = "neutro"
    elif dias <= 7:
        classe = "sobe"
    else:
        classe = "neutro" if dias <= 14 else "desce"
    return f'<span class="ad-pill {classe}">{h(texto_dias(dias))}</span>'


if not listings:
    painel_importacao()
    st.info(
        "Não há alojamentos com estadias para mostrar. Importa reservas na "
        "barra lateral."
    )
    st.stop()


# =========================================================
# FILTROS
# =========================================================

with st.sidebar:
    donos_em_uso = {
        propriedades.loc[listing, "Proprietário"] for listing in listings
    }
    donos_presentes = [dono for dono in PROPRIETARIOS if dono in donos_em_uso]
    donos_presentes += sorted(donos_em_uso - set(PROPRIETARIOS))

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

with st.sidebar:
    st.markdown(
        '<div class="ad-marca-nota" style="margin:1rem 0 0.2rem 0">'
        "Última atualização dos dados</div>"
        + "".join(
            '<div class="ad-atualizacao">'
            f'<span>{h(propriedades.loc[listing, "Nome"])}</span>'
            f"{etiqueta_atualizacao(listing)}</div>"
            for listing in selecionados
        ),
        unsafe_allow_html=True,
    )

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
    noites_atual = float(mensal.iloc[comparaveis]["Noites"].sum())
    noites_antes = float(mensal_anterior.iloc[comparaveis]["Noites"].sum())
    variacao_media = variacao(
        base_atual / noites_atual if noites_atual else None,
        base_antes / noites_antes if noites_antes else None,
    )
else:
    crescimento_ano = None
    periodo_comparavel = ""
    variacao_media = None


# =========================================================
# CABEÇALHO
# =========================================================

if alojamento_unico:
    titulo = propriedades.loc[alojamento_unico, "Nome"]
    subtitulo = (
        f"{propriedades.loc[alojamento_unico, 'Proprietário']} · {ano} · "
        "valores sem taxa turística"
    )
    if alojamento_unico in ultimas_atualizacoes:
        subtitulo += (
            " · dados atualizados "
            f"{texto_dias(dias_desde_atualizacao(alojamento_unico))} "
            f"({ultimas_atualizacoes[alojamento_unico]:%d/%m/%Y})"
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
    '<div class="ad-cabecalho">'
    + (imagem_html(titulo, "ad-foto") if alojamento_unico else "")
    + f'<div><p class="ad-titulo">{h(titulo)}</p>'
    f'<p class="ad-subtitulo">{h(subtitulo)}</p></div></div>',
    unsafe_allow_html=True,
)

desatualizados = [
    f"{propriedades.loc[listing, 'Nome']} ({texto_dias(dias_desde_atualizacao(listing))})"
    for listing in selecionados
    if (dias_desde_atualizacao(listing) or 0) > 14
]
if desatualizados:
    st.warning(
        "Dados com mais de 14 dias: " + ", ".join(desatualizados)
        + ". Exporta um CSV novo do Airbnb e importa-o na barra lateral."
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
    aba_calendario,
    aba_mensal,
    aba_precos,
    aba_custos,
    aba_reconciliacao,
    aba_taxa,
    aba_dados,
) = st.tabs([
    "Resumo anual",
    "Calendário",
    "Mensal",
    "Plano de preços",
    "Custos e ROI",
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
            "nota": (
                nota_variacao(
                    variacao_media, f"vs {ano_anterior} ({periodo_comparavel})",
                )
                if variacao_media is not None
                else h("por noite ocupada")
            ),
        },
    ])

    if anual["cancelamentos"] or anual["reembolsos"] or anual["outros"]:
        st.caption(
            f"Fora das estadias: cancelamentos retidos {euros(anual['cancelamentos'])}, "
            f"outros rendimentos {euros(anual['outros'])}, "
            f"reembolsos enviados {euros(anual['reembolsos'])}. "
            f"Total do ano com estes movimentos: {euros(anual['total'])}."
        )

    # ----- Evolução por ano -----

    anos_evolucao = sorted({
        int(valor)
        for listing in selecionados
        for valor in noites_por_listing[listing]["Data"].dt.year.unique()
    })
    resumos_anos = {
        valor: core.resumo_anual(mensal_selecao(valor), valor, HOJE)
        for valor in anos_evolucao
    }

    seccao(
        "Evolução por ano",
        "Rendimento líquido de cada ano; a parte clara são reservas futuras "
        "já confirmadas.",
    )

    figura_anos = go.Figure()
    figura_anos.add_bar(
        x=[str(valor) for valor in anos_evolucao],
        y=[resumos_anos[valor]["realizado"] for valor in anos_evolucao],
        name="Realizado",
        marker_color=[
            COR_PRINCIPAL if valor == ano else COR_ANTERIOR
            for valor in anos_evolucao
        ],
        hovertemplate="%{y:,.0f} €<extra>Realizado</extra>",
    )
    figura_anos.add_bar(
        x=[str(valor) for valor in anos_evolucao],
        y=[resumos_anos[valor]["futuro"] for valor in anos_evolucao],
        name="Reservas futuras",
        marker_color=COR_FUTURO,
        text=[
            etiqueta_euros(resumos_anos[valor]["liquido"]) for valor in anos_evolucao
        ],
        textposition="outside",
        cliponaxis=False,
        hovertemplate="%{y:,.0f} €<extra>Reservas futuras</extra>",
    )
    figura_anos.update_layout(barmode="stack", showlegend=False, bargap=0.45)
    figura_anos.update_xaxes(type="category")
    mostrar_grafico(estilo_grafico(figura_anos, altura=320))

    linhas_anos = []
    for posicao, valor in enumerate(anos_evolucao):
        resumo_ano = resumos_anos[valor]
        antes_ano = resumos_anos[anos_evolucao[posicao - 1]] if posicao else None
        linhas_anos.append([
            h(valor),
            f'<span class="ad-forte">{c_euros(resumo_ano["liquido"])}</span>',
            # Um ano que ainda não começou não se compara nem tem ocupação.
            c_diferenca(resumo_ano["liquido"] - antes_ano["liquido"])
            if antes_ano and valor <= HOJE.year else "—",
            h(inteiro(resumo_ano["noites"])),
            c_barra(resumo_ano["ocupacao"]) if valor <= HOJE.year else "—",
            c_euros(resumo_ano["media_noite"]),
            c_euros(resumo_ano["taxa"]),
        ])
    tabela_html(
        [
            "Ano", "Rendimento líquido", "Face ao ano anterior", "Noites",
            "Ocupação", "Média por noite", "Taxa turística",
        ],
        linhas_anos,
    )
    st.caption(
        "Estes valores são diferentes dos do Airbnb por três razões: aqui não "
        "entra a taxa turística, cada noite conta no mês em que acontece (o "
        "Airbnb conta o pagamento inteiro no dia a seguir à entrada) e os "
        "cancelamentos aparecem à parte. A comparação direta com o Airbnb, "
        "mês a mês, está no separador Reconciliação."
    )

    # ----- Progresso face ao ano anterior -----

    if mensal_anterior["Total líquido (€)"].sum() > 0:
        seccao(
            f"Progresso de {ano} face a {ano_anterior}",
            "Rendimento acumulado desde janeiro. A linha tracejada é o "
            f"objetivo: {ano_anterior} mais 10 %.",
        )

        acumulado_ano = mensal["Total líquido (€)"].astype(float).cumsum()
        acumulado_anterior = mensal_anterior["Total líquido (€)"].astype(float).cumsum()

        figura_progresso = go.Figure()
        figura_progresso.add_scatter(
            x=MESES_CURTOS, y=acumulado_anterior * 1.10,
            name=f"Objetivo ({ano_anterior} + 10 %)",
            mode="lines",
            line=dict(color=COR_SUAVE, width=1.5, dash="dash"),
            hovertemplate="%{y:,.0f} €<extra>Objetivo</extra>",
        )
        figura_progresso.add_scatter(
            x=MESES_CURTOS, y=acumulado_anterior,
            name=str(ano_anterior),
            mode="lines+markers",
            line=dict(color=COR_ANTERIOR, width=2.5),
            hovertemplate="%{y:,.0f} €<extra>" + str(ano_anterior) + "</extra>",
        )
        figura_progresso.add_scatter(
            x=MESES_CURTOS, y=acumulado_ano,
            name=str(ano),
            mode="lines+markers",
            line=dict(color=COR_PRINCIPAL, width=3.5),
            marker=dict(size=8),
            hovertemplate="%{y:,.0f} €<extra>" + str(ano) + "</extra>",
        )
        mostrar_grafico(estilo_grafico(figura_progresso, altura=360))


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



# =========================================================
# CALENDÁRIO
# =========================================================

with aba_calendario:

    ligacoes = ligacoes_ical()
    falhas_ical = []
    eventos_por_listing = {}

    for listing in selecionados:
        nome_alojamento = propriedades.loc[listing, "Nome"]
        ligacao = ligacoes.get(codigo_foto(nome_alojamento))
        eventos_ical = descarregar_ical(ligacao) if ligacao else None
        if ligacao and eventos_ical is None:
            falhas_ical.append(nome_alojamento)
        eventos_por_listing[listing] = core.eventos_calendario(
            reservas_por_listing[listing], eventos_ical, HOJE,
        )

    primeiras_noites = [
        noites_por_listing[listing]["Data"].min()
        for listing in selecionados
        if len(noites_por_listing[listing])
    ]
    primeiro_mes = min(primeiras_noites + [HOJE]).replace(day=1)
    meses_calendario = list(pd.date_range(
        primeiro_mes, HOJE.replace(day=1) + pd.DateOffset(months=12), freq="MS",
    ))
    rotulos_meses = [
        f"{MESES[mes.month - 1]} de {mes.year}" for mes in meses_calendario
    ]
    mes_atual = HOJE.replace(day=1)

    coluna_mes, _ = st.columns([1, 3])
    with coluna_mes:
        rotulo_mes = st.selectbox(
            "Mês",
            rotulos_meses,
            index=(
                meses_calendario.index(mes_atual)
                if mes_atual in meses_calendario else len(meses_calendario) - 1
            ),
            key="mes_calendario",
        )

    inicio_mes = meses_calendario[rotulos_meses.index(rotulo_mes)]
    dias_mes = inicio_mes.days_in_month
    fim_mes = inicio_mes + pd.Timedelta(days=dias_mes)
    datas_mes = list(pd.date_range(inicio_mes, periods=dias_mes))

    def classe_dia(data):
        if data == HOJE:
            return " hoje"
        return " fds" if data.dayofweek >= 5 else ""

    grelha_dias = f"grid-template-columns:repeat({dias_mes},1fr)"
    grelha_eventos = f"grid-template-columns:repeat({2 * dias_mes},1fr)"

    cabecalho_dias = "".join(
        f'<div class="ad-cal-dia{classe_dia(data)}">'
        f"{DIAS_SEMANA[data.dayofweek]}<b>{data.day}</b></div>"
        for data in datas_mes
    )
    fundo_dias = "".join(
        f'<div class="ad-cal-celula{classe_dia(data)}"></div>' for data in datas_mes
    )

    def barra_evento(evento):
        """Barra de uma reserva: da tarde da entrada à manhã da saída."""
        if evento["inicio"] < inicio_mes:
            coluna_inicio = 1
        else:
            coluna_inicio = 2 * (evento["inicio"] - inicio_mes).days + 2
        if evento["fim"] >= fim_mes:
            coluna_fim = 2 * dias_mes + 1
        else:
            coluna_fim = 2 * (evento["fim"] - inicio_mes).days + 2

        periodo = f"{evento['inicio']:%d/%m} → {evento['fim']:%d/%m}"

        if evento["tipo"] == "bloqueio":
            classe, rotulo = "bloqueio", "Indisponível"
            detalhe = f"Bloqueado · {periodo}"
        else:
            if evento["em_duvida"]:
                classe = "duvida"
            elif evento["origem"] == "ical":
                classe = "ical"
            elif evento["fim"] <= HOJE:
                classe = "passada"
            elif evento["inicio"] <= HOJE:
                classe = "atual"
            else:
                classe = ""

            if evento["valor"] is None:
                rotulo = f"{evento['noites']} n · reservado"
                detalhe = (
                    f"{evento['codigo'] or 'Reserva'} · {periodo} · "
                    f"{evento['noites']} noites · ainda sem CSV"
                )
            else:
                rotulo = (
                    f"{evento['noites']} n · {evento['hospedes']} hósp. · "
                    f"{etiqueta_euros(evento['valor']) or '0 €'}"
                )
                detalhe = (
                    f"{evento['codigo']} · {periodo} · {evento['noites']} noites · "
                    f"{evento['hospedes']} hóspedes · {euros(evento['valor'])}"
                )
            if evento["em_duvida"]:
                detalhe += " · não aparece no iCal: confirma se foi cancelada"

        return (
            f'<div class="ad-cal-ev {classe}" title="{h(detalhe)}" '
            f'style="grid-column:{coluna_inicio} / {coluna_fim}">{h(rotulo)}</div>'
        )

    linhas_calendario = [
        '<div class="ad-cal-linha"><div class="ad-cal-nome"></div>'
        f'<div class="ad-cal-dias" style="{grelha_dias}">{cabecalho_dias}</div></div>'
    ]

    ocupadas_mes_total = 0
    for listing in selecionados:
        nome_alojamento = propriedades.loc[listing, "Nome"]
        eventos = eventos_por_listing[listing]
        visiveis = [
            evento for evento in eventos
            if evento["fim"] >= inicio_mes and evento["inicio"] < fim_mes
        ]
        ocupadas = core.noites_ocupadas(
            [evento for evento in visiveis if evento["tipo"] == "reserva"]
        )
        ocupadas_mes = sum(1 for data in datas_mes if data in ocupadas)
        ocupadas_mes_total += ocupadas_mes

        linhas_calendario.append(
            '<div class="ad-cal-linha">'
            '<div class="ad-cal-nome">'
            + imagem_html(nome_alojamento, "ad-miniatura")
            + f"<div><b>{h(nome_alojamento)}</b>"
            f"<span>{ocupadas_mes} de {dias_mes} noites reservadas</span></div></div>"
            '<div class="ad-cal-pista">'
            f'<div class="ad-cal-fundo" style="{grelha_dias}">{fundo_dias}</div>'
            f'<div class="ad-cal-eventos" style="{grelha_eventos}">'
            + "".join(barra_evento(evento) for evento in visiveis)
            + "</div></div></div>"
        )

    seccao(
        rotulo_mes[0].upper() + rotulo_mes[1:],
        f"{ocupadas_mes_total} noites reservadas em "
        f"{dias_mes * len(selecionados)} possíveis. Cada barra vai da tarde "
        "da entrada à manhã da saída; passa o rato por cima para ver os detalhes.",
    )

    st.markdown(
        '<div class="ad-cal-caixa"><div class="ad-cal">'
        + "".join(linhas_calendario)
        + "</div></div>"
        '<div class="ad-legenda">'
        '<span><i class="ad-cal-ev passada"></i>Terminada</span>'
        '<span><i class="ad-cal-ev atual"></i>A decorrer</span>'
        '<span><i class="ad-cal-ev"></i>Confirmada</span>'
        '<span><i class="ad-cal-ev ical"></i>No Airbnb, ainda sem CSV</span>'
        '<span><i class="ad-cal-ev duvida"></i>No CSV mas não no Airbnb</span>'
        '<span><i class="ad-cal-ev bloqueio"></i>Indisponível</span>'
        "</div>",
        unsafe_allow_html=True,
    )

    if not ligacoes:
        st.caption(
            "Calendário feito só com as reservas dos CSV. Para ver também "
            "bloqueios e reservas ainda não importadas, adiciona as ligações "
            "iCal (instruções no separador Dados)."
        )
    if falhas_ical:
        st.warning(
            "Não foi possível ler o iCal de: " + ", ".join(falhas_ical)
            + ". O calendário desses alojamentos mostra só as reservas dos CSV."
        )

    em_duvida = sum(
        1 for eventos in eventos_por_listing.values()
        for evento in eventos if evento["em_duvida"]
    )
    if em_duvida:
        st.warning(
            f"{em_duvida} reserva(s) futura(s) estão nos CSV mas já não "
            "aparecem no calendário do Airbnb (contorno tracejado). Podem ter "
            "sido canceladas: exporta um CSV novo para atualizar."
        )

    # ----- Entradas e saídas -----

    seccao(
        "Entradas e saídas nos próximos 14 dias",
        "Para planear limpezas. \"Troca\" é uma saída e uma entrada no mesmo dia.",
    )

    nomes_dias = ["seg.", "ter.", "qua.", "qui.", "sex.", "sáb.", "dom."]
    estilo_movimento = {"Entrada": "sobe", "Saída": "neutro", "Troca": "desce"}

    def resumo_reserva(evento):
        if evento is None:
            return "—"
        if evento["hospedes"] is None:
            return h(f"{evento['noites']} noites")
        return h(f"{evento['noites']} noites · {evento['hospedes']} hóspedes")

    linhas_movimentos = [
        [
            h(
                ("Hoje" if movimento["data"] == HOJE
                 else nomes_dias[movimento["data"].dayofweek])
                + f" {movimento['data']:%d/%m}"
            ),
            h(movimento["alojamento"]),
            f'<span class="ad-pill {estilo_movimento[movimento["tipo"]]}">'
            f'{h(movimento["tipo"])}</span>',
            resumo_reserva(movimento["saida"]),
            resumo_reserva(movimento["entrada"]),
        ]
        for movimento in core.movimentos(
            {
                propriedades.loc[listing, "Nome"]: eventos_por_listing[listing]
                for listing in selecionados
            },
            HOJE, 14,
        )
    ]

    if linhas_movimentos:
        tabela_html(
            ["Dia", "Alojamento", "Movimento", "Quem sai", "Quem entra"],
            linhas_movimentos,
        )
    else:
        st.caption("Sem entradas nem saídas nos próximos 14 dias.")

    # ----- Noites livres -----

    seccao(
        "Noites livres nos próximos 30 dias",
        "Noites sem reserva nem bloqueio: são as que ainda podes vender.",
    )

    def texto_periodo(inicio, fim, noites):
        if noites == 1:
            return f"{inicio.day} {MESES_CURTOS[inicio.month - 1]} (1)"
        return (
            f"{inicio.day} {MESES_CURTOS[inicio.month - 1]} – "
            f"{fim.day} {MESES_CURTOS[fim.month - 1]} ({noites})"
        )

    linhas_livres = []
    for listing in selecionados:
        periodos = core.periodos_livres(eventos_por_listing[listing], HOJE, 30)
        livres = sum(noites for _, _, noites in periodos)
        linhas_livres.append([
            c_alojamento(propriedades.loc[listing, "Nome"]),
            f'<span class="ad-forte">{livres}</span>',
            c_barra(100 * (30 - livres) / 30),
            h(" · ".join(texto_periodo(*periodo) for periodo in periodos) or "—"),
        ])

    tabela_html(
        ["Alojamento", "Noites livres", "Ocupação 30 dias", "Períodos livres (noites)"],
        linhas_livres,
    )


# =========================================================
# MENSAL
# =========================================================

with aba_mensal:

    liquido_atual = mensal["Total líquido (€)"].astype(float)
    liquido_antes = mensal_anterior["Total líquido (€)"].astype(float)
    acumulado_atual = liquido_atual.cumsum()
    acumulado_antes = liquido_antes.cumsum()
    maximo_mes = float(max(liquido_atual.max(), liquido_antes.max(), 1.0))
    ha_anterior = liquido_antes.sum() > 0

    sem_dados = {
        indice for indice in range(12)
        if liquido_atual.iloc[indice] < 0.005 and liquido_antes.iloc[indice] < 0.005
    }

    seccao(
        f"Rendimento por mês · {ano} e {ano_anterior}",
        "Barras: este ano (a parte clara são reservas futuras). Linha: o "
        "mesmo mês do ano anterior. Cada noite conta no mês em que acontece.",
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

    # ----- 1. Rendimento e comparação -----

    seccao(
        f"Rendimento · {ano} face a {ano_anterior}" if ha_anterior
        else f"Rendimento · {ano}",
        "Valores líquidos, sem taxa turística. O acumulado soma os meses "
        "desde janeiro.",
    )

    linhas_rendimento = []
    for indice in range(12):
        atual = liquido_atual.iloc[indice]
        antes = liquido_antes.iloc[indice]
        linha = [h(MESES[indice]), c_calor(atual, maximo_mes)]
        if ha_anterior:
            linha += [
                c_euros(antes),
                c_diferenca(atual - antes) if indice not in sem_dados else "—",
                # A percentagem só aparece em meses fechados e comparáveis.
                c_variacao(variacao(atual, antes)) if indice in comparaveis else "—",
            ]
        linha.append(
            f'<span class="ad-forte">{c_euros(acumulado_atual.iloc[indice])}</span>'
        )
        if ha_anterior:
            linha += [
                c_euros(acumulado_antes.iloc[indice]),
                c_diferenca(
                    acumulado_atual.iloc[indice] - acumulado_antes.iloc[indice]
                ),
            ]
        linhas_rendimento.append(linha)

    if ha_anterior:
        tabela_html(
            [
                "Mês", str(ano), str(ano_anterior), "Diferença", "Variação",
                f"Acumulado {ano}", f"Acumulado {ano_anterior}", "Dif. acumulada",
            ],
            linhas_rendimento,
            total=[
                "Total",
                c_euros(liquido_atual.sum()),
                c_euros(liquido_antes.sum()),
                c_diferenca(liquido_atual.sum() - liquido_antes.sum()),
                c_variacao(crescimento_ano),
                "", "", "",
            ],
            apagadas=sem_dados,
        )
        if comparaveis:
            st.caption(
                "A variação em percentagem só aparece nos meses já fechados em "
                f"que {ano_anterior} esteve à venda o mês inteiro "
                f"({periodo_comparavel}); a do total usa só esses meses."
            )
    else:
        tabela_html(
            ["Mês", str(ano), f"Acumulado {ano}"],
            linhas_rendimento,
            total=["Total", c_euros(liquido_atual.sum()), ""],
            apagadas=sem_dados,
        )

    if not ha_anterior:
        st.caption(
            f"Ainda não há dados de {ano_anterior} para esta seleção; as "
            "colunas de comparação ficam preenchidas quando os carregares."
        )

    # ----- 2. Preço por noite e ocupação -----

    seccao(
        "Preço por noite e ocupação",
        "Mínimo, média e máximo do que cada noite rendeu. O potencial é o "
        "que o mês renderia com todas as noites ao preço da melhor noite."
        if alojamento_unico else
        "Noites ocupadas e média do que cada noite rendeu.",
    )

    sem_noites = {
        indice for indice in range(12) if mensal["Noites"].iloc[indice] == 0
    }

    cabecalho_noites = ["Mês", "Noites", "Ocupação", "Reservas", "Estadia média"]
    if alojamento_unico:
        cabecalho_noites += [
            "Mínimo", "Média", "Máximo", "Potencial ao máximo", "Por captar",
        ]
    else:
        cabecalho_noites += ["Média por noite"]

    linhas_noites = []
    for indice in range(12):
        linha = mensal.iloc[indice]
        celulas_linha = [
            h(MESES[indice]),
            h(inteiro(linha["Noites"])) if linha["Noites"] else "—",
            c_barra(linha["Ocupação (%)"]) if linha["Noites"] else "—",
            h(inteiro(linha["Reservas"])) if linha["Reservas"] else "—",
            h(decimal(linha["Duração média"])),
        ]
        if alojamento_unico:
            celulas_linha += [
                c_euros(linha["Mínimo/noite (€)"]),
                f'<span class="ad-forte">{c_euros(linha["Média líquida/noite (€)"])}</span>',
                c_euros(linha["Máximo/noite (€)"]),
                c_euros(linha["Potencial ao máximo (€)"], 0),
                c_euros(linha["Por captar (€)"], 0),
            ]
        else:
            celulas_linha += [
                f'<span class="ad-forte">{c_euros(linha["Média líquida/noite (€)"])}</span>',
            ]
        linhas_noites.append(celulas_linha)

    total_noites = [
        "Total",
        h(inteiro(anual["noites"])),
        c_barra(anual["ocupacao"]),
        h(inteiro(anual["reservas"])),
        h(decimal(
            mensal["Soma durações"].sum() / anual["reservas"]
            if anual["reservas"] else None
        )),
    ]
    if alojamento_unico:
        total_noites += [
            c_euros(mensal["Mínimo/noite (€)"].astype(float).min()),
            c_euros(anual["media_noite"]),
            c_euros(mensal["Máximo/noite (€)"].astype(float).max()),
            c_euros(mensal["Potencial ao máximo (€)"].sum(), 0),
            c_euros(mensal["Por captar (€)"].sum(), 0),
        ]
    else:
        total_noites += [c_euros(anual["media_noite"])]

    tabela_html(
        cabecalho_noites, linhas_noites, total=total_noites, apagadas=sem_noites,
    )

    figura_media = go.Figure()
    figura_media.add_bar(
        x=MESES_CURTOS,
        y=mensal["Média líquida/noite (€)"],
        name=f"Média {ano}",
        marker_color=COR_PRINCIPAL,
        text=mensal["Média líquida/noite (€)"].map(etiqueta_euros),
        textposition="outside",
        cliponaxis=False,
        hovertemplate="%{y:,.2f} €<extra>Média " + str(ano) + "</extra>",
    )
    if alojamento_unico:
        figura_media.add_scatter(
            x=MESES_CURTOS,
            y=mensal["Máximo/noite (€)"],
            name="Melhor noite",
            mode="markers",
            marker=dict(color=COR_TEXTO, size=9, symbol="triangle-up"),
            hovertemplate="%{y:,.2f} €<extra>Melhor noite</extra>",
        )
        figura_media.add_scatter(
            x=MESES_CURTOS,
            y=mensal["Mínimo/noite (€)"],
            name="Pior noite",
            mode="markers",
            marker=dict(color=COR_SUAVE, size=9, symbol="triangle-down"),
            hovertemplate="%{y:,.2f} €<extra>Pior noite</extra>",
        )
    if mensal_anterior["Noites"].sum() > 0:
        figura_media.add_scatter(
            x=MESES_CURTOS,
            y=mensal_anterior["Média líquida/noite (€)"],
            name=f"Média {ano_anterior}",
            mode="lines+markers",
            line=dict(color=COR_ANTERIOR, width=2.5),
            hovertemplate="%{y:,.2f} €<extra>Média " + str(ano_anterior) + "</extra>",
        )
    mostrar_grafico(estilo_grafico(figura_media, altura=340))

    # ----- 3. Comparação entre alojamentos -----

    if len(selecionados) > 1:
        seccao(
            "Rendimento por alojamento e mês",
            "A cor é mais forte nos melhores meses de cada alojamento.",
        )

        colunas_alojamento = [
            mensal_de(listing, ano)["Total líquido (€)"].astype(float)
            for listing in selecionados
        ]
        maximos = [float(max(coluna.max(), 1.0)) for coluna in colunas_alojamento]

        linhas_matriz = []
        for indice in range(12):
            linhas_matriz.append(
                [h(MESES[indice])]
                + [
                    c_calor(coluna.iloc[indice], maximo, 0)
                    for coluna, maximo in zip(colunas_alojamento, maximos)
                ]
                + [f'<span class="ad-forte">{c_euros(liquido_atual.iloc[indice], 0)}</span>']
            )

        tabela_html(
            ["Mês"]
            + [propriedades.loc[listing, "Nome"] for listing in selecionados]
            + ["Total"],
            linhas_matriz,
            total=(
                ["Total"]
                + [c_euros(coluna.sum(), 0) for coluna in colunas_alojamento]
                + [c_euros(liquido_atual.sum(), 0)]
            ),
            apagadas={
                indice for indice in range(12) if liquido_atual.iloc[indice] < 0.005
            },
        )

    # ----- 4. Taxa turística e outros movimentos -----

    with st.expander(
        "Taxa turística, cancelamentos, outros rendimentos e reembolsos por mês"
    ):
        linhas_movimentos = [
            [
                h(MESES[indice]),
                c_euros(mensal["Earnings bruto (€)"].iloc[indice]),
                c_euros(mensal["Taxa utilizada (€)"].iloc[indice]),
                c_euros(liquido_atual.iloc[indice]),
                c_euros(mensal["Cancelamentos retidos (€)"].iloc[indice]),
                c_euros(mensal["Outros rendimentos (€)"].iloc[indice]),
                c_euros(mensal["Reembolsos (€)"].iloc[indice]),
                f'<span class="ad-forte">{c_euros(mensal["Total do mês (€)"].iloc[indice])}</span>',
            ]
            for indice in range(12)
        ]
        tabela_html(
            [
                "Mês", "Recebido do Airbnb", "Taxa turística", "Estadias líquidas",
                "Cancelamentos retidos", "Outros rendimentos", "Reembolsos",
                "Total do mês",
            ],
            linhas_movimentos,
            total=[
                "Total",
                c_euros(mensal["Earnings bruto (€)"].sum()),
                c_euros(mensal["Taxa utilizada (€)"].sum()),
                c_euros(liquido_atual.sum()),
                c_euros(mensal["Cancelamentos retidos (€)"].sum()),
                c_euros(mensal["Outros rendimentos (€)"].sum()),
                c_euros(mensal["Reembolsos (€)"].sum()),
                c_euros(mensal["Total do mês (€)"].sum()),
            ],
            apagadas=sem_dados,
        )
        st.caption(
            "Estadias líquidas = recebido do Airbnb − taxa turística. "
            "Total do mês = estadias líquidas + cancelamentos retidos + outros "
            "rendimentos − reembolsos."
        )

    st.download_button(
        "Descarregar resumo mensal (CSV)",
        mensal.drop(columns=["Soma durações"]).round(2).to_csv(
            index=False, sep=";", decimal=",",
        ).encode("utf-8-sig"),
        file_name=f"resumo_{ano}.csv",
        mime="text/csv",
    )


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
            "Comissão Airbnb (%)", min_value=0.0, max_value=30.0, value=15.5,
            step=0.5, key="comissao_pct",
            help=(
                "O preço que publicas já inclui a comissão do Airbnb. "
                "Com 15,5 %, recebes 84,5 % do preço publicado."
            ),
        )

    ano_plano = int(ano_plano)
    ano_referencia = ano_plano - 1

    if alojamento_unico:
        coluna_limpeza, _ = st.columns([1, 3])
        with coluna_limpeza:
            taxa_limpeza = st.number_input(
                "Taxa de limpeza por reserva (€)", min_value=0.0, step=5.0,
                value=TAXAS_LIMPEZA.get(alojamento_unico, 0.0),
                key=f"taxa_limpeza_{alojamento_unico}",
                help=(
                    "O que cobras de limpeza em cada reserva, à parte do "
                    "preço por noite. O preço por noite a publicar desce o "
                    "equivalente a esta taxa dividida pela estadia média."
                ),
            )
    else:
        taxa_limpeza = 0.0

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
            taxa_limpeza=(
                taxa_limpeza if listing == alojamento_unico
                else TAXAS_LIMPEZA.get(listing, 0.0)
            ),
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
        maximo_tabela = float(plano["Preço de tabela (€)"].astype(float).max() or 1.0)

        linhas_plano = []
        for indice in range(12):
            linha = plano.iloc[indice]
            linhas_plano.append([
                h(linha["Mês"]),
                h(linha["Referência"]),
                c_euros(linha["Líquido/noite referência (€)"]),
                c_euros(linha["Máximo/noite referência (€)"]),
                c_euros(linha["Objetivo (€)"], 0),
                h(percentagem(linha["Ocupação esperada (%)"], 0)),
                f'<span class="ad-forte">{c_euros(linha["Líquido/noite necessário (€)"])}</span>',
                c_variacao(linha["Variação do preço (%)"]),
                c_euros(linha["Limpeza por noite (€)"], 0, zero_vazio=False)
                if taxa_limpeza > 0 else None,
                c_euros(linha["Preço mínimo (€)"], 0),
                c_calor(linha["Preço de tabela (€)"], maximo_tabela, 0),
                c_barra(linha["Objetivo atingido (%)"], rosa=True)
                if linha["Já reservado (€)"] > 0 else "—",
            ])

        tabela_html(
            [
                "Mês", "Referência", "Média ref.", "Melhor noite ref.",
                "Objetivo", "Ocupação", "Líquido necessário",
                "Subida", "Limpeza/noite" if taxa_limpeza > 0 else None,
                "Preço mínimo", "Preço de tabela", "Já reservado",
            ],
            linhas_plano,
            total=[
                "Total", "", "", "",
                c_euros(objetivo_total, 0), "", "", "",
                "" if taxa_limpeza > 0 else None, "", "",
                c_barra(atingido, rosa=True),
            ],
            apagadas={
                indice for indice in range(12)
                if pd.isna(plano["Objetivo (€)"].astype(float).iloc[indice])
            },
        )

        st.caption(
            "Líquido/noite necessário = objetivo ÷ noites esperadas. "
            f"Preço mínimo = esse valor ÷ {decimal(100 - comissao_pct)} %, porque o "
            f"Airbnb fica com {decimal(comissao_pct)} % do preço publicado "
            "(abaixo disto o mês não atinge o objetivo). "
            f"Preço de tabela = preço a publicar para que, com {desconto_pct} % "
            "de desconto, ainda fiques no preço mínimo. "
            "A taxa turística não está incluída em nenhum destes preços."
            + (
                f" Os preços são por noite e já descontam a taxa de limpeza de "
                f"{euros(taxa_limpeza)} por reserva (cada noite recebe a taxa "
                "÷ estadia média do mês de referência)."
                if taxa_limpeza > 0 else ""
            )
        )

        seccao(
            "3. Estratégia mês a mês",
            "Escolhe um mês para ver de onde vem o objetivo e que preços publicar.",
        )

        coluna_estrategia, _ = st.columns([1, 3])
        with coluna_estrategia:
            mes_estrategia = st.selectbox(
                "Mês do plano", MESES,
                key=f"mes_estrategia_{alojamento_unico}_{ano_plano}",
            )

        indice_mes = MESES.index(mes_estrategia)
        linha_mes = plano.iloc[indice_mes]

        if pd.isna(linha_mes["Objetivo (€)"]) or pd.isna(linha_mes["Preço mínimo (€)"]):
            st.info(
                f"Não há dados de {mes_estrategia.lower()} em anos anteriores "
                "para servir de referência. Quando houver, o plano aparece aqui."
            )
        else:
            ano_ref_mes = int(str(linha_mes["Referência"])[:4])
            ref_mes = mensal_de(alojamento_unico, ano_ref_mes).iloc[indice_mes]

            objetivo_mes = float(linha_mes["Objetivo (€)"])
            rendimento_ref = float(linha_mes["Rendimento referência (€)"])
            media_ref = float(linha_mes["Líquido/noite referência (€)"])
            maximo_ref = float(linha_mes["Máximo/noite referência (€)"])
            ocupacao_ref = float(linha_mes["Ocupação referência (%)"])
            necessario = float(linha_mes["Líquido/noite necessário (€)"])
            minimo_mes = float(linha_mes["Preço mínimo (€)"])
            tabela_mes = float(linha_mes["Preço de tabela (€)"])
            limpeza_mes = float(linha_mes["Limpeza por noite (€)"] or 0.0)
            noites_plano_mes = float(linha_mes["Noites necessárias"])
            reservado_mes = float(linha_mes["Já reservado (€)"])
            noites_reservadas_mes = float(linha_mes["Noites já reservadas"])
            livres_ref = float(ref_mes["Dias disponíveis"] - ref_mes["Noites"])

            cartoes([
                {
                    "rotulo": f"{mes_estrategia} de {ano_ref_mes} (referência)",
                    "valor": euros(rendimento_ref),
                    "nota": h(
                        f"{inteiro(ref_mes['Noites'])} noites · "
                        f"{percentagem(ocupacao_ref, 0)} de ocupação · "
                        f"{euros(media_ref)} por noite"
                    ),
                },
                {
                    "rotulo": f"Objetivo de {mes_estrategia.lower()} de {ano_plano}",
                    "valor": euros(objetivo_mes),
                    "nota": h(f"+{crescimento_pct} % · {euros(necessario)} por noite"),
                    "destaque": True,
                },
                {
                    "rotulo": "Preço de tabela a publicar",
                    "valor": euros(tabela_mes, 0),
                    "nota": h(f"por noite, antes de descontos"),
                },
                {
                    "rotulo": "Preço mínimo",
                    "valor": euros(minimo_mes, 0),
                    "nota": h("por noite, depois de descontos"),
                },
                {
                    "rotulo": "Já reservado",
                    "valor": euros(reservado_mes),
                    "nota": h(
                        f"{inteiro(noites_reservadas_mes)} noites · "
                        f"{percentagem(100 * reservado_mes / objetivo_mes, 0)} do objetivo"
                    ),
                },
            ])

            conselhos = []

            noites_extra = (objetivo_mes - rendimento_ref) / media_ref if media_ref else None
            if ocupacao_ref >= 95:
                conselhos.append(
                    f"**Mês cheio em {ano_ref_mes}** ({percentagem(ocupacao_ref, 0)} "
                    "de ocupação). Não há mais noites para vender, por isso os "
                    f"+{crescimento_pct} % têm de vir todos do preço."
                )
            elif noites_extra is not None and noites_extra <= livres_ref:
                conselhos.append(
                    f"**Há margem na ocupação.** Em {ano_ref_mes} ficaram "
                    f"{inteiro(livres_ref)} noites por vender. Vender mais "
                    f"{max(1, round(noites_extra))} noite(s) ao preço médio de "
                    f"{euros(media_ref)} já dava o objetivo, sem subir preços. "
                    "Se contas ocupar mais, sobe a ocupação esperada no passo 1 "
                    "e o preço necessário desce."
                )
            else:
                conselhos.append(
                    f"**É preciso subir o preço.** Mesmo com o mês cheio ao "
                    f"preço médio de {ano_ref_mes} não chegavas ao objetivo."
                )

            if media_ref and maximo_ref >= 1.25 * media_ref:
                conselhos.append(
                    f"**Procura desigual ao longo do mês.** A melhor noite rendeu "
                    f"{euros(maximo_ref)}, {percentagem(100 * (maximo_ref / media_ref - 1), 0)} "
                    f"acima da média. Usa preços por dia (fins de semana, "
                    "feriados, eventos) em vez de um preço único."
                )

            noites_por_vender = noites_plano_mes - noites_reservadas_mes
            if noites_reservadas_mes > 0 and noites_por_vender > 0.5:
                falta_por_noite = (objetivo_mes - reservado_mes) / noites_por_vender
                if falta_por_noite > necessario * 1.02:
                    final = (
                        "Isso é mais do que o plano previa: sobe o preço das "
                        "datas ainda livres."
                    )
                elif falta_por_noite < necessario * 0.98:
                    final = "Estás à frente do plano: tens folga para descontos."
                else:
                    final = "Estás em linha com o plano."
                conselhos.append(
                    f"**Já reservado:** {euros(reservado_mes)} em "
                    f"{inteiro(noites_reservadas_mes)} noites "
                    f"({euros(reservado_mes / noites_reservadas_mes)} por noite). "
                    f"As {inteiro(noites_por_vender)} noites que faltam têm de "
                    f"render {euros(falta_por_noite)} cada. {final}"
                )
            elif noites_reservadas_mes > 0:
                conselhos.append(
                    f"**Já reservado:** {euros(reservado_mes)} em "
                    f"{inteiro(noites_reservadas_mes)} noites; as noites "
                    "previstas no plano já estão vendidas."
                )

            conselhos.append(
                f"**Descontos.** Com o preço de tabela a {euros(tabela_mes, 0)} "
                f"podes dar até {desconto_pct} % de desconto. Abaixo de "
                f"{euros(minimo_mes, 0)} por noite o mês deixa de atingir o objetivo."
            )

            st.markdown("\n".join(f"- {conselho}" for conselho in conselhos))

            linhas_escada = []
            for desconto in [0, 5, 7, 10, 15, 20]:
                preco = tabela_mes * (1 - desconto / 100)
                recebes = (preco + limpeza_mes) * (1 - comissao_pct / 100)
                linhas_escada.append([
                    h("Preço de tabela" if desconto == 0 else f"Com −{desconto} %"),
                    f'<span class="ad-forte">{h(euros(preco, 0))}</span>',
                    h(euros(recebes)),
                    c_diferenca(recebes - necessario),
                    '<span class="ad-pill sobe">atinge o objetivo</span>'
                    if recebes >= necessario - 0.005
                    else '<span class="ad-pill desce">abaixo do objetivo</span>',
                ])

            tabela_html(
                [
                    f"{mes_estrategia} de {ano_plano}", "Preço por noite",
                    "Recebes por noite", "Face ao necessário", "",
                ],
                linhas_escada,
            )
            st.caption(
                "Recebes por noite = (preço + parte da taxa de limpeza) menos a "
                f"comissão de {decimal(comissao_pct)} %."
            )

        with st.expander("Todos os meses: preço por noite com cada desconto"):
            st.caption(
                "Preço por noite depois de aplicar o desconto ao preço de "
                "tabela. Os valores com ⚠ ficam abaixo do preço mínimo."
            )
            cenarios = core.cenarios_desconto(plano)
            colunas_desconto = [
                coluna for coluna in cenarios.columns if coluna.startswith("−")
            ]

            linhas_cenarios = []
            for indice in range(12):
                linha = cenarios.iloc[indice]
                minimo = linha["Preço mínimo (€)"]
                celulas_linha = [
                    h(linha["Mês"]),
                    f'<span class="ad-forte">{c_euros(linha["Preço de tabela (€)"], 0)}</span>',
                ]
                for coluna in colunas_desconto:
                    valor = linha[coluna]
                    if pd.isna(valor):
                        celulas_linha.append("—")
                    elif valor < minimo - 0.005:
                        celulas_linha.append(
                            f'<span class="ad-menos">{h(euros(valor, 0))} ⚠</span>'
                        )
                    else:
                        celulas_linha.append(h(euros(valor, 0)))
                celulas_linha.append(c_euros(minimo, 0))
                linhas_cenarios.append(celulas_linha)

            tabela_html(
                ["Mês", "Preço de tabela"] + colunas_desconto + ["Preço mínimo"],
                linhas_cenarios,
                apagadas={
                    indice for indice in range(12)
                    if pd.isna(cenarios["Preço de tabela (€)"].astype(float).iloc[indice])
                },
            )

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
            referencia = float(plano_listing["Rendimento referência (€)"].sum())
            reservado = float(plano_listing["Já reservado (€)"].sum())
            linhas_objetivo.append([
                c_alojamento(propriedades.loc[listing, "Nome"]),
                h(propriedades.loc[listing, "Proprietário"]),
                c_euros(referencia, 0),
                f'<span class="ad-forte">{c_euros(objetivo, 0)}</span>',
                c_euros(reservado, 0),
                c_barra(100 * reservado / objetivo if objetivo else None, rosa=True),
            ])

        tabela_html(
            [
                "Alojamento", "Proprietário", "Referência",
                f"Objetivo {ano_plano}", "Já reservado", "Atingido",
            ],
            linhas_objetivo,
            total=[
                "Total", "", c_euros(referencia_total, 0),
                c_euros(objetivo_total, 0), c_euros(reservado_total, 0),
                c_barra(atingido, rosa=True),
            ],
        )
        st.info(
            "Escolhe um alojamento na barra lateral para ver os preços por "
            "noite e ajustar a ocupação esperada."
        )


# =========================================================
# CUSTOS E ROI
# =========================================================

with aba_custos:

    if not alojamento_unico:
        st.info(
            "Escolhe um alojamento na barra lateral para registar os custos "
            "e ver o retorno do investimento."
        )
    else:
        custos_alojamento = [
            registo for registo in (registos_custos or [])
            if registo["listing"] == alojamento_unico
        ]
        custos_ano = [
            registo for registo in custos_alojamento
            if int(registo["cost_year"]) == ano
        ]
        aviso_custos = None

        if not custos_ano:
            anos_guardados = sorted({
                int(registo["cost_year"]) for registo in custos_alojamento
                if int(registo["cost_year"]) < ano
            })
            if anos_guardados:
                custos_ano = [
                    registo for registo in custos_alojamento
                    if int(registo["cost_year"]) == anos_guardados[-1]
                ]
                aviso_custos = (
                    f"Ainda não há custos de {ano}. A lista de categorias vem "
                    f"de {anos_guardados[-1]}; os valores começam vazios."
                )

        ordem = {
            linha[0]: posicao for posicao, linha in enumerate(core.CUSTOS_SUGERIDOS)
        }
        custos_ano = sorted(
            custos_ano,
            key=lambda registo: (
                ordem.get(registo["category"], len(ordem)), registo["category"],
            ),
        )

        if custos_ano:
            valores_guardados = [
                core.meses_do_registo(registo) for registo in custos_ano
            ]
            if aviso_custos:
                # Ano novo: fica a lista de categorias, os valores começam vazios.
                valores_guardados = [
                    ([None] * 12, anualizar) for _, anualizar in valores_guardados
                ]
            base_custos = pd.DataFrame({
                "Categoria": [registo["category"] for registo in custos_ano],
                "Tipo": [registo["kind"] for registo in custos_ano],
                "Anualizar": [anualizar for _, anualizar in valores_guardados],
                **{
                    MESES_CURTOS[indice]: [
                        meses[indice] for meses, _ in valores_guardados
                    ]
                    for indice in range(12)
                },
                "Notas": [registo.get("notes") or "" for registo in custos_ano],
            })
        else:
            base_custos = pd.DataFrame({
                "Categoria": [linha[0] for linha in core.CUSTOS_SUGERIDOS],
                "Tipo": [linha[1] for linha in core.CUSTOS_SUGERIDOS],
                "Anualizar": [linha[2] for linha in core.CUSTOS_SUGERIDOS],
                **{mes: None for mes in MESES_CURTOS},
                "Notas": "",
            })

        for coluna in MESES_CURTOS:
            base_custos[coluna] = pd.to_numeric(base_custos[coluna], errors="coerce")
        base_custos["Anualizar"] = base_custos["Anualizar"].astype(bool)

        seccao(
            f"Custos de {ano}, mês a mês",
            "Escreve o valor de cada fatura no mês em que a pagaste; o total "
            "do ano é calculado por baixo. Marca \"Anualizar\" nas despesas "
            "que caem num mês mas dizem respeito ao ano inteiro (IMI, seguros, "
            "condomínio, obras): o custo é repartido pelos 12 meses.",
        )
        if aviso_custos:
            st.caption(aviso_custos)

        editor_custos = st.data_editor(
            base_custos,
            num_rows="dynamic",
            hide_index=True,
            use_container_width=True,
            key=f"custos_{alojamento_unico}_{ano}",
            column_config={
                "Categoria": st.column_config.TextColumn(required=True),
                "Tipo": st.column_config.SelectboxColumn(
                    options=core.TIPOS_CUSTO, required=True,
                    help=(
                        "Juros e amortização são as duas partes da prestação "
                        "do banco: a amortização é dinheiro que sai, mas "
                        "fica como capital teu no imóvel."
                    ),
                ),
                "Anualizar": st.column_config.CheckboxColumn(
                    help=(
                        "Reparte o total da linha pelos 12 meses, em vez de "
                        "contar tudo no mês em que foi pago."
                    ),
                ),
                **{
                    mes: st.column_config.NumberColumn(
                        min_value=0.0, step=1.0, format="%.2f",
                    )
                    for mes in MESES_CURTOS
                },
                "Notas": st.column_config.TextColumn(),
            },
        )

        st.caption(
            "A comissão do Airbnb não entra aqui: a receita usada já é o que "
            "recebes depois da comissão e sem taxa turística."
        )

        definicoes_alojamento = sorted(
            (
                registo for registo in (registos_definicoes or [])
                if registo["listing"] == alojamento_unico
                and int(registo["cost_year"]) <= ano
            ),
            key=lambda registo: int(registo["cost_year"]),
        )
        guardadas = definicoes_alojamento[-1] if definicoes_alojamento else {}
        mesmo_ano = bool(guardadas) and int(guardadas["cost_year"]) == ano

        seccao(
            "Pressupostos",
            "Capital próprio investido é o dinheiro teu que lá puseste "
            "(entrada, obras, mobília, impostos da compra).",
        )

        d1, d2, d3, d4, d5 = st.columns(5)
        sufixo = f"{alojamento_unico}_{ano}"
        with d1:
            capital = st.number_input(
                "Capital próprio investido (€)", min_value=0.0, step=1000.0,
                value=float(guardadas.get("invested_cents") or 0) / 100,
                key=f"capital_{sufixo}",
            )
        with d2:
            valor_imovel = st.number_input(
                "Valor do imóvel (€)", min_value=0.0, step=1000.0,
                value=float(guardadas.get("property_value_cents") or 0) / 100,
                key=f"imovel_{sufixo}",
            )
        with d3:
            coeficiente_pct = st.number_input(
                "Rendimento tributável (%)", min_value=0.0, max_value=100.0,
                step=1.0, value=float(guardadas.get("taxable_pct") or 35),
                key=f"coeficiente_{sufixo}",
                help="Parte da receita sujeita a IRS no regime simplificado.",
            )
        with d4:
            taxa_irs_pct = st.number_input(
                "Taxa de IRS (%)", min_value=0.0, max_value=60.0, step=0.5,
                value=float(guardadas.get("tax_rate_pct") or 28),
                key=f"taxa_irs_{sufixo}",
            )
        with d5:
            irs_real = st.number_input(
                "IRS real pago (€)", min_value=0.0, step=50.0,
                value=(
                    float(guardadas.get("tax_paid_cents") or 0) / 100
                    if mesmo_ano else 0.0
                ),
                key=f"irs_real_{sufixo}",
                help="Deixa a 0 para usar a estimativa. Quando souberes o valor certo, escreve-o aqui.",
            )

        if tem_custos and not tem_custos_mensais:
            st.info(
                "Para guardar os custos mês a mês faltam duas colunas na "
                "tabela `cost_items`. Corre o SQL do separador Dados no "
                "Supabase e carrega em \"Atualizar dados\"."
            )
        elif tem_custos:
            if st.button("Guardar custos e pressupostos", type="primary"):
                try:
                    guardar_custos(alojamento_unico, ano, editor_custos, {
                        "capital": capital,
                        "imovel": valor_imovel,
                        "coeficiente": coeficiente_pct,
                        "taxa": taxa_irs_pct,
                        "irs_real": irs_real,
                    })
                    limpar_cache()
                    st.rerun()
                except Exception as erro:
                    st.error("Não foi possível guardar os custos.")
                    st.code(str(erro))
        else:
            st.info(
                "Podes experimentar valores, mas para os guardar é preciso "
                "criar as tabelas `cost_items` e `cost_settings` no Supabase. "
                "O SQL está no separador Dados."
            )

        custos_lista = []
        for _, linha in editor_custos.iterrows():
            categoria = linha["Categoria"]
            if pd.isna(categoria) or not str(categoria).strip():
                continue
            anualizar = linha["Anualizar"]
            custos_lista.append({
                "categoria": str(categoria).strip(),
                "tipo": linha["Tipo"],
                "anualizar": False if pd.isna(anualizar) else bool(anualizar),
                "meses": [linha[mes] for mes in MESES_CURTOS],
            })

        # Acrescenta o total anual a cada linha e soma os meses.
        totais_mes = core.custos_por_mes(custos_lista)

        fin = core.resultado_financeiro(
            anual["total"],
            custos_lista,
            capital_investido=capital,
            valor_imovel=valor_imovel,
            coeficiente=coeficiente_pct / 100,
            taxa_irs=taxa_irs_pct / 100,
            irs_real=irs_real,
            noites=anual["noites"],
            media_noite=anual["media_noite"],
            dias_ano=366 if pd.Timestamp(ano, 1, 1).is_leap_year else 365,
        )

        seccao(
            f"Resultado de {ano}",
            (
                f"A receita inclui {euros(anual['futuro'])} de reservas futuras "
                "já confirmadas; o ano ainda não acabou."
                if ano == HOJE.year and anual["futuro"] > 0 else None
            ),
        )

        def nota_percentagem(valor, texto):
            if valor is None:
                return h(texto)
            return h(f"{percentagem(valor)} {texto}")

        cartoes([
            {
                "rotulo": "Resultado final (dinheiro que sobra)",
                "valor": euros(fin["resultado"]),
                "nota": h(f"{euros(fin['resultado'] / 12)} por mês"),
                "destaque": True,
            },
            {
                "rotulo": "Retorno do capital (ROI)",
                "valor": percentagem(fin["roi"]),
                "nota": h(
                    "resultado ÷ capital investido" if capital
                    else "preenche o capital investido"
                ),
            },
            {
                "rotulo": "ROI com amortização",
                "valor": percentagem(fin["roi_com_amortizacao"]),
                "nota": h(
                    f"inclui {euros(fin['amortizacao'])} de capital amortizado"
                ),
            },
            {
                "rotulo": "Receita líquida",
                "valor": euros(fin["receita"]),
                "nota": h("depois da comissão, sem taxa turística"),
            },
            {
                "rotulo": "Despesas e IRS",
                "valor": euros(fin["despesas"] + fin["irs"]),
                "nota": nota_percentagem(
                    100 * (fin["despesas"] + fin["irs"]) / fin["receita"]
                    if fin["receita"] else None,
                    "da receita",
                ),
            },
        ])

        def linha_conta(rotulo, valor, sinal="", forte=False):
            peso = percentagem(100 * valor / fin["receita"]) if fin["receita"] else "—"
            texto = sinal + euros(abs(valor)) if sinal else euros(valor)
            mensal = sinal + euros(abs(valor) / 12) if sinal else euros(valor / 12)
            if forte:
                texto = f'<span class="ad-forte">{h(texto)}</span>'
                return [f"<b>{h(rotulo)}</b>", texto, h(mensal), h(peso)]
            return [h(rotulo), h(texto), h(mensal), h(peso)]

        tabela_html(
            ["Conta de exploração", "Ano", "Média por mês", "% da receita"],
            [
                linha_conta("Receita líquida", fin["receita"], forte=True),
                linha_conta("Custos operacionais", fin["operacionais"], "−"),
                linha_conta("Impostos e taxas (IMI, IVA)", fin["impostos"], "−"),
                linha_conta("Juros do crédito", fin["juros"], "−"),
                linha_conta("Amortização de capital", fin["amortizacao"], "−"),
                linha_conta("Sobra antes de IRS", fin["sobra"], forte=True),
                linha_conta(
                    "IRS pago" if fin["usa_irs_real"] else "IRS estimado",
                    fin["irs"], "−",
                ),
            ],
            total=linha_conta("Resultado final", fin["resultado"]),
        )

        st.caption(
            "IRS estimado = receita × "
            f"{decimal(coeficiente_pct)} % × {decimal(taxa_irs_pct)} %. "
            "É uma aproximação: confirma com o teu contabilista a base e a "
            "taxa do teu caso."
        )

        # ----- Custos por mês -----

        receita_mes = mensal_de(alojamento_unico, ano)["Total do mês (€)"].astype(float)
        custo_mes = totais_mes["custo"]
        pago_mes = totais_mes["pago"]
        total_custos = sum(custo_mes)

        if total_custos > 0:
            seccao(
                "Custos por mês",
                "\"Pago no mês\" são as faturas desse mês. \"Custo do mês\" "
                "reparte pelo ano as linhas marcadas para anualizar. O "
                "resultado é antes de IRS.",
            )

            mes_mais_caro = max(range(12), key=lambda indice: custo_mes[indice])
            maximo_custo = max(custo_mes) or 1.0
            # Com os meses todos iguais não há um "mês mais caro" a destacar.
            if maximo_custo <= 1.05 * total_custos / 12:
                mes_mais_caro = None

            linhas_custo_mes = []
            for indice in range(12):
                resultado_mes = receita_mes.iloc[indice] - custo_mes[indice]
                linhas_custo_mes.append([
                    h(MESES[indice])
                    + (
                        ' <span class="ad-pill desce">mês mais caro</span>'
                        if indice == mes_mais_caro else ""
                    ),
                    c_euros(pago_mes[indice]),
                    c_calor(custo_mes[indice], maximo_custo),
                    c_barra(100 * custo_mes[indice] / total_custos),
                    c_euros(receita_mes.iloc[indice]),
                    c_diferenca(resultado_mes)
                    if receita_mes.iloc[indice] or custo_mes[indice] else "—",
                ])

            tabela_html(
                [
                    "Mês", "Pago no mês", "Custo do mês", "% dos custos do ano",
                    "Receita do mês", "Resultado do mês",
                ],
                linhas_custo_mes,
                total=[
                    "Total",
                    c_euros(sum(pago_mes)),
                    c_euros(total_custos),
                    "",
                    c_euros(receita_mes.sum()),
                    c_diferenca(receita_mes.sum() - total_custos),
                ],
            )

            figura_custos = go.Figure()
            figura_custos.add_bar(
                x=MESES_CURTOS, y=custo_mes, name="Custo do mês",
                marker_color=COR_TEXTO,
                hovertemplate="%{y:,.0f} €<extra>Custo do mês</extra>",
            )
            figura_custos.add_scatter(
                x=MESES_CURTOS, y=receita_mes, name="Receita do mês",
                mode="lines+markers",
                line=dict(color=COR_PRINCIPAL, width=3),
                hovertemplate="%{y:,.0f} €<extra>Receita do mês</extra>",
            )
            mostrar_grafico(estilo_grafico(figura_custos, altura=320))

        seccao("Indicadores")

        cartoes([
            {
                "rotulo": "Margem",
                "valor": percentagem(fin["margem"]),
                "nota": h("do que recebes, quanto fica contigo"),
            },
            {
                "rotulo": "Custo por noite ocupada",
                "valor": euros(fin["custo_por_noite"]),
                "nota": h(
                    f"a noite média rende {euros(anual['media_noite'])}"
                ),
            },
            {
                "rotulo": "Ponto de equilíbrio",
                "valor": (
                    f"{inteiro(fin['noites_equilibrio'])} noites"
                    if fin["noites_equilibrio"] is not None else "—"
                ),
                "nota": h(
                    f"{percentagem(fin['ocupacao_equilibrio'], 0)} de ocupação "
                    f"ou {euros(fin['receita_equilibrio'], 0)} de receita"
                    if fin["receita_equilibrio"] is not None
                    else "preenche os custos"
                ),
            },
            {
                "rotulo": "Anos para recuperar o capital",
                "valor": (
                    decimal(fin["anos_retorno"])
                    if fin["anos_retorno"] is not None else "—"
                ),
                "nota": h("capital ÷ resultado com amortização"),
            },
            {
                "rotulo": "Receita ÷ valor do imóvel",
                "valor": percentagem(fin["rendimento_bruto_imovel"]),
                "nota": h(
                    "rendimento bruto do imóvel" if valor_imovel
                    else "preenche o valor do imóvel"
                ),
            },
        ])

        com_valor = sorted(
            (custo for custo in custos_lista if custo["anual"] > 0),
            key=lambda custo: custo["anual"], reverse=True,
        )
        if com_valor:
            seccao(
                "Custos por categoria",
                "Total do ano de cada linha, do maior para o menor.",
            )
            barras_alojamentos([
                (
                    custo["categoria"],
                    f"{custo['tipo']} · média de {euros(custo['anual'] / 12)} por mês"
                    + (" · anualizado" if custo["anualizar"] else ""),
                    custo["anual"],
                )
                for custo in com_valor
            ])


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
            sum(item.get("outros", 0.0) for item in reembolsos.get(chave, {}).values()),
        )

    def comparacao_airbnb(listas):
        """Tabela mês a mês pela regra do Airbnb, para um ou mais alojamentos."""
        pagamentos = [0.0] * 12
        for listing in listas:
            do_listing = core.pagamentos_mensais(reservas_por_listing[listing], ano)
            pagamentos = [a + b for a, b in zip(pagamentos, do_listing)]
        resumo_rec = core.agregar_mensal(
            [mensal_de(listing, ano) for listing in listas]
        )
        outros = resumo_rec["Outros rendimentos (€)"]
        como_airbnb = [pagamentos[indice] + outros.iloc[indice] for indice in range(12)]

        tabela_html(
            [
                "Mês", "Como no Airbnb", "Reservas (CSV)", "Outros rendimentos",
                "Taxa turística", "Cancelamentos retidos",
                "Estadias por noite (este painel)",
            ],
            [
                [
                    h(MESES[indice]),
                    f'<span class="ad-forte">{c_euros(como_airbnb[indice])}</span>',
                    c_euros(pagamentos[indice]),
                    c_euros(outros.iloc[indice]),
                    c_euros(resumo_rec["Taxa utilizada (€)"].iloc[indice]),
                    c_euros(resumo_rec["Cancelamentos retidos (€)"].iloc[indice]),
                    c_euros(resumo_rec["Total líquido (€)"].iloc[indice]),
                ]
                for indice in range(12)
            ],
            total=[
                "Total",
                c_euros(sum(como_airbnb)),
                c_euros(sum(pagamentos)),
                c_euros(outros.sum()),
                c_euros(resumo_rec["Taxa utilizada (€)"].sum()),
                c_euros(resumo_rec["Cancelamentos retidos (€)"].sum()),
                c_euros(resumo_rec["Total líquido (€)"].sum()),
            ],
        )
        st.caption(
            "\"Como no Airbnb\" = reservas pagas no dia a seguir à entrada "
            "(com taxa turística e cancelamentos) + outros rendimentos. Deve "
            "bater com a página Rendimentos do Airbnb, mês a mês e no total "
            "(pago + próximos pagamentos). Se um mês não bater, há um "
            "pagamento fora das reservas ainda por registar: vê esse mês em "
            "Pagamentos efetuados e regista-o em \"Outros rendimentos\"."
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
                "rotulo": "Outros rendimentos",
                "valor": euros(rec["outros_rendimentos"]),
                "nota": h("pagos pelo Airbnb fora das reservas"),
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
                "nota": h("CSV + outros − reembolsos − taxa turística"),
                "destaque": True,
            },
        ])

        if rec["negativos"]:
            st.caption(
                f"Os CSV já incluem {euros(rec['negativos'])} em valores "
                "negativos; não são subtraídos uma segunda vez."
            )

        seccao(
            "Reembolsos e outros rendimentos",
            "Movimentos que não aparecem nos CSV de reservas: o que devolveste "
            "a hóspedes e o que o Airbnb te pagou fora das reservas (por "
            "exemplo AirCover por danos ou limpezas).",
        )

        if tem_reembolsos:
            guardados = reembolsos.get((alojamento_unico, ano), {})
            base_reembolsos = pd.DataFrame({
                "Mês": MESES,
                "Cancelamentos retidos (€)": mensal_de(alojamento_unico, ano)[
                    "Cancelamentos retidos (€)"
                ].round(2),
                "Reembolso (€)": [
                    guardados.get(mes, {}).get("valor") or None
                    for mes in range(1, 13)
                ],
                "Outros rendimentos (€)": [
                    guardados.get(mes, {}).get("outros") or None
                    for mes in range(1, 13)
                ],
                "Notas": [
                    guardados.get(mes, {}).get("notes", "")
                    for mes in range(1, 13)
                ],
            })
            for coluna in ["Reembolso (€)", "Outros rendimentos (€)"]:
                base_reembolsos[coluna] = pd.to_numeric(base_reembolsos[coluna])
            if not tem_outros:
                base_reembolsos = base_reembolsos.drop(
                    columns=["Outros rendimentos (€)"]
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
                        help="O que devolveste a um hóspede.",
                    ),
                    **(
                        {
                            "Outros rendimentos (€)": st.column_config.NumberColumn(
                                min_value=0.0, step=1.0, format="%.2f €",
                                help=(
                                    "O que o Airbnb te pagou fora das reservas, "
                                    "por exemplo AirCover por danos."
                                ),
                            ),
                        }
                        if tem_outros else {}
                    ),
                    "Notas": st.column_config.TextColumn(),
                },
            )

            if not tem_outros:
                st.caption(
                    "Para registar outros rendimentos (por exemplo AirCover) "
                    "falta uma coluna na tabela. Corre isto no SQL Editor do "
                    "Supabase e depois carrega em \"Atualizar dados\":"
                )
                st.code(
                    "alter table public.monthly_adjustments\n"
                    "    add column if not exists other_income_cents "
                    "bigint not null default 0;",
                    language="sql",
                )

            if st.button("Guardar reembolsos e outros rendimentos", type="primary"):
                try:
                    guardar_reembolsos(
                        alojamento_unico, ano, editor_reembolsos, tem_outros,
                    )
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
            "Comparar com o Airbnb, mês a mês",
            "A primeira coluna segue a regra do Airbnb e deve bater com a "
            "página Rendimentos do Airbnb.",
        )

        comparacao_airbnb([alojamento_unico])

        st.markdown("**Total do ano no Airbnb**")

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
                "Outros rendimentos": rec["outros_rendimentos"],
                "Reembolsos": rec["reembolsos_manuais"],
                "Taxa turística": rec["taxa"],
                "Total final líquido": rec["final"],
            })

        tabela_rec = pd.DataFrame(linhas_rec)
        colunas_valor = [
            "Reservas ativas", "Cancelamentos", "Total dos CSV",
            "Outros rendimentos", "Reembolsos", "Taxa turística",
            "Total final líquido",
        ]

        cartoes([
            {
                "rotulo": "Total dos CSV",
                "valor": euros(tabela_rec["Total dos CSV"].sum()),
                "nota": "",
            },
            {
                "rotulo": "Outros rendimentos",
                "valor": euros(tabela_rec["Outros rendimentos"].sum()),
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

        tabela_html(
            ["Alojamento", "Proprietário"] + colunas_valor,
            [
                [h(linha["Alojamento"]), h(linha["Proprietário"])]
                + [c_euros(linha[coluna]) for coluna in colunas_valor[:-1]]
                + [f'<span class="ad-forte">{c_euros(linha[colunas_valor[-1]])}</span>']
                for _, linha in tabela_rec.iterrows()
            ],
            total=["Total", ""] + [
                c_euros(tabela_rec[coluna].sum()) for coluna in colunas_valor
            ],
        )
        seccao(
            "Comparar com o Airbnb, mês a mês",
            "Soma dos alojamentos selecionados, pela regra do Airbnb. Compara "
            "com a página Rendimentos da conta que tem estes alojamentos.",
        )
        comparacao_airbnb(selecionados)

        st.info(
            "Escolhe um alojamento na barra lateral para registar reembolsos "
            "e outros rendimentos."
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
                "Taxa automática": resumo_taxa["Taxa automática (€)"].sum(),
                "Taxa utilizada": resumo_taxa["Taxa utilizada (€)"].sum(),
            })

        cartoes([
            {
                "rotulo": f"Taxa utilizada em {ano}",
                "valor": euros(anual["taxa"]),
                "nota": h(f"{len(selecionados)} alojamentos"),
            },
        ])
        tabela_html(
            ["Alojamento", "Proprietário", "Estimativa automática", "Taxa utilizada"],
            [
                [
                    h(linha["Alojamento"]), h(linha["Proprietário"]),
                    c_euros(linha["Taxa automática"]),
                    f'<span class="ad-forte">{c_euros(linha["Taxa utilizada"])}</span>',
                ]
                for linha in linhas_taxa
            ],
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

    seccao(
        "Alojamentos",
        "Dá um nome curto a cada anúncio e indica de quem é. A foto é "
        "escolhida pelo início do nome curto (T2, T1+1, T0, T1). Anúncios "
        "ignorados ou sem nenhuma estadia não entram nos relatórios.",
    )

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
        "Anúncio no Airbnb": todos_listings,
        "Nome curto": [propriedades.loc[l, "Nome"] for l in todos_listings],
        "Proprietário": [
            propriedades.loc[l, "Proprietário"] for l in todos_listings
        ],
        "Reservas": [len(reservas_por_listing[l]) for l in todos_listings],
        "Estado": [estado_listing(l) for l in todos_listings],
        "Última atualização": [
            f"{ultimas_atualizacoes[l]:%d/%m/%Y} ({texto_dias(dias_desde_atualizacao(l))})"
            if l in ultimas_atualizacoes else "—"
            for l in todos_listings
        ],
    })

    if tem_propriedades:
        editor_propriedades = st.data_editor(
            base_propriedades,
            disabled=[
                "Anúncio no Airbnb", "Reservas", "Estado", "Última atualização",
            ],
            hide_index=True,
            use_container_width=True,
            key="propriedades",
            column_config={
                "Nome curto": st.column_config.TextColumn(
                    help="Por exemplo: T1+1 - Almeida Garrett",
                ),
                "Proprietário": st.column_config.SelectboxColumn(
                    options=PROPRIETARIOS + [IGNORAR], required=True,
                    help=(
                        "Escolhe \"Ignorar\" para um anúncio que não está "
                        "em uso: deixa de aparecer em todos os relatórios."
                    ),
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
            (
                "coluna other_income_cents em monthly_adjustments",
                tem_outros or not tem_reembolsos,
            ),
            ("cost_items e cost_settings", tem_custos),
            (
                "colunas month_cents e annualize em cost_items",
                tem_custos_mensais or not tem_custos,
            ),
        ] if not existe
    ]

    if em_falta:
        seccao(
            "Configuração em falta no Supabase",
            "Sem estas tabelas a aplicação funciona, mas não guarda nomes "
            "curtos, proprietários, reembolsos nem custos: "
            + ", ".join(em_falta) + ".",
        )
        st.code(SQL_CONFIGURACAO, language="sql")
        st.caption(
            "Depois de correr o SQL, carrega em \"Atualizar dados\" na barra lateral."
        )

    seccao(
        "Calendário do Airbnb (iCal)",
        "As ligações iCal ficam nos Secrets do Streamlit, não no código. "
        "Cada linha usa o início do nome curto do alojamento.",
    )

    ligacoes_guardadas = ligacoes_ical()
    tabela_html(
        ["Alojamento", "Chave nos Secrets", "Ligação iCal"],
        [
            [
                h(propriedades.loc[listing, "Nome"]),
                h(codigo_foto(propriedades.loc[listing, "Nome"])),
                '<span class="ad-pill sobe">configurada</span>'
                if codigo_foto(propriedades.loc[listing, "Nome"]) in ligacoes_guardadas
                else '<span class="ad-pill neutro">em falta</span>',
            ]
            for listing in listings
        ],
    )
    st.code(
        '[ical]\n"t1+1" = "https://www.airbnb.com/calendar/ical/....ics?s=...."\n'
        '"t2" = "https://www.airbnb.com/calendar/ical/....ics?s=...."',
        language="toml",
    )

    seccao("Regras aplicadas")
    st.markdown(
        """
- Cada reserva é identificada por anúncio + código de confirmação.
- O valor de uma reserva é repartido de forma igual pelas suas noites; cada noite conta no mês em que acontece. O dia de saída não conta.
- Os indicadores usam apenas reservas não canceladas e excluem a taxa turística.
- Os cancelamentos que ficaram com valor, os outros rendimentos (por exemplo AirCover) e os reembolsos enviados aparecem à parte, no total do mês e na reconciliação.
- A coluna "Como no Airbnb" da reconciliação soma cada reserva inteira no dia a seguir à entrada, com taxa turística, como faz a página Rendimentos do Airbnb.
- A ocupação divide as noites ocupadas pelos dias em que o alojamento já estava à venda (desde a primeira noite reservada).
- Antes de 2026 a taxa turística considerada é 0 €. O ajuste manual de um mês substitui o cálculo automático.
- A comissão do Airbnb (15,5 % por omissão) está incluída no preço publicado: o preço mínimo do plano é o líquido necessário ÷ 84,5 %.
- O plano de preços usa como referência o mesmo mês do ano anterior; se esse mês ainda não acabou, usa o do ano antes quando rendeu mais.
- A "última atualização" de um alojamento é a data da última importação de CSV que trazia reservas dele. Acima de 14 dias aparece um aviso.
- Nomes e contactos dos hóspedes não são guardados.
"""
    )
