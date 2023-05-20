# Script for Migrating WP3 Schema to new Schema

import sys
from os.path import dirname
sys.path.append(dirname(sys.path[0]))

import pydgraph
from flaskinventory.main.model import Schema
import json
import math
from datetime import datetime
from slugify import slugify
import requests
from pathlib import Path

client_stub = pydgraph.DgraphClientStub('localhost:9080')
client = pydgraph.DgraphClient(client_stub)

p = Path.cwd()

print('Loading Schema from model...')

# Apply new schema (after loading backup)
schema = Schema.generate_dgraph_schema()

print('Setting Schema to DGraph')
# Set schema
client.alter(pydgraph.Operation(schema=schema))

""" Migrate Types """

print('Migrating Datasets and Corpora...')

# Dataset and Corpus

query = """{
  c as var(func: type(Corpus))
  d as var(func: type(Dataset))
}"""

nquad = """uid(c) <fulltext_available> "true" .
            uid(c) <dgraph.type> "Dataset" .
            uid(d) <fulltext_available> "false" .
        """

delete = """uid(c) <dgraph.type> "Corpus" ."""

txn = client.txn()

mutation = txn.create_mutation(set_nquads=nquad, del_nquads=delete)
request = txn.create_request(query=query, mutations=[mutation], commit_now=True)
txn.do_request(request)

# News Sources

print('Migrating News Sources ...')


query = """{
  s as var(func: type(Source))
}"""

nquad = """uid(s) <dgraph.type> "NewsSource" . """

delete = """uid(s) <dgraph.type> "Source" ."""

txn = client.txn()

mutation = txn.create_mutation(set_nquads=nquad, del_nquads=delete)
request = txn.create_request(query=query, mutations=[mutation], commit_now=True)
txn.do_request(request)

# Journalistic Brands

print('Generating Journalistic Brands ...')

query_total_entries = """
{
	sources(func: type("NewsSource")) @filter(eq(entry_review_status, "accepted") or eq(entry_review_status, "pending")) {
        total: count(uid)
    }
} """

query_sources = """
query get_sources($maximum: int, $offset: int)
{
	sources(func: type("NewsSource"), first: $maximum, offset: $offset) @filter(eq(entry_review_status, "accepted") or eq(entry_review_status, "pending")) {
        uid name unique_name wikidata_id channel { uid unique_name } related_news_sources { uid unique_name channel { unique_name } }
    }
} """

total = client.txn(read_only=True).query(query_total_entries)
total = json.loads(total.json)

total_sources = total['sources'][0]['total']
results_maximum = 1000
offset = 0
variables = {'$maximum': str(results_maximum), '$offset': ""}

pages_sources = math.ceil(total_sources / results_maximum)

sources = []

for i in range(1, pages_sources + 1):
    variables['$offset'] = str(offset)
    res = client.txn(read_only=True).query(query_sources, variables=variables)
    raw = json.loads(res.json)
    sources += raw['sources']
    offset += results_maximum

# Order of priority: Transcript > Print > Website > Twitter > Facebook > Instagram > Telegram > VK

processed_memory = []
journalistic_brands = []
brand_template = {'dgraph.type': ["Entry", "JournalisticBrand"],
                   '_unique_name': "",
                  'name': "",
                  '_date_created': datetime.now().isoformat(),
                  'entry_review_status': "pending"}

# transcripts
for source in sources:
    if source['channel']['unique_name'] == 'transcript':
        processed_memory.append(source['uid'])
        brand = {**brand_template}
        brand['_unique_name'] = "journalisticbrand_" + slugify(source['name'], separator="") + "_" + datetime.now().strftime("%Y%m%d")
        brand['name'] = source['name']
        brand['sources_included'] = [{'uid': source['uid']}]
        if "wikidata_id" in source:
            brand['wikidata_id'] = "Q" + str(source['wikidata_id'])
        if "related_news_sources" in source:
            for related_news_sources in source['related_news_sources']:
                brand['sources_included'].append({'uid': related_news_sources['uid']})
                processed_memory.append(related_news_sources['uid'])
        journalistic_brands.append(brand)
        


# print
for source in sources:
    if source['channel']['unique_name'] == 'print':
        if source['uid'] in processed_memory:
            continue
        processed_memory.append(source['uid'])
        brand = {**brand_template}
        brand['_unique_name'] = "journalisticbrand_" + slugify(source['name'], separator="") + "_" + datetime.now().strftime("%Y%m%d")
        brand['name'] = source['name']
        brand['sources_included'] = [{'uid': source['uid']}]
        if "wikidata_id" in source:
            brand['wikidata_id'] = "Q" + str(source['wikidata_id'])
        if "related_news_sources" in source:
            for related_news_sources in source['related_news_sources']:
                brand['sources_included'].append({'uid': related_news_sources['uid']})
                processed_memory.append(related_news_sources['uid'])
        journalistic_brands.append(brand)
        

