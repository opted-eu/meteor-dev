"""
    Script for converting table (csv, xlsx) data about political parties
    to JSON files, ready for DGraph
"""

import json
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import date, datetime
import pydgraph
from slugify import slugify
import difflib
from wikibase_reconcile import Client
import tweepy

"""
    Helper Functions
"""
p = Path.cwd()

config_path = p / "flaskinventory"/ "config.json"

with open(config_path) as f:
    api_keys = json.load(f)


twitter_auth = tweepy.OAuthHandler(api_keys["TWITTER_CONSUMER_KEY"],
                                    api_keys["TWITTER_CONSUMER_SECRET"])
twitter_auth.set_access_token(api_keys["TWITTER_ACCESS_TOKEN"],
                                api_keys["TWITTER_ACCESS_SECRET"])

twitter_api = tweepy.API(twitter_auth)


def fetch_twitter(username):
    user = twitter_api.get_user(screen_name=username)
    return {'followers': user.followers_count, 'fullname': user.screen_name, 'joined': user.created_at, 'verified': user.verified}


# Load Data from Excel sheet
xlsx = p / 'data' / 'OPTED Taxonomy.xlsx'

# generate this feather file with `partyfacts_wikidata.py`
pfacts_feather = p / 'data' / 'partyfacts.feather'

df = pd.read_excel(xlsx, sheet_name="political_party")

# clean columns
df_strings = df.select_dtypes(['object'])
df[df_strings.columns] = df_strings.apply(lambda x: x.str.strip())


# Join with Party facts data

partyfacts = pd.read_feather(pfacts_feather)
partyfacts.partyfacts_id = partyfacts.partyfacts_id.astype(int)

# clean
partyfacts_strings = partyfacts.select_dtypes(['object'])
partyfacts[partyfacts_strings.columns] = partyfacts_strings.apply(lambda x: x.str.strip())

opted_countries = df.dropna(subset="country").country.unique().tolist()
# partyfacts = partyfacts.loc[partyfacts.country.isin(opted_countries), :]

# join by wikidata first
party_ids_by_wikidata = {wikidata_id: party_id for wikidata_id, party_id in zip(
    partyfacts.wikidata_id.to_list(), partyfacts.partyfacts_id.to_list())}

df['partyfacts_id'] = df.wikidata_id.map(party_ids_by_wikidata)

# join country-wise by abbreviation

def fuzzy_match(x: str, possibilities: list, lookup: dict) -> str:
    # small helper function that tries to fuzzy match party names
    # returns the partyfacts_id from lookup dictionary
    possibilities = [p for p in possibilities if p is not None]
    try:
        result = difflib.get_close_matches(x, possibilities)[0]
        return lookup[result]
    except:
        return np.NaN


for country in df.dropna(subset="country").country.unique():
    partyfacts_filt = partyfacts.country == country
    party_ids_by_abbrev = {name: party_id for name, party_id in zip(
        partyfacts[partyfacts_filt].name_short.to_list(), 
        partyfacts[partyfacts_filt].partyfacts_id.to_list()
        ) if name is not None}
    party_ids_by_name = {name: party_id for name, party_id in zip(
        partyfacts[partyfacts_filt].name.to_list(), 
        partyfacts[partyfacts_filt].partyfacts_id.to_list()
        ) if name is not None}
    lookup = {**party_ids_by_abbrev, **party_ids_by_name}
    possibilities = [p for p in partyfacts[partyfacts_filt].name.to_list() if p is not None]
    filt = (df.country == country) & (df.partyfacts_id.isna())
    # df.loc[filt, 'partyfacts_id'] = df[filt].abbrev_name.map(party_ids_by_abbrev).fillna(df.loc[filt, 'partyfacts_id'])
    df.loc[filt, 'partyfacts_id'] = df[filt].name.apply(lambda x: fuzzy_match(x, possibilities, lookup))

# find row without wikidata id or partyfacts_id
filt = df.partyfacts_id.isna() & df.wikidata_id.isna()

