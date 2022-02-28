from flaskinventory.flaskdgraph.dgraph_types import (UID, NewID, Predicate, Scalar,
                                        GeoScalar, Variable, make_nquad, dict_to_nquad)
from flaskinventory.flaskdgraph.utils import validate_uid
from flaskinventory.errors import InventoryValidationError, InventoryPermissionError
from flaskinventory.auxiliary import icu_codes
from flaskinventory.add.external import (geocode, instagram,
                                         parse_meta, siterankdata, find_sitemaps, find_feeds,
                                         build_url, twitter, facebook, get_wikidata)
from flaskinventory.users.constants import USER_ROLES
from flaskinventory.users.dgraph import User
from flaskinventory import dgraph
from flask import current_app

from flaskinventory.main.model import (entry_fields, organization_fields)

# External Utilities

from slugify import slugify
import secrets

import datetime
from dateutil import parser as dateparser


class Sanitizer:
    """ Base Class for validating data and generating mutation object
        Validates all predicates from dgraph type 'Entry'
        also keeps track of user & ip address.
        Relevant return attributes are upsert_query (string), set_nquads (string), delete_nquads (string)
    """

    upsert_query = None

    def __init__(self, data: dict, user: User, ip: str, fields: list = None, **kwargs):

        self._validate_inputdata(data, user, ip)
        self.fields = entry_fields
        if fields:
            self.fields += fields
        
        if user.user_role < USER_ROLES.Contributor:
            raise InventoryPermissionError

        self.data = data
        self.user = user
        self.user_ip = ip

        self.is_upsert = kwargs.get('is_upsert', False)
        self.overwrite = {}
        self.newsubunits = []

        self.entry = {}
        self._parse()

    @staticmethod
    def _validate_inputdata(data: dict, user: User, ip: str) -> bool:
        if not isinstance(data, dict):
            raise TypeError('Data object has to be type dict!')
        if not isinstance(user, User):
            raise TypeError('User Object is not class User!')
        if not isinstance(ip, str):
            raise TypeError('IP Address is not string!')
        return True

    @classmethod
    def edit(cls, data: dict, user: User, ip: str):
        cls._validate_inputdata(data, user, ip)

        if 'uid' not in data.keys():
            raise InventoryValidationError(
                'You cannot edit an entry without a UID')

        check = cls._check_entry(data['uid'])
        if not check:
            raise InventoryValidationError(
                f'Entry can not be edited! UID does not exist: {data["uid"]}')

        if not user.user_role >= USER_ROLES.Reviewer or check.get('entry_added').get('uid') == user.id:
            raise InventoryPermissionError(
                'You do not have the required permissions to edit this entry!')

        return cls(data, user, ip, is_upsert=True)

    @property
    def set_nquads(self):
        nquads = dict_to_nquad(self.entry)
        return " \n".join(nquads)

    @property
    def delete_nquads(self):
        if self.is_upsert:
            # for upserts, we first have to delete all list type predicates
            # otherwise, the user cannot remove relationships, but just add to them
            del_obj = []

            for key, val in self.overwrite.items():
                for predicate in list(set(val)):
                    del_obj.append({'uid': key, predicate: '*'})

            nquads = [" \n".join(dict_to_nquad(obj)) for obj in del_obj]
            return " \n".join(nquads)

        return None

    @staticmethod
    def _check_entry(uid):
        query = f'''{{ q(func: uid({uid})) @filter(has(dgraph.type))'''
        query += "{ unique_name dgraph.type entry_review_status entry_added { uid } } }"
        data = dgraph.query(query)

        if len(data['q']) == 0:
            return False

        return data['q'][0]

    def _add_entry_meta(self, entry, newentry=False):
        # verify that dgraph.type is not added to self if the entry already exists
        if entry == self.entry and not self.is_upsert:
            if entry.get('dgraph.type'):
                if type(entry['dgraph.type']) != list:
                    entry['dgraph.type'] = [entry['dgraph.type']]
                entry['dgraph.type'].append(
                    'Entry') if 'Entry' not in entry['dgraph.type'] else None
            else:
                entry['dgraph.type'] = ["Entry"]

        facets = {'timestamp': datetime.datetime.now(
            datetime.timezone.utc),
            'ip': self.user_ip}
        if not newentry:
            entry['entry_edit_history'] = UID(self.user.uid, facets=facets)
        else:
            entry['entry_added'] = UID(self.user.uid, facets=facets)
            entry['entry_review_status'] = 'pending'
            entry['creation_date'] = datetime.datetime.now(
                datetime.timezone.utc)

        return entry

    def _geo_query_subunit(self, query):
        geo_result = geocode(query)
        if geo_result:
            dql_string = f'''{{ q(func: eq(country_code, "{geo_result['address']['country_code']}")) @filter(type("Country")) {{ uid }} }}'''
            dql_result = dgraph.query(dql_string)
            try:
                country_uid = dql_result['q'][0]['uid']
            except Exception:
                raise InventoryValidationError(
                    f"Country not found in inventory: {geo_result['address']['country_code']}")
            geo_data = GeoScalar('Point', [
                float(geo_result.get('lon')), float(geo_result.get('lat'))])

            name = None
            other_names = [query]
            if geo_result['namedetails'].get('name'):
                other_names.append(geo_result['namedetails'].get('name'))
                name = geo_result['namedetails'].get('name')

            if geo_result['namedetails'].get('name:en'):
                other_names.append(geo_result['namedetails'].get('name:en'))
                name = geo_result['namedetails'].get('name:en')

            other_names = list(set(other_names))

            if not name:
                name = query

            if name in other_names:
                other_names.remove(name)

            new_subunit = {'name': name,
                           'country': UID(country_uid),
                           'other_names': other_names,
                           'location_point': geo_data,
                           'country_code': geo_result['address']['country_code']}

            if geo_result.get('extratags'):
                if geo_result.get('extratags').get('wikidata'):
                    if geo_result.get('extratags').get('wikidata').lower().startswith('q'):
                        try:
                            new_subunit['wikidataID'] = int(geo_result.get(
                                'extratags').get('wikidata').lower().replace('q', ''))
                        except Exception as e:
                            current_app.logger.debug(
                                f'Could not parse wikidata ID in subunit: {e}')

            return new_subunit
        else:
            return False

    def _resolve_subunit(self, subunit):
        geo_query = self._geo_query_subunit(subunit)
        if geo_query:
            geo_query['dgraph.type'] = ['Subunit']
            geo_query = self._add_entry_meta(geo_query, newentry=True)
            geo_query['unique_name'] = f"{slugify(subunit, separator='_')}_{geo_query['country_code']}"
            # prevent duplicates
            duplicate_check = dgraph.get_uid(
                'unique_name', geo_query['unique_name'])
            if duplicate_check:
                geo_query = {'uid': UID(duplicate_check)}
            else:
                geo_query['uid'] = NewID(
                    f"_:{slugify(secrets.token_urlsafe(8))}")
                self.newsubunits.append(geo_query)

            return geo_query
        else:
            raise InventoryValidationError(
                f'Invalid Data! Could not resolve geographic subunit {subunit}')

    def _parse(self):
        for item in dir(self):
            if item.startswith('parse_'):
                m = getattr(self, item)
                if callable(m):
                    m()

        if self.is_upsert:
            self.overwrite[self.entry['uid']] = []
            
        for item in self.fields:
            if self.data.get(item.predicate):
                validated = item.validate(self.data[item.predicate])
                if type(validated) == dict:
                    self.entry = {**self.entry, **validated}
                elif type(validated) == list and item.predicate in self.entry.keys():
                    self.entry[item.predicate] += validated
                elif type(validated) == set and item.predicate in self.entry.keys():
                    self.entry[item.predicate] = set.union(validated, self.entry[item.predicate])
                else:
                    self.entry[item.predicate] = validated
            elif hasattr(item, 'autocode'):
                if item.autoinput in self.data.keys():
                    autocoded = item.autocode(self.data[item.autoinput])
                    if type(autocoded) == dict:
                        self.entry = {**self.entry, **autocoded}
                    elif type(autocoded) == list and item.predicate in self.entry.keys():
                        self.entry[item.predicate] += autocoded
                    elif type(autocoded) == set and item.predicate in self.entry.keys():
                        self.entry[item.predicate] = set.union(autocoded, self.entry[item.predicate])
                    else:
                        self.entry[item.predicate] = autocoded

            elif item.default:
                self.entry[item.predicate] = item.default

            if hasattr(item, 'allow_new'):
                if item.allow_new:
                    print('generate unique name for new item')

            if item.overwrite and self.is_upsert:
                self.overwrite[self.entry['uid']].append(item.predicate)
        
        if not self.is_upsert:
            self.generate_unique_name()

    def parse_uid(self):
        # we already checked if the UID is valid with the edit() constructor
        uid = self.data.get('uid', '_:newentry')

        if not validate_uid(uid):
            self.entry['uid'] = NewID(uid)
            self.entry = self._add_entry_meta(self.entry, newentry=True)
        else:
            self.entry['uid'] = UID(uid)
            self.entry = self._add_entry_meta(self.entry)
            self.is_upsert = True

    def parse_entry_review_status(self):
        if self.data.get('accept'):
            if self.user.user_role < USER_ROLES.Reviewer:
                raise InventoryPermissionError(
                    'You do not have the required permissions to change the review status!')
            self.entry['entry_review_status'] = 'accepted'
            self.entry['reviewed_by'] = UID(self.user.uid, facets={
                                            'timestamp': datetime.datetime.now(datetime.timezone.utc)})
        elif self.data.get('entry_review_status'):
            if self.user.user_role < USER_ROLES.Reviewer:
                raise InventoryPermissionError(
                    'You do not have the required permissions to change the review status!')

    def parse_unique_name(self):
        if self.data.get('unique_name'):
            unique_name = self.data['unique_name'].strip().lower()
            if self.is_upsert:
                check = dgraph.get_uid('unique_name', unique_name)
                if check:
                    if check != str(self.entry['uid']):
                        raise InventoryValidationError(
                            'Unique Name already taken!')
            self.entry['unique_name'] = unique_name
        else:
            name = slugify(self.data.get('name'), separator="_")
            query_string = f'''{{
                                field1 as var(func: eq(unique_name, "{name}"))
                                data1(func: uid(field1)) {{
                                        unique_name
                                        uid
                                }}
                                
                            }}'''

            result = dgraph.query(query_string)

            if len(result['data1']) == 0:
                self.entry['unique_name'] = name
            else:
                self.entry['unique_name'] = f'{name}_{secrets.token_urlsafe(4)}'

    def parse_wikidata(self):
        if not self.is_upsert:
            wikidata = get_wikidata(self.data.get('name'))
            if wikidata:
                for key, val in wikidata.items():
                    if key not in self.entry.keys():
                        self.entry[key] = val
                    elif key == 'other_names':
                        if 'other_names' not in self.entry.keys():
                            self.entry['other_names'] = []
                        self.entry[key] += val

    def generate_unique_name(self):
        name = slugify(self.data.get('name'), separator="_")
        query_string = f'''{{
                            field1 as var(func: eq(unique_name, "{name}"))
                            data1(func: uid(field1)) {{
                                    unique_name
                                    uid
                            }}
                            
                        }}'''

        result = dgraph.query(query_string)

        if len(result['data1']) == 0:
            self.entry['unique_name'] = name
        else:
            self.entry['unique_name'] = f'{name}_{secrets.token_urlsafe(4)}'


class OrganizationSanitizer(Sanitizer):

    def __init__(self, data, user, ip, **kwargs):

        fields = organization_fields

        super().__init__(data, user, ip, fields=fields, **kwargs)

        if not self.is_upsert:
            self.entry['dgraph.type'].append('Organization')

        


