import copy
import itertools
import json
import os
import random
import re
import time
import urllib.parse
import uuid
import json
import os
import requests
import http.client
import gzip
from bs4 import BeautifulSoup
import io

from stable_baselines3 import PPO
import xml.etree.ElementTree as ET
from urllib.parse import urlparse
from requests.models import Request, PreparedRequest, CaseInsensitiveDict
import requests
import gymnasium as gym
from gymnasium import spaces
import numpy as np
from stable_baselines3 import DQN  # 使用适合离散空间的算法
from stable_baselines3.common.env_checker import check_env

from sklearn.feature_extraction.text import TfidfVectorizer
if __name__ == "__main__":
    import sys
    sys.path.append(os.path.join(os.path.dirname(__file__), '../'))
# from utils.prowler_mutant import prowler_begin_to_mutant_payloads
from utils.prowler_mutant import prowler_begin_to_mutant_payloads
from utils.prowler_rl_based_mutant import prowler_begin_to_mutant_payloads as rl_based_mutant
from utils.logUtils import LoggerSingleton
from utils.recordResUtils import JSONLogger
from utils.prowler_feature_extract import prowler_feature_extract
from utils.logUtils import LoggerSingleton
import utils.prowler_parse_raw_payload
from utils.dictUtils import content_types
from utils.prowler_mutant_methods import *

# Logger
logger = LoggerSingleton().get_logger()
# logger.setLevel("WARNING")
TAG = "prowler_rl_based_mutant.py: "

# RL PARAMETERS
SELF_MAX_STEPS = 800
MAX_TIME_STEPS = 50000
#熵损失
ENTROPY_LOSS = 0.01
LEARNING_RATE = 0.0001 


def handle_json_response(response):
    try:
        data = json.loads(response.read().decode('utf-8'))
        return data
    except json.JSONDecodeError:
        logger.warning(TAG + "==> 响应数据不是有效的 JSON 格式")
        return "解析响应失败"

def handle_html_response(response):
    try:
        # 读取响应数据
        content = response.read()

        # 检查是否需要解压缩
        if content[:2] == b'\x1f\x8b':  # Gzip 的魔术字节
            content = gzip.GzipFile(fileobj=io.BytesIO(content)).read()

        # 解码为字符串
        html_content = content.decode('utf-8')

        # 解析 HTML
        soup = BeautifulSoup(html_content, 'html.parser')
        soup = soup.prettify()
        return soup
    except UnicodeDecodeError as e:
        logger.warning(TAG + f"==> 解析 HTML 时出错: {e}")
        return None
    except Exception as e:
        logger.warning(TAG + f"==> 处理 HTML 响应时出错: {e}")
        return None

def handle_xml_response(response):
    try:
        xml_content = response.read().decode('utf-8')
        root = ET.fromstring(xml_content)
        return root
    except ET.ParseError:
        logger.warning(TAG + "==> 响应数据不是有效的 XML 格式")
        return "解析响应失败"


def handle_gzip_response(response):
    try:
        compressed_data = response.read()
        with gzip.GzipFile(fileobj=io.BytesIO(compressed_data)) as gz_file:
            decompressed_data = gz_file.read().decode('utf-8')
        return decompressed_data
    except Exception as e:
        logger.warning(TAG + f"==> 解压缩 Gzip 数据时出错: {e}")
        return "解析响应失败"

def handle_text_response(response):
    try:
        text_content = response.read().decode('utf-8')
        return text_content
    except UnicodeDecodeError:
        logger.warning(TAG + "==> 响应数据不是有效的文本格式")
        return "解析响应失败"



