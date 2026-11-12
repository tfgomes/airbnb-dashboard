-- Correr uma vez no Supabase: SQL Editor > New query > Run

create table if not exists public.cost_items (
    listing text not null,
    cost_year integer not null,
    category text not null,
    kind text not null default 'Operacional',
    monthly_cents bigint,
    annual_cents bigint,
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

alter table public.cost_items enable row level security;
alter table public.cost_settings enable row level security;

grant select, insert, update, delete on public.cost_items to service_role;
grant select, insert, update, delete on public.cost_settings to service_role;
