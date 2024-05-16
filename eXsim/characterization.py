from eXsim.clingo.clingo_for_reachability import nearly_connected_part
from eXsim.clingo.clingo_for_new_with_hashmap import compute_core
from eXsim.clingo.clingo_for_new import compute_core as compute_core_no_hashmap
from eXsim.clingo.clingo_for_core import compose
from eXsim.clingo.clingo_for_generic_homomorphism import unit_comparison_workflow
from typing import Tuple, Type

from eXsim.models import Formula, Predicate, Term, TermType, Unit


def simplify(f: Formula, fr: list[Term], hs=[True, True, True]) -> Tuple[Formula, bool]:
    return compose(f, hs)


def characterize(unit: Unit, readable: bool = False, hs=[True, True, True], core: bool = True) -> Formula:
    if any([item is None for item in unit.entities.values()]):
        raise Exception("All entities must have a summary")

    if len(unit.entities) <= 0:
        raise Exception("It is not possible to characterize a empty unit")


    if len(unit.entities) == 1:
        unit.characterization = list(unit.entities.values())[0]

    if unit.characterization is None:

        sorted_list = unit.to_sorted_list()

        e1: Tuple[Term, ...] = sorted_list[0][0]
        s1: Formula = sorted_list[0][1].atoms
        sorted_list.pop(0)

        while len(sorted_list) > 0:
            e2: Tuple[Term, ...] = sorted_list[0][0]
            s2: Formula = sorted_list[0][1].atoms
            sorted_list.pop(0)

            e1, s1 = compute_pairwise_characterization(e1, s1, e2, s2, readable, hs, core)
        unit.characterization = s1

    return unit.characterization


def compute_pairwise_characterization(e1: tuple, s1, e2: tuple, s2,
                                      readable: bool = True, hs=[True, True, True], core: bool = True) -> Tuple[Tuple, Type['Formula']]:

    if (not all([isinstance(item, Term) for item in e1]) or
            not all([isinstance(item, Term) for item in e2])):
        raise Exception("Tuples in a unit must contain only entities!")

    if (not isinstance(s1, Formula) or
            not isinstance(s2, Formula)):
        raise Exception("Wrong type for summaries")

    if len(e1) <= 0 or len(e2) <= 0:
        raise Exception("All tuples must have a positive arity")

    if len(e1) != len(e2):
        raise Exception("All tuples must have the same arity")

    fr = []

    for i in range(len(e1)):
        fr.append(e1[i].direct_product(e2[i]))

    to_return: Tuple[Term, ...] = tuple(fr)

    p: list[Predicate] = []
    d: list[Predicate] = []

    for i in range(len(s1.predicates)):
        for j in range(len(s2.predicates)):
            if (s1.predicates[i].name == s2.predicates[j].name and
                    len(s1.predicates[i].terms) == len(s2.predicates[j].terms) and
                    s1.predicates[i].is_deriv == s2.predicates[j].is_deriv):
                tmp = s1.predicates[i].direct_product(s2.predicates[j], fr)
                if not s1.predicates[i].is_deriv and tmp is not None:
                    p.append(tmp)
                elif s1.predicates[i].is_deriv and tmp is not None:
                    d.append(tmp)

    f = Formula(p)
    f.transform(fr)

    der_f = None

    if len(d) > 0:
        der_f = Formula(d)
        der_f.transform(fr)

    for x in fr:
        x.type = TermType.FREE_VARIABLE

    if any([len(item.terms) < 2 for item in f.predicates]):
        raise Exception("top check failed after transformation of variables ")

    f = nearly_connected_part(f, fr)
    is_core: bool = False
    if core:
        f, is_core = simplify(f, fr, hs)

    if len(d) > 0:
        for predicate in der_f.predicates:
            if predicate not in f.predicates:
                f.predicates.append(predicate)

    if not is_core and core:
        if not readable:
            f = compute_core(f)
        else:
            f = compute_core_no_hashmap(f)


    return to_return, f


def compare_units(u1: Unit, u2: Unit):
    if u1.characterization is None or u2.characterization is None:
        raise Exception("Both units must have a characterization")

    return unit_comparison_workflow(u1, u2)
