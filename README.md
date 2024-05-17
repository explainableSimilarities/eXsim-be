# neXSim-be 0.1 alpha

neXSim be is a RESTful system implemented in Python (Flask) for explaining similarities between entities from a Knowledge Base, relying on the main concepts of this [framework](https://www.sciencedirect.com/science/article/pii/S0020025524002445).


## Requirements

This version of neXSim requires Python [3.10](https://www.python.org/downloads/release/python-31011/) or [3.11](https://www.python.org/downloads/release/python-3117/) with [pip](https://pypi.org/project/pip/) to work properly.

*\*The following commands work on Linux and are tested on Ubuntu 24.04. Please check for the corresponding for other Operating Systems*

```
python3 --version
```

Please check also your version of 'pip'

```
pip --version
```

Please be sure to create a new [Python virtual environment](https://docs.python.org/3/library/venv.html), activate it and install the required packages.

In order to perform these operations, you can run the following from the root directory of the project:


*\*The following commands work on Linux and are tested on Ubuntu 24.04. Please check for the corresponding for other Operating Systems*
```
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

You can find the list of required packages [here](requirements.txt)

You also require a running instance of [Neo4j](https://neo4j.com/) storing a compliant semantic resource
(the online version of this software relies on data coming from [BabelNet 4.0.1](https://babelnet.org)

Please fill the corresponding data in [this file](eXsim/babelnet.py) (row 277) before starting the application 

## Usage

Once installed the requirements, you can simply run 

*\*The following commands work on Linux and are tested on Ubuntu 24.04. Please check for the corresponding for other Operating Systems*
```
python3 app.py
```

from the root folder of the project.

## Input Data

If you want to use the APIs directly, In [router.py](eXsim/router.py) you can find the available endpoints together with the required data format.

Alternatively, you can install our web interface, available at [neXSim-fe](https://github.com/explainableSimilarities/neXSim-fe).

## Online Version

An online version of this software is available [here](https://n9.cl/6ghqj)





