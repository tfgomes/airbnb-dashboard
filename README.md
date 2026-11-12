# Painel de Alojamentos

Aplicação privada em Streamlit para acompanhar o rendimento, a ocupação e os
preços de vários alojamentos no Airbnb, por proprietário.

## Estrutura

| Ficheiro | Para que serve |
|---|---|
| `streamlit_app.py` | Interface e leitura/escrita no Supabase |
| `core.py` | Todos os cálculos (sem Streamlit), para poderem ser testados |
| `tests/test_core.py` | Testes dos cálculos com os dados reais de `backups/` |
| `tests/smoke_app.py` | Corre a app inteira com Streamlit/Plotly/Supabase simulados |
| `supabase/001_alojamentos_e_reembolsos.sql` | Tabelas `properties` e `monthly_adjustments` |
| `supabase/002_custos_e_roi.sql` | Tabelas `cost_items` e `cost_settings` (custos e ROI) |
| `supabase/003_outros_rendimentos.sql` | Coluna dos outros rendimentos (ex.: AirCover) nos ajustes mensais |
| `.github/workflows/supabase-keepalive.yml` | Mantém o Supabase ativo e faz backup diário |
| `backups/` | Backup em CSV das tabelas (sem dados pessoais) |
| `assets/` | Foto de cada alojamento; o ficheiro tem o início do nome curto (`t2.jpg`, `t1+1.jpg`, `t0.jpg`, `t1.jpg`) |

## Correr localmente (Codespaces)

```
uv sync
uv run streamlit run streamlit_app.py
```

É preciso o ficheiro `.streamlit/secrets.toml` (nunca vai para o Git):

```
[supabase]
url = "SUPABASE_PROJECT_URL"
key = "SUPABASE_SECRET_KEY"
```

## Antes de publicar

```
uv run python -m py_compile streamlit_app.py core.py
uv run --with pytest pytest -q tests
uv run python tests/smoke_app.py
```

## Regras principais

- Chave de uma reserva: anúncio + código de confirmação.
- O valor da reserva é repartido de forma igual pelas noites; cada noite conta
  no mês em que acontece.
- Os indicadores excluem a taxa turística e as reservas canceladas.
- Cancelamentos com valor retido e reembolsos enviados entram no "total do mês"
  e na reconciliação, não na média por noite.
- A importação aceita datas em mês/dia/ano e dia/mês/ano (depende do idioma
  da conta Airbnb) e ignora reservas antigas que venham sem valor.
- A comissão do Airbnb (15,5 % por omissão) está incluída no preço publicado.
- Plano de preços: objetivo mensal = mês de referência × (1 + crescimento);
  preço mínimo = líquido por noite ÷ (1 − comissão); preço de tabela =
  preço mínimo ÷ (1 − desconto médio).

## Calendário (iCal)

As ligações iCal do Airbnb ficam nos Secrets do Streamlit, nunca no repositório.
A chave é o início do nome curto do alojamento:

```
[ical]
"t1+1" = "https://www.airbnb.com/calendar/ical/....ics?s=...."
"t2" = "https://www.airbnb.com/calendar/ical/....ics?s=...."
```

Sem ligações (ou se o Airbnb não responder), o calendário usa só as reservas
guardadas a partir dos CSV.
