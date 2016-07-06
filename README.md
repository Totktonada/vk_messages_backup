## About

The script for locally saving and incremental updating private and groupchat messages from social service vk.com.

## Requirements

* python 3
* requests

## How to use

Configure and first run:

* Open [this link](https://oauth.vk.com/authorize?client_id=5048703&redirect_uri=https://oauth.vk.com/blank.html&display=page&scope=offline,messages&response_type=token&v=5.37) in a browser and confirm permissions for the 'messages backup' application, in fact that is just obtaining an access token with certain rights.
* Copy `access_token` and `user_id` values from URL in an address bar and put it to the `config.json` file, use `config.json.example` as the format reference.
* Run `./messages_backup.py`.

The script will generate `storage` directory with json dump of gotten data and `chatlogs` directory with formatted chat logs (both in a current working directory).

Incremental update:

* Rerun `./messages_backup.py` in the same directory as before.

## Details

The script used straightforward approaches and algorithms, so don't wonder if it consume lots or memory and CPU time for processing and formatting the messages’ dump. The processing of some corner cases are not implemented properly.

## License

Public domain. You free to use it as you need without any restrictions. No guarantees provided.
