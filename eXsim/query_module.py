from eXsim.models import *
from eXsim.babelnet import DatasetManager


def build_match_clauses(query: Formula, params: dict[str, str], exclude_both_constants: bool = True,
                        is_first_free_var: bool = True, id_free_var: str = None):

    constants_detected = len(params)
    free_var = None
    bound_vars = {}
    last_bound = 0
    query_constants = ""
    query_str = ""
    query_deriv = ""

    if len(query.predicates) == 1 and query.predicates[0].type == PredicateType.TOP:
        if query.predicates[0].terms[0].type == TermType.FREE_VARIABLE:
            free_var = query.predicates[0].terms[0].name
            if id_free_var is None:
                query_str += "MATCH (n:Synset)"
            else:
                query_str += 'MATCH (n:Synset {id: "' + id_free_var + '"})'
        else:
            return None
    else:
        for predicate in query.predicates:
            if predicate.type != PredicateType.TOP:
                if DatasetManager().available_relations.get(predicate.name, False) or predicate.name == "HYPER":
                    if not isinstance(predicate, Predicate):
                        return None
                    
                    nodes: list[Term] = [predicate.terms[0], predicate.terms[1]]
                    query_components = []
                    both_constants = nodes[0].type == TermType.CONSTANT and nodes[1].type == TermType.CONSTANT
                    if not exclude_both_constants or not both_constants:
                        constant_found = False
                        for node in nodes:
                            if node.type == TermType.FREE_VARIABLE:
                                if free_var is not None and free_var != node.name:
                                    return None
                                
                                if free_var is None and is_first_free_var:
                                    if id_free_var is None:
                                        query_components.append("n:Synset")
                                    else:
                                        query_components.append('n:Synset {id: "' + id_free_var + '"}')
                                else:
                                    query_components.append("n")

                                free_var = node.name
                            elif node.type == TermType.BOUND_VARIABLE:
                                bound_id = bound_vars.get(str(node.name), -1)
                                if bound_id < 0:
                                    bound_id = last_bound
                                    bound_vars[str(node.name)] = bound_id
                                    last_bound += 1
                                    query_components.append("y" + str(bound_id) + ":Synset")
                                else:
                                    query_components.append("y" + str(bound_id))
                            elif node.type == TermType.CONSTANT:
                                constant_found = True
                                params["c" + str(constants_detected)] = node.name[0]
                                query_components.append(":Synset {id:$c" + str(constants_detected) + "}")
                                constants_detected += 1
                            else:
                                return None

                        modifier = ""
                        name = predicate.name
                        if predicate.is_deriv:
                            modifier = "*1..10"
                        
                        if name == "HYPER":
                            name = "`IS_A`|`SUBCLASS_OF`"
                        else:
                            name = f"`{name}`"

                        if constant_found:
                            if predicate.is_deriv:
                                query_deriv += " MATCH (" + query_components[0] + ")-[:" + name + modifier + "]->(" + query_components[1] + ")"
                            else:
                                query_constants += " MATCH (" + query_components[0] + ")-[:" + name + modifier + "]->(" + query_components[1] + ")"
                        else:
                            query_str += " MATCH (" + query_components[0] + ")-[:" + name + modifier + "]->(" + query_components[1] + ")"     
                else:
                    return None
      
    return query_constants + query_deriv + query_str




