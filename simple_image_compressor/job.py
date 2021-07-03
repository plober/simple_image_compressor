import json

class Job:

    status = {
        "forcedStop": False,
        "totalSize": 0,
        "totalSaved": 0,
        "totalFiles": 0,
        "skippedFiles": 0,
        "processedFiles": 0,
        "timeStart": 0,
        "timeEnd": 0,
    }
    result = {
        "dirs": {},
        "files": []
    }

    def __str__(self) -> str:
        return json.dumps([Job.status, Job.result], indent=2)

    def __repr__(self) -> str:
        return json.dumps({"status": Job.status, "result": Job.result})
    
    def load_settings(self, json_status:str, json_result:str="") -> None:
        if json_status != "":
            Job.status = json.loads(json_status)[0]
        if json_result != "":
            Job.result = json.loads(json_result)[1]
