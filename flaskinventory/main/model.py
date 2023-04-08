from flaskinventory import login_manager
import datetime
from typing import Union

from flaskinventory.flaskdgraph.dgraph_types import *

from flaskinventory.main.custom_types import *

from flaskinventory.users.constants import USER_ROLES
from flaskinventory.users.dgraph import UserLogin, generate_random_username
from flaskinventory.flaskdgraph import Schema
from flaskinventory.auxiliary import icu_codes, programming_languages

from slugify import slugify
import secrets

"""
    Users
"""


class User(Schema, UserLogin):

    # currently prevent any kind of editing
    __permission_new__ = USER_ROLES.Admin + 100
    __permission_edit__ = USER_ROLES.Admin + 100

    uid = UIDPredicate()
    email = String(label='Email', read_only=True, edit=False,
                   required=True, directives=['@index(hash)', '@upsert'])
    display_name = String('Username', default=generate_random_username,
                          description="Your publicly visible username",
                          required=True)
    _pw = Password(label='Password', required=True)
    _pw_reset = String(hidden=True, edit=False, facets=[
                       Facet('used', dtype=bool)])
    orcid = String('ORCID')
    _date_joined = DateTime(label="Date joined", description='Date when this account was created',
                            read_only=True, edit=False)
    role = SingleChoiceInt(label="User Role", edit=False, read_only=True,
                           default=USER_ROLES.Contributor,
                           choices=USER_ROLES.dict_reverse)

    affiliation = String()
    _account_status = SingleChoice(choices={'pending': 'Pending', 'active': 'Active'},
                                   hidden=True, edit=False, default='pending')

    preference_emails = Boolean('Receive Email notifications', default=True)
    follows_entities = ListRelationship('Following', autoload_choices=False,
                                        edit=False)
    follows_types = ListString('Following types')


@login_manager.user_loader
def load_user(user_id):
    if not user_id.startswith('0x'):
        return
    if not UserLogin.check_user(user_id):
        return
    return User(uid=user_id)


"""
    Entry
"""


class Entry(Schema):

    __permission_new__ = USER_ROLES.Contributor
    __permission_edit__ = USER_ROLES.Contributor

    uid = UIDPredicate()

    _unique_name = UniqueName()

    _date_created = DateTime(new=False,
                             edit=False,
                             read_only=True,
                             hidden=True,
                             default=datetime.datetime.now,
                             directives=['@index(day)'])

    _date_modified = DateTime(new=False,
                              edit=False,
                              read_only=True,
                              hidden=True,
                              directives=['@index(day)'])

    _added_by = SingleRelationship(label="Added by",
                                   relationship_constraint="User",
                                   new=False,
                                   edit=False,
                                   read_only=True,
                                   hidden=True,
                                   facets=[Facet('ip'),
                                           Facet('timestamp', dtype=datetime.datetime)])

    _reviewed_by = SingleRelationship(label="Reviewed by",
                                      relationship_constraint="User",
                                      new=False,
                                      edit=False,
                                      read_only=True,
                                      hidden=True,
                                      facets=[Facet('ip'),
                                              Facet('timestamp', dtype=datetime.datetime)])

    _edited_by = ListRelationship(label="Edited by",
                                  relationship_constraint="User",
                                  new=False,
                                  edit=False,
                                  read_only=True,
                                  hidden=True,
                                  facets=[Facet('ip'),
                                          Facet('timestamp', dtype=datetime.datetime)])

    entry_review_status = SingleChoice(choices={'draft': 'Draft',
                                                'pending': 'Pending',
                                                'accepted': 'Accepted',
                                                'rejected': 'Rejected'},
                                       default='pending',
                                       required=True,
                                       new=False,
                                       permission=USER_ROLES.Reviewer)

    name = String(required=True, directives=['@index(term, trigram)', '@lang'])

    alternate_names = ListString(directives=['@index(term)'])

    description = String(large_textfield=True,
                         overwrite=True,
                         directives=['@index(fulltext, trigram, term)'])

    wikidata_id = String(label='WikiData ID',
                         description='ID as used by WikiData',
                         overwrite=True,
                         new=False,
                         directives=['@index(hash)'])

    hdl = String(label='HDL',
                 description='handle.net external identifier',
                 directives=['@index(hash)'],
                 hidden=True)
    
