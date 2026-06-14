with c01 as (select id, c01 from t01),
c02 as (select id, c02 from t02),
c03 as (select id, c03 from t03),
c04 as (select id, c04 from t04),
c05 as (select id, c05 from t05),
c06 as (select id, c06 from t06),
c07 as (select id, c07 from t07),
c08 as (select id, c08 from t08),
c09 as (select id, c09 from t09),
c10 as (select id, c10 from t10),
c11 as (select id, c11 from t11),
c12 as (select id, c12 from t12),
c13 as (select id, c13 from t13),
c14 as (select id, c14 from t14),
c15 as (select id, c15 from t15),
c16 as (select id, c16 from t16),
c17 as (select id, c17 from t17),
c18 as (select id, c18 from t18),
c19 as (select id, c19 from t19),
c20 as (select id, c20 from t20)
select
  c01.id,
  c02.c02,
  c03.c03,
  c04.c04,
  c05.c05,
  c06.c06,
  c07.c07,
  c08.c08,
  c09.c09,
  c10.c10,
  c11.c11,
  c12.c12,
  c13.c13,
  c14.c14,
  c15.c15,
  c16.c16,
  c17.c17,
  c18.c18,
  c19.c19,
  c20.c20
from c01
left join c02 on c01.id = c02.id
left join c03 on c01.id = c03.id
left join c04 on c01.id = c04.id
left join c05 on c01.id = c05.id
left join c06 on c01.id = c06.id
left join c07 on c01.id = c07.id
left join c08 on c01.id = c08.id
left join c09 on c01.id = c09.id
left join c10 on c01.id = c10.id
left join c11 on c01.id = c11.id
left join c12 on c01.id = c12.id
left join c13 on c01.id = c13.id
left join c14 on c01.id = c14.id
left join c15 on c01.id = c15.id
left join c16 on c01.id = c16.id
left join c17 on c01.id = c17.id
left join c18 on c01.id = c18.id
left join c19 on c01.id = c19.id
left join c20 on c01.id = c20.id

