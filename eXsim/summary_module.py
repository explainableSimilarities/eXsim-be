from eXsim.models import *
from eXsim.babelnet import DatasetManager
from eXsim.clingo.clingo_for_lca import compute_lca


def least_common_subsumer_tmp(terms:list[str], pred:str):
    if pred == "IS_A":
        rtype = PredicateType.HYPERNYM
    elif pred == "PART_OF":
        rtype = PredicateType.HOLONYM
    else:
        return []

    datasetManager = DatasetManager()

    subgraphs = datasetManager.get_subgraphs(terms, rtype)

    #lca = set(compute_lca(terms, subgraphs))
    lca = set()

    constants = {}
    commonAtoms: set[tuple[str, str]] = set()
    first = True
    
    for term in terms:
        constants[term] = set()
        ancestorSet = set([term])
        localGraph = set(subgraphs)
        reachedFromSeed = set()
        while True:
            reached = set(filter(lambda t:(t[0] in ancestorSet), localGraph))
            reachedFromSeed = reachedFromSeed.union(reached)
            localGraph = localGraph.difference(reached)
            ancestorSet = set(map(lambda t:t[1], reached))
            constants[term] = constants[term].union(ancestorSet)
            if len(reached) == 0:
                break
        if first:
            commonAtoms = reachedFromSeed.copy()
            first = False
        else:
            commonAtoms = commonAtoms.intersection(reachedFromSeed)

    subsumer_subgraphs = {}
    common = set()
    first = True
    for term in terms:
        if first:
            common = constants[term]
            first = False
        else:
            common = common.intersection(constants[term])

    for subsumer in common:
        local_new_common_atoms = commonAtoms.copy()
        ancestorSet = set([subsumer])
        subsumer_sub = set()
        while True:
            reached = set(filter(lambda t:(t[0] in ancestorSet), local_new_common_atoms))
            subsumer_sub = subsumer_sub.union(reached)
            local_new_common_atoms = local_new_common_atoms.difference(reached)
            ancestorSet = set(map(lambda t:t[1], reached))
            if len(reached) == 0:
                break
        
        subsumer_sub = frozenset(subsumer_sub)
        if subsumer_sub not in subsumer_subgraphs:
            subsumer_subgraphs[subsumer_sub] = []
        subsumer_subgraphs[subsumer_sub].append(subsumer)

    orderedSub:list[frozenset] = list(subsumer_subgraphs.keys())
    orderedSub.sort(key=lambda x:len(x))
    if len(orderedSub) > 1:
        for i in range(0, len(orderedSub)):
            if orderedSub[i] is not None:
                for j in range(i + 1, len(orderedSub)):
                    if j < len(orderedSub) and orderedSub[j] is not None:
                        if orderedSub[i].issubset(orderedSub[j]):
                            orderedSub[i] = None
                            break

    orderedSub = list(filter(lambda x: x is not None, orderedSub))



    for ord in orderedSub:
        lca = lca.union(set(subsumer_subgraphs[ord]))

    return {"lca": lca, "constants": constants}


def compute_summary_by_pred_batched(entities, config_entry:SummaryConfigEntry):
    raw_summaries = {}
    level_ranges = {}
    for term in entities:
        bfs_list = [(term, term, 0)]
        already_reached_term = {term: 0}
        level_ranges[term] = {0: [-1, -1]}

        for level in range(1, config_entry.depth + 1):
            previous_size = len(bfs_list)
            datasetManager = DatasetManager()

            if (level - 1) in level_ranges[term]:
                if config_entry.predicate_name == "IS_A":
                    synsets = datasetManager.get_reached_synsets_by_hypernym_batched(list(map(lambda element: element[0], bfs_list[level_ranges[term][level - 1][0] + 1:level_ranges[term][level - 1][1] + 2])))
                else:
                    synsets = datasetManager.get_reached_synsets_by_relation_batched(list(map(lambda element: element[0], bfs_list[level_ranges[term][level - 1][0] + 1:level_ranges[term][level - 1][1] + 2])), config_entry.predicate_name)

                for synset in synsets:
                    if synset[1] not in already_reached_term:
                        already_reached_term[synset[1]] = level + 1
                        bfs_list.append((synset[1], synset[0], level + 1))

                if len(bfs_list) > previous_size:
                    level_ranges[term][level] = [level_ranges[term][level - 1][1] + 1, len(bfs_list) - 2]

        del level_ranges[term][0]
        raw_summaries[term] = bfs_list[1:]

    return raw_summaries, level_ranges