class PoliticalParty(Entry):

    __description__ = "political parties as legally registered"

    name_abbrev = String(label="Abbreviated Name", 
                         description="Abbreviation/Acronym of the party name.",
                         directives=["@index(term, trigram)", "@lang"],
                         queryable=True)
    
    parlgov_id = String(label="ParlGov ID", 
                        description="ID of party in ParlGov Dataset",
                        directives=["@index(hash)"])
    
    party_facts_id = String(label="Party Facts ID", 
                        description="ID of party in Party Facts Dataset",
                        directives=["@index(hash)"])

    country = SingleRelationship(relationship_constraint=['Country', 'Multinational'],
                                 autoload_choices=True,
                                 required=True,
                                 description='In which country is the political party registered?',
                                 render_kw={
                                     'placeholder': 'Select a country...'},
                                 queryable=True,
                                 predicate_alias="countries")


class Organization(Entry):

    __description__ = "companies, NGOs, businesses, media organizations"

    name = String(label='Organization Name',
                  required=True,
                  description='What is the legal or official name of the media organisation?',
                  render_kw={'placeholder': 'e.g. The Big Media Corp.'})

    alternate_names = ListString(description='Does the organisation have any other names or common abbreviations?',
                                 render_kw={'placeholder': 'Separate by comma'})

    ownership_kind = SingleChoice(choices={
        'NA': "Don't know / NA",
        'private ownership': 'Mainly private Ownership',
        'public ownership': 'Mainly public ownership',
        'unknown': 'Unknown Ownership'},
        description='Is the organization mainly privately owned or publicly owned?',
        queryable=True)

    country = SingleRelationship(relationship_constraint='Country',
                                 autoload_choices=True,
                                 description='In which country is the organisation located?',
                                 render_kw={
                                     'placeholder': 'Select a country...'},
                                 queryable=True,
                                 predicate_alias="countries")

    publishes = ListRelationship(relationship_constraint='Source',
                                 overwrite=True,
                                 description='Which news sources publishes the organisation (or person)?',
                                 render_kw={'placeholder': 'Type to search existing news sources and add multiple...'})

    owns = ListRelationship(allow_new=True,
                            relationship_constraint='Organization',
                            overwrite=True,
                            description='Which other media organisations are owned by this new organisation (or person)?',
                            render_kw={'placeholder': 'Type to search existing organisations and add multiple...'})

    is_ngo = Boolean("Is NGO", description="Is the organisation an NGO?")

    party_affiliated = SingleChoice(choices={
        'NA': "Don't know / NA",
        'yes': 'Yes',
        'no': 'No'},
        new=False,
        queryable=True)

    address = AddressAutocode(new=False,
                                     render_kw={'placeholder': 'Main address of the organization.'})

    employees = String(description='How many employees does the news organization have?',
                       render_kw={
                           'placeholder': 'Most recent figure as plain number'},
                       new=False)

    date_founded = DateTime(new=False, overwrite=True, queryable=True)


