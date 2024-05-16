from datetime import datetime
from typing import Dict, List, Tuple, Type
import jsonpickle
from enum import Enum

from eXsim import db as my_db
from werkzeug.security import generate_password_hash, check_password_hash

from flask_security import UserMixin

from sqlalchemy import text


class JsonEnumHandler(jsonpickle.handlers.BaseHandler):
    def restore(self, obj):
        pass

    def flatten(self, obj: Enum, data):
        return obj.value


class TermType(Enum):
    CONSTANT = "CONSTANT"
    FREE_VARIABLE = "FREE_VARIABLE"
    BOUND_VARIABLE = "BOUND_VARIABLE"
    D_PRODUCT_TERM = "D_PRODUCT_TERM"
    AGGREGATED_TERM = "AGGREGATED_TERM"

    def __str__(self):
        return self.name


jsonpickle.handlers.registry.register(TermType, JsonEnumHandler)


class BabelNetEntity:

    def __init__(self, main_sense: str or None, description: str or None, synonyms: list[str], image_url: str or None):
        self.main_sense = main_sense
        self.description = description
        self.synonyms = synonyms
        self.image_url = image_url

    def __str__(self):
        return self.main_sense

    def __getstate__(self) -> object:
        state = self.__dict__.copy()
        if self.description is None:
            del state['description']
        if len(self.synonyms) == 0:
            del state['synonyms']
        if self.image_url is None:
            del state['image_url']
        return state

    def __repr__(self):
        return jsonpickle.encode(self, unpicklable=False)


class Term:

    def __init__(self, name, type: TermType = TermType.CONSTANT, babelnet_entity: BabelNetEntity or None = None):
        if isinstance(name, str):
            self.name = [name]
        else:
            self.name = name
        self.type = type
        self.babelNetEntity = babelnet_entity

    def __eq__(self, other):
        if isinstance(other, Term):
            if self.type == other.type:
                if self.type == TermType.AGGREGATED_TERM:
                    return set(self.name) == set(other.name)

                return self.name == other.name
        return False


    def __getstate__(self):
        state = self.__dict__.copy()
        if self.babelNetEntity is None:
            del state['babelNetEntity']
        return state

    def __repr__(self):
        return jsonpickle.encode(self, unpicklable=False)

    def __str__(self):
        if self.type == TermType.FREE_VARIABLE:
            return 'X'
        else:
            des = ''.join(map(lambda x: str(x) + "_", self.name))[:-1]
            if self.type == TermType.BOUND_VARIABLE:
                return f'Y_{des}'
            if self.type == TermType.AGGREGATED_TERM:
                return f'AGG_{des[:20]}'

            return des

    def my_str(self):

        if self.babelNetEntity is None:
            return str(self)

        if self.type == TermType.FREE_VARIABLE:
            return 'X'
        else:
            des = ''.join(map(lambda x: str(x) + "_", self.babelNetEntity.main_sense))[:-1]
            if self.type == TermType.BOUND_VARIABLE:
                return f'Y_{des}'

            return des

    def __hash__(self):
        return hash(str(self))

    def direct_product(self, other):
        if not isinstance(other, Term):
            raise Exception("The direct product is defined only for terms")
        new_list = self.name.copy()
        new_list.extend(other.name)
        return Term(new_list, TermType.D_PRODUCT_TERM)

    def transform(self, fr: list):

        if len(fr) >= 0 and not isinstance(fr[0], Term):
            raise Exception("You must provide a list of Terms")

        if (self.type != TermType.D_PRODUCT_TERM
                and self.type != TermType.CONSTANT
                and self.type != TermType.AGGREGATED_TERM):
            raise Exception("The transform is defined only for direct product terms or constants")

        if self.type == TermType.CONSTANT or self.type == TermType.AGGREGATED_TERM:
            return self

        if self in fr:
            self.type = TermType.FREE_VARIABLE

        elif len(set(self.name)) == 1:
            self.type = TermType.CONSTANT
            self.name = [self.name[0]]

        else:
            self.type = TermType.BOUND_VARIABLE

        return self


class PredicateType(Enum):
    OTHER = "OTHER"
    HOLONYM = "HOLONYM"
    HYPERNYM = "HYPERNYM"
    TOP = "TOP"
    MERONYM = "MERONYM"
    HYPONYM = "HYPONYM"

    def __str__(self):
        return self.name


