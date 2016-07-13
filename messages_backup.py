#!/usr/bin/env python3


# TODO's:
# * Maybe uppercase first letter of classes names?
# * Maybe replace 'users_ids' with 'user_ids'?
# * Add separate script(s) for getting url for obtaining access token
#   and generate config.
# * Display artist and track for audio attachments.


import os
import sys
import json
import time
from datetime import tzinfo, timedelta, datetime
import re
import logging
import requests


# General purpose utils
# =====================

class TZ(tzinfo):
    def utcoffset(self, dt):
        return timedelta(hours=3)
    def dst(self, dt):
        return timedelta(0)


def safe_mkdir(new_dir):
    if os.path.exists(new_dir):
        if not os.path.isdir(new_dir):
            raise NameError('safe_mkdir: %s is not a directory' % new_dir)
    else:
        os.mkdir(new_dir)


def print_json(json_dict, file=sys.stdout):
    json.dump(json_dict, file, ensure_ascii=False, indent=4, \
        sort_keys=True)
    print(file=file)


def prettify_logging():
    """ Setup logger format. """
    # TODO: colors when isatty()
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        '{asctime} {levelname:4s} {message}', style='{')
    handler.setFormatter(formatter)
    logging.getLogger().addHandler(handler)


# Classes
# =======

class vk_api:
    def __init__(self):
        self.config_file = os.path.dirname(os.path.abspath(__file__)) + '/config.json'
        self.read_config()
        self.base_url = 'https://api.vk.com/method'
        self.vk_api_version = '5.37'
        self.time_between_requests = 0.35
        self.last_req_time = 0
        self.common_params = {
            'access_token': self.access_token,
            'v': self.vk_api_version,
        }
        self.session = requests.Session()

    # for internal use
    def read_config(self):
        if not os.path.isfile(self.config_file):
            raise NameError('vk_api.__init__: cannot read config file: %s' % \
                self.config_file)
        with open(self.config_file, 'r') as f:
            config_data = json.load(f)
        self.access_token = config_data['access_token']
        self.user_id = config_data['user_id']

    # specific method parameters will overwrite corresponding common parameters
    def do_request(self, method, params):
        # don't do requests too often
        time_since_prev_req = int(time.time()) - self.last_req_time
        time_to_wait = self.time_between_requests - time_since_prev_req
        if time_to_wait > 0:
            time.sleep(time_to_wait)

        # do http request
        request_url = self.base_url.rstrip('/') + '/' + method
        req_params = self.common_params.copy()
        req_params.update(params)
        r = self.session.get(request_url, params=req_params)
        self.last_req_time = int(time.time())

        # extract response
        r.encoding = 'utf-8'
        general_response = r.json()
        if 'error' in general_response:
            print('VK API response with error, see dump below', file=sys.stderr)
            print_json(general_response, file=sys.stderr)
            return NameError('vk_api.do_request: error response')
        return general_response['response']