def build_match_clauses_new(query: Formula, params: dict[str, str],
                        is_first_free_var: bool = True, id_free_var: str = None):
    
    constants_detected = len(params)
    free_var = "(n" + (":Synset" if is_first_free_var else "") + ")"
    last_bound = 0


    query_terms = {"constants": {}, "only_check_bound_vars": {}, "join_bound_vars": {}, "deriv_constants": {}}

    for predicate in query.predicates:
        if predicate.type != PredicateType.TOP:
                if DatasetManager().available_relations.get(predicate.name, False):
                    if not isinstance(predicate, Predicate):
                        return None
                    
                    term = predicate.terms[1]

                    if term.type == TermType.CONSTANT or term.type == TermType.AGGREGATED_TERM:
                        for name in term.name:
                            if predicate.name == "IS_A" or predicate.name == "PART_OF":
                                if name not in query_terms["deriv_constants"]:
                                    query_terms["deriv_constants"][name] = []
                                query_terms["deriv_constants"][name].append(predicate.name)
                            else:
                                if name not in query_terms["constants"]:
                                    query_terms["constants"][name] = []
                                query_terms["constants"][name].append(predicate.name)
                    elif term.type == TermType.BOUND_VARIABLE:
                        name = ",".join(term.name)
                        if name not in query_terms["only_check_bound_vars"]:
                            query_terms["only_check_bound_vars"][name] = predicate.name
                        else:
                            if name not in query_terms["join_bound_vars"]:
                                query_terms["join_bound_vars"][name] = [query_terms["only_check_bound_vars"][name], predicate.name]
                                del query_terms["only_check_bound_vars"][name]
                            else:
                                query_terms["join_bound_vars"][name].append(predicate.name)

    only_to_check_predicates = []
    for name in query_terms["only_check_bound_vars"]:
        only_to_check_predicates.append(query_terms["only_check_bound_vars"][name])


    selected_term = None
    constant_clauses = ""
    join_bound_vars_clauses = ""
    only_to_check_predicates_clauses = ""
    deriv_constants_clauses = ""
    sorted_deriv_constants = []

    if id_free_var is not None:
        params["tid"] = id_free_var
        selected_term = "MATCH (n:Synset {id: $tid})"
        dataset_manager = DatasetManager()
        deriv_rankings = dataset_manager.get_in_rank_by_id_batched(list(query_terms["deriv_constants"]))

        for rank_tuple in deriv_rankings:
            for predicate_name in query_terms["deriv_constants"][rank_tuple[0]]:
                if predicate_name == "IS_A":
                    rank = rank_tuple[1]
                else:
                    rank = rank_tuple[2]
                
                sorted_deriv_constants.append((predicate_name, rank, rank_tuple[0]))

    
    if selected_term is None:
        dataset_manager = DatasetManager()
        
        is_predicate = False
        minRank = None

        deriv_rankings = dataset_manager.get_in_rank_by_id_batched(list(query_terms["deriv_constants"]))

        for rank_tuple in deriv_rankings:
            for predicate_name in query_terms["deriv_constants"][rank_tuple[0]]:
                if predicate_name == "IS_A":
                    rank = rank_tuple[1]
                else:
                    rank = rank_tuple[2]
                
                sorted_deriv_constants.append((predicate_name, rank, rank_tuple[0]))

                if minRank is None or minRank[1] > rank:
                    minRank = (predicate_name, rank, rank_tuple[0])

        if minRank is None or minRank[1] > 1000000:
            if len(query_terms["constants"]) == 0 and len(query_terms["join_bound_vars"]) == 0:
                for predicate_name in only_to_check_predicates:
                    rank = dataset_manager.relations_ranking[predicate_name]

                    if minRank is None or minRank[1] > rank:
                        minRank = (predicate_name, rank)
                        is_predicate = True
            else:
                minRank = None
        
        if minRank is not None:
            if is_predicate:
                if minRank[0] == "IS_A" or minRank[0] == "PART_OF":
                    pred_name = f"`{minRank[0]}`*"
                else:
                    pred_name = f"`{minRank[0]}`"
                selected_term = "MATCH " + free_var + "-[:" + pred_name + "]->(:Synset)"
                only_to_check_predicates.remove(minRank[0])
            else:
                pred_name = f"`{minRank[0]}`*"
                term_node = ("c" + str(constants_detected))
                params[term_node] = minRank[2]
                constants_detected += 1
                selected_term = "MATCH " + free_var + "-[:" + pred_name + "]->(:Synset {id:$" + term_node + "}) WITH DISTINCT n"
                query_terms["deriv_constants"][minRank[2]].remove(minRank[0])
                if len(query_terms["deriv_constants"][minRank[2]]) == 0:
                    del query_terms["deriv_constants"][minRank[2]]

    for term_name in query_terms["constants"]:
        params["c" + str(constants_detected)] = term_name
        term_node = ":Synset {id:$c" + str(constants_detected) + "}"
        constants_detected += 1

        for predicate_name in query_terms["constants"][term_name]:
            if predicate_name == "IS_A" or predicate_name == "PART_OF":
                pred_name = f"`{predicate_name}`*"
            else:
                pred_name = f"`{predicate_name}`"

            if selected_term is None:
                selected_term = "MATCH " + free_var + "-[:" + pred_name + "]->(" + term_node + ")"
            else:
                constant_clauses += " MATCH (n)" + "-[:" + pred_name + "]->(" + term_node + ")"

    for term_name in query_terms["join_bound_vars"]:
        bound_var_map = "y" + str(last_bound)
        last_bound += 1
        first = True

        for predicate_name in query_terms["join_bound_vars"][term_name]:
            if predicate_name == "IS_A" or predicate_name == "PART_OF":
                pred_name = f"`{predicate_name}`*"
            else:
                pred_name = f"`{predicate_name}`"
            
            term_node = bound_var_map + (":Synset" if first else "")
            if selected_term is None:
                selected_term = "MATCH " + free_var + "-[:" + pred_name + "]->(" + term_node + ")"
            else:
                join_bound_vars_clauses += (" WITH DISTINCT n" if first else "") + " MATCH (n)" + "-[:" + pred_name + "]->(" + term_node + ")"
            first = False


    if len(only_to_check_predicates) > 0:
        predicates_string = "|".join(list(map(lambda pred: f"{pred}>", only_to_check_predicates)))
        only_to_check_predicates_clauses += ' WITH DISTINCT n, apoc.node.relationships.exist(n, "' + predicates_string + '") as map WHERE all(x in [k IN KEYS(map) | map[k]] where x)'

    sorted_deriv_constants.sort(key=lambda r: r[1])

    first_deriv = True
    found_deriv = 0
    deriv_aggr = {}
    batch_size = 16

    for deriv_const in sorted_deriv_constants:
        term_name = deriv_const[2]
        predicate_name = deriv_const[0]
        
        if first_deriv:
            deriv_constants_clauses += " WITH DISTINCT n"
            first_deriv = False
    
        term_node = ("c" + str(constants_detected))
        params[term_node] = term_name
        constants_detected += 1
        found_deriv += 1

        if found_deriv <= 10:
            deriv_constants_clauses += " WITH n"
            
            pred_name = f"`{predicate_name}`*"

            deriv_constants_clauses += " WHERE n.id <> $" + term_node + " MATCH shortestPath((n)-[:" + pred_name + "]->(:Synset {id:$" + term_node + "}))"
        else:
            pred_name = f"`{predicate_name}`>"

            if pred_name not in deriv_aggr:
                deriv_aggr[pred_name] = {}
                deriv_aggr[pred_name]["actual_batch"] = 0
                deriv_aggr[pred_name]["batches"] = [{"clause": "", "endNodes": []}]
            
            deriv_aggr[pred_name]["batches"][deriv_aggr[pred_name]["actual_batch"]]["clause"] += " MATCH(" + term_node + ":Synset {id:$" + term_node + "})"
            deriv_aggr[pred_name]["batches"][deriv_aggr[pred_name]["actual_batch"]]["endNodes"].append(term_node)

            if len(deriv_aggr[pred_name]["batches"][deriv_aggr[pred_name]["actual_batch"]]["endNodes"]) == batch_size:
                deriv_aggr[pred_name]["actual_batch"] += 1
                deriv_aggr[pred_name]["batches"].append({"clause": "", "endNodes": []})

    for pred_name in deriv_aggr:
        for batch in deriv_aggr[pred_name]["batches"]:
            deriv_constants_clauses += batch["clause"] + " CALL apoc.path.subgraphNodes(n, {endNodes:[" + ",".join(batch["endNodes"]) + "], labelFilter:'+Synset', relationshipFilter:'" + pred_name + "'}) YIELD node WITH n, count(node) as nc WHERE nc = " + str(len(batch["endNodes"]))

    return selected_term + constant_clauses + join_bound_vars_clauses + only_to_check_predicates_clauses + deriv_constants_clauses



