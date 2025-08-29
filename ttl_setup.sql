DROP TABLE IF EXISTS ttl;

CREATE TABLE IF NOT EXISTS ttl (
    thread_id TEXT PRIMARY KEY,
    last_message_time DATETIME
);