class Source(Entry):

    channel = SingleRelationship(description='Through which channel is the news source distributed?',
                                 edit=False,
                                 autoload_choices=True,
                                 relationship_constraint='Channel',
                                 read_only=True,
                                 required=True,
                                 queryable=True,
                                 predicate_alias=['channels'])

    name = String(label='Name of the News Source',
                  required=True,
                  description='What is the name of the news source?',
                  render_kw={'placeholder': "e.g. 'The Royal Gazette'"})

    channel_url = String(label='URL of Channel',
                         description="What is the url or social media handle of the news source?")

    verified_account = Boolean(new=False, edit=False, queryable=True)

    alternate_names = ListString(description='Is the news source known by alternative names (e.g. Krone, Die Kronen Zeitung)?',
                                 render_kw={
                                     'placeholder': 'Separate by comma'},
                                 overwrite=True)

    transcript_kind = SingleChoice(description="What kind of show is transcribed?",
                                   choices={'tv':  "TV (broadcast, cable, satellite, etc)",
                                            'radio': "Radio",
                                            "podcast": "Podcast",
                                            'NA': "Don't know / NA"},
                                   queryable=True)

    website_allows_comments = SingleChoice(description='Does the online news source have user comments below individual news articles?',
                                           choices={'yes': 'Yes',
                                                    'no': 'No',
                                                    'NA': "Don't know / NA"},
                                           queryable=True)

    website_comments_registration_required = SingleChoice(label="Registraion required for posting comments",
                                                          description='Is a registration or an account required to leave comments?',
                                                          choices={'yes': 'Yes',
                                                                   'no': 'No',
                                                                   'NA': "Don't know / NA"})

    date_founded = Year(description="What year was the news source date_founded?",
                   overwrite=True,
                   queryable=True)

    publication_kind = MultipleChoice(description='What label or labels describe the main source?',
                                      choices={'newspaper': 'Newspaper',
                                               'news site': 'News Site',
                                               'news agency': 'News Agency',
                                               'magazine': 'Magazine',
                                               'tv show': 'TV Show / TV Channel',
                                               'radio show': 'Radio Show / Radio Channel',
                                               'podcast': 'Podcast',
                                               'news blog': 'News Blog',
                                               'alternative media': 'Alternative Media'},
                                      tom_select=True,
                                      required=True,
                                      queryable=True)

    special_interest = Boolean(description='Does the news source have one main topical focus?',
                               label='Yes, is a special interest publication',
                               queryable=True,
                               query_label="Special Interest Publication")

    topical_focus = MultipleChoice(description="What is the main topical focus of the news source?",
                                   choices={
                                       'economy': 'Business, Economy, Finance & Stocks',
                                       'education': 'Education',
                                       'environment': 'Environment',
                                       'health': 'Health',
                                       'media': 'Media',
                                       'politics': 'Politics',
                                       'religion': 'Religion',
                                       'society': 'Society & Panorama',
                                       'science': 'Science & Technology',
                                       'youth': 'Youth'
                                   },
                                   tom_select=True,
                                   queryable=True)

    publication_cycle = SingleChoice(description="What is the publication cycle of the source?",
                                     choices={'continuous': 'Continuous',
                                                 'daily': 'Daily (7 times a week)',
                                                 'multiple times per week': 'Multiple times per week',
                                                 'weekly': 'Weekly',
                                                 'twice a month': 'Twice a month',
                                                 'monthly': 'Monthly',
                                                 'less than monthly': 'Less frequent than monthly',
                                                 'NA': "Don't Know / NA"},
                                     required=True,
                                     queryable=True)

    publication_cycle_weekday = MultipleChoiceInt(description="Please indicate the specific day(s) when the news source publishes.",
                                                  choices={"1": 'Monday',
                                                           "2": 'Tuesday',
                                                           "3": 'Wednesday',
                                                           "4": 'Thursday',
                                                           "5": 'Friday',
                                                           "6": 'Saturday',
                                                           "7": 'Sunday',
                                                           'NA': "Don't Know / NA"},
                                                  tom_select=True)

    geographic_scope = SingleChoice(description="What is the geographic scope of the news source?",
                                    choices={'multinational': 'Multinational',
                                             'national': 'National',
                                             'subnational': 'Subnational'},
                                    required=True,
                                    radio_field=True,
                                    queryable=True)

    country = SourceCountrySelection(label='Countries',
                                     description='Which countries are in the geographic scope?',
                                     required=True,
                                     queryable=True)

    geographic_scope_subunit = SubunitAutocode(label='Subunits',
                                               description='What is the subnational scope?',
                                               tom_select=True,
                                               queryable=True)

    languages = MultipleChoice(description="In which language(s) does the news source publish its news texts?",
                               required=True,
                               choices=icu_codes,
                               tom_select=True,
                               queryable=True)

    payment_model = SingleChoice(description="Is the content produced by the news source accessible free of charge?",
                                 choices={'free': 'All content is free of charge',
                                             'partly free': 'Some content is free of charge',
                                             'not free': 'Paid content only',
                                             'NA': "Don't Know / NA"},
                                 required=True,
                                 radio_field=True,
                                 queryable=True)

    contains_ads = SingleChoice(description="Does the news source contain advertisements?",
                                choices={'yes': 'Yes',
                                         'no': 'No',
                                                'non subscribers': 'Only for non-subscribers',
                                                'NA': "Don't Know / NA"},
                                required=True,
                                radio_field=True,
                                queryable=True)

    audience_size = ListYear(edit=False,
                             facets=[Facet("unit", queryable=True, choices=['followers', 'subscribers', 'copies sold', 'likes', 'daily visitors']),
                                     Facet("count", dtype=int, queryable=True, comparison_operators={
                                           'gt': 'greater', 'lt': 'less'}),
                                     Facet("data_from")]
                             )

    publishes_org = OrganizationAutocode('publishes',
                                         label='Published by')

    publishes_person = OrganizationAutocode('publishes',
                                            label='Published by person')

    channel_epaper = SingleChoice(description='Does the print news source have an e-paper version?',
                                  choices={'yes': 'Yes',
                                           'no': 'No',
                                           'NA': "Don't know / NA"},
                                  queryable=True,
                                  query_label="E-Paper Available")

    sources_included = ReverseListRelationship('sources_included',
                                               relationship_constraint=[
                                                   'Archive', 'Dataset', 'Corpus', 'ResearchPaper'],
                                               query_label='News source included in these resources',
                                               queryable=True,
                                               new=False,
                                               edit=False)

    archive_sources_included = ReverseListRelationship('sources_included',
                                                       relationship_constraint='Archive',
                                                       description="Are texts from the news source available for download in one or several of the following data archives?",
                                                       label='News source included in these archives')

    dataset_sources_included = ReverseListRelationship('sources_included',
                                                       relationship_constraint='Dataset',
                                                       description="Is the news source included in one or several of the following annotated media text data sets?",
                                                       label='News source included in these datasets')

    corpus_sources_included = ReverseListRelationship('sources_included',
                                                      relationship_constraint='Corpus',
                                                      description="Is the news source included in one or several of the following corpora?",
                                                      label='News source included in these corpora')

    party_affiliated = SingleChoice(description='Is the news source close to a political party?',
                                    choices={'NA': "Don't know / NA",
                                             'yes': 'Yes',
                                             'no': 'No',
                                             },
                                    queryable=True)

    defunct = Boolean(description="Is the news source defunct or out of business?",
                      queryable=True)

    related = MutualListRelationship(
        allow_new=True, autoload_choices=False, relationship_constraint='Source')

