import os

import optuna

from ziconnect import ZICustomConnection, ZIOptimize, ZISettingsHelper

SERIAL = "dev13087"

def main():

    # normalize all raw settings files in the config folder
    for file in os.listdir(os.path.join(ZISettingsHelper.CONFIG_BASE_PATH, "raw")):
        if file.endswith(".json"):
            ZISettingsHelper.normalize(f"raw/{file}", f"normalized/{file}")

    # Initialize standard session with pll
    session = ZICustomConnection.init_session("exp-pc-torus.ethz.ch", 8004)
    # failed= ZISettingsHelper.load_settings("normalized/config_phase_amp_pll.json", session, "dev3917")
    # failed= ZISettingsHelper.load_settings("normalized/vhfli_first_decent_lock_102626.json", session, SERIAL)

    # if failed:
    #     print(f"Failed to apply the following settings: {failed}")



    # ref_data = np.loadtxt("data/tmp/dev13087_demods_2_sample_theta_fft_abs_pwr_avg_00000.csv", delimiter=";", skiprows=1)
    # ref_freqs = ref_data[:, 1]
    # ref_values = ref_data[:, 2]

    # plt.loglog(ref_freqs, ref_values, label="Reference Phase Noise", color="blue", linestyle="--")
    # plt.plot(ref_freqs)



    roi_frequency_span = 10000
    # ZICustomConnection.get_phase_noise_direct('exp-pc-torus.ethz.ch', 8004, "dev13087", 2, frequency_span=roi_frequency_span*2, frequency_res=6)
    # ZICustomConnection.get_phase_noise(session, "dev3917", 1, frequency_span=10000, frequency_res=10)
    # ZICustomConnection.get_phase_noise_direct('mfli-torus.ethz.ch', 8004, "dev3917", 2, frequency_span=10000, frequency_res=20)
    # for G in np.linspace(0.1,10,10):
    #     ZIOptimize.test_pll_params('mfli-torus.ethz.ch', 8004, "dev3917", P=150 * G, I=3.25e6* G, D=1.5e-3*G, F=0, BW=1000, span=10000)

    # for G in np.logspace(-1,2,10) :
    #     ZIOptimize.test_pll_params('mfli-torus.ethz.ch', 8004, "dev3917", P=1.5 * G, I= 5.0e3* G, D=1.5 /(10.0e3)*G, F=0, BW=1000, span=10000)

    
    # optimize using sp optimize

    # test_pll_params_lambda = lambda x: ZIOptimize.test_pll_params('mfli-torus.ethz.ch', 8004, "dev3917", P=x[0], I=x[1], D=x[2], F=x[3], BW=x[4], span=10000)

    # sp.optimize.minimize(test_pll_params_lambda, x0=[1.5, 5.0e3, 1.5/(10.0e3), 0, 1000], method='Nelder-Mead', options={'disp': True})

    # optimize using optuna

    study = optuna.create_study(direction="minimize", storage="sqlite:///optuna_study.db", study_name="vhfli_pll_optimization_doublepass_largebw_cut", load_if_exists=True)
    optuna_objective_lambda = lambda trial: ZIOptimize.optuna_objective(trial, session, SERIAL, roi_frequency_span*50)
    study.optimize(
        optuna_objective_lambda,
        n_trials=100,
    )


if __name__ == "__main__":
    main()