def parse_response(response):
    content_type = response.getheader('Content-Type')
    logger.debug(TAG + "==>content_type: " + str(content_type))
    if content_type is None:
        logger.warning(TAG + "==>响应头中没有 Content-Type 字段")
        return "响应头中没有 Content-Type 字段, 解析响应失败"
    if 'application/json' in content_type:
        data = handle_json_response(response)
    elif 'text/html' in content_type:
        data = handle_html_response(response)
    elif 'application/xml' in content_type or 'text/xml' in content_type:
        data = handle_xml_response(response)
    elif 'gzip' in content_type:
        data = handle_gzip_response(response)
    elif 'text/plain' in content_type:
        data = handle_text_response(response)
    else:
        logger.warning(TAG + "==>Unknown response data format, content type: " + content_type)
        data = "解析响应失败"
    logger.info(TAG + "==>parsed data: " + str(data)+ "content_type is: " + content_type)

    return data

def send_requests(prep_request, timeout=0.5):
    url = urlparse(prep_request.get('url'))
    logger.debug(TAG + "==>url: " + str(prep_request.get('url')))
    # 创建 HTTP 连接并设置超时
    conn = http.client.HTTPConnection(url.netloc, timeout=timeout)
    
    try:
        
        # 获取 URL 和 body 并确保 body 为字节类型
        body = prep_request.get('body')
        # 确保 body 为字节类型
        if isinstance(body, dict):
            body = str(body).encode('utf-8')  # 将字典转换为字符串并编码为字节
        elif isinstance(body, str):
            body = body.encode('utf-8')  # 将字符串编码为字节
        conn.request(prep_request.get('method'), url.path,body=body, headers=prep_request.get('headers'))
    except Exception as e:
        logger.error(TAG + "==>error in sending request: " + str(e))
        logger.warning(TAG + "==>payload: " + str(prep_request))
        logger.warning(TAG + "==>type of payload: " + str(type(prep_request)))
        logger.warning(TAG + "==>url: " + str(url))
        logger.warning(TAG + "==>body: " + str(body))
        logger.warning(TAG + "==>type of body: " + str(type(body)))
        logger.warning(TAG + "==>headers: " + str(prep_request.get('headers')))
        response = requests.Response()
        # raise e
        return response
    
    try:
        # 获取响应，超时将导致异常
        response = conn.getresponse()
    except Exception as e:
        logger.error(TAG + "==>error in receiving response: " + str(e))
        response = requests.Response()
        return response

    # 记录响应状态
    temp_log = f"Response status: {response.status} {response.reason} {response.msg}"
    logger.info(TAG + temp_log)
    
    # 读取响应体内容
    response_body = parse_response(response)
    logger.info(TAG + str(response_body))
    
    # 将响应内容赋值给 response
    response.text = response_body
    response.status_code = response.status

    # 关闭连接
    conn.close()
    return response

def process_requests(headers, url, method, data=None, files=None):
    if method == 'JSON_POST':
        method = 'POST'
        data = json.dumps(data)
    if method == 'UPLOAD':
        method = 'POST'
    raw_request = Request(method, url, headers=headers, data=data, files=files)
    prep_request = raw_request.prepare()
    # 使用http.client发送请求
    logger.debug(TAG + "==>request: " + str(prep_request))
    logger.debug(TAG + "==>request headers: " + str(prep_request.headers))
    logger.debug(TAG + "==>request body: " + str(prep_request.body))
    logger.debug(TAG + "==>request url: " + str(prep_request.url))
    logger.debug(TAG + "==>request method: " + str(prep_request.method))
    return prep_request
    try:
        if method == 'GET':
            response = requests.get(url, headers=headers, verify=False)
        elif method == 'POST':
            # logger.error(TAG + "==>jsondata: " + str(data))
            # logger.error(TAG + "==>url: " + url)
            # logger.error(TAG + "==>headers: " + str(headers))
            response = requests.post(url, headers=headers, data=data, verify=False)
        elif method == 'JSON_POST':
            response = requests.post(url, headers=headers, json=data, verify=False)
        elif method == 'UPLOAD':
            response = requests.post(url, headers=headers, files=files, verify=False)
        return response
    except AssertionError as e:
        logger.error(TAG + "==>error: " + str(e))
        return None