def compute_transitive_summary_by_pred_batched(entities, config_entry:SummaryConfigEntry):
    raw_summaries = {}
    level_ranges = {}

    datasetManager = DatasetManager()
    reached = datasetManager.get_reached_synsets_variable_by_relation_batched(entities, config_entry.predicate_name)

    for term in entities:
        raw_summaries[term] = list(map(lambda r: (r, term, 1), reached[term]))
        level_ranges[term] = {1: [0, len(raw_summaries[term]) - 1]}

    return raw_summaries, level_ranges


def construct_summaries_from_lca_output(lca, summaries):
    raw_summaries = {}
    level_ranges = {}

    for term in lca["constants"]:
        to_keep = lca["lca"].copy()
        if "terms" in summaries[term]:
            to_keep = to_keep.union(set(filter(lambda c : c in summaries[term]["terms"], lca["constants"][term])))
        raw_summaries[term] = list(map(lambda r: (r, term, 1), to_keep))
        level_ranges[term] = {1: [0, len(raw_summaries[term]) - 1]}

    return raw_summaries, level_ranges


def transform_summaries(summaries, included_types):
    final_summary = {}

    for term in summaries.keys():
        if term not in final_summary:
            final_summary[term] = {}
            final_summary[term]["summary"] = Formula([])
            final_summary[term]["terms"] = summaries[term]["terms"]

        for entry in included_types:
            if entry.predicate_name in summaries[term]:
                final_summary[term]["summary"].predicates.extend(map(lambda atom: Predicate(entry.predicate_type, entry.predicate_name, (Term(atom[1]), Term(atom[0]))), summaries[term][entry.predicate_name]["atoms"]))
                if "derived_atoms" in summaries[term][entry.predicate_name]:
                    final_summary[term]["summary"].predicates.extend(map(lambda ancestor: Predicate(entry.predicate_type, entry.predicate_name, (Term(ancestor[1]), Term(ancestor[0])), is_deriv=True), summaries[term][entry.predicate_name]["derived_atoms"]))
                    merge_reached_terms(final_summary[term]["terms"], map(lambda ancestor: ancestor[0], summaries[term][entry.predicate_name]["derived_atoms"]))

    return final_summary


def is_transitive(entry:SummaryConfigEntry):
    return entry.predicate_type != PredicateType.OTHER


def merge_reached_terms(global_reached, local_reached):
    for term in local_reached:
        if term in global_reached:
            global_reached[term]["occurrences"] += 1
        else:
            global_reached[term] = {}
            global_reached[term]["occurrences"] = 1
    

def add_tops(summaries):
    for term in summaries:
        summaries[term]["summary"].predicates.append(Predicate(PredicateType.TOP, "T", (Term(term), )))
        summaries[term]["summary"].predicates.extend(map(lambda reached: Predicate(PredicateType.TOP, "T", (Term(reached), )), summaries[term]["terms"].keys()))


def beautify_summaries(summaries):
    datasetManager = DatasetManager()
    for term in summaries:
        terms = []
        for reached in summaries[term]["terms"]:
            terms.append(reached)
        full_terms = datasetManager.get_synsets_by_id_batched(terms)
        for full_term in full_terms:
            summaries[term]["terms"][full_term.name[0]]["full_repr"] = full_term


