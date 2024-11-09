import copy
import itertools
import json
import os
import random
import re
import urllib.parse
import uuid
from stable_baselines3 import DQN
from utils.logUtils import LoggerSingleton
from utils.dictUtils import content_types
from utils.prowler_mutant_methods import *
logger = LoggerSingleton().get_logger()
TAG = "prowler_mutant.py: "
# mutant_methods = [mutant_methods_multipart_boundary]
# mutant_methods = [mutant_methods_sql_comment_obfuscation]
# mutant_methods = [mutant_methods_add_harmless_command_for_get_request]
# mutant_methods = [mutant_methods_add_Content_Type_for_get_request]
# mutant_methods = [mutant_methods_convert_get_to_post]
# 上传载荷变异方法
mutant_methods_dedicated_to_upload = []


# using delta-debugging to reduce the size of the input
def dd_mutant(headers,url,method,data,files):
    # 生成从1到len(mutant_methods)的所有组合
    max_combination_length = 2
    if len(mutant_methods) % 2 != 0:
        max_combination_length += 1  # 处理奇数情况，取一半的上界

    # 生成从1到max_combination_length的所有组合
    all_combinations = []
    for r in range(1, max_combination_length + 1):
        combinations = itertools.combinations(mutant_methods, r)
        all_combinations.extend(combinations)
    # 对每个组合进行变异操作
    sub_mutant_payloads = []
    for combination in all_combinations:
        # 深拷贝初始参数
        headers_copy = copy.deepcopy(headers)
        url_copy = copy.deepcopy(url)
        method_copy = copy.deepcopy(method)
        data_copy = copy.deepcopy(data)
        files_copy = copy.deepcopy(files) if files else None

        # 应用每个mutant method在组合中
        for mutant_method in combination:
            logger.info(TAG + "==>mutant method: " + str(mutant_method))
            sub_payloads =  mutant_method(headers_copy, url_copy, method_copy, data_copy, files_copy)
            # get the first sub_payload
            if sub_payloads:
                headers_copy = copy.deepcopy(sub_payloads[0]['headers'])
                url_copy = copy.deepcopy(sub_payloads[0]['url'])
                method_copy = copy.deepcopy(sub_payloads[0]['method'])
                data_copy = copy.deepcopy(sub_payloads[0]['data'])
                files_copy = copy.deepcopy(sub_payloads[0]['files']) if sub_payloads[0].get('files') else None
        sub_mutant_payload = {
            'headers': headers_copy,
            'url': url_copy,
            'method': method_copy,
            'data': data_copy,
            'files': files_copy
        }
        sub_mutant_payloads.append(sub_mutant_payload)
    with open("test.json", "w") as f:
        content_to_write = []
        for sub_mutant_payload in sub_mutant_payloads:
            print(str(sub_mutant_payload))
            content_to_write.append(str(sub_mutant_payload))
        f.write(json.dumps(content_to_write))
    return sub_mutant_payloads



