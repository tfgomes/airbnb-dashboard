-- Correr uma vez no Supabase: SQL Editor > New query > Run
-- Acrescenta os valores mês a mês e a opção de anualizar aos custos.

alter table public.cost_items add column if not exists month_cents jsonb;
alter table public.cost_items
    add column if not exists annualize boolean not null default false;
