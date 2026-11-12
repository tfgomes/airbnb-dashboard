# Painel de Alojamentos — contexto do projeto

Atualizado em 12/11/2026. Este ficheiro resume o que o projeto é, como está
construído e as regras de negócio decididas. Serve para retomar o trabalho
numa conversa nova sem perder contexto.

## 1. Objetivo

Aplicação privada para acompanhar quatro alojamentos no Airbnb: rendimento,
ocupação, calendário, preços do ano seguinte, custos e retorno do
investimento. Substitui folhas de Excel mantidas à mão.

Objetivo de negócio do Tiago: aumentar o rendimento de cada mês cerca de 10 %
face ao mesmo mês do ano anterior.

## 2. Alojamentos e proprietários

| Nome curto | Anúncio no Airbnb (título nos CSV) | Proprietário | Foto |
|---|---|---|---|
| T1+1 - Almeida Garrett | Apartamento Moderno c/Piscina, a 12 min da Praia | Tiago | `assets/t1+1.jpg` |
| T2 - Gil Vicente | Apartamento com dois quartos perto da praia 550m | Guilhermino (pai) | `assets/t2.jpg` |
| T0 - Bayview | Charme Studio with Pool, Oldtown - 300m to Beach | Guilhermino | `assets/t0.jpg` |
| T1 - Dunfermline | Magnifico Apto renovado c/piscina 12 min da praia | Guilhermino | `assets/t1.jpg` |

- O Tiago analisa o T1+1 em separado; os três do pai aparecem um a um e
  agregados na carteira "Guilhermino".
- Existe um anúncio chamado "outro" que não está em uso: é ignorado.
- O T1+1 começou em 16/07/2025. Os do pai têm histórico desde 2019.
- A atribuição do T1 - Dunfermline ao anúncio "Magnifico Apto..." foi feita
  por exclusão; o Tiago não a contestou.

## 3. Arquitetura (custo zero)

| Peça | Função |
|---|---|
| Streamlit Community Cloud | Aloja a app (privada). Publica sozinho a cada alteração no `main`. |
| Supabase (plano gratuito) | Base de dados Postgres. |
| GitHub `tfgomes/airbnb-dashboard` (privado) | Código, testes, backups. |
| GitHub Actions | Todos os dias às 06:17 UTC lê as tabelas (evita a pausa do Supabase por inatividade) e guarda um backup em CSV em `backups/`. |

Secrets:
- Streamlit: `[supabase] url, key` e `[ical]` (uma ligação iCal por
  alojamento, com as chaves `"t0"`, `"t1"`, `"t1+1"`, `"t2"`).
- GitHub Actions: `SUPABASE_URL`, `SUPABASE_KEY`.
- As ligações iCal e as chaves nunca vão para o repositório.

Limites a ter em conta: o Streamlit gratuito só permite uma app privada e
adormece ao fim de 12 h sem visitas; o Supabase gratuito pausa com uma semana
de pouca atividade (o workflow diário evita isso) e devolve no máximo 1000
linhas por pedido (a app pagina; o workflow de backup ainda não).

## 4. Estrutura do repositório

| Ficheiro | Conteúdo |
|---|---|
| `streamlit_app.py` | Interface, leitura e escrita no Supabase, HTML/CSS dos cartões e tabelas. |
| `core.py` | Todos os cálculos, sem Streamlit. |
| `tests/test_core.py` | Testes dos cálculos com os dados reais de `backups/`. |
| `tests/smoke_app.py` | Corre a app inteira com Streamlit, Plotly e Supabase simulados. |
| `supabase/001…004*.sql` | Criação e alteração das tabelas. O mesmo SQL, completo e repetível, aparece no separador Dados da app. |
| `.github/workflows/supabase-keepalive.yml` | Keep-alive e backup diário. |
| `assets/` | Fotos dos alojamentos; o nome do ficheiro é o início do nome curto. |
| `backups/` | CSV das tabelas, sem dados pessoais. |

Antes de publicar:

```
python -m py_compile streamlit_app.py core.py
python -m pytest -q tests
python tests/smoke_app.py
```

## 5. Base de dados

