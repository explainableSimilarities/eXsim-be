from eXsim.models import Unit, lowest_rank, TermType, Formula, Predicate, Term
from eXsim.babelnet import DatasetManager
from eXsim.summary_module import nearest_common_ancestor_batched


def k_to_v(query: Formula, pred_name: str):
    for pred in query.predicates:
        if pred.name == pred_name:
            for term in pred.terms:
                if term.type == TermType.CONSTANT:
                    term.type = TermType.BOUND_VARIABLE

    return query


def remove_pred(query: Formula, pred_name: str):
    for pred in query.predicates:
        if pred.name == pred_name:
            query.predicates.remove(pred)


def expand(unit: Unit) -> Unit:
    expansion_formulas: list = [unit.characterization.copy(), unit.characterization.copy(),
                                unit.characterization.copy()]

    if unit.characterization is None:
        raise Exception("You can not expand a unit without a characterization")
    query: Formula = Formula([])
    query.predicates = unit.characterization.predicates.copy()

    pred_names = []
    for pred in query.predicates:
        pred_names.append(pred.name)
    try:
        to_be_relaxed = lowest_rank(pred_names)
    except Exception as e:
        raise Exception(f"An error occurred while relaxing... {e}")

    k_to_v(expansion_formulas[1], to_be_relaxed)
    remove_pred(expansion_formulas[2], to_be_relaxed)

    unit.expansion = expansion_formulas

    return unit


def find_by_right(to_find: str, source: list[Predicate]) -> int:
    for i in range(len(source)):
        if source[i].terms[1].name[0] == to_find:
            return i

    return -1


def all_the_superclasses(atoms: list[Predicate]) -> list[list[Predicate]]:
    return_value = [[] for _ in range(len(atoms))]
    if len(atoms) == 0:
        return []
    template = atoms[0]

    rights: list[str] = []
    for atom in atoms:
        rights.append(atom.terms[1].name[0])

    dm = DatasetManager()
    tmp: list = dm.get_reached_synsets_by_hypernym_batched(rights)
    if len(tmp) == 0:
        return []
    for _tuple in tmp:
        index = find_by_right(_tuple[0], atoms)
        values = dm.get_synsets_by_id_batched(_tuple[1])
        for v in values:
            return_value[index].append(
                Predicate(template.type,
                          template.name,
                          (template.terms[0], v),
                          True))

    return return_value


def common_superclasses(atoms: list[list[Predicate]]) -> list[Predicate]:
    if len(atoms) == 0:
        return []
    if len(atoms) == 1:
        return atoms[0]

    sets = [set(atoms[i]) for i in range(len(atoms))]

    intersection = sets[0].intersection(*sets)

    return list(intersection)


def nearest_common_ancestors(atoms: list[Predicate]) -> list[Predicate]:
    dm = DatasetManager()
    return_value: list[Predicate] = []
    nearest_common_ancestors_list: list[str] = []

    if len(atoms) == 0:
        return []
    template = atoms[0]
    rights: list[str] = []
    for atom in atoms:
        rights.append(atom.terms[1].name[0])
    nca = nearest_common_ancestor_batched(rights, template.name)
    for i in range(len(nca)):
        nearest_common_ancestors_list.append(nca[i][0])

    for string in nearest_common_ancestors_list:
        new_term: list[Term] = dm.get_synsets_by_id_batched([string])
        for term in new_term:
            return_value.append(
                Predicate(
                    template.type,
                    template.name,
                    (template.terms[0], term),
                    template.is_deriv)
            )

    return return_value


def fill_empty(atoms, lv_1_output, lv_2_output, lv_3_output):
    last_good = atoms
    if len(lv_1_output) > 0:
        last_good = lv_1_output
    else:
        lv_1_output = last_good
    if len(lv_2_output) > 0:
        last_good = lv_2_output
    else:
        lv_2_output = last_good
    if len(lv_3_output) == 0:
        lv_3_output = last_good

    return [atoms, lv_1_output, lv_2_output, lv_3_output]


def relax_transitive(atoms: list[Predicate]) -> list[list[Predicate]]:

    secondary_strategy: bool = False
    lv_1_output: list[list[Predicate]] = all_the_superclasses(atoms)
    lv_1_output_flat: list[Predicate] = []
    for lv in lv_1_output:
        lv_1_output_flat.extend(lv)
    lv_2_output: list[Predicate] = common_superclasses(lv_1_output)
    if len(lv_2_output) == 0:
        secondary_strategy = True
        lv_2_output = nearest_common_ancestors(lv_1_output_flat)
    lv_3_output: list[Predicate] = []
    if not secondary_strategy:
        lv_3_output = nearest_common_ancestors(lv_2_output)
    else:
        if len(lv_2_output) > 0:
            lv_3_output_tmp: list[list[Predicate]] = all_the_superclasses(lv_2_output)
            lv_3_output_flat: list[Predicate] = []
            for lv in lv_3_output_tmp:
                lv_3_output_flat.extend(lv)
        else:
            lv_2_output_tmp = all_the_superclasses(lv_1_output_flat)
            for lv in lv_2_output_tmp:
                lv_2_output.extend(lv)
            if len(lv_2_output) > 0:
                lv_3_output_tmp = all_the_superclasses(lv_2_output)
                for lv in lv_3_output_tmp:
                    lv_3_output.extend(lv)



    return fill_empty(atoms, lv_1_output_flat, lv_2_output, lv_3_output)


def relax_transitive_v2(atoms: list[Predicate]) -> list[list[Predicate]]:
    lv_1_output: list[Predicate] = nearest_common_ancestors(atoms)
    lv_2_output: list[list[Predicate]] = all_the_superclasses(lv_1_output)
    lv_2_output_flat: list[Predicate] = []
    for lv in lv_2_output:
        lv_2_output_flat.extend(lv)
    lv_3_output: list[Predicate] = common_superclasses(lv_2_output)

    return fill_empty(atoms, lv_1_output, lv_2_output_flat, lv_3_output)