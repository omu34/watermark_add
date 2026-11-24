from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WORK_DIR = PROJECT_ROOT / "watermark_workspace"
WORK_DIR.mkdir(exist_ok=True)