class Government(Entry):

    __description__ = "national, supranational or subnational executives"

    country = SingleRelationship(relationship_constraint=["Country", "Multinational"],
                                 queryable=True,
                                 required=True)
    
    languages = ListRelationship(relationship_constraint=["Language"],
                                 queryable=True,
                                 autoload_choices=True)
    
    geographic_scope = SingleChoice(description="What is the geographic scope of this government?",
                                    choices={'multinational': 'Multinational',
                                             'national': 'National',
                                             'subnational': 'Subnational'},
                                    default="national",
                                    required=True,
                                    radio_field=True,
                                    queryable=True)
    
    subnational = SingleRelationship()
    
    url = String(label="URL", description="Official website of the government")

class Parliament(Entry):

    __description__ = "national, supranational or subnational legislative bodies"

    country = SingleRelationship(relationship_constraint=["Country", "Multinational"],
                                 queryable=True,
                                 required=True)
    
    languages = ListRelationship(relationship_constraint=["Language"],
                                 queryable=True,
                                 autoload_choices=True)
    
    geographic_scope = SingleChoice(description="What is the geographic scope of this parliament?",
                                    choices={'multinational': 'Multinational',
                                             'national': 'National',
                                             'subnational': 'Subnational'},
                                    default="national",
                                    required=True,
                                    radio_field=True,
                                    queryable=True)
    
    url = String(label="URL", description="Official website of the parliament")

class Person(Entry):

    is_politician = Boolean(label="Politician", description="Is the person a politician?",
                            queryable=True)
    
    country = SingleRelationship(relationship_constraint=["Country"], 
                                 queryable=True)
    
    url = String(label="URL", description="Website related to the person")

class Channel(Entry):

    __permission_new__ = USER_ROLES.Admin
    __permission_edit__ = USER_ROLES.Admin


class Country(Entry):

    __permission_new__ = USER_ROLES.Admin
    __permission_edit__ = USER_ROLES.Admin

    iso_3166_1_2 = String(permission=USER_ROLES.Admin, directives=["@index(exact)"])
    iso_3166_1_3 = String(permission=USER_ROLES.Admin, directives=["@index(exact)"])
    opted_scope = Boolean(description="Is country in the scope of OPTED?",
                          label='Yes, in scope of OPTED')


class Multinational(Entry):

    __permission_new__ = USER_ROLES.Admin
    __permission_edit__ = USER_ROLES.Admin

    membership = ListRelationship(description="Which countries are part of this multinational construct?",
                                  relationship_constraint=["Country"])


class Subnational(Entry):

    __permission_new__ = USER_ROLES.Reviewer
    __permission_edit__ = USER_ROLES.Reviewer

    country = SingleRelationship(required=True,
                                 tom_select=True,
                                 autoload_choices=True,
                                 overwrite=True,
                                 relationship_constraint='Country')
    iso_3166_1_3 = String(description="ISO 3166-1 Alpha 3 code of the country this subunit belongs to",
                          directives=["@index(exact)"])
    location_point = Geo(edit=False, new=False)


