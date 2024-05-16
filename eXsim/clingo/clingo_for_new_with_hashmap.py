import clingo
from eXsim.models import Formula, Predicate, TermType, Term 



def inject_program(f: Formula, constant_map: {}, predicate_map: {}) -> str:
    program = ''
    for i in range (len(f.predicates)):
        if isinstance(f.predicates[i], Predicate):
            
            s:int = constant_map[f.predicates[i].terms[0]]
            d:int = constant_map[f.predicates[i].terms[1]]
            program += f'atom({i},{predicate_map[f.predicates[i].name]},{s},{d}).\n'

            program+=f'prime_no_{i}(Name,Source,Dest):- atom(_,Name,Source,Dest), not atom({i},Name,Source,Dest)'
            for j in range (i-1,-1,-1):
                if isinstance(f.predicates[j], Predicate):
                    program += f', not out_core_{j}(Name,Source,Dest)'
            program += f'.\n'
            program += f'out_core_{i}(Name,Source,Dest) :- atom({i},Name,Source,Dest)'
            for k in range(len(f.predicates)):
                if isinstance(f.predicates[k], Predicate):
                    name:int = predicate_map[f.predicates[k].name]
                    s:int = constant_map[f.predicates[k].terms[0]]
                    d:int = constant_map[f.predicates[k].terms[1]]
                    source = f'{s}' if f.predicates[k].terms[0].type != TermType.BOUND_VARIABLE else f'V_{s}'
                    destination = f'{d}' if f.predicates[k].terms[1].type != TermType.BOUND_VARIABLE else f'V_{d}'
                    program += f', prime_no_{i}({name},{source},{destination})'
            program += '.\n'

    return program




def execute_clingo_core(program: str, f:Formula) -> list[Predicate]:
    ctl = clingo.Control()
    ctl.add("base", [], program)
    ctl.ground([("base", [])])
    my_model = None
    with ctl.solve(yield_=True) as hnd:
        for m in hnd:
            my_model = m.symbols(atoms=True)
    
    atoms = filter(lambda x: x.name.__contains__("out_core_"), my_model)
    atoms = map(lambda x: int(x.name.replace("out_core_","")), atoms)
    for i in atoms:
        f.predicates[i] = None
    f.predicates = list(filter(lambda x: x is not None, f.predicates))
    return f


    
    
def compute_core(f: Formula):

    constant_map = {}
    predicate_map = {}
    k = 0
    for i in range (len(f.predicates)):
        if isinstance(f.predicates[i], Predicate):
            if f.predicates[i].name not in predicate_map.keys():
                predicate_map[f.predicates[i].name] = k
                k += 1
            for term in f.predicates[i].terms:
                if term not in constant_map.keys():
                    constant_map[term] = k
                    k += 1
    
    return execute_clingo_core(inject_program(f, constant_map, predicate_map),f)
