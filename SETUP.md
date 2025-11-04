# 环境配置指南

## 配置 Azure OpenAI API 密钥

### 方法 1: 使用环境变量（推荐）

**Windows (PowerShell):**
```powershell
$env:AZURE_OPENAI_API_KEY="your-api-key-here"
```

**Linux/Mac (Bash):**
```bash
export AZURE_OPENAI_API_KEY="your-api-key-here"
```

### 方法 2: 使用 .env 文件

1. 复制示例文件：
```powershell
Copy-Item .env.example .env
```

2. 编辑 `.env` 文件，填入你的 API 密钥：
```
AZURE_OPENAI_API_KEY=your-actual-api-key
```

3. 在代码中加载 .env 文件：
```python
from dotenv import load_dotenv
load_dotenv()

from llm_config import configure_azure_openai
lm = configure_azure_openai()
```

**注意**: `.env` 文件已被添加到 `.gitignore`，不会被提交到 git。

## 获取 API 密钥

联系项目管理员获取 Azure OpenAI API 密钥。

当前使用的端点：
- **Endpoint**: https://liby-ai-terminal-v1-koreacentral-gpt-5-01.openai.azure.com
- **Deployment**: gpt-5
- **API Version**: 2024-06-01
