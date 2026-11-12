"""Corre a aplicação inteira com Streamlit, Plotly e Supabase simulados.

Não substitui abrir a app a sério: só garante que o código percorre todos os
separadores sem erros, com os dados reais do backup, em vários cenários.

    python tests/smoke_app.py
"""

import runpy
import sys
import types
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))


class Parar(BaseException):
    pass


class Contexto:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class FalsoStreamlit(types.ModuleType):
    def __init__(self, escolhas, botoes):
        super().__init__("streamlit")
        self.escolhas = escolhas
        self.botoes = botoes
        self.saida = []
        self.session_state = {}
        self.secrets = {"supabase": {"url": "x", "key": "y"}}
        self.sidebar = Contexto()
        cfg = types.SimpleNamespace()
        for nome in ["NumberColumn", "TextColumn", "SelectboxColumn"]:
            setattr(cfg, nome, lambda *a, **k: {"cfg": k})
        self.column_config = cfg
        self.cache_data = self._cache()
        self.cache_resource = self._cache()

    def _cache(self):
        def decorador(funcao=None, **kwargs):
            if callable(funcao):
                return funcao
            return lambda f: f
        decorador.clear = lambda: None
        return decorador

    def _regista(self, tipo, *args):
        self.saida.append((tipo, args))

    def set_page_config(self, **k): pass
    def markdown(self, texto, unsafe_allow_html=False):
        assert isinstance(texto, str)
        if unsafe_allow_html:
            # HTML indentado seria tratado como bloco de código pelo Markdown.
            assert "\n    <" not in texto.replace("<style>", ""), texto[:200]
        self._regista("markdown", texto)
    def caption(self, t): self._regista("caption", t)
    def info(self, t): self._regista("info", t)
    def warning(self, t): self._regista("warning", t)
    def success(self, t): self._regista("success", t)
    def error(self, t): self._regista("error", t)
    def code(self, t, language=None): self._regista("code", t)
    def stop(self): raise Parar()
    def rerun(self): raise Parar()
    def columns(self, n):
        return [Contexto() for _ in range(n if isinstance(n, int) else len(n))]
    def tabs(self, nomes): return [Contexto() for _ in nomes]
    def expander(self, nome): return Contexto()
    def file_uploader(self, *a, **k): return None
    def button(self, rotulo, **k): return rotulo in self.botoes
    def download_button(self, rotulo, dados, **k):
        assert isinstance(dados, bytes) and len(dados) > 0
    def radio(self, rotulo, opcoes, **k):
        return self.escolhas.get(rotulo, opcoes[0])
    def selectbox(self, rotulo, opcoes, index=0, **k):
        opcoes = list(opcoes)
        escolha = self.escolhas.get(rotulo)
        if callable(escolha):
            return escolha(opcoes)
        return escolha if escolha in opcoes else opcoes[index]
    def slider(self, rotulo, minimo, maximo, valor, **k): return valor
    def number_input(self, rotulo, value=0.0, **k):
        return self.escolhas.get(rotulo, value)
    def dataframe(self, tabela, **k):
        assert isinstance(tabela, pd.DataFrame)
        self._regista("dataframe", tabela)
    def data_editor(self, tabela, disabled=(), column_config=None, **k):
        assert isinstance(tabela, pd.DataFrame)
        for coluna in list(disabled) + list(column_config or {}):
            assert coluna in tabela.columns, coluna
        self._regista("data_editor", tabela)
        return tabela.copy()
    def plotly_chart(self, figura, **k):
        self._regista("grafico", figura)


class FalsaFigura:
    def __init__(self):
        self.tracos = []
    def _traco(self, **k):
        for eixo in ("x", "y"):
            assert len(list(k[eixo])) == 12, (eixo, len(list(k[eixo])))
        self.tracos.append(k)
    def add_bar(self, **k): self._traco(**k)
    def add_scatter(self, **k): self._traco(**k)
    def update_layout(self, **k): return self
    def update_xaxes(self, **k): return self
    def update_yaxes(self, **k): return self


class FalsaConsulta:
    def __init__(self, base, nome):
        self.base, self.nome = base, nome
        self.operacao = "select"
        self.filtros = {}
        self.carga = None
    def select(self, colunas):
        self.colunas = colunas.split(",")
        return self
    def range(self, a, b): return self
    def eq(self, campo, valor):
        self.filtros[campo] = valor
        return self
    def upsert(self, carga, on_conflict=None):
        self.operacao, self.carga = "upsert", carga
        return self
    def delete(self):
        self.operacao = "delete"
        return self
    def execute(self):
        if self.nome not in self.base.tabelas:
            raise RuntimeError(f"relation {self.nome} does not exist")
        if self.operacao == "select":
            linhas = self.base.tabelas[self.nome]
            for linha in linhas:
                for coluna in self.colunas:
                    assert coluna in linha, (self.nome, coluna)
            return types.SimpleNamespace(data=linhas)
        self.base.escritas.append((self.nome, self.operacao, self.carga, self.filtros))
        return types.SimpleNamespace(data=[])


