"""One-time, idempotent schema bridge for Stage 6 SQLite installations."""

from sqlalchemy import inspect, text


# SQLite can add these columns without rebuilding populated Stage 6 tables.
# ORM defaults keep future writes current; SQL defaults make legacy rows valid.
LEGACY_STAGE6_COLUMNS = {
    "users": {
        "email": "VARCHAR(160) NOT NULL DEFAULT ''",
        "national_id": "VARCHAR(10) NOT NULL DEFAULT ''",
    },
    "children": {
        "national_id": "VARCHAR(10) NOT NULL DEFAULT ''",
    },
    "skill_modules": {
        "code": "VARCHAR(30) NOT NULL DEFAULT ''",
        "level": "VARCHAR(30) NOT NULL DEFAULT 'foundation'",
        "style_tags_json": "TEXT NOT NULL DEFAULT '[]'",
        "scenario_ids_json": "TEXT NOT NULL DEFAULT '[]'",
        "prerequisite_ids_json": "TEXT NOT NULL DEFAULT '[]'",
    },
    "dynamic_forms": {
        "form_type": "VARCHAR(30) NOT NULL DEFAULT 'assessment'",
        "use_case": "VARCHAR(80) NOT NULL DEFAULT 'general'",
        "version": "INTEGER NOT NULL DEFAULT 1",
        "settings_json": "TEXT NOT NULL DEFAULT '{}'",
        "scoring_json": "TEXT NOT NULL DEFAULT '{}'",
        "published_at": "DATETIME",
        "archived_at": "DATETIME",
    },
    "form_responses": {
        "assignment_id": "INTEGER",
        "form_version": "INTEGER NOT NULL DEFAULT 1",
        "status": "VARCHAR(20) NOT NULL DEFAULT 'submitted'",
        "score_total": "FLOAT",
        "subscale_scores_json": "TEXT NOT NULL DEFAULT '{}'",
        "result_key": "VARCHAR(80) NOT NULL DEFAULT ''",
        "updated_at": "DATETIME NOT NULL DEFAULT '1970-01-01 00:00:00.000000'",
        "submitted_at": "DATETIME",
    },
    "organizations": {
        "contact_email": "VARCHAR(160) NOT NULL DEFAULT ''",
        "address": "VARCHAR(700) NOT NULL DEFAULT ''",
        "website": "VARCHAR(300) NOT NULL DEFAULT ''",
        "logo_url": "VARCHAR(500) NOT NULL DEFAULT ''",
        "profile_form_id": "INTEGER",
        "profile_data_json": "TEXT NOT NULL DEFAULT '{}'",
        "updated_at": "DATETIME NOT NULL DEFAULT '1970-01-01 00:00:00.000000'",
    },
    "sponsored_projects": {
        "contract_id": "INTEGER",
    },
}


def upgrade_legacy_stage6_schema(engine, metadata):
    """Reconcile a populated Stage 6 SQLite schema with current metadata."""
    if engine.dialect.name != "sqlite":
        raise RuntimeError("ارتقای خودکار دیتابیس قدیمی فقط برای SQLite پشتیبانی می‌شود.")

    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    if "users" not in existing_tables or "skill_modules" not in existing_tables:
        raise RuntimeError("ساختار دیتابیس با نسخه شناخته‌شده استیج ۶ مطابقت ندارد.")
    if "alembic_version" in existing_tables:
        raise RuntimeError("این دیتابیس قبلاً وارد چرخه Migration شده است.")

    added_columns = []
    with engine.begin() as connection:
        for table_name, definitions in LEGACY_STAGE6_COLUMNS.items():
            if table_name not in existing_tables:
                continue
            current_columns = {
                item["name"] for item in inspect(connection).get_columns(table_name)
            }
            for column_name, ddl in definitions.items():
                if column_name in current_columns:
                    continue
                connection.exec_driver_sql(
                    f'ALTER TABLE "{table_name}" ADD COLUMN "{column_name}" {ddl}'
                )
                added_columns.append(f"{table_name}.{column_name}")

        # Replace the sentinel only for rows that existed before Stage 15.
        for table_name in ("form_responses", "organizations"):
            if table_name in existing_tables:
                connection.execute(
                    text(
                        f'UPDATE "{table_name}" SET updated_at = created_at '
                        "WHERE updated_at = '1970-01-01 00:00:00.000000'"
                    )
                )

    before_create = set(inspect(engine).get_table_names())
    metadata.create_all(bind=engine, checkfirst=True)
    after_create = set(inspect(engine).get_table_names())

    created_indexes = 0
    for table in metadata.sorted_tables:
        for index in table.indexes:
            before = {
                item["name"] for item in inspect(engine).get_indexes(table.name)
            }
            if index.name not in before:
                index.create(bind=engine, checkfirst=True)
                created_indexes += 1

    with engine.connect() as connection:
        integrity = connection.exec_driver_sql("PRAGMA integrity_check").scalar()
    if integrity != "ok":
        raise RuntimeError(f"بررسی یکپارچگی SQLite ناموفق بود: {integrity}")

    return {
        "legacy_version": "stage-6",
        "columns_added": len(added_columns),
        "column_names": added_columns,
        "tables_created": len(after_create - before_create),
        "indexes_created": created_indexes,
        "integrity": integrity,
    }
