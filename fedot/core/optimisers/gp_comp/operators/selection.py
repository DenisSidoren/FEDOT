import math
from random import choice, random
from typing import Any, List, TYPE_CHECKING, Sequence, Iterable, Tuple

from deap import tools

from fedot.core.optimisers.gp_comp.individual import Individual
from fedot.core.utilities.data_structures import ComparableEnum as Enum

if TYPE_CHECKING:
    from fedot.core.optimisers.optimizer import GraphGenerationParams


class SelectionTypesEnum(Enum):
    tournament = 'tournament'
    spea2 = 'spea2'


def selection(types: List[SelectionTypesEnum], population: List[Individual], pop_size: int,
              params: 'GraphGenerationParams') -> List[Any]:
    """
    Selection of individuals based on specified type of selection
    :param types: The set of selection types
    :param population: A list of individuals to select from.
    :param pop_size: The number of individuals to select.
    :param params: params for graph generation and convertation
    """
    selection_by_type = {
        SelectionTypesEnum.tournament: tournament_selection,
        SelectionTypesEnum.spea2: spea2_selection
    }

    selection_type = choice(types)
    if selection_type in selection_by_type:
        selected = selection_by_type[selection_type](population, pop_size)
        return selected
    else:
        raise ValueError(f'Required selection not found: {selection_type}')


def individuals_selection(types: List[SelectionTypesEnum], individuals: List[Any], pop_size: int,
                          graph_params: 'GraphGenerationParams') -> List[Any]:
    if pop_size == len(individuals):
        chosen = individuals
    else:
        chosen = []
        remaining_individuals = individuals
        individuals_pool_size = len(individuals)
        n_iter = 0
        while len(chosen) < pop_size and n_iter < pop_size * 10 and remaining_individuals:
            individual = selection(types, remaining_individuals, pop_size=1, params=graph_params)[0]
            if individual.uid not in (c.uid for c in chosen):
                chosen.append(individual)
                if pop_size <= individuals_pool_size:
                    remaining_individuals.remove(individual)
            n_iter += 1
    return chosen


def random_selection(individuals: List[Any], pop_size: int) -> List[int]:
    chosen = []
    n_iter = 0
    while len(chosen) < pop_size and n_iter < pop_size * 10:
        if not individuals:
            return []
        if len(individuals) <= 1:
            return [individuals[0]] * pop_size
        individual = choice(individuals)
        if individual.uid not in (c.uid for c in chosen):
            chosen.append(individual)
    return chosen


def tournament_selection(individuals: List[Any], pop_size: int, fraction: float = 0.1) -> List[Any]:
    group_size = math.ceil(len(individuals) * fraction)
    min_group_size = 2 if len(individuals) > 1 else 1
    group_size = max(group_size, min_group_size)
    chosen = []
    n_iter = 0

    while len(chosen) < pop_size and n_iter < pop_size * 10:
        group = random_selection(individuals, group_size)
        best = max(group, key=lambda ind: ind.fitness)
        if best.uid not in (c.uid for c in chosen):
            chosen.append(best)
        n_iter += 1

    return chosen


