import os
import time

from eXsim import app
from flask_restx import fields, Resource, Api
from flask import request

from flask_jwt_extended import create_access_token
from flask_jwt_extended import jwt_required
from flask_jwt_extended import JWTManager

from eXsim.characterization import characterize, compare_units
from eXsim.expansion import expand, relax_transitive, relax_transitive_v2
from eXsim.models import *

from eXsim.babelnet import DatasetManager
import eXsim.summary_module as sm
import eXsim.query_module as qm

api = Api(app, doc='/api/docs', title='eXsim API', version='0.1', description='eXsim API')
app.config['JWT_SECRET_KEY'] = os.environ.get('JWT_SECRET_KEY')
jwt = JWTManager(app)

babelnet_entity_model = api.model('BabelNetEntity', {
    'main_sense': fields.String(required=True, description='Main Sense'),
    'description': fields.String(required=False, description='A brief description of the entity'),
    'synonyms': fields.List(fields.String, required=False, description='Other senses linked to the entity'),
    'image_url': fields.String(required=False, description='The URL of a representative image'),
})

term_model = api.model('Term', {
    'name': fields.List(fields.String, required=True, description='Term name, i.e. its string representation',
                        min_items=1),
    'type': fields.String(required=True, description='Indicates whether the term is a constant or a variable',
                          enum=[str(t) for t in TermType]),
    'babelNetEntity': fields.Nested(babelnet_entity_model, required=False,
                                    description='BabelNet entity associated to the term (if any)')
})

predicate_model = api.model('Predicate', {
    'type': fields.String(required=True, description='Indicates the type of the relation',
                          enum=[str(t) for t in PredicateType]),
    'name': fields.String(required=True, description='The name of the relation'),
    'terms': fields.List(fields.Nested(term_model), required=True, description='The terms involved in it'),
    'is_deriv': fields.Boolean(required=False,
                               description='Such field is true if the atom represents a nearest common ancestor')
})

formula_model = api.model('Formula', {
    'predicates': fields.List(fields.Nested(predicate_model), required=True, description='Atoms of the formula')
})

summary_config_entry_model = api.model('SummaryConfigEntry', {
    'predicate_type': fields.String(required=True, description='Indicates the type of the relation',
                                    enum=[str(t) for t in PredicateType]),
    'predicate_name': fields.String(required=True, description='The name of the relation'),
    'depth': fields.Integer(required=True, description='The desired depth for the summary')
})

summary_config_model = api.model('SummaryConfig', {
    'included_types': fields.List(fields.Nested(summary_config_entry_model), required=True,
                                  description='List of relations to be included in the summary'),
    'ancestor_strategy': fields.String(required=True,
                                       description="The behavior of nearest common ancestor computation",
                                       enum=[str(t) for t in AncestorStrategy]),
    'summary_strategy': fields.String(required=True,
                                      description=("The amount of information to include in the summary from " +
                                                   "nearest common ancestor computation"),
                                      enum=[str(t) for t in SummaryStrategy]),
    'optimization_strategy': fields.String(required=True,
                                           description="The optimizations that summary selector has to perform",
                                           enum=[str(t) for t in OptimizationStrategy]),
    'include_top': fields.Boolean(required=True,
                                  description="Indicates if top atoms must be explicitly included in the summary"),
    'beautify': fields.Boolean(required=True,
                               description="Indicates if each term in the summary must be fully represented")
})

summary_term_model = api.model('SummaryTerm', {
    'id': fields.String(required=True, description='The synset id'),
    'occurrences': fields.Integer(required=True, description='Number of times a term occurs in the summary'),
    'full_repr': fields.Nested(term_model, required=False, description="The full representation of the term")
})

summary_model = api.model('Summary', {
    'atoms': fields.Nested(formula_model, required=True, description="Summary atoms"),
    'terms': fields.List(fields.Nested(summary_term_model), required=True,
                         description="All the terms occurring in the summary")
})

entity_summary_model = api.model('EntitySummary', {
    'entity': fields.List(fields.Nested(term_model), required=True, description='The term'),
    'summary': fields.Nested(summary_model, required=False, description='The summary of the term')
})

unit_model = api.model('Unit', {
    'entities': fields.List(fields.Nested(entity_summary_model), required=True,
                            description='List of entities in the unit'),
    'characterization': fields.Nested(formula_model, required=False, description='Characterization of the unit'),
    'expansion': fields.List(fields.Nested(formula_model), required=False, description='Expansion of the unit')
})

summary_request_model = api.model('SummaryRequest', {
    'unit': fields.Nested(unit_model, required=True, description='The entities to be summarized'),
    'summary_config': fields.Nested(summary_config_model, required=True, description='The summary configuration')
})

