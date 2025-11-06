
-- SELECT * from question_attempts WHERE session_id > 15 order by session_id

SELECT * from question_attempts where is_correct == '0' and session_id > 83 GROUP BY word_id ;