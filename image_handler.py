import base64
import os
import random
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from typing import List

import cv2
import numpy as np

try:
    from ultralytics import YOLO  # type: ignore
except Exception:  # pragma: no cover - ultralytics might be unavailable
    YOLO = None  # type: ignore


@dataclass
class SavedImage:
    path: str
    categories: List[str]


class ImageHandler:
    """Manages loading, saving and categorising images."""

    def __init__(self, base_dir: str = "images") -> None:
        self.base_dir = base_dir
        os.makedirs(self.base_dir, exist_ok=True)
        self.model = self._load_model()

    def _load_model(self):  # pragma: no cover - optional dependency
        if YOLO is None:
            return None
        try:
            # The default small model provides a balance between speed and accuracy.
            return YOLO("yolov8n.pt")
        except Exception:
            return None

    def save_images(self, file_paths: List[str], limit: int = 8) -> List[SavedImage]:
        if len(file_paths) > limit:
            raise ValueError(f"Можно загрузить не более {limit} изображений за раз")

        saved_images: List[SavedImage] = []
        for original_path in file_paths:
            if not os.path.exists(original_path):
                raise FileNotFoundError(original_path)

            image = cv2.imread(original_path)
            if image is None:
                raise ValueError(f"Не удалось прочитать изображение: {original_path}")

            timestamp = int(time.time())
            random_suffix = random.randint(1000, 9999)
            file_name = f"img_{timestamp}_{random_suffix}.png"
            destination_path = os.path.join(self.base_dir, file_name)

            # Ensure the directory exists via subprocess for Windows compatibility.
            if os.name == "nt":
                subprocess.run(["cmd", "/c", "if not exist", self.base_dir, "mkdir", self.base_dir], check=False)
            else:
                os.makedirs(self.base_dir, exist_ok=True)

            # Leverage numpy statistics for quick quality insights (mean intensity).
            average_intensity = float(np.mean(image))
            cv2.imwrite(destination_path, image)
            categories = self._categorise_image(destination_path)
            if not categories:
                categories = [f"intensity_{int(average_intensity)}"]
            saved_images.append(SavedImage(path=destination_path, categories=categories))

        return saved_images

    def _categorise_image(self, image_path: str) -> List[str]:  # pragma: no cover - depends on external model
        if self.model is None:
            # Fallback heuristic: use the filename as a pseudo-category.
            stem = os.path.splitext(os.path.basename(image_path))[0]
            return [stem]

        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp_file:
            shutil.copy(image_path, tmp_file.name)
            temp_path = tmp_file.name

        try:
            results = self.model(temp_path, verbose=False)
            categories = set()
            for result in results:
                for box in getattr(result, "boxes", []):
                    cls_idx = int(box.cls)
                    categories.add(result.names.get(cls_idx, f"class_{cls_idx}"))
            return sorted(categories)
        except Exception:
            return []
        finally:
            os.unlink(temp_path)

    @staticmethod
    def image_to_tk(image_path: str, max_size: int = 160):
        image = cv2.imread(image_path)
        if image is None:
            raise ValueError(f"Не удалось прочитать изображение: {image_path}")
        height, width = image.shape[:2]
        scale = min(max_size / max(height, width), 1.0)
        new_size = (int(width * scale), int(height * scale))
        resized = cv2.resize(image, new_size)
        rgb_image = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        success, buffer = cv2.imencode(".png", rgb_image)
        if not success:
            raise ValueError("Ошибка преобразования изображения")
        b64_data = base64.b64encode(buffer).decode("ascii")
        return f"data:image/png;base64,{b64_data}"

    def list_saved_images(self) -> List[str]:
        return [os.path.join(self.base_dir, name) for name in os.listdir(self.base_dir) if name.lower().endswith(".png")]


__all__ = ["ImageHandler", "SavedImage"]