list_of_units_model = api.model('ListOfUnits', {
    'units': fields.List(fields.Nested(unit_model), required=True, description='List of units')
})

query_model = api.model('Query', {
    'query': fields.Nested(formula_model, required=True, description='Query to evaluate'),
    'exclude_both_constants': fields.Boolean(required=False,
                                             description='Exclude from evaluation atoms with both terms constant'),
    'page': fields.Integer(required=False, description='Page of results')
})

query_results_model = api.model('QueryResults', {
    'results': fields.List(fields.Nested(term_model), required=True, description='List of results')
})

query_comparison_model = api.model('QueryComparison', {
    'query1': fields.Nested(formula_model, required=True, description='First query'),
    'query2': fields.Nested(formula_model, required=True, description='Second query'),
    'page': fields.Integer(required=False, description='Page of results')
})

term_in_query_model = api.model('TermQuery', {
    'term': fields.Nested(term_model, required=True, description='The term that has to occur in query results'),
    'query': fields.Nested(formula_model, required=True, description='Query to evaluate')
})

boolean_answer_model = api.model('BooleanAnswer', {
    'answer': fields.Boolean(required=True, description='The outcome of the required check')
})

check_superclasses_model = api.model('CheckSuperclasses', {
    'term': fields.String(required=True, description='The synset id'),
    'superclasses': fields.List(fields.String(), required=True,
                                description='The list of synset id representing the desired superclasses of term'),
    'predicate': fields.String(required=True, description='The predicate name')
})

superclasses_model = api.model('Superclasses', {
    'superclasses': fields.List(fields.String(), required=True, description='The list of found superclasses')
})

nearest_common_ancestors_request_model = api.model('NearestCommonAncestorsRequest', {
    'terms': fields.List(fields.String(), required=True, description='The list of synset id'),
    'predicate': fields.String(required=True, description='The predicate name to consider')
})

nearest_common_ancestors_model = api.model('NearestCommonAncestors', {
    'ancestors': fields.List(fields.String(), required=True, description='The list of found nearest common ancestors')
})

unit_relation_model = api.model('UnitRelation', {
    'relation': fields.String(required=True, description='The relation between the two units',
                              enum=[str(t) for t in UnitRelation])
})

user_model = api.model('User', {
    'id': fields.Integer(required=False),
    'username': fields.String(required=True, description='The username of the user'),
    'password': fields.String(required=False, description=''),
    'created_at': fields.String(required=False, description=''),
})

atom_list_model = api.model('AtomList', {
    'atoms': fields.List(fields.Nested(predicate_model), required=True)
})
expansion_levels_model = api.model('ExpansionLevels', {'levels': fields.List(fields.Nested(formula_model))})

sizes_model = api.model('Sizes', {
    'shown': fields.Integer(required=True, description=''),
    'kern': fields.Integer(required=True, description=''),
    'core': fields.Integer(required=True, description='')
})


@api.route('/prova')
class Hello(Resource):

    @api.response(200, 'Success', )
    def get(self):
        x = ['ISA', 'PART_OF', 'NAMED_AFTER']
        d = lowest_rank(x)
        return f"Lowest rank {d}"


@api.route('/index')
@api.doc()
class Index(Resource):

    @api.response(200, 'Success')
    def get(self):
        return "Welcome to eXsim :)"


@api.route('/api/search/id/<string:bn_id>')
@api.doc(params={'id': 'a valid babelnet id'})
class SearchById(Resource):

    @api.response(200, 'Success', model=term_model)
    def get(self, bn_id):
        dataset_manager = DatasetManager()
        result = dataset_manager.get_synset_by_id(bn_id)

        return app.response_class(
            response=repr(result),
            status=200,
            mimetype='application/json'
        )


@api.route('/api/search/batched/')
class SearchByIdBatched(Resource):
    @api.expect(fields.List(fields.String(required=True, description='The synset id')), validate=True)
    @api.response(200, 'Success', model=fields.List(fields.Nested(term_model)))
    def post(self):
        dataset_manager = DatasetManager()
        body = api.payload
        result = dataset_manager.get_synsets_by_id_batched(body)

        return app.response_class(
            response=repr(result),
            status=200,
            mimetype='application/json'
        )


@api.route('/api/search/<path:lemma>/<int:page>')
@api.doc(params={'lemma': 'a search string given by the user'})
class SearchByLemma(Resource):

    @api.response(200, 'Success', model=fields.List(fields.Nested(term_model)))
    def get(self, lemma, page):
        dataset_manager = DatasetManager()
        results = dataset_manager.get_synsets_by_lemma(lemma, page)

        return app.response_class(
            response=repr(results),
            status=200,
            mimetype='application/json'
        )


