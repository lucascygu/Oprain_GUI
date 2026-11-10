# BCIMods 部署与台架验证

## 选择匹配的接收端

| 手头的硬件 | 采集入口 | 当前可验证的范围 |
| --- | --- | --- |
| 以 Cyton + Daisy 串口协议输出的 BCIMods | `main.py --board cyton-daisy --port COM5` | 标准 BrainFlow 配置为 16 通道，每通道 125 S/s。 |
| FreeEEG32-beta，STM32H743ZI 与四颗 AD7771 | `main.py --board freeeeg32 --port COM5` | 标准配置为 32 通道，每通道 512 S/s。可记录原始数据并回放。 |
| Arduino Due 与四块 8 通道 ADS1299 HackEEG Shield | Starcat `multiboard` 固件及同分支 Python 客户端 | 32 路板载测试信号。上游给出的四板测试点为 500 S/s。该固件使用独立的串口协议。 |

Oprain 产品页标注 BCIMods 系列最高 64 通道。接线前先核对板卡版本、主控、模拟前端和 USB/无线协议。标准 Cyton + Daisy、FreeEEG32 与 HackEEG 各自采用上表所列的数据格式。[BCIMods 产品页](https://oprain.com/projects/bcimods/) · [FreeEEG32 BOM](https://github.com/lucascygu/FreeEEG32-beta/blob/bc4e9fd4ecf560f3b349afcb36dbf81ab811338c/AssemblyFiles/bom/components%20FreeEEG32%20beta.csv) · [BrainFlow 板型](https://brainflow.readthedocs.io/en/stable/SupportedBoards.html)

## 在电脑上验证采集端

在 Windows 按首页命令安装。先运行 `--board demo32` 看 32 路测试波形，再用以下命令录制和回放。`COM5` 是示例，实板请改成设备管理器中的端口。Linux 可使用 `/dev/ttyACM0` 或系统分配的其他串口。

```powershell
.\.venv\Scripts\python.exe main.py --board demo32 --check 10 --record demo32.tsv
.\.venv\Scripts\python.exe main.py --board freeeeg32 --replay demo32.tsv
.\.venv\Scripts\python.exe main.py --board freeeeg32 --port COM5 --check 60 --record bench32.tsv
```

`nominal_sps` 来自板型描述。`received_sps` 用每通道实际收到的样本数除以经过秒数。`counter_discontinuities` 为序号跳变次数。要把实测速率加入退出条件，可在 `--check` 后加 `--min-sps` 和验收值。GUI 对波形做去趋势和 1–50 Hz 带通，原始记录保留全部板卡行。

Linux 上可用 BrainFlow 5.24.0 的官方串口模拟器复现两条原生驱动路径。从本仓库根目录运行以下命令。模拟器把虚拟串口名追加在 `--port` 后面。

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
git clone --branch 5.24.0 --depth 1 --filter=blob:none --sparse https://github.com/brainflow-dev/brainflow.git ../brainflow-test
git -C ../brainflow-test sparse-checkout set emulator
PYTHONPATH=../brainflow-test/emulator .venv/bin/python -m brainflow_emulator.freeeeg32_linux .venv/bin/python main.py --board freeeeg32 --check 3 --port
PYTHONPATH=../brainflow-test/emulator .venv/bin/python -m brainflow_emulator.cyton_linux .venv/bin/python main.py --board cyton-daisy --check 3 --port
```

FreeEEG32 模拟器每包等待 5 ms，测试用于核对通道顺序和序号连续性。实板的持续速率请从接线后的日志读取。[官方模拟器源码](https://github.com/brainflow-dev/brainflow/blob/915009afb0a0ea41095dc9cf90e28a99bef8c38f/emulator/brainflow_emulator/freeeeg32_emulator.py)

## 四颗 ADS1299 的参考固件

下列命令从本仓库根目录运行，目标为 **Arduino Due 原生 USB 口与 HackEEG 四板堆叠**。在 Linux 或已有 Python 的开发机上构建。配置锁定 Atmel SAM 8.3.0 与 ArduinoJson 6.15.2。这版旧固件用了早期 ArduinoJson 接口。

```bash
git clone https://github.com/starcat-io/hackeeg-driver-arduino.git ../hackeeg-fw
git -C ../hackeeg-fw checkout --detach b4f0611e509e83351a58f747fea73426687c026f
python3 -m venv ../hackeeg-build-env
../hackeeg-build-env/bin/python -m pip install platformio==6.2.0
cp deploy/hackeeg-platformio.ini ../hackeeg-fw/platformio.ini
../hackeeg-build-env/bin/pio run -d ../hackeeg-fw -e due_native
```

产物在 `../hackeeg-fw/.pio/build/due_native/firmware.bin`。核对实物型号后，可用同一环境的 `pio run -d ../hackeeg-fw -e due_native -t upload --upload-port <实际端口>` 写入匹配的 Due。上游说明列出了板 1–3 的片选和 DRDY 跳线。台架首测使用片内测试波，HackEEG 及连接的电脑按厂商要求使用电池供电。[硬件与多板接线](https://docs.starcat.io/hackeeg-crowdsupply/user/hardware-32-channel.html) · [参考固件](https://github.com/starcat-io/hackeeg-driver-arduino/tree/b4f0611e509e83351a58f747fea73426687c026f)

上位机使用配套的 `hackeeg-client-python` 的 `multiboard` 分支（提交 `a659148d2bb342ce08686067663270a9016e2646`）。按上游 Linux/macOS 安装说明配置客户端后，运行 `hackeeg_stream --channel-test --sps 500 --samples 2000`。单块 8 通道通过 USB DMA 可达 16 kS/s，是另一个测试条件。若已有树莓派 4，可将 Due 的原生 USB 接到树莓派，由配套客户端把 LSL 数据送到同一 Wi-Fi 下的电脑。移植到 BCIMods 需要对应版本的原理图，以及四颗 ADC 的时钟、片选和 DRDY 定义。[四板软件与测试命令](https://docs.starcat.io/hackeeg-crowdsupply/user/software-installation-32-channel.html) · [八通道高速规格](https://docs.starcat.io/hackeeg-crowdsupply/user/hackeeg.html) · [树莓派无线转发](https://docs.starcat.io/hackeeg-crowdsupply/user/raspberry-pi.html)

## 编译 FreeEEG32-beta 参考固件

Linux 环境需安装 GNU Make 与 `arm-none-eabi-gcc`。本次验证使用 Arm Embedded GCC 7.2.1。以下命令从独立工作目录运行。`BUILD_DIR` 指定空输出目录，避开上游归档自带的旧编译文件。

```bash
git clone https://github.com/lucascygu/FreeEEG32-beta.git
git -C FreeEEG32-beta checkout --detach bc4e9fd4ecf560f3b349afcb36dbf81ab811338c
tar -xzf FreeEEG32-beta/Firmware/STM32H743ZI_beta_80MHz_makefile.tar.gz
make -C STM32H743ZI_beta_80MHz_makefile -j4 BUILD_DIR=oprain-build
```

该构建的 ELF 保留 Flash `0x08000000` 与 RAM 中 `.dma_buffer` `0x30000000` 的不同装载地址。直接把全部装载段摊平成 `.bin` 会生成约 640 MiB 的地址空洞。此版本使用带地址的 ELF，调试器和接线按该硬件版本的上游指南配置。[上游固件与调试说明](https://github.com/lucascygu/FreeEEG32-beta/tree/bc4e9fd4ecf560f3b349afcb36dbf81ab811338c)

## 测量 2.4 GHz 回传

若 8/16 kHz 指每通道采样率，32 通道 × 24 位原始数据分别需要 6.144/12.288 Mbit/s。若指接收器回报率，则分别统计每秒收到的包数和每包的样本数。选择无线模块前先核对接收器芯片、固件以及空中协议。两端可使用 Wi-Fi 时，可用 Espressif 的 iPerf 示例测板到电脑的方向。[Espressif 示例](https://github.com/espressif/esp-idf/tree/v5.4.2/examples/wifi/iperf) · [iPerf 命令参数](https://components.espressif.com/components/espressif/iperf-cmd/versions/0.1.2/readme?language=en)

1. 在已配置的 ESP-IDF v5.4.2 开发环境中进入 `examples/wifi/iperf`，运行 `idf.py set-target esp32` 和 `idf.py build`。该目标适用于经典 ESP32 开发板，其他型号选用对应 target。给参考板烧录示例后，用 `idf.py monitor` 进入控制台。
2. 电脑和 ESP32 接入同一 2.4 GHz 局域网。在电脑启动 iPerf **2.x** 的 UDP 服务端 `iperf -s -u -i 1`。
3. 在 ESP 控制台运行 `sta_connect <SSID> <密码>`。将下面示例 IP 换为电脑局域网 IPv4，然后依次测试两个发送速率。

```text
iperf -c 192.0.2.10 -u -l 1200 -b 8 -i 1 -t 60
iperf -c 192.0.2.10 -u -l 1200 -b 16 -i 1 -t 60
```

保存电脑接收端的实际吞吐、抖动、丢包数和测试距离。8、16 Mbit/s 是为原始样本之外的开销留出余量的台架测试点。换成真实采集帧后，还应把板端采样计数和主机文件逐通道对齐，再确定该组合下能持续达到的采样率。
