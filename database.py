import json
import os
import sqlite3
from datetime import datetime
from typing import Iterable, List, Optional

import pandas as pd


class DatabaseManager:
    """Wrapper around SQLite operations for product and image storage."""

    def __init__(self, db_path: str = "app.db") -> None:
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self) -> None:
        cursor = self.conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT,
                date_added TEXT NOT NULL,
                purchase_price REAL,
                sale_price REAL,
                photo_paths TEXT NOT NULL
            )
        """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS images (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT NOT NULL,
                uploaded_at TEXT NOT NULL,
                product_id INTEGER,
                categories TEXT,
                FOREIGN KEY(product_id) REFERENCES products(id)
            )
            """
        )
        # Ensure columns exist for legacy databases
        cursor.execute("PRAGMA table_info(products)")
        existing_columns = {row["name"] for row in cursor.fetchall()}
        if "purchase_price" not in existing_columns:
            cursor.execute("ALTER TABLE products ADD COLUMN purchase_price REAL")
        if "sale_price" not in existing_columns:
            cursor.execute("ALTER TABLE products ADD COLUMN sale_price REAL")
        self.conn.commit()

    def add_image(self, path: str, uploaded_at: Optional[str] = None, *, categories: Optional[List[str]] = None) -> int:
        uploaded_at = uploaded_at or datetime.utcnow().isoformat()
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT INTO images(path, uploaded_at, product_id, categories) VALUES (?, ?, NULL, ?)",
            (path, uploaded_at, json.dumps(categories or [])),
        )
        self.conn.commit()
        return int(cursor.lastrowid)

    def get_all_images(self) -> pd.DataFrame:
        cursor = self.conn.cursor()
        cursor.execute("SELECT id, path, uploaded_at, product_id, categories FROM images ORDER BY uploaded_at DESC")
        rows = cursor.fetchall()
        if not rows:
            return pd.DataFrame(columns=["id", "path", "uploaded_at", "product_id", "categories"])
        return pd.DataFrame(rows, columns=rows[0].keys())

    def get_unassigned_images(self) -> pd.DataFrame:
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT id, path, uploaded_at, categories FROM images WHERE product_id IS NULL ORDER BY uploaded_at DESC"
        )
        rows = cursor.fetchall()
        if not rows:
            return pd.DataFrame(columns=["id", "path", "uploaded_at", "categories"])
        return pd.DataFrame(rows, columns=rows[0].keys())

    def create_product(
        self,
        name: str,
        description: str,
        image_ids: Iterable[int],
        *,
        date_added: Optional[str] = None,
        purchase_price: Optional[float] = None,
        sale_price: Optional[float] = None,
    ) -> int:
        date_added = date_added or datetime.utcnow().isoformat()
        image_ids = list(image_ids)
        if not image_ids:
            raise ValueError("At least one image must be linked to the product")
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT id, path FROM images WHERE id IN (%s)" % ",".join("?" for _ in image_ids),
            tuple(image_ids),
        )
        rows = cursor.fetchall()
        if len(rows) != len(image_ids):
            raise ValueError("One or more images do not exist")
        photo_paths = [row["path"] for row in rows]
        cursor.execute(
            """
            INSERT INTO products(name, description, date_added, purchase_price, sale_price, photo_paths)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (name, description, date_added, purchase_price, sale_price, json.dumps(photo_paths)),
        )
        product_id = int(cursor.lastrowid)
        cursor.execute(
            "UPDATE images SET product_id = ? WHERE id IN (%s)" % ",".join("?" for _ in image_ids),
            (product_id, *image_ids),
        )
        self.conn.commit()
        return product_id

    def get_products(self) -> pd.DataFrame:
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT id, name, description, date_added, purchase_price, sale_price, photo_paths
            FROM products
            ORDER BY date_added DESC
            """
        )
        rows = cursor.fetchall()
        if not rows:
            return pd.DataFrame(
                columns=[
                    "id",
                    "name",
                    "description",
                    "date_added",
                    "purchase_price",
                    "sale_price",
                    "photo_paths",
                ]
            )
        frame = pd.DataFrame(rows, columns=rows[0].keys())
        frame["photo_paths"] = frame["photo_paths"].apply(lambda value: json.loads(value) if value else [])
        for column in ("purchase_price", "sale_price"):
            if column in frame.columns:
                frame[column] = frame[column].where(frame[column].notna(), None)
        return frame

    def delete_product(self, product_id: int) -> None:
        cursor = self.conn.cursor()
        cursor.execute("UPDATE images SET product_id = NULL WHERE product_id = ?", (product_id,))
        cursor.execute("DELETE FROM products WHERE id = ?", (product_id,))
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()


__all__ = ["DatabaseManager"]
