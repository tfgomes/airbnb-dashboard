import base64
import html
import re
from datetime import datetime
from pathlib import Path
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
PASTA_FOTOS = Path(__file__).parent / "assets"

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
.ad-cabecalho { display: flex; align-items: center; gap: 18px; margin-bottom: 1.2rem; }
.ad-cabecalho img.ad-foto { width: 132px; height: 88px; object-fit: cover; border-radius: 16px; flex: 0 0 auto; box-shadow: 0 2px 8px rgba(0,0,0,0.10); }
.ad-cabecalho .ad-subtitulo { margin-bottom: 0; }
.ad-miniatura { width: 56px; height: 40px; object-fit: cover; border-radius: 10px; flex: 0 0 auto; }
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
        for posicao, titulo in enumerate(cabecalhos)
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
                    resultado_importacao = guardar_reservas(lote)
                    resultado_importacao["ignoradas"] = lote.attrs.get(
                        "ignoradas", 0,
                    )
                    st.session_state["importacao"] = resultado_importacao
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
        nome_sugerido, dono_sugerido = SUGESTOES.get(
            listing, (listing, PROPRIETARIOS[0]),
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

    with st.expander("Taxa turística, cancelamentos e reembolsos por mês"):
        linhas_movimentos = [
            [
                h(MESES[indice]),
                c_euros(mensal["Earnings bruto (€)"].iloc[indice]),
                c_euros(mensal["Taxa utilizada (€)"].iloc[indice]),
                c_euros(liquido_atual.iloc[indice]),
                c_euros(mensal["Cancelamentos retidos (€)"].iloc[indice]),
                c_euros(mensal["Reembolsos (€)"].iloc[indice]),
                f'<span class="ad-forte">{c_euros(mensal["Total do mês (€)"].iloc[indice])}</span>',
            ]
            for indice in range(12)
        ]
        tabela_html(
            [
                "Mês", "Recebido do Airbnb", "Taxa turística", "Estadias líquidas",
                "Cancelamentos retidos", "Reembolsos", "Total do mês",
            ],
            linhas_movimentos,
            total=[
                "Total",
                c_euros(mensal["Earnings bruto (€)"].sum()),
                c_euros(mensal["Taxa utilizada (€)"].sum()),
                c_euros(liquido_atual.sum()),
                c_euros(mensal["Cancelamentos retidos (€)"].sum()),
                c_euros(mensal["Reembolsos (€)"].sum()),
                c_euros(mensal["Total do mês (€)"].sum()),
            ],
            apagadas=sem_dados,
        )
        st.caption(
            "Estadias líquidas = recebido do Airbnb − taxa turística. "
            "Total do mês = estadias líquidas + cancelamentos retidos − reembolsos."
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
                c_euros(linha["Preço mínimo (€)"], 0),
                c_calor(linha["Preço de tabela (€)"], maximo_tabela, 0),
                c_barra(linha["Objetivo atingido (%)"], rosa=True)
                if linha["Já reservado (€)"] > 0 else "—",
            ])

        tabela_html(
            [
                "Mês", "Referência", "Média ref.", "Melhor noite ref.",
                "Objetivo", "Ocupação", "Líquido necessário",
                "Subida", "Preço mínimo", "Preço de tabela", "Já reservado",
            ],
            linhas_plano,
            total=[
                "Total", "", "", "",
                c_euros(objetivo_total, 0), "", "", "", "", "",
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
        )

        seccao(
            "3. O que o hóspede paga com cada desconto",
            "Preço por noite depois de aplicar o desconto ao preço de tabela. "
            "Os valores com ⚠ ficam abaixo do preço mínimo.",
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
                imagem_html(propriedades.loc[listing, "Nome"], "ad-miniatura")
                + " " + h(propriedades.loc[listing, "Nome"]),
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
        "escolhida pelo início do nome curto (T2, T1+1, T0, T1).",
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
- A comissão do Airbnb (15,5 % por omissão) está incluída no preço publicado: o preço mínimo do plano é o líquido necessário ÷ 84,5 %.
- O plano de preços usa como referência o mesmo mês do ano anterior; se esse mês ainda não acabou, usa o do ano antes quando rendeu mais.
- Nomes e contactos dos hóspedes não são guardados.
"""
    )
