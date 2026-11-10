# Oprain GUI

Live time-domain and frequency plots, raw recording, and a headless acquisition check for BCIMods-compatible devices. The default serial profile is OpenBCI Cyton + Daisy. The FreeEEG32 profile reads 32 channels through BrainFlow. [中文部署与台架验证](docs/deployment.md)

## Run on Windows

From this checkout with 64-bit Python 3.12 installed, run the following in PowerShell.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py --board demo32
```

The demo generates 32 test tones and plays them through BrainFlow. For a live device, use the COM port shown in Device Manager. On Linux use `python3 -m venv .venv`, then `.venv/bin/python` and the serial device path. The existing `nix develop` shell is also available.

```powershell
.\.venv\Scripts\python.exe main.py --board cyton-daisy --port COM5
.\.venv\Scripts\python.exe main.py --board freeeeg32 --port COM5 --check 10 --record run32.tsv
.\.venv\Scripts\python.exe main.py --board freeeeg32 --replay run32.tsv
```

| Profile | EEG channels | Nominal rate per channel | Input |
| --- | ---: | ---: | --- |
| `cyton-daisy` | 16 | 125 S/s | Cyton + Daisy compatible serial device |
| `freeeeg32` | 32 | 512 S/s | FreeEEG32 serial protocol |
| `demo32` | 32 | 512 S/s | Generated FreeEEG32-layout playback |

`--check SECONDS` prints the received rate, count per channel, counter discontinuities, and nonfinite EEG values as JSON. A failed acquisition, zero samples, a counter discontinuity, a nonfinite EEG value, or a rate below an optional `--min-sps` returns a nonzero exit code. Set `--min-sps` to the threshold needed for that test. The counter wraps at 256, so a whole counter cycle of missing wire packets can be invisible to this check.

`--record` creates a new tab-separated BrainFlow file containing all board rows with one sample per line. Existing files are protected. Recording occurs before the GUI display filter. Select the same board profile for replay. Run `python -m unittest discover -s tests` for the hardware-free regression checks.
