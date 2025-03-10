import datetime
from pathlib import Path

import numpy as np

from fedot.core.dag.graph_node import GraphNode
from fedot.core.optimisers.gp_comp.pipeline_composer_requirements import PipelineComposerRequirements
from fedot.core.composer.gp_composer.specific_operators import boosting_mutation
from fedot.core.dag.verification_rules import DEFAULT_DAG_RULES
from fedot.core.data.data import InputData
from fedot.core.optimisers.adapters import DirectAdapter, PipelineAdapter
from fedot.core.optimisers.archive import ParetoFront
from fedot.core.optimisers.fitness.multi_objective_fitness import MultiObjFitness
from fedot.core.optimisers.gp_comp.evaluation import MultiprocessingDispatcher
from fedot.core.optimisers.gp_comp.gp_operators import filter_duplicates
from fedot.core.optimisers.gp_comp.individual import Individual
from fedot.core.optimisers.gp_comp.operators.crossover import CrossoverTypesEnum, Crossover
from fedot.core.optimisers.gp_comp.operators.mutation import MutationTypesEnum, Mutation
from fedot.core.optimisers.graph import OptGraph, OptNode
from fedot.core.optimisers.objective import PipelineObjectiveEvaluate
from fedot.core.optimisers.objective.data_source_builder import DataSourceBuilder
from fedot.core.optimisers.objective.objective import Objective
from fedot.core.optimisers.opt_node_factory import DefaultOptNodeFactory
from fedot.core.optimisers.optimizer import GraphGenerationParams
from fedot.core.optimisers.timer import OptimisationTimer
from fedot.core.pipelines.node import PrimaryNode, SecondaryNode
from fedot.core.pipelines.pipeline import Pipeline
from fedot.core.pipelines.pipeline_graph_generation_params import get_pipeline_generation_params
from fedot.core.pipelines.pipeline_node_factory import PipelineOptNodeFactory
from fedot.core.repository.operation_types_repository import OperationTypesRepository
from fedot.core.repository.quality_metrics_repository import ClassificationMetricsEnum
from fedot.core.repository.tasks import Task, TaskTypesEnum
from fedot.core.utils import fedot_project_root
from test.unit.composer.test_composer import to_numerical
from test.unit.dag.test_graph_utils import find_same_node, find_first
from test.unit.pipelines.test_node_cache import pipeline_first, pipeline_second, pipeline_third
from test.unit.pipelines.test_node_cache import pipeline_fourth, pipeline_fifth
from test.unit.tasks.test_forecasting import get_ts_data
from test.unit.tasks.test_regression import get_synthetic_regression_data


def file_data():
    test_file_path = Path(__file__).parents[2].joinpath('data', 'simple_classification.csv')
    input_data = InputData.from_csv(test_file_path)
    input_data.idx = to_numerical(categorical_ids=input_data.idx)
    return input_data


def graph_example():
    #    XG
    #  |     \
    # XG     KNN
    # |  \    |  \
    # LR LDA LR  LDA
    graph = OptGraph()

    root_of_tree, root_child_first, root_child_second = \
        [OptNode({'name': model}) for model in ('xgboost', 'xgboost', 'knn')]

    for root_node_child in (root_child_first, root_child_second):
        for requirement_model in ('logit', 'lda'):
            new_node = OptNode({'name': requirement_model})
            root_node_child.nodes_from.append(new_node)
            graph.add_node(new_node)
        graph.add_node(root_node_child)
        root_of_tree.nodes_from.append(root_node_child)

    graph.add_node(root_of_tree)
    return graph


def generate_pipeline_with_single_node():
    pipeline = Pipeline()
    pipeline.add_node(PrimaryNode('knn'))

    return pipeline


def generate_so_complex_pipeline():
    node_imp = PrimaryNode('simple_imputation')
    node_lagged = SecondaryNode('lagged', nodes_from=[node_imp])
    node_ridge = SecondaryNode('ridge', nodes_from=[node_lagged])
    node_decompose = SecondaryNode('decompose', nodes_from=[node_lagged, node_ridge])
    node_pca = SecondaryNode('pca', nodes_from=[node_decompose])
    node_final = SecondaryNode('ridge', nodes_from=[node_ridge, node_pca])
    pipeline = Pipeline(node_final)
    return pipeline


