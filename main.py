import argparse
import json
import math
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

import numpy as np
from brainflow.board_shim import BoardIds, BoardShim, BrainFlowError, BrainFlowInputParams
from brainflow.data_filter import DataFilter, DetrendOperations, FilterTypes


BOARDS = {
    'cyton-daisy': BoardIds.CYTON_DAISY_BOARD.value,
    'freeeeg32': BoardIds.FREEEEG32_BOARD.value,
}
WINDOW_SIZE = 256
CHANNEL_COLORS = [
    (255, 0, 0), (0, 255, 0), (0, 128, 255), (255, 255, 0),
    (255, 0, 255), (0, 255, 255), (255, 165, 0), (160, 80, 255),
    (25, 155, 25), (255, 192, 203), (165, 82, 42), (160, 160, 160),
    (0, 175, 175), (240, 128, 128), (150, 90, 175), (240, 230, 140),
]


def parse_args():
    parser = argparse.ArgumentParser(description='Display or check a BCIMods-compatible data stream.')
    parser.add_argument('--board', choices=[*BOARDS, 'demo32'], default='cyton-daisy')
    source = parser.add_mutually_exclusive_group()
    source.add_argument('--port', help='Serial device, for example COM5 or /dev/ttyACM0.')
    source.add_argument('--replay', type=Path, help='Read a BrainFlow recording made with the selected board profile.')
    parser.add_argument('--check', type=float, metavar='SECONDS', help='Run a timed capture without a display.')
    parser.add_argument('--min-sps', type=float, help='Require this measured per-channel rate during --check.')
    parser.add_argument('--record', type=Path, help='Create a new raw BrainFlow TSV recording.')
    args = parser.parse_args()
    if args.check is not None and (not math.isfinite(args.check) or args.check <= 0):
        parser.error('--check requires a positive, finite number of seconds')
    if args.min_sps is not None and (args.check is None or not math.isfinite(args.min_sps) or args.min_sps <= 0):
        parser.error('--min-sps requires --check and a positive, finite rate')
    if args.board == 'demo32' and (args.port or args.replay):
        parser.error('demo32 generates its own playback input')
    if args.replay is not None and not args.replay.is_file():
        parser.error(f'replay file does not exist: {args.replay}')
    if sys.platform == 'win32' and args.board != 'demo32' and not (args.port or args.replay):
        parser.error('specify --port COM<number> for the board in Device Manager')
    return args


def make_demo(path, profile):
    """Make four seconds of labelled test tones in the FreeEEG32 playback layout."""
    rate = BoardShim.get_sampling_rate(profile)
    index = np.arange(4 * rate)
    seconds = index / rate
    data = np.zeros((BoardShim.get_num_rows(profile), len(index)))
    for channel, row in enumerate(BoardShim.get_eeg_channels(profile)):
        data[row] = 600 * np.sin(2 * np.pi * (channel + 3) * seconds)
    data[BoardShim.get_package_num_channel(profile)] = index % 256
    data[BoardShim.get_timestamp_channel(profile)] = 1_700_000_000 + seconds
    DataFilter.write_file(data, str(path), 'w')


@contextmanager
def session(board, record, loop_demo):
    board.prepare_session()
    try:
        if loop_demo:
            board.config_board('loopback_true')
        streamer = ''
        if record is not None:
            # Reserve the name exclusively before giving it to BrainFlow's native writer.
            with record.open('xb'):
                pass
            streamer = f'file://{record.resolve().as_posix()}:a'
        try:
            board.start_stream(45000, streamer)
        except BrainFlowError:
            if record is not None and record.stat().st_size == 0:
                record.unlink()
            raise
        try:
            yield
        finally:
            board.stop_stream()
    finally:
        board.release_session()


def check_stream(board, profile, seconds, source_name, min_sps):
    channels = BoardShim.get_eeg_channels(profile)
    counter_row = BoardShim.get_package_num_channel(profile)
    # The Daisy driver combines two consecutive wire packets into one 16-channel sample.
    step = 2 if profile == BOARDS['cyton-daisy'] else 1
    count = breaks = nonfinite = 0
    last = None
    started = time.monotonic()
    while True:
        remaining = started + seconds - time.monotonic()
        if remaining > 0:
            time.sleep(min(remaining, 0.10))
        block = board.get_board_data()
        if block.shape[1]:
            count += block.shape[1]
            nonfinite += int((~np.isfinite(block[channels])).sum())
            counters = block[counter_row].astype(np.int64)
            if last is not None and (int(counters[0]) - last) % 256 != step:
                breaks += 1
            breaks += int(np.count_nonzero(np.diff(counters) % 256 != step))
            last = int(counters[-1])
        if time.monotonic() >= started + seconds:
            break
    elapsed = time.monotonic() - started
    measured = count / elapsed
    print(json.dumps({
        'source': source_name, 'eeg_channels': len(channels),
        'nominal_sps': BoardShim.get_sampling_rate(profile), 'samples_per_channel': count,
        'elapsed_s': round(elapsed, 3), 'received_sps': round(measured, 2),
        'counter_discontinuities': breaks, 'nonfinite_eeg_values': nonfinite,
    }))
    return 0 if count and not breaks and not nonfinite and measured >= (min_sps or 0) else 1