class vk_message:
    no_id = -1

    def __init__(self, m, from_cache=False):
        self.m = m
        self.from_cache = from_cache

    def format(self, users_dict):
        def format_timestamp(msg):
            return datetime.fromtimestamp(msg['date'], TZ()).isoformat(' ')
        def format_username_by_id(user_id):
            if user_id in users_dict:
                return str(users_dict[user_id])
            else:
                return 'user_' + str(user_id)
        def format_username(msg):
            if 'out' in msg and msg['out']:
                user_id = 'me'
            else:
                user_id = msg['user_id']
            return format_username_by_id(user_id)
        def format_forward(msg):
            fwd = ''
            if 'fwd_messages' in msg:
                fwd_mark = '>>> '
                fwd_template = '\n' + fwd_mark + '[%s] %s:%s'
                for fwd_msg in msg['fwd_messages']:
                    fwd_timestamp = format_timestamp(fwd_msg)
                    fwd_username = format_username(fwd_msg)
                    fwd_body = (format_forward(fwd_msg) + fwd_msg['body'])
                    fwd_body = fwd_body.replace('\n', '\n' + fwd_mark)
                    fwd += fwd_template % (fwd_timestamp, fwd_username, fwd_body)
            if len(fwd) == 0:
                fwd += ' '
            else:
                fwd += '\n'
            return fwd
        def format_action(msg):
            if 'action' in msg:
                action_mark_left = '*** ['
                action_mark_right = '] ***'
                if 'action_mid' in msg:
                    if int(msg['action_mid']) > 0:
                        act_username = format_username_by_id(int(msg['action_mid']))
                    else:
                        act_username = msg['action_email']
                if msg['action'] == 'chat_photo_update':
                    action = 'chat photo updated'
                elif msg['action'] == 'chat_photo_remove':
                    action = 'chat photo removed'
                elif msg['action'] == 'chat_create':
                    action = 'chat created: ' + msg['action_text']
                elif msg['action'] == 'chat_title_update':
                    action = 'chat title updated: ' + msg['action_text']
                elif msg['action'] == 'chat_invite_user':
                    action = 'user invited: ' + act_username
                elif msg['action'] == 'chat_kick_user':
                    action = 'user kicked: ' + act_username
                else:
                    raise NameError('vk_message.format.format_action: unsupported action type')
                return action_mark_left + action + action_mark_right
            else:
                return ''

        template = '%s[%s] %s:%s%s%s'
        title = ''
        more = ''

        # timestamp, username, body
        timestamp = format_timestamp(self.m)
        username = format_username(self.m)
        body = self.m['body']
        # forward messages if exists
        fwd = format_forward(self.m)
        # title if not groupchat message and exists
        if not self.is_from_groupchat() and self.m['title'].strip() != '...':
            title = self.m['title'] + '\n'

        # action if exists
        more += format_action(self.m)
        # geolocation if exists
        if 'geo' in self.m:
            more += '\n    <- geolocation attached but displaying is not implemented'
        # media attachments if exists
        if 'attachments' in self.m:
            more += '\n    <- media attachments attached but displaying is not implemented'

        return template % (title, timestamp, username, fwd, body, more)

    def dialog_id(self):
        if self.is_from_groupchat():
            return (True, self.m['chat_id'])
        else:
            return (False, self.m['user_id'])

    def raw(self):
        return self.m
    def id(self):
        return self.m.get('id', vk_message.no_id)
    def sent(self):
        return self.m['out']
    def is_from_cache(self):
        return self.from_cache
    def is_from_groupchat(self):
        return 'chat_id' in self.m

    def participants(self):
        def fwd_participants(msg):
            fwd_res = set()
            if 'fwd_messages' in msg:
                for fwd_msg in msg['fwd_messages']:
                    fwd_res.add(fwd_msg['user_id'])
                    fwd_res.update(fwd_participants(fwd_msg))
            return fwd_res
        res = set()
        res.add(self.m['user_id'])
        action_user_id = int(self.m.get('action_mid', "0"))
        if action_user_id > 0:
            res.add(action_user_id)
        res.update(fwd_participants(self.m))
        return res

    # for dump filename
    def title(self, users_dict):
        bad_symbol_re = r'[^a-zA-Z0-9А-ЯЁа-яё «»"\'()?.,:+-]'
        if self.is_from_groupchat():
            title = self.m['title']
        else:
            user_id = self.m['user_id']
            title = str(users_dict[user_id])
        return re.sub(bad_symbol_re, '_', title).rstrip('.')


