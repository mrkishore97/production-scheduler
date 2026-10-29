-- Production Scheduler: safe saving.
--
-- Run once in Supabase: Dashboard -> SQL Editor -> New query -> paste this
-- whole file -> Run. Running it again is harmless (it replaces the function).
--
-- save_schedule() applies one save in a single transaction: either every
-- change is written or none is. It refuses the save when someone else has
-- saved since the caller loaded the schedule (the data_version in app_meta
-- moved on), so one session can't silently overwrite another's work.

-- The version row must exist so saves can lock it.
insert into public.app_meta (key, value)
select 'data_version', '0'
where not exists (select 1 from public.app_meta where key = 'data_version');

create or replace function public.save_schedule(
  expected_version text,
  upserts jsonb default '[]'::jsonb,  -- rows to write; rows without "id" are inserted
  deletes jsonb default '[]'::jsonb   -- ids of rows to delete
) returns text
language plpgsql
as $$
declare
  current_version text;
  next_version bigint;
begin
  -- Lock the version row: a second save waits here until this one finishes.
  select value into current_version
  from public.app_meta
  where key = 'data_version'
  for update;

  if coalesce(current_version, '0') is distinct from coalesce(expected_version, '0') then
    raise exception 'schedule_conflict'
      using errcode = 'PT409',  -- PostgREST answers HTTP 409
            detail = format('Saved version is %s; this session loaded %s.', current_version, expected_version);
  end if;

  delete from public.order_book
  where id::text in (select jsonb_array_elements_text(deletes));

  update public.order_book o
  set wo = r.wo,
      quote = r.quote,
      po_number = r.po_number,
      status = r.status,
      customer_name = r.customer_name,
      model_description = r.model_description,
      scheduled_date = r.scheduled_date,
      completion_date = r.completion_date,
      price = r.price,
      uploaded_name = r.uploaded_name
  from jsonb_populate_recordset(null::public.order_book, upserts) r
  where r.id is not null and o.id = r.id;

  insert into public.order_book (
    wo, quote, po_number, status, customer_name, model_description,
    scheduled_date, completion_date, price, uploaded_name
  )
  select r.wo, r.quote, r.po_number, r.status, r.customer_name, r.model_description,
         r.scheduled_date, r.completion_date, r.price, r.uploaded_name
  from jsonb_populate_recordset(null::public.order_book, upserts) r
  where r.id is null;

  next_version := (case when current_version ~ '^[0-9]+$' then current_version::bigint else 0 end) + 1;
  update public.app_meta set value = next_version::text where key = 'data_version';
  if not found then
    insert into public.app_meta (key, value) values ('data_version', next_version::text);
  end if;

  return next_version::text;
end;
$$;

grant execute on function public.save_schedule(text, jsonb, jsonb) to anon, authenticated;

-- Make the new function visible to the API straight away.
notify pgrst, 'reload schema';
