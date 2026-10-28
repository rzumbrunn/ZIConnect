import time

import matplotlib.pyplot as plt
import numpy as np
import optuna

from ziconnect import ZICustomConnection

artifact_store = optuna.artifacts.FileSystemArtifactStore("data/artifacts")

def optuna_objective(trial, session, serial, span):

    # P0 = 1.5
    # I0 = 5.0e3
    # D0 = 1.5 / (10.0e3)
    # F0 = 0
    # BW0 = 1000

    # Trial 2
    # P0 = 14.188084934437933
    # I0 = 42669.089183065145
    # D0 = 0.0014779803568506133
    # F0 = 0
    # BW0 = 1000

    # Double pass Trial
    # P0 = 1.5
    # I0 = 10.0e3
    # D0 = 1.5 / (20.0e3)
    # F0 = 0
    # BW0 = 1000

    # Double pass optimal filter trial (500Hz )
    # P0 = 7.6e6 / (22**2)
    # I0 = 2.5e10/(22**3)
    # D0 = 760 /(22)
    # F0 = 0
    # BW0 = 1000

    # Double pass trial 2
    # G = trial.suggest_float("G", 0.1, 100)
    # P = P0 * G
    # I = I0 * G
    # D = D0 * G
    # BW = BW0 * G

    # Double pass trial 3

    # New calculation (second order filter)
    # P0 = 250
    # I0 = 20e6
    # D0 = 1.2e-3
    # BW0 = 5e3
    P0 = 500
    I0 = 200e6
    D0 = 2e-3
    BW0 = 10e3


    factors = 10   

    P = trial.suggest_float("P", P0/factors,  P0 * factors, log=True)
    I = trial.suggest_float("I", I0/factors, I0 * factors, log=True)
    D = trial.suggest_float("D",  D0/factors, D0 * factors, log=True)
    BW = trial.suggest_float("BW", BW0/factors, BW0*factors,    log=True)

    # Verification 
    # P =19.723557208489048

    # I = 173.27026528510467

    # D = 0.0020636402971697517

    # BW = 33196.67312100776


    # Alt trial 2
    # P = trial.suggest_float("P", 0.5 * P0, 2 * P0)
    # I = trial.suggest_float("I", 0.5 * I0, 2 * I0)
    # D = trial.suggest_float("D", 0.5 * D0, 2 * D0)


    # P = trial.suggest_float("P", 1 * P0, 100 * P0)
    # I = trial.suggest_float("I", 0.1 * I0, 100 * I0)
    # D = trial.suggest_float("D", 0.1 * D0, 10 * D0)
    # F = trial.suggest_float("F", 0.1 * F0, 10 * F0)
    # BW = trial.suggest_float("BW", 0.1 * BW0, 10 * BW0)
    F = 1 * 0  # Keep F fixed for now
    # BW = 1 * BW0  # Keep BW fixed for now

    demod_BW_0 = span/ 10
    demod_BW = trial.suggest_float("demod_BW", demod_BW_0/10, demod_BW_0*10, log=True)

    settle_time_0  = 0.5  # seconds
    settle_time = trial.suggest_float("settle_time", 0.01, 2.0)  # seconds

    score = test_pll_params(session, serial, P, I, D, F, BW, demod_BW, span, settle_time=settle_time)
    optuna.artifacts.upload_artifact(
        artifact_store=artifact_store,
        study_or_trial=trial,
        file_path=f"data/phase_noise_comparison_{serial}_P{P}_I{I}_D{D}_F{F}_BW{BW}_demod_BW{demod_BW}_settle_time{settle_time}.png",
    )

    score = score + 0.001 * settle_time  # Penalize longer settling times


    return score


