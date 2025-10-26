import re
import json
from pathlib import Path
from typing import Optional, List, Dict
from time import sleep, time
from threading import Event, Thread
from loguru import logger
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.common.action_chains import ActionChains

from config.WebdriverConfig import WebDriverConfigurator
from config.JsonLoadConfig import resolve_cookie_file_path
from service.SolutionService import SolutionService


# 初始化解题服务
solution_service = SolutionService()

class WebEdgeService:
    def __init__(
        self, 
        configurator: Optional[WebDriverConfigurator] = None, 
        cookies_file: Optional[str] = None
    ):
        # 统一 cookies 路径：从 JsonLoadConfig 解析
        self._shutdown_done = False
        self.cookies_file = resolve_cookie_file_path()
        cookies_cfg_path: Optional[str] = self.cookies_file
        try:
            p = Path(self.cookies_file)
            if not p.exists():
                logger.debug("Cookie 文件不存在，跳过加载。")
                cookies_cfg_path = None
            else:
                raw = p.read_text(encoding="utf-8").strip()
                if not raw:
                    logger.debug("Cookie 文件为空，跳过加载。")
                    cookies_cfg_path = None
                else:
                    try:
                        data = json.loads(raw)
                        if not isinstance(data, list) or len(data) == 0:
                            logger.debug("Cookie 数据为空或格式不为列表，跳过加载。")
                            cookies_cfg_path = None
                    except Exception as e:
                        logger.warning(f"Cookie 文件解析失败，跳过加载：{e}")
                        cookies_cfg_path = None
        except Exception as e:
            logger.warning(f"Cookie 文件检查异常，跳过加载：{e}")
            cookies_cfg_path = None

        # 构建驱动配置，只有在 cookies 文件有效时才传入路径，否则禁用加载
        self.configurator = configurator or WebDriverConfigurator(cookies_file=cookies_cfg_path)
        self.driver = self.configurator.build()

    def _save_cookies(
        self, 
        file_path: Optional[str] = None
    ):
        """保存当前浏览器的 Cookie 到指定文件。"""
        target = file_path or self.cookies_file
        # 会话健壮性检查：若驱动或会话已关闭，直接跳过保存
        try:
            if not hasattr(self, "driver") or self.driver is None:
                logger.debug("Driver 不存在，跳过保存 Cookie。")
                return
            if getattr(self.driver, "session_id", None) is None:
                logger.debug("Driver 会话已结束，跳过保存 Cookie。")
                return
        except Exception:
            # 若检查本身异常，不影响后续保存流程
            pass
        try:
            cookies = self.driver.get_cookies()
            try:
                Path(target).parent.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                logger.error(f"创建Cookie目录失败: {e}")
                return
            for c in cookies:
                if "expiry" in c and c["expiry"] is not None:
                    try:
                        c["expiry"] = int(c["expiry"])
                    except Exception:
                        c["expiry"] = None
            with open(target, "w", encoding="utf-8") as f:
                json.dump(cookies, f, ensure_ascii=False, indent=2)
            logger.info(f"已保存 {len(cookies)} 条 Cookie 到 {target}")
        except Exception as e:
            logger.error(f"保存 Cookie 失败: {e}")

    # 打开入口并确保登录进入学习页面
    def _ensure_login_and_enter_study(
        self, 
        base_url: str = "https://onlineweb.zhihuishu.com/", 
        study_url_hint: str = "https://onlineweb.zhihuishu.com/onlinestuh5", 
        login_domain_hint: str = "passport.zhihuishu.com", 
        login_wait_seconds: int = 180
    ) -> bool:
        """
        打开入口页，若未登录则提示用户在浏览器中完成登录，并等待进入学习页面。
        返回是否成功进入学习页。
        """
        driver = self.driver
        driver.get(base_url)
        logger.debug(f"已打开入口页：{base_url}")

        try:
            WebDriverWait(driver, 2).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        except Exception:
            pass

        current_url = driver.current_url
        if login_domain_hint in current_url:
            logger.warning("检测到未登录，请在浏览器窗口内完成登录（扫码或知到APP）。系统将自动监听登录状态，登录成功后会自动跳转到学习页面。")
            try:
                WebDriverWait(driver, login_wait_seconds, poll_frequency=1).until(EC.url_contains(study_url_hint))
                logger.info("登录成功，已进入学习页面。")
                return True
            except TimeoutException:
                logger.error("登录等待超时（%s 秒）。请确认已在浏览器中完成登录后重新运行程序。", login_wait_seconds)
                return False
        else:
            try:
                WebDriverWait(driver, login_wait_seconds, poll_frequency=1).until(EC.url_contains(study_url_hint))
                logger.info("已登录，自动进入学习页面。")
                return True
            except TimeoutException:
                logger.warning(f"未在预期时间进入学习页面，当前地址：{driver.current_url}")
                return False

    # 提示用户选择课程;进入课程页面后关闭课前必读并提取课程名称
    def _wait_course_and_prepare(
        self, 
        course_url_hint: str = "https://studywisdomh5.zhihuishu.com/study/index", 
        wait_seconds: int = 30
    ) -> Optional[str]:
        """
        提示用户选择课程并等待课程页面，关闭课前必读弹窗，返回课程名称。
        """
        driver = self.driver
        logger.warning(f"请在{wait_seconds}秒内选择要进入的课程。")
        sleep(3)
        try:
            WebDriverWait(driver, wait_seconds, poll_frequency=1).until(EC.url_contains(course_url_hint))
            overlays = driver.find_elements(By.CSS_SELECTOR, ".el-overlay.ss2077-custom-modal")
            for overlay in overlays:
                style = overlay.get_attribute("style") or ""
                if not re.search(r"display\s*:\s*none\s*;", style, flags=re.IGNORECASE):
                    new_style = style.rstrip(";") + "; display: none;"
                    driver.execute_script("arguments[0].setAttribute('style', arguments[1]);", overlay, new_style)
            logger.info("已关闭课前必读窗口。")

            try:
                container = WebDriverWait(driver, 5, poll_frequency=1).until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.course-name")))
                spans = container.find_elements(By.TAG_NAME, "span")
                if len(spans) >= 2:
                    course_name = spans[1].text.strip()
                    logger.info(f"当前课程名称: {course_name}")
                    return course_name
                else:
                    logger.warning("未找到课程名称的第二个 span，页面结构可能变化。")
                    return None
            except TimeoutException:
                logger.warning("在课程页面未找到课程名称容器（等待超时）。")
                return None
            except Exception as e:
                logger.error(f"提取课程名称时发生异常: {e}")
                return None
        except TimeoutException:
            logger.error(f"未在{wait_seconds}秒内选择课程，操作终止。当前URL：{driver.current_url}")
            return None

    # 获取所有课程和测试
    def _get_course_and_test_account(
        self
    ) -> Dict[str, List[WebElement]]:
        res: Dict[str, List[WebElement]] = {
            "unfinished_course": [],
            "unfinished_test": []
        }
        driver = self.driver
        
        # 以 catalogue 容器为锚点查找
        try:
            # 等待并获取课程目录的滚动容器
            catalogue = WebDriverWait(driver, 10, poll_frequency=0.5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.el-scrollbar.catalogue"))
            )
            inner_view = catalogue.find_element(By.CSS_SELECTOR, "div.el-scrollbar__view")
            # 在 catalogue 的 view 中查找 item
            child_concontainer = inner_view.find_elements(By.CSS_SELECTOR, "div.item")

            logger.debug(f"catalogue 容器存在: {catalogue is not None}")
            logger.debug(f"课程列表子容器数量: {len(child_concontainer)}")
            if not child_concontainer:
                logger.error("未找到课程列表子容器class=\"item\"")
                return res
        except TimeoutException:
            logger.error("未在限定时间找到课程目录容器 div.el-scrollbar.catalogue")
            return res
        except Exception as e:
            logger.error(f"查询课程列表子容器失败：{e}")
            return res

        # 收集每个子容器内的 item-main
        item_main_list: List[WebElement] = []
        for item in child_concontainer:
            item_main_list.extend(item.find_elements(By.CSS_SELECTOR, "div.item-main"))

        if not item_main_list:
            logger.error("未找到课程列表子容器内的class=\"item-main\"")
            return res

        # 遍历每个 item-main，查找课程 child 项
        for item_main in item_main_list:
            child_list = item_main.find_elements(By.CSS_SELECTOR, "div.child")
            if not child_list:
                logger.warning("未找到课程列表子容器内的class=\"child\"")
                continue

            for child in child_list:
                # 打开class="child"内的class="child-info cur hasvideo"
                child_info_list = child.find_elements(By.CSS_SELECTOR, "div.child-info.cur.hasvideo")
                if not child_info_list:
                    # 兼容结构变化
                    child_info_list = child.find_elements(By.CSS_SELECTOR, "div.child-info")
                if not child_info_list:
                    continue
                child_info_el = child_info_list[0]

                # 获取课程名称
                child_main = child.find_element(By.CSS_SELECTOR, "div.child-main")
                child_line = child_main.find_element(By.CSS_SELECTOR, "div.child-line")
                current_course_name = child_line.find_element(By.CSS_SELECTOR, "span").text.strip()

                # 检查是否已完成
                try:
                    has_finish = driver.execute_script(
                        "return !!arguments[0].querySelector('img.finish-icon')",
                        child_info_el
                    )
                except Exception:
                    # 兜底：若 JS 执行失败，再用 find_elements
                    has_finish = bool(child_info_el.find_elements(By.CSS_SELECTOR, "img.finish-icon"))

                if has_finish:
                    logger.debug(f"已完成课程: {current_course_name}")
                else:
                    res["unfinished_course"].append(child_info_el)
                    logger.debug(f"待完成课程: {current_course_name}")

            # 遍历剩余测试数
            item_tests = item_main.find_elements(By.CSS_SELECTOR, "div.item-test")
            if not item_tests:
                logger.debug("未找到测试项 item-test")
            else:
                for item_test in item_tests:
                    try:
                        status_text = driver.execute_script(
                            "var el = arguments[0].querySelector('span.float-right'); return el ? el.textContent.trim() : '';",
                            item_test
                        )
                    except Exception:
                        spans = item_test.find_elements(By.CSS_SELECTOR, "span.float-right")
                        status_text = spans[0].text.strip() if spans else ""

                    if status_text and ("去完成" in status_text):
                        res["unfinished_test"].append(item_test)

        logger.info(f"待观看课程数: {len(res['unfinished_course'])}, 待测试数: {len(res['unfinished_test'])}")
        return res
    
    # 判断视频是否正在播放
    def _is_playing(
        self
    ) -> bool:
        driver = self.driver
        # 先确保 controlsBar 可见
        try:
            if not self._is_controls_bar_visible():
                logger.debug("controlsBar 不可见，尝试显示以检测播放状态")
                self.show_controls_bar()
                sleep(0.2)
        except Exception as e:
            logger.debug(f"显示 controlsBar 异常: {e}")
        btn = driver.execute_script("return document.querySelector('div.controlsBar #playButton');")
        if not btn:
            logger.warning("未找到播放控制按钮 #playButton，无法判断播放状态")
            return False
        try:
            cls = driver.execute_script("return arguments[0].getAttribute('class') || '';", btn) or ""
            logger.debug(f"播放控制按钮(#playButton)的 class 属性: '{cls}'")
            # 规则：class 包含 'pauseButton' 视为正在播放；否则视为暂停
            return "pauseButton" in cls
        except Exception as e:
            logger.error(f"读取播放状态失败: {e}")
            return False

    # FIXME: 切换视频播放状态（暂停/播放）
    def _change_play_state(
        self, pause: bool = True
    ):
        driver = self.driver
        # 先确保 controlsBar 可见
        try:
            if not self._is_controls_bar_visible():
                logger.debug("controlsBar 不可见，尝试显示以切换播放状态")
                self.show_controls_bar()
                sleep(0.2)
        except Exception as e:
            logger.debug(f"显示 controlsBar 异常: {e}")
        btn = driver.execute_script("return document.querySelector('div.controlsBar #playButton');")
        if not btn:
            logger.error("切换播放状态失败：未找到 #playButton")
            return False
        current_playing = self._is_playing()
        logger.debug(f"当前播放状态: {'播放中' if current_playing else '已暂停'}，目标: {'暂停' if pause else '播放'}")
        # 需要点击的条件：
        # - 目标为暂停，且当前播放中
        # - 目标为播放，且当前已暂停
        need_click = (pause and current_playing) or ((not pause) and (not current_playing))
        if not need_click:
            logger.info("视频播放状态未改变, 无需操作")
            return True
        # 点击 #playButton 切换状态
        try:
            btn.click()
        except Exception:
            try:
                driver.execute_script("arguments[0].click();", btn)
            except Exception as e:
                logger.error(f"点击播放按钮失败：{e}")
                return False
        # 点击后短暂等待并复核状态
        sleep(0.3)
        changed_playing = self._is_playing()
        logger.info(f"切换播放状态完成，当前: {'播放中' if changed_playing else '已暂停'}")
        return True

    def _is_controls_bar_visible(self) -> bool:
        """检测 controlsBar 是否可见。"""
        driver = self.driver
        try:
            el = driver.execute_script("return document.querySelector('div.controlsBar');")
            if not el:
                return False
            try:
                visible = driver.execute_script(
                    "var s=window.getComputedStyle(arguments[0]); return s && s.display !== 'none';",
                    el
                )
            except Exception:
                style = driver.execute_script("return arguments[0].getAttribute('style') || '';", el) or ""
                visible = ("display: block" in style)
            return bool(visible)
        except Exception:
            return False
    
    # 将 controlsBar 设置为可见
    def show_controls_bar(self) -> bool:
        driver = self.driver
        try:
            el = driver.execute_script("return document.querySelector('div.controlsBar');")
            if el:
                driver.execute_script(
                    "arguments[0].setAttribute('style', 'z-index: 2; overflow: inherit; display: block;');",
                    el
                )
                logger.debug("controlsBar 已设置为可见")
                return True
            return False
        except Exception:
            return False
    
    # 恢复 controlsBar 隐藏
    def hide_controls_bar(self) -> bool:
        driver = self.driver
        try:
            el = driver.execute_script("return document.querySelector('div.controlsBar');")
            if el:
                driver.execute_script(
                    "arguments[0].setAttribute('style', 'z-index: 2; overflow: hidden; display: none;');",
                    el
                )
                logger.debug("controlsBar 已恢复为隐藏")
                return True
            return False
        except Exception:
            return False
    
    # 设置播放速度为1.5x
    def _set_15x_play(
        self
    ):
        driver = self.driver
        
        # 确保 controlsBar 可见
        if not self._is_controls_bar_visible():
            self.show_controls_bar()
        
        # 在设置播放速度前，若检测到随堂测试窗口，则等待其结束
        try:
            has_test = driver.execute_script("return !!document.querySelector('div.ai-test-question-wrapper');")
        except Exception:
            has_test = False
        if has_test:
            logger.info("设置倍速前检测到随堂测试窗口")
            while True:
                try:
                    present = driver.execute_script("var el=document.querySelector('div.ai-test-question-wrapper'); return !!el && el.offsetParent!==null;")
                except Exception:
                    present = False
                if not present:
                    break
                sleep(0.5)
            logger.info("随堂测试结束")
        
        # 设置倍速
        speed15 = driver.execute_script("return document.querySelector('div.speedBox .speedTab.speedTab15');")
        if speed15:
            try:
                # 将光标放到 class="speedBox" 上
                speedBox = driver.execute_script("return document.querySelector('div.speedBox');")
                if speedBox:
                    ActionChains(driver).move_to_element(speedBox).perform()
                # 点击1.5倍速度
                speed15.click()
            except Exception:
                driver.execute_script("arguments[0].click();", speed15)
                pass
            logger.info("设置播放速度为1.5x")
            # 确保视频开始播放
            self._change_play_state(pause=False)
        else:
            logger.warning("未找到1.5倍播放速度选项")
        
        # 恢复controlsBar的默认样式
        try:
            driver.execute_script("arguments[0].setAttribute('style', 'z-index: 2; overflow: hidden; display: none;');", controls_bar)
        except Exception:
            pass
    
    # FIXME: 视频结束监听线程
    def _listen_video_play_end(
        self
    ):
        """
        启动一个后台线程，周期性读取页面上的当前播放时间和总时长，
        当检测到当前时间达到总时长或达到最大等待时长后，置位 finished 事件。
        线程支持通过 pause/stop 事件进行暂停与停止控制。
        """
        driver = self.driver

        # 控制事件（若不存在则创建），并清理初始状态
        pause_event = getattr(self, "_video_pause_event", None) or Event()
        stop_event = getattr(self, "_video_stop_event", None) or Event()
        finished_event = getattr(self, "_video_finished_event", None) or Event()
        self._video_pause_event = pause_event
        self._video_stop_event = stop_event
        self._video_finished_event = finished_event
        finished_event.clear()
        stop_event.clear()

        def js_read_times():
            """从页面读取当前播放时间与总时长文本。"""
            try:
                return driver.execute_script(
                    """
                    var el = document.querySelector("div.nPlayTime[class='nPlayTime 33322']")
                             || document.querySelector("div.nPlayTime");
                    var cur = el ? el.querySelector("span.currentTime") : null;
                    var dur = el ? el.querySelector("span.duration") : null;
                    return { cur: cur ? cur.textContent.trim() : null,
                             dur: dur ? dur.textContent.trim() : null };
                    """
                )
            except Exception:
                return {"cur": None, "dur": None}
        
        def parse_time(text: str):
            """将类似 00:23:45 的时间文本转为秒。"""
            if not text:
                return None
            parts = str(text).split(":")
            try:
                vals = [int(p) for p in parts]
            except Exception:
                return None
            sec = 0
            for v in vals:
                sec = sec * 60 + v
            return sec
        
        def worker():
            """后台线程：监控播放进度，设置 finished 事件。"""
            interval = 0.5  # 固定检查间隔
            # 优先使用课程上下文中读取的总时长文本（在 _handle_course 中设置）
            attr_dur_txt = getattr(self, "_video_total_text", None)
            dur_sec_attr = parse_time(attr_dur_txt) if attr_dur_txt else None
            if attr_dur_txt:
                logger.debug(f"视频结束监控线程开始，总时长：{attr_dur_txt}")
            else:
                logger.debug("视频结束监控线程开始，总时长信息未就绪，稍后继续读取")
            # 最大等待时间：若能读到时长则+60秒余量，否则固定30分钟
            max_wait = (dur_sec_attr + 60) if dur_sec_attr is not None else 1800
            logger.debug(f"视频结束监控线程开始，最大等待时间：{max_wait}秒")
            logged_dur = bool(attr_dur_txt)
            start_ts = time()  # 新增：监控起始时间，用于最大等待时间判断
            
            while not stop_event.is_set():
                if pause_event.is_set():
                    sleep(interval)
                    continue
                data = js_read_times()
                cur_txt = data.get("cur") if data else None
                dur_txt = data.get("dur") if data else None
                cur_sec = parse_time(cur_txt)
                dur_sec2 = parse_time(dur_txt)
                # 首次读取到总时长时更新日志与最大等待时间
                if dur_txt and not logged_dur:
                    logger.debug(f"已读取到总时长：{dur_txt}")
                    if dur_sec2 is not None:
                        max_wait = dur_sec2 + 60
                        logger.debug(f"更新最大等待时间：{max_wait}秒")
                    logged_dur = True
                # 达到总时长或接近结束（差1秒以内）即认为完成
                if (cur_txt and dur_txt and cur_txt == dur_txt) or (
                    cur_sec is not None and dur_sec2 is not None and cur_sec >= (dur_sec2 - 1)
                ) or (
                    cur_sec is not None and dur_sec_attr is not None and cur_sec >= (dur_sec_attr - 1)
                ):
                    finished_event.set()
                    logger.debug("视频结束监控线程检测到视频结束")
                    break
                # 超过最大等待时间也认为完成，防止卡死
                if (time() - start_ts) > max_wait:
                    finished_event.set()
                    logger.debug("视频结束监控线程超过最大等待时间，认为视频结束")
                    break
                sleep(interval)
            logger.debug("视频结束监控线程已退出")
        
        # 若旧线程仍在运行，先停止并回收
        old = getattr(self, "_video_thread", None)
        if old and old.is_alive():
            logger.debug("正在停止旧视频结束监控线程")
            stop_event.set()
            try:
                logger.debug("等待旧视频结束监控线程停止")
                old.join(timeout=3)
            except Exception:
                pass
            logger.debug("旧视频结束监控线程已停止")
            stop_event.clear()
        
        # 启动新线程
        th = Thread(target=worker, name="VideoPlayEndMonitor", daemon=True)
        th.start()
        logger.debug("视频结束监控线程已启动")
        self._video_thread = th
        
        # 返回控制事件（也存放在 self 上，外部可直接访问）
        return {
            "thread": th,
            "pause": pause_event,
            "stop": stop_event,
            "finished": finished_event,
        }

    # HACK: 监听随堂测试窗口是否出现
    def _listen_in_class_test(
        self
    ) -> bool:
        driver = self.driver

        # 标记：随堂测试检测状态，供外部主循环暂停/恢复使用
        setattr(self, "_in_class_test_detected", False)
        stop_event = getattr(self, "_in_class_test_stop_event", None)
        pause_event = getattr(self, "_in_class_test_pause_event", None)
        while True:
            # 支持暂停与停止
            if stop_event and stop_event.is_set():
                setattr(self, "_in_class_test_detected", False)
                logger.debug("随堂测试监听停止")
                return False
            if pause_event and pause_event.is_set():
                sleep(0.5)
                continue
            try:
                # 检测弹窗是否可见（offsetParent 为 null 表示不可见）
                present = driver.execute_script(
                    "var el=document.querySelector('div.ai-test-question-wrapper'); return !!el && el.offsetParent!==null;"
                )
                if present:
                    logger.info("检测到随堂测试窗口")
                    # 通知主循环：测试已出现
                    setattr(self, "_in_class_test_detected", True)

                    # 暂停视频结束监控线程
                    v_pause = getattr(self, "_video_pause_event", None)
                    if v_pause:
                        v_pause.set()

                    # 小幅等待以确保弹窗渲染完成
                    sleep(0.5)

                    # 开始答题
                    ok = solution_service.solve_answers_from_image(driver=driver)
                    if ok:
                        logger.info("随堂测试已完成并已提交")
                        # 等待弹窗消失，最多 30 秒
                        try:
                            WebDriverWait(driver, 30, poll_frequency=0.5).until(
                                lambda d: d.execute_script(
                                    "var el=document.querySelector('div.ai-test-question-wrapper'); return !el || el.offsetParent===null;"
                                )
                            )
                        except Exception:
                            pass
                        sleep(2)
                        self._change_play_state(pause=False)
                    else:
                        logger.error("解决随堂测试失败")

                    # 恢复视频结束监控线程
                    if v_pause:
                        v_pause.clear()

                    # 清除测试检测标记，允许后续再次检测与处理
                    setattr(self, "_in_class_test_detected", False)
            except Exception:
                pass
            sleep(0.5)
    
    # 初始化线程
    def init_listeners(
        self
    ):
        """初始化并启动监听线程（随堂测试与视频监控），默认置为暂停状态。"""
        # 初始化随堂测试监听
        self._in_class_test_stop_event = getattr(self, "_in_class_test_stop_event", None) or Event()
        self._in_class_test_pause_event = getattr(self, "_in_class_test_pause_event", None) or Event()
        self._in_class_test_pause_event.set()  # 初始暂停
        th_test = getattr(self, "_in_class_test_thread", None)
        if not th_test or not th_test.is_alive():
            th_test = Thread(target=self._listen_in_class_test, name="InClassTestListener", daemon=True)
            th_test.start()
            self._in_class_test_thread = th_test
            logger.debug("随堂测试监听线程已初始化并启动（暂停中）")
        
        # 初始化视频结束监控线程
        ctrl = self._listen_video_play_end()  # 创建事件与线程
        ctrl["pause"].set()  # 初始暂停
        logger.debug("视频结束监控线程已初始化并启动（暂停中）")
    
    # 恢复线程
    def resume_listeners(
        self
    ):
        """恢复线程（清除暂停）。"""
        # 清除随堂测试监听的暂停
        pause_evt = getattr(self, "_in_class_test_pause_event", None)
        if pause_evt:
            pause_evt.clear()
        # 清除视频监控的暂停，并重置完成事件
        v_pause = getattr(self, "_video_pause_event", None)
        v_finished = getattr(self, "_video_finished_event", None)
        if v_finished:
            v_finished.clear()
        if v_pause:
            v_pause.clear()
        logger.debug("已恢复线程")
    
    # 暂停线程
    def pause_listeners(
        self
    ):
        """暂停线程。"""
        p1 = getattr(self, "_in_class_test_pause_event", None)
        if p1:
            p1.set()
        p2 = getattr(self, "_video_pause_event", None)
        if p2:
            p2.set()
        logger.debug("已暂停线程")
    
    # 释放线程
    def release_listeners(
        self
    ):
        """停止并释放线程资源。"""
        # 停止视频监控
        v_stop = getattr(self, "_video_stop_event", None)
        v_th = getattr(self, "_video_thread", None)
        try:
            if v_stop:
                v_stop.set()
            if v_th and v_th.is_alive():
                v_th.join(timeout=3)
        except Exception:
            pass
        # 停止随堂测试监听
        t_stop = getattr(self, "_in_class_test_stop_event", None)
        t_th = getattr(self, "_in_class_test_thread", None)
        try:
            if t_stop:
                t_stop.set()
            if t_th and t_th.is_alive():
                t_th.join(timeout=3)
        except Exception:
            pass
        logger.debug("已释放线程资源")

    # TODO: 处理单个课程
    def _handle_course(
        self, 
        course_element: WebElement
    ):
        # 点击进入课程页面
        course_element.click()
        logger.debug(f"点击进入课程：{course_element}")
        sleep(1)

        # 等待播放器时间区域加载，并在课程上下文中读取总时长文本，供监控线程使用
        driver = self.driver
        try:
            WebDriverWait(driver, 15, poll_frequency=0.5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.nPlayTime"))
            )
            info = driver.execute_script(
                """
                var el = document.querySelector("div.nPlayTime[class='nPlayTime 33322']")
                         || document.querySelector("div.nPlayTime");
                var dur = el ? el.querySelector("span.duration") : null;
                return { dur: dur ? dur.textContent.trim() : null };
                """
            )
            dur_txt = (info or {}).get("dur")
            setattr(self, "_video_total_text", dur_txt)
            if dur_txt:
                logger.debug(f"读取到视频总时长文本：{dur_txt}")
            else:
                logger.debug("未读取到视频总时长文本，监控线程将继续尝试获取")
        except TimeoutException:
            setattr(self, "_video_total_text", None)
            logger.warning("等待播放器时间区域加载超时，可能导致总时长不可读")

        # 课程开始前：确保 controlsBar 可见
        try:
            if not self._is_controls_bar_visible():
                self.show_controls_bar()
                sleep(1)
        except Exception:
            pass

        # 启动当次课程的监听（取消暂停），并清除视频完成标记
        self.resume_listeners()
        sleep(1)
        
        # 设置播放速度 1.5x 并确保播放
        self._set_15x_play()
        sleep(1)

        # 主循环：等待播放完成或处理随堂测试
        try:
            while True:
                # 播放结束：置位 finished
                finished_evt = getattr(self, "_video_finished_event", None)
                if finished_evt and finished_evt.is_set():
                    logger.info("当前视频播放完成")
                    # 课程结束后暂停监听，控制权交还给外层循环
                    self.pause_listeners()
                    return
                # 若随堂测试监听线程检测到测试窗口出现，则暂停视频结束监控线程
                if getattr(self, "_in_class_test_detected", False):
                    logger.info("检测到随堂测试窗口，暂停视频结束监控线程")
                    v_pause = getattr(self, "_video_pause_event", None)
                    if v_pause:
                        v_pause.set()
                    # 等待随堂测试结束
                    while getattr(self, "_in_class_test_detected", False):
                        sleep(0.5)
                    logger.info("随堂测试结束，恢复视频结束监控线程")
                    if v_pause:
                        v_pause.clear()
                sleep(0.5)
        finally:
            # 兜底：课程退出时确保监听被暂停（资源释放在全局 release_listeners 中处理）
            self.pause_listeners()


    # TODO: 完成测试功能
    # - 测试界面URL：https://onlineexamh5new.zhihuishu.com/
    # - 当完成率为100时说明以及答完所有题目，提交答案
    def _handle_test(self, test_element: WebElement):
        pass
    
    
    # FIXME: 关闭浏览器并保存 Cookie,释放线程
    def shutdown(self):
        """结束服务，先保存 Cookie，再释放线程，最后关闭浏览器。"""
        if self._shutdown_done:
            return
        self._shutdown_done = True
        try:
            logger.info("触发服务关闭：准备先保存 Cookie")
            self._save_cookies(self.cookies_file)
        except Exception as e:
            logger.warning(f"服务关闭保存 Cookie 失败：{e}")
        finally:
            try:
                self.release_listeners()
                logger.debug("监听线程已释放")
            except Exception:
                pass
            try:
                self.driver.quit()
                logger.info("浏览器已关闭，退出程序。")
            except Exception:
                pass