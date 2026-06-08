with search_result as (
    select
        a.user_id,
        count(distinct a.search_request_uid) as search_times,
        max(a.search_time) as last_search_time
    from dwd_search_log_di a
    where a.dt = '${dt}'
    group by a.user_id
)
select
    user_id,
    search_times,
    last_search_time
from search_result;