def pipeline_with_custom_parameters(alpha_value):
    node_scaling = PrimaryNode('scaling')
    node_norm = PrimaryNode('normalization')
    node_dtreg = SecondaryNode('dtreg', nodes_from=[node_scaling])
    node_lasso = SecondaryNode('lasso', nodes_from=[node_norm])
    node_final = SecondaryNode('ridge', nodes_from=[node_dtreg, node_lasso])
    node_final.custom_params = {'alpha': alpha_value}
    pipeline = Pipeline(node_final)

    return pipeline


def test_nodes_from_height():
    graph = graph_example()
    found_nodes = graph.nodes_from_layer(1)
    true_nodes = [node for node in graph.root_node.nodes_from]
    assert all([node_model == found_node for node_model, found_node in
                zip(true_nodes, found_nodes)])


def test_evaluate_individuals():
    file_path_train = Path(fedot_project_root(), 'test', 'data', 'simple_classification.csv')
    full_path_train = Path(fedot_project_root(), file_path_train)

    task = Task(TaskTypesEnum.classification)
    dataset_to_compose = InputData.from_csv(full_path_train, task=task)
    pipelines_to_evaluate = [pipeline_first(), pipeline_second(),
                             pipeline_third(), pipeline_fourth()]

    metric_function = ClassificationMetricsEnum.ROCAUC_penalty
    objective = Objective(metric_function)
    data_source = DataSourceBuilder().build(dataset_to_compose)
    objective_eval = PipelineObjectiveEvaluate(objective, data_source)
    adapter = PipelineAdapter()

    population = [Individual(adapter.adapt(c)) for c in pipelines_to_evaluate]
    timeout = datetime.timedelta(minutes=0.001)
    params = get_pipeline_generation_params()
    with OptimisationTimer(timeout=timeout) as t:
        evaluator = MultiprocessingDispatcher(params.adapter, timer=t).dispatch(objective_eval)
        evaluated = evaluator(population)
    assert len(evaluated) == 1
    assert evaluated[0].fitness is not None
    assert evaluated[0].fitness.valid
    assert evaluated[0].metadata['computation_time_in_seconds'] is not None

    population = [Individual(adapter.adapt(c)) for c in pipelines_to_evaluate]
    timeout = datetime.timedelta(minutes=5)
    with OptimisationTimer(timeout=timeout) as t:
        evaluator = MultiprocessingDispatcher(params.adapter, timer=t).dispatch(objective_eval)
        evaluated = evaluator(population)
    assert len(evaluated) == 4
    assert all([ind.fitness.valid for ind in evaluated])


def test_filter_duplicates():
    archive = ParetoFront()
    adapter = PipelineAdapter()

    archive_items = [Individual(adapter.adapt(p)) for p in [pipeline_first(), pipeline_second(), pipeline_third()]]
    population = [Individual(adapter.adapt(p)) for p in [pipeline_first(), pipeline_second(),
                                                         pipeline_third(), pipeline_fourth()]]
    archive_items_fitness = ((0.80001, 0.25), (0.7, 0.1), (0.9, 0.7))
    population_fitness = ((0.8, 0.25), (0.59, 0.25), (0.9, 0.7), (0.7, 0.1))
    weights = (-1, 1)
    for ind_num in range(len(archive_items)):
        archive_items[ind_num].set_evaluation_result(
            MultiObjFitness(values=archive_items_fitness[ind_num], weights=weights))
    for ind_num in range(len(population)):
        population[ind_num].set_evaluation_result(MultiObjFitness(values=population_fitness[ind_num], weights=weights))
    archive.update(archive_items)
    filtered_archive = filter_duplicates(archive, population)
    assert len(filtered_archive) == 1
    assert filtered_archive[0].fitness.values[0] == -0.80001
    assert filtered_archive[0].fitness.values[1] == 0.25


