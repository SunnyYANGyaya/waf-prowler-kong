#!/usr/bin/env python3

import json
from utils.logUtils import LoggerSingleton
import os
logger = LoggerSingleton().get_logger()
TAG = "prowler_parse_raw_payload.py: "


def get_unformatted_payload(json_path):

    # init
    ret = {}

    # processing JSON file
    with open(json_path) as f:
        try:
            jdata = json.load(f)
        except Exception as e:
            print(
                'An error occurred while loading file {}: file not in JSON format ({})'
                .format(json_path, e)
            )
            return {}

    # url
    url = jdata.get('url', None)
    ret['url'] = None if not url else url

    # headers
    headers = jdata.get('headers', None)
    ret['headers'] = None if not headers else headers

    # data
    data = jdata.get('data', None)

    # verify
    verify = jdata.get('verify', None)
    ret['verify'] = verify if isinstance(verify, bool) else False

    # determine whether this is a POST or GET request
    if data:
        ret['data'] = data
        ret['method'] = 'POST'
    else:
        ret['method'] = 'GET'

    # return dictionary
    return ret


# 逐层读取文件夹中的多个json文件
def get_payloads_from_folder(folder_path):
    # init
    payloads = []

    # read all files in the folder
    for root, dirs, files in os.walk(folder_path):
        for file in files:
            logger.debug(TAG + "file: {}".format(file))
            if file.endswith('.json'):
                # skip empty files
                if os.stat(os.path.join(root, file)).st_size == 0:
                    continue
                # get the full path of the file
                file_path = os.path.join(root, file)
                # get the formatted payload
                payloads.append(get_unformatted_payload(file_path))

    # return payloads
    return payloads

def prowler_begin_to_sniff_payload(path):
    # get payloads from folder
    payloads = get_payloads_from_folder(path)
    payload_log_output = json.dumps(payloads, indent=4, ensure_ascii=False)
    logger.info(TAG + "payloads: {}".format(payload_log_output))
    return payloads

