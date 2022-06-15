from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, List, Optional, Union, Dict

from fedot.core.dag.graph_operator import GraphOperator
from fedot.core.visualisation.graph_viz import GraphVisualiser

if TYPE_CHECKING:
    from fedot.core.dag.graph_node import GraphNode

from fedot.core.utilities.data_structures import ensure_wrapped_in_sequence


class Graph(ABC):
    """
    # TODO: docs!
    """

    @abstractmethod
    def add_node(self, new_node: 'GraphNode'):
        """
        Add new node to the Pipeline

        :param new_node: new GraphNode object
        """
        raise NotImplementedError()

    @abstractmethod
    def update_node(self, old_node: 'GraphNode', new_node: 'GraphNode'):
        """
        Replace old_node with new one.

        :param old_node: 'GraphNode' object to replace
        :param new_node: 'GraphNode' new object
        """
        raise NotImplementedError()

    @abstractmethod
    def update_subtree(self, old_subroot: 'GraphNode', new_subroot: 'GraphNode'):
        """
        Replace the subtrees with old and new nodes as subroots

        :param old_subroot: 'GraphNode' object to replace
        :param new_subroot: 'GraphNode' new object
        """
        raise NotImplementedError()

    @abstractmethod
    def delete_node(self, node: 'GraphNode'):
        """
        Delete chosen node redirecting all its parents to the child.

        :param node: 'GraphNode' object to delete
        """
        raise NotImplementedError()

    @abstractmethod
    def delete_subtree(self, subroot: 'GraphNode'):
        """
        Delete the subtree with node as subroot.

        :param subroot:
        """
        raise NotImplementedError()

    def __eq__(self, other) -> bool:
        # return self.operator.is_graph_equal(other)
        raise NotImplementedError()

    def __str__(self):
        return str(self._graph_description)

    def __repr__(self):
        return self.__str__()

    def __len__(self):
        return self.length

    @property
    def root_node(self):
        raise NotImplementedError()

    @property
    def length(self) -> int:
        raise NotImplementedError()

    @property
    def depth(self) -> int:
        raise NotImplementedError()

    def show(self, path: str = None):
        GraphVisualiser().visualise(self, path)

    @property
    def _graph_description(self) -> Dict:
        return {
            'depth': self._graph.depth,
            'length': self._graph.length,
            'nodes': self._graph.nodes,
        }


class GraphDelegate(Graph):
    """
    Base class used for the pipeline structure definition

    :param nodes: 'GraphNode' object(s)
    """

    # def __init__(self, nodes: Optional[Union['GraphNode', List['GraphNode']]] = None):
    #     self.nodes = []
    #     self.operator = GraphOperator(self, self._empty_postproc)
    #
    #     if nodes:
    #         for node in ensure_wrapped_in_sequence(nodes):
    #             self.add_node(node)
    #

    def __init__(self, delegate: Graph):
        self.operator = delegate

    def add_node(self, new_node: 'GraphNode'):
        self.operator.add_node(new_node)

    def update_node(self, old_node: 'GraphNode', new_node: 'GraphNode'):
        self.operator.update_node(old_node, new_node)

    def update_subtree(self, old_subroot: 'GraphNode', new_subroot: 'GraphNode'):
        self.operator.update_subtree(old_subroot, new_subroot)

    def delete_node(self, node: 'GraphNode'):
        self.operator.delete_node(node)

    def delete_subtree(self, subroot: 'GraphNode'):
        self.operator.delete_subtree(subroot)

    def __eq__(self, other) -> bool:
        return self.operator.__eq__(other)

    def __str__(self):
        return self.operator.__str__()

    def __repr__(self):
        return self.operator.__repr__()

    @property
    def root_node(self):
        return self.operator.root_node()

    @property
    def length(self) -> int:
        return self.operator.length

    @property
    def depth(self) -> int:
        return self.operator.depth
