from abc import abstractmethod
from copy import deepcopy
from typing import Any, Dict, Generic, Optional, Type, TypeVar

from fedot.core.dag.graph_node import GraphNode
from fedot.core.log import default_log
from fedot.core.optimisers.graph import OptGraph, OptNode
from fedot.core.pipelines.node import Node, PrimaryNode, SecondaryNode
from fedot.core.pipelines.pipeline import Pipeline
from fedot.core.pipelines.template import PipelineTemplate

AdapteeType = TypeVar('AdapteeType')
AdapteeNodeType = TypeVar('AdapteeNodeType')


class BaseOptimizationAdapter(Generic[AdapteeType, AdapteeNodeType]):
    def __init__(self,
                 base_graph_class: Type[AdapteeType],
                 base_node_class: Type[AdapteeNodeType]):
        self._log = default_log(self)
        self._base_graph_class = base_graph_class
        self._base_node_class = base_node_class

    def adapt(self, adaptee: AdapteeType) -> OptGraph:
        if isinstance(adaptee, OptGraph):
            return adaptee
        return self._adapt(adaptee)

    def restore(self, opt_graph: OptGraph, metadata: Optional[Dict[str, Any]] = None) -> AdapteeType:
        if isinstance(opt_graph, self._base_graph_class):
            return opt_graph
        return self._restore(opt_graph, metadata)

    @abstractmethod
    def _adapt(self, adaptee: AdapteeType) -> OptGraph:
        raise NotImplementedError()

    @abstractmethod
    def _restore(self, opt_graph: OptGraph, metadata: Optional[Dict[str, Any]] = None) -> AdapteeType:
        raise NotImplementedError()

    def restore_as_template(self, opt_graph: OptGraph, metadata: Optional[Dict[str, Any]] = None) -> AdapteeType:
        return self.restore(opt_graph, metadata)


class DirectAdapter(BaseOptimizationAdapter[AdapteeType, AdapteeNodeType]):
    """ Naive optimization adapter for arbitrary class that just overwrites __class__. """

    def __init__(self,
                 base_graph_class: Type[AdapteeType] = None,
                 base_node_class: Type[AdapteeNodeType] = None):
        super().__init__(base_graph_class or OptGraph, base_node_class or OptNode)

    def _adapt(self, adaptee: AdapteeType) -> OptGraph:
        opt_graph = deepcopy(adaptee)
        opt_graph.__class__ = OptGraph

        for node in opt_graph.nodes:
            node.__class__ = OptNode
        return opt_graph

    def _restore(self, opt_graph: OptGraph, metadata: Optional[Dict[str, Any]] = None) -> AdapteeType:
        obj = deepcopy(opt_graph)
        obj.__class__ = self._base_graph_class
        for node in obj.nodes:
            node.__class__ = self._base_node_class
        return obj


class PipelineAdapter(BaseOptimizationAdapter[Pipeline, Node]):
    """ Optimization adapter for Pipeline class """

    def __init__(self):
        super().__init__(base_graph_class=Pipeline, base_node_class=Node)

    def _transform_to_opt_node(self, node, *args, **params):
        # Prepare content for nodes
        if type(node) == OptNode:
            self._log.warning('Unexpected: OptNode found in PipelineAdapter instead'
                              'PrimaryNode or SecondaryNode.')
        else:
            if type(node) == GraphNode:
                self._log.warning('Unexpected: GraphNode found in PipelineAdapter instead'
                                  'PrimaryNode or SecondaryNode.')
            else:
                content = {'name': str(node.operation),
                           'params': node.custom_params,
                           'metadata': node.metadata}

                node.__class__ = OptNode
                node._fitted_operation = None
                node._node_data = None
                del node.metadata
                node.content = content

    def _transform_to_pipeline_node(self, node, *args, **params):
        if node.nodes_from:
            node.__class__ = params.get('secondary_class')
        else:
            node.__class__ = params.get('primary_class')
        if not node.nodes_from:
            node.__init__(operation_type=node.content['name'], content=node.content)
        else:
            node.__init__(nodes_from=node.nodes_from,
                          operation_type=node.content['name'], content=node.content
                          )

    def _adapt(self, adaptee: Pipeline) -> OptGraph:
        """ Convert Pipeline class into OptGraph class """
        source_pipeline = deepcopy(adaptee)

        # Apply recursive transformation since root
        for node in source_pipeline.nodes:
            _transform_node(node=node, primary_class=OptNode,
                            transform_func=self._transform_to_opt_node)
        graph = OptGraph(source_pipeline.nodes)
        return graph

    def _restore(self, opt_graph: OptGraph, metadata: Optional[Dict[str, Any]] = None) -> Pipeline:
        """ Convert OptGraph class into Pipeline class """
        metadata = metadata or {}
        source_graph = deepcopy(opt_graph)

        # Inverse transformation since root node
        for node in source_graph.nodes:
            _transform_node(node=node, primary_class=PrimaryNode, secondary_class=SecondaryNode,
                            transform_func=self._transform_to_pipeline_node)
        pipeline = Pipeline(source_graph.nodes)
        pipeline.computation_time = metadata.get('computation_time_in_seconds')
        return pipeline

    def restore_as_template(self, opt_graph: OptGraph, metadata: Optional[Dict[str, Any]] = None):
        metadata = metadata or {}
        pipeline = self.restore(opt_graph, metadata)
        tmp = PipelineTemplate(pipeline)
        return tmp


def _check_nodes_references_correct(graph):
    for node in graph.nodes:
        if node.nodes_from:
            for parent_node in node.nodes_from:
                if parent_node not in graph.nodes:
                    raise ValueError('Parent node not in graph nodes list')


def _transform_node(node, primary_class, secondary_class=None, transform_func=None):
    if transform_func:
        if not secondary_class:
            secondary_class = primary_class  # if there are no differences between primary and secondary class
        transform_func(node=node,
                       primary_class=primary_class,
                       secondary_class=secondary_class)
