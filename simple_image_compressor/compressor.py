import os, re, json, datetime, uuid, signal
from pathlib import Path
from PIL import Image

class Compressor(object):

    def __init__(self, path, config, job, logger) -> None:
        super().__init__()
        self.path = path
        self.conf = config
        self.job = job
        self.logger = logger
        signal.signal(signal.SIGTERM, self.cancel_run)
        signal.signal(signal.SIGINT, self.cancel_run)

    def run(self, lock):
        if self.conf.settings["verbosity"] < 3:
            with lock:
                self.logger.info(f"Dir {self.path} given to pid {os.getpid()}")
        files = self.scan_files([self.path])
        self.job.status["totalFiles"] += len(files)
        for image in files:
            if self.job.status["forcedStop"] is True:
                break
            result = self.compress(self.path, image)
            if result:
                self.job.result["files"].append(result)
                self.job.status["totalSize"] += result["size"]
                if result["status"] == "skipped":
                    self.job.status["skippedFiles"] += 1
                else:
                    self.job.status["totalSaved"] += result["process"]["partialSaving"]
                    self.job.status["processedFiles"] += 1 

                if self.conf.settings["verbosity"] in (0, 2):
                    with lock:
                        self.logger.info(self.print_result(result))
                elif self.conf.settings["verbosity"] == 3:
                    with lock:
                        self.logger.info(json.dumps(result, indent=2) + ", ")
        return repr(self.job)

    def cancel_run(self, signum, stackframe):
        self.job.status["forcedStop"] = True

    def scan_files(self, dirs):
        """Scans a list of directories paths and returns a dict of files apt to be processed"""
        file_list = []
        for dir in dirs:
            dir_path = Path(dir)
            if dir_path.is_dir and os.access(dir_path, os.W_OK):
                file_list = [file.name for file in dir_path.glob("*") if file.suffix in['.jpg', '.png', '.gif'] and "_t_" not in file.name]
        return file_list

    def print_result(self, result) -> str:
        processed_status = "OK" if result["status"] == "processed" else "--"
        if len(result['reason']) == 0:
            skipped = f"(-{str(result['process']['percentSaving'])}%)"
        else:
            skipped = f"({', '.join(result['reason'])})"
        print_r  = f"{processed_status} {result['path']}: "
        print_r += f"{'x'.join(str(v) for v in result['wh'])} {self.convert_unit(result['size'],2,'{0:0.{1}f}{2}B')} -> "
        print_r += f"{'x'.join(str(v) for v in result['new_wh'])} {self.convert_unit(result['new_size'],2,'{0:0.{1}f}{2}B')} "
        print_r += skipped
        return print_r
    
    def compress(self, path, image, quality=80):
        """Uses Pillow to compress the image to the quality specified"""
        img_info = {
            "path": "",
            "dir": path, 
            "base": image,
            "status": "",
            "reason": {},
            "process": {
                "targetSize": 1,
                "targetQuality": 100,
                "partialSaving": 0,
                "percentSaving": 0,
                "hex": 0
            },
            "wh": (),
            "size": 0,
            "modtime": 0,
            "new_wh": (),
            "new_size": 0,
        }
        img_path = Path(path + image)
        img_info["path"] = str(img_path)
        if not img_path.is_file():
            img_info["reason"]["NotAFile"] = f"Source image ({str(img_path)}) is not a file."
            return img_info
        if not os.access(img_path, os.W_OK):
            img_info["reason"]["NotWritable"] = f"Source image ({str(img_path)}) is not writable."
            return img_info
        img_stat = img_path.stat()        
        img_temp = path if self.conf.settings["temp"] is False else self.conf.settings["temp_dir"]
        target_quality = quality # default: 80
        target_size = 1.0 # 100%
        today = datetime.datetime.today()
        try:
            img = Image.open(img_path)
            img_info["wh"] = img.size
            img_info["size"] = os.path.getsize(img_path)
            img_info["modtime"] = int(img_stat.st_mtime)
        except Exception as e:
            img_info["reason"]["BadImagePath"] = f"Image cannot be read ({img_path.name})({e})"
            return img_info
        else:
            if img_info["size"] < int(self.conf.settings["params"]["min_source_size"]):
                img_info["reason"]["SourceSizeSmall"] = f"Source file is too small ({self.convert_unit(img_info['size'])})"
            elif ( int(today.timestamp()) - img_info["modtime"] ) < int(self.conf.settings["params"]["min_mod_time"]):
                img_info["reason"]["MinModTime"] = f"Source file modified {(int(today.timestamp()) - img_info['modtime'])} sooner than {self.conf.settings['params']['min_mod_time']} sec ago"
            else:
                if not self.conf.settings["soft"]:
                    if img_info["wh"] > (4000, 4000) or img_info["size"] > 5242880: # > 4000 px o > 5 MB
                        target_quality = 70
                        target_size = 0.6 # 60%
                    elif img_info["wh"] > (2560, 2560) or img_info["size"] > 2097152: # > 2560 px o 2 MB
                        target_quality = 75
                        target_size = 0.8 # 80%
                    elif img_info["wh"] > (1080, 1080) and (img_info["size"] > int(self.conf.settings["params"]["min_source_size"]) and img_info["size"] < 1048576): #  > 1080px y (> 150 KB y < a 1 MB)
                        target_quality = 75
                        target_size = 0.9 # 90%
                img_info["new_wh"] = tuple(int(wh*target_size) for wh in img_info['wh'])
                img_temp += f"_t_{uuid.uuid4()}_s{int(target_size*100)}_q{target_quality}{img_path.suffix}"
                if img_info['wh'] != img_info["new_wh"]:
                    img = img.resize(img_info["new_wh"])
                try:
                    img.save(img_temp, optimize=True, quality=target_quality, dpi=(72,72))
                except IOError as e:
                    img_info["reason"]["CantSaveCompressed"] = f"Error saving the compressed image: {e}."
                else:
                    img_info["new_size"] = os.path.getsize(img_temp)
            img.close()
            # checks the new image ############################################
            size_partial_saving = 0
            size_percent_saving = 0
            compression_hex = 0
            if len(img_info["reason"]) == 0 and "new_size" in img_info and img_info["new_size"] != 0:
                size_partial_saving = img_info["size"] - img_info["new_size"]
                size_percent_saving = round((size_partial_saving * 100) / img_info["size"])
                compression_hex = abs(round( ((30 if size_percent_saving<30 else size_percent_saving) * 255) / 100 ))
                if img_info["new_size"] <= int(self.conf.settings["params"]["min_target_size"]):
                    img_info["reason"]["TargetSizeSmall"] = f"Target file is too small ({self.convert_unit(img_info['new_size'])})"
                if size_partial_saving <= int(self.conf.settings["params"]["min_target_saving_size"]):
                    img_info["reason"]["TargetSizeBigger"] = f"Target file is bigger than source ({self.convert_unit(size_partial_saving)})"
                if size_percent_saving <= int(self.conf.settings["params"]["min_target_saving_percent"]):
                    img_info["reason"]["SavingPercentSmall"] = f"Target file doesnt save enough ({self.convert_unit(size_partial_saving)} = {round(size_percent_saving)}%)"
            # replace the original image ######################################            
            if len(img_info["reason"]) > 0:            
                img_info["status"] = "skipped"
                if self.conf.settings["temp"] is False and img_temp != "": #and Path(img_temp).is_file():
                    try:
                        os.remove(img_temp)
                    except Exception as e:
                        img_info["reason"]["CantRemoveTmp"] = f"Temp image cannot be removed ({e})"  
            else:
                img_info["status"] = "processed"          
                if self.conf.settings["temp"] is False:
                    try:
                        os.remove(img_path)
                        os.rename(img_temp, img_path)
                        os.utime(img_path, (img_stat.st_ctime, img_stat.st_mtime))
                    except Exception as e:
                        img_info["reason"]["CantReplace"] = f"Original image cannot be replaced ({e})"
            img_info["process"]["targetSize"] = target_size
            img_info["process"]["targetQuality"] = target_quality
            img_info["process"]["partialSaving"] = size_partial_saving
            img_info["process"]["percentSaving"] = size_percent_saving
            img_info["process"]["hex"] = compression_hex
        finally:
            return img_info
    
    @staticmethod
    def scan_dirs(dirs, exceptions):
        """Scans a list of directories paths and returns a dict of included/excluded paths"""
        reg = re.compile(fr"\b({exceptions})\b") if exceptions != "" else False
        dir_dict = {"included": [], "excluded": []}
        dir_list = []
        for dir in dirs:
            dir_path = Path(dir)
            if dir_path.is_dir:
                dir_list.append(dir_path)
                dir_list += [d for d in dir_path.rglob("*") if d.is_dir()]
        for dir_path in dir_list:
            if reg and reg.search(str(dir_path)) is not None:
                dir_dict["excluded"].append(str(dir_path))
                continue
            has_files = (sum(1 for f in dir_path.glob("*.*") if f.is_file())) > 0
            if not has_files:
                dir_dict["excluded"].append(str(dir_path))
                continue
            if os.access(dir_path, os.W_OK) and str(dir_path) not in dir_dict["included"]:
                dir_dict["included"].append(str(dir_path) + ("" if str(dir_path)[-1]==os.sep else os.sep))
        return dir_dict

    @staticmethod
    def convert_unit(num, precision=2, str_format="{0:0.{1}f} {2}B"):
        """Returns sizes in human readable format"""
        fmt = str_format
        prec = 0
        for unit in ['', 'K', 'M', 'G', 'T', 'P', 'E', 'Z']:
            if abs(round(num, precision)) < 1024:
                break
            num /= 1024.0
            prec = precision
        return fmt.format(num, prec, unit)