import time

import matplotlib.pyplot as plt
import numpy as np
import zhinst.core as zi

from ziconnect import ZICustomConnection


def optuna_objective(trial, host, port, serial, span):

    # P0 = 1.5
    # I0 = 5.0e3
    # D0 = 1.5 / (10.0e3)
    # F0 = 0
    # BW0 = 1000

    # Trial 2
    P0 = 14.188084934437933
    I0 = 42669.089183065145
    D0 = 0.0014779803568506133
    F0 = 0
    BW0 = 1000

    P = trial.suggest_float("P", 0.1 * P0, 10 * P0)
    I = trial.suggest_float("I", 0.1 * I0, 10 * I0)
    D = trial.suggest_float("D", 0.1 * D0, 10 * D0)
    # F = trial.suggest_float("F", 0.1 * F0, 10 * F0)
    # BW = trial.suggest_float("BW", 0.1 * BW0, 10 * BW0)
    F = 1 * F0  # Keep F fixed for now
    BW = 1 * BW0  # Keep BW fixed for now

    score = test_pll_params(host, port, serial, P, I, D, F, BW, span)

    return score


def test_pll_params(host, port, serial, P, I, D, F, BW, span):

    daq = zi.ziDAQServer(host, port, 0)
    daq_module = daq.dataAcquisitionModule()

    # turn off PLL
    daq.set(f"/{serial}/pids/0/enable", 0)

    
    pn_no_pll, freqs = ZICustomConnection.get_phase_noise_direct_retry(
        host=host,
        port=port,
        serial=serial,
        channel=2,
        frequency_span=span,
        frequency_res=10,
        plot=False
    )
    pn_no_pll = np.sum(np.array(pn_no_pll), axis=1)  # Sum the two arrays element-wise

    daq.set(f"/{serial}/pids/0/p", P)
    daq.set(f"/{serial}/pids/0/i", I)
    daq.set(f"/{serial}/pids/0/d", D)
    daq.set(f"/{serial}/pids/0/dlimittimeconstant", F)
    daq.set(f"/{serial}/pids/0/limitupper", BW/2)
    daq.set(f"/{serial}/pids/0/limitlower", -BW/2)

    # turn on PLL
    daq.set(f"/{serial}/pids/0/enable", 1)

    # wait for the PLL to stabilize
    print("Waiting for PLL to stabilize...")
    time.sleep(2)  

    pn_with_pll, freqs = ZICustomConnection.get_phase_noise_direct_retry(
        host=host,
        port=port,
        serial=serial,
        channel=2,
        frequency_span=span,
        frequency_res=10,
        plot=False
    )
    pn_with_pll = np.sum(np.array(pn_with_pll), axis=1)  # Sum the two arrays element-wise


    plt.figure(figsize=(10, 6))
    plt.loglog(freqs, pn_no_pll, label="Without PLL", color="blue")
    plt.loglog(freqs, pn_with_pll, label="With PLL", color="orange")
    plt.title(f"Phase Noise Comparison for {serial} with PLL Parameters: P={P}, I={I}, D={D}, F={F}, BW={BW}")
    plt.xlabel("Frequency Offset (Hz)")
    plt.ylabel("Phase Noise (dBc/Hz)")
    plt.grid(which="both", linestyle="--", linewidth=0.5)
    plt.legend()
    plt.tight_layout()
    # plt.show()
    plt.savefig(f"data/phase_noise_comparison_{serial}_P{P}_I{I}_D{D}_F{F}_BW{BW}.png")

    np.savez(f"data/phase_noise_data_{serial}_P{P}_I{I}_D{D}_F{F}_BW{BW}.npz", freqs=freqs, pn_no_pll=pn_no_pll, pn_with_pll=pn_with_pll)

    def scoring_function(freqs, pn_no_pll, pn_with_pll):
        # Define a frequency range of interest (e.g., 10 Hz to 10 kHz)
        freq_min = 10
        freq_max = 10000

        # Create a mask for the frequency range
        mask = (freqs >= freq_min) & (freqs <= freq_max)

        with_pll_integral = np.trapezoid(pn_with_pll[mask], freqs[mask])
        without_pll_integral = np.trapezoid(pn_no_pll[mask], freqs[mask])

        return with_pll_integral /   without_pll_integral  # The smaller the ratio, the better the PLL performance

    return scoring_function(freqs, pn_no_pll, pn_with_pll)
