import csv
import io
import itertools
import json
import os
import shutil
from pathlib import Path
from typing import Any, List, Optional, Sequence, Union

from fedot.core.log import default_log
from fedot.core.optimisers.adapters import PipelineAdapter
from fedot.core.optimisers.archive import GenerationKeeper
# ParentOperator is needed for backward compatibility with older optimization histories.
# This is a temporary solution until the issue #699 (https://github.com/nccr-itmo/FEDOT/issues/699) is closed.
from fedot.core.optimisers.gp_comp.individual import Individual, ParentOperator  # noqa
from fedot.core.optimisers.gp_comp.operators.operator import PopulationT
from fedot.core.optimisers.objective import Objective
from fedot.core.optimisers.utils.population_utils import get_metric_position
from fedot.core.repository.quality_metrics_repository import QualityMetricsEnum
from fedot.core.serializers import Serializer
from fedot.core.utils import default_fedot_data_dir
from fedot.core.visualisation.opt_viz import PipelineEvolutionVisualiser, PlotTypesEnum


class OptHistory:
    """
    Contain history, convert Pipeline to PipelineTemplate, save history to csv
    """

    def __init__(self, objective: Objective = None, save_folder: Optional[Union[str, os.PathLike]] = None):
        self._objective = objective or Objective([])
        self.individuals: List[List[Individual]] = []
        self.archive_history: List[List[Individual]] = []
        self.save_folder: Optional[str] = save_folder
        self._log = default_log(self)

    def is_empty(self) -> bool:
        return not self.individuals

    def add_to_history(self, individuals: List[Individual]):
        self.individuals.append(individuals)

    def add_to_archive_history(self, individuals: List[Individual]):
        self.archive_history.append(individuals)

    def write_composer_history_to_csv(self, file='history.csv'):
        history_dir = self._get_save_path()
        file = Path(history_dir, file)
        if not os.path.isdir(history_dir):
            os.mkdir(history_dir)
        self._write_header_to_csv(file)
        idx = 0
        adapter = PipelineAdapter()
        for gen_num, gen_inds in enumerate(self.individuals):
            for ind_num, ind in enumerate(gen_inds):
                ind_pipeline_template = adapter.restore_as_template(ind.graph, ind.metadata)
                row = [
                    idx, gen_num, ind.fitness.values,
                    len(ind_pipeline_template.operation_templates), ind_pipeline_template.depth, ind.metadata
                ]
                self._add_history_to_csv(file, row)
                idx += 1

    def _write_header_to_csv(self, f):
        with open(f, 'w', newline='') as file:
            writer = csv.writer(file, quoting=csv.QUOTE_ALL)
            metric_str = 'metric'
            if self._objective.is_multi_objective:
                metric_str += 's'
            row = ['index', 'generation', metric_str, 'quantity_of_operations', 'depth', 'metadata']
            writer.writerow(row)

    @staticmethod
    def _add_history_to_csv(f: str, row: List[Any]):
        with open(f, 'a', newline='') as file:
            writer = csv.writer(file, quoting=csv.QUOTE_ALL)
            writer.writerow(row)

    def save_current_results(self, path: Optional[Union[str, os.PathLike]] = None):
        if not path:
            path = self._get_save_path()
        if path is not None:
            try:
                last_gen_id = len(self.individuals) - 1
                last_gen = self.individuals[last_gen_id]
                last_gen_history = self.historical_fitness[last_gen_id]
                for individual, ind_fitness in zip(last_gen, last_gen_history):
                    ind_path = Path(path, str(last_gen_id), str(individual.uid))
                    additional_info = \
                        {'fitness_name': self._objective.metric_names,
                         'fitness_value': ind_fitness}
                    PipelineAdapter().restore_as_template(
                        individual.graph, individual.metadata
                    ).export_pipeline(path=ind_path, additional_info=additional_info, datetime_in_path=False)
            except Exception as ex:
                self._log.exception(ex)

    def save(self, json_file_path: Union[str, os.PathLike] = None) -> Optional[str]:
        if json_file_path is None:
            return json.dumps(self, indent=4, cls=Serializer)
        with open(json_file_path, mode='w') as json_file:
            json.dump(self, json_file, indent=4, cls=Serializer)

    @staticmethod
    def load(json_str_or_file_path: Union[str, os.PathLike] = None) -> 'OptHistory':
        def load_as_file_path():
            with open(json_str_or_file_path, mode='r') as json_file:
                return json.load(json_file, cls=Serializer)

        def load_as_json_str():
            return json.loads(json_str_or_file_path, cls=Serializer)

        if isinstance(json_str_or_file_path, os.PathLike):
            return load_as_file_path()

        try:
            return load_as_json_str()
        except json.JSONDecodeError:
            return load_as_file_path()

    def clean_results(self, path: Optional[str] = None):
        if not path and self.save_folder is not None:
            path = Path(default_fedot_data_dir(), self.save_folder)
        if path is not None:
            shutil.rmtree(path, ignore_errors=True)
            os.mkdir(path)

    def show(self, plot_type: Union[PlotTypesEnum, str] = PlotTypesEnum.fitness_box,
             save_path: Optional[Union[os.PathLike, str]] = None,
             pct_best: Optional[float] = None, show_fitness: bool = True, per_time: bool = True):
        """ Visualizes fitness values or operations used across generations.

        :param plot_type: visualization to show. Expected values are listed in
            'fedot.core.visualisation.opt_viz.PlotTypesEnum'.
        :param save_path: path to save the visualization. If set, then the image will be saved,
            and if not, it will be displayed. Essential for animations.
        :param pct_best: fraction of individuals with the best fitness per generation. The value should be in the
            interval (0, 1]. The other individuals are filtered out. The fraction will also be mentioned on the plot.
        :param show_fitness: if False, visualizations that support this parameter will not display fitness.
        :param per_time: Shows time axis instead of generations axis.
            Currently, supported for plot_type = 'show_fitness_line'.
        """

        def check_args_constraints():
            nonlocal per_time
            # Check supported cases for `pct_best`.
            if pct_best is not None and \
                    (pct_best <= 0 or pct_best > 1):
                raise ValueError('`pct_best` parameter should be in the interval (0, 1].')
            # Check supported cases for show_fitness == False.
            if not show_fitness and plot_type is not PlotTypesEnum.operations_animated_bar:
                self._log.warning(f'Argument `show_fitness` is not supported for "{plot_type.name}". It is ignored.')
            # Check plot_type-specific cases
            if plot_type in (PlotTypesEnum.fitness_line, PlotTypesEnum.fitness_line_interactive) and \
                    per_time and self.individuals[0][0].metadata.get('evaluation_time_iso') is None:
                self._log.warning('Evaluation time not found in optimization history. '
                                  'Showing fitness plot per generations...')
                per_time = False
            elif plot_type is PlotTypesEnum.operations_animated_bar:
                if not save_path:
                    raise ValueError('Argument `save_path` is required to save the animation.')

        if isinstance(plot_type, str):
            try:
                plot_type = PlotTypesEnum[plot_type]
            except KeyError:
                raise NotImplementedError(
                    f'Visualization "{plot_type}" is not supported. Expected values: '
                    f'{", ".join(PlotTypesEnum.member_names())}.')

        check_args_constraints()

        self._log.info('Visualizing optimization history... It may take some time, depending on the history size.')

        viz = PipelineEvolutionVisualiser()
        if plot_type is PlotTypesEnum.fitness_line:
            viz.visualize_fitness_line(self, per_time, save_path)
        elif plot_type is PlotTypesEnum.fitness_line_interactive:
            viz.visualize_fitness_line_interactive(self, per_time, save_path)
        elif plot_type is PlotTypesEnum.fitness_box:
            viz.visualise_fitness_box(self, save_path=save_path, pct_best=pct_best)
        elif plot_type is PlotTypesEnum.operations_kde:
            viz.visualize_operations_kde(self, save_path=save_path, pct_best=pct_best)
        elif plot_type is PlotTypesEnum.operations_animated_bar:
            viz.visualize_operations_animated_bar(
                self, save_path=save_path, pct_best=pct_best, show_fitness_color=show_fitness)
        else:
            raise NotImplementedError(f'Oops, plot type {plot_type.name} has no function to show!')

    @property
    def historical_fitness(self) -> Sequence[Sequence[Union[float, Sequence[float]]]]:
        """Return sequence of histories of generations per each metric"""
        if self._objective.is_multi_objective:
            historical_fitness = []
            num_metrics = len(self._objective.metrics)
            for objective_num in range(num_metrics):
                # history of specific objective for each generation
                objective_history = [[ind.fitness.values[objective_num] for ind in generation]
                                     for generation in self.individuals]
                historical_fitness.append(objective_history)
        else:
            historical_fitness = [[pipeline.fitness.value for pipeline in pop] for pop in self.individuals]
        return historical_fitness

    @property
    def all_historical_fitness(self):
        historical_fitness = self.historical_fitness
        if self._objective.is_multi_objective:
            all_historical_fitness = []
            for obj_num in range(len(historical_fitness)):
                all_historical_fitness.append(list(itertools.chain(*historical_fitness[obj_num])))
        else:
            all_historical_fitness = list(itertools.chain(*historical_fitness))
        return all_historical_fitness

    @property
    def all_historical_quality(self):
        if self._objective.is_multi_objective:
            metric_position = get_metric_position(self._objective.metrics, QualityMetricsEnum)
            all_historical_quality = self.all_historical_fitness[metric_position]
        else:
            all_historical_quality = self.all_historical_fitness
        return all_historical_quality

    @property
    def historical_pipelines(self):
        adapter = PipelineAdapter()
        return [
            adapter.restore_as_template(ind.graph, ind.metadata)
            for ind in list(itertools.chain(*self.individuals))
        ]

    def _get_save_path(self):
        if self.save_folder is not None:
            if os.path.sep in self.save_folder:
                # Defined path is full - there is no need to use default dir
                # Create folder if it's not exists
                if os.path.isdir(self.save_folder) is False:
                    os.makedirs(self.save_folder)
                return self.save_folder
            else:
                return Path(default_fedot_data_dir(), self.save_folder)
        return None

    def get_leaderboard(self, top_n: int = 10) -> str:
        """
        Prints ordered description of best solutions in history
        :param top_n: number of solutions to print
        """
        # Take only the first graph's appearance in history
        individuals_with_positions \
            = list({ind.graph.descriptive_id: (ind, gen_num, ind_num)
                    for gen_num, gen in enumerate(self.individuals)
                    for ind_num, ind in reversed(list(enumerate(gen)))}.values())

        top_individuals = sorted(individuals_with_positions,
                                 key=lambda pos_ind: pos_ind[0].fitness, reverse=True)[:top_n]

        output = io.StringIO()
        separator = ' | '
        header = separator.join(['Position', 'Fitness', 'Generation', 'Pipeline'])
        print(header, file=output)
        for ind_num, ind_with_position in enumerate(top_individuals):
            individual, gen_num, ind_num = ind_with_position
            positional_id = f'g{gen_num}-i{ind_num}'
            print(separator.join([f'{ind_num:>3}, '
                                  f'{str(individual.fitness):>8}, '
                                  f'{positional_id:>8}, '
                                  f'{individual.graph.descriptive_id}']), file=output)

        # add info about initial assumptions (stored as zero generation)
        for i, individual in enumerate(self.individuals[0]):
            ind = f'I{i}'
            print(separator.join([f'{ind:>3}'
                                  f'{str(individual.fitness):>8}',
                                  f'-',
                                  f'{individual.graph.descriptive_id}']), file=output)
        return output.getvalue()


def log_to_history(history: OptHistory, population: PopulationT, generations: GenerationKeeper):
    """
    Default variant of callback that preserves optimisation history
    :param history: OptHistory for logging
    :param population: list of individuals obtained in last iteration
    :param generations: keeper of the best individuals from all iterations
    """
    history.add_to_history(population)
    history.add_to_archive_history(generations.best_individuals)
    if history.save_folder:
        history.save_current_results()
