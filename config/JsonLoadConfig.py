import json
from pathlib import Path
from typing import Dict, Any

# 定位项目根 config.json
def get_project_root() -> Path:
    p = Path(__file__).resolve()
    for i in range(1, 4):
        root = p.parents[i - 1]
        if (root / "config.json").exists():
            return root
    return p.parents[1]

# 加载完整配置 JSON
def load_config() -> Dict[str, Any]:
    root = get_project_root()
    cfg_path = root / "config.json"
    try:
        with cfg_path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

# 读取项目配置 JSON
cfg = load_config()

# 读取 llm.deepseek 配置
def get_llm_deepseek_config() -> Dict[str, Any]:
    d = cfg.get("llm", {}).get("deepseek", {})
    return {
        "api_key": (d.get("api_key") or "").strip(),
        "base_url": d.get("base_url") or "https://api.deepseek.com",
        "model": d.get("model") or "deepseek-chat",
    }

# 读取 web_config 配置（目录名），并提供路径解析
def get_web_config() -> Dict[str, Any]:
    w = cfg.get("web_config", {})
    driver_dir = (w.get("driver_path") or "edgedriver_win64").strip() or "edgedriver_win64"
    cookie_rel = (w.get("cookie_path") or "edgedriver_win64/cookies.json").strip() or "edgedriver_win64/cookies.json"
    return {
        "driver_path": driver_dir,
        "cookie_path": cookie_rel,
    }

# 解析绝对路径（驱动与 Cookie）
def resolve_driver_exe_path() -> str:
    root = get_project_root()
    web = get_web_config()
    exe = root / "tools" / web["driver_path"] / "msedgedriver.exe"
    if exe.exists():
        return str(exe)
    # 回退默认
    return str(root / "tools" / "edgedriver_win64" / "msedgedriver.exe")


def resolve_cookie_file_path() -> str:
    root = get_project_root()
    web = get_web_config()
    # 固定统一到 tools 目录下
    cookie = root / "tools" / web["cookie_path"].replace("\\", "/")
    return str(cookie)