from eXsim.models import *
from neo4j import GraphDatabase
import re

def init_relation_ranking() -> dict[str, int]:
    rel_ranking = {}
    with open('utility_files/relation_ranking.csv', 'r') as f:
        lines = f.readlines()
        relation = ''
        rank = 0
        for line in lines:
            if line.__contains__('relation_name,c'):
                continue
            try:
                split = line.split(',')
                relation = str(split[0]).replace('"', '')
                rank = int(split[1])
                rel_ranking[relation] = rank
            except ValueError:
                print(f'Invalid line {relation},{rank}')

    return rel_ranking


def get_summary_config_query(tx, synset_id: str) -> list[SummaryConfigEntry]:
    result = tx.run("MATCH (:Synset {id: $id})-[r]->(:Synset) RETURN DISTINCT type(r) AS name, r.kind AS kind",
                    id=synset_id)

    entries = []

    for record in result:
        record_kind = PredicateType(record["kind"])
        if record_kind not in [PredicateType.MERONYM, PredicateType.HYPONYM]:
            entry = SummaryConfigEntry(record_kind, record["name"], DatasetManager().default_depths[record_kind])
            entries.append(entry)

    return entries


def remove_lucene_special_characters(lemma):
    lucene_special_characters = r'+-!(){}[]<>/^"~*?:\\'
    escaped_query = re.sub(r'([{}])'.format(re.escape(lucene_special_characters)), '', lemma)
    return escaped_query


def get_synsets_by_lemma_query(tx, lemma: str, page: int = 0) -> list[Term]:
    lemma = remove_lucene_special_characters(lemma)
    tokens = lemma.split(" ")

    if len(tokens) == 0:
        return []

    params = {}
    count_lemma = 0
    main_sense_str = ""
    synonyms_str = ""
    params_str = ""

    for token in tokens:
        if token == "":
            continue

        params[f"l{count_lemma}"] = token
        params_str += f"$l{count_lemma},"
        count_lemma += 1

        main_sense_str += "main_sense:%s* AND "
        synonyms_str += "synonyms:%s AND "

    main_sense_str = f"({main_sense_str[:-5]})^3"
    synonyms_str = f"({synonyms_str[:-5]})"
    params_str = f"[{(params_str + params_str)[:-1]}]"

    if page < 0:
        page = 0

    skip = page * 10

    result = tx.run(f"""CALL db.index.fulltext.queryNodes("mainSensesAndSynonyms", 
    apoc.text.format("{main_sense_str} OR {synonyms_str}", {params_str})) YIELD node,
                     score WITH node, score ORDER BY node.num_rel*score DESC, node.id 
                    RETURN node.id as id, node.main_sense as main_sense, node.synonyms as synonyms, 
                    node.description as description, node.image_url as image_url SKIP {skip} LIMIT 10"""
                    , parameters=params)

    entities = []

    for record in result:
        entities.append(Term(record["id"], babelnet_entity=BabelNetEntity(record["main_sense"], record["description"],
                                                                         record["synonyms"], record["image_url"])))

    return entities


def get_reached_synsets_query(tx, _id: str, rel: str):
    if DatasetManager().available_relations.get(rel, False):
        result = tx.run("MATCH (:Synset {id: $id})-[:`" + rel + "`]->(x:Synset) RETURN x.id as id", id=_id)

        synsets = []

        for record in result:
            synsets.append(record["id"])

        return synsets

    return []


def get_reached_synsets_query_batched(tx, terms: list, rel: str):
    if DatasetManager().available_relations.get(rel, False):
        result = tx.run(
            "UNWIND $terms AS term MATCH (:Synset {id: term})-[:`" + rel +
            "`]->(x:Synset) RETURN term as source, x.id as id",
            terms=terms)

        synsets = []

        for record in result:
            synsets.append((record["source"], record["id"]))

        return synsets

    return []


