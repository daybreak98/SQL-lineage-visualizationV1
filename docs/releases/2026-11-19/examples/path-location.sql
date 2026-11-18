-- Public synthetic SQL: paste this text as a custom submission.
WITH raw_payload AS (
  SELECT event_payload
  FROM lab.media_events
), carried AS (
  SELECT event_payload AS payload
  FROM raw_payload
)
SELECT get_json_object(payload, '$.media_id') AS media_id,
       get_json_object(payload, '$.session_id') AS session_id
FROM carried
