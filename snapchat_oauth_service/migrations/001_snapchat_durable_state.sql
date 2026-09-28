CREATE TABLE IF NOT EXISTS snapchat_oauth_intents (
    intent_hash TEXT PRIMARY KEY,
    created_at BIGINT NOT NULL,
    expires_at BIGINT NOT NULL,
    consumed_at BIGINT
);

CREATE TABLE IF NOT EXISTS snapchat_oauth_states (
    state_hash TEXT PRIMARY KEY,
    browser_hash TEXT NOT NULL,
    created_at BIGINT NOT NULL,
    expires_at BIGINT NOT NULL,
    consumed_at BIGINT
);

CREATE TABLE IF NOT EXISTS snapchat_oauth_tokens (
    id INTEGER PRIMARY KEY,
    access_cipher TEXT,
    refresh_cipher TEXT,
    expires_at BIGINT,
    scope TEXT,
    profile_id TEXT,
    username TEXT,
    connected INTEGER NOT NULL DEFAULT 0,
    updated_at BIGINT NOT NULL
);

CREATE TABLE IF NOT EXISTS snapchat_publications (
    profile_id TEXT NOT NULL,
    publication_id TEXT NOT NULL,
    state TEXT NOT NULL,
    attempt_count INTEGER NOT NULL,
    description TEXT,
    description_hash TEXT,
    media_sha256 TEXT,
    media_duration REAL,
    media_width INTEGER,
    media_height INTEGER,
    remote_media_id TEXT,
    remote_spotlight_id TEXT,
    correlation_id TEXT,
    created_at BIGINT NOT NULL,
    updated_at BIGINT NOT NULL,
    submit_started_at BIGINT,
    final_at BIGINT,
    last_error TEXT,
    PRIMARY KEY (profile_id, publication_id)
);

CREATE INDEX IF NOT EXISTS idx_snapchat_publications_state_created
ON snapchat_publications (profile_id, state, created_at);

CREATE INDEX IF NOT EXISTS idx_snapchat_publications_remote_spotlight
ON snapchat_publications (remote_spotlight_id);