def test_crossover():
    adapter = PipelineAdapter()
    graph_example_first = adapter.adapt(pipeline_first())
    graph_example_second = adapter.adapt(pipeline_second())
    crossover_types = [CrossoverTypesEnum.none]
    requirements = PipelineComposerRequirements(primary=[], secondary=[], max_depth=3, crossover_prob=1)
    crossover = Crossover(crossover_types, requirements, get_pipeline_generation_params())
    new_graphs = crossover([Individual(graph_example_first), Individual(graph_example_second)])
    assert new_graphs[0].graph == graph_example_first
    assert new_graphs[1].graph == graph_example_second
    crossover_types = [CrossoverTypesEnum.subtree]
    requirements.crossover_prob = 0
    crossover = Crossover(crossover_types, requirements, get_pipeline_generation_params())
    new_graphs = crossover([Individual(graph_example_first), Individual(graph_example_second)])
    assert new_graphs[0].graph == graph_example_first
    assert new_graphs[1].graph == graph_example_second


def test_mutation():
    adapter = PipelineAdapter()
    ind = Individual(adapter.adapt(pipeline_first()))
    mutation_types = [MutationTypesEnum.none]
    task = Task(TaskTypesEnum.classification)
    primary_model_types, _ = OperationTypesRepository().suitable_operation(task_type=task.task_type)
    secondary_model_types = ['xgboost', 'knn', 'lda', 'qda']
    composer_requirements = PipelineComposerRequirements(primary=primary_model_types,
                                                         secondary=secondary_model_types, mutation_prob=1,
                                                         max_depth=3)
    graph_gener_params = get_pipeline_generation_params(requirements=composer_requirements,
                                                        task=task)
    mutation = Mutation(mutation_types=mutation_types, graph_generation_params=graph_gener_params,
                        requirements=composer_requirements)
    new_ind = mutation(ind)
    assert new_ind.graph == ind.graph
    mutation_types = [MutationTypesEnum.growth]
    composer_requirements = PipelineComposerRequirements(primary=primary_model_types,
                                                         secondary=secondary_model_types, mutation_prob=0,
                                                         max_depth=3)
    mutation = Mutation(mutation_types=mutation_types, graph_generation_params=graph_gener_params,
                        requirements=composer_requirements)
    new_ind = mutation(ind)
    assert new_ind.graph == ind.graph
    ind = Individual(adapter.adapt(pipeline_fifth()))
    new_ind = mutation(ind)
    assert new_ind.graph == ind.graph


def test_intermediate_add_mutation_for_linear_graph():
    """
    Tests single_add mutation can add node between two existing nodes
    """

    linear_two_nodes = OptGraph(OptNode({'name': 'logit'}, [OptNode({'name': 'scaling'})]))
    nodes_from = [OptNode({'name': 'one_hot_encoding'}, [OptNode({'name': 'scaling'})])]
    linear_three_nodes_inner = OptGraph(OptNode({'name': 'logit'}, nodes_from))

    composer_requirements = PipelineComposerRequirements(primary=['scaling'],
                                                         secondary=['one_hot_encoding'], mutation_prob=1,
                                                         max_depth=3)

    graph_params = get_pipeline_generation_params(requirements=composer_requirements,
                                                  rules_for_constraint=DEFAULT_DAG_RULES)
    successful_mutation_inner = False
    mutation = Mutation(mutation_types=[MutationTypesEnum.single_add], graph_generation_params=graph_params,
                        requirements=composer_requirements)

    for _ in range(100):
        graph_after_mutation = mutation(Individual(linear_two_nodes)).graph
        if not successful_mutation_inner:
            successful_mutation_inner = \
                graph_after_mutation.root_node.descriptive_id == linear_three_nodes_inner.root_node.descriptive_id
        else:
            break

    assert successful_mutation_inner


def test_parent_add_mutation_for_linear_graph():
    """
    Tests single_add mutation can add node before existing node
    """

    linear_one_node = OptGraph(OptNode({'name': 'logit'}))

    linear_two_nodes = OptGraph(OptNode({'name': 'logit'}, [OptNode({'name': 'scaling'})]))

    composer_requirements = PipelineComposerRequirements(primary=['scaling'],
                                                         secondary=['logit'], mutation_prob=1, max_depth=2)

    graph_params = GraphGenerationParams(adapter=DirectAdapter(),
                                         rules_for_constraint=DEFAULT_DAG_RULES,
                                         node_factory=DefaultOptNodeFactory(requirements=composer_requirements))
    successful_mutation_outer = False

    mutation = Mutation(mutation_types=[MutationTypesEnum.single_add], graph_generation_params=graph_params,
                        requirements=composer_requirements)

    for _ in range(200):  # since add mutations has a lot of variations
        graph_after_mutation = mutation(Individual(linear_one_node)).graph
        if not successful_mutation_outer:
            successful_mutation_outer = \
                graph_after_mutation.root_node.descriptive_id == linear_two_nodes.root_node.descriptive_id
        else:
            break
    assert successful_mutation_outer


