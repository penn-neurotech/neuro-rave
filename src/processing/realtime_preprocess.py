import numpy as np
import matplotlib
%matplotlib inline
import matplotlib.pyplot as plt
from scipy.signal import butter, lfilter
import argparse
import time
from IPython.display import clear_output
try:
    from pylsl import StreamInlet, resolve_stream
except:
    pass

# PARAMETERS

SAMPLE_RATE = 512
WINDOW_SEC = 1.0
OVERLAP = 0.5

THETA = (4,8)
ALPHA = (8,13)
BETA  = (13,30)
GAMMA = (30,100)

# FILTER UTILITIES

def bandpass(data, low, high, fs):
    b,a = butter(4,[low/(fs/2), high/(fs/2)],btype='band')
    return lfilter(b,a,data,axis=1)

def notch(data, freq, fs, Q=30):
    from scipy.signal import iirnotch
    b,a = iirnotch(freq/(fs/2),Q)
    return lfilter(b,a,data,axis=1)

# BANDPOWER

def bandpower(data):
    return np.mean(data**2)

# REALTIME PROCESSOR

class EEGProcessor:

    def __init__(self, sfreq):

        self.sfreq = sfreq
        self.window_samples = int(WINDOW_SEC*sfreq)
        self.step_samples = int(self.window_samples*(1-OVERLAP))

        self.buffer = []

        self.theta_hist = []
        self.alpha_hist = []
        self.beta_hist = []
        self.gamma_hist = []
        self.times = []

        self.start_time = time.time()

    def process(self, sample):

        self.buffer.append(sample)

        if len(self.buffer) < self.window_samples:
            return

        data = np.array(self.buffer).T
        self.buffer = self.buffer[self.step_samples:]

        # PREPROCESSING

        data = notch(data,60,self.sfreq)
        data = bandpass(data,1,100,self.sfreq)

        # BAND FILTERS

        theta = bandpass(data,*THETA,self.sfreq)
        alpha = bandpass(data,*ALPHA,self.sfreq)
        beta  = bandpass(data,*BETA,self.sfreq)
        gamma = bandpass(data,*GAMMA,self.sfreq)

        theta_power = bandpower(theta)
        alpha_power = bandpower(alpha)
        beta_power  = bandpower(beta)
        gamma_power = bandpower(gamma)
       
        # FEATURES

        theta_beta = theta_power / beta_power if beta_power>0 else 0

        # STORE HISTORY

        self.theta_hist.append(theta_power)
        self.alpha_hist.append(alpha_power)
        self.beta_hist.append(beta_power)
        self.gamma_hist.append(gamma_power)

        self.times.append(time.time()-self.start_time)

        # ALPHA SUPPRESSION

        if len(self.alpha_hist)>5:
            baseline = np.mean(self.alpha_hist[:5])
            alpha_sup = (baseline-alpha_power)/baseline*100
        else:
            alpha_sup = 0

        print(
            f"Theta/Beta: {theta_beta:.2f} | "
            f"Alpha Suppression: {alpha_sup:.1f}%"
        )

        # PLOT

        self.plot()

    def plot(self):
   
        clear_output(wait=True)
        plt.clf()
        plt.figure(1, figsize=(8,6))

        plt.subplot(2,1,1)
        plt.plot(self.times,self.theta_hist,label="Theta")
        plt.plot(self.times,self.alpha_hist,label="Alpha")
        plt.plot(self.times,self.beta_hist,label="Beta")
        plt.plot(self.times,self.gamma_hist,label="Gamma")
        plt.legend()
        plt.title("Bandpower")
   
        plt.subplot(2,1,2)
   
        if len(self.beta_hist)>0:
            ratio = np.array(self.theta_hist)/np.array(self.beta_hist)
            plt.plot(self.times,ratio)
   
        plt.title("Theta/Beta Ratio")
   
        plt.show()
   
# SIMULATION

def simulate():

    print("Running simulated EEG")

    processor = EEGProcessor(SAMPLE_RATE)

    while True:

        t = time.time()
        sample = np.sin(2*np.pi*10*t) + 0.5*np.random.randn(32)
        sample = np.repeat(sample,32)

        processor.process(sample)

        time.sleep(1/SAMPLE_RATE)

# LSL STREAM

def run_lsl():

    print("Searching for LSL EEG stream...")

    streams = resolve_stream('type','EEG')
    inlet = StreamInlet(streams[0])

    sfreq = inlet.info().nominal_srate()
    n_channels = inlet.info().channel_count()

    print("Connected")
    print("Sample rate:",sfreq)
    print("Channels:",n_channels)

    processor = EEGProcessor(sfreq)


    while True:

        sample,_ = inlet.pull_sample()

        processor.process(sample)

# MAIN

if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument("--simulate",action="store_true")

    args = parser.parse_args()

    if args.simulate:
        simulate()
    else:
        run_lsl()