def new_aggregate_info(summaries, included_types):
    final_summary = {}

    for term in summaries.keys():
        if term not in final_summary:
            final_summary[term] = {}
            final_summary[term]["summary"] = Formula([])
    
    for entry in included_types:
        terms_intersection = set()
        not_aggregable = set()
        first = True
        for term in summaries:
            if len(summaries[term][entry.predicate_name]["atoms"]) == 0:
                continue
            if first:
                terms_intersection = set(map(lambda a: a[0],summaries[term][entry.predicate_name]["atoms"]))
                not_aggregable = set(filter(lambda t: summaries[term]["terms"][t]["occurrences"] > 1, map(lambda a: a[0],summaries[term][entry.predicate_name]["atoms"])))
                first = False
            else:
                terms_intersection = terms_intersection.intersection(set(map(lambda a: a[0],summaries[term][entry.predicate_name]["atoms"])))
                not_aggregable = not_aggregable.union(set(filter(lambda t: summaries[term]["terms"][t]["occurrences"] > 1, map(lambda a: a[0],summaries[term][entry.predicate_name]["atoms"]))))
        
        for term in summaries:
            final_summary[term]["terms"] = summaries[term]["terms"]

            source_term = Term(term)

            aggregable_deriv = terms_intersection.difference(not_aggregable)
            aggregable_not_common = set(map(lambda a: a[0],summaries[term][entry.predicate_name]["atoms"])).difference(terms_intersection).difference(not_aggregable)
            not_aggregable_local = set(map(lambda a: a[0],summaries[term][entry.predicate_name]["atoms"])).difference(aggregable_deriv).difference(aggregable_not_common)

            if len(aggregable_deriv) > 0:
                final_summary[term]["summary"].predicates.append(Predicate(entry.predicate_type, entry.predicate_name, (source_term, Term(type=TermType.AGGREGATED_TERM if len(aggregable_deriv) > 1 else TermType.CONSTANT, name=list(aggregable_deriv))), is_deriv=True))
            
            if len(aggregable_not_common) > 0:
                final_summary[term]["summary"].predicates.append(Predicate(entry.predicate_type, entry.predicate_name, (source_term, Term(type=TermType.AGGREGATED_TERM if len(aggregable_not_common) > 1 else TermType.CONSTANT, name=list(aggregable_not_common)))))

            if len(not_aggregable_local) > 0:
                final_summary[term]["summary"].predicates.extend(list(map(lambda t: Predicate(entry.predicate_type, entry.predicate_name, (source_term, Term(type=TermType.CONSTANT, name=t))), not_aggregable_local)))

    return final_summary


def summary_selector(unit:Unit, config:SummaryConfig):
    summary_approach:SummaryApproach = SummaryApproach.SINGLE_ENTITY if len(unit.entities) == 1 else SummaryApproach.MULTI_ENTITY

    entities = list(map(lambda tuple: tuple[0].name[0], unit.entities.keys()))
    summaries = {}
    for term in entities:
        summaries[term] = {}

    is_a_found = False

    for entry in config.included_types:
        if entry.predicate_name == "IS_A":
            is_a_found = True
            continue
        
        for term in entities:
            summaries[term][entry.predicate_name] = {}

        partial_summaries = {}
        level_ranges = {}

        if summary_approach == SummaryApproach.SINGLE_ENTITY or (not is_transitive(entry) and entry.depth == 1):
            partial_summaries, level_ranges = compute_summary_by_pred_batched(entities, entry)
        else:
            partial_summaries, level_ranges = compute_transitive_summary_by_pred_batched(entities, entry)
            
        for term in partial_summaries.keys():
            if "terms" not in summaries[term]:
                summaries[term]["terms"] = {}
        
            merge_reached_terms(summaries[term]["terms"], map(lambda sum_entry: sum_entry[0], partial_summaries[term]))

            summaries[term][entry.predicate_name]["atoms"] = partial_summaries[term]
            summaries[term][entry.predicate_name]["level_ranges"] = level_ranges[term]

    if is_a_found:
        lca_output = least_common_subsumer_tmp(entities, "IS_A")

        for term in lca_output["constants"]:
            if "terms" not in summaries[term]:
                summaries[term]["terms"] = {}

        partial_summaries, level_ranges = construct_summaries_from_lca_output(lca_output, summaries)
        
        for term in lca_output["constants"]:
            merge_reached_terms(summaries[term]["terms"], map(lambda sum_entry: sum_entry[0], partial_summaries[term]))

            summaries[term]["IS_A"] = {}
            summaries[term]["IS_A"]["atoms"] = partial_summaries[term]
            summaries[term]["IS_A"]["level_ranges"] = level_ranges[term]
        
    if "terms" in summaries[term]:
        if config.optimization_strategy == OptimizationStrategy.FULL_OPT:
            output = new_aggregate_info(summaries, config.included_types)
        else:
            output = transform_summaries(summaries, config.included_types)

        if config.include_top:
            add_tops(output)
        
        if config.beautify:
            beautify_summaries(output)
        
        for entity in unit.entities:
            unit.entities[entity] = Summary(output[entity[0].name[0]]["summary"], list(map(lambda term: SummaryTerm(term, output[entity[0].name[0]]["terms"][term]['occurrences'], output[entity[0].name[0]]["terms"][term].get('full_repr', None)), output[entity[0].name[0]]["terms"].keys())))