def prowler_begin_to_mutant_payloads(headers, url, method, data,files=None,memory=None,deep_mutant=False,dd_enabled=False):
    logger.info(TAG + "==>begin to mutant payloads")
    url_backup = copy.deepcopy(url)
    mutant_payloads = []
    if os.path.exists("config/memory.json") and not deep_mutant:
        with open("config/memory.json", "r") as f:
            try:
                memories = json.load(f)
            except json.decoder.JSONDecodeError:
                memories = []
        mem_dict = {}
        for mem in memories:
            mem_dict[mem['url']] = mem['successful_mutant_method']
        __url = url.replace('8001', '9001').replace('8002', '9002').replace('8003', '9003')
        if __url in mem_dict:
            if mem_dict[__url] in mutant_methods_config:
                mutant_method, flag = mutant_methods_config[mem_dict[__url]]

                # 调用对应的变异方法
                sub_mutant_payloads = mutant_method(headers, url, method, data, files)
                logger.info(TAG + "==>found url in memory, use method: " + mem_dict[__url])
                # keep original url for result
                mutant_payloads.extend(sub_mutant_payloads)
                for payload in mutant_payloads:
                    payload['original_url'] = url

                return mutant_payloads
    # if rl:
    #     # 使用强化学习进行策略选择
    #     logger.info(TAG + "==>use RL to select mutant method")
    #     action = choose_strategy({
    #         'headers': headers,
    #         'url': url,
    #         'method': method,
    #         'data': data,
    #         'files': files
    #     }, mutant_methods)
    #     # 调用对应的变异方法
    #     sub_mutant_payloads = mutant_methods[action](headers, url, method, data, files)
    #     logger.info(TAG + "==>found url in memory, use method: " + mem_dict[__url])
    #     # keep original url for result
    #     mutant_payloads.extend(sub_mutant_payloads)
    #     for payload in mutant_payloads:
    #         payload['original_url'] = url
    #     logger.info(TAG + "==>RL selected method: " + str(mutant_methods[action]))
    #     return mutant_payloads
    else :
        #打印当前路径
        logger.info(os.getcwd())
        logger.info("memory.json not exists")
        # exit()
    if deep_mutant:
        logger.info(TAG + "==>deep mutant")
        headers,url,method,data,files,success = mutant_methods_change_request_method(headers,url,method,data,files)
        if not success:
            return []
        # print(headers,url,method,data,files)
        # exit()
    if dd_enabled:
        logger.info(TAG + "==>dd enabled")
        return dd_mutant(headers,url,method,data,files)
    for mutant_method in mutant_methods:
        # 对需要变异的参数进行深拷贝
        headers_copy = copy.deepcopy(headers)
        url_copy = copy.deepcopy(url)  # 如果url是字符串，不拷贝也可以
        method_copy = copy.deepcopy(method)  # 如果method是字符串，不拷贝也可以
        data_copy = copy.deepcopy(data)
        files_copy = copy.deepcopy(files) if files else None
        logger.info(TAG + "==>mutant method: " + str(mutant_method))
        sub_mutant_payloads = mutant_method(headers_copy, url_copy, method_copy, data_copy, files_copy)
        # print(str(headers) +"after mutant method " + str(mutant_method))
        # 如果没有子变异载荷，输出警告
        if not sub_mutant_payloads:
            logger.warning(TAG + "==>no sub mutant payloads for method: " + str(mutant_method))
        for sub_mutant_payload in sub_mutant_payloads:
            sub_mutant_payload['mutant_method'] = mutant_method.__name__
        mutant_payloads.extend(sub_mutant_payloads)

    if method == 'UPLOAD':
        for mutant_upload_method in mutant_methods_dedicated_to_upload:
            logger.info(TAG + "==>mutant upload method: " + str(mutant_upload_method))
            headers,url,method,data,files = mutant_upload_method(headers,url,method,data,files=data)
            mutant_payloads.append({
                'headers': headers,
                'url': url,
                'method': method,
                'data': data,
                'files': data
            })
    # keep original url for result
    for payload in mutant_payloads:
        payload['original_url'] = url_backup
    # 若执行了某变异方法后，本来持有的参数变为None，抛出异常
    #检查初始payload含有的参数是否为空
    initial_payload_status = {
        'have_headers': True if headers else False,
        'have_url': True if url else False,
        'have_method': True if method else False,
        'have_data': True if data else False,
        'have_files': True if files else False
    }
    for payload in mutant_payloads:
        #检查变异后的payload含有的参数是否为空与initial_payload_status进行比较
        if not payload['headers'] and initial_payload_status['have_headers'] and not payload['url'] and initial_payload_status['have_url'] and not payload['method'] and initial_payload_status['have_method'] and not payload['data'] and initial_payload_status['have_data'] and not payload['files'] and initial_payload_status['have_files']:
            logger.info(TAG + "initial headers: " + str(headers))
            logger.info(TAG + "initial url: " + str(url))
            logger.info(TAG + "initial method: " + str(method))
            logger.info(TAG + "initial data: " + str(data))
            logger.info(TAG + "initial files: " + str(files))
            logger.info(TAG + "after mutant method: " + str(payload['mutant_method']))
            logger.info(TAG + "after mutant headers: " + str(payload['headers']))
            logger.info(TAG + "after mutant url: " + str(payload['url']))
            logger.info(TAG + "after mutant method: " + str(payload['method']))
            logger.info(TAG + "after mutant data: " + str(payload['data']))
            logger.info(TAG + "after mutant files: " + str(payload['files']))
            raise Exception("==>None parameter after mutant method")
    return mutant_payloads
