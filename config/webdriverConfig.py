from typing import Iterable, Optional

from selenium import webdriver
from selenium.webdriver.edge.service import Service


class WebDriverConfigurator:
    """
    浏览器驱动配置类

    该类封装 Edge WebDriver 的创建逻辑，支持：
    - 基础降噪选项；
    - 指定用户数据目录与额外命令行参数；
    - 隐式等待时间配置。
    """

    def __init__(
        self,
        driver_path: str = "./tools/edgedriver_win64/msedgedriver.exe",
        user_data_dir: Optional[str] = None,
        additional_args: Optional[Iterable[str]] = None,
        implicit_wait_seconds: int = 10,
    ):
        # 保存初始化参数，便于在 build 中使用
        self.driver_path = driver_path
        self.user_data_dir = user_data_dir
        self.additional_args = list(additional_args) if additional_args else []
        self.implicit_wait_seconds = implicit_wait_seconds

    def build(self):
        """
        创建并返回配置好的 Edge WebDriver 实例。
        """
        # 创建 Service
        service = Service(executable_path=self.driver_path)

        # 创建 EdgeOptions 并设置基础降噪
        options = webdriver.EdgeOptions()
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

        # 创建浏览器实例
        driver = webdriver.Edge(service=service, options=options)

        # 隐式等待
        if self.implicit_wait_seconds and self.implicit_wait_seconds > 0:
            driver.implicitly_wait(self.implicit_wait_seconds)

        return driver