# Drop all without any id (for now)

df_parties = df[~filt].reset_index(drop=True)
df_parties.partyfacts_id = df_parties.partyfacts_id.astype(np.float64)


# We want output like this
sample_json = {
    'dgraph.type': ['Entry', 'PoliticalParty'],
    'name': 'Sozialdemokratische Partei Deutschlands',
    'name@en': 'Social Democratic Party of Germany',
    'alternate_names': ['SPD'],
    'description': '',
    'wikidata_id': 'Q49768',
    'name_abbrev': 'SPD',
    'parlgov_id': "558",
    'party_facts_id': "383",
    'country': '<germany>'
}


# This is a template dict that we copy below for each social media handle
newssource_template = {
    'dgraph.type': ['Entry', 'NewsSource'],
    'uid': '_:newsource',
    'channel': {'uid': ''},
    'name': 'Name',
    'identifier': 'handle',
    'publication_kind': 'organizational communication',
    'special_interest': False,
    'publication_cycle': 'continuous',
    'geographic_scope': 'national',
    'countries': [],
    'languages': [],
    'payment_model': 'free',
    'contains_ads': 'no',
    'party_affiliated': 'yes',
    'related_news_sources': []
}

# Step 1: resolve country names

client_stub = pydgraph.DgraphClientStub('localhost:9080')
client = pydgraph.DgraphClient(client_stub)

query_string = '''query countries($country: string) {
    q(func: eq(name, $country)) @filter(eq(dgraph.type, [Country, Multinational])) { uid _unique_name } 
}'''

countries = df_parties.country.unique().tolist()

country_uid_mapping = {}
country_unique_name_mapping = {}

for country_name in countries:
    country = client.txn(read_only=True).query(query_string, variables={'$country': country_name})
    j = json.loads(country.json)
    country_uid_mapping[country_name] = j['q'][0]['uid']
    country_unique_name_mapping[country_name] = j['q'][0]['_unique_name']

df_parties['country_unique_name'] = df_parties.country.replace(country_unique_name_mapping)
df_parties['country'] = df_parties.country.replace(country_uid_mapping)


# Generate Unique Names for political parties

df_parties['_unique_name'] = ''

df_parties['_unique_name'] = 'politicalparty_' + df_parties['country_unique_name'].apply(slugify, separator="") + '_' + df_parties['name'].apply(slugify, separator="")


# Step 1.5: Resolve channel uids

query_string = '''{
    q(func: type(Channel)) { uid _unique_name } 
}'''

res = client.txn(read_only=True).query(query_string)
j = json.loads(res.json)

channels_mapping = {c['_unique_name']: c['uid'] for c in j['q']}

# Step 2: rename existing columns

# name -> name
# abbrev_name -> abbrev_name
# alternate_names -> [drop if identical with `name`]
# name_english -> name@en
# wikidata_id -> wikidata_id
# country -> country
# original.name -> add to alternate_names
# note -> [drop]
# party_colors -> color_hex
# official_website -> url
# facebook_id -> facebook
# instagram_username -> instagram
# twitter_username -> twitter

filt = df_parties.name == df_parties.alternate_names
df_parties.loc[filt, 'alternate_names'] = ""

df_parties = df_parties.drop(columns=["color_hex"])

df_parties = df_parties.rename(columns={'name_english': 'name@en', 
                   'party_colors': 'color_hex',
                   'official_website': 'url',
                   'facebook_id': 'facebook',
                   'instagram_username': 'instagram',
                   'twitter_username': 'twitter'})

df_parties = df_parties.drop(columns=['country_unique_name'])

# remove np.nan values

df_parties_strings = df_parties.select_dtypes(['object'])
df_parties[df_parties_strings.columns] = df_parties_strings.replace({np.nan: ""})

df_parties['tmp_unique_name'] = df_parties.unique_name
df_parties = df_parties.drop(columns=["unique_name"])

# convert df_parties (unique by wikidata_id) to a dict

