from fedot.core.repository.tasks import TaskTypesEnum

MINIMAL_SECONDS_FOR_TUNING = 15
DEFAULT_TUNING_ITERATIONS_NUMBER = 1000
MAXIMAL_ATTEMPTS_NUMBER = 1000
EVALUATION_ATTEMPTS_NUMBER = 5
DEFAULT_API_TIMEOUT_MINUTES = 5.0
DEFAULT_FORECAST_LENGTH = 30
COMPOSING_TUNING_PROPORTION = 0.6

BEST_QUALITY_PRESET_NAME = 'best_quality'
FAST_TRAIN_PRESET_NAME = 'fast_train'
AUTO_PRESET_NAME = 'auto'

MINIMAL_PIPELINE_NUMBER_FOR_EVALUATION = 100

default_data_split_ratio_by_task = {
    TaskTypesEnum.classification: 0.8,
    TaskTypesEnum.regression: 0.8,
    TaskTypesEnum.ts_forecasting: 0.5
}