def test_pll_params(session, serial, P, I, D, F, actuation_BW, demod_BW, span, settle_time=0.5):

    FREQUENCY_RES = 10  # Hz
    NO_SAMPLES = 10  # Number of samples to average

    # daq = zi.ziDAQServer(session.host, session.port, api_level=API_LEVEL)
    daq_module = session.modules.daq

    # turn off PLL
    # daq.set(f"/{serial}/pids/0/enable", 0)
    session.devices[serial].pids[0].enable(0)

    # TODO
    #session.devices[serial].demods[channel].timeconstant(1.0 / (2*np.pi *2*adjusted_frequency_span*filter_margin_factor)) # adjust filter time constant to match the aquisition bandwidth f_3db = (1/(2*pi * tau))
    # session.devices[serial].demods[PID_DEMOD].timeconstant(1.0 / (2 * np.pi * demod_BW*2))  # adjust filter time constant to match the aquisition bandwidth f_3db = (1/(2*pi * tau))


    
    pn_no_pll, freqs = ZICustomConnection.get_phase_noise_direct_retry(
        session=session,
        serial=serial,
        channel=2,
        frequency_span=span,
        frequency_res=FREQUENCY_RES,
        plot=False,
    )
    session.devices[serial].pids[0].p(P)
    session.devices[serial].pids[0].i(I)
    session.devices[serial].pids[0].d(D)
    session.devices[serial].pids[0].dlimittimeconstant(F)
    session.devices[serial].pids[0].limitupper(actuation_BW / 2)
    session.devices[serial].pids[0].limitlower(-actuation_BW / 2)
    session.devices[serial].pids[0].demod.timeconstant(1.0 / (2 * np.pi * demod_BW * 2))  # adjust filter time constant to match the aquisition bandwidth f_3db = (1/(2*pi * tau))


    # turn on PLL
    session.devices[serial].pids[0].enable(1)

    # wait for the PLL to stabilize
    print("Waiting for PLL to stabilize...")
    time.sleep(settle_time)  

    pn_with_pll, freqs = ZICustomConnection.get_phase_noise_direct_retry(
        session=session,
        serial=serial,
        channel=2,
        frequency_span=span,
        frequency_res=FREQUENCY_RES,
        no_samples=NO_SAMPLES,
        plot=False
    )
    plt.figure(figsize=(10, 6))
    plt.loglog(freqs, pn_no_pll, label="Without PLL", color="blue")
    plt.loglog(freqs, pn_with_pll, label="With PLL", color="orange")
    plt.title(f"Phase Noise Comparison for {serial} with PLL Parameters: P={P}, I={I}, D={D}, F={F}, BW={actuation_BW}")
    plt.xlabel("Frequency Offset (Hz)")
    plt.ylabel("Phase Noise (dBc/Hz)")
    plt.grid(which="both", linestyle="--", linewidth=0.5)
    plt.legend()
    plt.tight_layout()
    # plt.show()
    plt.savefig(f"data/phase_noise_comparison_{serial}_P{P}_I{I}_D{D}_F{F}_BW{actuation_BW}_demod_BW{demod_BW}_settle_time{settle_time}.png")
    plt.close()

    np.savez(f"data/phase_noise_data_{serial}_P{P}_I{I}_D{D}_F{F}_BW{actuation_BW}.npz", freqs=freqs, pn_no_pll=pn_no_pll, pn_with_pll=pn_with_pll)

    def scoring_function(freqs, pn_no_pll, pn_with_pll):
        # Define a frequency range of interest (e.g., 10 Hz to 10 kHz)
        freq_min = 1000
        freq_max = 40000

        # Create a mask for the frequency range
        mask = (freqs >= freq_min) & (freqs <= freq_max)

        with_pll_integral = np.trapezoid(pn_with_pll[mask], freqs[mask])
        without_pll_integral = np.trapezoid(pn_no_pll[mask], freqs[mask])

        # return with_pll_integral /   without_pll_integral  # The smaller the ratio, the better the PLL performance
        return with_pll_integral  # The smaller the integral, the better the PLL performance

    return scoring_function(freqs, pn_no_pll, pn_with_pll)