| Tabela | Chave | Para que serve |
|---|---|---|
| `reservations` | listing + confirmation_code | Reservas importadas dos CSV (sem nomes nem contactos). Valores em cêntimos. |
| `tourist_tax_monthly` | listing + ano + mês | Taxa turística real de um mês (substitui a estimativa). |
| `properties` | listing | Nome curto e proprietário. "Ignorar" tira o anúncio dos relatórios. |
| `monthly_adjustments` | listing + ano + mês | Reembolsos enviados a hóspedes (`refund_cents`) e outros rendimentos pagos pelo Airbnb fora das reservas, como AirCover (`other_income_cents`). |
| `cost_items` | listing + ano + categoria | Custos: 12 valores mensais (`month_cents`, jsonb), tipo e opção de anualizar. |
| `cost_settings` | listing + ano | Capital investido, valor do imóvel, percentagens de IRS, IRS real. |

As tabelas além das duas primeiras são opcionais: se faltarem (ou faltar uma
coluna nova), a app funciona e mostra o SQL a correr.

## 6. Regras de negócio

Rendimento e ocupação
- O valor de cada reserva (coluna Earnings, já depois da comissão do Airbnb)
  é repartido de forma igual pelas noites. Cada noite conta no mês em que
  acontece; o dia de saída não conta.
- Os indicadores usam só reservas não canceladas e excluem a taxa turística.
- Cancelamentos que ficaram com valor, outros rendimentos e reembolsos
  aparecem à parte e entram no "total do mês", não na média por noite.
- Ocupação = noites ocupadas ÷ dias em que o alojamento já estava à venda
  (desde a primeira noite). No ano corrente conta só até ontem. Um anúncio
  sem nenhuma noite num ano não conta para a ocupação desse ano.
- As percentagens face ao ano anterior só aparecem em meses fechados em que
  o ano anterior esteve à venda o mês inteiro.

Taxa turística
- 2 € por hóspede e por noite, de abril a outubro, até 7 noites por reserva,
  desde 01/04/2026. Antes de 2026 é 0 €.
- O regulamento isenta menores de 13 anos, mas o Airbnb não distingue idades,
  por isso é cobrada a todos os hóspedes.
- A estimativa automática falha quando a reserva foi feita antes de o Airbnb
  passar a cobrar a taxa. O valor real de cada mês está no relatório mensal
  do Airbnb, linha "Impostos remetidos", e regista-se como ajuste manual.
- T1+1 em 2026 (valores reais): abril 44, maio 134, junho 158, julho 84,
  agosto 240, setembro 126, outubro 164 €. Total 950 €.

Comissão e preços
- Desde outubro/novembro de 2026 o Airbnb cobra 15,5 % incluídos no preço publicado
  (antes eram 3 % ao anfitrião). O plano assume sempre 15,5 %.
- O T1+1 cobra 50 € de taxa de limpeza por reserva.
- Plano de preços, por mês: objetivo = rendimento do mês de referência ×
  (1 + crescimento). Líquido por noite necessário = objetivo ÷ noites
  esperadas. Preço mínimo = líquido necessário ÷ (1 − comissão) − taxa de
  limpeza ÷ estadia média. Preço de tabela = preço mínimo ÷ (1 − desconto
  médio). Os descontos aplicam-se ao preço por noite, não à limpeza.
- Referência = mesmo mês do ano anterior; se esse mês ainda não acabou, usa
  o do ano antes quando rendeu mais.

Comparação com o Airbnb
- A página Rendimentos do Airbnb soma cada reserva inteira no dia a seguir
  à entrada, inclui a taxa turística e os pagamentos fora das reservas.
- T1+1 em 2026: painel 30.909,75 € + taxa 950 € + cancelamento retido
  308,70 € + AirCover 184,50 € = 32.352,95 €, igual ao Airbnb.
- A coluna "Como no Airbnb" da Reconciliação reproduz essa regra.

Custos e ROI
- Custos inseridos mês a mês. "Anualizar" reparte o total da linha pelos 12
  meses (IMI, seguros, condomínio, obras).
- A comissão do Airbnb não é uma linha de custo: a receita já vem depois dela.
- A prestação do banco divide-se em juros e amortização de capital.
- IRS estimado = receita × 35 % × 28 %, editável; pode ser substituído pelo
  IRS real. É uma aproximação a confirmar com o contabilista.
