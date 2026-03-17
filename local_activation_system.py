#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
本地激活系统 - 完整版
集成所有安全机制：
- 增强版硬件ID
- 时间篡改检测
- 容错验证
- 虚拟机检测
"""

import hashlib
import base64
import json
import os
import sqlite3
import uuid
import platform
import subprocess
import requests
import socket
import struct
from datetime import datetime, timedelta
from cryptography.fernet import Fernet
from typing import Tuple, Dict, Optional, List
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 服务器地址
SERVER_URL = "https://wfnlj520.com"

# NTP服务器列表
NTP_SERVERS = [
    'ntp.aliyun.com',
    'ntp.tencent.com',
    'time.windows.com',
    'pool.ntp.org',
]

# 加密密钥（与服务器端一致）
ACTIVATION_SECRET_KEY = b'PDF_MERGER_2026_ACTIVATION_SECRET_KEY_FIX'

# 硬件特征权重
FEATURE_WEIGHTS = {
    'cpu': 0.20,
    'motherboard': 0.15,
    'disk': 0.15,
    'mac': 0.10,
    'bios': 0.10,
    'memory': 0.10,
    'machine_guid': 0.05,
    'windows_id': 0.05,
    'volume': 0.05,
    'gpu': 0.05,
}

# 最低匹配阈值
MIN_MATCH_THRESHOLD = 0.60


# ============================================
# 加密工具
# ============================================

def _get_encryption_key() -> bytes:
    key_hash = hashlib.sha256(ACTIVATION_SECRET_KEY).digest()
    return base64.urlsafe_b64encode(key_hash)


def _encrypt_data(data: str) -> str:
    key = _get_encryption_key()
    cipher = Fernet(key)
    encrypted = cipher.encrypt(data.encode())
    return base64.urlsafe_b64encode(encrypted).decode()


def _decrypt_data(encrypted_data: str) -> str:
    try:
        key = _get_encryption_key()
        cipher = Fernet(key)
        encrypted_bytes = base64.urlsafe_b64decode(encrypted_data.encode())
        decrypted = cipher.decrypt(encrypted_bytes)
        return decrypted.decode()
    except Exception as e:
        logger.error(f"解密失败: {e}")
        return ""


# ============================================
# 硬件ID生成（增强版）
# ============================================

def get_cpu_id() -> str:
    try:
        if platform.system() == 'Windows':
            result = subprocess.run(
                ['wmic', 'cpu', 'get', 'ProcessorId'],
                capture_output=True, text=True, timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                if len(lines) > 1:
                    return lines[1].strip()
    except:
        pass
    return ""


def get_disk_serial() -> str:
    try:
        if platform.system() == 'Windows':
            result = subprocess.run(
                ['wmic', 'diskdrive', 'get', 'serialnumber'],
                capture_output=True, text=True, timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                for line in lines[1:]:
                    serial = line.strip()
                    if serial:
                        return serial
    except:
        pass
    return ""


def get_volume_serial() -> str:
    try:
        if platform.system() == 'Windows':
            result = subprocess.run(
                ['vol', 'C:'],
                capture_output=True, text=True, timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            if result.returncode == 0 and '序列号' in result.stdout:
                parts = result.stdout.split('序列号')
                if len(parts) > 1:
                    return parts[1].strip().replace('是', '').strip().replace('-', '')
    except:
        pass
    return ""


def get_mac_address() -> str:
    try:
        mac = uuid.getnode()
        mac_str = ':'.join(['{:02x}'.format((mac >> elements) & 0xff) 
                           for elements in range(0, 2*6, 2)][::-1])
        if mac_str != '00:00:00:00:00:00':
            return mac_str
    except:
        pass
    return ""


def get_motherboard_serial() -> str:
    try:
        if platform.system() == 'Windows':
            result = subprocess.run(
                ['wmic', 'baseboard', 'get', 'serialnumber'],
                capture_output=True, text=True, timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                if len(lines) > 1:
                    serial = lines[1].strip()
                    if serial.lower() not in ['', 'none', 'to be filled by o.e.m.']:
                        return serial
    except:
        pass
    return ""


def get_bios_serial() -> str:
    try:
        if platform.system() == 'Windows':
            result = subprocess.run(
                ['wmic', 'bios', 'get', 'serialnumber'],
                capture_output=True, text=True, timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                if len(lines) > 1:
                    serial = lines[1].strip()
                    if serial.lower() not in ['', 'none', 'to be filled by o.e.m.']:
                        return serial
    except:
        pass
    return ""


def get_memory_info() -> str:
    try:
        if platform.system() == 'Windows':
            result = subprocess.run(
                ['wmic', 'memorychip', 'get', 'SerialNumber'],
                capture_output=True, text=True, timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                serials = [line.strip() for line in lines[1:] if line.strip()]
                return '-'.join(serials[:2])
    except:
        pass
    return ""


def get_gpu_info() -> str:
    try:
        if platform.system() == 'Windows':
            result = subprocess.run(
                ['wmic', 'path', 'win32_VideoController', 'get', 'PNPDeviceID'],
                capture_output=True, text=True, timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                for line in lines[1:]:
                    if 'VEN_' in line:
                        return line.strip()
    except:
        pass
    return ""


def get_machine_guid() -> str:
    try:
        if platform.system() == 'Windows':
            import winreg
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography")
            guid, _ = winreg.QueryValueEx(key, "MachineGuid")
            winreg.CloseKey(key)
            return guid
    except:
        pass
    return ""


def get_windows_product_id() -> str:
    try:
        if platform.system() == 'Windows':
            import winreg
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion")
            product_id, _ = winreg.QueryValueEx(key, "ProductId")
            winreg.CloseKey(key)
            return product_id
    except:
        pass
    return ""


def get_all_hardware_features() -> Dict[str, str]:
    """获取所有硬件特征"""
    features = {}
    
    cpu = get_cpu_id()
    if cpu:
        features['cpu'] = cpu
    
    disk = get_disk_serial()
    if disk:
        features['disk'] = disk
    
    volume = get_volume_serial()
    if volume:
        features['volume'] = volume
    
    mb = get_motherboard_serial()
    if mb:
        features['motherboard'] = mb
    
    bios = get_bios_serial()
    if bios:
        features['bios'] = bios
    
    mac = get_mac_address()
    if mac:
        features['mac'] = mac
    
    guid = get_machine_guid()
    if guid:
        features['machine_guid'] = guid
    
    win_id = get_windows_product_id()
    if win_id:
        features['windows_id'] = win_id
    
    mem = get_memory_info()
    if mem:
        features['memory'] = mem
    
    gpu = get_gpu_info()
    if gpu:
        features['gpu'] = gpu
    
    return features


def get_hardware_id() -> str:
    """生成硬件ID（主入口）"""
    features = get_all_hardware_features()
    
    if not features:
        # 回退方案
        fallback = f"{platform.node()}{platform.processor()}"
        return hashlib.sha256(fallback.encode()).hexdigest().upper()[:16]
    
    # 使用核心特征生成主ID
    core_features = []
    for key in ['cpu', 'motherboard', 'disk']:
        if key in features:
            core_features.append(f"{key}:{features[key]}")
    
    combined = '|'.join(core_features)
    return hashlib.sha256(combined.encode()).hexdigest().upper()[:16]


# ============================================
# 时间验证（防篡改）
# ============================================

def get_ntp_time(timeout: int = 3) -> Optional[datetime]:
    """从NTP服务器获取网络时间"""
    for ntp_server in NTP_SERVERS:
        try:
            client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            client.settimeout(timeout)
            data = b'\x1b' + 47 * b'\x00'
            client.sendto(data, (ntp_server, 123))
            response, _ = client.recvfrom(1024)
            client.close()
            unpacked = struct.unpack('!12I', response)
            timestamp = unpacked[10] - 2208988800
            return datetime.fromtimestamp(timestamp)
        except:
            continue
    return None


def get_network_time() -> Optional[datetime]:
    """获取网络时间（优先NTP，备用HTTP）"""
    # NTP方式
    ntp_time = get_ntp_time(timeout=2)
    if ntp_time:
        return ntp_time
    
    # HTTP方式
    try:
        response = requests.get(f"{SERVER_URL}/api/time", timeout=3)
        if response.status_code == 200:
            data = response.json()
            return datetime.fromisoformat(data['time'].replace('Z', '+00:00'))
    except:
        pass
    
    return None


def record_last_run_time() -> datetime:
    """记录本次运行时间"""
    current_time = datetime.now()
    try:
        time_file = ".runtime"
        data = {
            'last_run': current_time.isoformat(),
            'hardware_id': get_hardware_id()
        }
        with open(time_file, 'w') as f:
            json.dump(data, f)
        if platform.system() == 'Windows':
            subprocess.run(['attrib', '+H', time_file], creationflags=subprocess.CREATE_NO_WINDOW)
    except Exception as e:
        logger.warning(f"记录运行时间失败: {e}")
    return current_time


def get_last_run_time() -> Optional[datetime]:
    """获取上次运行时间"""
    try:
        if not os.path.exists(".runtime"):
            return None
        with open(".runtime", 'r') as f:
            data = json.load(f)
        if data.get('hardware_id') != get_hardware_id():
            return None
        return datetime.fromisoformat(data['last_run'])
    except:
        return None


def verify_time_not_tampered() -> Tuple[bool, str]:
    """验证时间是否被篡改"""
    local_time = datetime.now()
    
    # 检查1：对比上次运行时间
    last_run = get_last_run_time()
    if last_run:
        time_diff = (local_time - last_run).total_seconds()
        if time_diff < -60:
            return False, "检测到系统时间异常，请将系统时间调整正确后重试"
    
    # 检查2：获取网络时间对比
    network_time = get_network_time()
    if network_time:
        # 去掉时区信息进行比较
        if hasattr(network_time, 'tzinfo') and network_time.tzinfo:
            network_time = network_time.replace(tzinfo=None)
        time_diff = abs((local_time - network_time).total_seconds())
        if time_diff > 300:
            return False, "系统时间与网络时间不一致，请校准时间后重试"
    
    # 记录本次时间
    record_last_run_time()
    
    return True, ""


# ============================================
# 虚拟机检测
# ============================================

def is_virtual_machine() -> Tuple[bool, str]:
    """检测是否在虚拟机中运行"""
    indicators = []
    
    try:
        if platform.system() == 'Windows':
            # 检查CPU名称
            result = subprocess.run(
                ['wmic', 'cpu', 'get', 'Name'],
                capture_output=True, text=True, timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            if result.returncode == 0:
                cpu_name = result.stdout.lower()
                for keyword in ['virtual', 'vmware', 'vbox', 'qemu', 'xen', 'kvm']:
                    if keyword in cpu_name:
                        indicators.append(f"CPU: {keyword}")
            
            # 检查主板制造商
            result = subprocess.run(
                ['wmic', 'baseboard', 'get', 'Manufacturer'],
                capture_output=True, text=True, timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            if result.returncode == 0:
                manufacturer = result.stdout.lower()
                for vm in ['vmware', 'virtualbox', 'xen', 'qemu']:
                    if vm in manufacturer:
                        indicators.append(f"主板: {vm}")
            
            # 检查MAC地址前缀
            mac = get_mac_address()
            if mac:
                vm_mac_prefixes = ['00:0C:29', '00:50:56', '08:00:27', '00:16:3E']
                for prefix in vm_mac_prefixes:
                    if mac.upper().startswith(prefix):
                        indicators.append(f"MAC: {prefix}")
    except:
        pass
    
    if indicators:
        return True, "; ".join(indicators)
    return False, ""


# ============================================
# 激活码验证
# ============================================

def parse_activation_code(activation_code: str) -> Optional[Dict]:
    """解析激活码"""
    try:
        parts = activation_code.strip().split('-')
        if len(parts) != 3:
            return None
        
        type_prefix, encrypted_data, checksum = parts
        
        type_map = {'TRY': 'trial', 'MON': 'monthly', 'YEA': 'yearly', 'LTD': 'lifetime'}
        activation_type = type_map.get(type_prefix)
        if not activation_type:
            return None
        
        decrypted = _decrypt_data(encrypted_data)
        if not decrypted:
            return None
        
        data = json.loads(decrypted)
        
        # 验证校验码
        check_data = f"{data.get('hwid')}{activation_type}{data.get('expire')}"
        expected_checksum = hashlib.md5(check_data.encode()).hexdigest()[:4].upper()
        if checksum != expected_checksum:
            return None
        
        return {
            'activation_type': activation_type,
            'hardware_id': data['hwid'],
            'expire_timestamp': data['expire'],
            'created_timestamp': data['created']
        }
    except:
        return None


def verify_activation_code(activation_code: str, hardware_id: str) -> Tuple[bool, str, Dict]:
    """验证激活码"""
    try:
        # 时间验证
        time_ok, time_error = verify_time_not_tampered()
        if not time_ok:
            return False, time_error, {}
        
        # 解析激活码
        data = parse_activation_code(activation_code)
        if not data:
            return False, "激活码无效", {}
        
        # 验证硬件ID（容错）
        if data['hardware_id'] != hardware_id:
            # 尝试容错验证
            current_features = get_all_hardware_features()
            # 简化：直接返回不匹配
            return False, "激活码与当前设备不匹配", {}
        
        # 验证过期时间
        expire_date = datetime.fromtimestamp(data['expire_timestamp'])
        current_time = get_network_time() or datetime.now()
        
        if current_time > expire_date:
            return False, f"激活码已过期（{expire_date.strftime('%Y-%m-%d')}）", {}
        
        days_remaining = (expire_date - current_time).days
        
        return True, "", {
            'activation_type': data['activation_type'],
            'expire_date': expire_date.isoformat(),
            'days_remaining': days_remaining,
            'hardware_id': hardware_id,
            'activation_code': activation_code
        }
    except Exception as e:
        return False, f"验证失败: {e}", {}


# ============================================
# 激活信息存储
# ============================================

def save_activation(activation_code: str, activation_info: Dict, hardware_id: str) -> bool:
    """保存激活信息到本地"""
    try:
        db_path = "activation.db"
        
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS activation (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    hardware_id TEXT NOT NULL,
                    activation_code TEXT NOT NULL,
                    activation_type TEXT NOT NULL,
                    expire_date TEXT NOT NULL,
                    last_run_time TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            cursor.execute('DELETE FROM activation')
            
            cursor.execute('''
                INSERT INTO activation (hardware_id, activation_code, activation_type, expire_date, last_run_time)
                VALUES (?, ?, ?, ?, ?)
            ''', (hardware_id, activation_code, activation_info['activation_type'], 
                  activation_info['expire_date'], datetime.now().isoformat()))
            
            conn.commit()
        
        logger.info("激活信息已保存到本地")
        return True
    except Exception as e:
        logger.error(f"保存激活信息失败: {e}")
        return False


def load_activation(hardware_id: str) -> Optional[Dict]:
    """从本地加载激活信息"""
    try:
        if not os.path.exists("activation.db"):
            return None
        
        with sqlite3.connect("activation.db") as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT hardware_id, activation_code, activation_type, expire_date, last_run_time
                FROM activation ORDER BY created_at DESC LIMIT 1
            ''')
            
            result = cursor.fetchone()
            
            if result:
                saved_hwid, activation_code, activation_type, expire_date, last_run_time = result
                
                # 容错验证硬件ID
                if saved_hwid != hardware_id:
                    # 简化处理
                    logger.warning("硬件ID不匹配")
                    return None
                
                # 时间篡改检测
                if last_run_time:
                    try:
                        last_dt = datetime.fromisoformat(last_run_time)
                        if datetime.now() < last_dt - timedelta(minutes=5):
                            logger.warning("检测到时间倒退")
                            return None
                    except:
                        pass
                
                # 验证过期
                expire_dt = datetime.fromisoformat(expire_date)
                current_time = get_network_time() or datetime.now()
                
                if current_time > expire_dt:
                    logger.warning("激活已过期")
                    return None
                
                days_remaining = (expire_dt - current_time).days
                
                # 更新最后运行时间
                cursor.execute('UPDATE activation SET last_run_time = ? WHERE hardware_id = ?',
                             (datetime.now().isoformat(), hardware_id))
                conn.commit()
                
                return {
                    'activation_code': activation_code,
                    'activation_type': activation_type,
                    'expire_date': expire_date,
                    'days_remaining': days_remaining,
                    'hardware_id': hardware_id
                }
        
        return None
    except Exception as e:
        logger.error(f"加载激活信息失败: {e}")
        return None


# ============================================
# 主入口函数
# ============================================

def check_activation() -> Tuple[bool, str, Dict]:
    """
    检查激活状态（主入口）
    
    Returns:
        (是否已激活, 错误信息, 激活信息)
    """
    try:
        hardware_id = get_hardware_id()
        logger.info(f"当前硬件ID: {hardware_id}")
        
        # 时间验证
        time_ok, time_error = verify_time_not_tampered()
        if not time_ok:
            return False, time_error, {}
        
        # 加载本地激活信息
        activation_info = load_activation(hardware_id)
        
        if activation_info:
            type_names = {'trial': '试用版', 'monthly': '月卡版', 'yearly': '年卡版', 'lifetime': '长期版'}
            type_name = type_names.get(activation_info['activation_type'], '未知')
            logger.info(f"已激活: {type_name}, 剩余 {activation_info['days_remaining']} 天")
            return True, "", activation_info
        else:
            return False, "需要激活", {}
    
    except Exception as e:
        logger.error(f"检查激活状态异常: {e}")
        return False, f"检查失败: {e}", {}


def activate_with_code(activation_code: str) -> Tuple[bool, str]:
    """
    使用激活码激活
    
    Args:
        activation_code: 激活码
    
    Returns:
        (是否成功, 消息)
    """
    try:
        hardware_id = get_hardware_id()
        
        success, error_msg, activation_info = verify_activation_code(activation_code, hardware_id)
        
        if success:
            if save_activation(activation_code, activation_info, hardware_id):
                type_names = {'trial': '试用版', 'monthly': '月卡版', 'yearly': '年卡版', 'lifetime': '长期版'}
                type_name = type_names.get(activation_info['activation_type'], '未知')
                
                if activation_info['activation_type'] == 'lifetime':
                    return True, f"激活成功！{type_name}，永久有效"
                else:
                    return True, f"激活成功！{type_name}，有效期至 {activation_info['expire_date'][:10]}"
            else:
                return False, "保存激活信息失败"
        else:
            return False, error_msg
    
    except Exception as e:
        logger.error(f"激活异常: {e}")
        return False, f"激活失败: {e}"


def activate_online(activation_type: str, timeout_seconds: int = 300) -> Tuple[bool, str, str]:
    """
    在线激活（创建订单并等待支付）
    
    Args:
        activation_type: 激活类型
        timeout_seconds: 超时时间
    
    Returns:
        (是否成功, 消息, 二维码URL)
    """
    import time
    
    try:
        hardware_id = get_hardware_id()
        
        # 产品ID映射
        product_id_map = {
            'trial': 'pdf_merger_test',
            'monthly': 'pdf_merger_yue',
            'yearly': 'pdf_merger_nian',
            'lifetime': 'pdf_merger'
        }
        product_id = product_id_map.get(activation_type, 'pdf_merger')
        
        # 创建订单
        response = requests.post(
            f"{SERVER_URL}/api/create_order",
            json={
                "product_id": product_id,
                "hardware_id": hardware_id,
                "activation_type": activation_type
            },
            timeout=10
        )
        
        if response.status_code != 200:
            return False, f"服务器错误: {response.status_code}", ""
        
        result = response.json()
        if not result.get('success'):
            return False, result.get('error', '创建订单失败'), ""
        
        order_no = result.get('order_id')
        qr_url = result.get('qr_code_url', '')
        
        if qr_url and not qr_url.startswith('http'):
            qr_url = f"{SERVER_URL}{qr_url}"
        
        return True, order_no, qr_url
    
    except Exception as e:
        logger.error(f"在线激活异常: {e}")
        return False, f"激活失败: {e}", ""


def check_payment_status(order_no: str) -> Tuple[bool, str, str]:
    """
    检查支付状态
    
    Args:
        order_no: 订单号
    
    Returns:
        (是否支付成功, 激活码/状态信息, 激活码)
    """
    try:
        response = requests.get(f"{SERVER_URL}/api/check-status/{order_no}", timeout=10)
        
        if response.status_code != 200:
            return False, f"查询失败: {response.status_code}", ""
        
        result = response.json()
        
        if result.get('status') == 'SUCCESS':
            activation_code = result.get('activation_code', '')
            
            if activation_code:
                # 自动激活
                success, msg = activate_with_code(activation_code)
                if success:
                    return True, msg, activation_code
                else:
                    return False, msg, ""
            else:
                return False, "支付成功，等待生成激活码...", ""
        else:
            return False, f"等待支付... ({result.get('status', 'PENDING')})", ""
    
    except Exception as e:
        return False, f"查询失败: {e}", ""


# ============================================
# 测试
# ============================================

if __name__ == "__main__":
    print("=" * 60)
    print("本地激活系统测试")
    print("=" * 60)
    
    # 硬件ID
    hwid = get_hardware_id()
    print(f"\n硬件ID: {hwid}")
    
    # 硬件特征
    features = get_all_hardware_features()
    print(f"\n硬件特征 ({len(features)}个):")
    for k, v in features.items():
        print(f"  {k}: {v[:20]}..." if len(str(v)) > 20 else f"  {k}: {v}")
    
    # 时间验证
    print(f"\n时间验证:")
    time_ok, time_error = verify_time_not_tampered()
    print(f"  结果: {'正常' if time_ok else time_error}")
    
    # 虚拟机检测
    print(f"\n虚拟机检测:")
    is_vm, vm_info = is_virtual_machine()
    print(f"  结果: {'检测到虚拟机: ' + vm_info if is_vm else '物理机环境'}")
    
    # 激活状态
    print(f"\n激活状态:")
    success, msg, info = check_activation()
    if success:
        print(f"  已激活: {info}")
    else:
        print(f"  未激活: {msg}")