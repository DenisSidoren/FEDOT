import json
import logging
import os
import sys
from logging.config import dictConfig
from logging.handlers import QueueHandler, QueueListener, RotatingFileHandler
from multiprocessing import RLock
import multiprocessing

from fedot.core.utils import default_fedot_data_dir


class SingletonMeta(type):
    """
    This meta class can provide other classes with the Singleton pattern.
    It guarantees to create one and only class instance.
    Pass it to the metaclass parameter when defining your class as follows:
    class YourClassName(metaclass=SingletonMeta)
    """
    _instances = {}

    _lock: RLock = RLock()

    def __call__(cls, *args, **kwargs):
        with cls._lock:
            if cls not in cls._instances:
                instance = super().__call__(*args, **kwargs)
                cls._instances[cls] = instance
        return cls._instances[cls]


class Log(metaclass=SingletonMeta):
    __log_adapters = {}

    def __init__(self, logger_name: str,
                 config_json_file: str = 'default',
                 output_verbosity_level: int = 1,
                 log_file: str = None):
        if not log_file:
            self.log_file = os.path.join(default_fedot_data_dir(), 'log.log')
        else:
            self.log_file = log_file
        # self.queue_listener, self.queue = self._init_handlers()
        # self.queue_listener.start()
        self.logger = self.get_logger(name=logger_name, config_file=config_json_file)
        self.verbosity_level = output_verbosity_level

    def _init_handlers(self):
        queue = multiprocessing.Queue(-1)

        file_handler = RotatingFileHandler(self.log_file)
        file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
        file_handler.setLevel(logging.DEBUG)

        queue_listener = QueueListener(queue, file_handler)
        return queue_listener, queue

    def get_adapter(self, prefix) -> 'LoggerAdapter':
        if prefix not in self.__log_adapters.keys():
            self.__log_adapters[prefix] = LoggerAdapter(self.logger,
                                                        {'class_name': prefix},
                                                        verbosity_level=self.verbosity_level)
        return self.__log_adapters[prefix]

    def get_logger(self, name, config_file: str):
        logger = logging.getLogger(name)
        if config_file != 'default':
            self._setup_logger_from_json_file(config_file)
        else:
            self._setup_default_logger(logger)
        return logger

    def _setup_default_logger(self, logger):
        # logger.addHandler(QueueHandler(self.queue))

        console_handler = logging.StreamHandler(sys.stdout)
        console_formatter = logging.Formatter('%(asctime)s - %(message)s')
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)

        # file_handler = RotatingFileHandler(self.log_file)
        # file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
        # file_handler.setLevel(logging.DEBUG)
        # logger.addHandler(file_handler)

    @staticmethod
    def _setup_logger_from_json_file(config_file):
        """Setup logging configuration from file"""
        try:
            with open(config_file, 'rt') as file:
                config = json.load(file)
            dictConfig(config)
        except Exception as ex:
            raise Exception(f'Can not open the log config file because of {ex}')

    @property
    def handlers(self):
        return self.logger.handlers

    def release_handlers(self):
        """This function closes handlers of logger"""
        for handler in self.handlers:
            handler.close()

    def __getstate__(self):
        """
        Define the attributes to be pickled via deepcopy or pickle
        :return: dict: state
        """
        state = dict(self.__dict__)
        del state['logger']
        return state

    def __setstate__(self, state):
        """
        Restore an unpickled dict state and assign state items
        to the new instance’s dictionary.
        :param state: pickled class attributes
        """
        self.__dict__.update(state)
        self.logger = logging.getLogger(self.logger.name)

    def __str__(self):
        return f'Log object for {self.logger.name} module'

    def __repr__(self):
        return self.__str__()


class LoggerAdapter(logging.LoggerAdapter):
    def __init__(self, logger, extra, verbosity_level: int = 1):
        super().__init__(logger=logger, extra=extra)
        self.verbosity_level = verbosity_level

    def process(self, msg, kwargs):
        return '%s - %s' % (self.extra['class_name'], msg), kwargs

    def message(self, msg, *args, **kwargs):
        """Record the message to user"""
        for_verbosity = 1
        if self.verbosity_level >= for_verbosity:
            self.log(logging.INFO, msg, *args, **kwargs)

    def info(self, msg, *args, **kwargs):
        """Record the INFO log message"""
        for_verbosity = 2
        if self.verbosity_level >= for_verbosity:
            self.log(logging.INFO, msg, *args, **kwargs)

    def debug(self, msg, *args, **kwargs):
        """
        Delegate a debug call to the underlying logger.
        """
        for_verbosity = 3
        if self.verbosity_level >= for_verbosity:
            self.log(logging.DEBUG, msg, *args, **kwargs)

    def ext_debug(self, msg, *args, **kwargs):
        """Record the extended DEBUG log message"""
        for_verbosity = 4
        if self.verbosity_level >= for_verbosity:
            self.log(logging.DEBUG, msg, *args, **kwargs)

    def warn(self, msg, *args, **kwargs):
        """Record the WARN log message"""
        for_verbosity = 2
        if self.verbosity_level >= for_verbosity:
            self.log(logging.WARN, msg, *args, **kwargs)

    def error(self, msg, *args, **kwargs):
        """Record the ERROR log message"""
        for_verbosity = 0
        if self.verbosity_level >= for_verbosity:
            self.log(logging.ERROR, msg, *args, **kwargs)


def default_log(prefix: str,
                verbose_level: int = 2) -> logging.LoggerAdapter:
    """
    :param prefix: string name for adapter
    :param verbose_level level of detalization
    :return LoggerAdapter: Log object
    """

    log = Log(logger_name='default',
              config_json_file='default',
              output_verbosity_level=verbose_level)

    return log.get_adapter(prefix=prefix)


def worker_init(q):
    qh = logging.handlers.QueueHandler(q)
    logger2 = logging.getLogger()
    logger2.setLevel(logging.DEBUG)
    logger2.addHandler(qh)


def multiproc_wrapper():

    queue = multiprocessing.Queue()

    file_handler = logging.handlers.RotatingFileHandler(os.path.join(default_fedot_data_dir(), 'log.log'))
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    file_handler.setLevel(logging.DEBUG)

    queue_listener = logging.handlers.QueueListener(queue, file_handler)
    queue_listener.start()
    return queue