class FalsaBase:
    def __init__(self, tabelas):
        self.tabelas = tabelas
        self.escritas = []
    def table(self, nome):
        return FalsaConsulta(self, nome)


def correr(nome, tabelas, escolhas=None, botoes=(), segredos=None):
    st = FalsoStreamlit(escolhas or {}, set(botoes))
    st.secrets.update(segredos or {})
    base = FalsaBase(tabelas)

    plotly = types.ModuleType("plotly")
    go = types.ModuleType("plotly.graph_objects")
    go.Figure = FalsaFigura
    plotly.graph_objects = go
    supabase = types.ModuleType("supabase")
    supabase.create_client = lambda url, key: base

    sys.modules.update({
        "streamlit": st, "plotly": plotly,
        "plotly.graph_objects": go, "supabase": supabase,
    })

    try:
        runpy.run_path(str(RAIZ / "streamlit_app.py"), run_name="__main__")
    except Parar:
        pass

    erros = [args for tipo, args in st.saida if tipo == "error"]
    assert not erros, (nome, erros, [a for t, a in st.saida if t == "code"])
    graficos = sum(1 for tipo, _ in st.saida if tipo == "grafico")
    tabelas_vistas = sum(1 for tipo, _ in st.saida if tipo in ("dataframe", "data_editor"))
    print(f"OK  {nome}: {graficos} gráficos, {tabelas_vistas} tabelas, {len(base.escritas)} escritas")
    return st, base


def ler(nome):
    tabela = pd.read_csv(RAIZ / "backups" / nome)
    tabela = tabela.astype(object).where(tabela.notna(), None)
    return tabela.to_dict("records")


reservas = ler("reservations.csv")
taxas = ler("tourist_tax_monthly.csv")
LISTING = reservas[0]["listing"]

# 1. Estado atual: um alojamento, tabelas novas ainda não criadas.
st, _ = correr("um alojamento, sem tabelas novas", {
    "reservations": reservas, "tourist_tax_monthly": taxas,
})
assert any(t == "code" and "create table" in a[0] for t, a in st.saida)

# 2. Um alojamento com as tabelas novas e um reembolso em setembro.
st, base = correr("um alojamento, com reembolso", {
    "reservations": reservas, "tourist_tax_monthly": taxas,
    "properties": [{"listing": LISTING, "display_name": "T1+1 - Almeida Garrett", "owner": "Tiago"}],
    "monthly_adjustments": [{"listing": LISTING, "adj_year": 2026, "adj_month": 9, "refund_cents": 24000, "notes": "Matas"}],
}, escolhas={"Total apresentado no Airbnb (€)": 32325.95})
texto = " ".join(a[0] for t, a in st.saida if t == "markdown")
assert "T1+1 - Almeida Garrett" in texto
assert "30.909,75 €" in texto          # rendimento líquido 2026
assert "30.978,45 €" in texto          # total final: 32.168,45 − 240 − 950

# 3. Guardar (botões carregados): escreve nas tabelas certas.
for botao, tabela in [
    ("Guardar reembolsos", "monthly_adjustments"),
    ("Guardar ajustes da taxa", "tourist_tax_monthly"),
    ("Guardar alojamentos", "properties"),
]:
    _, base = correr(f"botão '{botao}'", {
        "reservations": reservas, "tourist_tax_monthly": taxas,
        "properties": [], "monthly_adjustments": [
            {"listing": LISTING, "adj_year": 2026, "adj_month": 9, "refund_cents": 24000, "notes": "Matas"},
        ],
    }, botoes=[botao])
    assert base.escritas and all(e[0] == tabela for e in base.escritas), base.escritas
    if tabela == "tourist_tax_monthly":
        gravados = {e[2]["tax_month"]: e[2]["manual_tax_cents"] for e in base.escritas if e[1] == "upsert"}
        assert gravados == {4: 4400, 5: 13400, 6: 15800, 7: 8400, 8: 24000, 9: 12600}, gravados
    if tabela == "monthly_adjustments":
        gravados = [e[2] for e in base.escritas if e[1] == "upsert"]
        assert len(gravados) == 1 and gravados[0]["refund_cents"] == 24000

# 4. Quatro alojamentos, dois proprietários.
nomes = ["Apartamento A", "Apartamento B", "Apartamento C", "Apartamento D"]
quatro = [dict(r, listing=nome) for nome in nomes for r in reservas]
quatro_taxas = [dict(t, listing=nome) for nome in nomes for t in taxas]
props = [
    {"listing": nomes[0], "display_name": "T1+1 - Almeida Garrett", "owner": "Tiago"},
    {"listing": nomes[1], "display_name": "Casa 1", "owner": "Guilhermino"},
    {"listing": nomes[2], "display_name": "Casa 2", "owner": "Guilhermino"},
    # o quarto fica por configurar de propósito
]
tabelas4 = {
    "reservations": quatro, "tourist_tax_monthly": quatro_taxas,
    "properties": props, "monthly_adjustments": [],
}
st, _ = correr("quatro alojamentos, todos", tabelas4)
texto = " ".join(a[0] for t, a in st.saida if t == "markdown")
assert "Todos os alojamentos" in texto and "123.639,00 €" in texto   # 4 × 30.909,75
assert "Rendimento por proprietário" in texto