- Resultado final = receita − todas as despesas − IRS. ROI = resultado ÷
  capital próprio investido; há também o ROI que soma a amortização.

Importação de CSV
- Aceita datas mês/dia/ano e dia/mês/ano (depende do idioma da conta).
- Reservas antigas sem valor (Earnings vazio) são ignoradas e contadas.
- A mesma reserva vinda de duas contas não é conflito; valores diferentes
  para a mesma reserva são recusados.
- Nomes e contactos dos hóspedes nunca são guardados.
- Cada importação marca a data em todas as reservas que vinham nos ficheiros.
  A "última atualização" de um alojamento é a mais recente dessas datas;
  aparece na barra lateral, no cabeçalho e no separador Dados, com aviso
  acima de 14 dias.

## 7. Separadores da app

1. Resumo anual: indicadores, progresso face ao ano anterior com a linha do
   objetivo (mês a mês por omissão, com um interruptor para ver acumulado),
   evolução por ano (com o número de alojamentos ativos em cada ano),
   rendimento por alojamento e proprietário.
2. Todos os apartamentos: aparece sempre com os quatro, seja qual for a
   carteira. Gráfico circular com o valor e a percentagem de cada um (até
   hoje ou ano inteiro com reservas futuras), tabela comparativa, rendimento
   e ocupação mês a mês por apartamento.
3. Calendário: uma linha por alojamento, entradas e saídas dos próximos 14
   dias, noites livres dos próximos 30. Com iCal mostra também bloqueios e
   reservas ainda não importadas.
4. Mensal: gráfico mês a mês com o ano anterior, tabelas de rendimento e
   acumulados, preço por noite (mínimo, média, máximo, potencial), matriz
   por alojamento.
5. Plano de preços: resumo do ano e estratégia mês a mês com conselhos.
6. Custos e ROI: por alojamento e ano.
7. Reconciliação: totais, reembolsos e outros rendimentos, comparação com o
   Airbnb mês a mês.
8. Taxa turística: estimativa e valores reais por mês.
9. Dados: nomes, proprietários, estado dos anúncios, iCal, SQL, regras.

Aspeto: os gráficos de barras de rendimento usam um degradê magenta → rosa →
coral, como os do Airbnb. O Plotly não pinta degradês numa barra, por isso
cada barra é desenhada em camadas sobrepostas (`barras_degrade`). No gráfico
mensal há duas barras por mês: o ano escolhido e o anterior. A ocupação usa
sempre as mesmas cores: verde a 100 %, verde claro de 90 % a 99 %, laranja
abaixo de 90 %. Os cabeçalhos das tabelas são azul-escuros; nas tabelas
editáveis são azul-claros (`dataframeHeaderBackgroundColor` no
`.streamlit/config.toml`), porque aí a cor do texto não se pode mudar.
A carteira que abre por omissão é a do Tiago; a ordem é Tiago, Guilhermino,
Todos.

## 8. Forma de trabalhar

- O Claude tem acesso de leitura e escrita ao repositório. Cada alteração
  vai num branch `claude/...`; o Tiago cria o pull request e faz merge, e o
  Streamlit publica.
- O Claude não consegue correr o Streamlit nem ligar ao Supabase ou ao
  Airbnb: valida com os testes e com a app simulada, e o Tiago confirma na
  app real.
- Alterações à base de dados: o Tiago corre o SQL no SQL Editor do Supabase
  e carrega em "Atualizar dados".
- O Tiago é engenheiro de software (Databricks, PySpark). Quando há ações
  a fazer fora do código, os passos vão numerados.

## 9. Pendentes

- Registar na app: reembolso de 240 € (setembro de 2026, T1+1) e AirCover de
  184,50 € (janeiro de 2026, T1+1).
- Taxa turística real dos três alojamentos do pai (está na estimativa).
- Confirmar se os alojamentos do pai cobram taxa de limpeza e quanto.
- Confirmar se as ligações iCal já estão nos Secrets e se o Airbnb responde
  a partir do Streamlit.
- A ocupação esperada e a taxa de limpeza do plano de preços não ficam
  guardadas entre sessões.
- Confirmar com o contabilista a base e a taxa de IRS.
- Fechar a diferença entre o painel e o Airbnb na conta do pai (deve ser
  taxa turística e pagamentos fora das reservas).
