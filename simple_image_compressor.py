import sys, os, atexit, datetime, argparse, json, logging, shutil
from multiprocessing import Process, Queue, Lock
from simple_image_compressor import settings, job, compressor

def arg_parser() -> argparse:
    global conf
    parser = argparse.ArgumentParser("Simple Image Compressor")
    parser.add_argument("path", nargs="+", help="path to the directory to compress")
    parser.add_argument("-v", type=int, choices=[0,1,2,3], default=1, help="verbosity level: 0=log file, 1=print dirs, 2=print files, 3=print json")
    parser.add_argument("-s", action="store_true", help="soft compression: doesn't resize, just compresses up to 80%% quality")
    parser.add_argument("-t", action="store_true", help=f"temp output: doesn't replace source images, instead saves compressed images to {conf.settings['temp_dir']}")
    parser.add_argument("-n", action="store_false", help="no exceptions: process files even if they're in the exceptions list")
    return parser

def main():
    parser = arg_parser()
    try:
        parsed_args = parser.parse_args()
        if parsed_args.v == 0:
            file_handler = logging.FileHandler(os.getcwd() + conf.settings["log"])
            file_handler.setFormatter(logging.Formatter("%(asctime)s %(message)s", "%Y-%m-%d %H:%M:%S"))
            logger.addHandler(file_handler)
        else:
            logger.addHandler(logging.StreamHandler(sys.stdout))
        conf.edit("source_dir", parsed_args.path)
        conf.edit("verbosity", parsed_args.v)
        conf.edit("soft", parsed_args.s)
        conf.edit("temp", parsed_args.t)
        conf.edit("exceptions", parsed_args.n)
    except SystemExit as se:
        logger.critical(f"Couldn't process the arguments: {se}")
        exit()
    except Exception as e:
        logger.critical(f"Couldn't process the arguments: {e}")
        exit()

    if conf.settings["verbosity"] < 3:
        logger.info(f"\r\nStarted processing image files in {', '.join(conf.settings['source_dir'])}")
        logger.info(f"Job config exceptions: {conf.settings['exceptions']}")
        logger.info(f"Job config soft: {conf.settings['soft']}")
        logger.info(f"Job config temp: {conf.settings['temp']} " + (f"({conf.settings['temp_dir']})" if conf.settings['temp'] is True else ""))
    else:
        logger.info("{[")
    
    try:
        job.result["dirs"] = compressor.Compressor.scan_dirs(
            parsed_args.path,
            (conf.settings["params"]["exceptions"] if conf.settings['exceptions'] is True else "")
        )
        if len(job.result["dirs"]["included"]) == 0:
            raise Exception("directories can't be scanned or were excluded by exception list")
    except Exception as e:
        logger.error(f"Error scanning sources: {e}")
        job.result["dirs"] = {"included": [], "excluded": []}
    else:
        if conf.settings["temp"] is True:
            try:
                os.makedirs(conf.settings["temp_dir"], exist_ok=True)
            except Exception as e:
                logger.critical(e)

def terminate():
    global processes, q
    for process in processes:
        if process.is_alive():
            process.terminate()

def process(queue, results, lock):
    """Process items from the queue to process"""
    try:
        while not queue.empty():
            queue_compressor = queue.get()
            queue_result = queue_compressor.run(lock)
            results["q"].put(queue_result) # using a list as mapping type: https://realpython.com/python-pass-by-reference/
    except KeyboardInterrupt:
        job.status["forcedStop"] = True
    except Exception as e:
        template = "An exception of type {0} occurred. Arguments:\n{1!r}"
        print(template.format(type(e).__name__, e.args))
    return

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    logger = logging.getLogger(__name__)
    logger.propagate = False
    conf = settings.Settings("settings.json")
    job = job.Job()
    job.status['timeStart'] = str(datetime.datetime.now().replace(microsecond=0))

    main()
    count_dir = len(job.result["dirs"]["included"])
    if count_dir > 0:
        count_cpu = os.cpu_count()
        count_processes = count_cpu if count_cpu < count_dir else count_dir
        processes = []
        
        atexit.register(terminate)

        q_tasks = Queue()
        q_results = Queue()
        l = Lock()

        for i in range(count_processes):
            processes.append( Process(None, process, args=( q_tasks, {"q":q_results}, l ), daemon=True) )

        for dir_path in job.result["dirs"]["included"]:
            q_tasks.put(compressor.Compressor(dir_path, conf, job, logger))
        
        for process in processes:
            process.start()

        try:
            for process in processes:
                process.join()
        except KeyboardInterrupt:
            logger.info("Process interrupted by the user.")
            terminate()
        except Exception as e:
            logger.critical(f"Main exception: {e}")

        job.status['timeEnd'] = str(datetime.datetime.now().replace(microsecond=0))
        job_time = datetime.datetime.strptime(job.status['timeEnd'], "%Y-%m-%d %H:%M:%S") - datetime.datetime.strptime(job.status['timeStart'], "%Y-%m-%d %H:%M:%S")

        while not q_results.empty():
            r = json.loads(q_results.get())
            job.status['totalFiles'] += r["status"]['totalFiles']
            job.status['processedFiles'] += r["status"]['processedFiles']
            job.status['skippedFiles'] += r["status"]['skippedFiles']
            job.status['totalSize'] += r["status"]['totalSize']
            job.status['totalSaved'] += r["status"]['totalSaved']
        
        if conf.settings["verbosity"] < 3:
            logger.info(f"Files: {job.status['totalFiles']} ({job.status['processedFiles']} processed, {job.status['skippedFiles']} skipped)")
            logger.info(f"Source size: {compressor.Compressor.convert_unit(job.status['totalSize'])}")
            job_new_size = job.status['totalSize'] - job.status['totalSaved']
            logger.info(f"Compressed size: {compressor.Compressor.convert_unit(job_new_size)} ({compressor.Compressor.convert_unit(job.status['totalSaved'])} saved)")        
            logger.info(f"Time: {int(job_time.total_seconds())}s")

        shutil.rmtree(conf.settings["temp_dir"], ignore_errors=True) if conf.settings["temp"] is True and os.path.exists(conf.settings["temp_dir"]) else pass
            

    logger.info("Process finished.\r\n") if conf.settings["verbosity"] < 3 else logger.info("]}")
