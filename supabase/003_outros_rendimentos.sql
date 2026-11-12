-- Correr uma vez no Supabase: SQL Editor > New query > Run
-- Acrescenta os "outros rendimentos" (por exemplo AirCover) aos ajustes mensais.

alter table public.monthly_adjustments
    add column if not exists other_income_cents bigint not null default 0;
