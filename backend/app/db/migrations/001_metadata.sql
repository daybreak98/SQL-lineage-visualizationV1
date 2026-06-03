CREATE TABLE IF NOT EXISTS metadata_imports (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    metadata_version TEXT NOT NULL,
    source_name     TEXT,
    imported_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    table_count     INTEGER DEFAULT 0,
    column_count    INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS table_metadata (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    catalog     TEXT DEFAULT 'default',
    schema_name TEXT DEFAULT 'default',
    table_name  TEXT NOT NULL,
    comment     TEXT,
    table_type  TEXT DEFAULT 'table',
    import_id   INTEGER REFERENCES metadata_imports(id),
    UNIQUE(catalog, schema_name, table_name)
);

CREATE TABLE IF NOT EXISTS column_metadata (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    table_id    INTEGER NOT NULL REFERENCES table_metadata(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    data_type   TEXT,
    comment     TEXT,
    ordinal     INTEGER,
    is_partition BOOLEAN DEFAULT 0,
    nullable    BOOLEAN DEFAULT 1,
    UNIQUE(table_id, name)
);
