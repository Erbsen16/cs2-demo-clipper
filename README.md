# CS2 自动剪辑

Windows 本地桌面工具。Demo 和录像均在本机处理。

## 启动

1. 在 Windows 10/11 x64 上安装 Python 3.11–3.13（勾选 **Add python.exe to PATH**）、Steam 和 CS2。
2. 在 GitHub 点击 **Code → Download ZIP** 并解压，或使用 Git 克隆仓库。
3. 双击解压目录里的 **Start CS2 Editor.cmd**。首次启动会安装 Python 依赖，从上游发布页下载录制组件并验证 SHA-256。准备完成后会自动打开本地网页。使用期间保留启动窗口。

如需剪辑已有录像，完成首次启动后可运行 `python app.py` 打开桌面界面。

## 直接从 Demo 自动出片

保持 Steam 登录，关闭其他正在进行的 CS2 游戏。拖入一份 .dem，选择选手和剪辑模式，点 **自动导出 MP4**。录制时游戏窗口会自动打开，完成后网页会触发下载，也可以点「下载成片」。

网页使用首次启动时下载的 [CS2 Video Generator](https://github.com/CS2OpenDev/CS2VideoGenerator/releases/tag/v0.10.1) 驱动本机 CS2 录制，再用 FFmpeg 烧录击杀计数并合并。默认 1280×720、24 帧。录制组件会临时备份和调整游戏文件并在录制结束后还原，请等待结束再进行在线游戏。

## 画面统计

导出时可选「仅击杀」「击杀-死亡」或「不显示」，也可以单独取消「显示 KILLS 字样」以只保留数字。「仅击杀」累计成片里出现的击杀。「击杀-死亡」按比赛时间显示选手的全场累计战绩，即使只剪某类枪械也会带入片段开始前的战绩。击杀数恰好为 1 时使用小写 i，例如 0-3 → i3 → i4 → 2-4，1 杀 20 死显示为 i20。

## 从已有录像剪辑

1. 选择 CS2 比赛的 `.dem` 文件，再选择选手。
2. 选择同一场比赛中该选手的连续视角录像。用 CS2 回放 Demo，切到该选手，以正常速度录制并避免暂停、跳转或切换视角。
3. 在事件表中选中一条击杀或死亡，点击 **用选中事件对齐** 自动填入 Tick，再输入同一事件在录像中的秒数。例如，界面显示首个击杀在 Tick 6400，录像里看到该击杀发生在 12.5 秒，就填 Tick 6400 和录像 12.5 秒。Tick 率默认 64。
4. 选择 **高光**、**全部击杀** 或 **全部死亡**。击杀和高光可以按狙击、步枪、手枪、冲锋枪筛选。
5. 选好画面统计样式，点 **从已有录像导出**。

高光规则包括单回合多杀、爆头、盲狙、穿烟和穿墙。每个事件截取前 5 秒至后 3 秒，重叠片段合并。

## 许可证与依赖

本项目源码采用 [MIT 许可证](LICENSE)。CS2 由 Steam 提供。录制组件、Demo 解析库和 FFmpeg 使用各自的许可证，详见 [CS2 Video Generator 第三方声明](https://github.com/CS2OpenDev/CS2VideoGenerator/blob/v0.10.1/THIRD-PARTY-NOTICES.md)、[demoparser2](https://github.com/LaihoE/demoparser) 和 [imageio-ffmpeg](https://github.com/imageio/imageio-ffmpeg)。
