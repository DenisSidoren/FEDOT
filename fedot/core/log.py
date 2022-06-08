import json
import logging
import os
import sys
from logging.config import dictConfig
from logging.handlers import RotatingFileHandler
from threading import RLock

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

    def clear(cls):
        cls._instances = {}


class LogProfile:
    """
    This class provides with basic logging object

    :param str prefix: name of the logger object
    :param str config_json_file: path to json file with configuration for logger setup
    :param str log_file: path to file where log messages are recorded to
    """

    def __init__(self, prefix: str = 'default',
                 config_json_file: str = 'default',
                 output_verbosity_level=1,
                 log_file: str = None):
        self.__errors_for_log_file = {}

        if not log_file:
            self.log_file = os.path.join(default_fedot_data_dir(), 'log.log')
        else:
            self.log_file = log_file

        self.profiles = []

        self.prefix = prefix
        self.config_file = config_json_file
        self.logger = logging.getLogger(prefix)
        self._setup_logger(config_file=self.config_file,
                           log_file_path=self.log_file)

        self.verbosity_level = output_verbosity_level

    def message(self, message):
        """Record the message to user"""
        for_verbosity = 1
        if self.verbosity_level >= for_verbosity:
            self.logger.info(message)

    def info(self, message):
        """Record the INFO log message"""
        for_verbosity = 2
        if self.verbosity_level >= for_verbosity:
            self.logger.info(message)

    def debug(self, message):
        """Record the DEBUG log message"""
        for_verbosity = 3
        if self.verbosity_level >= for_verbosity:
            self.logger.debug(message)

    def ext_debug(self, message):
        """Record the extended DEBUG log message"""
        for_verbosity = 4
        if self.verbosity_level >= for_verbosity:
            self.logger.debug(message)

    def warn(self, message):
        """Record the WARN log message"""
        for_verbosity = 2
        if self.verbosity_level >= for_verbosity:
            self.logger.warning(message)

    def error(self, message):
        """Record the ERROR log message"""
        for_verbosity = 0
        if self.verbosity_level >= for_verbosity:
            self.logger.error(message, exc_info=True)

    @property
    def handlers(self):
        return self.logger.handlers

    def release_handlers(self):
        """This function closes handlers of logger"""
        for handler in self.handlers:
            handler.close()

    def _setup_logger(self, config_file: str, log_file_path: str):
        """ Setup logger with config file if specified """
        if config_file != 'default':
            self._setup_logger_from_json_file(config_file)
        else:
            self._setup_default_logger(log_file_path)

    def _setup_default_logger(self, log_file_path: str):
        """ Setup default logger """
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        console_handler = logging.StreamHandler(sys.stdout)

        console_formatter = logging.Formatter('%(asctime)s - %(message)s')
        console_handler.setFormatter(console_formatter)

        try:
            file_handler = RotatingFileHandler(log_file_path)
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(formatter)
            self.logger.addHandler(file_handler)
        except PermissionError as ex:
            # if log_file is unavailable
            if not self.__errors_for_log_file.get(log_file_path, False):
                self.__errors_for_log_file[log_file_path] = True
                print(f'Logger problem: Can not log to {log_file_path} because of {ex}')
        else:
            self.__errors_for_log_file[log_file_path] = False
        self.logger.setLevel(logging.DEBUG)
        self.logger.addHandler(console_handler)

    @staticmethod
    def _setup_logger_from_json_file(config_file):
        """Setup logging configuration from file"""
        try:
            with open(config_file, 'rt') as file:
                config = json.load(file)
            dictConfig(config)
        except Exception as ex:
            raise Exception(f'Can not open the log config file because of {ex}')

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
        self.logger = logging.getLogger(self.prefix)

    def __str__(self):
        return f'Log object for {self.prefix} module'

    def __repr__(self):
        return self.__str__()


class Log(metaclass=SingletonMeta):
    __logger_dict = {}
    __default_logger = LogProfile(prefix='default',
                                  config_json_file='default',
                                  log_file=os.path.join(default_fedot_data_dir(), 'log.log'))
    # stores the flag of error notification for each log file (e.g. permission error).
    __errors_for_log_files = {}

    def __init__(self):
        pass

    def get_logger(self, prefix: str = None, config_file: str = 'default', log_file: str = None) -> 'LogProfile':
        if not prefix:
            return self.__default_logger
        if prefix not in self.__logger_dict.keys():
            if not log_file:
                log_file = os.path.join(default_fedot_data_dir(), 'log.log')
            self.__logger_dict[prefix] = LogProfile(prefix=prefix,
                                                    config_json_file=config_file,
                                                    log_file=log_file)
        return self.__logger_dict[prefix]

    @property
    def debug(self):
        """Returns the information about available loggers"""
        debug_info = {
            'loggers_number': len(self.__logger_dict),
            'loggers_names': [self.__logger_dict.keys()],
            'loggers': [self.__logger_dict.values()]
        }
        return debug_info

    def clear_cache(self):
        self.__logger_dict.clear()


# default logger: logs to default directory with default name
default_log = Log().get_logger()


# ---------------------------------------------------------------------------
# Utility functions at module level.
# Basically delegate everything to the default logger.
# ---------------------------------------------------------------------------


def get_logger(prefix: str = None, config_file: str = 'default', log_file: str = None):
    return Log().get_logger(prefix, config_file, log_file)


def message(message):
    """Record the message to user"""
    for_verbosity = 1
    if default_log.verbosity_level >= for_verbosity:
        default_log.logger.info(message)


def info(message):
    """Record the INFO log message"""
    for_verbosity = 2
    if default_log.verbosity_level >= for_verbosity:
        default_log.logger.info(message)


def debug(message):
    """Record the DEBUG log message"""
    for_verbosity = 3
    if default_log.verbosity_level >= for_verbosity:
        default_log.logger.info(message)


def ext_debug(message):
    """Record the extended DEBUG log message"""
    for_verbosity = 4
    if default_log.verbosity_level >= for_verbosity:
        default_log.logger.info(message)


def warn(message):
    """Record the WARN log message"""
    for_verbosity = 2
    if default_log.verbosity_level >= for_verbosity:
        default_log.logger.info(message)


def error(message):
    """Record the ERROR log message"""
    for_verbosity = 0
    if default_log.verbosity_level >= for_verbosity:
        default_log.logger.error(message, exc_info=True)