@api.route('/api/summary/config/')
class SummaryConfigurator(Resource):
    @api.expect(unit_model, validate=True)
    @api.response(200, 'Success', model=summary_config_model)
    def post(self):
        body = api.payload

        unit = json_to_unit(body)
        config = sm.summary_configurator(unit)

        return app.response_class(
            response=repr(config),
            status=200,
            mimetype='application/json'
        )


@api.route('/api/summary/')
class SummaryComputer(Resource):
    @api.expect(summary_request_model, validate=True)
    @api.response(200, 'Success', model=unit_model)
    def post(self):

        body = api.payload

        response: Unit = json_to_unit(body["unit"])
        config: SummaryConfig = json_to_summary_config(body["summary_config"])
        sm.summary_selector(response, config)

        return app.response_class(
            response=repr(response),
            status=200,
            mimetype='application/json'
        )


@api.route('/api/characterize/')
class Characterize(Resource):
    @api.expect(unit_model, validate=True)

    @api.response(200, 'Success', model=unit_model)
    def post(self):
        my_unit = json_to_unit(request.json)
        my_unit.characterization = characterize(my_unit, False, [True, True, False])

        return app.response_class(
            response=repr(my_unit),
            status=200,
            mimetype='application/json'
        )


@api.route('/api/sizes/')
class Sizes(Resource):

    @api.expect(unit_model, validate=True)
    @api.response(200, 'Success', model=sizes_model)
    def post(self):
        my_unit: Unit = json_to_unit(request.json)
        if my_unit.characterization is None:
            pass

        shown = len(my_unit.characterization.predicates)
        kern = 0  
        core = 0  

        return app.response_class(
            response={'shown': shown, 'kern': kern, 'core': core},
            status=200,
            mimetype='application/json'
        )


@api.route('/api/canonical')
class Canonical(Resource):

    @api.expect(unit_model, validate=True)
    @api.response(200, 'Success', model=unit_model)
    def post(self):
        timeout = 5

        my_unit = json_to_unit(request.json)
        my_unit.characterization = characterize(my_unit, False, [True, True, False], False)
        return app.response_class(
            response=repr(my_unit),
            status=200,
            mimetype='application/json'
        )


@api.route('/api/compare/')
class Comparator(Resource):
    @api.expect(list_of_units_model, validate=True)
    @api.response(200, 'Success', model=unit_relation_model)
    def post(self):
        body = request.json
        unit1 = json_to_unit(body["units"][0])
        unit2 = json_to_unit(body["units"][1])

        resp = compare_units(unit1, unit2)
        return app.response_class(
            response=jsonpickle.encode({"relation": resp}),
            status=200,
            mimetype='application/json'
        )


@api.route('/api/expand/')
class Expander(Resource):
    @api.expect(unit_model, validate=True)
    @api.response(200, 'Success', model=unit_model)
    def post(self):
        my_unit: Unit = json_to_unit(request.json)
        try:
            expanded_unit = expand(my_unit)
        except Exception as e:
            return app.response_class(
                response=str(e),
                status=500
            )
        return app.response_class(
            response=repr(expanded_unit),
            status=200,
            mimetype='application/json'
        )


@api.route('/api/relax/transitive')
class IsaRelaxer(Resource):

    @api.expect(atom_list_model, validate=True)
    @api.response(200, 'Success', model=expansion_levels_model)
    def post(self):
        body = api.payload
        p: list[Predicate] = []
        for v in body['atoms']:
            p.append(json_to_predicate(v))

        output = relax_transitive_v2(p)
        formulas = []
        for v in output:
            formulas.append(
                Formula(v)
            )

        return app.response_class(
            response=jsonpickle.encode({'levels': formulas}, unpicklable=False),
            status=200,
            mimetype='application/json'
        )


@api.route('/api/query')
class QueryExecutor(Resource):
    @api.expect(query_model, validate=True)
    @api.response(200, 'Success', model=query_results_model)
    def post(self):
        body = api.payload
        query = json_to_formula(body["query"])
        exclude_both_constants = body.get("exclude_both_constants", False)
        page = body.get("page", 0)

        results = qm.execute_query(query, exclude_both_constants, page)

        return app.response_class(
            response=repr(results),
            status=200,
            mimetype='application/json'
        )


@api.route('/api/query/diff')
class QueryDiff(Resource):
    @api.expect(query_comparison_model, validate=True)
    @api.response(200, 'Success', model=query_results_model)
    def post(self):
        body = api.payload
        query1 = json_to_formula(body["query1"])
        query2 = json_to_formula(body["query2"])
        page = body.get("page", 0)

        results = qm.compute_diff_output(query1, query2, page)

        return app.response_class(
            response=repr(results),
            status=200,
            mimetype='application/json'
        )


