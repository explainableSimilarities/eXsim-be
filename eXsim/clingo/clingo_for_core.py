from eXsim.models import *
import clingo

END_LINE = '.\n'


class CoreContext:

    def __init__(self, f: Formula):
        self.ks = []
        self.vs = []
        self.atoms = []
        for i in range(len(f.predicates)):
            self.atoms.append((i, f.predicates[i].name, str(f.predicates[i].terms[0]), str(f.predicates[i].terms[1])))
            for atom in f.predicates[i].terms:
                if atom.type == TermType.BOUND_VARIABLE:
                    self.vs.append(str(atom))
                else:
                    self.ks.append(str(atom))

        self.ks = list(set(self.ks))
        self.vs = list(set(self.vs))

    def tuple_composer(self, old_tuple: clingo.Symbol,
                       join_atom_name,
                       join_atom_s,
                       new_term):

        if old_tuple.type == clingo.SymbolType.Function:
            if len(old_tuple.arguments) == 0:
                terms = [join_atom_name, new_term]
                return clingo.Function('', terms)
            elif old_tuple.arguments[-1] == join_atom_s and old_tuple.arguments[0] == join_atom_name:
                args = []
                for arg in old_tuple.arguments:
                    args.append(arg)
                args.append(new_term)
                return clingo.Function('', args)

        return []

    def complete_tuple(self, tuple, dest):
        if tuple.type == clingo.SymbolType.Function:
            if len(tuple.arguments) > 0:
                if tuple.arguments[-1] == dest:
                    return tuple
        return []

    def overlapping_chain(self, a, b):
        if a.arguments == b.arguments:
            return []

        if a.arguments[0] != b.arguments[0]:
            return []

        if len(a.arguments) > len(b.arguments):
            return []

        if len(a.arguments) < len(b.arguments):

            for i in range(len(a.arguments)):
                left = a.arguments[i].string
                right = b.arguments[i].string

                if left in self.ks and right in self.vs:
                    return []

                if (left in self.ks and right in self.ks
                        and left != right):
                    return []

        else:
            comparable = True
            first_different = -1
            for i in range(len(a.arguments)):
                left = a.arguments[i].string
                right = b.arguments[i].string

                if left in self.ks and right in self.vs:
                    return []

                if (left in self.ks and right in self.ks
                        and left != right):
                    return []

                if left in self.vs and right in self.ks:
                    comparable = False

                if (left in self.vs and right in self.vs
                        and left != right and first_different == -1):
                    first_different = i

            if comparable:
                if first_different != -1:
                    return []

                if (first_different > -1 and str(a.arguments[first_different]) >
                        str(b.arguments[first_different])):
                    return []

        outs = []

        pred_name = a.arguments[0].string
        for i in range(2, len(a.arguments)):
            atom_source = a.arguments[i - 1].string
            atom_dest = a.arguments[i].string
            for j in range(len(self.atoms)):
                if (self.atoms[j][1] == pred_name and
                        self.atoms[j][2] == atom_source and
                        self.atoms[j][3] == atom_dest):
                    outs.append(clingo.Number(self.atoms[j][0]))
                    break

        return outs

    def is_superset(self, a, b):
        a_list = []
        b_list = []
        for arg in a:
            a_list.append(arg)
        for arg in b:
            b_list.append(arg)

        a_list.sort()
        b_list.sort()

        for i in range(len(b_list)):
            if a_list[i] != b_list[i]:
                return clingo.String("False")

        return clingo.String("True")


def inject_facts(f: Formula, additional: bool = False) -> (str, bool):
    program = ''
    is_core = True
    for i in range(len(f.predicates)):
        tmp = f'atom({i},"{f.predicates[i].name}",'
        has_v = False
        for term in f.predicates[i].terms:
            tmp += f'"{str(term)}",'
            program += 'term("' + str(term) + '")' + END_LINE
            if term.type == TermType.BOUND_VARIABLE:
                program += 'v("' + str(term) + '")' + END_LINE
                has_v = True
                is_core = False
            else:
                program += 'k("' + str(term) + '")' + END_LINE
                if additional:
                    program += 'map("' + str(term) + '","' + str(term) + '")' + END_LINE
        if additional and not has_v:
            program += 'core(' + str(i) + ')' + END_LINE

        tmp = tmp[:-1]
        tmp += ')' + END_LINE
        program += tmp

    if is_core:
        return program, True

    return program, False