def get_reached_synsets_variable_query_batched(tx, terms: list, rel: str):
    if DatasetManager().available_relations.get(rel, False):
        result = tx.run(
            "UNWIND $terms AS term MATCH (:Synset {id: term})-[:`" + rel +
            "`*]->(x:Synset) WITH DISTINCT term as source, x.id as id RETURN source, id",
            terms=terms)

        synsets = {}
        for term in terms:
            synsets[term] = []

        for record in result:
            synsets[record["source"]].append(record["id"])

        return synsets

    return {}


def get_reached_synsets_hypernym_query(tx, _id: str):
    result = tx.run("MATCH (:Synset {id: $id})-[:IS_A]->(x:Synset) RETURN x.id as id", id=_id)

    synsets = []

    for record in result:
        synsets.append(record["id"])

    return synsets


def get_reached_synsets_hypernym_query_batched(tx, terms: list):
    result = tx.run(
        "UNWIND $terms AS term MATCH (:Synset {id: term})-[:IS_A]->(x:Synset) RETURN term as source, x.id as id",
        terms=terms)

    synsets = []

    for record in result:
        synsets.append((record["source"], record["id"]))

    return synsets


def get_subgraphs_query(tx, terms: list, rtype:PredicateType):
    if rtype not in [PredicateType.HYPERNYM, PredicateType.HOLONYM]:
        return []
    
    rel_type = "IS_A>" if rtype == PredicateType.HYPERNYM else "PART_OF>"
    rel_name = "rel = 'IS_A'" if rtype == PredicateType.HYPERNYM else "rel = 'PART_OF'"
    dummy_rel = "`IS_A`" if rtype == PredicateType.HYPERNYM else "`PART_OF`"
    match_entities = ""
    with_entities = ""
    merge_entities = ""

    params = {}

    for i in range(0, len(terms)):
        params["e"+str(i)] = terms[i]
        match_entities += "MATCH (e" + str(i) + ":Synset {id:$e" + str(i) + "}) "
        with_entities += "e" + str(i) + (", " if i < len(terms) - 1 else " ")
        merge_entities += "MERGE (dummy)-[:" + dummy_rel + "]->(e" + str(i) + ") "

    query = match_entities + "CREATE (dummy:Dummy) WITH dummy, " + with_entities + merge_entities + """ WITH dummy CALL apoc.path.subgraphAll(dummy, {uniqueness:'RELATIONSHIP_GLOBAL', relationshipFilter:'""" + rel_type + """'}) YIELD nodes, relationships UNWIND relationships as relation WITH dummy, startNode(relation).id as x, endNode(relation).id as y, type(relation) as rel WHERE x IS NOT null and """ + rel_name + """ DETACH DELETE dummy RETURN x, y; """

    result = tx.run(query,
        parameters=params)

    subgraph = []

    for record in result:
        subgraph.append((record["x"], record["y"]))

    return subgraph


def get_available_relations_query(tx):
    result = tx.run("CALL db.relationshipTypes()")

    relations = {}

    for record in result:
        relations[record["relationshipType"]] = True

    return relations


def get_synsets_by_cq_query(tx, query: str, params: dict):
    result = tx.run(query, parameters=params)

    entities = []

    for record in result:
        entities.append(Term(record["id"]))

    return entities


def get_synset_by_id_query(tx, _id) -> Term or None:
    result = tx.run("MATCH (node:Synset {id: $id}) RETURN node.id as id, node.main_sense as main_sense, " +
                    "node.synonyms as synonyms, node.description as description, node.image_url as image_url", id=_id)
    record = result.single()

    if record is None:
        return None

    return Term(record["id"],
                babelnet_entity=BabelNetEntity(record["main_sense"], record["description"], record["synonyms"],
                                              record["image_url"]))