def test_edge_mutation_for_graph():
    """
    Tests edge mutation can add edge between nodes
    """
    graph_without_edge = \
        OptGraph(OptNode({'name': 'logit'}, [OptNode({'name': 'one_hot_encoding'}, [OptNode({'name': 'scaling'})])]))

    primary = OptNode({'name': 'scaling'})
    graph_with_edge = \
        OptGraph(OptNode({'name': 'logit'}, [OptNode({'name': 'one_hot_encoding'}, [primary]), primary]))

    composer_requirements = PipelineComposerRequirements(primary=['scaling', 'one_hot_encoding'],
                                                         secondary=['logit', 'scaling'], mutation_prob=1,
                                                         max_depth=graph_with_edge.depth)

    graph_params = get_pipeline_generation_params(requirements=composer_requirements,
                                                  rules_for_constraint=DEFAULT_DAG_RULES)
    successful_mutation_edge = False
    mutation = Mutation(mutation_types=[MutationTypesEnum.single_edge], graph_generation_params=graph_params,
                        requirements=composer_requirements)
    for _ in range(100):
        graph_after_mutation = mutation(Individual(graph_without_edge)).graph
        if not successful_mutation_edge:
            successful_mutation_edge = \
                graph_after_mutation.root_node.descriptive_id == graph_with_edge.root_node.descriptive_id
        else:
            break
    assert successful_mutation_edge


def test_replace_mutation_for_linear_graph():
    """
    Tests single_change mutation can change node to another
    """
    linear_two_nodes = OptGraph(OptNode({'name': 'logit'}, [OptNode({'name': 'scaling'})]))

    linear_changed = OptGraph(OptNode({'name': 'logit'}, [OptNode({'name': 'one_hot_encoding'})]))

    composer_requirements = PipelineComposerRequirements(primary=['scaling', 'one_hot_encoding'],
                                                         secondary=['logit'], mutation_prob=1, max_depth=2)

    graph_params = GraphGenerationParams(adapter=DirectAdapter(),
                                         rules_for_constraint=DEFAULT_DAG_RULES,
                                         node_factory=PipelineOptNodeFactory(requirements=composer_requirements))
    successful_mutation_replace = False
    mutation = Mutation(mutation_types=[MutationTypesEnum.single_change], graph_generation_params=graph_params,
                        requirements=composer_requirements)
    for _ in range(100):
        graph_after_mutation = mutation(Individual(linear_two_nodes)).graph
        if not successful_mutation_replace:
            successful_mutation_replace = \
                graph_after_mutation.root_node.descriptive_id == linear_changed.root_node.descriptive_id
        else:
            break
    assert successful_mutation_replace


def test_drop_mutation_for_linear_graph():
    """
    Tests single_drop mutation can remove node
    """

    linear_two_nodes = OptGraph(OptNode({'name': 'logit'}, [OptNode({'name': 'scaling'})]))

    linear_one_node = OptGraph(OptNode({'name': 'logit'}))

    composer_requirements = PipelineComposerRequirements(primary=['scaling'],
                                                         secondary=['logit'], mutation_prob=1, max_depth=2)

    graph_params = get_pipeline_generation_params(requirements=composer_requirements,
                                                  rules_for_constraint=DEFAULT_DAG_RULES)
    successful_mutation_drop = False
    mutation = Mutation(mutation_types=[MutationTypesEnum.single_drop], graph_generation_params=graph_params,
                        requirements=composer_requirements)

    for _ in range(100):
        graph_after_mutation = mutation(Individual(linear_two_nodes)).graph
        if not successful_mutation_drop:
            successful_mutation_drop = \
                graph_after_mutation.root_node.descriptive_id == linear_one_node.root_node.descriptive_id
        else:
            break
    assert successful_mutation_drop


