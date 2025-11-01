import json
import os
from datetime import datetime
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Any, Dict, List, Optional, Set

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
        self.sold_product_preview_cache: Dict[int, tk.PhotoImage] = {}
        self.image_thumbnails: Dict[int, tk.PhotoImage] = {}
        self.placeholder_thumbnail = self._create_placeholder_thumbnail()
        self.product_cards: List[Dict[str, Any]] = []
        self.selected_product_ids: Set[int] = set()
        self.last_selected_index: Optional[int] = None

        self._configure_style()

        self._build_ui()
        self._populate_images_tab()
        self._populate_created_products()
        self._populate_sold_products()

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
        style.configure("CardWrapper.TFrame", background=base_bg, relief="flat")
        style.configure("SelectedCardWrapper.TFrame", background="#bfdbfe", relief="flat")
        style.configure("Preview.TLabelframe", background=card_bg, padding=(16, 12))
        style.configure("Preview.TLabelframe.Label", font=("Segoe UI Semibold", 11), foreground=text_secondary)
        style.configure("Section.TLabelframe", background=card_bg, padding=(16, 12))
        style.configure("Section.TLabelframe.Label", font=("Segoe UI Semibold", 11), foreground=text_secondary)
        style.configure("SectionFrame.TFrame", background=card_bg)

        style.configure("Primary.TButton", font=("Segoe UI Semibold", 11), padding=(14, 8))
        style.configure("Secondary.TButton", font=("Segoe UI", 11), padding=(12, 6))
        style.configure("Accent.TButton", font=("Segoe UI Semibold", 11), padding=(14, 8))
        style.configure("Icon.TButton", font=("Segoe UI", 11), padding=(4, 2))
        style.map(
            "Accent.TButton",
            background=[("!disabled", accent), ("pressed", "#1d4ed8")],
            foreground=[("!disabled", "white")],
        )
        style.map(
            "Icon.TButton",
            background=[("pressed", "#fee2e2"), ("active", "#fee2e2")],
            foreground=[("!disabled", "#dc2626")],
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
        style.configure(
            "StatusBadge.TLabel",
            background="#dcfce7",
            foreground="#166534",
            font=("Segoe UI Semibold", 10),
            padding=(8, 4),
        )

        style.configure(
            "Images.Treeview",
            background="#ffffff",
            fieldbackground="#ffffff",
            rowheight=136,
            borderwidth=0,
        )
        style.map(
            "Images.Treeview",
            background=[("selected", "#dbeafe")],
            foreground=[("selected", text_primary)],
        )
        style.configure(
            "Images.Treeview.Heading",
            font=("Segoe UI Semibold", 11),
            background="#f8fafc",
            foreground=text_secondary,
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

        # Tab for sold products
        self.sold_products_frame = ttk.Frame(notebook)
        notebook.add(self.sold_products_frame, text="Проданные товары")
        self._build_sold_products_tab(self.sold_products_frame)

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
            text=(
                "Соберите карточку товара из уже загруженных фотографий и подготовьте её к публикации. "
                "Можно прикрепить до 10 изображений, первое станет главным."
            ),
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

        ttk.Label(input_frame, text="Цена закупки", font=("Segoe UI", 11)).grid(row=4, column=0, sticky="w")
        self.purchase_price_entry = ttk.Entry(input_frame, font=("Segoe UI", 11))
        self.purchase_price_entry.grid(row=5, column=0, sticky="ew", pady=(4, 12))

        ttk.Label(input_frame, text="Цена продажи", font=("Segoe UI", 11)).grid(row=6, column=0, sticky="w")
        self.sale_price_entry = ttk.Entry(input_frame, font=("Segoe UI", 11))
        self.sale_price_entry.grid(row=7, column=0, sticky="ew", pady=(4, 16))

        button_container = ttk.Frame(input_frame, style="SectionFrame.TFrame")
        button_container.grid(row=8, column=0, sticky="ew")
        button_container.columnconfigure(0, weight=1)

        self.toggle_extra_button = ttk.Button(
            button_container,
            text="Доп. параметры",
            style="Secondary.TButton",
            command=self._toggle_extra_fields,
        )
        self.toggle_extra_button.grid(row=0, column=0, sticky="w")

        auto_button = ttk.Button(
            button_container,
            text="Создать автоматически",
            style="Secondary.TButton",
            command=self._auto_fill_product,
        )
        auto_button.grid(row=0, column=1, sticky="e", padx=(12, 12))

        create_button = ttk.Button(
            button_container,
            text="Создать",
            style="Accent.TButton",
            command=self._create_product,
        )
        create_button.grid(row=0, column=2, sticky="e")

        self.additional_section = ttk.LabelFrame(
            input_frame,
            text="Дополнительные параметры",
            style="Section.TLabelframe",
        )
        self.additional_section.grid(row=9, column=0, sticky="ew", pady=(16, 0))
        self.additional_section.columnconfigure(0, weight=1)
        self.additional_section.grid_remove()

        ttk.Label(self.additional_section, text="Почтовый номер", font=("Segoe UI", 11)).grid(
            row=0, column=0, sticky="w"
        )
        self.postal_code_entry = ttk.Entry(self.additional_section, font=("Segoe UI", 11))
        self.postal_code_entry.grid(row=1, column=0, sticky="ew", pady=(4, 12))

        category_row = ttk.Frame(self.additional_section, style="SectionFrame.TFrame")
        category_row.grid(row=2, column=0, sticky="ew")
        category_row.columnconfigure(0, weight=1)

        ttk.Label(category_row, text="Главная категория", font=("Segoe UI", 11)).grid(
            row=0, column=0, sticky="w"
        )
        self.main_category_var = tk.StringVar()
        self.main_category_entry = ttk.Entry(
            category_row,
            font=("Segoe UI", 11),
            textvariable=self.main_category_var,
            state="readonly",
        )
        self.main_category_entry.grid(row=1, column=0, sticky="ew", pady=(4, 0))

        suggest_button = ttk.Button(
            category_row,
            text="Определить автоматически",
            style="Secondary.TButton",
            command=self._suggest_main_category,
        )
        suggest_button.grid(row=1, column=1, sticky="e", padx=(12, 0))

        ttk.Label(
            self.additional_section,
            text="Заметки для публикации",
            font=("Segoe UI", 11),
        ).grid(row=3, column=0, sticky="w", pady=(16, 0))
        self.publish_notes = tk.Text(
            self.additional_section,
            height=4,
            font=("Segoe UI", 11),
            wrap="word",
            relief="flat",
            borderwidth=1,
        )
        self.publish_notes.configure(
            background="#ffffff",
            highlightthickness=1,
            highlightbackground="#e2e8f0",
            highlightcolor="#2563eb",
        )
        self.publish_notes.grid(row=4, column=0, sticky="ew", pady=(4, 0))

        # Image selection
        images_frame = ttk.LabelFrame(frame, text="Выберите изображения", style="Section.TLabelframe")
        images_frame.grid(row=2, column=1, sticky="nsew", padx=(12, 0))
        images_frame.rowconfigure(0, weight=1)
        images_frame.columnconfigure(0, weight=1)

        columns = ("categories", "assigned", "path_value")
        self.images_tree = ttk.Treeview(
            images_frame,
            columns=columns,
            show="tree headings",
            selectmode="extended",
            padding=4,
            style="Images.Treeview",
        )
        self.images_tree.heading("#0", text="Фото товара")
        self.images_tree.heading("categories", text="Категории")
        self.images_tree.heading("assigned", text="Привязка")
        self.images_tree.heading("path_value", text="")
        self.images_tree.column("#0", width=180, anchor="center", stretch=False)
        self.images_tree.column("categories", width=200, anchor="w")
        self.images_tree.column("assigned", width=110, anchor="center")
        self.images_tree.column("path_value", width=0, stretch=False)
        self.images_tree.grid(row=0, column=0, sticky="nsew")
        self.images_tree.bind("<<TreeviewSelect>>", self._on_images_selection_change)

        scrollbar = ttk.Scrollbar(images_frame, orient=tk.VERTICAL, command=self.images_tree.yview)
        self.images_tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.grid(row=0, column=1, sticky="ns")

        helper_label = ttk.Label(
            images_frame,
            text="Выберите до 10 изображений. Первое выбранное фото будет главным в карточке товара.",
            style="CardBody.TLabel",
            wraplength=360,
            justify="left",
        )
        helper_label.grid(row=1, column=0, sticky="w", pady=(12, 0))

        refresh_button = ttk.Button(
            images_frame,
            text="Обновить",
            style="Secondary.TButton",
            command=self._populate_images_tab,
        )
        refresh_button.grid(row=2, column=0, sticky="e", pady=(8, 0))

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

        actions_frame = ttk.Frame(frame, style="SectionFrame.TFrame")
        actions_frame.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        actions_frame.columnconfigure(0, weight=1)

        self.selection_label = ttk.Label(
            actions_frame,
            text="Выберите товары для групповых действий (Shift — диапазон, Ctrl — выборочно)",
            style="CardBody.TLabel",
        )
        self.selection_label.grid(row=0, column=0, sticky="w")

        buttons_holder = ttk.Frame(actions_frame, style="SectionFrame.TFrame")
        buttons_holder.grid(row=0, column=1, sticky="e")

        self.mark_sold_button = ttk.Button(
            buttons_holder,
            text="Отметить как продано",
            style="Secondary.TButton",
            command=self._mark_selected_as_sold,
            state="disabled",
        )
        self.mark_sold_button.grid(row=0, column=0, sticky="e")

        self.delete_selected_button = ttk.Button(
            buttons_holder,
            text="Удалить выбранные",
            style="Secondary.TButton",
            command=self._delete_selected_products,
            state="disabled",
        )
        self.delete_selected_button.grid(row=0, column=1, sticky="e", padx=(12, 0))

        container = ttk.Frame(frame, style="Card.TFrame")
        container.grid(row=3, column=0, sticky="nsew")
        frame.rowconfigure(3, weight=1)
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

    def _build_sold_products_tab(self, frame: ttk.Frame) -> None:
        frame.columnconfigure(0, weight=1)

        header = ttk.Label(frame, text="Проданные товары", style="PageTitle.TLabel")
        header.grid(row=0, column=0, sticky="w", pady=(4, 0))

        subtitle = ttk.Label(
            frame,
            text="Архив реализованных позиций с быстрым доступом к истории цен и дате продажи.",
            style="Subtitle.TLabel",
        )
        subtitle.grid(row=1, column=0, sticky="w", pady=(6, 18))

        container = ttk.Frame(frame, style="Card.TFrame")
        container.grid(row=2, column=0, sticky="nsew")
        frame.rowconfigure(2, weight=1)
        container.columnconfigure(0, weight=1)

        self.sold_canvas = tk.Canvas(container, highlightthickness=0, background="#ffffff")
        self.sold_canvas.grid(row=0, column=0, sticky="nsew")
        container.rowconfigure(0, weight=1)

        scrollbar = ttk.Scrollbar(container, orient=tk.VERTICAL, command=self.sold_canvas.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.sold_canvas.configure(yscrollcommand=scrollbar.set)

        self.sold_inner = ttk.Frame(self.sold_canvas, style="Card.TFrame")
        self.sold_window = self.sold_canvas.create_window((0, 0), window=self.sold_inner, anchor="nw")
        self.sold_inner.bind(
            "<Configure>",
            lambda event: self.sold_canvas.configure(scrollregion=self.sold_canvas.bbox("all")),
        )
        self.sold_canvas.bind(
            "<Configure>",
            lambda event: self.sold_canvas.itemconfigure(self.sold_window, width=event.width),
        )

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

        self.image_thumbnails.clear()
        images_df = self.db.get_all_images()
        for _, row in images_df.iterrows():
            categories = ", ".join(json.loads(row["categories"])) if row["categories"] else ""
            assigned = "Да" if row["product_id"] else "Нет"
            thumbnail = self._load_thumbnail(row["id"], row["path"])
            self.images_tree.insert(
                "",
                tk.END,
                iid=str(row["id"]),
                image=thumbnail,
                values=(categories, assigned, row["path"]),
            )

    def _resize_product_cards(self, event: tk.Event) -> None:
        self.products_canvas.itemconfigure(self.products_window, width=event.width)

    def _populate_created_products(self) -> None:
        for child in self.products_inner.winfo_children():
            child.destroy()
        self.product_preview_cache.clear()
        previous_selection = set(self.selected_product_ids)
        self.selected_product_ids.clear()
        self.product_cards.clear()

        products_df = self.db.get_products(status="active")
        if products_df.empty:
            empty_label = ttk.Label(
                self.products_inner,
                text="Вы ещё не создали ни одного товара. Создайте карточку на соседней вкладке.",
                style="CardBody.TLabel",
            )
            empty_label.grid(row=0, column=0, sticky="w", padx=24, pady=24)
            self.selection_label.configure(text="Нет активных товаров для отображения")
            self._update_bulk_actions_state()
            return

        for index, (_, row) in enumerate(products_df.iterrows()):
            wrapper = ttk.Frame(
                self.products_inner,
                style="CardWrapper.TFrame",
                padding=2,
            )
            wrapper.grid(row=index, column=0, sticky="ew", padx=16, pady=(0 if index == 0 else 12))
            wrapper.columnconfigure(0, weight=1)

            card = ttk.Frame(wrapper, style="Card.TFrame", padding=(20, 16))
            card.grid(row=0, column=0, sticky="ew")
            card.columnconfigure(1, weight=1)
            card.columnconfigure(2, weight=0)

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

            image_label.grid(row=0, column=0, rowspan=5, sticky="nw", padx=(0, 20))

            main_photo_badge = ttk.Label(card, text="Главное фото", style="CardBody.TLabel")
            main_photo_badge.grid(row=4, column=0, sticky="n", padx=(0, 20), pady=(12, 0))

            title_label = ttk.Label(card, text=row["name"], style="CardTitle.TLabel")
            title_label.grid(row=0, column=1, sticky="w")

            action_frame = ttk.Frame(card, style="SectionFrame.TFrame")
            action_frame.grid(row=0, column=2, rowspan=5, sticky="ne")

            delete_button = ttk.Button(
                action_frame,
                text="✕",
                width=3,
                style="Icon.TButton",
                command=lambda pid=row["id"], name=row["name"]: self._confirm_delete_product(pid, name),
            )
            delete_button.grid(row=0, column=0, sticky="ne")
            delete_button.bind(
                "<Button-1>",
                lambda event, btn=delete_button: self._handle_button_click(event, btn),
            )

            edit_button = ttk.Button(
                action_frame,
                text="Изменить товар",
                style="Secondary.TButton",
                command=lambda product=row: self._open_edit_product_dialog(product),
            )
            edit_button.grid(row=1, column=0, sticky="ew", pady=(12, 0))
            edit_button.bind(
                "<Button-1>",
                lambda event, btn=edit_button: self._handle_button_click(event, btn),
            )

            realization_button = ttk.Button(
                action_frame,
                text="Реализация",
                style="Secondary.TButton",
                command=lambda product=row: self._open_realization_stub(product),
            )
            realization_button.grid(row=2, column=0, sticky="ew", pady=(8, 0))
            realization_button.bind(
                "<Button-1>",
                lambda event, btn=realization_button: self._handle_button_click(event, btn),
            )

            description = row["description"] or "Описание не указано"
            description_label = ttk.Label(card, text=description, style="CardBody.TLabel")
            description_label.grid(row=1, column=1, sticky="ew", pady=(8, 0))

            purchase_price_text = self._format_price_value(row.get("purchase_price"))
            sale_price_text = self._format_price_value(row.get("sale_price"))
            price_label = ttk.Label(
                card,
                text=f"Закупка: {purchase_price_text}   Продажа: {sale_price_text}",
                style="CardBody.TLabel",
            )
            price_label.grid(row=2, column=1, sticky="w", pady=(8, 0))

            category_text = row.get("main_category") or "Категория не определена"
            postal_text = row.get("postal_code") or "Не указан"
            category_label = ttk.Label(
                card,
                text=f"Категория: {category_text}   Почтовый номер: {postal_text}",
                style="CardBody.TLabel",
            )
            category_label.grid(row=3, column=1, sticky="w", pady=(4, 0))

            total_photos = len(row.get("photo_paths", []) or [])
            photos_label = ttk.Label(
                card,
                text=f"Фотографии: {total_photos} шт. Первое фото отображается как главное.",
                style="CardBody.TLabel",
            )
            photos_label.grid(row=4, column=1, sticky="w", pady=(8, 0))

            self._bind_card_selection(card, index, row["id"])

            if row["id"] in previous_selection:
                self.selected_product_ids.add(row["id"])

            self.product_cards.append(
                {
                    "id": row["id"],
                    "index": index,
                    "wrapper": wrapper,
                    "card": card,
                    "data": row,
                }
            )

        self._refresh_product_selection()
        self._update_bulk_actions_state()

    def _bind_card_selection(self, widget: tk.Widget, index: int, product_id: int) -> None:
        if isinstance(widget, ttk.Button):
            return
        widget.bind(
            "<Button-1>",
            lambda event, idx=index, pid=product_id: self._on_product_card_click(event, idx, pid),
        )
        for child in widget.winfo_children():
            self._bind_card_selection(child, index, product_id)

    def _handle_button_click(self, _event: tk.Event, button: ttk.Button) -> str:
        button.invoke()
        return "break"

    def _refresh_product_selection(self) -> None:
        total_cards = len(self.product_cards)
        selected_count = len(self.selected_product_ids)
        for card_info in self.product_cards:
            style_name = (
                "SelectedCardWrapper.TFrame"
                if card_info["id"] in self.selected_product_ids
                else "CardWrapper.TFrame"
            )
            card_info["wrapper"].configure(style=style_name)

        if selected_count:
            self.selection_label.configure(
                text=(
                    f"Выбрано товаров: {selected_count}. Вы можете отметить их как проданные или удалить."
                )
            )
        else:
            base_text = (
                "Выберите товары для групповых действий (Shift — диапазон, Ctrl — выборочно)"
                if total_cards
                else "Нет активных товаров для отображения"
            )
            self.selection_label.configure(text=base_text)
            self.last_selected_index = None

    def _update_bulk_actions_state(self) -> None:
        state = "normal" if self.selected_product_ids else "disabled"
        self.mark_sold_button.configure(state=state)
        self.delete_selected_button.configure(state=state)

    def _clear_product_selection(self) -> None:
        self.selected_product_ids.clear()
        self.last_selected_index = None
        self._refresh_product_selection()
        self._update_bulk_actions_state()

    def _on_product_card_click(self, event: tk.Event, index: int, product_id: int) -> str:
        shift_pressed = bool(event.state & 0x0001)
        control_pressed = bool(event.state & 0x0004 or event.state & 0x0008)

        if shift_pressed and self.last_selected_index is not None and self.product_cards:
            start = min(self.last_selected_index, index)
            end = max(self.last_selected_index, index)
            self.selected_product_ids = {
                self.product_cards[i]["id"] for i in range(start, end + 1)
            }
            self.last_selected_index = index
        elif control_pressed:
            if product_id in self.selected_product_ids:
                self.selected_product_ids.remove(product_id)
            else:
                self.selected_product_ids.add(product_id)
            self.last_selected_index = index if self.selected_product_ids else None
        else:
            self.selected_product_ids = {product_id}
            self.last_selected_index = index

        self._refresh_product_selection()
        self._update_bulk_actions_state()
        return "break"

    def _mark_selected_as_sold(self) -> None:
        if not self.selected_product_ids:
            return
        count = len(self.selected_product_ids)
        if not messagebox.askyesno(
            "Перенос в проданные",
            f"Отметить {count} товар(ов) как проданные и перенести в архив?",
        ):
            return
        try:
            self.db.mark_products_as_sold(self.selected_product_ids)
        except Exception as exc:  # pragma: no cover - GUI feedback
            messagebox.showerror("Ошибка", str(exc))
            return

        messagebox.showinfo(
            "Готово",
            f"Товары успешно перенесены в раздел \"Проданные\" ({count} шт.)",
        )
        self._clear_product_selection()
        self._populate_created_products()
        self._populate_sold_products()

    def _delete_selected_products(self) -> None:
        if not self.selected_product_ids:
            return
        count = len(self.selected_product_ids)
        if not messagebox.askyesno(
            "Удаление товаров",
            f"Вы действительно хотите удалить {count} выбранных товар(ов)?",
        ):
            return
        try:
            self.db.delete_products(self.selected_product_ids)
        except Exception as exc:  # pragma: no cover - GUI feedback
            messagebox.showerror("Ошибка", str(exc))
            return

        messagebox.showinfo("Готово", "Выбранные товары удалены")
        self._clear_product_selection()
        self._populate_created_products()
        self._populate_sold_products()

    def _populate_sold_products(self) -> None:
        for child in self.sold_inner.winfo_children():
            child.destroy()
        self.sold_product_preview_cache.clear()

        sold_df = self.db.get_products(status="sold")
        if sold_df.empty:
            empty_label = ttk.Label(
                self.sold_inner,
                text="Проданных товаров пока нет. Отмечайте позиции как реализованные во вкладке \"Созданные товары\".",
                style="CardBody.TLabel",
            )
            empty_label.grid(row=0, column=0, sticky="w", padx=24, pady=24)
            return

        for index, (_, row) in enumerate(sold_df.iterrows()):
            card = ttk.Frame(self.sold_inner, style="Card.TFrame", padding=(20, 16))
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
                    self.sold_product_preview_cache[row["id"]] = photo
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

            image_label.grid(row=0, column=0, rowspan=5, sticky="nw", padx=(0, 20))

            status_badge = ttk.Label(
                card,
                text=f"Продано: {self._format_sold_datetime(row.get('sold_at'))}",
                style="StatusBadge.TLabel",
            )
            status_badge.grid(row=0, column=2, sticky="ne")

            title_label = ttk.Label(card, text=row["name"], style="CardTitle.TLabel")
            title_label.grid(row=0, column=1, sticky="w")

            description = row.get("description") or "Описание не указано"
            description_label = ttk.Label(card, text=description, style="CardBody.TLabel")
            description_label.grid(row=1, column=1, sticky="ew", pady=(8, 0))

            purchase_price_text = self._format_price_value(row.get("purchase_price"))
            sale_price_text = self._format_price_value(row.get("sale_price"))
            price_label = ttk.Label(
                card,
                text=f"Закупка: {purchase_price_text}   Продажа: {sale_price_text}",
                style="CardBody.TLabel",
            )
            price_label.grid(row=2, column=1, sticky="w", pady=(8, 0))

            category_text = row.get("main_category") or "Категория не определена"
            postal_text = row.get("postal_code") or "Не указан"
            info_label = ttk.Label(
                card,
                text=f"Категория: {category_text}   Почтовый номер: {postal_text}",
                style="CardBody.TLabel",
            )
            info_label.grid(row=3, column=1, sticky="w", pady=(4, 0))

            total_photos = len(row.get("photo_paths", []) or [])
            photos_label = ttk.Label(
                card,
                text=f"Фотографии: {total_photos} шт.",
                style="CardBody.TLabel",
            )
            photos_label.grid(row=4, column=0, columnspan=3, sticky="w", pady=(12, 0))

    def _format_sold_datetime(self, value: Optional[str]) -> str:
        if not value:
            return "—"
        try:
            dt = datetime.fromisoformat(value)
        except ValueError:
            return value
        return dt.strftime("%d.%m.%Y %H:%M")
    def _create_product(self) -> None:
        name = self.name_entry.get().strip()
        description = self.description_text.get("1.0", tk.END).strip()
        selected_items = self.images_tree.selection()
        purchase_raw = self.purchase_price_entry.get().strip()
        sale_raw = self.sale_price_entry.get().strip()
        postal_code = self.postal_code_entry.get().strip()
        main_category = self.main_category_var.get().strip()
        notes = self.publish_notes.get("1.0", tk.END).strip()

        purchase_price = None
        if purchase_raw:
            try:
                purchase_price = float(purchase_raw.replace(",", "."))
            except ValueError:
                messagebox.showerror("Ошибка", "Некорректное значение в поле 'Цена закупки'")
                return

        sale_price = None
        if sale_raw:
            try:
                sale_price = float(sale_raw.replace(",", "."))
            except ValueError:
                messagebox.showerror("Ошибка", "Некорректное значение в поле 'Цена продажи'")
                return

        if not name:
            messagebox.showwarning("Внимание", "Введите название товара")
            return
        if not selected_items:
            messagebox.showwarning("Внимание", "Выберите хотя бы одно изображение")
            return
        if len(selected_items) > 10:
            messagebox.showwarning("Внимание", "Можно выбрать не более 10 изображений для одного товара")
            return

        try:
            product_id = self.db.create_product(
                name,
                description,
                [int(item) for item in selected_items],
                purchase_price=purchase_price,
                sale_price=sale_price,
                postal_code=postal_code or None,
                main_category=main_category or None,
                publish_notes=notes or None,
            )
            product_info = {
                "id": product_id,
                "name": name,
                "description": description,
                "images": [self.images_tree.set(item, "path_value") for item in selected_items],
            }
            status = self.publisher.prepare_listing(product_info)
            messagebox.showinfo("Готово", f"Товар создан (ID: {product_id}).\n{status}")
        except Exception as exc:  # pragma: no cover - GUI feedback
            messagebox.showerror("Ошибка", str(exc))
            return

        self.name_entry.delete(0, tk.END)
        self.description_text.delete("1.0", tk.END)
        self.purchase_price_entry.delete(0, tk.END)
        self.sale_price_entry.delete(0, tk.END)
        self.postal_code_entry.delete(0, tk.END)
        self.main_category_var.set("")
        self.publish_notes.delete("1.0", tk.END)
        self._populate_images_tab()
        self._populate_created_products()
        
    def _auto_fill_product(self) -> None:
        messagebox.showinfo(
            "Скоро появится",
            "Функция автоматического заполнения находится в разработке.",
        )

    def _confirm_delete_product(self, product_id: int, name: str) -> None:
        if not messagebox.askyesno(
            "Удаление товара",
            f"Вы действительно хотите удалить \"{name}\"?",
        ):
            return
        try:
            self.db.delete_product(product_id)
        except Exception as exc:  # pragma: no cover - GUI feedback
            messagebox.showerror("Ошибка", str(exc))
            return

        messagebox.showinfo("Готово", "Товар удалён")
        if product_id in self.selected_product_ids:
            self.selected_product_ids.discard(product_id)
            self._refresh_product_selection()
            self._update_bulk_actions_state()
        self._populate_images_tab()
        self._populate_created_products()
        self._populate_sold_products()

    def _open_edit_product_dialog(self, product_row) -> None:
        product_name = product_row.get("name", "Товар")
        messagebox.showinfo(
            "Изменение товара",
            (
                "Функция редактирования находится в разработке. "
                f"Скоро вы сможете обновлять информацию для \"{product_name}\"."
            ),
        )

    def _open_realization_stub(self, product_row) -> None:
        product_name = product_row.get("name", "Товар")
        messagebox.showinfo(
            "Реализация",
            f"Подготовка реализации для \"{product_name}\" скоро будет доступна.",
        )

    def _toggle_extra_fields(self) -> None:
        if self.additional_section.winfo_ismapped():
            self.additional_section.grid_remove()
            self.toggle_extra_button.configure(text="Доп. параметры")
        else:
            self.additional_section.grid()
            self.toggle_extra_button.configure(text="Скрыть доп. параметры")
            self._suggest_main_category(auto=True)

    def _suggest_main_category(self, auto: bool = False) -> None:
        selected_items = self.images_tree.selection()
        if not selected_items:
            if not auto:
                messagebox.showinfo(
                    "Категория не определена",
                    "Выберите изображения, чтобы определить категорию товара",
                )
            return

        categories: List[str] = []
        for item in selected_items:
            cats_text = self.images_tree.set(item, "categories")
            if cats_text:
                categories.extend(
                    [part.strip() for part in cats_text.split(",") if part.strip()]
                )

        if not categories:
            if not auto:
                messagebox.showwarning(
                    "Категории не найдены",
                    "Не удалось определить категории по выбранным изображениям",
                )
            return

        frequency: Dict[str, int] = {}
        for category in categories:
            frequency[category] = frequency.get(category, 0) + 1

        main_category = max(frequency, key=frequency.get)
        self.main_category_var.set(main_category)

        if not auto:
            messagebox.showinfo(
                "Категория определена",
                f"Основная категория выбрана автоматически: {main_category}",
            )

    def _on_images_selection_change(self, _event: tk.Event) -> None:
        if self.additional_section.winfo_ismapped():
            self._suggest_main_category(auto=True)

    def _format_price_value(self, value: Optional[float]) -> str:
        if value in (None, ""):
            return "—"
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return "—"
        return f"{numeric:.2f} ₽"

    def _create_placeholder_thumbnail(self, size: int = 120) -> tk.PhotoImage:
        placeholder = tk.PhotoImage(width=size, height=size)
        placeholder.put("#f1f5f9", to=(0, 0, size, size))
        border_color = "#cbd5f5"
        placeholder.put(border_color, to=(0, 0, size, 2))
        placeholder.put(border_color, to=(0, size - 2, size, size))
        placeholder.put(border_color, to=(0, 0, 2, size))
        placeholder.put(border_color, to=(size - 2, 0, size, size))
        return placeholder

    def _load_thumbnail(self, image_id: int, path: str) -> tk.PhotoImage:
        if path and os.path.exists(path):
            try:
                data_uri = self.image_handler.image_to_tk(path, max_size=120)
                b64_data = data_uri.split(",", 1)[1]
                thumbnail = tk.PhotoImage(data=b64_data)
                self.image_thumbnails[image_id] = thumbnail
                return thumbnail
            except Exception:
                pass
        return self.placeholder_thumbnail


def main() -> None:
    root = tk.Tk()
    app = InventoryApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
