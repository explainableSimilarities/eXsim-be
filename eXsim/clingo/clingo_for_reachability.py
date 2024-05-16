from typing import  List

import clingo

from eXsim.models import Formula, Predicate, Term


ENDLINE = '.\n'

def inject_facts_reachability(characterization:Formula, fr) -> str:
    program  = ''
    for term in fr:
        program += f'reach("{str(term)}")'+ENDLINE
    
    for i in range (len(characterization.predicates)):
        for term in characterization.predicates[i].terms:
            program += f'pred({i},"{str(term)}")'+ENDLINE
       
    return program
        
            

def inject_rules_reachability() -> str:
    rules = ''
    rules += 'reach(X) :- pred(N,X), pred(N,Y), reach(Y)'+ENDLINE
    rules += 'reach_pred(N) :- pred(N,X), reach(X)'+ENDLINE
    return rules



def execute_clingo_reachability(program:str) -> list[int]:
    ctl = clingo.Control()
    my_model = None
    ctl.add("base", [], program)
    ctl.ground([("base", [])])

    with ctl.solve(yield_=True) as hnd:
        for m in hnd:
            my_model = m.symbols(atoms=True)

    result = []
    for atom in my_model:
        if atom.name == 'reach_pred':
            result.append(int(atom.arguments[0].number))

    return result



def prepare_and_execute_reachability(characterization:Formula, fr) -> list[int]:
    program = inject_facts_reachability(characterization, fr)
    program += inject_rules_reachability()
    return execute_clingo_reachability(program)



def nearly_connected_part(f:Formula, fr:List['Term']):
        
    for term in fr:
        if not isinstance(term, Term):
            raise Exception("Fr must be a list of terms")

    result = prepare_and_execute_reachability(f, fr)
    p:list[Predicate] = []
    for i in result:
        p.append(f.predicates[i])
    return Formula(p)