def test_boosting_mutation_for_linear_graph():
    """
    Tests boosting mutation can add correct boosting cascade
    """

    linear_one_node = OptGraph(OptNode({'name': 'knn'}, [OptNode({'name': 'scaling'})]))

    init_node = OptNode({'name': 'scaling'})
    model_node = OptNode({'name': 'knn'}, [init_node])

    boosting_graph = \
        OptGraph(
            OptNode({'name': 'logit'},
                    [model_node, OptNode({'name': 'linear', },
                                         [OptNode({'name': 'class_decompose'},
                                                  [model_node, init_node])])]))

    available_operations = [node.content['name'] for node in boosting_graph.nodes]
    composer_requirements = PipelineComposerRequirements(primary=available_operations,
                                                         secondary=available_operations, mutation_prob=1,
                                                         max_depth=2)

    graph_params = get_pipeline_generation_params(requirements=composer_requirements,
                                                  rules_for_constraint=DEFAULT_DAG_RULES,
                                                  task=Task(TaskTypesEnum.classification))
    successful_mutation_boosting = False
    mutation = Mutation(mutation_types=[boosting_mutation], graph_generation_params=graph_params,
                        requirements=composer_requirements)
    for _ in range(100):
        if not successful_mutation_boosting:
            graph_after_mutation = mutation(Individual(linear_one_node)).graph
            successful_mutation_boosting = \
                graph_after_mutation.root_node.descriptive_id == boosting_graph.root_node.descriptive_id
        else:
            break
    assert successful_mutation_boosting

    # check that obtained pipeline can be fitted
    pipeline = PipelineAdapter().restore(graph_after_mutation)
    data = file_data()
    pipeline.fit(data)
    result = pipeline.predict(data)
    assert result is not None


def test_boosting_mutation_for_non_lagged_ts_model():
    """
    Tests boosting mutation can add correct boosting cascade for ts forecasting with non-lagged model
    """
    linear_two_nodes = OptGraph(OptNode({'name': 'clstm'},
                                        nodes_from=[OptNode({'name': 'smoothing'})]))

    init_node = OptNode({'name': 'smoothing'})
    model_node = OptNode({'name': 'clstm'}, nodes_from=[init_node])
    lagged_node = OptNode({'name': 'lagged'}, nodes_from=[init_node])

    boosting_graph = \
        OptGraph(
            OptNode({'name': 'ridge'},
                    [model_node, OptNode({'name': 'ridge', },
                                         [OptNode({'name': 'decompose'},
                                                  [model_node, lagged_node])])]))
    adapter = PipelineAdapter()
    # to ensure hyperparameters of custom models
    boosting_graph = adapter.adapt(adapter.restore(boosting_graph))

    available_operations = [node.content['name'] for node in boosting_graph.nodes]
    composer_requirements = PipelineComposerRequirements(primary=available_operations,
                                                         secondary=available_operations, mutation_prob=1, max_depth=2)

    graph_params = get_pipeline_generation_params(requirements=composer_requirements,
                                                  rules_for_constraint=DEFAULT_DAG_RULES,
                                                  task=Task(TaskTypesEnum.ts_forecasting))
    successful_mutation_boosting = False
    mutation = Mutation(mutation_types=[boosting_mutation], graph_generation_params=graph_params,
                        requirements=composer_requirements)
    for _ in range(100):
        if not successful_mutation_boosting:
            graph_after_mutation = mutation(Individual(linear_two_nodes)).graph
            successful_mutation_boosting = \
                graph_after_mutation.root_node.descriptive_id == boosting_graph.root_node.descriptive_id
        else:
            break
    assert successful_mutation_boosting

    # check that obtained pipeline can be fitted
    pipeline = PipelineAdapter().restore(graph_after_mutation)
    data_train, data_test = get_ts_data()
    pipeline.fit(data_train)
    result = pipeline.predict(data_test)
    assert result is not None


def test_pipeline_adapters_params_correct():
    """ Checking the correct conversion of hyperparameters in nodes when nodes
    are passing through adapter
    """
    init_alpha = 12.1
    pipeline = pipeline_with_custom_parameters(init_alpha)

    # Convert into OptGraph object
    adapter = PipelineAdapter()
    opt_graph = adapter.adapt(pipeline)
    # Get Pipeline object back
    restored_pipeline = adapter.restore(opt_graph)
    # Get hyperparameter value after pipeline restoration
    restored_alpha = restored_pipeline.root_node.custom_params['alpha']
    assert np.isclose(init_alpha, restored_alpha)


