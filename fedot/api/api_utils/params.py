import random
import numpy as np

from fedot.core.log import default_log
from fedot.core.repository.tasks import Task, TaskTypesEnum, TsForecastingParams


class Fedot_params_helper():

    def __init__(self):
        return

    def get_default_evo_params(self):
        """ Dictionary with default parameters for composer """
        return {'max_depth': 2,
                'max_arity': 3,
                'pop_size': 20,
                'num_of_generations': 20,
                'learning_time': 2,
                'preset': 'light_tun'}

    def get_default_metric(self, problem: str):
        default_test_metric_dict = {
            'regression': ['rmse', 'mae'],
            'classification': ['roc_auc', 'f1'],
            'multiclassification': 'f1',
            'clustering': 'silhouette',
            'ts_forecasting': ['rmse', 'mae']
        }
        return default_test_metric_dict[problem]

    def get_task_params(self,
                        problem,
                        task_params):
        task_dict = {'regression': Task(TaskTypesEnum.regression, task_params=task_params),
                     'classification': Task(TaskTypesEnum.classification, task_params=task_params),
                     'clustering': Task(TaskTypesEnum.clustering, task_params=task_params),
                     'ts_forecasting': Task(TaskTypesEnum.ts_forecasting, task_params=task_params)
                     }
        return task_dict[problem]

    def check_input_params(self, **input_params):
        self.metric_to_compose = None
        self.composer_params['problem'] = input_params['problem']
        self.log = default_log('FEDOT logger', verbose_level=input_params['verbose_level'])

        if input_params['seed'] is not None:
            np.random.seed(input_params['seed'])
            random.seed(input_params['seed'])

        if input_params['learning_time'] is not None:
            self.composer_params['learning_time'] = self.composer_params['learning_time']
            self.composer_params['num_of_generations'] = 10000

        if 'metric' in self.composer_params:
            self.composer_params['composer_metric'] = self.composer_params['metric']
            del self.composer_params['metric']
            self.metric_to_compose = self.composer_params['composer_metric']

        if input_params['problem'] == 'ts_forecasting' and input_params['task_params'] is None:
            self.task_params = TsForecastingParams(forecast_length=30)

        if input_params['problem'] == 'clustering':
            raise ValueError('This type of task is not not supported in API now')

    def get_initial_params(self, **input_params):

        if input_params['composer_params'] is None:
            self.composer_params = self.get_default_evo_params()
        else:
            self.composer_params = {**self.get_default_evo_params(), **input_params['composer_params']}

        self.check_input_params(**input_params)

        self.task = self.get_task_params(input_params['problem'],
                                         input_params['task_params'])
        self.metric_name = self.get_default_metric(input_params['problem'])

        return

    def initialize_params(self, **input_params):
        self.get_initial_params(**input_params)
        param_dict = {
            'task': self.task,
            'logger': self.log,
            'metric_name': self.metric_name,
            'composer_metric': self.metric_to_compose
        }

        return {**param_dict, **self.composer_params}
