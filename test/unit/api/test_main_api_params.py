import pytest

from fedot.api.main import Fedot
from fedot.core.optimisers.opt_history import OptHistory
from fedot.core.repository.tasks import TsForecastingParams
from .dataclasses.api_params_dataclasses import TimeoutParams
from .test_main_api import get_dataset

TIMEOUT_CASES = [
    TimeoutParams(
        test_input={'timeout': -1, 'num_of_generations': 1},
        test_answer=lambda hist: len(hist.individuals) == 1
    ),
    TimeoutParams(
        test_input={'timeout': None, 'num_of_generations': 1},
        test_answer=lambda hist: len(hist.individuals) == 1
    ),
    TimeoutParams(
        test_input={'timeout': 0.1, 'num_of_generations': 15},
        test_answer=lambda hist: len(hist.individuals) < 15
    ),
    TimeoutParams(
        test_input={'timeout': -2, 'num_of_generations': 15},
        test_answer=ValueError()
    ),
    TimeoutParams(
        test_input={'timeout': -1, 'num_of_generations': 3},
        test_answer=lambda hist: len(hist.individuals) == 3
    )
]


def custom_metric(pipeline, *args, **kwargs):
    return float(pipeline.depth)


@pytest.mark.parametrize('case', TIMEOUT_CASES)
def test_timeout(case: TimeoutParams):
    composer_params = {
        'max_depth': 1,
        'max_arity': 1,
        'pop_size': 1,
        'with_tuning': False,
        'validation_blocks': 1,
        'metric': custom_metric,
        'cv_folds': None,
        **case.test_input
    }

    task_type = 'classification'
    preset = 'fast_train'
    fedot_input = {'problem': task_type, 'seed': 42, 'preset': preset, 'verbose_level': 4,
                   'timeout': composer_params['timeout'],
                   'composer_params': composer_params, 'task_params': TsForecastingParams(forecast_length=1)}

    train_data, test_data, _ = get_dataset(task_type)
    if isinstance(case.test_answer, ValueError):
        with pytest.raises(ValueError):
            Fedot(**fedot_input)
    else:
        auto_model = Fedot(**fedot_input)
        auto_model.fit(features=train_data, target='target')
        history: OptHistory = auto_model.history

        assert case.test_answer(history)
