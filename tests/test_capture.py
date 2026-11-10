import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from brainflow.board_shim import BoardIds, BoardShim
from brainflow.data_filter import DataFilter


MAIN = Path(__file__).resolve().parents[1] / 'main.py'


def capture(*args):
    return subprocess.run([sys.executable, str(MAIN), *map(str, args)], capture_output=True, text=True, timeout=15)


class CaptureTest(unittest.TestCase):
    def test_32_channel_recording_replay_and_counter_gap(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'demo.tsv'
            run = capture('--board', 'demo32', '--check', '1', '--record', path)
            self.assertEqual(run.returncode, 0, run.stderr)
            summary = json.loads(run.stdout)
            self.assertEqual(summary['eeg_channels'], 32)
            self.assertEqual(summary['counter_discontinuities'], 0)
            profile = BoardIds.FREEEEG32_BOARD.value
            data = DataFilter.read_file(str(path))
            self.assertEqual(data.shape[0], BoardShim.get_num_rows(profile))
            self.assertGreater(data.shape[1], 50)
            channels = BoardShim.get_eeg_channels(profile)
            self.assertTrue(np.all(np.ptp(data[channels], axis=1) > 0))

            original = path.read_bytes()
            self.assertNotEqual(capture('--board', 'demo32', '--check', '.1', '--record', path).returncode, 0)
            self.assertEqual(path.read_bytes(), original)
            ok = capture('--board', 'freeeeg32', '--replay', path, '--check', '.3')
            self.assertEqual(ok.returncode, 0, ok.stderr)
            missed = Path(tmp) / 'missing-sample.tsv'
            DataFilter.write_file(np.delete(data, 25, axis=1), str(missed), 'w')
            gap = capture('--board', 'freeeeg32', '--replay', missed, '--check', '.3')
            self.assertEqual(gap.returncode, 1, gap.stderr)
            self.assertEqual(json.loads(gap.stdout)['counter_discontinuities'], 1)

    def test_measured_rate_gate(self):
        run = capture('--board', 'demo32', '--check', '.5', '--min-sps', '8000')
        self.assertEqual(run.returncode, 1, run.stderr)
        self.assertEqual(json.loads(run.stdout)['nominal_sps'], 512)