def execute_query(query: Formula, exclude_both_constants: bool, page: int = 0):
    params = {}
    query_str = build_match_clauses_new(query, params)

    if query_str is None:
        return []

    if page < 0:
        page = 0
    
    skip = page * 20

    query_str += f" WITH DISTINCT n.id as id RETURN id SKIP {skip} LIMIT 20"
    return QueryResult(DatasetManager().get_synsets_by_cq(query_str, params))
   

def is_term_in_output(term: Term, query: Formula):
    params = {}
    query_str = build_match_clauses_new(query, params, id_free_var=term.name[0])

    if query_str is None:
        return False

    query_str += " WITH DISTINCT n.id as id RETURN id"
    
    if len(DatasetManager().get_synsets_by_cq(query_str, params)) > 0:
        return True
    
    return False


def is_subset(query1: Formula, query2: Formula):
    diff = compute_diff_output(query1, query2, 0)

    if len(diff.results) == 0:
        return True
    
    return False


def compute_diff_output(query1: Formula, query2: Formula, page: int = 0):
    params = {}
    query1_str = build_match_clauses_new(query1, params)
    query2_str = build_match_clauses_new(query2, params, is_first_free_var=False)

    if query1_str is None or query2_str is None:
        return []

    query_str = query1_str + " WITH DISTINCT n WHERE NOT EXISTS {" + query2_str + "}"

    if page < 0:
        page = 0
    
    skip = page * 20

    query_str += f" WITH DISTINCT n.id as id RETURN id SKIP {skip} LIMIT 20"

    return QueryResult(DatasetManager().get_synsets_by_cq(query_str, params))