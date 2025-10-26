# auto-zhihuishu
这是一个由Python编写的自动智慧树答题脚本。该脚本使用Selenium获取网页元素，通过OCR技术提取文字，再由LLM外置大脑进行思考答题。整个过程完全自动化，双击即可运行脚本。

## 如何使用
1. 首先确保你已安装Python 3.10+
2. 安装依赖
```bash
pip install -r requirements.txt
```
3. 下载Edge WebDriver
   - 请下载与你Edge浏览器版本匹配的WebDriver，下载地址：[Edge WebDriver](https://msedgedriver.microsoft.com/141.0.3537.99/edgedriver_win64.zip)
   - 下载完成后，将`edgedriver_win64.zip`文件解压到`tools`根目录下
   - 解压好后的文件结构应是
```
tools/
├── edgedriver_win64
├── llms
```
4. 配置文件
   - 请在项目根目录下打开`config.json`文件，配置好DeepSeek API Key
   - 将你的DeepSeek API Key替换`YOUR_API_KEY`
   - 配置好的`config.json`例子如下
```json
{
  "llm": {
    "deepseek": {
      "api_key": "sk-xxxx",
      "base_url": "https://api.deepseek.com",
      "model": "deepseek-chat"
    }
  },
  "web_config": {
    "driver_path": "edgedriver_win64",
    "cookie_path": "edgedriver_win64/cookies.json"
  }
}
```
5. 运行脚本
   - 双击`run.bat`文件即可运行脚本


## 如何获取DeepSeek API Key
**注意：需要充值才能使用API，金额无所谓，充值后即可使用**
1. 访问[DeepSeek API](https://platform.deepseek.com/)
2. 在`密码登录`中点击`立即注册`按钮
3. 填写注册信息
4. 注册成功后，登录账号
5. 在左侧侧边栏点击`API keys`
6. 点击`创建 API Key`按钮
7. 填写API Key名称
8. 点击`创建`按钮
9. 创建好后点击`复制`，即可获取到你的API Key
10. 请将获取到的API Key替换`config.json`中的`YOUR_API_KEY`



