-- Claude Monet (Flask) -> Supabase schema
-- Run this in Supabase: SQL Editor

-- 1) Categories
create table if not exists public.categories (
  id bigserial primary key,
  slug text not null unique,
  label text not null,
  created_at timestamptz not null default now()
);

-- 2) Menu items
create table if not exists public.menu_items (
  id bigserial primary key,
  category_slug text not null references public.categories(slug) on update cascade on delete restrict,
  title text not null,
  description text not null,
  ingredients text,
  allergens text,
  price_cents integer not null default 0,
  image_path text,
  wine_title text,
  wine_text text,
  created_at timestamptz not null default now()
);

create index if not exists menu_items_category_slug_idx on public.menu_items(category_slug);

-- 3) Bookings
create table if not exists public.bookings (
  id bigserial primary key,
  full_name text not null,
  email text,
  phone text not null,
  booking_date date not null,
  booking_time time not null,
  guests integer not null,
  notes text,
  cart_total_cents integer not null default 0,
  created_at timestamptz not null default now()
);

create index if not exists bookings_created_at_idx on public.bookings(created_at desc);

-- 4) Booking items (what customer ordered)
create table if not exists public.booking_items (
  id bigserial primary key,
  booking_id bigint not null references public.bookings(id) on delete cascade,
  menu_item_id bigint references public.menu_items(id) on delete set null,
  title text not null,
  qty integer not null default 1,
  unit_price_cents integer not null default 0,
  line_total_cents integer not null default 0,
  image_path text,
  created_at timestamptz not null default now()
);

create index if not exists booking_items_booking_id_idx on public.booking_items(booking_id);

-- =========================
-- SECURITY (IMPORTANT)
-- =========================
-- By default, tables are readable/writable depending on RLS.
-- For a simple demo without auth, you can disable RLS:
-- alter table public.categories disable row level security;
-- alter table public.menu_items disable row level security;
-- alter table public.bookings disable row level security;
-- alter table public.booking_items disable row level security;

-- OR (recommended) enable RLS + add permissive policies for anon role (demo only):
alter table public.categories enable row level security;
alter table public.menu_items enable row level security;
alter table public.bookings enable row level security;
alter table public.booking_items enable row level security;

-- Categories
drop policy if exists "anon_read_categories" on public.categories;
create policy "anon_read_categories"
on public.categories for select
to anon
using (true);

drop policy if exists "anon_write_categories" on public.categories;
create policy "anon_write_categories"
on public.categories for insert
to anon
with check (true);

drop policy if exists "anon_update_categories" on public.categories;
create policy "anon_update_categories"
on public.categories for update
to anon
using (true)
with check (true);

-- Menu items
drop policy if exists "anon_read_menu_items" on public.menu_items;
create policy "anon_read_menu_items"
on public.menu_items for select
to anon
using (true);

drop policy if exists "anon_write_menu_items" on public.menu_items;
create policy "anon_write_menu_items"
on public.menu_items for insert
to anon
with check (true);

drop policy if exists "anon_update_menu_items" on public.menu_items;
create policy "anon_update_menu_items"
on public.menu_items for update
to anon
using (true)
with check (true);

-- Bookings
drop policy if exists "anon_read_bookings" on public.bookings;
create policy "anon_read_bookings"
on public.bookings for select
to anon
using (true);

drop policy if exists "anon_write_bookings" on public.bookings;
create policy "anon_write_bookings"
on public.bookings for insert
to anon
with check (true);

-- Booking items
drop policy if exists "anon_read_booking_items" on public.booking_items;
create policy "anon_read_booking_items"
on public.booking_items for select
to anon
using (true);

drop policy if exists "anon_write_booking_items" on public.booking_items;
create policy "anon_write_booking_items"
on public.booking_items for insert
to anon
with check (true);
