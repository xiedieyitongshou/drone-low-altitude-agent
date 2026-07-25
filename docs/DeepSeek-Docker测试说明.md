# DeepSeek Docker 测试说明

本文档用�?Day 50：在 Docker 环境中验�?DeepSeek 自然语言解析�?
## 1. API Key 放哪�?
DeepSeek API Key 放在项目根目�?`.env` 文件中，不要写进�?
- `Dockerfile`
- `docker-compose.yml`
- 前端代码
- GitHub 仓库

推荐�?Docker 示例复制�?
```powershell
Copy-Item .env.docker.example .env
```

然后�?`.env` 中填写：

```env
LLM_ENABLED=true
LLM_PROVIDER=deepseek
LLM_MODEL=deepseek-v4-flash
DEEPSEEK_API_KEY=你的_deepseek_api_key
NL_PARSER_MODE=hybrid
```

也可以使用通用变量�?
```env
LLM_API_KEY=你的_deepseek_api_key
```

如果 `LLM_API_KEY` �?`DEEPSEEK_API_KEY` 都存在，代码优先读取 `LLM_API_KEY`�?
## 2. 为什么不�?Dockerfile

`Dockerfile` 会构建镜像。如果把 API Key 写进 Dockerfile，key 可能被打进镜像层，后续推送镜像或分享镜像时存在泄露风险�?
当前做法是：

```text
Dockerfile：只放非敏感默认配置
docker-compose.yml：声明环境变量如何注入容�?.env：保存真�?API Key，本地使用，不提�?Git
```

## 3. Docker 启动

在项目根目录运行�?
```powershell
docker compose up --build
```

后台启动�?
```powershell
docker compose up --build -d
```

查看后端日志�?
```powershell
docker compose logs -f app
```

## 4. 验证 Agent 接口

后端启动后，可以请求 `/agent/query`�?
PowerShell 示例�?
```powershell
Invoke-RestMethod `
  -Uri "http://127.0.0.1:8000/agent/query" `
  -Method Post `
  -ContentType "application/json" `
  -Body '{"query":"深圳湾明天下�?点到5点可以飞�?,"session_id":"docker-deepseek-demo","user_id":"default_user"}'
```

重点查看响应字段�?
```text
parser_source
parsed
warnings
```

预期�?
- DeepSeek 成功：`parser_source=llm`
- DeepSeek 失败但规则解析成功：`parser_source=llm_fallback_rule`
- 关闭 LLM �?`NL_PARSER_MODE=rule`：`parser_source=rule`

## 5. 建议测试输入

```text
深圳湾明天下�?点到5点可以飞�?深圳未来72小时最佳执行窗口是什么时�?深圳湾、南山区、宝安机场附近明天下午哪个更适合先巡检
那换成测绘呢
帮我看看明天能不能飞
```

## 6. 成本控制

建议开发时使用�?
```env
NL_PARSER_MODE=hybrid
LLM_TIMEOUT_SECONDS=20
LLM_MAX_TOKENS=600
```

不要对同一条输入反复高频调用。Day 50 的批量样例测试建议先做少量手动验证，再决定是否写自动化测试�?
