import clingo
from eXsim.models import *

ENDLINE: str = '.\n'


def inject_facts(terms:list[str], ancestors: list[tuple[str, str]]):
    program:str = ''
    for entity in terms:
        program += f'seed("{entity}")'+ENDLINE

    for ancestor in ancestors:
        program += f'isa("{ancestor[0]}","{ancestor[1]}")'+ENDLINE

    return program


def inject_rules():
    program: str = 'isa(X,Z) :- isa(X,Y), isa(Y,Z)'+ENDLINE
    program += 'entity(X) :- isa(X,_)'+ENDLINE
    program += 'entity(Y) :- isa(_,Y)'+ENDLINE
    program += 'notAncestor(E) :- seed(S), entity(E), not isa(S,E)'+ENDLINE
    program += 'common(E) :- entity(E), not notAncestor(E)'+ENDLINE
    program += 'equiv(X,Y) :- isa(X,Y), isa(Y,X)'+ENDLINE
    program += 'noLeastCommon(E) :- common(E), isa(C,E), common(C), not equiv(C,E)'+ENDLINE
    program += 'leastCommon(X) :- common(X), not noLeastCommon(X)'+ENDLINE
    return program


def execute_clingo_lca(program: str) -> List[Term]:
    ctl = clingo.Control()
    my_model = None
    ctl.add("base", [], program)
    ctl.ground([("base", [])])

    with ctl.solve(yield_=True) as hnd:
        for m in hnd:
            my_model = m.symbols(atoms=True)

    lca = []
    for atom in my_model:
        if atom.name == 'leastCommon':
            lca.append(str(atom.arguments[0].string))


    return lca


def compute_lca(terms:list[str], ancestors: list[tuple[str, str]]) -> list[str]:
    return execute_clingo_lca(inject_facts(terms,ancestors)+inject_rules())