def test_preds_before_and_after_convert_equal():
    """ Check if the pipeline predictions change before and after conversion
    through the adapter
    """
    init_alpha = 12.1
    pipeline = pipeline_with_custom_parameters(init_alpha)

    # Generate data
    input_data = get_synthetic_regression_data(n_samples=10, n_features=2,
                                               random_state=2021)
    # Init fit
    pipeline.fit(input_data)
    init_preds = pipeline.predict(input_data)

    # Convert into OptGraph object
    adapter = PipelineAdapter()
    opt_graph = adapter.adapt(pipeline)
    restored_pipeline = adapter.restore(opt_graph)

    # Restored pipeline fit
    restored_pipeline.fit(input_data)
    restored_preds = restored_pipeline.predict(input_data)

    assert np.array_equal(init_preds.predict, restored_preds.predict)


def test_crossover_with_single_node():
    adapter = PipelineAdapter()
    graph_example_first = adapter.adapt(generate_pipeline_with_single_node())
    graph_example_second = adapter.adapt(generate_pipeline_with_single_node())

    graph_params = get_pipeline_generation_params(rules_for_constraint=DEFAULT_DAG_RULES)
    requirements = PipelineComposerRequirements(primary=[], secondary=[], max_depth=3, crossover_prob=1)

    for crossover_type in CrossoverTypesEnum:
        crossover = Crossover([crossover_type], requirements, graph_params)
        new_graphs = crossover([Individual(graph_example_first), Individual(graph_example_second)])

        assert new_graphs[0].graph == graph_example_first
        assert new_graphs[1].graph == graph_example_second


def test_mutation_with_single_node():
    adapter = PipelineAdapter()
    individual = Individual(adapter.adapt(generate_pipeline_with_single_node()))
    task = Task(TaskTypesEnum.classification)
    available_model_types, _ = OperationTypesRepository().suitable_operation(task_type=task.task_type)

    composer_requirements = PipelineComposerRequirements(primary=available_model_types, secondary=available_model_types,
                                                         max_arity=3, max_depth=3, pop_size=5, num_of_generations=4,
                                                         crossover_prob=.8, mutation_prob=1)

    graph_params = get_pipeline_generation_params(requirements=composer_requirements,
                                                  rules_for_constraint=DEFAULT_DAG_RULES,
                                                  task=task)
    mutation = Mutation(mutation_types=[MutationTypesEnum.reduce], graph_generation_params=graph_params,
                        requirements=composer_requirements)
    new_individual = mutation(individual)
    assert individual.graph == new_individual.graph

    mutation = Mutation(mutation_types=[MutationTypesEnum.single_drop], graph_generation_params=graph_params,
                        requirements=composer_requirements)
    new_individual = mutation(individual)
    assert individual.graph == new_individual.graph


def test_no_opt_or_graph_nodes_after_mutation():
    adapter = PipelineAdapter()
    graph = adapter.adapt(generate_pipeline_with_single_node())
    task = Task(TaskTypesEnum.classification)
    mutation_types = [MutationTypesEnum.growth]
    available_model_types, _ = OperationTypesRepository().suitable_operation(task_type=task.task_type)
    composer_requirements = PipelineComposerRequirements(primary=available_model_types, secondary=available_model_types,
                                                         max_arity=3, max_depth=2, pop_size=5, num_of_generations=4,
                                                         crossover_prob=.8, mutation_prob=1)
    graph_params = get_pipeline_generation_params(composer_requirements, DEFAULT_DAG_RULES, task)
    mutation = Mutation(mutation_types=mutation_types, graph_generation_params=graph_params,
                        requirements=composer_requirements)
    new_graph, _ = mutation._adapt_and_apply_mutations(new_graph=graph, num_mut=1)
    new_pipeline = adapter.restore(new_graph)

    assert not find_first(new_pipeline, lambda n: type(n) in (GraphNode, OptNode))


def test_no_opt_or_graph_nodes_after_adapt_so_complex_graph():
    adapter = PipelineAdapter()
    pipeline = generate_so_complex_pipeline()
    graph = adapter.adapt(pipeline)

    assert not find_first(pipeline, lambda n: type(n) in (GraphNode, OptNode))
