# 固定配音

所有项目固定使用豆包语音合成 2.0、刘飞、0.95 倍语速，不进行选声比较，也不读取外部选声偏好文件。`project.json` 可以省略 `voice`；默认配置为：

```json
{"provider":"doubao","model":"seed-tts-2.0","speaker":"zh_male_liufei_uranus_bigtts","speed":0.95}
```

显式填写这四项时必须与上述值一致，否则构建报错。

## 语气与发音

默认采用自然普通话讲解语气，语速平稳，因果和对比有重音，推导之间留停顿。可用全片 `voice.instruct` 调整表达，用 `pronunciation_dict: {"tone":["原词/修正读法"]}` 修正术语发音；它们不改变字幕正文。录音重试由流水线记录，不提供生成种子参数。

按语义确定录音段和 `narration_groups`，相连镜头可以共享配音。使用 `build --stop-after audio` 检查实际旁白，复查开头、中间、结尾及独立录音接缝。语气或发音异常时重做相应录音段；不通过换声、变调或后期变速处理。

## 凭证与运行

在火山引擎豆包语音控制台开通语音合成 2.0，创建新版控制台 API Key。运行进程只需要 `DOUBAO_API_KEY`；不要将密钥写进项目、命令参数、日志或交付物。

用户选择私密保存凭证时，可在工程外使用当前用户拥有、权限为 `0600` 的 JSON 文件，只包含 `DOUBAO_API_KEY` 字段。启动器只加载这一项，已有环境变量优先，不自动搜索凭证：

```bash
python3 <skill>/scripts/with_credentials.py <runtime>/doubao-credentials.json python3 <skill>/scripts/zvideo.py build <project> --stop-after audio
```

`doctor` 检查本地运行环境并报告凭证是否存在；不调用 API，也不证明账户有权限或余额。配音通过网络调用豆包，识别与对齐仍使用本地运行环境。

## 缓存与错误处理

豆包接口 `speech_rate` 固定为 `-5`，返回单声道 24 kHz PCM，保存为 WAV 进入识别、对齐和动画流程。字幕来自讲稿，时间戳来自实际波形对齐。

缓存记录文本、声音配置、适配器和波形指纹；只改画面复用旁白。服务商可能更新云模型权重，缓存的原始音频是本次生成依据。网络或服务错误立即停止，不自动重试收费请求；识别差异超阈值时仍按流水线上限重做录音（最多两次，服务会计费）。未实际试听不得标记听感通过。

接口依据：[豆包 HTTP 单向流式合成](https://docs.volcengine.com/docs/DoubaoVoice/unidirectional-streaming-text-to-speech-http?lang=zh)。