def run_payload(payload, host=None, port=None, waf=True):
    logger.info(TAG + "==>run payload: " + str(payload))
    url = payload['url']
    # todo: more sophiscated way to obtain waf payload
    if waf:
        url = url.replace("8001", "9001").replace("8002", "9002").replace("8003", "9003")
    # for not mutanted payload, copy url as original url
    # for mutanted payload, use 'original_url' to display result

    if 'original_url' not in payload:
        original_url = url
    else:
        original_url = payload['original_url']
        if waf:
            original_url = original_url.replace("8001", "9001").replace("8002", "9002").replace("8003", "9003")
    # processed_req = process_requests(headers, url, method, data=data, files=files)
    processed_req = {
        "url": url,
        "headers": payload.get('headers', None),
        "method": payload.get('method', None),
        "body": payload.get('body', None),
    }
    # print(payload)
    # print(processed_req)
    # exit()
    response = send_requests(processed_req)
    logger.info(TAG + "==>send payload to " + url)
    logger.info(TAG + "==>response: " + str(response))
    # logger.debug(TAG + "==>response: " + str(response.text))
    if response is not None:
        logger.debug(TAG + "==>response: " + str(response.text))
        result = {
            'url': url,
            'original_url': original_url,
            'payload': str(payload),
            'response_status_code': response.status_code,
            'response_text': response.text,
            'success':''
        }
    else:
        result = {
            'url': url,
            'original_url': original_url,
            'payload': str(payload),
            'response_status_code': "Error",
            'response_text': "Error",
            'success':''
        }
    return result

# 获取启用的变异方法
enabled_mutant_methods = [
    (name, func) for name, (func, enabled) in mutant_methods_config_for_rl.items() if enabled
]
# 测试，仅使用 mutant_methods_modify_content_type,fake_content_type,add_harmless_command_for_get_request
# enabled_mutant_methods = [
#     ('mutant_methods_modify_content_type', mutant_methods_modify_content_type),
#     ('mutant_methods_fake_content_type', mutant_methods_fake_content_type),
#     ('mutant_methods_add_harmless_command_for_get_request', mutant_methods_add_harmless_command_for_get_request)
# ]
logger.warning(TAG + "Enabled Mutant Methods: " + str(enabled_mutant_methods))
# convert GET to POST
deep_mutant_methods = [
    (name, func) for name, (func, enabled) in deep_mutant_methods_config.items() if enabled
]
logger.warning(TAG + "Deep Mutant Methods: " + str(deep_mutant_methods))
# 发送请求的函数
def send_request(url, method, headers, data, files):
    try:
        if method == 'GET':
            response = requests.get(url, headers=headers, params=data)
        elif method == 'POST':
            response = requests.post(url, headers=headers, data=data, files=files)
        elif method == 'PUT':
            response = requests.put(url, headers=headers, data=data, files=files)
        elif method == 'DELETE':
            response = requests.delete(url, headers=headers, data=data)
        else:
            raise ValueError("Unsupported HTTP method: " + method)
        return response.status_code
    except requests.RequestException as e:
        logger.warning(TAG + "==> 发送请求时出错: " + str(e))
        return 0