jsonpickle.handlers.registry.register(PredicateType, JsonEnumHandler)


class Predicate:

    def __init__(self, _type: PredicateType, name: str, terms: Tuple[Term, ...], is_deriv: bool = False):

        for term in terms:
            if not isinstance(term, Term):
                raise Exception("All terms must be instances of the class Term")
        self.type = _type
        self.name = name
        self.terms = terms
        self.is_deriv = is_deriv

    def __eq__(self, other):
        if isinstance(other, Predicate):
            return self.name == other.name and self.type == other.type and self.terms == other.terms
        return False

    def __str__(self):
        tmp = ''.join(map(lambda x: str(x) + ", ", self.terms))[:-2]
        return f'{self.name}({tmp})'

    def __hash__(self):
        return hash(str(self))

    def my_str(self):
        tmp = ''.join(map(lambda x: x.my_str() + ", ", self.terms))[:-2]
        return f'{self.name}({tmp})'

    def __repr__(self):
        return jsonpickle.encode(self, unpicklable=False)

    def local_compare(self, other) -> int or None:
        if not isinstance(other, Predicate):
            raise Exception("The local compare is defined only for predicates")
        if self.name != other.name:
            return None
        if len(self.terms) != len(other.terms):
            return None
        ae = True
        ms = True
        ls = True
        for i in range(len(self.terms)):
            if self.terms[i] != other.terms[i]:
                ae = False
            if (self.terms[i].type == TermType.CONSTANT and other.terms[i].type == TermType.CONSTANT
                    and self.terms[i] != other.terms[i]):
                return None
            if self.terms[i].type == TermType.BOUND_VARIABLE and other.terms[i].type != TermType.BOUND_VARIABLE:
                ms = False
            if self.terms[i].type != TermType.BOUND_VARIABLE and other.terms[i].type == TermType.BOUND_VARIABLE:
                ls = False

        if ae:
            return 0

        if ms and not ls:
            return 1
        elif ls and not ms:
            return -1

        return None

    def __lt__(self, other):
        if not isinstance(other, Predicate):
            raise Exception("The < operator is defined only for predicates")
        bound_in_1 = 0
        k_in_1 = 0
        bound_in_2 = 0
        k_in_2 = 0
        for i in range(max(len(self.terms), len(other.terms))):
            if i < len(self.terms):
                if not isinstance(self.terms[i], Term):
                    raise Exception("Predicate terms must be of type Term")
                if self.terms[i].type == TermType.BOUND_VARIABLE:
                    bound_in_1 += 1
                elif self.terms[i].type == TermType.CONSTANT:
                    k_in_1 += 1
            if i < len(other.terms):
                if not isinstance(other.terms[i], Term):
                    raise Exception("Predicate terms must be of type Term")
                if other.terms[i].type == TermType.BOUND_VARIABLE:
                    bound_in_2 += 1
                elif other.terms[i].type == TermType.CONSTANT:
                    k_in_2 += 1

            if bound_in_1 != bound_in_2:
                return bound_in_1 < bound_in_2

            if k_in_1 != k_in_2:
                return k_in_2 > k_in_1

            if self.type != other.type:
                return self.type.value < other.type.value

        return self.name < other.name

    def direct_product(self, other, fr):

        if not isinstance(other, Predicate):
            raise Exception("The direct product is defined only for predicates")

        if self.name != other.name:
            raise Exception("The direct product is defined only for predicates with the same name")

        if len(self.terms) != len(other.terms):
            raise Exception("The direct product is defined only for predicates with the same arity")

        new_terms = []

        if not self.is_deriv:

            for i in range(0, len(self.terms)):
                t = self.terms[i].direct_product(other.terms[i])
                new_terms.append(t)

            return Predicate(self.type, self.name, tuple(new_terms))

        else:
            for i in range(0, len(self.terms)):
                if self.terms[i] == other.terms[i]:
                    new_terms.append(self.terms[i])
                else:
                    term_d_pr = self.terms[i].direct_product(other.terms[i])
                    if term_d_pr in fr:
                        new_terms.append(term_d_pr)
                    else:
                        return None
            return Predicate(self.type, self.name, tuple(new_terms), True)


