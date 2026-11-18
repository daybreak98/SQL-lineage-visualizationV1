-- Public synthetic SQL. Select Spark in the workbench.
WITH c AS (SELECT s.j AS raw FROM src s)
SELECT get_json_object(c.raw, '$.a.x') AS hit, c.raw AS whole FROM c
