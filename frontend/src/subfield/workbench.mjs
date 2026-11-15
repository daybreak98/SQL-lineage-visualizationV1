// Synthetic SQL fixtures for the public workbench.
export const layeredSQL = `WITH raw_payload AS (
  SELECT context_json
  FROM demo.events
), carried AS (
  SELECT context_json AS payload
  FROM raw_payload
)
SELECT get_json_object(payload, '$.item_id') AS item_id,
       get_json_object(payload, '$.session_key') AS session_key
FROM carried`;
export const twoJsonSQL = `WITH raw_payload AS (
  SELECT t.object_json, t.context_json
  FROM demo.events t
), carried AS (
  SELECT r.object_json AS object_payload, r.context_json AS context_payload
  FROM raw_payload r
)
SELECT get_json_object(c.object_payload, '$.object.identifier') AS object_id,
       get_json_object(c.context_payload, '$.item_id') AS item_id,
       get_json_object(c.context_payload, '$.session_key') AS session_key
FROM carried c`;

export const windowSQL = `WITH ranked AS (
  SELECT g.tag AS tag,
         row_number() OVER (PARTITION BY g.tag ORDER BY e.event_time DESC) AS rn
  FROM demo.events e
  LATERAL VIEW explode(e.tags) g AS tag
)
SELECT tag FROM ranked WHERE rn = 1`;

export const textMapSQL = `SELECT str_to_map(e.attributes, '&', '=')['category'] AS category
FROM demo.events e
WHERE str_to_map(e.attributes, '&', '=')['region'] = 'sample'`;