class Formula:

    def __init__(self, predicates: List[Predicate]):
        self.predicates = predicates

    def __eq__(self, other):
        if isinstance(other, Formula):
            return self.predicates == other.predicates
        return False

    def __lt__(self, other):
        if not isinstance(other, Formula):
            raise Exception("The < operator is defined only for formulas")

        return len(self.predicates) < len(other.predicates)

    def __str__(self):
        return ''.join(map(lambda x: str(x) + ", ", self.predicates))[:-2]

    def my_str(self):
        return ''.join(map(lambda x: x.my_str() + ", ", self.predicates))[:-2]

    def __repr__(self):
        return jsonpickle.encode(self, unpicklable=False)

    def transform(self, free_variables: List[Term]):

        for predicate in self.predicates:
            for term in predicate.terms:
                term.transform(free_variables)
        return self


    def copy(self):
        return Formula(self.predicates)




class AncestorStrategy(Enum):
    ALL_NEAREST = "ALL_NEAREST"
    UP_TO_LEVEL = "UP_TO_LEVEL"

    def __str__(self):
        return self.name


jsonpickle.handlers.registry.register(AncestorStrategy, JsonEnumHandler)


class SummaryStrategy(Enum):
    NO_SUMMARY = "NO_SUMMARY"
    UP_TO_CONFIG = "UP_TO_CONFIG"
    UP_TO_FUNC_STRATEGY = "UP_TO_FUNC_STRATEGY"

    def __str__(self):
        return self.name


jsonpickle.handlers.registry.register(SummaryStrategy, JsonEnumHandler)


class OptimizationStrategy(Enum):
    NO_OPT = "NO_OPT"
    PRUNE_COMMON_INFO = "PRUNE_COMMON_INFO"
    FULL_OPT = "FULL_OPT"

    def __str__(self):
        return self.name


jsonpickle.handlers.registry.register(OptimizationStrategy, JsonEnumHandler)


class SummaryApproach(Enum):
    SINGLE_ENTITY = "SINGLE_ENTITY"
    MULTI_ENTITY = "MULTI_ENTITY"

    def __str__(self):
        return self.name


jsonpickle.handlers.registry.register(SummaryApproach, JsonEnumHandler)


class SummaryConfigEntry:

    def __init__(self, predicate_type: PredicateType, predicate_name: str, depth: int):
        self.predicate_type = predicate_type
        self.predicate_name = predicate_name
        self.depth = depth

    def __eq__(self, other):
        if isinstance(other, SummaryConfigEntry):
            return self.predicate_name == other.predicate_name
        return False

    def __hash__(self):
        return hash(self.predicate_name)

    def __str__(self):
        return f'{self.predicate_name}({self.predicate_type}) --> {self.depth}'

    def __repr__(self):
        return jsonpickle.encode(self, unpicklable=False)


class SummaryConfig:
    def __init__(self, included_types: list[SummaryConfigEntry], ancestor_strategy: AncestorStrategy,
                 summary_strategy: SummaryStrategy, optimization_strategy: OptimizationStrategy, include_top: bool,
                 beautify: bool):
        self.included_types = included_types
        self.ancestor_strategy = ancestor_strategy
        self.summary_strategy = summary_strategy
        self.optimization_strategy = optimization_strategy
        self.include_top = include_top
        self.beautify = beautify

    def __str__(self):
        return ''.join(map(lambda x: str(x) + ", ", self.included_types))[:-2]

    def __repr__(self):
        return jsonpickle.encode(self, unpicklable=False)


class SummaryTerm:
    def __init__(self, id: str or None, occurrences: int or None, full_repr: Term or None):
        self.id = id
        self.occurrences = occurrences
        self.full_repr = full_repr

    def __str__(self):
        return f'{self.id}: {self.occurrences}'

    def __repr__(self):
        return jsonpickle.encode(self, unpicklable=False)

    def __getstate__(self):
        state = self.__dict__.copy()
        if self.full_repr is None:
            del state['full_repr']
        return state


