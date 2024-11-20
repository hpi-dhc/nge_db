# Next Generation Evidence

This repository contains code for combining and harmonizing primary and secondary evidnce from different sources (Pubmed, ClinicalTrials.gov, CIViC, GGPONC).
It consists of a database, an application server with a REST API, and a Vue.js frontend.

## Installation

We use [`poetry`](https://python-poetry.org/) as a build tool..
Therefore, the dependencies can be installed by running

    poetry install

To also install the dev dependencies, run

    poetry install --with dev

On an M1 Mac, the installation might fail due to a bug in `pygraphviz`,
[a fix can be found here](https://github.com/pygraphviz/pygraphviz/issues/398#issuecomment-1450367670).

Additionally, `pre-commit` is used to run a few checks and fixes before commits.
In order to use them, run

    poetry run pre-commit install

## Usage

## Environment Variables

The system expects the following environment variables to be set. We used a `.env` file placed in the root directory of the repository for this purpose:

* `PUBMED_API_KEY` for accessing eUtils (only needed for populating the DB)
* `UMLS_API_KEY` for downloading UMLS (needed for populating the DB and for the API)

## Populating the Database

To download the necessary data and to populate the database, run

    `poetry run populate`
    
You may run to populate individual parts of the database individually, e.g.,:

    `poetry run populate ggponc`

### Guidelines

Get access to the latest [GGPONC release](https://www.leitlinienprogramm-onkologie.de/projekte/ggponc-english) and place its contents in `data/ggponc/` (or adapt the part in the `config.ini`.

### PubMed

### ClinicalTrials.gov

`poetry run populate` automatically identifies the latest monthly dump from [AACT](https://aact.ctti-clinicaltrials.org/download) and downloads it if necessary.

### CIViC

`poetry run populate` automatically identifies the latest nightly dump from [CIViC](https://civicdb.org/) and downloads it if necessary.

## Starting the application server

To start the application server and REST API, please run

    poetry run api

## Evaluation

An overview of the systems features and its evaluation can be found it the notebooks in the repository's root directory.

## Documentation

To show the documentation, run

    poetry shell
    pdoc integration
    
## Citation

TODO