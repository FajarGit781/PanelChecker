-- ============================================================
-- Panel Tracker — skema cloud Supabase (sudah diterapkan ke project)
-- Disimpan di sini sebagai referensi / untuk membuat ulang project.
-- ============================================================
-- Daftar user yang boleh akses + peran (admin / engineer / vendor / viewer)
create table public.app_users (
  email text primary key, full_name text default '',
  role text not null default 'engineer' check (role in ('admin','engineer','vendor','viewer')),
  created_at timestamptz not null default now()
);

create schema if not exists private;
revoke all on schema private from public, anon;
grant usage on schema private to authenticated;

create or replace function private.pt_is_member() returns boolean
language sql stable security definer set search_path = '' as $$
  select exists (select 1 from public.app_users u
                 where lower(u.email) = lower(coalesce(auth.jwt() ->> 'email', '')));
$$;
create or replace function private.pt_can_write() returns boolean
language sql stable security definer set search_path = '' as $$
  select exists (select 1 from public.app_users u
                 where lower(u.email) = lower(coalesce(auth.jwt() ->> 'email', ''))
                   and u.role in ('admin','engineer','vendor'));
$$;
-- last-write-wins: update dengan updated_at lebih lama diabaikan
create or replace function private.pt_touch() returns trigger
language plpgsql set search_path = '' as $$
begin
  if tg_op = 'UPDATE' and new.updated_at < old.updated_at then return null; end if;
  new.server_updated_at := now();
  new.updated_by := auth.uid();
  return new;
end; $$;
revoke execute on all functions in schema private from public, anon;
grant execute on function private.pt_is_member() to authenticated;
grant execute on function private.pt_can_write() to authenticated;

-- Tabel data: projects, sites, panels, panel_checks, issues, attachments, check_templates
-- (kolom: uuid PK, kolom data, *_uuid relasi, updated_at text, deleted int, server_updated_at, updated_by)
-- Lihat app/cloud.py → MAP untuk daftar kolom lengkap.
-- Setiap tabel: trigger private.pt_touch, RLS aktif,
--   select  → private.pt_is_member()
--   insert/update → private.pt_can_write()
-- Storage bucket privat 'panel-photos' (maks 5 MB, jpeg/png) dengan policy yang sama.

-- Menambah anggota tim:
-- insert into public.app_users(email, full_name, role) values ('nama@perusahaan.com', 'Nama', 'engineer');

-- =====================================================================================
-- v2.6 HARDENING KEAMANAN (sudah diterapkan ke project: migrasi security_hardening_v26
-- dan fix_pt_touch_text_timestamp)
-- =====================================================================================
-- * anon (publishable key tanpa login) tidak punya hak apa pun di schema public/private.
-- * authenticated hanya SELECT/INSERT/UPDATE, dibatasi RLS; tidak ada DELETE/TRUNCATE (hapus = soft delete).
-- * app_users: tiap user hanya bisa membaca barisnya sendiri; tidak ada yang bisa mengubah peran dari aplikasi.
-- * pt_touch: updated_at di masa depan (> now()+10 menit) dikoreksi ke jam server, supaya klien tidak bisa
--   "mengunci" data dari perubahan orang lain.
-- * private.pt_audit: riwayat setiap INSERT/UPDATE (siapa, kapan, data lama & baru) untuk investigasi /
--   pemulihan. Tidak bisa dibaca dari aplikasi; hanya admin lewat SQL Editor.
-- * Bucket panel-photos: privat, maks 5 MB per file, hanya JPEG/PNG, tidak ada policy delete.
--
-- Contoh pemulihan punch yang terhapus/terubah (SQL Editor):
--   select at, actor_email, op, old_row->>'title', old_row->>'status', old_row->>'deleted'
--   from private.pt_audit where tbl = 'issues' and new_row->>'code' = 'GA2-0003' order by at desc;
--
-- Reset password user oleh admin (user lupa password):
--   update auth.users set encrypted_password = extensions.crypt('PasswordSementara123', extensions.gen_salt('bf'))
--   where email = 'budi@paneltracker.local';
--   → user login dengan password sementara, lalu aplikasi mewajibkan ganti password bila lemah.

-- =====================================================================================================
-- v2.7.1: pengaturan bersama tim (kop report, logo, tanda tangan, daftar pilihan, target default)
-- Satu baris per key; uuid = uuid5(namespace aplikasi, 'team_setting:' || key) sehingga semua laptop
-- meng-upsert baris yang sama. Logo disimpan base64 (dibatasi < 300 KB oleh aplikasi).
-- =====================================================================================================
create table if not exists public.team_settings (
  uuid uuid primary key,
  key text not null unique check (key ~ '^[a-z0-9_]{1,64}$'),
  value text not null default '' check (length(value) <= 1500000),
  updated_at text,
  deleted integer not null default 0,
  server_updated_at timestamptz not null default now(),
  updated_by uuid
);
create index if not exists team_settings_server_updated_at on public.team_settings (server_updated_at, uuid);
alter table public.team_settings enable row level security;
revoke all on public.team_settings from anon, authenticated;
grant select, insert, update on public.team_settings to authenticated;
create policy "member read" on public.team_settings for select to authenticated using ((select private.pt_is_member()));
create policy "writer insert" on public.team_settings for insert to authenticated with check ((select private.pt_can_write()));
create policy "writer update" on public.team_settings for update to authenticated
  using ((select private.pt_can_write())) with check ((select private.pt_can_write()));
create trigger pt_touch before insert or update on public.team_settings for each row execute function private.pt_touch();
create trigger pt_audit after insert or update on public.team_settings for each row execute function private.pt_audit_fn();

-- =====================================================================================================
-- v2.7.2: viewer web publik (tanpa login) — migrasi public_panel_view_fn + Edge Function "panel-view"
-- Data SATU panel per uuid (dari label QR). Tidak ada pencarian tag / daftar panel.
-- Hanya service_role (Edge Function) yang boleh memanggil; anon/authenticated tidak.
-- service_role tetap tanpa hak SELECT tabel. Kode function: web-viewer/supabase/functions/panel-view.
-- Matikan akses publik: hapus Edge Function panel-view (dan/atau: drop function public.pt_panel_view(uuid);)
-- =====================================================================================================
-- create or replace function public.pt_panel_view(p_id uuid) returns jsonb
--   language sql stable security definer set search_path = '' as $$ ... $$;   (lihat migrasi di project)
-- revoke all on function public.pt_panel_view(uuid) from public, anon, authenticated;
-- grant execute on function public.pt_panel_view(uuid) to service_role;