class WAFBypassEnv(gym.Env):
    def __init__(self, enabled_methods, payload_for_rl):
        super(WAFBypassEnv, self).__init__()
        
        self.initial_payload = self._initialize_payload(payload_for_rl)
        self.payload = copy.deepcopy(self.initial_payload)
        if 'headers' not in self.payload or 'url' not in self.payload or 'method' not in self.payload:
            raise ValueError("Payload must contain 'headers', 'url', and 'method' fields.")
        self.payloads = [self.payload]
        self.num_methods = len(enabled_methods)
        self.payload_dim = 50
        self.max_steps = SELF_MAX_STEPS
        self.current_step = 0
        self.previous_payloads = set()
        self.total_actions = self.num_methods + 3
        self.ACTION_RESTORE = self.num_methods
        self.ACTION_SKIP = self.num_methods + 1
        self.ACTION_SPECIAL_MUTATION = self.num_methods + 2
        self.enabled_methods = enabled_methods

        # 计算总的动作数量，包括特殊动作
        self.total_methods = self.num_methods + 3

        # 计算观察空间的长度
        self.observation_length = 2 * self.total_methods + 2 + self.payload_dim

        self.action_space = spaces.Discrete(self.total_actions)
        self.observation_space = spaces.Box(
            low=0, high=1,
            shape=(self.observation_length,),
            dtype=np.float32
        )

        self._reset_environment()

    def _initialize_payload(self, payload_for_rl):
        if isinstance(payload_for_rl, dict):
            return payload_for_rl
        return {
            'headers': payload_for_rl.headers,
            'url': payload_for_rl.url,
            'method': payload_for_rl.method,
            'body': payload_for_rl.body,
        }

    def _reset_environment(self):
        self.current_step = 0
        self.success = False
        # 更新 failed_methods 和 action_history 的大小
        self.failed_methods = np.zeros(self.total_methods, dtype=np.float32)
        self.action_history = np.zeros(self.total_methods, dtype=np.float32)
        self.last_action = -1
        self.payload = copy.deepcopy(self.initial_payload)
        self.state = self._get_state()

    def reset(self, *, seed=None, options=None):
        self._reset_environment()
        return self.state, {}

    def extract_features(self, payload):
        features = prowler_feature_extract({
            'url': payload['url'],
            'method': payload['method'],
            'headers': payload.get('headers', {}),
            'body': payload.get('body', '')
        })
        logger.debug(f"{TAG}==>features: {features}")
        if len(features) < self.payload_dim:
            features = np.pad(features, (0, self.payload_dim - len(features)))
        return features[:self.payload_dim]

    def _get_state(self):
        payload_features = self.extract_features(self.payload)
        action_flags = np.array([
            int(self.last_action == self.ACTION_RESTORE),
            int(self.last_action == self.ACTION_SKIP)
        ], dtype=np.float32)
        method_status = np.concatenate([self.failed_methods, self.action_history])
        return np.concatenate([method_status, action_flags, payload_features]).astype(np.float32)

    def step(self, action):
        self.current_step += 1
        self._record_action(action)

        if action == self.ACTION_RESTORE:
            self._restore_payload()
        elif action == self.ACTION_SKIP:
            logger.warning("Skipping, no mutation applied.")
        elif action == self.ACTION_SPECIAL_MUTATION:
            self._apply_special_mutation()
        else:
            self._apply_mutation(action)

        self.state = self._get_state()
        reward, self.success = self._calculate_reward()
        done = self.success or self.current_step >= self.max_steps

        return self.state, reward, done, False, {}

    def _record_action(self, action):
        if action < self.total_methods:
            self.action_history[action] = 1.0
        self.last_action = action

    def _restore_payload(self):
        logger.warning("Restoring original payload.")
        self.payload = copy.deepcopy(self.initial_payload)

    def _apply_special_mutation(self):
        logger.warning("Applying special mutation method.")
        payload_to_mutate = copy.deepcopy(self.payload)
        special_method_name, special_method_func = deep_mutant_methods[0]

        try:
            payloads = special_method_func(
                payload_to_mutate.get('headers'),
                payload_to_mutate.get('url'),
                payload_to_mutate.get('method'),
                payload_to_mutate.get('body'),
                None
            )
            self._update_payload_from_mutation_results(payloads)
        except Exception as e:
            logger.error(f"Error applying special mutation method '{special_method_name}': {e}")
            self.failed_methods[self.ACTION_SPECIAL_MUTATION] = 1

    def _apply_mutation(self, action):
        method_index = action
        if self.failed_methods[method_index]:
            logger.warning(f"Mutation method {method_index} previously failed. Skipping.")
            return

        name, func = self.enabled_methods[method_index]
        logger.warning(f"Applying mutation method '{name}'.")
        payload_to_mutate = copy.deepcopy(self.payload)

        try:
            payloads = func(
                payload_to_mutate.get('headers'),
                payload_to_mutate.get('url'),
                payload_to_mutate.get('method'),
                payload_to_mutate.get('body'),
                None
            )
            self._update_payload_from_mutation_results(payloads)
        except Exception as e:
            logger.error(f"Error applying mutation method '{name}': {e}")
            self.failed_methods[method_index] = 1

    def _update_payload_from_mutation_results(self, payloads):
        if payloads:
            for payload in payloads:
                if 'data' in payload:
                    payload['body'] = payload.pop('data')
            self.payload = copy.deepcopy(payloads[0])
            self.payloads = payloads
        logger.info(f"{TAG}==>mutated payload: {self.payload}")

    def _calculate_reward(self):
        reward = -1  # 默认的轻微负奖励
        success = False

        def make_hashable(d):
            if isinstance(d, dict):
                return frozenset((k, make_hashable(v)) for k, v in d.items())
            elif isinstance(d, CaseInsensitiveDict):
                return make_hashable(dict(d))
            return d

        current_payload_dict = dict(self.payload)
        current_payload_hash = hash(make_hashable(current_payload_dict))

        for payload in self.payloads:
            if len(str(payload)) >= 5000:
                logger.info(TAG + "==>payload too long, skip")
                reward = -5
                success = False
                break

            result = run_payload(payload, waf=True)
            status_code = result.get('response_status_code', 0)

            if status_code is None:
                status_code = 0

            if status_code == 200:
                reward = 10  # 成功奖励
                success = True
                logger.warning("WAF bypassed!")

                if current_payload_hash not in self.previous_payloads:
                    reward += 2  # 给予额外奖励以鼓励多样性
                    self.previous_payloads.add(current_payload_hash)
                    logger.info(TAG + "==>payload diversity rewarded")
                break
            else:
                if status_code == 403:
                    reward -= 2
                elif status_code == 0:  # 超时
                    reward -= 3
                else:
                    reward -= 1
            logger.info(TAG + f"==> Status code: {status_code}, Reward: {reward}")
        return reward, success

    def get_payload(self):
        return self.payload

    def get_current_used_methods(self):
        return self.action_history

