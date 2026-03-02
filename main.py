import threading
from src.streaming.lslbridge import start_lsl_stream, create_inlet, get_chunk_from_stream
from src.processing.test_dsp import apply_fft
from src.dashboard.test_plot import plot_fft
import numpy as np
import matplotlib.pyplot as plt

def build():
    thread = threading.Thread(target=start_lsl_stream, daemon=True)
    thread.start()


if __name__ == "__main__":
    build()
    inlet = create_inlet()
    WINDOW_SIZE = 512
    buffer_idx = 0
    signal_buffer = np.zeros(WINDOW_SIZE)
    plt.ion()
    while True:
        samples, ts = inlet.pull_chunk()
        print(ts)

        if len(samples) == 0:
            continue

        samples = np.array(samples)[:, 0]

        for value in samples:
            signal_buffer = np.roll(signal_buffer, -1)
            signal_buffer[-1] = value

        sp = np.fft.fft(signal_buffer)
        sp[0] = 0

        plt.clf()
        plt.plot(sp.real)
        plt.pause(0.001)