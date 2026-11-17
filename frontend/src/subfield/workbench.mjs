// Synthetic SQL for the workbench demos.
export const layeredSQL = `WITH raw_payload AS (
  SELECT event_payload
  FROM lab.media_events
), carried AS (
  SELECT event_payload AS payload
  FROM raw_payload
)
SELECT get_json_object(payload, '$.media_id') AS media_id,
       get_json_object(payload, '$.session_id') AS session_id
FROM carried`;
export const twoJsonSQL = `WITH raw_payload AS (
  SELECT t.context_payload, t.event_payload
  FROM lab.media_events t
), carried AS (
  SELECT r.context_payload AS share_payload, r.event_payload AS refer_payload
  FROM raw_payload r
)
SELECT get_json_object(c.share_payload, '$.media.category') AS media_category,
       get_json_object(c.refer_payload, '$.media_id') AS media_id,
       get_json_object(c.refer_payload, '$.session_id') AS session_id
FROM carried c`;