class vk_dialog:
    def __init__(self, id):
        self.id = id
        self.messages = []
        self.is_sorted = True

    def add_message(self, msg):
        if msg.dialog_id() != self.id:
            raise NameError('vk_dialog.add_message: expected %s dialog id for message, got %s' % \
                (self.id, msg.dialog_id()))
        self.messages.append(msg)
        self.is_sorted = False

    # assume (is_from_groupchat, chatid_/user_id) id format
    def filename(self):
        if self.id[0]:
            return 'groupchat_%d.json' % self.id[1]
        else:
            return 'userchat_%d.json' % self.id[1]

    # assume that all dialogs has different titles
    def dump_filename(self, users_dict):
        return self.messages[-1].title(users_dict) + '.txt'

    def sort(self):
        if self.is_sorted:
            return
        self.messages.sort(key=lambda msg: msg.raw()['date'])
        self.is_sorted = True

    def save(self, storage_dir):
        self.sort()
        filepath = os.path.join(storage_dir, self.filename())
        data = [msg.raw() for msg in self.messages]
        with open(filepath, 'w') as f:
            print_json(data, file=f)

    def dump(self, dump_dir, users_dict):
        self.sort()
        filepath = os.path.join(dump_dir, self.dump_filename(users_dict))
        data = ''
        for msg in self.messages:
            data += msg.format(users_dict) + '\n'
        with open(filepath, 'w') as f:
            f.write(data)

    def get_messages(self):
        self.sort()
        return self.messages

    # return set of users' IDs
    def participants(self):
        users_ids = set()
        for msg in self.messages:
            users_ids.update(msg.participants())
        return users_ids

    # assume (is_from_groupchat, chatid_/user_id) id format
    @staticmethod
    def filepath_to_id(filepath):
        filename = os.path.basename(filepath)
        m = re.match(r'(userchat|groupchat)_(\d+).json', filename)
        if m:
            return (m.group(1) == 'groupchat', int(m.group(2)))
        else:
            return None


# assume that ids are integers
class vk_messages_storage:
    def __init__(self):
        self.storage_dir = 'storage'
        self.dump_dir = 'chatlogs'
        self.last_sent_id = vk_message.no_id
        self.last_recv_id = vk_message.no_id
        self.dialogs = dict()

    # for internal use
    def update_last_id(self, msg):
        if msg.sent():
            self.last_sent_id = max(self.last_sent_id, msg.id())
        else:
            self.last_recv_id = max(self.last_recv_id, msg.id())

    # assume that adding message is not stored already
    def add_message(self, msg):
        self.update_last_id(msg)
        dialog_id = msg.dialog_id()
        if dialog_id not in self.dialogs.keys():
            self.dialogs[dialog_id] = vk_dialog(dialog_id)
        self.dialogs[dialog_id].add_message(msg)

    def add_messages(self, messages):
        for msg in messages:
            self.add_message(msg)

    def save(self):
        logging.info('Saving messages to storage...')
        safe_mkdir(self.storage_dir)
        for dialog in self.dialogs.values():
            dialog.save(self.storage_dir)

    def dump(self, users_dict):
        logging.info('Dumping messages log into files...')
        safe_mkdir(self.dump_dir)
        for dialog in self.dialogs.values():
            dialog.dump(self.dump_dir, users_dict)

    def load(self):
        if not os.path.isdir(self.storage_dir):
            return
        logging.info('Loading messages from storage...')
        for filename in os.listdir(self.storage_dir):
            filepath = os.path.join(self.storage_dir, filename)
            dialog_id = vk_dialog.filepath_to_id(filepath)
            # skip files that not matching vk_dialog naming scheme
            if dialog_id == None:
                continue
            if not os.path.isfile(filepath):
                raise NameError('vk_messages_storage.load: %s is not regular file' % filepath)
            with open(filepath, 'r') as f:
                for raw_msg in json.load(f):
                    msg = vk_message(raw_msg, from_cache=True)
                    self.add_message(msg)

    def last_id(self, sent):
        if sent:
            return self.last_sent_id
        else:
            return self.last_recv_id

    # return set of users' IDs
    def participants(self):
        users_ids = set()
        for dialog in self.dialogs.values():
            users_ids.update(dialog.participants())
        return users_ids


class vk_user:
    no_id = -1

    def __init__(self, data, from_cache=False):
        self.data = data
        self.from_cache = from_cache

    def __str__(self):
        return '%s %s' % (self.data['first_name'], self.data['last_name'])
    def raw(self):
        return self.data
    def id(self):
        return self.data.get('id', vk_user.no_id)
    def is_from_cache(self):
        return self.from_cache

    @staticmethod
    def filepath_to_id(filepath):
        filename = os.path.basename(filepath)
        m = re.match(r'user_(\d+).json', filename)
        if m:
            return m.group(1)
        else:
            return None