class Summary:
    def __init__(self, atoms: Formula, terms: list[SummaryTerm]):
        self.atoms = atoms
        self.terms = terms

    def __str__(self):
        return str(self.atoms)

    def __repr__(self):
        return jsonpickle.encode(self, unpicklable=False)

    def __lt__(self, other):
        if not isinstance(other, Summary):
            raise Exception("The < operator is defined only for summaries")
        return self.atoms < other.atoms


class Unit:
    entities = dict()
    characterization = None
    expansion = None  

    def __init__(self):
        self.entities: Dict[Tuple[Term, ...], Summary or None] = {}
        self.characterization: Formula or None = None
        self.expansion = None  

    def __str__(self):
        return ''.join(map(lambda x: str(x) + "_", self.entities.keys()))[:-1]

    def __repr__(self):
        ent = '['
        for e in self.entities.keys():
            tmp = f'[{"".join(map(lambda x: repr(x) + ", ", e))[:-2]}]'
            _sum = f', \"summary\" : {repr(self.entities[e])}' if self.entities[e] is not None else ''
            ent += f'{{\"entity\" :{tmp}{_sum}}},'
        if len(ent) > 1:
            ent = ent[:-1]
        ent = ent + ']'
        characterization = None
        exp = None
        if self.characterization is not None:
            characterization = repr(self.characterization)

        if self.expansion is not None:
            exp = repr(self.expansion)

        string = "{" + f'\"entities\" : {ent}'
        if characterization is not None:
            string += f', \"characterization\" : {characterization}'
        if exp is not None:
            string += f', \"expansion\" : {exp}'
        string += '}'

        return string

    def add_entity(self, entity: Tuple[Term, ...]):
        for e in entity:
            if not isinstance(e, Term):
                raise Exception("All entities must be instances of the class Term")

        self.entities[entity] = None
        self.characterization = None

    def add_entities(self, entities: list[Tuple[Term, ...]]):
        for entity in entities:
            self.add_entity(entity)

    def concat(self, other: Type["Unit"]):
        for entity in other.entities.keys():
            self.add_entity(entity)
            self.entities[entity] = other.entities[entity]
        self.characterization = None

    def to_sorted_list(self):
        return sorted(self.entities.items(), key=lambda x: x[1])


class UnitRelation(Enum):
    SIM = "SIM"
    INC = "INC"
    PREC = "PREC"
    SUCC = "SUCC"

    def __str__(self):
        return self.name

jsonpickle.handlers.registry.register(UnitRelation, JsonEnumHandler)


class QueryResult:
    def __init__(self, results: List[Term]):
        self.results = results

    def __eq__(self, other):
        if isinstance(other, QueryResult):
            return self.results == other.results
        return False

    def __str__(self):
        return ''.join(map(lambda x: str(x) + ", ", self.results))[:-2]

    def __repr__(self):
        return jsonpickle.encode(self, unpicklable=False)


class BooleanAnswer:
    def __init__(self, answer: bool):
        self.answer = answer

    def __str__(self):
        return self.answer

    def __repr__(self):
        return jsonpickle.encode(self, unpicklable=False)


def json_decode(json) -> dict:
    if isinstance(json, str):
        return jsonpickle.decode(json)

    return json


def check_keys(json: dict, keys: list[str]) -> bool:
    return all([item in json.keys() for item in keys])


def json_to_babel_net_entity(json) -> BabelNetEntity or None:
    if json is None:
        return None

    json = json_decode(json)

    if check_keys(json, ["main_sense"]):
        return BabelNetEntity(json["main_sense"], json.get("description", None), json.get("synonyms", []),
                              json.get("image_url", None))

    return None


def json_to_term(json) -> Term or None:
    if json is None:
        return None

    json = json_decode(json)

    if check_keys(json, ["name"]):
        return Term(json["name"], TermType(json.get("type", TermType.CONSTANT)),
                    json_to_babel_net_entity(json.get("babelNetEntity", None)))

    return None


def json_to_predicate(json) -> Predicate or None:
    if json is None:
        return None

    json = json_decode(json)

    if check_keys(json, ["type", "name", "terms"]):
        return Predicate(PredicateType(json["type"]),
                         json["name"],
                         tuple(map(lambda x: json_to_term(x), json["terms"])),
                         json.get("is_deriv", False))

    return None