# website
for source in sources:
    if source['channel']['unique_name'] == 'website':
        if source['uid'] in processed_memory:
            continue
        processed_memory.append(source['uid'])
        brand = {**brand_template}
        brand['_unique_name'] = "journalisticbrand_" + slugify(source['name'], separator="") + "_" + datetime.now().strftime("%Y%m%d")
        brand['name'] = source['name']
        brand['sources_included'] = [{'uid': source['uid']}]
        if "wikidata_id" in source:
            brand['wikidata_id'] = "Q" + str(source['wikidata_id'])
        if "related_news_sources" in source:
            for related_news_sources in source['related_news_sources']:
                brand['sources_included'].append({'uid': related_news_sources['uid']})
                processed_memory.append(related_news_sources['uid'])
        journalistic_brands.append(brand)
        

# twitter
for source in sources:
    if source['channel']['unique_name'] == 'twitter':
        if source['uid'] in processed_memory:
            continue
        processed_memory.append(source['uid'])
        brand = {**brand_template}
        brand['_unique_name'] = "journalisticbrand_" + slugify(source['name'], separator="") + "_" + datetime.now().strftime("%Y%m%d")
        brand['name'] = source['name']
        brand['sources_included'] = [{'uid': source['uid']}]
        if "wikidata_id" in source:
            brand['wikidata_id'] = "Q" + str(source['wikidata_id'])
        if "related_news_sources" in source:
            for related_news_sources in source['related_news_sources']:
                brand['sources_included'].append({'uid': related_news_sources['uid']})
                processed_memory.append(related_news_sources['uid'])
        journalistic_brands.append(brand)
        



# facebook
for source in sources:
    if source['channel']['unique_name'] == 'facebook':
        if source['uid'] in processed_memory:
            continue
        processed_memory.append(source['uid'])
        brand = {**brand_template}
        brand['_unique_name'] = "journalisticbrand_" + slugify(source['name'], separator="") + "_" + datetime.now().strftime("%Y%m%d")
        brand['name'] = source['name']
        brand['sources_included'] = [{'uid': source['uid']}]
        if "wikidata_id" in source:
            brand['wikidata_id'] = "Q" + str(source['wikidata_id'])
        if "related_news_sources" in source:
            for related_news_sources in source['related_news_sources']:
                brand['sources_included'].append({'uid': related_news_sources['uid']})
                processed_memory.append(related_news_sources['uid'])
        journalistic_brands.append(brand)
        

# instagram
for source in sources:
    if source['channel']['unique_name'] == 'instagram':
        if source['uid'] in processed_memory:
            continue
        processed_memory.append(source['uid'])
        brand = {**brand_template}
        brand['_unique_name'] = "journalisticbrand_" + slugify(source['name'], separator="") + "_" + datetime.now().strftime("%Y%m%d")
        brand['name'] = source['name']
        brand['sources_included'] = [{'uid': source['uid']}]
        if "wikidata_id" in source:
            brand['wikidata_id'] = "Q" + str(source['wikidata_id'])
        if "related_news_sources" in source:
            for related_news_sources in source['related_news_sources']:
                brand['sources_included'].append({'uid': related_news_sources['uid']})
                processed_memory.append(related_news_sources['uid'])
        journalistic_brands.append(brand)
        

# telegram
for source in sources:
    if source['channel']['unique_name'] == 'telegram':
        if source['uid'] in processed_memory:
            continue
        processed_memory.append(source['uid'])
        brand = {**brand_template}
        brand['_unique_name'] = "journalisticbrand_" + slugify(source['name'], separator="") + "_" + datetime.now().strftime("%Y%m%d")
        brand['name'] = source['name']
        brand['sources_included'] = [{'uid': source['uid']}]
        if "wikidata_id" in source:
            brand['wikidata_id'] = "Q" + str(source['wikidata_id'])
        if "related_news_sources" in source:
            for related_news_sources in source['related_news_sources']:
                brand['sources_included'].append({'uid': related_news_sources['uid']})
                processed_memory.append(related_news_sources['uid'])
        journalistic_brands.append(brand)

# Apply

txn = client.txn()

res = txn.mutate(set_obj=journalistic_brands, commit_now=True)

print('Adding audience_size_recent ...')

query_string = """{
	q(func: has(audience_size)) {
		uid audience_size @facets
  }
}"""

res = client.txn().query(query_string)

j = json.loads(res.json)['q']

audience_size_recent = []

for node in j:
    try:
        updated = {'uid': node['uid'],
                'audience_size_recent': node['audience_size|count']['0'],
                'audience_size_recent|unit': node['audience_size|unit']['0'],
                'audience_size_recent|timestamp': node['audience_size'][0]}
    except:
        print('Could not parse node', node['uid'])
        continue
    audience_size_recent.append(updated)
    
res = client.txn().mutate(set_obj=audience_size_recent, commit_now=True)

""" Scientific Publication """

print('Migrating Scientific Publications ...')

query = """{
  r as var(func: type(ResearchPaper))
}"""

nquad = """uid(r) <dgraph.type> "ScientificPublication" . """

delete = """uid(r) <dgraph.type> "ResearchPaper" ."""

txn = client.txn()

mutation = txn.create_mutation(set_nquads=nquad, del_nquads=delete)
request = txn.create_request(query=query, mutations=[mutation], commit_now=True)
txn.do_request(request)

""" Organization """