@api.route('/api/query/superclass/get/<string:bn_id>')
@api.doc(params={'bn_id': 'A valid babelnet id'})
class GetSuperclasses(Resource):

    @api.response(200, 'Success', model=fields.List(fields.Nested(term_model)))
    def get(self, bn_id):
        dataset_manager = DatasetManager()
        result = dataset_manager.get_synsets_by_id_batched(dataset_manager.get_reached_synsets_by_hypernym(bn_id))

        return app.response_class(
            response=repr(result),
            status=200,
            mimetype='application/json'
        )


@api.route('/api/query/term')
class CheckTermInQuery(Resource):
    @api.expect(term_in_query_model, validate=True)
    @api.response(200, 'Success', model=boolean_answer_model)
    def post(self):
        body = api.payload
        query = json_to_formula(body["query"])
        term = json_to_term(body["term"])

        result = BooleanAnswer(qm.is_term_in_output(term, query))

        return app.response_class(
            response=repr(result),
            status=200,
            mimetype='application/json'
        )


@api.route('/api/query/subset')
class CheckQuerySubset(Resource):
    @api.expect(query_comparison_model, validate=True)
    @api.response(200, 'Success', model=boolean_answer_model)
    def post(self):
        body = api.payload
        query1 = json_to_formula(body["query1"])
        query2 = json_to_formula(body["query2"])

        result = BooleanAnswer(qm.is_subset(query1, query2))

        return app.response_class(
            response=repr(result),
            status=200,
            mimetype='application/json'
        )


@api.route('/api/query/superclass/check')
class CheckSuperclasses(Resource):

    @api.expect(check_superclasses_model, validate=True)
    @api.response(200, 'Success', model=superclasses_model)
    def post(self):
        body = api.payload
        result = sm.compute_common_by_pred_list(body["term"], body["superclasses"], body["predicate"])

        return app.response_class(
            response=jsonpickle.encode(result, unpicklable=False),
            status=200,
            mimetype='application/json'
        )


@api.route('/api/summary/ancestors')
class NearestCommonAncestors(Resource):

    @api.expect(nearest_common_ancestors_request_model, validate=True)
    @api.response(200, 'Success', model=nearest_common_ancestors_model)
    def post(self):
        body = api.payload
        dataset_manager = DatasetManager()
        result = dataset_manager.get_synsets_by_id_batched(list(
            map(lambda ancestor: ancestor[0], sm.nearest_common_ancestor_batched(body["terms"], body["predicate"]))))

        return app.response_class(
            response=jsonpickle.encode(result, unpicklable=False),
            status=200,
            mimetype='application/json'
        )


@api.route("/api/register")
class Register(Resource):
    @api.response(200, 'Success', model=boolean_answer_model)
    @api.response(404, 'Not Found')
    @api.expect(user_model, validate=True)
    def post(self):
        data = request.json
        if not data:
            return app.response_class(
                message='Missing data',
                response='Bad Request',
                status=400
            )

        u = User(data['username'], '')
        exists = u.find_user_by_username()
        if exists:
            return app.response_class(
                response=f'User {u.username} already registered',
                status=409
            )

        u = User(data['username'], data['password'])
        try:
            u.save_to_db()
            return app.response_class(
                status=201,
                response=repr(BooleanAnswer(True))
            )
        except Exception as e:
            return app.response_class(
                response=f'Error: "{str(e)}" while registering',
                status=500

            )


@api.route("/api/login")
class Login(Resource):
    @api.response(200, 'Success', model=user_model)
    @api.expect(user_model, validate=False)
    def post(self):
        data = request.json
        if not data:
            return app.response_class(
                response='User data is mandatory',
                status=400,
                mimetype='application/json')
        username = data['username']
        password = data['password']
        if not username or username == '':
            return app.response_class(
                response='Please provide a valid username',
                status=400,
                mimetype='application/json'
            )
        if not password or not validate_password(password):
            return app.response_class(
                response='The password does not match the minimum requirements',
                status=400,
                mimetype='application/json'
            )

        u = User(username, password)
        pwd_ok = u.check_password(password)
        if pwd_ok:
            access_token = create_access_token(identity=u.username)
            try:
                headers = {'Authorization': 'Bearer ' + access_token}
                return app.response_class(response=str(u), status=200, mimetype='application/json', headers=headers)
            except Exception as e:
                return app.response_class(response=f'Login error: {e}', status=500, mimetype='application/json')

        return app.response_class(response='Wrong password', status=401, mimetype='application/json')


class Protected(Resource):

    @api.response(200, 'Success', model=user_model)
    @api.expect(user_model, validate=False)
    @jwt_required()
    def post(self):
        data = request.json
        return app.response_class(response='ok', status=200,
                                  mimetype='text/plain',
                                  headers=dict())
