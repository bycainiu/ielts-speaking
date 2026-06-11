-- +goose Up

insert into subscription_usage_events (user_id, session_id, credits, mode)
select ps.user_id,
       ps.id,
       case ps.mode
           when 'full_exam' then 3
           else 1
       end,
       ps.mode
from practice_sessions ps
join users u on u.id = ps.user_id
left join subscription_usage_events sue on sue.session_id = ps.id
where ps.status = 'completed'
  and ps.deleted_at is null
  and sue.id is null
  and u.role not in ('admin', 'operator')
  and ps.mode in ('full_exam', 'part_practice', 'topic_practice');

update user_subscriptions us
set credits_used = coalesce((
        select sum(sue.credits)::int
        from subscription_usage_events sue
        where sue.user_id = us.user_id
    ), 0),
    updated_at = now();

-- +goose Down

delete from subscription_usage_events sue
using practice_sessions ps
where sue.session_id = ps.id
  and ps.status = 'completed'
  and ps.completed_at <= '2026-06-10T13:40:00Z'::timestamptz;

update user_subscriptions us
set credits_used = coalesce((
        select sum(sue.credits)::int
        from subscription_usage_events sue
        where sue.user_id = us.user_id
    ), 0),
    updated_at = now();
