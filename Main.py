from loguru import logger
from config.LoggerConfig import LoggerConfigurator
from service.WebEdgeService import WebEdgeService
from time import sleep
from config.JsonLoadConfig import resolve_driver_exe_path, resolve_cookie_file_path
from config.WebdriverConfig import WebDriverConfigurator
import signal
import atexit

# 注册 Ctrl+C 信号处理与退出兜底，确保保存 Cookie 与释放资源
def safe_shutdown(*_args):
    try:
        web_service.shutdown()
    except Exception:
        pass
    atexit.register(safe_shutdown)
    try:
        signal.signal(signal.SIGINT, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt))
    except Exception:
        pass

def main():
    # 初始化日志系统
    LoggerConfigurator().setup()

    # 构建浏览器服务
    driver_exe = resolve_driver_exe_path()
    cookie_file = resolve_cookie_file_path()
    configurator = WebDriverConfigurator(driver_path=driver_exe, cookies_file=cookie_file)
    web_service = WebEdgeService(configurator=configurator)
    
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

    except KeyboardInterrupt:
        logger.warning("收到 Ctrl+C，正在保存 Cookie 并退出...")
        safe_shutdown()
    finally:
        # 兜底关闭（shutdown 已幂等）
        safe_shutdown()


if __name__ == "__main__":
    main()