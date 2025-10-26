from loguru import logger
from config.LoggerConfig import LoggerConfigurator
from service.WebEdgeService import WebEdgeService
from time import sleep
from config.JsonLoadConfig import resolve_driver_exe_path, resolve_cookie_file_path
from config.WebdriverConfig import WebDriverConfigurator
import signal
import atexit
import keyboard 
import os

def main():
    # 初始化日志系统
    LoggerConfigurator().setup()

    # 构建浏览器服务
    driver_exe = resolve_driver_exe_path()
    cookie_file = resolve_cookie_file_path()
    configurator = WebDriverConfigurator(driver_path=driver_exe, cookies_file=cookie_file)
    web_service = WebEdgeService(configurator=configurator)

    # 热键退出：Ctrl+Shift+C
    def hotkey_shutdown():
        logger.warning("收到 Ctrl+Shift+C，先保存 Cookie，再释放线程与浏览器资源...")
        try:
            web_service.shutdown()
        finally:
            # 确保立刻退出进程（已完成清理）
            os._exit(0)

    # 注册热键
    atexit.register(hotkey_shutdown)
    try:
        keyboard.add_hotkey("ctrl+shift+c", hotkey_shutdown)
        logger.info("已注册退出热键：Ctrl+Shift+C")
    except Exception as e:
        logger.error(f"注册热键失败：{e}")

    try:
        # 打开入口并确保登录进入学习页面
        web_service._ensure_login_and_enter_study()

        # 提示用户选择课程，进入课程页面后关闭课前必读并提取课程名称
        web_service._wait_course_and_prepare()

        # 初始化并暂停监听线程
        web_service.init_listeners()
        web_service.pause_listeners()

        # 获取待完成课程和测试
        unfinisheds = web_service._get_course_and_test_account()

        for unfinished in unfinisheds["unfinished_course"]:
            logger.info(f"开始处理课程: {unfinished}")
            # 本课程开始前恢复监听
            web_service.resume_listeners()
            web_service._handle_course(unfinished)
            # 本课程结束后暂停监听，等待下一门课程
            web_service.pause_listeners()
            logger.info(f"课程 {unfinished} 处理完成，即将进行下一个课程")
            sleep(3)
    finally:
        web_service.shutdown()


if __name__ == "__main__":
    main()