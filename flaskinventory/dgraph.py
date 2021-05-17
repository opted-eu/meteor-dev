import json
import datetime
import math
from dateutil import parser as dateparser
import os

from flask import current_app, _app_ctx_stack, Markup
import pydgraph

from flaskinventory.auxiliary import icu_codes

class DGraph(object):
    '''Class for dgraph database connection'''

    def __init__(self, app=None):
        if app is not None:
            self.init_app(app)

    def init_app(self, app):

        app.config.setdefault('DGRAPH_ENDPOINT', 'localhost:9080')
        app.config.setdefault('DGRAPH_CREDENTIALS', None)
        app.config.setdefault('DGRAPH_OPTIONS', None)

        app.logger.info(f"Establishing connection to DGraph: {app.config['DGRAPH_ENDPOINT']}")

        self._app = app
        self.client_stub = pydgraph.DgraphClientStub(app.config['DGRAPH_ENDPOINT'], 
                                                        credentials=app.config['DGRAPH_CREDENTIALS'],
                                                        options=app.config['DGRAPH_OPTIONS'])

        self.client = pydgraph.DgraphClient(self.client_stub)

    ''' Connection Related Methods '''
    def close(self, *args):
        # Close each DGraph client stub
        self.client_stub.close()


    def teardown(self, exception):
        self._app.logger.info(f"Closing Connection: {self._app.config['DGRAPH_ENDPOINT']}")
        self.client_stub.close()

    ''' static methods '''

    @staticmethod
    def flatten_date_facets(data, field_name):
        tmp_list = []
        facet_keys = [item for item in data.keys() if item.startswith(field_name + '|')]
        facet_labels = [item.split('|')[1] for item in facet_keys]
        for index, value in enumerate(data[field_name]):
            tmp_dict = {'date': value}
            for facet, label in zip(facet_keys, facet_labels): 
                tmp_dict[label] = data[facet][str(index)]
            tmp_list.append(tmp_dict)
        data[field_name] = tmp_list
        data[field_name + '_labels'] = facet_labels
        return data

    def query(self, query_string, variables=None):
        self._app.logger.debug(f"Sending dgraph query.")
        if variables is None:
            res = self.client.txn(read_only=True).query(query_string)
        else:
            res = self.client.txn(read_only=True).query(query_string, variables=variables)
        self._app.logger.debug(f"Received response for dgraph query.")
        data = json.loads(res.json)
        return data
    
    def get_uid(self, field, value):
        query_string = f'{{ q(func: eq({field}, {value})) {{ uid {field} }} }}'
        data = self.query(query_string)
        if len(data['q']) == 0:
            return None
        return data['q'][0]['uid']

    def get_user(self, **kwargs):

        uid = kwargs.get('uid', None)
        username = kwargs.get('username', None)
        email = kwargs.get('email', None)

        if uid:
            query_func = f'{{ q(func: uid({uid}))'
        elif email:
            query_func = f'{{ q(func: eq(email, "{email}"))'
        elif username:
            query_func = f'{{ q(func: eq(username, "{username}"))'
        else:
            raise ValueError()

        query_fields =  f'{{ uid username email avatar_img date_joined }} }}'
        query_string = query_func + query_fields
        data = self.query(query_string)
        if len(data['q']) == 0:
            return None
        data = data['q'][0]
        data['date_joined'] = dateparser.parse(data['date_joined'])
        return data


    def user_login(self, email, pw):
        query_string = f'{{login_attempt(func: eq(email, "{email}")) {{ checkpwd(pw, {pw}) }} }}'
        result = self.query(query_string)
        if len(result['login_attempt']) == 0:
            return 'Invalid Email'
        else:
            return result['login_attempt'][0]['checkpwd(pw)']

    def create_user(self, user_data):
        if type(user_data) is not dict:
            raise TypeError()
        
        user_data['uid'] =  '_:newuser'
        user_data['dgraph.type'] = 'User'
        user_data['date_joined'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        user_data['avatar_img'] = os.path.join('default.jpg')
        
        txn = self.client.txn()

        try:
            response = txn.mutate(set_obj=user_data)
            txn.commit()
        except:
            response = False
        finally:
            txn.discard()

        if response:
            return response.uids['newuser']
        else: return False

    def update_entry(self, uid, input_data):
        if type(input_data) is not dict:
            raise TypeError()
        
        input_data['uid'] =  uid
        
        txn = self.client.txn()

        try:
            response = txn.mutate(set_obj=input_data)
            txn.commit()
        except:
            response = False
        finally:
            txn.discard()

        if response:
            return True
        else: return False

    def delete_entry(self, uid):

        mutation = {'uid': uid}
        txn = self.client.txn()

        try:
            response = txn.mutate(del_obj=mutation)
            txn.commit()
        except:
            response = False
        finally:
            txn.discard()

        if response:
            return True
        else: return False

    def list_posts(self, per_page=3, page=1):

        offset = per_page * (page-1)

        query_func = f'{{ posts(func: type(Post), orderdesc: date_published, first: {per_page}, offset: {offset})' 
        query_fields = '''{ 
                            uid title content date_published 
                            author { uid username display_name avatar_img } 
                            tags category { uid name }
                            }
                        total(func: type(Post)) {
                            count(uid)
                        }
                            }'''
        
        query = query_func + query_fields

        try:
            res = self.client.txn(read_only=True).query(query)
        except:
            return [], 0, 0

        data = json.loads(res.json)
        posts = data['posts']
        total = data['total'][0]['count']
        pages = math.ceil(total / per_page)
        for item in posts:
            item['date_published'] = dateparser.parse(item['date_published'])
            item['content'] = Markup(item['content'].replace('\n', '</br>'))
        
        return posts, total, pages
    
    def list_user_posts(self, uid=None, username=None, per_page=3, page=1):
        if username:
            uid = self.get_uid('username', username)
        if uid is None:
            raise ValueError
        offset = per_page * (page-1)

        query_func = f'{{ posts(func: uid({uid}))' 
        query_user = '{ uid username display_name avatar_img '
        query_posts = f'pub_posts: ~author (orderdesc: date_published) (first: {per_page}) (offset: {offset})'
        query_posts_fields = '{ uid title content date_published tags category { uid name } author { uid username display_name avatar_img} }' 
        query_total_posts = 'total_posts: count(~author) } }'
                            
        query = query_func + query_user + query_posts + query_posts_fields + query_total_posts

        res = self.client.txn(read_only=True).query(query)

        data = json.loads(res.json)
        user = data['posts'][0]
        posts = data['posts'][0]['pub_posts']
        total = data['posts'][0]['total_posts']
        pages = math.ceil(total / per_page)
        for item in posts:
            item['date_published'] = dateparser.parse(item['date_published'])
            item['content'] = Markup(item['content'].replace('\n', '</br>'))
        
        return user, posts, total, pages

    def get_post(self, uid):

        query_uid = f'{{ post(func: uid({uid})) @filter(type("Post"))' 
        query_fields = '''{ 
                            uid title content date_published 
                            author { 
                                uid username display_name avatar_img 
                                } 
                            tags category { uid name }
                        } }'''
        
        query = query_uid + query_fields

        res = self.client.txn(read_only=True).query(query)

        data = json.loads(res.json)

        if len(data['post']) == 0:
            return False

        data = data['post'][0]
        data['date_published'] = dateparser.parse(data['date_published'])
        data['content_raw'] = data['content']
        data['content'] = Markup(data['content'].replace('\n', '</br>'))
        return data

    def get_source(self, unique_name=None, uid=None):
        if unique_name:
            query_func = f'{{ source(func: eq(unique_name, "{unique_name}"))'
        elif uid:
            query_func = f'{{ source(func: uid({uid}))' 
        else: return None

        query_fields = '''{ uid dgraph.type expand(_all_)  { uid unique_name name channel { name } }
                            published_by: ~publishes { name unique_name uid } 
                            archives: ~sources_included @facets @filter(type("Archive")) { name unique_name uid } 
                            papers: ~sources_included @facets @filter(type("ResearchPaper")) { uid title published_date authors } } }'''
        
        query = query_func + query_fields

        # current_app.logger.error(query)
        res = self.client.txn(read_only=True).query(query)

        data = json.loads(res.json)

        if len(data['source']) == 0:
            return False

        data = data['source'][0]
        
        # parse dates
        if data.get('founded'):
            data['founded'] = dateparser.parse(data['founded'])
        if data.get('audience_size'):
            data['audience_size'] = [dateparser.parse(item) for item in data['audience_size']]
        if data.get('audience_residency'):
            data['audience_residency'] = [dateparser.parse(item) for item in data['audience_residency']]
        if data.get('papers'):
            for paper in data.get('papers'):
                paper['published_date'] = dateparser.parse(paper['published_date'])
                if paper['authors'].startswith('['):
                    paper['authors'] = paper['authors'].replace('[', '').replace(']', '').split(';')

        # flatten facets
        if data.get('channel_feeds'):
            tmp_list = []
            for key, item in data['channel_feeds|url'].items():
                tmp_list.append({'kind': data['channel_feeds'][int(key)], 'url': item})
            data['channel_feeds'] = tmp_list
            data.pop('channel_feeds|url', None)
        if data.get('audience_size'):
            data = self.flatten_date_facets(data, 'audience_size')
        if data.get('audience_residency'):
            data = self.flatten_date_facets(data, 'audience_residency')

        # prettify language
        if data.get('languages'):
            data['languages_pretty'] = [icu_codes[language] for language in data['languages']]

        return data

    def get_archive(self, unique_name=None, uid=None):
        if unique_name:
            query_func = f'{{ archive(func: eq(unique_name, "{unique_name}"))'
        elif uid:
            query_func = f'{{ archive(func: uid({uid}))' 
        else: return None

        query_fields = '''{ uid dgraph.type expand(_all_) num_sources: count(sources_included) } }'''
        
        query = query_func + query_fields
        res = self.client.txn(read_only=True).query(query)
        data = json.loads(res.json)

        if len(data['archive']) == 0:
            return False

        data = data['archive'][0]

        return data

    def get_organization(self, unique_name=None, uid=None):
        if unique_name:
            query_func = f'{{ organization(func: eq(unique_name, "{unique_name}"))'
        elif uid:
            query_func = f'{{ organization(func: uid({uid}))' 
        else: return None

        query_fields = '''{ uid dgraph.type expand(_all_) { uid name unique_name channel { name } }
    	                    owned_by: ~owns { uid	name unique_name } } }'''
        
        query = query_func + query_fields

        res = self.client.txn(read_only=True).query(query)
        data = json.loads(res.json)

        if len(data['organization']) == 0:
            return False

        data = data['organization'][0]

        # parse dates
        if data.get('founded'):
            data['founded'] = dateparser.parse(data['founded'])

        return data

    def get_channel(self, unique_name=None, uid=None):
        if unique_name:
            query_func = f'{{ channel(func: eq(unique_name, "{unique_name}"))'
        elif uid:
            query_func = f'{{ channel(func: uid({uid}))' 
        else: return None

        query_fields = '''{ uid dgraph.type expand(_all_) num_sources: count(~channel) } }'''
        
        query = query_func + query_fields

        res = self.client.txn(read_only=True).query(query)
        data = json.loads(res.json)

        if len(data['channel']) == 0:
            return False

        data = data['channel'][0]

        # parse dates
        if data.get('founded'):
            data['founded'] = dateparser.parse(data['founded'])

        return data

    def get_country(self, unique_name=None, uid=None):
        if unique_name:
            query_func = f'{{ country(func: eq(unique_name, "{unique_name}"))'
        elif uid:
            query_func = f'{{ country(func: uid({uid}))' 
        else: return None

        query_fields = '''{ uid dgraph.type expand(_all_) 
                            num_sources: count(~country @filter(type("Source")))  
                            num_orgs: count(~country @filter(type("Organization"))) } }'''
        
        query = query_func + query_fields

        res = self.client.txn(read_only=True).query(query)
        data = json.loads(res.json)

        if len(data['country']) == 0:
            return False

        data = data['country'][0]
        return data

    def get_paper(self, uid):
        query_func = f'{{ paper(func: uid({uid}))' 

        query_fields = '''{ uid dgraph.type expand(_all_) { uid name unique_name channel { name } } } }'''
        
        query = query_func + query_fields

        res = self.client.txn(read_only=True).query(query)
        data = json.loads(res.json)

        if len(data['paper']) == 0:
            return False

        data = data['paper'][0]

        # parse dates
        if data.get('published_date'):
            data['published_date'] = dateparser.parse(data['published_date'])

        # split authors
        if data.get('authors'):
            if data['authors'].startswith('['):
                data['authors'] = data['authors'].replace('[', '').replace(']', '').split(';')

        return data

    def get_orphan(self, query):
        q_string = '''{
                    source(func: eq(dgraph.type, "Source")) 
                    @filter(not(has(~publishes))) {
                        uid
                        name
                     }
                    }'''
        pass

    def create_post(self, post_data):
        if type(post_data) is not dict:
            raise TypeError()
        
        post_data['uid'] =  '_:newpost'
        post_data['dgraph.type'] = 'Post'
        post_data['date_published'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        
        txn = self.client.txn()

        try:
            response = txn.mutate(set_obj=post_data)
            txn.commit()
        except:
            response = False
        finally:
            txn.discard()

        if response:
            return response.uids['newpost']
        else: return False

    def iter_filt_dict(self, filt_dict):
        for key, val in filt_dict.items():
                filt_string = f'{key}('
                if type(val) == dict:
                    for subkey, subval in val.items():
                        filt_string += f'{subkey}, "{subval}")'
                else:
                    filt_string += f'{val})'
        return filt_string

    def build_filt_string(self, filt, operator="AND"):
        if type(filt) == str:
            return filt
        elif type(filt) == dict:
            return f'@filter({self.iter_filt_dict(filt)})'
        elif type(filt) == list:
            filt_string = f" {operator} ".join([self.iter_filt_dict(item) for item in filt])    
            return f'@filter({filt_string})'
        else:
            return ''

    
    def list_by_type(self, typename, filt=None, relation_filt=None, fields=None, normalize=False):
        query_head = f'{{ q(func: type("{typename}")) '
        if filt:
            query_head += self.build_filt_string(filt)
        
        if fields == 'all':
            query_fields = " expand(_all_) "
        elif fields:
            query_fields = " ".join(fields)
        else:
            normalize = True
            if typename == 'Source':
                query_fields = ''' uid: uid unique_name: unique_name name: name founded: founded
                                    channel { channel: name }
                                    '''
            if typename == 'Organization':
                query_fields = ''' uid: uid unique_name: unique_name name: name founded: founded
                                    publishes: count(publishes)
                                    owns: count(owns)
                                    '''
            if typename == 'Archive':
                query_fields = ''' uid: uid unique_name: unique_name name: name access: access
                                    sources_included: count(sources_included)
                                    '''
            if typename == 'ResearchPaper':
                normalize = False
                query_fields = ''' uid title authors published_date journal
                                    sources_included: count(sources_included)
                                    '''
                
        query_relation = ''
        if relation_filt:
            query_head += ' @cascade '
            if 'Country' in relation_filt.keys() and fields is None:
                query_fields += ''' country { country: name } '''

            for key, val in relation_filt.items():
                query_relation += f'{key} {self.build_filt_string(val)}'
                if fields == None: 
                    query_relation += f'{{ {key}: '
                else: query_relation += ' { '
                query_relation += ''' name }'''
        else:
            query_fields += ''' country { country: name } '''
        
        if normalize:
            query_head += '@normalize'

        query_string = query_head + ' { ' + query_fields + ' ' + query_relation + ' } }'

        res = self.client.txn(read_only=True).query(query_string)
        data = json.loads(res.json)

        if len(data['q']) == 0:
            return False

        data = data['q']

        # parse dates

        return data
