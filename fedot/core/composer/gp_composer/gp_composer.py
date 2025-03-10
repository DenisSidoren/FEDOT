from typing import Collection, Optional, Sequence, Tuple, Union

from fedot.core.caching.pipelines_cache import OperationsCache
from fedot.core.caching.preprocessing_cache import PreprocessingCache
from fedot.core.composer.composer import Composer
from fedot.core.data.data import InputData
from fedot.core.data.multi_modal import MultiModalData
from fedot.core.optimisers.gp_comp.pipeline_composer_requirements import PipelineComposerRequirements
from fedot.core.optimisers.graph import OptGraph
from fedot.core.optimisers.objective import PipelineObjectiveEvaluate
from fedot.core.optimisers.objective.data_source_builder import DataSourceBuilder
from fedot.core.optimisers.opt_history import OptHistory
from fedot.core.optimisers.optimizer import GraphOptimizer
from fedot.core.pipelines.pipeline import Pipeline


class GPComposer(Composer):
    """
    Genetic programming based composer
    :param optimizer: optimiser generated in ComposerBuilder.
    :param composer_requirements: requirements for composition process.
    :param history: optimization history
    :param pipelines_cache: Cache manager for fitted models, optional.
    :param preprocessing_cache: Cache manager for optional preprocessing encoders and imputers, optional.
    """

    def __init__(self, optimizer: GraphOptimizer,
                 composer_requirements: PipelineComposerRequirements,
                 history: Optional[OptHistory] = None,
                 pipelines_cache: Optional[OperationsCache] = None,
                 preprocessing_cache: Optional[PreprocessingCache] = None):

        super().__init__(optimizer, composer_requirements)
        self.composer_requirements = composer_requirements
        self.pipelines_cache: Optional[OperationsCache] = pipelines_cache
        self.preprocessing_cache: Optional[PreprocessingCache] = preprocessing_cache

        self.history: Optional[OptHistory] = history
        self.best_models: Collection[Pipeline] = ()

    def compose_pipeline(self, data: Union[InputData, MultiModalData]) -> Union[Pipeline, Sequence[Pipeline]]:
        # shuffle data if necessary
        data.shuffle()

        # Keep history of optimization
        if self.history:
            self.history.clean_results()

        # Define data source
        data_producer = DataSourceBuilder(self.composer_requirements.cv_folds,
                                          self.composer_requirements.validation_blocks).build(data)
        # Define objective function
        objective_evaluator = PipelineObjectiveEvaluate(self.optimizer.objective, data_producer,
                                                        self.composer_requirements.max_pipeline_fit_time,
                                                        self.composer_requirements.validation_blocks,
                                                        self.pipelines_cache, self.preprocessing_cache)
        objective_function = objective_evaluator.evaluate

        # Define callback for computing intermediate metrics if needed
        if self.composer_requirements.collect_intermediate_metric:
            self.optimizer.set_evaluation_callback(objective_evaluator.evaluate_intermediate_metrics)

        # Finally, run optimization process
        opt_result = self.optimizer.optimise(objective_function,
                                             show_progress=self.composer_requirements.show_progress)

        best_model, self.best_models = self._convert_opt_results_to_pipeline(opt_result)
        self.log.info('GP composition finished')
        return best_model

    def _convert_opt_results_to_pipeline(self, opt_result: Sequence[OptGraph]) -> Tuple[Pipeline, Sequence[Pipeline]]:
        adapter = self.optimizer.graph_generation_params.adapter
        multi_objective = self.optimizer.objective.is_multi_objective
        best_pipelines = [adapter.restore(graph) for graph in opt_result]
        chosen_best_pipeline = best_pipelines if multi_objective else best_pipelines[0]
        return chosen_best_pipeline, best_pipelines

    @staticmethod
    def tune_pipeline(pipeline: Pipeline, data: InputData, time_limit):
        raise NotImplementedError()
