## About

The script for locally saving and incremental updating private and groupchat messages from social service vk.com.

## Requirements

* python 3
* requests
* TODO: something else?

## How to use

Configure and first run:

* Get the used ID and the access token (TODO: expand required actions).
* Generate `config.json` file, a json object with `user_id` and `access_token` fields, see `config.json.example` file.
* Run `./messages_backup.py` if Python 3 is default Python implementation or `python3 ./messages_backup.py`.

The script will generate `storage` directory with json dump of gotten data and `chatlogs` directory with formatted chat logs (both in a current working directory).

Incremental update:

* Rerun `./messages_backup.py` in the same directory as before.

## Details

The script used straightforward approaches and algorithms, so don't wonder if it consume lots or memory and CPU time for processing and formatting the messages’ dump. The processing of some corner cases are not implemented properly.

The one of such 'bad case' that I remember is when count of all participants in all dialogs is more than 1000. The possible workaround is running script two times (three for more than 2000 participants, four for more than 3000 and so on) despite horrible stacktraces. Once all users will saved in the `storage` directory and the script will successful extract user first and last names.

## License

Public domain. You free to use it as you need without any restrictions. No guarantees provided.
