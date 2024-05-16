import clingo
from eXsim.models import Formula, Predicate, TermType, Term 


def inject_program(f: Formula) -> str:
    program = ''
    x = len (f.predicates)
    for i in range (len(f.predicates)):
        if isinstance(f.predicates[i], Predicate):
            
            s:Term = f.predicates[i].terms[0]
            d:Term = f.predicates[i].terms[1]
            program += f'atom({i},"{f.predicates[i].name}","{str(s).lower().replace(":","")}","{str(d).lower().replace(":","")}").\n'

            program+=f'prime_no_{i}(Name,Source,Dest):- atom(_,Name,Source,Dest), not atom({i},Name,Source,Dest)'
            for j in range (i-1,-1,-1):
                if isinstance(f.predicates[j], Predicate):
                    program += f', not out_core_{j}(Name,Source,Dest)'
            program += f'.\n'
            program += f'out_core_{i}(Name,Source,Dest) :- atom({i},Name,Source,Dest)'
            for k in range(len(f.predicates)):
                if isinstance(f.predicates[k], Predicate):
                    name = f.predicates[k].name
                    s:Term = f.predicates[k].terms[0]
                    if len(f.predicates[k].terms) > 1:
                        d:Term = f.predicates[k].terms[1]
                    else:
                        raise Exception("predicate has only one term")
                    source = f'"{str(s).lower().replace(":","")}"' if s.type != TermType.BOUND_VARIABLE else f'V_{str(s).replace(":","")}'
                    destination = f'"{str(d).lower().replace(":","")}"' if d.type != TermType.BOUND_VARIABLE else f'V_{str(d).replace(":","")}'
                    program += f', prime_no_{i}("{name}",{source},{destination})'
            program += '.\n'
        program += f"#show out_core_{i}/3.\n"
    return program




def execute_clingo_core(program: str, f:Formula) -> list[Predicate]:
    ctl = clingo.Control()
    ctl.add("base", [], program)
    ctl.ground([("base", [])])
    my_model = None
    with ctl.solve(yield_=True) as hnd:
        for m in hnd:
            my_model = m.symbols(atoms=True)
            break
    
    atoms = filter(lambda x: x.name.__contains__("out_core_"), my_model)
    atoms = map(lambda x: int(x.name.replace("out_core_","")), atoms)
    for i in atoms:
        f.predicates[i] = None
    f.predicates = list(filter(lambda x: x is not None, f.predicates))
    return f


    
    
def compute_core(f: Formula):
    return execute_clingo_core(inject_program(f),f)