class Archive(Entry):

    name = String(
        description="What is the name of the archive?", required=True)

    alternate_names = ListString(description="Does the archive have other names?",
                                 render_kw={
                                     'placeholder': 'Separate by comma ","'},
                                 overwrite=True)

    description = String(large_textfield=True)

    url = String()

    access = SingleChoice(choices={'free': 'Free',
                                   'restricted': 'Restricted'})
    sources_included = ListRelationship(
        relationship_constraint='Source')
    fulltext = Boolean(description='Archive contains fulltext')
    country = ListRelationship(relationship_constraint=[
                               'Country', 'Multinational'], autoload_choices=True)
    text_units = ListRelationship(description="List of text units available in the data archive (e.g., sentences, paragraphs, tweets, news articles, summaries, headlines)",
                                  relationship_constraint="UnitOfAnalysis",
                                  render_kw={
                                      'placeholder': 'Select multiple...'},
                                  autoload_choices=True,
                                  allow_new=True)


class Dataset(Entry):

    name = String(
        description="What is the name of the dataset?", required=True)

    alternate_names = ListString(description="Does the dataset have other names?",
                                 render_kw={
                                     'placeholder': 'Separate by comma ","'},
                                 overwrite=True)

    authors = OrderedListString(delimiter=';',
                                render_kw={'placeholder': 'Separate by semicolon ";"'}, tom_select=True,
                                required=True,
                                directives=['@index(term)'])

    published_date = Year(label='Year of publication',
                          description="Which year was the dataset published?")

    last_updated = DateTime(
        description="When was the dataset last updated?", new=False)

    url = String(label="URL", description="Link to the dataset", required=True)
    doi = String(label='DOI', directives=['@index(hash)'])
    arxiv = String(label="arXiv", directives=['@index(hash)'])

    description = String(
        large_textfield=True, description="Please provide a short description for the tool")

    access = SingleChoice(choices={'free': 'Free',
                                   'restricted': 'Restricted'})

    country = ListRelationship(description="Does the dataset have a specific geographic coverage?",
                               relationship_constraint=[
                                   'Country', 'Multinational'],
                               autoload_choices=True,
                               render_kw={'placeholder': 'Select multiple countries...'})

    languages = MultipleChoice(description="Which languages are covered in the dataset?",
                               choices=icu_codes,
                               tom_select=True,
                               render_kw={'placeholder': 'Select multiple...'})

    start_date = DateTime(description="Start date of the dataset")

    end_date = DateTime(description="End date of the dataset")

    file_format = ListRelationship(description="In which file format(s) is the dataset stored?",
                                   autoload_choices=True,
                                   relationship_constraint="FileFormat",
                                   render_kw={'placeholder': 'Select multiple...'})

    sources_included = ListRelationship(relationship_constraint='Source',
                                        render_kw={'placeholder': 'Select multiple...'})

    materials = ListString(description="Are there additional materials for the dataset? (e.g., codebook, documentation, etc)",
                           tom_select=True, render_kw={'placeholder': 'please paste the URLs to the materials here!'})

    initial_source = ListRelationship(description="If the dataset is derived from another corpus or dataset, the original source can be linked here",
                                      relationship_constraint=[
                                          'Dataset', 'Corpus'],
                                      render_kw={'placeholder': 'Select multiple...'})

    meta_vars = ListRelationship(description="List of meta data included in the dataset (e.g., date, language, source, medium)",
                                 relationship_constraint="MetaVariable",
                                 render_kw={
                                     'placeholder': 'Select multiple...'},
                                 autoload_choices=True)

    concept_vars = ListRelationship(description="List of variables based on concepts (e.g. sentiment, frames, etc)",
                                    relationship_constraint="ConceptVariable",
                                    render_kw={
                                        'placeholder': 'Select multiple...'},
                                    autoload_choices=True
                                    )


