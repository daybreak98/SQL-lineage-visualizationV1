with a as (select id from t1),
broken as (select from),
c as (select id from t2)
select a.id
from a
join c on a.id = c.id

