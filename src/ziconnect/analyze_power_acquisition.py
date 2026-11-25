import time

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from pynufft import NUFFT
import allantools as at


def main():
    runs = [
        {
            "run_dir": "data/power_remote/dev3917_20261123_111737",
            "title": "Noise baseline",
            "downsample_factor": 100,
        },
        {
            "run_dir": "data/power_remote/dev3917_20261123_174831",
            "title": "Polarisation noise",
            "downsample_factor": 100,
        }
    ]

    fig = make_subplots(rows=1, cols=3, subplot_titles=("Power Acquisition", "FFT of Power Acquisition", "Allan Variance"))
    for i, run in enumerate(runs):
        run_dir = run["run_dir"]
        title = run["title"]
        downsample_factor = run["downsample_factor"]


        data = np.load(f"{run_dir}/downsampled_100.npz")

        wave, times = data["wave"], data["times"]

        # host_timestamps = data["host_timestamps"]
        times_sort = np.argsort(times)
        wave = wave[times_sort]
        times = times[times_sort]

        start_time = int(data["timestamp_host"])


        tend = 10000  # seconds
        wave = wave[times < tend]
        times = times[times < tend]


        print(f"Loaded waveform data from {run_dir}/downsampled_100.npz", f"Waveform length: {len(wave)}")

        ds_factor = 10
        plot_ds_factor = 10

        wave_ds = wave[::ds_factor] / np.average(wave[::ds_factor])  # Downsampled waveform, normalized
        t_ds = times[::ds_factor] - times[0]  # Downsampled time array, starting from 0

        currcol = 1

        fig.add_trace(go.Scatter(x=t_ds[::plot_ds_factor], y=wave_ds[::plot_ds_factor], opacity=0.7, mode="lines", name=f"Waveform {title}"), row=1, col=currcol); currcol += 1
        # add start and end host time in datetime format (rotated 90 degrees) as annotation
        fig.add_annotation(x=t_ds[0] + (t_ds[-1] - t_ds[0]) * 0.1* i, y=1.1, xref="x", yref="y", text=fr"Start run {title}: {time.ctime(start_time)}", showarrow=True, arrowhead=1, ax=0, ay=-40, row=1, col=currcol-1, textangle=-90)
        fig.add_annotation(x=t_ds[-1] + (t_ds[-1] - t_ds[0]) * 0.1* i, y=1.1, xref="x", yref="y", text=fr"End run {title}: {time.ctime(start_time+ t_ds[-1])}", showarrow=True, arrowhead=1, ax=0, ay=-40, row=1, col=currcol-1, textangle=-90)

        # #standard fft
        resampled_wave = np.interp(np.linspace(t_ds[0], t_ds[-1], len(t_ds)), t_ds, wave_ds)
        resampled_t = np.linspace(t_ds[0], t_ds[-1], len(t_ds))

        # freqs = np.fft.fftshift(np.fft.fftfreq(len(wave_ds), d=(t_ds[1] - t_ds[0])))
        # fft_data = np.fft.fftshift(np.fft.fft(wave_ds))
        freqs = np.fft.fftshift(np.fft.fftfreq(len(resampled_wave), d=(resampled_t[1] - resampled_t[0])))
        fft_data = 1/len(resampled_wave) *   np.fft.fftshift(np.fft.fft(resampled_wave))

        # downsampled for plotting
        ds_factor_fft = 10
        
      
        fig.add_trace(go.Scatter(x=freqs[::ds_factor_fft], y=np.abs(fft_data[::ds_factor_fft]), opacity=0.7, mode="lines", name=f"FFT Magnitude {title}"), row=1, col=currcol); currcol += 1

        # alan variance
        # taus = np.logspace(-2, 6, num=20)  # Tau values from 1 ms to 1000 s
        adev = at.oadev(wave_ds, rate=1/(t_ds[1]-t_ds[0]), data_type='freq', taus='octave')  # Calculate Allan deviation
        fig.add_trace(go.Scatter(x=adev[0], y=adev[1], opacity=0.7, mode="lines", name=f" Allan Variance {title}"), row=1, col=currcol); currcol += 1





    fig.update_layout(title_text="Power Acquisition Analysis")
    fig.update_xaxes(title_text="Time (s)", row=1, col=1)
    fig.update_yaxes(title_text="Normalized amplitude", row=1, col=1)
    fig.update_xaxes(title_text="Frequency (Hz)", type="log", row=1, col=2)
    fig.update_yaxes(title_text="FFT magnitude", type="log", row=1, col=2)
    fig.update_xaxes(title_text="Tau (s)", type="log", row=1, col=3)
    fig.update_yaxes(title_text="Allan Deviation", type="log", row=1, col=3)
    fig.show()

        
        # nufft
        # A = NUFFT()
        # om = np.random.randn(2 * len(wave_ds), 2) * np.pi  # Random frequency locations for NUFFT
        # Nd = (len(wave_ds),)
        # Kd = (2 * len(wave_ds),)
        # Jd = (6,)
        # A.plan(om, Nd, Kd, Jd)
        # y = A.forward(wave_ds)
        # freqs = np.fft.fftshift(np.fft.fftfreq(len(wave_ds), d=(t_ds[1] - t_ds[0])))

        # fig2 = go.Figure()
        # fig2.add_trace(go.Scatter(x=freqs, y=np.abs(np.fft.fftshift(y)), mode="lines", name="NUFFT Magnitude"))
        # fig2.update_layout(title="NUFFT of Power Acquisition", xaxis_title="Frequency (Hz)", yaxis_title="Magnitude")
        # fig2.update_xaxes(type="log")
        # fig2.update_yaxes(type="log")
        # fig2.show()





if __name__ == "__main__":
    main()