class vk_users_storage:
    def __init__(self):
        self.storage_dir = 'storage'
        self.users = []

    # assume that users not added already
    def add_users(self, users):
        self.users.extend(users)

    def save(self):
        logging.info('Saving users to storage...')
        safe_mkdir(self.storage_dir)
        for user in self.users:
            data = user.raw()
            filename = 'user_%d.json' % data['id']
            filepath = os.path.join(self.storage_dir, filename)
            with open(filepath, 'w') as f:
                print_json(data, file=f)

    def load(self):
        if not os.path.isdir(self.storage_dir):
            return
        logging.info('Loading users from storage...')
        for filename in os.listdir(self.storage_dir):
            filepath = os.path.join(self.storage_dir, filename)
            user_id = vk_user.filepath_to_id(filepath)
            # skip files that not matching vk_user naming scheme
            if user_id == None:
                continue
            if not os.path.isfile(filepath):
                raise NameError('vk_users_storage.load: %s is not regular file' % filepath)
            with open(filepath, 'r') as f:
                user = vk_user(json.load(f), from_cache=True)
            self.users.append(user)

    def ids(self):
        users_ids = set()
        for user in self.users:
            users_ids.add(user.id())
        return users_ids

    def users_dict(self, my_id):
        res = dict()
        for user in self.users:
            res[user.id()] = user
        res['me'] = res[my_id]
        return res


# Functions that touch certain VK API methods
# ===========================================

# get all messages from the most fresher than 'after_id'
def get_vk_messages(vk, sent, after_id):
    if sent:
        logging.info('Downloading sent messages...')
    else:
        logging.info('Downloading received messages...')
    res_messages = []
    ids = set()
    msg_per_request = 200
    params = {
        'out': int(sent),
        'offset': 0,
        'count': msg_per_request,
        'time_offset': 0,
        'preview_length': 0,
    }
    # don't get messages before 'after_id' (inclusive)
    if after_id != vk_message.no_id:
        params['last_message_id'] = after_id
    while True:
        logging.info('[get_vk_messages] Downloading from offset %s...', \
            params['offset'])
        response = vk.do_request('messages.get', params)
        messages = [vk_message(msg) for msg in response['items']]
        # stop when empty list received
        if len(messages) == 0:
            break
        for msg in messages:
            if msg.id() not in ids:
                res_messages.append(msg)
                ids.add(msg.id())
        params['offset'] += msg_per_request
    return res_messages


def get_vk_users(vk, users_ids):
    if len(users_ids) == 0:
        return []

    logging.info('Downloading users (chats\' participants)...')

    chunksize = 20
    chunks_cnt = (len(users_ids) + chunksize - 1) // chunksize
    chunk_start = lambda i: i * chunksize
    chunk_end = lambda i: min((i+1) * chunksize, len(users_ids))

    res_users = []
    for i in range(0, chunks_cnt):
        logging.info('[get_vk_users] Downloading chunk %d / %d', i, \
            chunks_cnt)
        users_ids_chunk = users_ids[chunk_start(i):chunk_end(i)]
        users_ids_str = ','.join([str(user_id) for user_id in users_ids_chunk])
        params = {
            'user_ids': users_ids_str,
            'fields': [],
            'name_case': 'nom',
        }
        response = vk.do_request('users.get', params)
        res_users.extend([vk_user(user) for user in response])
    return res_users


# Main
# ====

# We're too silent by default
logging.getLogger().setLevel(logging.INFO)
prettify_logging()

vk = vk_api()

# load saved messages
storage = vk_messages_storage()
storage.load()
# load new messages
sent_messages = get_vk_messages(vk, sent=True, after_id=storage.last_id(sent=True))
recv_messages = get_vk_messages(vk, sent=False, after_id=storage.last_id(sent=False))
storage.add_messages(sent_messages)
storage.add_messages(recv_messages)
# save all messages
storage.save()

participants = storage.participants()

# load saved users
users_storage = vk_users_storage()
users_storage.load()
# load missing users
users_ids_new = list(participants - users_storage.ids())
users_new = get_vk_users(vk, users_ids_new)
users_storage.add_users(users_new)
# save all users
users_storage.save()

# dump all messages
users_dict = users_storage.users_dict(vk.user_id)
storage.dump(users_dict)
