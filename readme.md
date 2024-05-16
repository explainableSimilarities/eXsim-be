python3 -m venv venv \
source venv/bin/activate \
python3 -m pip install git+https://github.com/DeMaCS-UNICAL/EmbASP-Python.git \
pip install flask \
pip freeze > requirements.txt \
Remember to put embasp module folder into venv/lib and to add the dlv2 executable (compatible with external predicates) into eXsim/asp/executables. \
You can find all this stuff here: https://drive.google.com/drive/folders/1vAFU7CGVbDW_UpUJQfaOG_xmX9LTmZum?usp=sharing \
It is required python3.9

NEW SEARCH MODULE REQUIREMENTS:

1) Create a new fulltext index \
CREATE FULLTEXT INDEX mainSensesAndSynonyms \
FOR (n:Synset) \
ON EACH [n.main_sense, n.synonyms] \
OPTIONS {indexConfig: {`fulltext.analyzer`: 'classic'}}

2) Precompute relationships count for each synset \
CALL apoc.periodic.iterate( \
  "MATCH (n:Synset) \
   RETURN n", \
  "WITH n, COUNT{(n)-->(:Synset)} as count_rel \
   SET n.num_rel = count_rel", \
  {batchSize:20000, parallel: true})

NEW CONFIGURATOR REQUIREMENTS:

1) Migrate relationships kind field to new notation: \
CALL apoc.periodic.iterate( \
  "MATCH (:Synset)-[r]->(:Synset) \
   RETURN r", \
  'WITH r,  \
   apoc.map.fromPairs([ \
    [1, "HYPERNYM"], \
    [2, "HOLONYM"], \
    [3, "OTHER"], \
    [4, "TOP"], \
    [5, "HYPONYM"], \
    [6, "MERONYM"]]) AS rel_map \
   SET r.kind = apoc.map.get(rel_map, toString(r.kind), toString(r.kind))', \
  {batchSize:20000, parallel: true})