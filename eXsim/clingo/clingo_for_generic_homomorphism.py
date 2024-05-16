import clingo
from eXsim.models import *

ENDLINE: str = '.\n'


class HomContext:

    def __init__(self, u1: Unit = None, u2: Unit = None):
        self.u1 = u1
        self.u2 = u2


def execute_clingo_program(program: str) -> bool:
    ctl = clingo.Control()
    ctl.add("base", [], program)
    ctl.ground([("base", [])], context=HomContext())

    with ctl.solve(yield_=True) as hnd:
        for _ in hnd:
            return True

    return False


def inject_facts(f1: Formula, f2: Formula, program: list, add_info: list) -> bool:

    if len(f1.predicates) > len(f2.predicates):

        return False

    f1_prednames = set()
    f2_prednames = set()

    f1_constants = set()
    f2_constants = set()

    f1_variables = set()
    f2_variables = set()

    f1_atoms = []
    f2_atoms = []

    for i in range(len(f2.predicates)):
        if i < len(f1.predicates):
            f1_atoms.append(f1.predicates[i])
            f1_prednames.union(f1.predicates[i].name)

        f2_atoms.append(f2.predicates[i])
        f2_prednames.union(f2.predicates[i].name)

        m1 = 0
        m2 = 0

        if i < len(f1.predicates):
            m1 = len(f1.predicates[i].terms)
        m2 = len(f2.predicates[i].terms)

        for j in range(max(m1, m2)):
            if i < len(f1.predicates):
                if j < len(f1.predicates[i].terms):
                    if f1.predicates[i].terms[j].type != TermType.BOUND_VARIABLE:
                        f1_constants = f1_constants.union({str(f1.predicates[i].terms[j])})
                    else:
                        f1_variables = f1_variables.union({str(f1.predicates[i].terms[j])})

            if f2.predicates[i].terms[j].type != TermType.BOUND_VARIABLE:
                f2_constants = f2_constants.union({str(f2.predicates[i].terms[j])})
            else:
                f2_variables = f2_variables.union({str(f2.predicates[i].terms[j])})

    f1_minus_f2_p = f1_prednames.difference(f2_prednames)

    if len(f1_minus_f2_p) > 0:
        return False

    f1_minus_f2_k = f1_constants.difference(f2_constants)

    if len(f1_minus_f2_k) > 0:
        return False

    program[0] = ''
    for s_var in f1_variables:
        for t_var in f2_variables:
            add_info[2] = True
            program[0] += f'canmap("{s_var}","{t_var}")' + ENDLINE

    for s_const in f1_constants:
        program[0] += f'canmap("{s_const}","{s_const}")' + ENDLINE

    for i in range(len(f1_atoms)):
        for j in range(len(f2_atoms)):
            if f1_atoms[i].name == f2_atoms[j].name and len(f1_atoms[i].terms) == len(f2_atoms[j].terms):
                good = True
                for k in range(len(f1_atoms[i].terms)):
                    if f1_atoms[i].terms[k].type != TermType.BOUND_VARIABLE:
                        if f1_atoms[i].terms[k].type == TermType.CONSTANT and f2_atoms[j].terms[
                            k].type != TermType.CONSTANT:
                            good = False
                            break
                        elif f1_atoms[i].terms[k].type == TermType.CONSTANT and f2_atoms[j].terms[
                            k].type == TermType.CONSTANT and f1_atoms[i].terms[k] != f2_atoms[j].terms[k]:
                            good = False
                            break
                        elif f1_atoms[i].terms[k].type == TermType.FREE_VARIABLE and f2_atoms[j].terms[
                            k].type != TermType.FREE_VARIABLE:
                            good = False
                            break
                if good:
                    program[0] += f'atom_corr({i},{j})' + ENDLINE

    for i in range(len(f1_atoms)):
        tmp = ''
        for t in f1_atoms[i].terms:
            tmp += f'"{str(t)}",'
        program[0] += f'atom("a",{i},"{f1_atoms[i].name}",{tmp[:-1]})' + ENDLINE

    for i in range(len(f2_atoms)):
        tmp = ''
        for t in f2_atoms[i].terms:
            tmp += f'"{str(t)}",'
        program[0] += f'atom("b",{i},"{f2_atoms[i].name}",{tmp[:-1]})' + ENDLINE

    for t in f1_variables:
        add_info[1] = True
        program[0] += f'var("a","{t}")' + ENDLINE

    for t in f2_variables:
        add_info[1] = True
        program[0] += f'var("b","{t}")' + ENDLINE

    for t in f1_constants:
        add_info[0] = True
        program[0] += f'const("a","{t}")' + ENDLINE

    for t in f2_constants:
        add_info[0] = True
        program[0] += f'const("b","{t}")' + ENDLINE

    return True


def classical_hom(add_info: list) -> str:
    program = ''
    if add_info[1] and add_info[0]:
        program += 'canmap(V,K) :- var("a", V), const("b",K)' + ENDLINE
    program += 'map(A,B) | nmp(A,B) :- atom_corr(A,B), atom("a",A,Name,S,D), atom("b",B,Name,S1,D1), canmap(S,S1), canmap(D,D1)' + ENDLINE
    program += 'new_formula(A,Name,S,D) :- atom("a",A,Name,S1,D1), map(S,S1), map(D,D1)'+ ENDLINE
    program += ':- map(A,B1), map(A,B2), B1 !=B2' + ENDLINE
    program += ':- atom("a",A,_,_,_), not map(A,_)' + ENDLINE
    program += ':- new_formula(_,Name,S,D), not atom("b",_,Name,S,D)'+ENDLINE

    return program


def unit_comparison_workflow(u1: Unit, u2: Unit) -> UnitRelation:
    left = False
    right = False
    a_on_b = ['']
    b_on_a = ['']

    add_info = [False, False, False]

    if (inject_facts(u1.characterization, u2.characterization, a_on_b, add_info)):
        left = execute_clingo_program(a_on_b[0] + classical_hom(add_info))
    if (inject_facts(u2.characterization, u1.characterization, b_on_a, add_info)):
        right = execute_clingo_program(b_on_a[0] + classical_hom(add_info))

    if left and right:
        return UnitRelation.SIM
    elif left and not right:
        return UnitRelation.SUCC
    elif right and not left:
        return UnitRelation.PREC

    return UnitRelation.INC
