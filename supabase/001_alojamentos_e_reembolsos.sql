-- Correr uma vez no Supabase: SQL Editor > New query > Run

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