LOAD_NUM =0
def initialize_model(payload, enabled_mutant_methods, model_path="ppo_waf_bypass"):
    """初始化模型，如果已存在则加载模型，否则创建新模型"""
    global  LOAD_NUM
    try:
        if not os.path.exists(model_path):
            # 尝试加载最新的中间模型
            for i in range(1, 100):
                model_name = f"ppo_waf_bypass_payload_{i}.zip"
                if os.path.exists(model_name):
                    model_path = model_name
                    LOAD_NUM = i
            model = PPO.load(model_path, device="cuda")
        else:
            model = PPO.load(model_path, device="cuda")
        # 检查模型的环境状态空间是否与当前环境匹配
        env = WAFBypassEnv(enabled_mutant_methods, payload)
        if model.observation_space.shape != env.observation_space.shape:
            logger.warning("Observation space mismatch, reinitializing model.")
            model = create_new_model(env)
        else:
            model.set_env(env)
    except FileNotFoundError:
        logger.warning("Model not found, creating a new model.")
        env = WAFBypassEnv(enabled_mutant_methods, payload)
        model = create_new_model(env)
    except Exception as e:
        logger.error(f"Error loading model: {e}")
        env = WAFBypassEnv(enabled_mutant_methods, payload)
        model = create_new_model(env)
    return model

def create_new_model(env):
    """创建新的 PPO 模型"""
    return PPO("MlpPolicy", env,learning_rate=LEARNING_RATE,ent_coef=ENTROPY_LOSS, verbose=1, device="cuda")
