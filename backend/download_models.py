"""Chuan bi model ONNX YuNet (face detection) va SFace (128-D face recognition)."""

from pathlib import Path
import shutil
import urllib.request

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = PROJECT_ROOT / "backend" / "models"
FACES_STORAGE_DIR = PROJECT_ROOT / "backend" / "storage" / "faces"

MODEL_SPECS = {
    "face_detection_yunet_2023mar.onnx": {
        "local_cache": Path(r"D:\school\IoT\test\data\models\face_detection_yunet_2023mar.onnx"),
        "url": "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
    },
    "face_recognition_sface_2021dec.onnx": {
        "local_cache": Path(r"D:\school\IoT\test\data\models\face_recognition_sface_2021dec.onnx"),
        "url": "https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx",
    },
}


def ensure_models() -> None:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    FACES_STORAGE_DIR.mkdir(parents=True, exist_ok=True)

    for filename, spec in MODEL_SPECS.items():
        target_path = MODELS_DIR / filename
        if target_path.exists() and target_path.stat().st_size > 100_000:
            print(f"[OK] Model da ton tai: {target_path}")
            continue

        local_cache: Path = spec["local_cache"]
        if local_cache.exists() and local_cache.stat().st_size > 100_000:
            shutil.copy2(local_cache, target_path)
            print(f"[OK] Da sao chep model tu cache: {local_cache} -> {target_path}")
            continue

        print(f"[INFO] Dang tai model {filename} tu {spec['url']} ...")
        urllib.request.urlretrieve(spec["url"], target_path)
        print(f"[OK] Da tai xong: {target_path} ({target_path.stat().st_size} bytes)")


if __name__ == "__main__":
    ensure_models()