def summary_configurator(unit:Unit):
    datasetManager = DatasetManager()

    entities = list(map(lambda tuple: tuple[0].name[0], unit.entities.keys()))

    entries = set()
    first = True

    for entity in entities:
        result = datasetManager.get_summary_config(entity)

        if first:
            entries = set(result)
            first = False
        else:
            entries = entries.intersection(set(result))

    is_a = SummaryConfigEntry(PredicateType.HYPERNYM, "IS_A", datasetManager.default_depths[PredicateType.HYPERNYM])
    subclass_of = SummaryConfigEntry(PredicateType.HYPERNYM, "SUBCLASS_OF", datasetManager.default_depths[PredicateType.HYPERNYM])
    aggregable_predicates = [is_a, subclass_of]
    removed = False
    
    for predicate in aggregable_predicates:
        if predicate in entries:
            entries.discard(predicate)
            removed = True

    if removed:
        entries.add(SummaryConfigEntry(PredicateType.HYPERNYM, "IS_A", datasetManager.default_depths[PredicateType.HYPERNYM]))

    return SummaryConfig(list(entries), AncestorStrategy.ALL_NEAREST, SummaryStrategy.UP_TO_CONFIG, OptimizationStrategy.FULL_OPT, False, False)


def compute_common_by_pred_list(term, common_to_check, pred):
    level_ranges = {}
    bfs_list = [(term, term, 0)]
    common_found = []
    already_reached_term = {term: 0}
    level_ranges = {0: [-1, -1]}

    for level in range(1, 11):
        if len(common_found) == len(common_to_check):
            break

        previous_size = len(bfs_list)
        datasetManager = DatasetManager()

        if (level - 1) in level_ranges:
            if pred == "IS_A":
                synsets = datasetManager.get_reached_synsets_by_hypernym_batched(list(map(lambda element: element[0], bfs_list[level_ranges[level - 1][0] + 1:level_ranges[level - 1][1] + 2])))
            else:
                synsets = datasetManager.get_reached_synsets_by_relation_batched(list(map(lambda element: element[0], bfs_list[level_ranges[level - 1][0] + 1:level_ranges[level - 1][1] + 2])), pred)

            for synset in synsets:
                if synset[1] not in already_reached_term:
                    already_reached_term[synset[1]] = level + 1
                    bfs_list.append((synset[1], synset[0], level + 1))

                    if synset[1] in common_to_check:
                        common_found.append(synset[1])

            if len(bfs_list) > previous_size:
                level_ranges[level] = [level_ranges[level - 1][1] + 1, len(bfs_list) - 2]

    return common_found


