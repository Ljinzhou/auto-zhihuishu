import platform
import json
from pathlib import Path
from typing import Optional, Iterable

from loguru import logger
from selenium import webdriver
from selenium.webdriver.edge.service import Service
from selenium.webdriver.edge.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from config.JsonLoadConfig import resolve_driver_exe_path, resolve_cookie_file_path




class WebDriverConfigurator:
    def __init__(
            self,
            driver_path: Optional[str] = None,
            user_data_dir: Optional[str] = None,
            additional_args: Optional[Iterable[str]] = None,
            implicit_wait_seconds: int = 10,
            cookies_file: Optional[str] = None,
            cookie_base_url: Optional[str] = "https://onlineweb.zhihuishu.com/",
        ):
        # 使用集中配置解析默认路径
        self.driver_path = driver_path or resolve_driver_exe_path()
        self.user_data_dir = user_data_dir
        self.additional_args = list(additional_args) if additional_args else []
        self.implicit_wait_seconds = implicit_wait_seconds
        self.cookies_file = cookies_file or resolve_cookie_file_path()
        self.cookie_base_url = cookie_base_url

    def build(self):
        # 创建 EdgeOptions 并设置基础降噪
        options = Options()
        options.add_argument("--log-level=3")
        options.add_argument("--silent")
        options.add_experimental_option("excludeSwitches", ["enable-logging"])  # 禁用驱动层日志
        options.add_experimental_option("useAutomationExtension", False)         # 禁用自动化扩展

        # 用户数据目录
        if self.user_data_dir:
            options.add_argument(f"--user-data-dir={self.user_data_dir}")

        # 额外参数
        for arg in self.additional_args:
            options.add_argument(str(arg))

        # 创建 Service 和浏览器实例
        service = Service(executable_path=self.driver_path)
        driver = webdriver.Edge(service=service, options=options)

        # 隐式等待
        if self.implicit_wait_seconds and self.implicit_wait_seconds > 0:
            driver.implicitly_wait(self.implicit_wait_seconds)

        # 加载已保存的 Cookie（如果存在）
        try:
            self._load_cookies(driver)
        except Exception as e:
            logger.warning(f"加载 Cookie 时出现异常：{e}")

        return driver

    def _load_cookies(self, driver):
        if not self.cookies_file or not Path(self.cookies_file).exists():
            logger.debug("未发现 Cookie 文件，跳过加载。")
            return

        base_url = self.cookie_base_url or "about:blank"
        logger.info(f"准备从 {self.cookies_file} 加载 Cookie，目标域：{base_url}")

        # 先打开基础域，确保后续 add_cookie 域名匹配
        driver.get(base_url)
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
        except Exception:
            logger.debug("基础域页面等待失败，但继续尝试注入 Cookie。")

        # 读取 Cookie 文件
        with open(self.cookies_file, "r", encoding="utf-8") as f:
            cookies = json.load(f)

        loaded = 0
        for c in cookies:
            # 规范化可选字段，避免 add_cookie 报错
            c = dict(c)
            if "expiry" in c and c["expiry"] is not None:
                try:
                    c["expiry"] = int(c["expiry"])
                except Exception:
                    c["expiry"] = None
            try:
                driver.add_cookie(c)
                loaded += 1
            except Exception:
                # 某些情况下 domain/path 与当前站点不匹配，移除后重试
                c.pop("domain", None)
                c.pop("path", None)
                try:
                    driver.add_cookie(c)
                    loaded += 1
                except Exception as e:
                    logger.debug(f"注入单条 Cookie 失败：{e}")

        logger.info(f"已加载 {loaded}/{len(cookies)} 条 Cookie，刷新页面以应用登录态。")
        try:
            driver.refresh()
        except Exception:
            # 某些场景 refresh 可能报错（如 about:blank），则重新访问基础域
            driver.get(base_url)