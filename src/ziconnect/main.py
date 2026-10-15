import os

from ziconnect import ZICustomConnection, ZISettingsHelper


def main():

    # normalize all raw settings files in the config folder
    for file in os.listdir(os.path.join(ZISettingsHelper.CONFIG_BASE_PATH, "raw")):
        if file.endswith(".json"):
            ZISettingsHelper.normalize(f"raw/{file}", f"normalized/{file}")

    # Initialize standard session with pll
    session = ZICustomConnection.init_session()
    # failed= ZISettingsHelper.load_settings("normalized/config_phase_amp_pll.json", session, "dev3917")

    # if failed:
    #     print(f"Failed to apply the following settings: {failed}")

    ZICustomConnection.get_phase_noise(session, "dev3917", 1)

if __name__ == "__main__":
    main()