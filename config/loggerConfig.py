# -*- coding: utf-8 -*-
"""
日志配置模块

该模块提供 `init_logger` 初始化函数，用于统一配置 loguru 的日志输出，
包括控制台与文件日志、日志格式、日志级别、轮转与保留策略等。
所有注释均为中文，帮助后续维护与扩展。
"""

from __future__ import annotations
import os
from typing import Optional
from loguru import logger
import sys  # 引入 sys 以便将日志输出到标准输出，从而支持颜色
import datetime as dt  # 引入日期时间模块用于生成日志文件的时间戳
import logging  # 控制第三方库（如 urllib3、selenium）的日志级别


class LoggerConfigurator:
    """
    日志配置类

    该类封装日志初始化逻辑，支持：
    - 根据传入的日志级别进行配置；
    - 若未提供文件路径，自动按中文时间戳创建日志文件；
    - 控制台与文件统一使用自定义格式（控制台带颜色，文件不带颜色）。
    """

    def __init__(self, log_level: str = "DEBUG", log_file_path: Optional[str] = None):
        # 保存日志级别与文件路径，便于在 setup 中使用
        self.log_level = log_level
        self.log_file_path = log_file_path

    def setup(self) -> logger.__class__:
        """
        执行日志初始化，返回 loguru 的全局 logger 对象。
        """
        # 先移除已有的 sink，避免重复输出
        logger.remove()

        # 若未提供日志文件路径，生成中文时间戳命名的日志文件
        if self.log_file_path is None:
            timestamp_cn = dt.datetime.now().strftime("%Y年%m月%d日-%H时%M分%S秒")
            self.log_file_path = os.path.join("./logs", f"{timestamp_cn}.log")

        # 确保目录存在
        log_dir = os.path.dirname(os.path.abspath(self.log_file_path))
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)

        # 统一的日志格式（控制台有颜色标记，文件使用相同格式但不启用颜色）
        log_format = (
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> "
            "| <level>{level}</level> "
            "| <cyan>{module}</cyan>:<cyan>{function}</cyan> "
            "| <level>{message}</level>"
        )

        # 控制台 sink：颜色高亮，便于开发调试
        logger.add(
            sink=sys.stdout,
            level=self.log_level,
            format=log_format,
            colorize=True,
            backtrace=True,
            diagnose=False,
        )

        # 文件 sink：写入中文时间戳命名的日志文件
        logger.add(
            self.log_file_path,
            level=self.log_level,
            format=log_format,
            encoding="utf-8",
            enqueue=True,
        )

        # 抑制第三方库在控制台的噪音（特别是 urllib3 的连接池告警）
        try:
            logging.getLogger("urllib3").setLevel(logging.ERROR)
            logging.getLogger("urllib3.connectionpool").setLevel(logging.ERROR)
            logging.getLogger("requests.packages.urllib3").setLevel(logging.ERROR)
            logging.getLogger("selenium.webdriver.remote.remote_connection").setLevel(logging.ERROR)
        except Exception:
            pass

        # 返回配置后的 logger
        return logger