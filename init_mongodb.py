from __future__ import annotations

from mongo_gaikyo import ensure_indexes, get_client, get_database_name, ping_database


def main() -> None:
    client = get_client()
    try:
        ping_database(client)
        db = client[get_database_name()]
        ensure_indexes(db)
        print(f"[OK] MongoDB初期化が完了しました: db={db.name}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
