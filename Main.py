from loguru import logger
from config.loggerConfig import LoggerConfigurator
from service.WebEdgeService import WebEdgeService
from time import sleep


def main():
    # 初始化日志系统
    LoggerConfigurator().setup()

    # 构建浏览器服务
    web_service = WebEdgeService()
    
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
        # 释放监听线程资源，并在结束前保存 Cookie 关闭浏览器
        try:
            web_service.release_listeners()
        except Exception:
            pass
        web_service.shutdown()


if __name__ == "__main__":
    main()