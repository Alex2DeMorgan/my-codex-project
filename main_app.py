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
        self.root.geometry("1100x720")
        self.root.configure(bg="#f3f4f6")
        self.db = DatabaseManager()
        self.image_handler = ImageHandler(base_dir=os.path.join(os.getcwd(), "images"))
        self.publisher = FinnPublisher()
        self.preview_images: List[tk.PhotoImage] = []
        self.product_preview_cache: Dict[int, tk.PhotoImage] = {}

        self._configure_style()

        self._build_ui()
        self._populate_images_tab()
        self._populate_created_products()

    def _configure_style(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        base_bg = "#f3f4f6"
        card_bg = "#ffffff"
        accent = "#2563eb"
        text_primary = "#0f172a"
        text_secondary = "#475569"

        style.configure("TFrame", background=base_bg)
        style.configure("Modern.TNotebook", background=base_bg, borderwidth=0)
        style.configure("Modern.TNotebook.Tab", padding=(18, 10), font=("Segoe UI", 11))
        style.map(
            "Modern.TNotebook.Tab",
            foreground=[("selected", text_primary)],
            background=[("selected", card_bg)],
        )
        style.layout("Modern.TNotebook.Tab", style.layout("TNotebook.Tab"))

        style.configure("Card.TFrame", background=card_bg, relief="flat")
        style.configure("Preview.TLabelframe", background=card_bg, padding=(16, 12))
        style.configure("Preview.TLabelframe.Label", font=("Segoe UI Semibold", 11), foreground=text_secondary)
        style.configure("Section.TLabelframe", background=card_bg, padding=(16, 12))
        style.configure("Section.TLabelframe.Label", font=("Segoe UI Semibold", 11), foreground=text_secondary)
        style.configure("SectionFrame.TFrame", background=card_bg)

        style.configure("Primary.TButton", font=("Segoe UI Semibold", 11), padding=(14, 8))
        style.configure("Secondary.TButton", font=("Segoe UI", 11), padding=(12, 6))
        style.configure("Accent.TButton", font=("Segoe UI Semibold", 11), padding=(14, 8))
        style.map(
            "Accent.TButton",
            background=[("!disabled", accent), ("pressed", "#1d4ed8")],
            foreground=[("!disabled", "white")],
        )

        style.configure("PageTitle.TLabel", font=("Segoe UI Semibold", 20), foreground=text_primary, background=base_bg)
        style.configure("Subtitle.TLabel", font=("Segoe UI", 12), foreground=text_secondary, background=base_bg)
        style.configure("CardTitle.TLabel", font=("Segoe UI Semibold", 13), foreground=text_primary, background=card_bg)
        style.configure(
            "CardBody.TLabel",
            font=("Segoe UI", 11),
            foreground=text_secondary,
            background=card_bg,
            wraplength=560,
            justify="left",
        )
        style.configure("CardImage.TLabel", background=card_bg, anchor="center")
        style.configure(
            "CardImagePlaceholder.TLabel",
            background=card_bg,
            foreground="#94a3b8",
            font=("Segoe UI", 11),
            anchor="center",
        )

    def _build_ui(self) -> None:
        container = ttk.Frame(self.root, padding=(24, 24, 24, 16))
        container.pack(fill=tk.BOTH, expand=True)

        notebook = ttk.Notebook(container, style="Modern.TNotebook")
        notebook.pack(fill=tk.BOTH, expand=True)

        # Tab for uploading photos
        self.add_photo_frame = ttk.Frame(notebook)
        notebook.add(self.add_photo_frame, text="Добавить фото")
        self._build_add_photo_tab(self.add_photo_frame)

        # Tab for creating products
        self.create_product_frame = ttk.Frame(notebook)
        notebook.add(self.create_product_frame, text="Создать товар")
        self._build_create_product_tab(self.create_product_frame)

        # Tab for viewing created products
        self.created_products_frame = ttk.Frame(notebook)
        notebook.add(self.created_products_frame, text="Созданные товары")
        self._build_created_products_tab(self.created_products_frame)

    def _build_add_photo_tab(self, frame: ttk.Frame) -> None:
        frame.columnconfigure(0, weight=1)

        header = ttk.Label(frame, text="Добавление изображений", style="PageTitle.TLabel")
        header.grid(row=0, column=0, sticky="w", pady=(4, 0))
        subtitle = ttk.Label(
            frame,
            text="Загрузите до восьми изображений за раз. Мы создадим предпросмотр и сохраним их в базе.",
            style="Subtitle.TLabel",
        )
        subtitle.grid(row=1, column=0, sticky="w", pady=(6, 18))

        upload_button = ttk.Button(
            frame,
            text="Выбрать изображения",
            style="Accent.TButton",
            command=self._upload_images,
        )
        upload_button.grid(row=2, column=0, sticky="w", pady=(0, 18))

        self.preview_container = ttk.LabelFrame(frame, text="Предпросмотр", style="Preview.TLabelframe")
        self.preview_container.grid(row=3, column=0, sticky="nsew")
        frame.rowconfigure(3, weight=1)

        self.preview_canvas = tk.Canvas(self.preview_container, highlightthickness=0, background="#ffffff")
        self.preview_canvas.pack(fill=tk.BOTH, expand=True)

    def _build_create_product_tab(self, frame: ttk.Frame) -> None:
        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)

        header = ttk.Label(frame, text="Создание нового товара", style="PageTitle.TLabel")
        header.grid(row=0, column=0, columnspan=2, sticky="w", pady=(4, 0))
        subtitle = ttk.Label(
            frame,
            text="Соберите карточку товара из уже загруженных фотографий и подготовьте её к публикации.",
            style="Subtitle.TLabel",
        )
        subtitle.grid(row=1, column=0, columnspan=2, sticky="w", pady=(6, 18))

        # Inputs
        input_frame = ttk.LabelFrame(frame, text="Информация о товаре", style="Section.TLabelframe")
        input_frame.grid(row=2, column=0, sticky="nsew", padx=(0, 12))
        input_frame.columnconfigure(0, weight=1)

        ttk.Label(input_frame, text="Название", font=("Segoe UI", 11)).grid(row=0, column=0, sticky="w")
        self.name_entry = ttk.Entry(input_frame, font=("Segoe UI", 11))
        self.name_entry.grid(row=1, column=0, sticky="ew", pady=(4, 12))

        ttk.Label(input_frame, text="Описание", font=("Segoe UI", 11)).grid(row=2, column=0, sticky="w")
        self.description_text = tk.Text(
            input_frame,
            height=10,
            font=("Segoe UI", 11),
            wrap="word",
            relief="flat",
            borderwidth=1,
        )
        self.description_text.grid(row=3, column=0, sticky="ew", pady=(4, 16))
        self.description_text.configure(
            background="#ffffff",
            highlightthickness=1,
            highlightbackground="#e2e8f0",
            highlightcolor="#2563eb",
        )

        button_container = ttk.Frame(input_frame, style="SectionFrame.TFrame")
        button_container.grid(row=4, column=0, sticky="ew")
        button_container.columnconfigure(0, weight=1)

        auto_button = ttk.Button(
            button_container,
            text="Создать автоматически",
            style="Secondary.TButton",
            command=self._auto_fill_product,
        )
        auto_button.grid(row=0, column=0, sticky="w")

        create_button = ttk.Button(
            button_container,
            text="Создать",
            style="Accent.TButton",
            command=self._create_product,
        )
        create_button.grid(row=0, column=1, sticky="e")

        # Image selection
        images_frame = ttk.LabelFrame(frame, text="Выберите изображения", style="Section.TLabelframe")
        images_frame.grid(row=2, column=1, sticky="nsew", padx=(12, 0))
        images_frame.rowconfigure(0, weight=1)
        images_frame.columnconfigure(0, weight=1)

        columns = ("path", "categories", "assigned")
        self.images_tree = ttk.Treeview(
            images_frame,
            columns=columns,
            show="headings",
            selectmode="extended",
            padding=4,
        )
        self.images_tree.heading("path", text="Путь")
        self.images_tree.heading("categories", text="Категории")
        self.images_tree.heading("assigned", text="Привязка")
        self.images_tree.column("path", width=300)
        self.images_tree.column("categories", width=160)
        self.images_tree.column("assigned", width=100)
        self.images_tree.grid(row=0, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(images_frame, orient=tk.VERTICAL, command=self.images_tree.yview)
        self.images_tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.grid(row=0, column=1, sticky="ns")

        refresh_button = ttk.Button(
            images_frame,
            text="Обновить",
            style="Secondary.TButton",
            command=self._populate_images_tab,
        )
        refresh_button.grid(row=1, column=0, sticky="e", pady=(12, 0))

        frame.rowconfigure(2, weight=1)

    def _build_created_products_tab(self, frame: ttk.Frame) -> None:
        frame.columnconfigure(0, weight=1)

        header = ttk.Label(frame, text="Созданные товары", style="PageTitle.TLabel")
        header.grid(row=0, column=0, sticky="w", pady=(4, 0))
        subtitle = ttk.Label(
            frame,
            text="Просматривайте все готовые карточки. Первое изображение, название и описание помогают быстро найти нужный товар.",
            style="Subtitle.TLabel",
        )
        subtitle.grid(row=1, column=0, sticky="w", pady=(6, 18))

        container = ttk.Frame(frame, style="Card.TFrame")
        container.grid(row=2, column=0, sticky="nsew")
        frame.rowconfigure(2, weight=1)
        container.columnconfigure(0, weight=1)

        self.products_canvas = tk.Canvas(container, highlightthickness=0, background="#ffffff")
        self.products_canvas.grid(row=0, column=0, sticky="nsew")
        container.rowconfigure(0, weight=1)

        scrollbar = ttk.Scrollbar(container, orient=tk.VERTICAL, command=self.products_canvas.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.products_canvas.configure(yscrollcommand=scrollbar.set)

        self.products_inner = ttk.Frame(self.products_canvas, style="Card.TFrame")
        self.products_window = self.products_canvas.create_window((0, 0), window=self.products_inner, anchor="nw")
        self.products_inner.bind(
            "<Configure>",
            lambda event: self.products_canvas.configure(scrollregion=self.products_canvas.bbox("all")),
        )
        self.products_canvas.bind("<Configure>", self._resize_product_cards)

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
        x_offset, y_offset = 20, 20
        max_height = 0
        spacing = 40

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
                y_offset + photo.height() + 18,
                text=f"{caption}\n{categories}",
                anchor="nw",
                font=("Segoe UI", 10),
                fill="#475569",
            )
            x_offset += photo.width() + spacing
            max_height = max(max_height, photo.height())
            if x_offset > self.preview_canvas.winfo_width() - 180:
                x_offset = 20
                y_offset += max_height + 80
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

    def _resize_product_cards(self, event: tk.Event) -> None:
        self.products_canvas.itemconfigure(self.products_window, width=event.width)

    def _populate_created_products(self) -> None:
        for child in self.products_inner.winfo_children():
            child.destroy()
        self.product_preview_cache.clear()

        products_df = self.db.get_products()
        if products_df.empty:
            empty_label = ttk.Label(
                self.products_inner,
                text="Вы ещё не создали ни одного товара. Создайте карточку на соседней вкладке.",
                style="CardBody.TLabel",
            )
            empty_label.grid(row=0, column=0, sticky="w", padx=24, pady=24)
            return

        for index, row in products_df.iterrows():
            card = ttk.Frame(self.products_inner, style="Card.TFrame", padding=(20, 16))
            card.grid(row=index, column=0, sticky="ew", padx=16, pady=(0 if index == 0 else 12))
            card.columnconfigure(1, weight=1)

            first_image_path = None
            photo_paths = row.get("photo_paths", [])
            if photo_paths:
                first_image_path = photo_paths[0]

            if first_image_path and os.path.exists(first_image_path):
                try:
                    data_uri = self.image_handler.image_to_tk(first_image_path, max_size=120)
                    b64_data = data_uri.split(",", 1)[1]
                    photo = tk.PhotoImage(data=b64_data)
                    self.product_preview_cache[row["id"]] = photo
                    image_label = ttk.Label(card, image=photo, style="CardImage.TLabel")
                except Exception:
                    image_label = ttk.Label(
                        card,
                        text="Нет предпросмотра",
                        style="CardImagePlaceholder.TLabel",
                        width=18,
                    )
            else:
                image_label = ttk.Label(
                    card,
                    text="Фото отсутствует",
                    style="CardImagePlaceholder.TLabel",
                    width=18,
                )

            image_label.grid(row=0, column=0, rowspan=2, sticky="nw", padx=(0, 20))

            title_label = ttk.Label(card, text=row["name"], style="CardTitle.TLabel")
            title_label.grid(row=0, column=1, sticky="w")

            description = row["description"] or "Описание не указано"
            description_label = ttk.Label(card, text=description, style="CardBody.TLabel")
            description_label.grid(row=1, column=1, sticky="ew", pady=(8, 0))

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
        self._populate_created_products()

    def _auto_fill_product(self) -> None:
        messagebox.showinfo(
            "Скоро появится",
            "Функция автоматического заполнения находится в разработке.",
        )


def main() -> None:
    root = tk.Tk()
    app = InventoryApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