def train_model(model, payloads, enabled_mutant_methods, total_timesteps=MAX_TIME_STEPS):
    """遍历 payloads 并逐个训练模型"""
    global LOAD_NUM
    for i, payload_for_rl in enumerate(payloads):
        if i < LOAD_NUM:
            logger.warning(f"Skip payload {i + 1}/{len(payloads)}")
            continue
        env = WAFBypassEnv(enabled_mutant_methods, payload_for_rl)
        # 更新模型的环境
        model.set_env(env)
        logger.warning(f"Training on payload {i + 1}/{len(payloads)}")
        # show payload
        logger.warning(f"Payload: " + str(payload_for_rl.url))
        # 可选的休眠观察
        time.sleep(5)
        model.learn(total_timesteps=total_timesteps)
        # 保存中间状态（可选）
        # break
        model.save(f"ppo_waf_bypass_payload_{i + 1}")

    # 最终保存模型
    model.save("ppo_waf_bypass")
def test_model(model, env):
    """测试模型在特定环境中的性能"""
    obs, _ = env.reset()
    done = False
    total_reward = 0
    successful_payloads = []  # 存储有效载荷的列表
    payload_count = 0  # 有效载荷计数
    total_steps = 0
    max_steps = 20  # 最大步数上限

    while not done and total_steps < max_steps:
        action, _ = model.predict(obs, deterministic=True)
        obs, reward, done, truncated, info = env.step(action)
        
        # 假设正奖励表示生成有效载荷
        if reward > 0:
            successful_payloads.append(env.get_payload())
            payload_count += 1  # 有效载荷计数增加

        total_reward += reward
        total_steps += 1

        # 打印当前状态
        print(f"Payload: {env.get_payload()}")
        print(f"Action: {action}, Reward: {reward}")

        # 如果达到正总奖励，则提前结束
        if total_reward > 0:
            print("Positive total reward achieved, ending test.")
            break

    print(f"Total Reward: {total_reward}")
    print(f"Number of Successful Payloads: {payload_count}")
    print(f"Successful Payloads: {successful_payloads}")


# def prowler_begin_to_mutant_payload_with_rl(headers, url, method, data, files=None):
#     logger.warning(TAG + "==> Begin mutating payloads with RL")
#     mutant_payloads = []

#     # 创建一个符合 WAFBypassEnv 要求的字典结构
#     payload_for_rl = {
#         'headers': headers,
#         'url': url,
#         'method': method,
#         'body': data
#     }

#     # 创建环境，使用初始的请求数据
#     env = WAFBypassEnv(enabled_mutant_methods, payload_for_rl)

#     # 加载预训练的模型
#     model = PPO.load("ppo_waf_bypass", device="cuda")

#     # 重置环境，获取初始观察
#     obs, _ = env.reset()
#     done = False
#     total_reward = 0

#     # 使用模型进行推理，直到成功绕过 WAF 或达到最大步骤数
#     while not done:
#         # 使用模型预测下一个动作
#         action, _states = model.predict(obs, deterministic=True)

#         # 执行动作，获取新的状态和奖励
#         obs, reward, done, truncated, info = env.step(action)
#         total_reward += reward

#         logger.debug(f"Action: {action}, Reward: {reward}")

#     logger.info(f"Total Reward: {total_reward}")

#     logger.info(TAG + "==> RL suggested mutant methods: " + str(env.action_history))
#     logger.info(TAG + "==> RL suggested payload: " + str(env.payload))
#     logger.info(TAG + "==> RL suggested state: " + str(env.state))
#     logger.info(TAG + "==> RL failed methods: " + str(env.failed_methods))
#     # 获取最终的变异后的 payload
#     mutant_payload = env.payload

#     # 将变异后的 payload 添加到列表中
#     mutant_payloads.append(mutant_payload)