parties = df_parties.drop_duplicates(subset="wikidata_id").to_dict(orient='records')

# Reformatting

for party in parties:
    # Add dgraph.type
    party['dgraph.type'] = ['Entry', 'PoliticalParty']
    # reformat `alternate_names` to lists, drop `original.name`
    if party['original.name'] != party['alternate_names']:
        party['alternate_names'] = list(set([party['original.name'], party['alternate_names']]))
        try:
            party['alternate_names'].remove('')
        except:
            pass
    del party['original.name']
    # Step 5: reformat `country` to dicts
    party['country'] = {'uid': party['country']}
    # Step 6: Reformat social media channels to news sources
    party['publishes'] = []
    if party['twitter'] != '':
        handle = party['twitter']
        twitter = {**newssource_template}
        twitter['uid'] = f'_:{handle}_twitter'
        twitter['entry_review_status'] = f'accepted'
        twitter['_unique_name'] = "newssource_" + slugify(handle, separator="") + '_twitter'
        twitter['channel'] = {'uid': channels_mapping['twitter']}
        twitter['name'] = handle
        twitter['identifier'] = handle
        try:
            profile = fetch_twitter(handle)
            twitter['alternate_names'] = profile['fullname']
            twitter['audience_size'] = datetime.now().isoformat()
            twitter['audience_size|unit'] = "followers"
            twitter['audience_size|count'] = profile['followers'] 
            twitter['audience_size_recent'] = profile['followers']
            twitter['audience_size_recent|unit'] = "followers"
            twitter['audience_size_recent|timestamp'] = datetime.now().isoformat()
            twitter['date_founded'] = profile['joined'].isoformat()
            twitter['verified_account'] = profile['verified']
        except:
            pass
        party['publishes'].append(twitter)
    _ = party.pop('twitter')
    if party['facebook'] != '':
        handle = party['facebook']
        facebook = {**newssource_template}
        facebook['uid'] = f'_:{handle}_facebook'
        facebook['entry_review_status'] = f'accepted'
        facebook['_unique_name'] = "newssource_" + slugify(handle, separator="") + '_facebook'
        facebook['channel'] = {'uid': channels_mapping['facebook']}
        facebook['name'] = handle
        facebook['identifier'] = handle
        party['publishes'].append(facebook)
    _ = party.pop('facebook')
    if party['instagram'] != '':
        handle = party['instagram']
        instagram = {**newssource_template}
        instagram['uid'] = f'_:{handle}_instagram'
        instagram['entry_review_status'] = f'accepted'
        instagram['_unique_name'] = "newssource_" + slugify(handle, separator="") + '_instagram'
        instagram['channel'] = {'uid': channels_mapping['instagram']}
        instagram['name'] = handle
        instagram['identifier'] = handle
        party['publishes'].append(instagram)
    _ = party.pop('instagram')
    # check for duplicates and append new names
    if len(df_parties[df_parties.wikidata_id == party['wikidata_id']]) > 1:
        additional_names = df_parties[df_parties.wikidata_id == party['wikidata_id']]['original.name'].to_list()
        party['alternate_names'] += additional_names
        party['alternate_names'] = list(set(party['alternate_names']))
    
for party in parties:
    # final cleaning on np.nan vals
    for k in list(party.keys()):
        try:
            if np.isnan(party[k]):
                del party[k]
        except:
            continue

for party in parties:
    try:
        party["partyfacts_id"] = int(party["partyfacts_id"])
    except:
        continue

for party in parties:
    # coerce floats to int
    for k in list(party.keys()):
        if isinstance(party[k], float):
            party[k] = int(party[k])


# Add related news sources to each other

for party in parties:
    if len(party['publishes']) > 1:
        new_ids = [{'uid': s['uid']} for s in party['publishes']]
        for newssource in party['publishes']:
            newssource['related_news_sources'] = new_ids



# Export JSON

output_file = p / 'data' / 'parties.json'

with open(output_file, 'w') as f:
    json.dump(parties, f, indent=True)