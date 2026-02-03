"""剧本杀对话记忆：使用 SQLite3 存储场景内角色对话。"""

import sqlite3
from pathlib import Path
from typing import Optional


class StoryMemory:
    """使用 SQLite3 存储对话过程，包含场景 ID/名称、角色 ID/名称、消息内容。"""

    def __init__(self, story_id: str, db_dir: str | Path = "."):
        self.db_path = Path(db_dir) / f"{story_id}.db"
        self._conn: Optional[sqlite3.Connection] = None
        self._ensure_table()

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def _ensure_table(self) -> None:
        conn = self._get_conn()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scene_id TEXT NOT NULL,
                scene_name TEXT NOT NULL,
                character_id TEXT NOT NULL,
                character_name TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now', 'localtime'))
            )
        """)
        conn.commit()

    def add(
        self,
        scene_id: str,
        scene_name: str,
        character_id: str,
        character_name: str,
        content: str,
    ) -> int:
        """写入一条对话记录，返回自增 id。"""
        conn = self._get_conn()
        cur = conn.execute(
            """
            INSERT INTO messages (scene_id, scene_name, character_id, character_name, content)
            VALUES (?, ?, ?, ?, ?)
            """,
            (scene_id, scene_name, character_id, character_name, content),
        )
        conn.commit()
        return cur.lastrowid or 0

    def list_by_scene(self, scene_id: str) -> list[dict]:
        """按场景 ID 查询该场景下所有对话，按时间顺序。"""
        conn = self._get_conn()
        cur = conn.execute(
            """
            SELECT id, scene_id, scene_name, character_id, character_name, content, created_at
            FROM messages
            WHERE scene_id = ?
            ORDER BY id
            """,
            (scene_id,),
        )
        return [dict(row) for row in cur.fetchall()]

    def list_all(self) -> list[dict]:
        """查询全部对话，按 id 升序。"""
        conn = self._get_conn()
        cur = conn.execute(
            """
            SELECT id, scene_id, scene_name, character_id, character_name, content, created_at
            FROM messages
            ORDER BY id
            """
        )
        return [dict(row) for row in cur.fetchall()]

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> "StoryMemory":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