class Corpus(Entry):

    name = String(description="What is the name of the corpus?", required=True)

    alternate_names = ListString(description="Does the corpus have other names?",
                                 render_kw={
                                     'placeholder': 'Separate by comma ","'},
                                 overwrite=True)

    authors = OrderedListString(delimiter=';',
                                render_kw={'placeholder': 'Separate by semicolon ";"'}, tom_select=True,
                                required=True,
                                directives=['@index(term)'])

    published_date = Year(label='Year of publication',
                          description="Which year was the corpus published?")

    last_updated = DateTime(
        description="When was the corpus last updated?", new=False)

    url = String(label="URL", description="Link to the corpus", required=True)
    doi = String(label='DOI')
    arxiv = String(label="arXiv")

    description = String(
        large_textfield=True, description="Please provide a short description for the corpus")

    access = SingleChoice(choices={'free': 'Free',
                                   'restricted': 'Restricted'})

    country = ListRelationship(description="Does the corpus have a specific geographic coverage?",
                               relationship_constraint=[
                                   'Country', 'Multinational'],
                               autoload_choices=True,
                               render_kw={'placeholder': 'Select multiple countries...'})

    languages = MultipleChoice(description="Which languages are covered in the corpus?",
                               choices=icu_codes,
                               tom_select=True,
                               render_kw={'placeholder': 'Select multiple...'})

    start_date = DateTime(description="Start date of the corpus")

    end_date = DateTime(description="End date of the corpus")

    file_format = ListRelationship(description="In which file format(s) is the corpus stored?",
                                   autoload_choices=True,
                                   relationship_constraint="FileFormat",
                                   render_kw={'placeholder': 'Select multiple...'})

    materials = ListString(description="Are there additional materials for the corpus? (e.g., codebook, documentation, etc)",
                           tom_select=True, render_kw={'placeholder': 'please paste the URLs to the materials here!'})

    sources_included = ListRelationship(relationship_constraint='Source',
                                        render_kw={'placeholder': 'Select multiple...'})

    text_units = ListRelationship(description="List of text units included in the corpus (e.g., sentences, paragraphs, tweets, news articles, summaries, headlines)",
                                  relationship_constraint="UnitOfAnalysis",
                                  render_kw={
                                      'placeholder': 'Select multiple...'},
                                  autoload_choices=True,
                                  allow_new=True)

    meta_vars = ListRelationship(description="List of meta data included in the corpus (e.g., date, language, source, medium)",
                                 relationship_constraint="MetaVariable",
                                 render_kw={
                                     'placeholder': 'Select multiple...'},
                                 autoload_choices=True)

    concept_vars = ListRelationship(description="List of annotations included in the corpus (e.g., sentiment, topic, named entities)",
                                    relationship_constraint="ConceptVariable",
                                    render_kw={
                                        'placeholder': 'Select multiple...'},
                                    autoload_choices=True)

    initial_source = ListRelationship(description="If the corpus is derived from another corpus or dataset, the original source can be linked here",
                                      relationship_constraint=[
                                          'Dataset', 'Corpus'],
                                      render_kw={'placeholder': 'Select multiple...'})


class Tool(Entry):

    name = String(description="What is the name of the tool?", required=True)

    alternate_names = ListString(description="Does the tool have other names?",
                                 render_kw={
                                     'placeholder': 'Separate by comma ","'},
                                 overwrite=True)

    authors = OrderedListString(delimiter=';',
                                render_kw={'placeholder': 'Separate by semicolon ";"'}, tom_select=True,
                                required=True,
                                directives=['@index(term)'])

    published_date = Year(label='Year of publication',
                          description="Which year was the tool published?",
                          queryable=True,
                          comparison_operators={'ge': 'after', 'le': 'before', 'eq': 'exact'})

    last_updated = DateTime(
        description="When was the tool last updated?", new=False)

    url = String(label="URL", description="Link to the tool", required=True)
    doi = String(label='DOI',
                 overwrite=True)
    arxiv = String(label='arXiv',
                   overwrite=True)
    cran = String(label="CRAN", description="CRAN Package name",
                  render_kw={
                      'placeholder': 'usually this is filled in automatically...'},
                  overwrite=True)

    pypi = String(label="PyPi", description="PyPi Project name",
                  render_kw={
                      'placeholder': 'usually this is filled in automatically...'},
                  overwrite=True)

    github = GitHubAuto(label="Github", description="Github repository",
                        render_kw={
                            'placeholder': 'If the tool has a repository on Github you can add this here.'},
                        overwrite=True)

    description = String(large_textfield=True, description="Please provide a short description for the tool",
                         overwrite=True)

    platform = MultipleChoice(description="For which kind of operating systems is the tool available?",
                              choices={'windows': 'Windows',
                                       'linux': 'Linux',
                                       'macos': 'macOS'},
                              required=True,
                              tom_select=True,
                              queryable=True)

    programming_languages = MultipleChoice(label="Programming Languages",
                                           description="Which programming languages are used for the tool? \
                                            Please also include language that can directly interface with this tool.",
                                           choices=programming_languages,
                                           required=False,
                                           tom_select=True,
                                           queryable=True)

    open_source = SingleChoice(description="Is this tool open source?",
                               choices={'NA': 'NA / Unknown',
                                        'yes': 'Yes',
                                        'no': 'No, proprietary'},
                               queryable=True)

    license = String(description="What kind of license attached to the tool?")

    user_access = SingleChoice(description="How can the user access the tool?",
                               choices={'NA': 'NA / Unknown',
                                        'free': 'Free',
                                        'registration': 'Registration',
                                        'request': 'Upon Request',
                                        'purchase': 'Purchase'},
                               queryable=True)

    used_for = ListRelationship(description="Which operations can the tool perform?",
                                relationship_constraint="Operation",
                                autoload_choices=True,
                                required=True,
                                queryable=True)

    concept_vars = ListRelationship(description="Which concepts can the tool measure (e.g. sentiment, frames, etc)",
                                    relationship_constraint="ConceptVariable",
                                    autoload_choices=True,
                                    queryable=True,
                                    query_label='Concept Variables')

    graphical_user_interface = Boolean(description="Does the tool have a graphical user interface?",
                                       label="Yes, it does have a GUI",
                                       default=False,
                                       queryable=True)

    channels = ListRelationship(description="Is the tool designed for specific channels?",
                                autoload_choices=True,
                                relationship_constraint="Channel")

    language_independent = Boolean(description="Is the tool language independent?",
                                   label="Yes",
                                   queryable=True)

    languages = MultipleChoice(description="Which languages does the tool support?",
                               choices=icu_codes,
                               tom_select=True,
                               queryable=True)

    input_file_format = ListRelationship(description="Which file formats does the tool take as input?",
                                         autoload_choices=True,
                                         relationship_constraint="FileFormat",
                                         queryable=True)

    output_file_format = ListRelationship(description="Which file formats does the tool output?",
                                          autoload_choices=True,
                                          relationship_constraint="FileFormat",
                                          queryable=True)

    author_validated = SingleChoice(description="Do the authors of the tool report any validation?",
                                    choices={'NA': 'NA / Unknown',
                                             'yes': 'Yes',
                                             'no': 'No, not reported'},
                                    queryable=True)

    validation_corpus = ListRelationship(description="Which corpus was used to validate the tool?",
                                         autoload_choices=True,
                                         relationship_constraint="Corpus",
                                         queryable=True)

    materials = ListString(description="Are there additional materials for the tool? (e.g., FAQ, Tutorials, Website, etc)",
                           tom_select=True, render_kw={'placeholder': 'please paste the URLs to the materials here!'})

    related_publications = ReverseListRelationship('tools_used',
                                                   description="Which research publications are using this tool?",
                                                   autoload_choices=True,
                                                   new=False,
                                                   relationship_constraint="ResearchPaper")

    defunct = Boolean(description="Is the tool defunct?", queryable=True)


