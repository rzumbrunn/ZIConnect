import os

from ziconnect import ZICustomConnection, ZISettingsHelper

SERIAL = "dev13087"

def main():

    # normalize all raw settings files in the config folder
    for file in os.listdir(os.path.join(ZISettingsHelper.CONFIG_BASE_PATH, "raw")):
        if file.endswith(".json"):
            ZISettingsHelper.normalize(f"raw/{file}", f"normalized/{file}")

    # Initialize standard session with pll
    session = ZICustomConnection.init_session()
    # failed= ZISettingsHelper.load_settings("normalized/config_phase_amp_pll.json", session, "dev3917")
    failed= ZISettingsHelper.load_settings("normalized/phase_lock_doublepass_102126.json", session, "dev3917")

    # if failed:
    #     print(f"Failed to apply the following settings: {failed}")

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

    study = optuna.create_study(direction="minimize", storage="sqlite:///optuna_study.db", study_name="pll_optimization_doublepass_G_opt_new_errfunc_500Hz", load_if_exists=True)
    optuna_objective_lambda = lambda trial: ZIOptimize.optuna_objective(trial, 'mfli-torus.ethz.ch', 8004, "dev3917", span=10000)
    study.optimize(
        optuna_objective_lambda,
        n_trials=100,
    )


if __name__ == "__main__":
    main()