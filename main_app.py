import json
import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Dict, List

import pyautogui

from database import DatabaseManager
from image_handler import ImageHandler


class FinnPublisher:
    """Stub for future finn.no integration using pyautogui."""

    def __init__(self) -> None:
        try:
            self.screen_size = pyautogui.size()
        except Exception:
            self.screen_size = None

    def prepare_listing(self, product: Dict) -> str:
        if not self.screen_size:
            return "Автоматизация finn.no недоступна в текущей среде"
        return (
            "Готово к автоматической публикации на finn.no. "
            f"Размер экрана: {self.screen_size.width}x{self.screen_size.height}"
        )


class InventoryApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Product Manager")
        self.db = DatabaseManager()
        self.image_handler = ImageHandler(base_dir=os.path.join(os.getcwd(), "images"))
        self.publisher = FinnPublisher()
        self.preview_images: List[tk.PhotoImage] = []

        self._build_ui()
        self._populate_images_tab()
        self._populate_products_table()

    def _build_ui(self) -> None:
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill=tk.BOTH, expand=True)

        # Tab for uploading photos
        self.add_photo_frame = ttk.Frame(notebook)
        notebook.add(self.add_photo_frame, text="Добавить фото")
        self._build_add_photo_tab(self.add_photo_frame)

        # Tab for creating products
        self.create_product_frame = ttk.Frame(notebook)
        notebook.add(self.create_product_frame, text="Создать товар")
        self._build_create_product_tab(self.create_product_frame)

    def _build_add_photo_tab(self, frame: ttk.Frame) -> None:
        upload_button = ttk.Button(frame, text="Выбрать изображения", command=self._upload_images)
        upload_button.pack(pady=10)

        self.preview_container = ttk.LabelFrame(frame, text="Предпросмотр")
        self.preview_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.preview_canvas = tk.Canvas(self.preview_container)
        self.preview_canvas.pack(fill=tk.BOTH, expand=True)

    def _build_create_product_tab(self, frame: ttk.Frame) -> None:
        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)

        # Inputs
        input_frame = ttk.LabelFrame(frame, text="Информация о товаре")
        input_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

        ttk.Label(input_frame, text="Название").grid(row=0, column=0, sticky="w")
        self.name_entry = ttk.Entry(input_frame)
        self.name_entry.grid(row=1, column=0, sticky="ew", pady=5)

        ttk.Label(input_frame, text="Описание").grid(row=2, column=0, sticky="w")
        self.description_text = tk.Text(input_frame, height=6)
        self.description_text.grid(row=3, column=0, sticky="ew", pady=5)

        create_button = ttk.Button(input_frame, text="Создать", command=self._create_product)
        create_button.grid(row=4, column=0, sticky="e", pady=5)

        # Image selection
        images_frame = ttk.LabelFrame(frame, text="Выберите изображения")
        images_frame.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
        images_frame.rowconfigure(0, weight=1)
        images_frame.columnconfigure(0, weight=1)

        columns = ("path", "categories", "assigned")
        self.images_tree = ttk.Treeview(images_frame, columns=columns, show="headings", selectmode="extended")
        self.images_tree.heading("path", text="Путь")
        self.images_tree.heading("categories", text="Категории")
        self.images_tree.heading("assigned", text="Привязан")
        self.images_tree.column("path", width=250)
        self.images_tree.column("categories", width=150)
        self.images_tree.column("assigned", width=80)
        self.images_tree.grid(row=0, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(images_frame, orient=tk.VERTICAL, command=self.images_tree.yview)
        self.images_tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.grid(row=0, column=1, sticky="ns")

        refresh_button = ttk.Button(images_frame, text="Обновить", command=self._populate_images_tab)
        refresh_button.grid(row=1, column=0, sticky="e", pady=5)

        # Product overview
        products_frame = ttk.LabelFrame(frame, text="Созданные товары")
        products_frame.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=10, pady=10)
        products_frame.columnconfigure(0, weight=1)
        products_frame.rowconfigure(0, weight=1)

        product_columns = ("id", "name", "description", "images")
        self.products_tree = ttk.Treeview(products_frame, columns=product_columns, show="headings")
        self.products_tree.heading("id", text="ID")
        self.products_tree.heading("name", text="Название")
        self.products_tree.heading("description", text="Описание")
        self.products_tree.heading("images", text="Изображения")
        self.products_tree.column("description", width=250)
        self.products_tree.column("images", width=200)
        self.products_tree.grid(row=0, column=0, sticky="nsew")

        product_scroll = ttk.Scrollbar(products_frame, orient=tk.VERTICAL, command=self.products_tree.yview)
        self.products_tree.configure(yscrollcommand=product_scroll.set)
        product_scroll.grid(row=0, column=1, sticky="ns")

    def _upload_images(self) -> None:
        file_paths = filedialog.askopenfilenames(
            title="Выберите изображения",
            filetypes=(
                ("Image files", "*.png *.jpg *.jpeg *.bmp"),
                ("All files", "*.*"),
            ),
        )
        if not file_paths:
            return

        try:
            saved = self.image_handler.save_images(list(file_paths))
        except Exception as exc:  # pragma: no cover - GUI feedback
            messagebox.showerror("Ошибка", str(exc))
            return

        self.preview_images.clear()
        self.preview_canvas.delete("all")
        x_offset, y_offset = 10, 10
        max_height = 0
        for saved_image in saved:
            data_uri = self.image_handler.image_to_tk(saved_image.path)
            b64_data = data_uri.split(",", 1)[1]
            photo = tk.PhotoImage(data=b64_data)
            self.preview_images.append(photo)
            self.preview_canvas.create_image(x_offset, y_offset, image=photo, anchor="nw")
            caption = os.path.basename(saved_image.path)
            categories = ", ".join(saved_image.categories)
            self.preview_canvas.create_text(
                x_offset,
                y_offset + photo.height() + 15,
                text=f"{caption}\n{categories}",
                anchor="nw",
            )
            x_offset += photo.width() + 20
            max_height = max(max_height, photo.height())
            if x_offset > self.preview_canvas.winfo_width() - 160:
                x_offset = 10
                y_offset += max_height + 60
                max_height = 0

            self.db.add_image(saved_image.path, categories=saved_image.categories)

        messagebox.showinfo("Успех", "Изображения успешно добавлены")
        self._populate_images_tab()

    def _populate_images_tab(self) -> None:
        for item in self.images_tree.get_children():
            self.images_tree.delete(item)

        images_df = self.db.get_all_images()
        for _, row in images_df.iterrows():
            categories = ", ".join(json.loads(row["categories"])) if row["categories"] else ""
            assigned = "Да" if row["product_id"] else "Нет"
            self.images_tree.insert("", tk.END, iid=str(row["id"]), values=(row["path"], categories, assigned))

    def _populate_products_table(self) -> None:
        for item in self.products_tree.get_children():
            self.products_tree.delete(item)

        products_df = self.db.get_products()
        for _, row in products_df.iterrows():
            self.products_tree.insert(
                "",
                tk.END,
                iid=str(row["id"]),
                values=(row["id"], row["name"], row["description"], ", ".join(row["photo_paths"])),
            )

    def _create_product(self) -> None:
        name = self.name_entry.get().strip()
        description = self.description_text.get("1.0", tk.END).strip()
        selected_items = self.images_tree.selection()

        if not name:
            messagebox.showwarning("Внимание", "Введите название товара")
            return
        if not selected_items:
            messagebox.showwarning("Внимание", "Выберите хотя бы одно изображение")
            return

        try:
            product_id = self.db.create_product(name, description, [int(item) for item in selected_items])
            product_info = {
                "id": product_id,
                "name": name,
                "description": description,
                "images": [self.images_tree.set(item, "path") for item in selected_items],
            }
            status = self.publisher.prepare_listing(product_info)
            messagebox.showinfo("Готово", f"Товар создан (ID: {product_id}).\n{status}")
        except Exception as exc:  # pragma: no cover - GUI feedback
            messagebox.showerror("Ошибка", str(exc))
            return

        self.name_entry.delete(0, tk.END)
        self.description_text.delete("1.0", tk.END)
        self._populate_images_tab()
        self._populate_products_table()


def main() -> None:
    root = tk.Tk()
    app = InventoryApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