def display(board, profile, source_name):
    import pygame

    channels = BoardShim.get_eeg_channels(profile)
    rate = BoardShim.get_sampling_rate(profile)
    timestamp_row = BoardShim.get_timestamp_channel(profile)
    width, height = 1200, 800
    half = width // 2
    title_height = 28
    track = (height - title_height) / len(channels)
    wave_x = np.linspace(31, half - 2, WINDOW_SIZE)
    spectrum_x = np.linspace(half + 1, width - 1, WINDOW_SIZE // 2 + 1)
    pygame.display.init()
    pygame.font.init()
    try:
        screen = pygame.display.set_mode((width, height))
        pygame.display.set_caption(f'Oprain | {source_name} | {len(channels)} channels | {rate} S/s')
        font = pygame.font.Font(None, 21)
        clock = pygame.time.Clock()
        last_stamp = None
        last_update = time.monotonic()
        while True:
            if any(event.type == pygame.QUIT for event in pygame.event.get()):
                return 0
            block = board.get_current_board_data(WINDOW_SIZE)
            if block.shape[1] and block[timestamp_row, -1] != last_stamp:
                last_stamp = block[timestamp_row, -1]
                last_update = time.monotonic()
            screen.fill((0, 0, 0))
            if block.shape[1] < WINDOW_SIZE:
                text = f'{source_name} | Waiting for samples ({block.shape[1]}/{WINDOW_SIZE})'
                screen.blit(font.render(text, True, 'white'), (10, 5))
            else:
                eeg = np.ascontiguousarray(block[channels])
                for signal in eeg:
                    DataFilter.detrend(signal, DetrendOperations.LINEAR.value)
                    DataFilter.perform_bandpass(signal, rate, 1.0, 50.0, 4, FilterTypes.BUTTERWORTH.value, 0)
                spectrum = np.abs(np.fft.rfft(eeg, axis=1))
                peak = max(float(spectrum.max()) * 1.1, 1e-9)
                status = ' | waiting for new samples' if time.monotonic() - last_update > 1 else ''
                screen.blit(font.render(f'{source_name} | {len(channels)} channels | {rate} S/s{status}', True, 'white'), (8, 5))
                screen.blit(font.render(f'Spectrum  0–{rate / 2:g} Hz', True, 'white'), (half + 8, 5))
                for i, signal in enumerate(eeg):
                    color = CHANNEL_COLORS[i % len(CHANNEL_COLORS)]
                    top = title_height + i * track
                    wave_y = top + np.clip(0.5 + signal / 2000, 0, 0.999) * (track - 1)
                    spectrum_y = height - 1 - spectrum[i] / peak * (height - title_height - 1)
                    pygame.draw.line(screen, (50, 50, 50), (0, int(top)), (half, int(top)))
                    screen.blit(font.render(str(i + 1), True, color), (4, int(top + 2)))
                    pygame.draw.lines(screen, color, False, np.column_stack((wave_x, wave_y)).tolist())
                    pygame.draw.lines(screen, color, False, np.column_stack((spectrum_x, spectrum_y)).tolist())
                pygame.draw.line(screen, 'white', (half, 0), (half, height), 1)
            pygame.display.flip()
            clock.tick(30)
    finally:
        pygame.quit()


def main():
    args = parse_args()
    is_demo = args.board == 'demo32'
    profile = BOARDS['freeeeg32' if is_demo else args.board]
    try:
        with tempfile.TemporaryDirectory() as tmp:
            params = BrainFlowInputParams()
            board_id = profile
            source_name = args.board
            if is_demo or args.replay is not None:
                board_id = BoardIds.PLAYBACK_FILE_BOARD.value
                params.master_board = profile
                if is_demo:
                    demo_path = Path(tmp) / 'generated-tones.tsv'
                    make_demo(demo_path, profile)
                    params.file = str(demo_path)
                    source_name = 'demo32 (generated tones)'
                else:
                    with args.replay.open(encoding='utf-8') as recording:
                        columns = len(recording.readline().split())
                    if columns != BoardShim.get_num_rows(profile):
                        raise ValueError(f'{args.replay} has {columns} columns; {args.board} expects {BoardShim.get_num_rows(profile)}')
                    params.file = str(args.replay.resolve())
                    source_name = f'{args.board} (replay)'
            else:
                params.serial_port = args.port or '/dev/ttyACM0'
            board = BoardShim(board_id, params)
            with session(board, args.record, is_demo):
                if args.check is not None:
                    return check_stream(board, profile, args.check, source_name, args.min_sps)
                return display(board, profile, source_name)
    except (BrainFlowError, OSError, ValueError) as exc:
        print(f'Oprain capture failed: {exc}', file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == '__main__':
    sys.exit(main())