#     return mutant_payloads
def prowler_begin_to_mutant_payload_with_rl(headers, url, method, data, files=None):
    logger.warning(TAG + "==> Begin mutating payloads with RL")
    mutant_payloads = []

    # 创建一个符合 WAFBypassEnv 要求的字典结构
    payload_for_rl = {
        'headers': headers,
        'url': url,
        'method': method,
        'body': data
    }

    # 创建环境，使用初始的请求数据
    env = WAFBypassEnv(enabled_mutant_methods, payload_for_rl)

    # 加载预训练的模型
    model = PPO.load("ppo_waf_bypass", device="cuda")

    # 重置环境，获取初始观察
    obs, _ = env.reset()
    done = False
    total_reward = 0
    total_steps = 0
    # 使用模型进行推理，直到成功绕过 WAF 或达到最大步骤数
    while not done:
        # 使用模型预测下一个动作
        action, _states = model.predict(obs, deterministic=True)

        # 执行动作，获取新的状态和奖励
        obs, reward, done, truncated, info = env.step(action)
        total_reward += reward
        total_steps += 1
        # 仅保留奖励为 100 的 payload
        if reward > 0:
            currently_used_methods = env.get_current_used_methods()
            payload = env.get_payload()
            # get the name of the method
            used_methods = [enabled_mutant_methods[i][0] for i in range(len(currently_used_methods)) if currently_used_methods[i] == 1]
            # append currently used methods to payload
            payload['currently_used_methods'] = used_methods
            mutant_payloads.append(copy.deepcopy(payload))
            logger.info("Added payload with reward 100 to mutant_payloads")
            break
        if total_steps >= 20:
            break
        
        logger.debug(f"Action: {action}, Reward: {reward}")

    logger.info(f"Total Reward: {total_reward}")
    logger.info(TAG + "==> RL suggested mutant methods: " + str(env.action_history))
    logger.info(TAG + "==> RL suggested state: " + str(env.state))
    logger.info(TAG + "==> RL failed methods: " + str(env.failed_methods))

    # 返回奖励为 100 的 payload 列表
    return mutant_payloads

if __name__ == "__main__":
    # 添加参数清空模型，重新训练
    if "--reset" in sys.argv:
        if os.path.exists("ppo_waf_bypass.zip"):
            os.remove("ppo_waf_bypass.zip")
            logger.warning("Model reset.")
        # 移除所有的中间模型
        for i in range(1, 100):
            model_name = f"ppo_waf_bypass_payload_{i}.zip"
            if os.path.exists(model_name):
                os.remove(model_name)
    if "--verbose" not in sys.argv:
        logger.warning("Verbose mode is disabled.")
        logger.setLevel("WARNING")

    # 加载并解析 payloads
    payloads = utils.prowler_parse_raw_payload.prowler_begin_to_sniff_payload("test/test_payloads")
    # payloads = utils.prowler_parse_raw_payload.prowler_begin_to_sniff_payload("config/payload/json")


    payloads_processed = []
    for payload in payloads:
        new_payload = process_requests(   
            payload['headers'],
            payload['url'],
            payload['method'],
            payload.get('data', None),
            payload.get('files', None)
            )
        payloads_processed.append(new_payload)
    if "--test" in sys.argv:
        print("Testing model on payload " + payloads_processed[0].url)
        test_env = WAFBypassEnv(enabled_mutant_methods, payloads_processed[0])
        model = PPO.load("ppo_waf_bypass", device="cuda")
        test_model(model, test_env)
        exit()    # 初始化模型

    model = initialize_model(payloads_processed[0], enabled_mutant_methods)
    # 训练模型
    train_model(model, payloads_processed, enabled_mutant_methods, total_timesteps=MAX_TIME_STEPS)

    # 测试模型
    # 对所有的payload进行测试
    for i, payload in enumerate(payloads_processed):
        test_env = WAFBypassEnv(enabled_mutant_methods, payload)
        model = PPO.load("ppo_waf_bypass", device="cuda")
        logger.warning(f"Testing on payload {i + 1}/{len(payloads_processed)}")
        test_model(model, test_env)