def get_synsets_by_id_query_batched(tx, terms) -> list[Term] or None:
    result = tx.run("UNWIND $terms AS term MATCH (node:Synset {id: term}) RETURN node.id as id, node.main_sense as main_sense, " +
                    "node.synonyms as synonyms, node.description as description, node.image_url as image_url", terms=terms)
    
    entities = []

    for record in result:
        entities.append(Term(record["id"], babelnet_entity=BabelNetEntity(record["main_sense"], record["description"],
                                                                         record["synonyms"], record["image_url"])))

    return entities


def get_in_rank_by_id_query_batched(tx, terms) -> list[tuple[str, int, int]]:
    result = tx.run("UNWIND $terms AS term MATCH (node:Synset {id: term}) RETURN node.id as id, node.hyperInRank as hyperInRank, " +
                    "node.holonymInRank as holonymInRank", terms=terms)
    
    entities = []

    for record in result:
        entities.append((record["id"], record["hyperInRank"], record["holonymInRank"]))

    return entities


class SingletonMeta(type):
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            instance = super().__call__(*args, **kwargs)
            cls._instances[cls] = instance
        return cls._instances[cls]


class DatasetManager(metaclass=SingletonMeta):
    def __init__(self) -> None:
        self.default_depths = {PredicateType.HYPERNYM: 1, PredicateType.HOLONYM: 1, PredicateType.OTHER: 1}
        self.available_relations = {}
        self.relations_ranking = init_relation_ranking()
        
        self.driver = GraphDatabase.driver("**********", auth=("******", "********"))
        try:
            self.driver.verify_connectivity()
            self.load_available_relations()
        except Exception:
            self.driver.close()
            self.driver = None

    def load_available_relations(self):
        with self.driver.session() as session:
            self.available_relations = session.read_transaction(get_available_relations_query)

    def get_synsets_by_lemma(self, lemma: str, page: int) -> list[Term]:
        with self.driver.session() as session:
            return session.read_transaction(get_synsets_by_lemma_query, lemma, page)

    def get_reached_synsets_by_relation(self, current_id: str, relation: str):
        with self.driver.session() as session:
            return session.read_transaction(get_reached_synsets_query, current_id, relation)

    def get_reached_synsets_by_relation_batched(self, current_ids: list, relation: str):
        with self.driver.session() as session:
            return session.read_transaction(get_reached_synsets_query_batched, current_ids, relation)
        
    def get_reached_synsets_variable_by_relation_batched(self, current_ids: list, relation: str):
        with self.driver.session() as session:
            return session.read_transaction(get_reached_synsets_variable_query_batched, current_ids, relation)

    def get_reached_synsets_by_hypernym(self, current_id: str):
        with self.driver.session() as session:
            return session.read_transaction(get_reached_synsets_hypernym_query, current_id)
        
    def get_reached_synsets_by_hypernym_batched(self, current_ids: list):
        with self.driver.session() as session:
            return session.read_transaction(get_reached_synsets_hypernym_query_batched, current_ids)

    def get_summary_config(self, synset_id: str) -> list[SummaryConfigEntry]:
        with self.driver.session() as session:
            return session.read_transaction(get_summary_config_query, synset_id)

    def get_synsets_by_cq(self, query: str, params: dict):
        with self.driver.session() as session:
            return session.read_transaction(get_synsets_by_cq_query, query, params)

    def get_synset_by_id(self, _id: str) -> Term:
        with self.driver.session() as session:
            return session.read_transaction(get_synset_by_id_query, _id)
        
    def get_synsets_by_id_batched(self, terms: list[str]) -> list[Term]:
        with self.driver.session() as session:
            return session.read_transaction(get_synsets_by_id_query_batched, terms)
        
    def get_in_rank_by_id_batched(self, terms: list[str]) -> list[tuple[str, int, int]]:
        with self.driver.session() as session:
            return session.read_transaction(get_in_rank_by_id_query_batched, terms)
        
    def get_subgraphs(self, terms: list[str], rtype:PredicateType) -> list[tuple[str, str]]:
        with self.driver.session() as session:
            return session.write_transaction(get_subgraphs_query, terms, rtype)