def inject_terminals_program():
    p = ''
    p += ('occurrences(X,Count) :- v(X), #count { N : atom(N,_,X,_) } = Left, ' +
          '#count { N: atom(N,_,_,X) } = Right, Count=Left+Right') + END_LINE
    p += 'terminal(T) :- occurrences(T,1)' + END_LINE
    p += 'map(B,A) :- atom(N,Name,K,A), k(A), v(B), terminal(B), atom(M,Name,K,B)' + END_LINE
    p += 'map(B,A) :- atom(N,Name,A,K), k(A), v(B), terminal(B), atom(M,Name,B,K)' + END_LINE
    p += 'collapsed(N,M) :- atom(N,Name,B,K), atom(M,Name,A,K), map(B,A), k(K)' + END_LINE
    p += 'collapsed(N,M) :- atom(N,Name,K,B), atom(M,Name,K,A), map(B,A), k(K)' + END_LINE
    p += 'collapsed(N,M) :- atom(N,Name,B,K), atom(M,Name,A,K), map(B,A), k(K)' + END_LINE
    p += 'out(N) :- collapsed(N,_)' + END_LINE

    return p


def inject_trivial_mapping():
    p = ''
    p += ('occurrences(X,Count) :- v(X), #count { N : atom(N,_,X,_) } = Left, ' +
                '#count { N: atom(N,_,_,X) } = Right, Count=Left+Right') + END_LINE
    p += 'terminal(T) :- occurrences(T,1)' + END_LINE
    p += 'core(Atom) :- atom(Atom,Name,S,D), k(S), k(D)' + END_LINE
    p += 'out(Atom) :- not core(Atom), atom(Atom,Name,S,D), atom(A2,Name,S,D2), terminal(D), A2 < Atom' + END_LINE
    p += 'out(Atom) :- not core(Atom), atom(Atom,Name,S,D), atom(A2,Name,S2,D), terminal(S), A2 < Atom' + END_LINE

    return p


def inject_chaining():
    p = ''
    p += 'left(X) :- term(X), #count { N: atom(N,_,_,X) } = R, R=0' + END_LINE
    p += 'right(X) :- term(X), #count { N: atom(N,_,X,_) } = L, L=0, #count { N: atom(N,_,_,X) } = R, R=1' + END_LINE
    p += 'semiterminal(X) :- #count { N: atom(N,_,_,X) } = R, R=1, #count { N: atom(N,_,X,_) } = L, L=1, term(X)' + END_LINE
    p += 't_chain(@tuple_composer((),Name,X,X)) :- left(X), atom(_,Name,X,_)' + END_LINE
    p += ('t_chain(@tuple_composer(Tuple,Name,Source,Dest)) :- t_chain(Tuple), atom(_,Name,Source,Dest), ' +
          'semiterminal(Dest)') + END_LINE
    p += 'chain(@tuple_composer(Tuple,Name,Source,Dest)) :- t_chain(Tuple), atom(_,Name,Source,Dest), right(Dest)' + END_LINE
    p += 'out(@overlapping_chain(A,B)) :- chain(A), chain(B)' + END_LINE
    return p


def chain_recognizer():
    p = ''
    p += 't(X) :- v(X)' + END_LINE
    p += 't(X) :- k(X)' + END_LINE
    p += ('occurrences(X,Count) :- v(X), #count { N : atom(N,_,X,_) } = Left, ' +
          '#count { N: atom(N,_,_,X) } = Right, Count=Left+Right') + END_LINE
    p += 'terminal(T) :- occurrences(T,1)' + END_LINE
    p += ''


def execute_clingo_program(program: str, f: Formula) -> Formula:

    ctl = clingo.Control()
    ctl.add("base", [], program)
    ctl.ground([("base", [])], context=CoreContext(f))

    my_model = None
    with ctl.solve(yield_=True) as hnd:
        for m in hnd:
            my_model = m.symbols(atoms=True)

    atoms = filter(lambda x: x.name.__contains__("out"), my_model)
    for atom in atoms:
        i: int = atom.arguments[0].number
        f.predicates[i] = None
    f.predicates = list(filter(lambda x: x is not None, f.predicates))

    return f


def compose(f: Formula, hs=[True, True, True]) -> (Formula, bool):

    facts, is_core = inject_facts(f)
    if is_core:
        return f, True

    if hs[0]:

        f = execute_clingo_program(facts + inject_trivial_mapping(), f)

        facts, is_core = inject_facts(f)

        if is_core:
            return f, True


    if hs[1]:
        f = execute_clingo_program(facts + inject_terminals_program(), f)

        facts, is_core = inject_facts(f)

        if is_core:
            return f, True

    if hs[2]:

        f = execute_clingo_program(facts + inject_chaining(), f)

        facts, is_core = inject_facts(f)

        if is_core:
            return f, True

    return f, False