print('Migrating Organizations to Parties and Persons ...')


query = """{
  party as var(func: type(Organization)) @filter(eq(ownership_kind, "political party")) 
  person as var(func: type(Organization)) @filter(eq(is_person, "true")) 
}"""

nquad = """uid(party) <dgraph.type> "PoliticalParty" . 
            uid(person) <dgraph.type> "Person" . 
        """

delete = """uid(party) <dgraph.type> "Organization" .
            uid(party) <ownership_kind> * .
            uid(person) <dgraph.type> "Organization" .
            uid(person) <is_persion> * .
        """

txn = client.txn()

mutation = txn.create_mutation(set_nquads=nquad, del_nquads=delete)
request = txn.create_request(query=query, mutations=[mutation], commit_now=True)
txn.do_request(request)

""" Authors """

print('Migrating Authors ...')

def resolve_openalex(entry):
    doi = entry['doi']
    api = "http://api.openalex.org/works/doi:"
    r = requests.get(api + doi)
    j = r.json()
    output = {'uid': entry['uid'],
              '_date_modified': datetime.now().isoformat()}
    authors = []
    for i, author in enumerate(j['authorships']):
        a_name = author['author']['display_name']
        open_alex = author['author']['id'].replace('https://openalex.org/', "")
        author_entry = {'uid': '_:' + slugify(open_alex, separator="_"),
                        '_unique_name': 'author_' + slugify(open_alex, separator=""),
                        'entry_review_status': "pending",
                        'openalex': open_alex,
                        'name': a_name,
                        '_date_created': datetime.now().isoformat(),
                        'authors|sequence': i}
        if author['author'].get("orcid"):
            author_entry['orcid'] = author['author']['orcid']
        authors.append(author_entry)
    output['authors'] = authors
    return output

# get all entries with DOI

query = """{
	q(func: has(_authors_tmp)) @filter(has(doi))  {
		uid name doi _authors_tmp
        }
    }
"""

res = client.txn().query(query)

entries_with_doi = json.loads(res.json)['q']
authors = []
failed = []

print('Retrieving Authors from OpenAlex ...')

for entry in entries_with_doi:
    try:
        authors.append(resolve_openalex(entry))
    except:
        failed.append(entry)

txn = client.txn()
res = txn.mutate(set_obj=authors, commit_now=True)

# Delete _authors_tmp

uids = [a['uid'] for a in authors]

delete_nquads = [f'<{uid}> <_authors_tmp> * .' for uid in uids]

txn = client.txn()
res = txn.mutate(del_nquads="\n".join(delete_nquads), commit_now=True)

""" Languages """

print('Migrating Languages ...')

langs_json = p / 'data' / 'languages.json'

with open(langs_json, 'r') as f:
    languages = json.load(f)

languages = languages['set']

for l in languages:
    l['entry_review_status'] = 'accepted'

languages_lookup = {l['icu_code']: l['uid'] for l in languages}

# find all entries with languages

query_string = """{
	q(func: has(_languages_tmp)) {
		uid _languages_tmp
  }
}"""

res = client.txn().query(query_string)

j = json.loads(res.json)['q']

updated_entries = []

for entry in j:
    updated = {'uid': entry['uid'],
               'languages': []}
    for l in entry['_languages_tmp']:
        updated['languages'].append({'uid': languages_lookup[l]})
    updated_entries.append(updated)

updated_entries += languages

res = client.txn().mutate(set_obj=updated_entries, commit_now=True)

# delete _languages_tmp


query = """{
  l as var(func: has(_languages_tmp))
}"""

delete = """uid(l) <_languages_tmp> * ."""

txn = client.txn()

mutation = txn.create_mutation(del_nquads=delete)
request = txn.create_request(query=query, mutations=[mutation], commit_now=True)
txn.do_request(request)


""" Programming Languages """

print('Migrating Programming Languages ...')

langs_json = p / 'data' / 'programming_languages.json'

with open(langs_json, 'r') as f:
    languages = json.load(f)

languages = languages['set']

for l in languages:
    l['entry_review_status'] = 'accepted'

languages_lookup = {l['_unique_name'].replace("programming_language_", ""): l['uid'] for l in languages}

# find all entries with languages

query_string = """{
	q(func: has(_programming_languages_tmp)) {
		uid _programming_languages_tmp
  }
}"""

res = client.txn().query(query_string)

j = json.loads(res.json)['q']

updated_entries = []

for entry in j:
    updated = {'uid': entry['uid'],
               'programming_languages': []}
    for l in entry['_programming_languages_tmp']:
        updated['programming_languages'].append({'uid': languages_lookup[l]})
    updated_entries.append(updated)

updated_entries += languages

res = client.txn().mutate(set_obj=updated_entries, commit_now=True)

# delete _programming_languages_tmp

query = """{
  l as var(func: has(_programming_languages_tmp))
}"""

delete = """uid(l) <_programming_languages_tmp> * ."""

txn = client.txn()

mutation = txn.create_mutation(del_nquads=delete)
request = txn.create_request(query=query, mutations=[mutation], commit_now=True)
txn.do_request(request)


""" Generate new unique names """

client_stub.close()