class ResearchPaper(Entry):

    name = String(new=False, edit=False, hidden=True)
    alternate_names = ListString(
        new=False, edit=False, hidden=True, required=False)

    title = String(description="What is the title of the publication?", required=True,
                   directives=['@index(term)'])

    authors = OrderedListString(delimiter=';',
                                render_kw={'placeholder': 'Separate by semicolon ";"'}, tom_select=True,
                                required=True,
                                directives=['@index(term)'])

    published_date = Year(label='Year of publication',
                          description="Which year was the publication published?",
                          required=True)

    paper_kind = String(
        description="What kind of publcation is this? (e.g., Journal article, book section)")

    journal = String(description="In which journal was it published?")

    url = String(
        label="URL", description="Link to the publication", required=True)
    doi = String(label='DOI')
    arxiv = String(label='arXiv')

    description = String(
        large_textfield=True, description="Abstract or a short description of the publication")

    tools_used = ListRelationship(description="Which research tool(s) where used in the publication?",
                                  autoload_choices=True,
                                  relationship_constraint="Tool")

    sources_included = ListRelationship(description="Which news sources are investigated in this publication?",
                                        autoload_choices=False,
                                        relationship_constraint="Source")

    text_units = ListRelationship(description="List of text units analysed in the publication (e.g., sentences, paragraphs, tweets, news articles, summaries, headlines)",
                                  relationship_constraint="UnitOfAnalysis",
                                  render_kw={
                                      'placeholder': 'Select multiple...'},
                                  autoload_choices=True,
                                  allow_new=True)

    datasets_used = ListRelationship(description="Which dataset(s) where used in the publication?",
                                     autoload_choices=True,
                                     relationship_constraint="Dataset")

    corpus_used = ListRelationship(description="Which corpora where used in the publication?",
                                   autoload_choices=True,
                                   relationship_constraint="Corpus")

    country = ListRelationship(description="Does the publication have some sort of country that it focuses on?",
                               autoload_choices=True,
                               relationship_constraint="Country")

"""
    Authors
"""

class Author(Entry):
    orcid = String(label="ORCID", directives=["@index(hash)"])
    url = String(label="URL", description="Website of author")
    openalex = ListString(label="OpenAlex ID", description="ID(s) of the author on OpenAlex")