def json_to_formula(json) -> Formula or None:
    if json is None:
        return None

    json = json_decode(json)

    if check_keys(json, ["predicates"]):
        return Formula(list(map(lambda x: json_to_predicate(x), json["predicates"])))

    return None


def json_to_summary_config_entry(json) -> SummaryConfigEntry or None:
    if json is None:
        return None

    json = json_decode(json)

    if check_keys(json, ["predicate_type", "predicate_name", "depth"]):
        return SummaryConfigEntry(PredicateType(json["predicate_type"]), json["predicate_name"], json["depth"])

    return None


def json_to_summary_config(json) -> SummaryConfig or None:
    if json is None:
        return None

    json = json_decode(json)

    if check_keys(json,
                  ["included_types", "ancestor_strategy", "summary_strategy",
                   "optimization_strategy", "include_top", "beautify"]):
        return SummaryConfig(list(map(lambda x: json_to_summary_config_entry(x), json["included_types"])),
                             AncestorStrategy(json["ancestor_strategy"]), SummaryStrategy(json["summary_strategy"]),
                             OptimizationStrategy(json["optimization_strategy"]), json["include_top"], json["beautify"])

    return None


def json_to_summary_term(json) -> SummaryTerm or None:
    if json is None:
        return None

    json = json_decode(json)

    if check_keys(json, ['id', 'occurrences']):
        return SummaryTerm(json['id'], json['occurrences'], json.get('full_repr', None))

    return None


def json_to_summary(json) -> Summary or None:
    if json is None:
        return None

    json = json_decode(json)

    if check_keys(json, ["atoms", "terms"]):
        return Summary(json_to_formula(json["atoms"]), list(map(lambda x: json_to_summary_term(x), json["terms"])))

    return None


def json_to_unit(json) -> Unit or None:
    if json is None:
        return None

    json = json_decode(json)

    if check_keys(json, ["entities"]):
        u: Unit = Unit()
        for entry in json["entities"]:
            if not check_keys(entry, ["entity"]):
                return None

            entity: tuple = tuple(map(lambda x: json_to_term(x), entry["entity"]))
            u.add_entity(entity)
            u.entities[entity] = json_to_summary(entry.get("summary", None))

        u.characterization = json_to_formula(json.get("characterization", None))
        return u

    return None


class GraphNode:
    pass


class ExpansionGraph:
    base_unit: Unit
    super_units: list[Unit]
    graph: GraphNode

    def __init__(self, _base_unit, _super_units):
        self.base_unit = _base_unit
        self.super_units = _super_units


class User(my_db.Model, UserMixin):
    __tablename__ = 'user'
    id = my_db.Column(my_db.Integer,
                      primary_key=True,
                      autoincrement=True)
    created_at = my_db.Column(my_db.DateTime,
                              default=datetime.utcnow)
    username = my_db.Column(my_db.String())
    password = my_db.Column(my_db.String())

    def __init__(self, username, password):
        self.username = username
        self.password = generate_password_hash(password, method='scrypt:32768:8:1')

    def __repr__(self):
        return f'{{"username": "{self.username}"}}'

    def __str__(self):
        return self.__repr__()

    def save_to_db(self):
        my_db.session.add(self)
        my_db.session.commit()

    def find_user_by_username(self):
        x = self.query.filter_by(username=self.username).first()
        if x is not None:
            self.id = x.id
            self.username = x.username
            self.created_at = x.created_at
            self.password = x.password
            return True
        return False

    def check_password(self, password):

        if self.password is None:
            return False

        if not self.find_user_by_username():
            return False

        if not check_password_hash(self.password, password):
            return False

        return True



lowest_rank_query = ("SELECT RELATION_NAME FROM RELATION_RANKING WHERE " +
                     "UPPER(RELATION_NAME) IN ({0}) ORDER BY RANK LIMIT 1")


def lowest_rank(pred_names: list[str]):
    f_string = ''
    for p in pred_names:
        p = p.replace('"', '')
        p = p.replace('DERIV#', '')
        f_string += f'"{p}",'
    f_string = f_string[:-1]
    query_instance = lowest_rank_query.format(f_string)
    result = my_db.engine.connect().execute(text(query_instance)).first().tuple()[0]
    return result


def validate_password(password: str) -> bool:
    return len(password) > 0
