# SSH 隧道访问说明

## 使用场景

未备案或不希望公开公网 Web 入口时，可以让服务器只在本机监听前端和后端端口，再通过 SSH 隧道从本地访问。

本文档仅记录通用 SSH 隧道访问方式，公开版本不得替换为真实服务器 IP、真实 SSH 用户名或真实私钥文件名。

推荐服务器端口绑定方式：

```text
frontend -> 127.0.0.1:5173
backend  -> 127.0.0.1:8000
redis    -> 127.0.0.1:6379
```

这样公网只需要开放 SSH 维护入口，前端、后端和 Redis 不直接暴露公网。

## 手动恢复 SSH 隧道

在本地 PowerShell 中执行：

```powershell
ssh -i .\<private-key.pem> `
  -N `
  -o ServerAliveInterval=30 `
  -o ServerAliveCountMax=3 `
  -L 5173:127.0.0.1:5173 `
  -L 8000:127.0.0.1:8000 `
  <ssh-user>@<server-public-ip>
```

参数说明：

- `-i .\<private-key.pem>`：指定本地 SSH 私钥文件。
- `-N`：只建立端口转发，不进入远程 shell。
- `ServerAliveInterval=30`：每 30 秒发送一次保活包。
- `ServerAliveCountMax=3`：连续 3 次无响应后断开。
- `-L 5173:127.0.0.1:5173`：本地 `localhost:5173` 转发到服务器本机前端端口。
- `-L 8000:127.0.0.1:8000`：本地 `localhost:8000` 转发到服务器本机后端端口。

该命令所在窗口需要保持打开。窗口关闭、电脑睡眠或网络切换后，隧道会断开。

`-i .\<private-key.pem>` 中的路径是相对当前 PowerShell 所在目录的私钥路径，不一定是项目根目录。手动执行时需要按实际位置填写，例如：

```powershell
# 在项目根目录执行，私钥也放在项目根目录时
ssh -i .\<private-key.pem> ...

# 使用绝对路径
ssh -i "D:\path\to\<private-key.pem>" ...

# 私钥放在用户 SSH 目录时
ssh -i "$HOME\.ssh\<private-key.pem>" ...
```

私钥文件不应提交 GitHub，建议通过 `.gitignore` 忽略 `*.pem`、`*.key` 等文件。

## 后台启动 SSH 隧道

如果不想占用 PowerShell 窗口，可以后台启动：

```powershell
Start-Process ssh.exe -ArgumentList @(
  "-i", ".\<private-key.pem>",
  "-N",
  "-o", "ExitOnForwardFailure=yes",
  "-o", "ServerAliveInterval=30",
  "-o", "ServerAliveCountMax=3",
  "-L", "5173:127.0.0.1:5173",
  "-L", "8000:127.0.0.1:8000",
  "<ssh-user>@<server-public-ip>"
) -WindowStyle Hidden
```

## 检查本地隧道是否正常

检查本地端口是否监听：

```powershell
Get-NetTCPConnection -LocalPort 5173,8000 -State Listen
```

检查后端健康状态：

```powershell
curl.exe http://localhost:8000/health
```

检查前端容器健康入口：

```powershell
curl.exe http://localhost:5173/health
```

浏览器访问：

```text
http://localhost:5173/
http://localhost:5173/login
```

## 检查远程服务器服务状态

如果本地 `localhost` 无法访问，先判断是隧道问题还是服务器服务问题。

检查 SSH 是否能连上服务器：

```powershell
ssh -i .\<private-key.pem> <ssh-user>@<server-public-ip> "echo ssh_ok"
```

检查远程容器状态：

```powershell
ssh -i .\<private-key.pem> <ssh-user>@<server-public-ip> `
  "cd /opt/drone-low-altitude-agent/app && docker compose ps"
```

检查远程后端健康状态：

```powershell
ssh -i .\<private-key.pem> <ssh-user>@<server-public-ip> `
  "curl -fsS http://127.0.0.1:8000/health"
```

检查远程前端健康状态：

```powershell
ssh -i .\<private-key.pem> <ssh-user>@<server-public-ip> `
  "curl -fsS http://127.0.0.1:5173/health"
```

如果远程健康检查正常，但本地 `localhost:5173` / `localhost:8000` 无法访问，通常是本地 SSH 隧道断了，重新执行隧道命令即可。

## 查看和关闭本地 SSH 隧道

查看本地 SSH 进程：

```powershell
Get-Process ssh
```

查看 SSH 进程命令行：

```powershell
Get-CimInstance Win32_Process -Filter "name = 'ssh.exe'" |
  Select-Object ProcessId,CommandLine
```

关闭指定 SSH 隧道进程：

```powershell
Stop-Process -Id <ssh-process-id>
```

## 常见问题

### 本地网页打不开

先检查：

```powershell
Get-NetTCPConnection -LocalPort 5173,8000 -State Listen
```

如果没有输出，说明本地 SSH 隧道没有建立或已经断开。

### 后端 health 没反应

先检查本地：

```powershell
curl.exe http://localhost:8000/health
```

再检查远程：

```powershell
ssh -i .\<private-key.pem> <ssh-user>@<server-public-ip> `
  "curl -fsS http://127.0.0.1:8000/health"
```

如果远程正常、本地失败，是隧道问题。如果远程也失败，再检查容器：

```powershell
ssh -i .\<private-key.pem> <ssh-user>@<server-public-ip> `
  "cd /opt/drone-low-altitude-agent/app && docker compose ps && docker compose logs --tail=100 app"
```

### 本地端口被占用

检查占用进程：

```powershell
Get-NetTCPConnection -LocalPort 5173,8000 -State Listen |
  Select-Object LocalAddress,LocalPort,OwningProcess
```

必要时关闭旧的 SSH 进程：

```powershell
Stop-Process -Id <ssh-process-id>
```

## 安全注意事项

- 不要把真实服务器公网 IP 写入公开文档。
- 不要把真实 SSH 私钥文件提交 Git。
- 不要把管理员账号、演示账号密码、API key、JWT secret 写入 Git。
- README 中只说明演示获取方式，不直接公开真实演示入口。
- 如果需要短期公网演示，应临时开放 HTTP/HTTPS，演示后关闭公网 Web 入口或收紧安全组。