def nearest_common_ancestor_batched(terms:list[str], pred:str, strategy:AncestorStrategy = AncestorStrategy.ALL_NEAREST, max_level:int = 10, summary_strategy:SummaryStrategy = SummaryStrategy.NO_SUMMARY, depth=1, prune_common=True):
    num_terms = len(terms)
    previous_size = 0
    bfs_list = list(map(lambda x: (x, x, x, 0), terms))

    # TODO! E' ARRIVATO IL MOMENTO DI GESTIRE CICLI COME SI DEVE!
    # NON E' CARINISSIMO VEDERE CHE UN NODO LO SI PUO' RAGGIUNGERE IN UN MODO SOLO!
    # SE UN NODO E' RAGGIUNGIBILE DA PIU' NODI NON VIENE PROPRIO CONSIDERATO POI NEL SUMMARY
    # E OKAY CHE MI INTERESSA SOLO LA DISTANZA MINIMA, MA SE QUESTA ADDIRITTURA E' LA STESSA
    # POTREI NON METTERE IN BFS_LIST LE RIPETIZIONI, COSI' DA NON FAR RICALCOLARE DOVE VA UNO STESSO TERMINE
    # MA L'INFORMAZIONE CHE QUESTO VIENE RAGGIUNTO DA PIU' NODI NON E' BELLO BUTTARLA
    # TUTTAVIA, NEL CASO IN CUI QUESTO NODO E' RAGGIUNGIBILE DAL NODO RAGGIUNTO VA MALISSIMO
    # PERCHE' SIGNIFICA CHE PRENDERE QUESTO ATOMO CHIUDE UN CICLO, ED IO NON LO VOGLIO MANCO PAGATO!
    # TODO! ATTENTO, POTREBBE ESSERCI UN CICLO CHE RIPORTA ALLA SORGENTE! MALE MALE MALE
    already_reached_term:dict[str, dict[str, int]] = {}
    stop = False
    # AGGIUNTA STRUTTURA CHE PER OGNI LIVELLO RIPORTA QUALI TERMINI DI PARTENZA SONO COMPARSI
    # SE A FINE LIVELLO NON SONO COMPARSI TUTTI I TERMINI, NEL MOMENTO IN CUI UN PUNTO DI INCONTRO NON E' STATO TROVATO
    # BEH, FERMATI COMUNQUE PERCHE' NON LO TROVERAI MAI, IN QUANTO PER ALMENO UNO DEI TERMINI NON CI SONO PIU' RELAZIONI DA
    # ESPLORARE
    # COMMENTO POSTUMO: STA ROBA E' ERRATA, UN CONTROLLO CHE PUO' AVER SENSO E' QUELLO DI VERIFICARE CHE ALMENO A LIVELLO 1 COMPAIONO TUTTI
    # IN QUANTO SIGNIFICA CHE POTENZIALMENTE SI PUO' TROVARE.
    # IN CASO CONTRARIO SAREBBE IMPOSSIBILE TROVARE UN COMMON ANCESTOR, IN QUANTO UN'ENTITA' NON HA PROPRIO UN ANCESTOR...
    involved_input_terms_level = {}
    # TODO! SEGNATI IN UNA STRUTTURA AUSILIARIA RIPETIZIONE A UNO STESSO TERMINE RAGGIUNTO ALLO STESSO LIVELLO E AGGIUNGILO A BFS_LIST
    # IN QUALCHE MODO ALLA FINE!
    # VALUTA DI TRASFORMARLO IN UN DICT PER OTTIMIZZARE LA RICERCA DOPO!
    nearest_common_ancestors = []

    for level in range(1, 100 if max_level == -1 else max_level + 1):
        if stop or (level > 1 and len(involved_input_terms_level) < num_terms) or previous_size == len(bfs_list):
            break

        datasetManager = DatasetManager()

        if pred == "IS_A":
            synsets = datasetManager.get_reached_synsets_by_hypernym_batched(list(set(map(lambda element: element[1], bfs_list[previous_size:]))))
        else:
            synsets = datasetManager.get_reached_synsets_by_relation_batched(list(set(map(lambda element: element[1], bfs_list[previous_size:]))), pred)

        previous_size = len(bfs_list)
        bfs_dict = {}

        for synset in synsets:
            # IF IT IS NOT ALREADY REACHED AT ALL OR FROM SOURCE element[0]:
            if synset[1] not in already_reached_term:
                already_reached_term[synset[1]] = {}

            origins = [synset[0]] if level == 1 else already_reached_term[synset[0]].keys()

            for origin in origins:
                if origin not in bfs_dict:
                    bfs_dict[origin] = []

                involved_input_terms_level[origin] = True

                if origin not in already_reached_term[synset[1]]:
                    # ADD TO ALREADY REACHED, DECLARE IN THE MAP THAT SOURCE element[0] REACHED TERM X IN STEPS level
                    already_reached_term[synset[1]][origin] = level

                    # IF SUCH TERM IS REACHED BY ALL SOURCES, I.E. len(already_reached_term[TERM]) == num_terms:
                    if len(already_reached_term[synset[1]].keys()) == num_terms:
                        # YEEEEEEEEEEEE! EVERYONE IS HAPPY, COMMON ANCESTOR!!!
                        nearest_common_ancestors.append((synset[1], already_reached_term[synset[1]]))
                        stop = True
                    
                    # APPEND TUPLE (element[0], TERM) TO bfs_list
                    bfs_dict[origin].append((origin, synset[1], synset[0], level))

        for term in terms:
            if term in bfs_dict:
                bfs_list.extend(bfs_dict[term])
    
    if strategy == AncestorStrategy.ALL_NEAREST and len(nearest_common_ancestors) > 0:
        min_depth = min(map(lambda ancestor: sum(ancestor[1].values()), nearest_common_ancestors))
        nearest_common_ancestors = list(filter(lambda ancestor: sum(ancestor[1].values()) == min_depth, nearest_common_ancestors))

    return nearest_common_ancestors