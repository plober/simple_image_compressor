import re, datetime, json, tempfile
from pathlib import Path

class Settings:

    filename = None
    settings = {}

    def __init__(self, json_file:str=None) -> None:
        if json_file is not None:
            Settings.filename = json_file
            self.load(json_file)

    def __str__(self) -> str:
        return json.dumps([Settings.filename, Settings.settings], indent=2)

    def __repr__(self) -> str:
        return json.dumps(Settings.settings)

    def load_settings(self, json_string:str) -> None:
        if json_string != "":
            Settings.settings = json.loads(json_string)

    def load(self, json_file:str=None) -> None:
        """Reads settings.json and returns a dictionary"""
        if json_file is None and Settings.filename == "":
            raise Exception("Settings load: No settings file")
        Settings.filename = json_file
        reg = re.compile(r" //.*$")
        try:
            with open(self.filename, "rt", encoding="utf8") as f:
                settings_lines = f.readlines()
                settings_str = "".join([ re.sub(reg, "", l) for l in settings_lines])
                self.load_settings(settings_str)
                Settings.settings["temp_dir"] = f"{str(Path(tempfile.gettempdir()).as_posix())}/sic_{str(int(datetime.datetime.today().timestamp()))}/"
        except Exception as e:
            print(e)

    def edit(self, setting:str, value) -> None:
        if setting in Settings.settings and value is not None:
            Settings.settings[setting] = value

