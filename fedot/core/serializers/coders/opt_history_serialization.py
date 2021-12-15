import itertools
from typing import TYPE_CHECKING, Any, Dict, List, Type

from fedot.core.optimisers.adapters import PipelineAdapter
from fedot.core.optimisers.opt_history import OptHistory

if TYPE_CHECKING:
    from fedot.core.optimisers.gp_comp.individual import Individual

from . import any_from_json


def _convert_parent_objects_ids_to_templates(individuals: List[List['Individual']]) -> List[List['Individual']]:
    adapter = PipelineAdapter()
    for ind in list(itertools.chain(*individuals)):
        for parent_op in ind.parent_operators:
            for idx in range(len(parent_op.parent_objects)):
                parent_obj_id = parent_op.parent_objects[idx]
                for _ind in list(itertools.chain(*individuals)):
                    if parent_obj_id == _ind.graph._serialization_id:
                        parent_op.parent_objects[idx] = adapter.restore_as_template(_ind.graph, _ind.computation_time)
                        break
    return individuals


def opt_history_from_json(cls: Type[OptHistory], json_obj: Dict[str, Any]) -> OptHistory:
    deserialized = any_from_json(cls, json_obj)
    deserialized.individuals = _convert_parent_objects_ids_to_templates(deserialized.individuals)
    deserialized.archive_history = _convert_parent_objects_ids_to_templates(deserialized.archive_history)
    return deserialized
