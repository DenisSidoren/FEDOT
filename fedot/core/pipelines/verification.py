from typing import Callable, List, Sequence, Optional, Union

from fedot.core.dag.graph import Graph
from fedot.core.dag.graph_verifier import GraphVerifier, VerifierRuleType
from fedot.core.dag.verification_rules import (
    has_no_cycle,
    has_no_isolated_nodes,
    has_no_self_cycled_nodes,
    has_one_root
)
from fedot.core.optimisers.adapters import PipelineAdapter, BaseOptimizationAdapter
from fedot.core.optimisers.graph import OptGraph
from fedot.core.pipelines.verification_rules import (
    has_correct_data_connections,
    has_correct_data_sources,
    has_correct_operation_positions,
    has_final_operation_as_model,
    has_no_conflicts_after_class_decompose,
    has_no_conflicts_during_multitask,
    has_no_conflicts_in_decompose,
    has_no_conflicts_with_data_flow,
    has_no_data_flow_conflicts_in_ts_pipeline,
    has_primary_nodes,
    is_pipeline_contains_ts_operations,
    only_non_lagged_operations_are_primary
)
from fedot.core.repository.tasks import TaskTypesEnum

common_rules = [has_one_root,
                has_no_cycle,
                has_no_self_cycled_nodes,
                has_no_isolated_nodes,
                has_primary_nodes,
                has_correct_operation_positions,
                has_final_operation_as_model,
                has_no_conflicts_with_data_flow,
                has_no_conflicts_in_decompose,
                has_correct_data_connections,
                has_correct_data_sources]

ts_rules = [is_pipeline_contains_ts_operations,
            only_non_lagged_operations_are_primary,
            has_no_data_flow_conflicts_in_ts_pipeline]

class_rules = [has_no_conflicts_during_multitask,
               has_no_conflicts_after_class_decompose]


def verifier_for_task(task_type: Optional[TaskTypesEnum] = None,
                      adapter: Optional[BaseOptimizationAdapter] = None):
    return GraphVerifier(rules_by_task(task_type), adapter)


def rules_by_task(task_type: Optional[TaskTypesEnum],
                  rules: Sequence[VerifierRuleType] = ()) -> Sequence[VerifierRuleType]:
    tmp_rules = []

    tmp_rules.extend(rules or common_rules)

    if task_type is TaskTypesEnum.ts_forecasting:
        tmp_rules.extend(ts_rules)
    elif task_type is TaskTypesEnum.classification:
        tmp_rules.extend(class_rules)

    return tmp_rules


def verify_pipeline(graph: Union[Graph, OptGraph],
                    rules: List[Callable] = None,
                    task_type: Optional[TaskTypesEnum] = None):
    """Method for validation of graphs with default rules.
    NB: It is preserved for simplicity, use graph checker instead."""
    adapter = PipelineAdapter()
    return GraphVerifier(rules_by_task(task_type, rules), adapter).verify(graph)
