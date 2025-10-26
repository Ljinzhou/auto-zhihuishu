import json
import re
import json
from typing import List, Dict, Any
from openai import OpenAI
from loguru import logger
from config.JsonLoadConfig import get_llm_deepseek_config


# DeepSeek 配置
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"


class DeepSeek:
    def __init__(
        self,
    ):
        # 统一从 JsonLoadConfig 读取
        ds = get_llm_deepseek_config()
        self.api_key = ds.get("api_key")
        if not self.api_key or self.api_key == "YOUR_API_KEY":
            logger.error("DeepSeek API 密钥未配置")
            raise RuntimeError("请在 config.json 的 llm.deepseek.api_key 写入真实的密钥，或在代码中传入 api_key。")
        self.client = OpenAI(api_key=self.api_key, base_url=ds.get("base_url") or DEEPSEEK_BASE_URL)
        self.model = ds.get("model") or DEEPSEEK_MODEL
        logger.info(f"DeepSeek 初始化完成，模型：{self.model}")

    def answer_question(self, qa_text: str) -> Dict[str, Any]:
        """
        直接把题目与选项的原始文本交给模型，不做任何预处理/分离。
        要求模型只返回严格 JSON：{"selected": ["A"]}。
        """
        if not qa_text:
            logger.error("题目不能为空")
            raise ValueError("qa_text 不能为空")

        sys_prompt = (
            "你是答题助手，题目和答案我将会一起给你，请你自行判断是否为单选题或多选题。只返回严格 JSON（不包含任何额外文本或代码块）。"
            "若是判断题，则只返回 {\"selected\": [\"对\"]} 或 {\"selected\": [\"错\"]}。"
            "如果你无法判断这道题的正确答案，则返回一个你认为对的选择，前提是需要判断出这是选择题还是判断题。"
            "字段：selected；值为选项字母数组，如格式：{\"selected\": [\"A\"]}；多选则返回多个字母，如 {\"selected\": [\"A\", \"C\"]}。"
            "用户给出的原始文本中可能存在其他信息不是题干或者选项的，请你自行识别题干与选项并选择答案。"
        )
        messages = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": qa_text},
        ]

        logger.info(f"问题：{qa_text}")
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
        )
        logger.info(f"DeepSeek 原始回复：{resp}")
        
        # 提取模型回复内容
        content = resp.choices[0].message.content if resp and resp.choices else ""
        logger.info(f"DeepSeek 回复内容：{content}")
        
        return self.parse_content(content)

    def parse_content(self, content: str) -> Dict[str, Any]:
        """
        仅解析模型返回的严格 JSON，提取 selected 数组。
        - 允许答案元素为选项字母（统一转为大写）、中文“对/错”、或选项原文；
        - 若解析不到有效 selected，则返回空数组。
        """
        raw = content or ""
        cleaned = raw.strip()
        cleaned = re.sub(r"^```json\s*|\s*```$", "", cleaned)
        cleaned = re.sub(r"^```\s*|\s*```$", "", cleaned)

        result: Dict[str, Any] = {"selected": [], "raw": raw}
        try:
            data = json.loads(cleaned)
            sel = data.get("selected")
            if isinstance(sel, list):
                selected: List[str] = []
                for s in sel:
                    if s is None:
                        continue
                    token = str(s).strip()
                    if not token:
                        continue
                    # 字母统一大写，其余保留原样（含“对/错”和选项原文）
                    if re.fullmatch(r"[A-Za-z]", token):
                        token = token.upper()
                    selected.append(token)
                result["selected"] = selected
        except Exception:
            pass
        logger.debug(f"DeepSeek.parse_content: result={result}")
        return result


def get_client() -> DeepSeek:
    """
    获取一个 DeepSeek 客户端实例。
    """
    return DeepSeek()


if __name__ == "__main__":
    # 示例：单一字符串输入
    client = get_client()
    qa_text = (
        "执行以int a=10;printf(“%d”,a++);后的输出结果和a的值是（ ）。"
        "A. 10和11"
        "B. 11和10"
        "C. 10和10"
        "D. 11和11"
    )
    result = client.answer_question(qa_text)
    
    print(json.dumps({"selected": result["selected"]}, ensure_ascii=False)) # 模型返回的 JSON 字符串
    print(result["raw"])    # 原始文本
    print(result["selected"])   # 解析后的选项字母数组
    print(result["selected"][0]) # 第一个选项字母