# Code of spea2 selection is modified part of DEAP library (Library URL: https://github.com/DEAP/deap).
def spea2_selection(individuals: List[Any], pop_size: int) -> List[Any]:
    N = len(individuals)
    L = len(individuals[0].fitness.values)
    K = math.sqrt(N)
    strength_fits = [0] * N
    fits = [0] * N
    dominating_inds = [list() for i in range(N)]

    for i, ind_i in enumerate(individuals):
        for j, ind_j in enumerate(individuals[i + 1:], i + 1):
            if ind_i.fitness.dominates(ind_j.fitness):
                strength_fits[i] += 1
                dominating_inds[j].append(i)
            elif ind_j.fitness.dominates(ind_i.fitness):
                strength_fits[j] += 1
                dominating_inds[i].append(j)

    for i in range(N):
        for j in dominating_inds[i]:
            fits[i] += strength_fits[j]

    # Choose all non-dominated individuals
    chosen_indices = [i for i in range(N) if fits[i] < 1]

    if len(chosen_indices) < pop_size:  # The archive is too small
        for i in range(N):
            distances = [0.0] * N
            for j in range(i + 1, N):
                dist = 0.0
                for l in range(L):
                    val = individuals[i].fitness.values[l] - \
                          individuals[j].fitness.values[l]
                    dist += val * val
                distances[j] = dist
            kth_dist = _randomized_select(distances, 0, N - 1, K)
            density = 1.0 / (kth_dist + 2.0)
            fits[i] += density

        next_indices = [(fits[i], i) for i in range(N)
                        if not i in chosen_indices]
        next_indices.sort()
        # print next_indices
        chosen_indices += [i for _, i in next_indices[:pop_size - len(chosen_indices)]]

    elif len(chosen_indices) > pop_size:  # The archive is too large
        N = len(chosen_indices)
        distances = [[0.0] * N for i in range(N)]
        sorted_indices = [[0] * N for i in range(N)]
        for i in range(N):
            for j in range(i + 1, N):
                dist = 0.0
                for l in range(L):
                    val = individuals[chosen_indices[i]].fitness.values[l] - \
                          individuals[chosen_indices[j]].fitness.values[l]
                    dist += val * val
                distances[i][j] = dist
                distances[j][i] = dist
            distances[i][i] = -1

        # Insert sort is faster than quick sort for short arrays
        for i in range(N):
            for j in range(1, N):
                l = j
                while l > 0 and distances[i][j] < distances[i][sorted_indices[i][l - 1]]:
                    sorted_indices[i][l] = sorted_indices[i][l - 1]
                    l -= 1
                sorted_indices[i][l] = j

        size = N
        to_remove = []
        while size > pop_size:
            # Search for minimal distance
            min_pos = 0
            for i in range(1, N):
                for j in range(1, size):
                    dist_i_sorted_j = distances[i][sorted_indices[i][j]]
                    dist_min_sorted_j = distances[min_pos][sorted_indices[min_pos][j]]

                    if dist_i_sorted_j < dist_min_sorted_j:
                        min_pos = i
                        break
                    elif dist_i_sorted_j > dist_min_sorted_j:
                        break

            # Remove minimal distance from sorted_indices
            for i in range(N):
                distances[i][min_pos] = float("inf")
                distances[min_pos][i] = float("inf")

                for j in range(1, size - 1):
                    if sorted_indices[i][j] == min_pos:
                        sorted_indices[i][j] = sorted_indices[i][j + 1]
                        sorted_indices[i][j + 1] = min_pos

            # Remove corresponding individual from chosen_indices
            to_remove.append(min_pos)
            size -= 1

        for index in reversed(sorted(to_remove)):
            del chosen_indices[index]

    return [individuals[i] for i in chosen_indices]


def crossover_parents_selection(population: Sequence[Individual]) -> Iterable[Tuple[Individual, Individual]]:
    return zip(population[::2], population[1::2])


# Auxiliary algorithmic functions for spea2_selection
# This code is modified part of DEAP library (Library URL: https://github.com/DEAP/deap).
def _randomized_select(array, begin, end, i):
    """Allows to select the ith smallest element from array without sorting it.
    Runtime is expected to be O(n).
    """
    if begin == end:
        return array[begin]
    q = _randomized_partition(array, begin, end)
    k = q - begin + 1
    if i < k:
        return _randomized_select(array, begin, q, i)
    else:
        return _randomized_select(array, q + 1, end, i - k)


def _randomized_partition(array, begin, end):
    i = random.randint(begin, end)
    array[begin], array[i] = array[i], array[begin]
    return _partition(array, begin, end)


def _partition(array, begin, end):
    x = array[begin]
    i = begin - 1
    j = end + 1
    while True:
        j -= 1
        while array[j] > x:
            j -= 1
        i += 1
        while array[i] < x:
            i += 1
        if i < j:
            array[i], array[j] = array[j], array[i]
        else:
            return j
