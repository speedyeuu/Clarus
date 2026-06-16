-- 1. Odstranění starých, nevyhovujících constraintů
ALTER TABLE indicator_readings DROP CONSTRAINT IF EXISTS indicator_readings_date_indicator_name_key;
ALTER TABLE daily_scores DROP CONSTRAINT IF EXISTS daily_scores_date_key;

-- 2. Přidání nových kompozitních unikátních constraintů (pro podporu více párů ve stejný den)
ALTER TABLE indicator_readings ADD CONSTRAINT uq_indicator_readings_date_name_pair UNIQUE (date, indicator_name, pair);
ALTER TABLE daily_scores ADD CONSTRAINT uq_daily_scores_date_pair UNIQUE (date, pair);