"""
    Meta Predicates / Tag Like Types
"""


class Language(Entry):

    iso_639_2 = String(label="ISO-639-2 Code",
                       description="ISO code with 2 characters (e.g. 'en')",
                       directives=['@index(exact)'])

    iso_639_3 = String(label="ISO-639-3 Code",
                       description="ISO code with 3 characters (e.g. 'eng')",
                       directives=['@index(exact)'])

    icu_code = String(label="ICU Locale Code",
                      description="ICU locale for scripts (e.g. 'en_GB', 'zh_Hans')",
                      directives=['@index(exact)'])


class ProgrammingLanguage(Entry):

    pass


class Operation(Entry):

    pass


class FileFormat(Entry):

    mime_type = String(label="MIME type")


class MetaVariable(Entry):

    pass


class ConceptVariable(Entry):

    pass


class UnitOfAnalysis(Entry):

    pass


"""
    Collections / User Curated Entries
"""


class Collection(Entry):

    creators = ListRelationship(
        relationship_constraint="User", default=get_current_user_uid)

    entries_included = ListRelationship(description="What are the entries that you want to include in this collection?",
                                        autoload_choices=False,
                                        relationship_constraint=["Dataset",
                                                                 "Archive",
                                                                 "NewsSource",
                                                                 "JournalisticBrand",
                                                                 "Government",
                                                                 "Parliament",
                                                                 "Person",
                                                                 "PoliticalParty",
                                                                 "Organization"])
    
    languages = ListRelationship(description="Which languages are related to this collection?",
                                 relationship_constraint=["Language"])
    
    countries = ListRelationship(description="Which countries, multinational constructs, or subunits are related to this collection?",
                                 relationship_constraint=["Country", "Multinational", "Subnational"])
    
    tools = ListRelationship(description="Which tools are related to this collection?",
                                 relationship_constraint=["Tool"])
    
    references = ListRelationship(description="Is the collection is directly related to a paper, or derived from a series of papers / publications?",
                                 relationship_constraint=["ScientificPublication"])
    
    materials = ListRelationship(description="Are there any learning materials related to this collection?",
                                 relationship_constraint=["LearningMaterial"])
    
    concept_variables = ListRelationship(description="Is this collection about concepts or related to theoretical constructs?",
                                 relationship_constraint=["ConceptVariable"])


"""
    System Types
"""


class File(Schema):

    __permission_new__ = 99
    __permission_edit__ = 99

    uid = UIDPredicate()

    _download_url = String(description="location of the resource")
    _path = String(description="location on local disk")
    file_format = SingleRelationship(relationship_constraint="FileFormat")


class Notification(Schema):

    __permission_new__ = 99
    __permission_edit__ = 99

    uid = UIDPredicate()

    _notification_date = DateTime(default=datetime.datetime.now,
                                  directives=['@index(hour)'])
    _read = Boolean(default=False)
    _notify = SingleRelationship(relationship_constraint="User",
                                 required=True)
    
    _title = String(default="Notification")
    _content = String()
    _email_dispatched = Boolean(default=False)


class Comment(Schema):

    __permission_new__ = USER_ROLES.Contributor
    __permission_edit__ = USER_ROLES.Contributor

    uid = UIDPredicate()

    _creator = SingleRelationship(relationship_constraint='User',
                                  required=True)
    
    _comment_date = DateTime(default=datetime.datetime.now,
                             directives=['@index(hour)'])
    
    _comment_edited = DateTime(default=datetime.datetime.now,
                               directives=['@index(hour)'])
    
    _comment_on = SingleRelationship(relationship_constraint="Entry")
    content = String()


class Rejected(Schema):

    __permission_new__ = 99
    __permission_edit__ = 99

    uid = UIDPredicate()

    _date_created = DateTime(directives=['@index(hour)'])
    _date_modified = DateTime(directives=['@index(hour)'])

    _added_by = SingleRelationship(label="Added by",
                                   relationship_constraint="User",
                                   new=False,
                                   edit=False,
                                   read_only=True,
                                   hidden=True)

    _reviewed_by = SingleRelationship(label="Reviewed by",
                                      relationship_constraint="User",
                                      new=False,
                                      edit=False,
                                      read_only=True,
                                      hidden=True)
    _edited_by = SingleRelationship(label="Edited by",
                                    relationship_constraint="User",
                                    new=False,
                                    edit=False,
                                    read_only=True,
                                    hidden=True)

    _former_types = ListString()

    entry_review_status = String(default="rejected")
