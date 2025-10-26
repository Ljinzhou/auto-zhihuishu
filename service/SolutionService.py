import numpy as np
import tempfile
import os

from typing import List, Any, Optional
from PIL import Image
from loguru import logger
from cnocr import CnOcr
from tools.llms.DeepSeek import DeepSeek, get_client
from io import BytesIO
from time import sleep


class SolutionService:
    def __init__(self, llm: Optional[DeepSeek] = None):
        self.ocr = CnOcr()
        self.llm = llm or get_client()

    def _get_text(self, item) -> str:
        if isinstance(item, dict) and "text" in item:
            return str(item["text"]).strip()
        elif isinstance(item, list) and len(item) > 0:
            return str(item[0]).strip()
        return ""

    def ocr_items(self, img_or_path) -> List[Any]:
        """
        执行 OCR，接受图片路径、PIL.Image 或 numpy 数组。
        返回原始识别项列表（字典/列表混合）。
        """
        try:
            if isinstance(img_or_path, str):
                out = self.ocr.ocr(img_or_path)
            elif isinstance(img_or_path, Image.Image):
                out = self.ocr.ocr(np.array(img_or_path))
            else:
                out = self.ocr.ocr(img_or_path)
            return out or []
        except Exception as e:
            logger.error(f"OCR失败: {e}")
            return []

    def ocr_text(self, img_or_path) -> str:
        """执行 OCR 并返回拼接后的文本。"""
        items = self.ocr_items(img_or_path)
        lines: List[str] = []
        for it in items:
            txt = self._get_text(it)
            if txt:
                lines.append(txt)
        text = "".join(lines)
        logger.debug(f"OCR提取{len(lines)}行")
        return text

    # 对指定元素图片进行 截屏
    def screenshot_web_element(self, element: Any, save_crop_path: Optional[str] = None) -> Image.Image:
        try:
            # 优先使用 screenshot_as_png 直接获取内存字节
            if hasattr(element, "screenshot_as_png"):
                png_bytes = element.screenshot_as_png
                if save_crop_path:
                    try:
                        with open(save_crop_path, "wb") as f:
                            f.write(png_bytes)
                    except Exception as e:
                        logger.warning(f"调试保存元素截图失败: {e}")
                return Image.open(BytesIO(png_bytes)).convert("RGB")
            # 兼容不支持属性的驱动，使用临时文件保存再读取
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                tmp_path = tmp.name
            try:
                ok = element.screenshot(tmp_path)
                if not ok:
                    raise RuntimeError("element.screenshot 返回失败")
                # 若需要保存到指定路径，拷贝一份方便调试
                if save_crop_path:
                    try:
                        with open(save_crop_path, "wb") as f:
                            with open(tmp_path, "rb") as tmp_f:
                                f.write(tmp_f.read())
                    except Exception as e:
                        logger.warning(f"调试保存元素截图失败: {e}")
                return Image.open(tmp_path).convert("RGB")
            finally:
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass
        except Exception as e:
            logger.error(f"元素截图失败: {e}")
            return Image.new("RGB", (0, 0))
    
    # 对指定元素图片进行 OCR 识别，并将识别结果拼成字符串交给 LLM 解答。
    def solve_answers_from_image(self, element: Any = None, save_crop_path: Optional[str] = None, driver: Any = None) -> bool:
        # 校验 driver 并定位题目容器元素
        if driver is None and element is None:
            logger.error("solve_answers_from_image 需要传入 driver 或已定位的元素")
            return False
        try:
            ques_box = element or driver.execute_script(
                "return document.querySelector('div.ques .item.ques-card-box');"
            )
        except Exception as e:
            logger.error(f"查询题目容器失败: {e}")
            ques_box = None
        if not ques_box:
            logger.error("未找到题目容器 div.ques .item.ques-card-box")
            return False
    
        # 截取元素图片
        img = self.screenshot_web_element(ques_box, save_crop_path)
    
        # 对元素图片进行 OCR，得到题目与选项文本
        try:
            qa_text = self.ocr_text(img)
        except Exception as e:
            logger.error(f"OCR处理失败: {e}")
            qa_text = ""
        logger.debug(f"OCR提取题目与选项：{qa_text}")
        
        # 交给 LLM 获取答案列表
        selected: List[str] = []
        try:
            result = self.llm.answer_question(qa_text)
            logger.debug(f"LLM返回: {result}")
            if isinstance(result, dict):
                sel = result.get("selected")
                if isinstance(sel, list):
                    selected = [str(s).strip() for s in sel]
        except Exception as e:
            logger.error(f"LLM解答失败: {e}")
            selected = []
        
        # 若提供 driver，则执行页面选项定位与点击，并提交
        if driver:
            try:
                # 获取所有选项元素
                options = driver.execute_script(
                    "return Array.from(document.querySelectorAll('.ques .item.ques-card-box .options .option'));"
                )
                if not options:
                    logger.error("未找到选项元素 .ques .item.ques-card-box .options .option")
                logger.debug(f"页面选项元素数量: {len(options) if options else 0}")
                
                # 预取每个选项文本（便于匹配判断题）
                opt_texts = []
                for el in options or []:
                    try:
                        txt = driver.execute_script(
                            "return (arguments[0].innerText||arguments[0].textContent||'').trim();",
                            el,
                        ) or ""
                    except Exception:
                        txt = ""
                    opt_texts.append(txt)
                logger.debug(f"选项文本列表: {opt_texts}")
                
                # 点击选项
                def click_opt(el):
                    try:
                        driver.execute_script("arguments[0].click();", el)
                    except Exception:
                        try:
                            el.click()
                        except Exception as e2:
                            logger.warning(f"选项点击失败: {e2}")
        
                def match_true_false(ans: str):
                    a = str(ans).strip()
                    if a in ("对","正确","TRUE","T","YES","Y","是"):
                        for i, t in enumerate(opt_texts):
                            if "对" in t or "正确" in t:
                                return i
                    if a in ("错","错误","FALSE","F","NO","N","否"):
                        for i, t in enumerate(opt_texts):
                            if "错" in t or "错误" in t:
                                return i
                    return None
        
                # 依据提示词：优先按字母选项；判断题则匹配“对/错”；无法判断时也要选择一个
                normalized = []
                for s in selected or []:
                    if not s:
                        continue
                    s2 = str(s).strip()
                    # 提示词要求字母返回，统一转大写
                    normalized.append(s2.upper())
        
                indices_to_click = []
                for ans in normalized:
                    # 字母选项（A/B/C/...）
                    if ans and ans[0].isalpha():
                        idx = ord(ans[0]) - ord('A')
                        if options and 0 <= idx < len(options):
                            indices_to_click.append(idx)
                            logger.info(f"选择字母答案: {ans} -> 选项索引 {idx}")
                            continue
                    # 判断题匹配
                    idx_tf = match_true_false(ans)
                    if idx_tf is not None:
                        indices_to_click.append(idx_tf)
                        logger.info(f"选择判断题答案: {ans} -> 选项索引 {idx_tf}")
        
                # 若仍未有任何可点击索引，按提示词“无法判断则返回一个你认为对的选择”，选择第一个
                if options and not indices_to_click:
                    indices_to_click = [0]
                    logger.info(f"未能从答案列表匹配到选项，按提示词策略选择第一个选项: {opt_texts[0]}")
        
                # 去重并按索引升序点击（避免重复点击）
                for idx in sorted(set(indices_to_click)):
                    try:
                        click_opt(options[idx])
                    except Exception as e:
                        logger.warning(f"点击选项索引 {idx} 失败: {e}")
        
                # 提交答案
                submit = driver.execute_script(
                    "return document.querySelector('div.question-body .submit-footer .submit-btn span.submits');"
                )
                if submit:
                    try:
                        driver.execute_script("arguments[0].click();", submit)
                        logger.info("已点击提交按钮")
                    except Exception:
                        try:
                            submit.click()
                            logger.info("已点击提交按钮")
                        except Exception as e2:
                            logger.warning(f"提交按钮点击失败: {e2}")
                else:
                    logger.warning("未找到提交按钮")
            except Exception as e:
                logger.error(f"页面答题流程失败: {e}")

            sleep(2)
            
            # HACK: 关闭页面
            close_box = driver.execute_script(
                """
                var root = document.querySelector('div.ai-test-question-wrapper');
                if (!root) return null;
                return root.querySelector('.header-box .close-box')
                    || root.querySelector('.header-box [class*="close"]')
                    || root.querySelector('.header-box .right-box .close-box')
                    || root.querySelector('.header-box .close');
                """
            )
            if close_box:
                try:
                    driver.execute_script(
                        """
                        var el = arguments[0];
                        try { el.scrollIntoView({block:'center', inline:'center'}); } catch(e){}
                        try { el.click(); } catch(e){}
                        try {
                            var rect = el.getBoundingClientRect();
                            var opts = {view: window, bubbles: true, cancelable: true, clientX: rect.left + rect.width/2, clientY: rect.top + rect.height/2};
                            ['pointerdown','mousedown','mouseup','click'].forEach(function(t){ try { el.dispatchEvent(new MouseEvent(t, opts)); } catch(e){} });
                        } catch(e) {}
                        """,
                        close_box,
                    )
                    logger.info("已触发关闭按钮事件")
                except Exception as e:
                    logger.warning(f"关闭按钮事件派发失败: {e}")

                # 验证是否关闭
                try:
                    closed = driver.execute_script(
                        "var r=document.querySelector('div.ai-test-question-wrapper'); return !r || r.style.display==='none' || r.offsetParent===null;"
                    )
                except Exception:
                    closed = False
                if not closed:
                    close_box.click()
            else:
                logger.error("未找到关闭按钮")
            return True
        return False