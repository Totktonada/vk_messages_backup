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
from argparse import ArgumentParser


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
    json.dump(json_dict, file, ensure_ascii=False, indent=4,
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


def find_config(config_file=None):
    from os.path import abspath, dirname, expanduser, join, isfile

    # always return pointed file if any
    if config_file is not None:
        return config_file if isfile(config_file) else None

    # fallback to default locations
    app_name = 'vk_messages_backup'
    conf_name = 'config.json'
    script_dir = dirname(abspath(__file__))
    home_dir = expanduser('~')
    xdg_config_dir = os.getenv('XDG_CONFIG_HOME', join(home_dir, '.config'))
    sys_config_dir = '/etc'
    files = [
        (script_dir, conf_name),
        (home_dir, '.' + app_name, conf_name),
        (xdg_config_dir, app_name, conf_name),
        (sys_config_dir, app_name, conf_name)
    ]
    for file_tuple in files:
        f = os.path.join(*file_tuple)
        if isfile(f):
            return f
    return None


def create_argparser():
    parser = ArgumentParser(
        description='Backup chatlogs from vk.com social network')
    parser.add_argument('--quiet', '-q', action='store_true')
    parser.add_argument('--config', default=None, help='specify a config file')
    parser.add_argument(
        '--storage', default='./storage',
        help='path to messages storage (default: %(default)s)')
    parser.add_argument(
        '--chatlogs', default='./chatlogs',
        help='where to save formatted chatlogs (default: %(default)s)')
    return parser


# Classes
# =======

class vk_api:
    def __init__(self, config_file=None):
        self.config_file = find_config(config_file)
        self.read_config()
        self.base_url = 'https://api.vk.com/method'
        self.vk_api_version = '5.80'
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
            raise NameError('vk_api.__init__: cannot read config file: %s' %
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
            print('VK API response with error, see dump below',
                  file=sys.stderr)
            print_json(general_response, file=sys.stderr)
            return NameError('vk_api.do_request: error response')
        return general_response['response']


def peer_id_to_dialog_id(peer_id):
    GROUP_OFFSET = 2000000000 # see https://vk.com/dev/messages.send
    if peer_id >= GROUP_OFFSET:
        did = (True, peer_id - GROUP_OFFSET)
    else:
        did = (False, peer_id)
    return did


def get_sender_id(m):
    return m.get('from_id', None) or m.get('user_id', None)


def get_msg_body(m):
    body = m.get('body', None)
    if body is not None:
        return body
    return m.get('text', None)


def get_chat_title(m):
    # TODO in new api, title is not sent in each chat message
    # till we figure out how to extract it it's fine though, since it only impacts rendering to .txt, not json raw data
    return m.get('title', 'NO TITLE')


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
            # new api still got 'out' field
            if 'out' in msg and msg['out']:
                user_id = 'me'
            else:
                user_id = get_sender_id(msg)
            return format_username_by_id(user_id)

        def format_forward(msg):
            fwd = ''
            if 'fwd_messages' in msg:
                fwd_mark = '>>> '
                fwd_template = '\n' + fwd_mark + '[%s] %s:%s'
                for fwd_msg in msg['fwd_messages']:
                    fwd_timestamp = format_timestamp(fwd_msg)
                    fwd_username = format_username(fwd_msg)
                    fwd_body = (format_forward(fwd_msg) + get_msg_body(fwd_msg))
                    fwd_body = fwd_body.replace('\n', '\n' + fwd_mark)
                    fwd += fwd_template % (
                        fwd_timestamp, fwd_username, fwd_body)
            if len(fwd) == 0:
                fwd += ' '
            else:
                fwd += '\n'
            return fwd

        def format_action(msg):
            if 'action' in msg:
                action = msg['action']
                atype: str
                act_username = None
                if isinstance(action, dict): # new api
                    atype = action['type']
                    if 'member_id' in action:
                        mid = action['member_id']
                        act_username = format_username_by_id(mid)
                else:
                    atype = action
                    if 'action_mid' in msg:
                        if int(msg['action_mid']) > 0:
                            act_username = format_username_by_id(int(msg['action_mid']))
                        else:
                            act_username = msg['action_email']

                action_mark_left = '*** ['
                action_mark_right = '] ***'
                if atype == 'chat_photo_update':
                    action = 'chat photo updated'
                elif atype == 'chat_photo_remove':
                    action = 'chat photo removed'
                elif atype == 'chat_create':
                    action = 'chat created: ' + msg['action_text']
                elif atype == 'chat_title_update':
                    action = 'chat title updated: ' + msg['action_text']
                elif atype == 'chat_invite_user':
                    action = 'user invited: ' + act_username
                elif atype == 'chat_kick_user':
                    action = 'user kicked: ' + act_username
                else:
                    raise NameError('vk_message.format.format_action: '
                                    'unsupported action type')
                return action_mark_left + action + action_mark_right
            else:
                return ''

        template = '%s[%s] %s:%s%s%s'
        title = ''
        more = ''

        # timestamp, username, body
        timestamp = format_timestamp(self.m)
        username = format_username(self.m)
        body = get_msg_body(self.m)
        # forward messages if exists
        fwd = format_forward(self.m)
        # title if not groupchat message and exists
        if not self.is_from_groupchat() and get_chat_title(self.m).strip() != '...':
            title = get_chat_title(self.m) + '\n'

        # action if exists
        more += format_action(self.m)
        # geolocation if exists
        if 'geo' in self.m:
            more += '\n    <- ' \
                'geolocation attached but displaying is not implemented'
        # media attachments if exists
        if 'attachments' in self.m:
            more += '\n    <- ' \
                'media attachments attached but displaying is not implemented'

        return template % (title, timestamp, username, fwd, body, more)

    def dialog_id(self):
        if 'peer_id' in self.m:
            return peer_id_to_dialog_id(self.m['peer_id'])

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
                    fwd_res.add(get_sender_id(fwd_msg))
                    fwd_res.update(fwd_participants(fwd_msg))
            return fwd_res
        res = set()
        res.add(get_sender_id(self.m))
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
            user_id = get_sender_id(self.m)
            title = str(users_dict[user_id])
        return re.sub(bad_symbol_re, '_', title).rstrip('.')


class vk_dialog:
    def __init__(self, id):
        self.id = id
        self.messages = []
        self.is_sorted = True

    def add_message(self, msg):
        if msg.dialog_id() != self.id:
            raise NameError('vk_dialog.add_message: '
                            'expected %s dialog id for message, got %s' %
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
        self.messages.sort(key=lambda msg: msg.id())
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
    def __init__(self, storage_dir, dump_dir):
        self.storage_dir = storage_dir
        self.dump_dir = dump_dir
        self.dialogs = dict()

    # assume that adding message is not stored already
    def add_message(self, msg):
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
            if dialog_id is None:
                continue
            if not os.path.isfile(filepath):
                raise NameError('vk_messages_storage.load: '
                                '%s is not regular file' % filepath)
            with open(filepath, 'r') as f:
                for raw_msg in json.load(f):
                    msg = vk_message(raw_msg, from_cache=True)
                    self.add_message(msg)

    def last_known_message_id(self, peer_id):
        did = peer_id_to_dialog_id(peer_id)
        dialog = self.dialogs.get(did, None)
        if dialog is None:
            return None

        messages = dialog.messages
        if len(messages) == 0:
            return None

        return max(m.id() for m in messages)

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
    def __init__(self, storage_dir):
        self.storage_dir = storage_dir
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
            if user_id is None:
                continue
            if not os.path.isfile(filepath):
                raise NameError('vk_users_storage.load: '
                                '%s is not regular file' % filepath)
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

def get_vk_history(vk, peer_id, last_known_message_id=None):
    res = []
    params = {
        'peer_id': peer_id,
        'count': 200,
    }
    done = False
    while not done:
        if len(res) > 0:
            params['start_message_id'] = res[-1]['id'] - 1
        response = vk.do_request('messages.getHistory', params)
        items = response['items']
        if len(items) == 0:
            done = True
            continue
        for m in items:
            if last_known_message_id is not None and m['id'] <= last_known_message_id:
                done = True
                break
            else:
                res.append(m)
    logging.info('[get_vk_history] fetched %d new messages for %s', len(res), peer_id)
    return res


def get_vk_users(vk, users_ids):
    if len(users_ids) == 0:
        return []

    logging.info('Downloading users (chats\' participants)...')

    chunksize = 20
    chunks_cnt = (len(users_ids) + chunksize - 1) // chunksize

    def chunk_start(i):
        return i * chunksize

    def chunk_end(i):
        return min((i+1) * chunksize, len(users_ids))

    res_users = []
    for i in range(0, chunks_cnt):
        logging.info('[get_vk_users] Downloading chunk %d / %d', i, chunks_cnt)
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


def get_vk_conversations(vk):
    results = []
    while True:
        params = {
            'count': 200,
        }
        if len(results) > 0:
            last_id = results[-1]['last_message_id']
            params['start_message_id'] = last_id - 1
        res = vk.do_request('messages.getConversations', params)
        items = res['items'] # TODO check against 'count'?
        if len(items) == 0:
            break
        results.extend([r['conversation'] for r in items])
        logging.info('[get_vk_conversations] Downloaded %d conversations', len(results))
    return results


# Main
# ====
def main():
    args = create_argparser().parse_args()

    log_level = logging.WARNING if args.quiet else logging.INFO
    logging.getLogger().setLevel(log_level)
    prettify_logging()

    vk = vk_api(args.config)

    # load saved messages
    storage = vk_messages_storage(args.storage, args.chatlogs)
    storage.load()

    conversations = get_vk_conversations(vk)
    for c in conversations:
        peer_id = c['peer']['id']
        last_message_id = storage.last_known_message_id(peer_id=peer_id)
        hist = get_vk_history(vk, peer_id=peer_id, last_known_message_id=last_message_id)
        messages = list(map(vk_message, hist))
        storage.add_messages(messages)
    storage.save()

    participants = storage.participants()

    # load saved users
    users_storage = vk_users_storage(args.storage)
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

if __name__ == '__main__':
    main()