st, _ = correr("carteira Guilhermino", tabelas4, escolhas={"Carteira": "Guilhermino"})
texto = " ".join(a[0] for t, a in st.saida if t == "markdown")
assert "Alojamentos de Guilhermino" in texto and "61.819,50 €" in texto

correr("Guilhermino, um alojamento", tabelas4, escolhas={"Carteira": "Guilhermino", "Alojamento": "Casa 2"})
correr("ano 2025", tabelas4, escolhas={"Ano": 2025})
correr("planear o ano corrente", {"reservations": reservas, "tourist_tax_monthly": taxas}, escolhas={"Ano a planear": 2026})

# 5. Custos e ROI guardados, e gravação.
tabelas_custos = {
    "reservations": reservas, "tourist_tax_monthly": taxas,
    "properties": [], "monthly_adjustments": [],
    "cost_items": [
        {"listing": LISTING, "cost_year": 2026, "category": "Limpezas", "kind": "Operacional",
         "monthly_cents": 40000, "annual_cents": None, "notes": ""},
        {"listing": LISTING, "cost_year": 2026, "category": "Crédito: amortização de capital",
         "kind": "Amortização de capital", "monthly_cents": 28500, "annual_cents": None, "notes": ""},
        {"listing": LISTING, "cost_year": 2026, "category": "IMI", "kind": "Impostos e taxas",
         "monthly_cents": None, "annual_cents": 27600, "notes": ""},
    ],
    "cost_settings": [
        {"listing": LISTING, "cost_year": 2026, "invested_cents": 6500000, "property_value_cents": 0,
         "taxable_pct": 35, "tax_rate_pct": 28, "tax_paid_cents": 0},
    ],
}
st, _ = correr("custos e ROI", tabelas_custos)
texto = " ".join(a[0] for t, a in st.saida if t == "markdown")
# receita 31.218,45 (estadias + cancelamento retido); despesas 4.800 + 3.420 + 276;
# IRS 31.218,45 × 35 % × 28 % = 3.059,41; resultado 19.663,04.
assert "19.663,04 €" in texto
assert "30,3 %" in texto                      # ROI: 19.663,04 ÷ 65.000

_, base = correr("botão guardar custos", tabelas_custos, botoes=["Guardar custos e pressupostos"])
escritas = [(e[0], e[1]) for e in base.escritas]
assert escritas == [("cost_items", "delete"), ("cost_items", "upsert"), ("cost_settings", "upsert")], escritas
gravados = {linha["category"]: linha for linha in base.escritas[1][2]}
assert gravados["Limpezas"]["monthly_cents"] == 40000 and gravados["IMI"]["annual_cents"] == 27600
assert base.escritas[2][2]["invested_cents"] == 6500000

# 6. Calendário com iCal (descarga simulada) e sem iCal.
import io
import urllib.request

ICAL = (
    "BEGIN:VCALENDAR\r\nVERSION:2.0\r\n"
    "BEGIN:VEVENT\r\nDTEND;VALUE=DATE:20261116\r\nDTSTART;VALUE=DATE:20261110\r\n"
    "DESCRIPTION:Reservation URL: https://www.airbnb.com/hosting/reservations/details/HMA3A3TEJW\r\n"
    "SUMMARY:Reserved\r\nEND:VEVENT\r\n"
    "BEGIN:VEVENT\r\nDTEND;VALUE=DATE:20261128\r\nDTSTART;VALUE=DATE:20261124\r\n"
    "SUMMARY:Airbnb (Not available)\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n"
)


class FalsaResposta(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): return False


original = urllib.request.urlopen
urllib.request.urlopen = lambda pedido, timeout=None: FalsaResposta(ICAL.encode())
try:
    st, _ = correr("calendário com iCal", {
        "reservations": reservas, "tourist_tax_monthly": taxas,
    }, segredos={"ical": {"t1+1": "https://exemplo/ical.ics"}})
finally:
    urllib.request.urlopen = original
texto = " ".join(a[0] for t, a in st.saida if t == "markdown")
assert "ad-cal-ev bloqueio" in texto and "ad-cal-ev duvida" in texto
assert any(t == "warning" and "já não" in a[0] for t, a in st.saida)

urllib.request.urlopen = lambda pedido, timeout=None: (_ for _ in ()).throw(OSError("sem rede"))
try:
    st, _ = correr("iCal indisponível", {
        "reservations": reservas, "tourist_tax_monthly": taxas,
    }, segredos={"ical": {"t1+1": "https://exemplo/ical.ics"}})
finally:
    urllib.request.urlopen = original
assert any(t == "warning" and "iCal" in a[0] for t, a in st.saida)

# 7. Base de dados vazia.
st, _ = correr("sem reservas", {"reservations": [], "tourist_tax_monthly": []})
assert any(t == "info" for t, _ in st.saida)

print("Tudo certo.")
