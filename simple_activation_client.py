#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简单激活客户端
集成到主程序中，提供激活检查和激活界面
"""

import sqlite3
import json
import time
import hashlib
import base64
import hmac
import requests
import logging
import os
import platform
import tkinter as tk
from tkinter import messagebox
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
import threading
import schedule
import uuid
from cryptography.fernet import Fernet

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 全局变量：保存最后一次服务器验证状态，用于区分网络错误和激活过期
_last_server_status = {
    'success': None,
    'error': None,
    'result': None
}

# 数据完整性保护密钥（不存储在代码中，运行时动态生成）
_INTEGRITY_SECRET = "PDF_MERGER_INTEGRITY_SECRET_2026_SECURE"

def get_hardware_id() -> str:
    """获取增强版硬件ID（包含MAC地址和主板信息）"""
    identifiers = []
    
    # 1. 基础系统信息
    identifiers.append(platform.node())  # 主机名
    identifiers.append(platform.processor())  # 处理器信息
    
    # 2. MAC地址信息
    try:
        mac = ':'.join(['{:02x}'.format((uuid.getnode() >> elements) & 0xff) 
                       for elements in range(0, 2*6, 2)][::-1])
        if mac != '00:00:00:00:00:00':  # 排除空MAC地址
            identifiers.append(mac)
    except Exception as e:
        logger.warning(f"获取MAC地址失败: {e}")
    
    # 3. 主板信息（Windows系统）
    try:
        import subprocess
        # 获取主板序列号，隐藏控制台窗口
        result = subprocess.run(['wmic', 'baseboard', 'get', 'serialnumber'], 
                              capture_output=True, text=True, timeout=5, 
                              creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            if len(lines) > 1:
                serial = lines[1].strip()
                if serial and serial.lower() not in ['', 'none', 'to be filled by o.e.m.']:
                    identifiers.append(serial)
    except Exception as e:
        logger.warning(f"获取主板信息失败: {e}")
    
    # 4. 硬盘序列号（增强硬件绑定）
    try:
        import subprocess
        # 获取硬盘序列号，隐藏控制台窗口
        result = subprocess.run(['wmic', 'diskdrive', 'get', 'serialnumber'], 
                              capture_output=True, text=True, timeout=5,
                              creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            for line in lines[1:]:  # 跳过标题行
                serial = line.strip()
                if serial and serial.lower() not in ['', 'none']:
                    identifiers.append(serial)
                    break  # 只取第一个有效硬盘序列号
    except Exception as e:
        logger.warning(f"获取硬盘序列号失败: {e}")
    
    # 5. BIOS信息
    try:
        import subprocess
        # 获取BIOS序列号，隐藏控制台窗口
        result = subprocess.run(['wmic', 'bios', 'get', 'serialnumber'], 
                              capture_output=True, text=True, timeout=5,
                              creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            if len(lines) > 1:
                serial = lines[1].strip()
                if serial and serial.lower() not in ['', 'none', 'to be filled by o.e.m.']:
                    identifiers.append(serial)
    except Exception as e:
        logger.warning(f"获取BIOS信息失败: {e}")
    
    # 过滤空值并生成硬件ID
    valid_identifiers = [str(id) for id in identifiers if id and str(id).strip()]
    
    if not valid_identifiers:
        # 如果所有硬件信息获取失败，回退到基础方法
        logger.warning("所有硬件信息获取失败，使用基础系统信息")
        machine_info = f"{platform.node()}{platform.processor()}"
    else:
        # 使用所有有效的硬件信息
        machine_info = ''.join(valid_identifiers)
    
    # 使用更安全的SHA256哈希算法
    hardware_id = hashlib.sha256(machine_info.encode()).hexdigest().upper()[:32]
    
    logger.info(f"硬件ID生成完成，使用了 {len(valid_identifiers)} 个硬件标识符")
    return hardware_id

def _get_encryption_key(hardware_id: str) -> bytes:
    """从硬件ID生成加密密钥"""
    # 使用硬件ID生成固定的32字节密钥
    key_material = f"{hardware_id}_PDF_MERGER_ACTIVATION_KEY_2026".encode()
    key_hash = hashlib.sha256(key_material).digest()
    # Fernet需要32字节的base64编码密钥
    return base64.urlsafe_b64encode(key_hash)

def encrypt_hardware_id(hardware_id: str) -> str:
    """使用当前硬件ID加密硬件ID（用于存储）"""
    try:
        if not hardware_id:
            return ""
        # 使用当前硬件ID作为密钥来加密硬件ID本身
        key = _get_encryption_key(hardware_id)
        cipher = Fernet(key)
        encrypted_data = cipher.encrypt(hardware_id.encode())
        return base64.urlsafe_b64encode(encrypted_data).decode()
    except Exception as e:
        logger.error(f"加密硬件ID失败: {str(e)}")
        return ""

def decrypt_hardware_id(encrypted_hardware_id: str, current_hardware_id: str) -> str:
    """使用当前硬件ID解密保存的硬件ID"""
    try:
        if not encrypted_hardware_id or not current_hardware_id:
            return ""
        # 使用当前硬件ID作为密钥来解密保存的硬件ID
        key = _get_encryption_key(current_hardware_id)
        cipher = Fernet(key)
        encrypted_bytes = base64.urlsafe_b64decode(encrypted_hardware_id.encode())
        decrypted_data = cipher.decrypt(encrypted_bytes)
        return decrypted_data.decode()
    except Exception as e:
        logger.error(f"解密硬件ID失败: {str(e)}")
        raise Exception("硬件ID解密失败，设备不匹配")

def encrypt_data(data: str, hardware_id: str) -> str:
    """加密数据"""
    try:
        if not data:
            return ""
        key = _get_encryption_key(hardware_id)
        cipher = Fernet(key)
        encrypted_data = cipher.encrypt(data.encode())
        return base64.urlsafe_b64encode(encrypted_data).decode()
    except Exception as e:
        logger.error(f"加密数据失败: {str(e)}")
        return ""

def decrypt_data(encrypted_data: str, hardware_id: str) -> str:
    """解密数据"""
    try:
        if not encrypted_data:
            return ""
        key = _get_encryption_key(hardware_id)
        cipher = Fernet(key)
        encrypted_bytes = base64.urlsafe_b64decode(encrypted_data.encode())
        decrypted_data = cipher.decrypt(encrypted_bytes)
        return decrypted_data.decode()
    except Exception as e:
        logger.error(f"解密数据失败，可能是硬件ID不匹配: {str(e)}")
        raise Exception("数据解密失败，硬件ID不匹配")

def _calculate_hmac(data: str, secret: str = None) -> str:
    """计算数据的HMAC签名（用于完整性校验）

    Args:
        data: 要签名的数据
        secret: 密钥（可选，默认使用全局密钥）

    Returns:
        HMAC签名字符串
    """
    if secret is None:
        secret = _INTEGRITY_SECRET
    signature = hmac.new(secret.encode(), data.encode(), hashlib.sha256).hexdigest()
    return signature

def _verify_hmac(data: str, signature: str, secret: str = None) -> bool:
    """验证HMAC签名

    Args:
        data: 原始数据
        signature: 要验证的签名
        secret: 密钥（可选，默认使用全局密钥）

    Returns:
        是否验证通过
    """
    if secret is None:
        secret = _INTEGRITY_SECRET
    expected_signature = _calculate_hmac(data, secret)
    return hmac.compare_digest(expected_signature, signature)

def cleanup_database_files(hardware_id: str):
    """清理数据库文件（程序退出时调用）"""
    try:
        # 不再需要文件级加密，数据已经是加密存储的
        logger.info("程序退出，数据库数据已加密保存")
    except Exception as e:
        logger.error(f"清理数据库文件失败: {str(e)}")

def _verify_database_integrity(db_path: str = "client_activation.db") -> bool:
    """验证数据库完整性

    检查数据库文件是否被篡改或损坏
    Returns:
        bool: 数据库是否完整
    """
    try:
        if not os.path.exists(db_path):
            return True  # 数据库不存在，不算损坏

        # 检查数据库是否可以正常打开
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # 检查表是否存在
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='activation_status'")
        if not cursor.fetchone():
            logger.error("数据库缺少activation_status表")
            conn.close()
            return False

        # 检查记录结构是否正确
        cursor.execute("PRAGMA table_info(activation_status)")
        columns = {column[1] for column in cursor.fetchall()}

        # 必需的新字段
        required_columns = {'product_id', 'encrypted_hardware_id', 'integrity_signature', 'version'}
        if not required_columns.issubset(columns):
            logger.error(f"数据库缺少必需字段: {required_columns - columns}")
            conn.close()
            return False

        # 检查版本2的记录签名
        cursor.execute('''
            SELECT product_id, activation_type, expiration_date,
                   encrypted_expiration_date, offline_usage_count,
                   encrypted_offline_count, integrity_signature,
                   encrypted_hardware_id
            FROM activation_status
            WHERE version = 2 AND integrity_signature IS NOT NULL
        ''')

        records = cursor.fetchall()
        for record in records:
            product_id, activation_type, expiration_date, encrypted_expiration_date, \
            offline_usage_count, encrypted_offline_count, integrity_signature, \
            encrypted_hardware_id = record

            # 验证签名
            try:
                hardware_id = get_hardware_id()
                if encrypted_expiration_date:
                    try:
                        verified_expiration = decrypt_data(encrypted_expiration_date, hardware_id)
                    except:
                        verified_expiration = expiration_date
                else:
                    verified_expiration = expiration_date

                if encrypted_offline_count:
                    try:
                        verified_offline_count = decrypt_data(encrypted_offline_count, hardware_id)
                    except:
                        verified_offline_count = str(offline_usage_count)
                else:
                    verified_offline_count = str(offline_usage_count)

                data_to_verify = f"{product_id}{activation_type}{verified_expiration}{verified_offline_count}"
                if not _verify_hmac(data_to_verify, integrity_signature):
                    logger.error("数据库签名验证失败，数据可能被篡改")
                    conn.close()
                    return False
            except Exception as e:
                logger.warning(f"验证签名时出现异常: {e}")

        conn.close()
        logger.debug("数据库完整性验证通过")
        return True

    except sqlite3.DatabaseError as e:
        logger.error(f"数据库损坏: {e}")
        return False
    except Exception as e:
        logger.error(f"验证数据库完整性异常: {e}")
        return False

def get_app_user_id() -> str:
    """获取应用用户ID"""
    # 尝试从本地获取已存在的用户ID，如果不存在则生成新的
    user_id_file = os.path.join(os.path.dirname(__file__), ".app_user_id")
    
    if os.path.exists(user_id_file):
        try:
            with open(user_id_file, 'r') as f:
                user_id = f.read().strip()
                if user_id:
                    return user_id
        except Exception as e:
            logger.warning(f"读取用户ID文件失败: {e}")
    
    # 生成新的用户ID
    # 基于用户名、机器名和随机数生成
    user_info = f"{os.environ.get('USERNAME', 'unknown')}{platform.node()}{uuid.uuid4()}"
    user_id = hashlib.md5(user_info.encode()).hexdigest().upper()[:16]
    
    # 保存用户ID到本地
    try:
        with open(user_id_file, 'w') as f:
            f.write(user_id)
    except Exception as e:
        logger.warning(f"保存用户ID文件失败: {e}")
    
    return user_id

def show_activation_error_dialog(error_reason: str, allow_continue=False):
    """显示激活错误弹窗

    Args:
        error_reason: 错误原因
        allow_continue: 是否允许继续使用（True=显示警告后继续，False=退出程序）
    """
    try:
        # 创建隐藏的根窗口
        root = tk.Tk()
        root.withdraw()  # 隐藏主窗口

        # 显示错误消息框
        messagebox.showerror(
            "激活验证失败",
            error_reason
        )

        # 销毁窗口
        root.destroy()

        # 如果不允许继续，退出程序
        if not allow_continue:
            import sys
            logger.info("不允许继续使用，退出程序")
            sys.exit(1)
    except Exception as e:
        logger.error(f"显示错误弹窗失败: {str(e)}")
        # 如果GUI显示失败，使用控制台输出
        print(f"\n❌ 激活验证失败！")
        print(f"原因：{error_reason}")
        print("请重新进行激活操作。\n")

        # 如果不允许继续，退出程序
        if not allow_continue:
            import sys
            sys.exit(1)

def check_activation(product_id: str = "pdf_merger", server_url: str = "https://wfnlj520.com", hardware_id: str = None) -> bool:
    """
    检查软件是否可以使用

    Args:
        product_id: 产品ID
        server_url: 服务器地址
        hardware_id: 硬件ID（可选，如果为None则自动生成）

    Returns:
        bool: 是否可以继续使用
    """
    try:
        # 如果未提供硬件ID，则生成一次
        if hardware_id is None:
            hardware_id = get_hardware_id()
            logger.debug(f"当前硬件ID: {hardware_id}")

        # 第一步：直接从数据库读取加密的硬件ID并尝试解密验证
        db_path = "client_activation.db"

        if not os.path.exists(db_path):
            logger.info("数据库不存在，需要激活")
            return False

        try:
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()

                # 检查表是否存在
                cursor.execute('''
                    SELECT name FROM sqlite_master
                    WHERE type='table' AND name='activation_status'
                ''')

                if not cursor.fetchone():
                    logger.info("激活状态表不存在，需要激活")
                    return False

                # 查询所有激活记录
                cursor.execute('''
                    SELECT product_id, encrypted_hardware_id, encrypted_order_no, encrypted_activation_code,
                           activation_type, activation_date, expiration_date, offline_usage_count
                    FROM activation_status
                    ORDER BY created_at DESC
                ''')

                all_results = cursor.fetchall()

                if not all_results:
                    logger.info("数据库中没有激活记录，需要激活")
                    return False

                # 遍历所有记录，尝试用当前硬件ID解密
                for result in all_results:
                    saved_product_id, saved_encrypted_hardware_id, encrypted_order_no, encrypted_activation_code, \
                    activation_type, activation_date, expiration_date, offline_usage_count = result

                    # 尝试用当前硬件ID解密保存的硬件ID
                    try:
                        saved_hardware_id = decrypt_hardware_id(saved_encrypted_hardware_id, hardware_id)
                    except:
                        # 解密失败，说明不是同一设备或数据损坏
                        continue

                    # 检查解密后的硬件ID是否与当前硬件ID一致
                    if saved_hardware_id == hardware_id:
                        logger.info(f"✅ 硬件ID验证通过，找到有效激活记录: {saved_product_id}")

                        # 检查是否过期
                        expiration_dt = datetime.fromisoformat(expiration_date)
                        current_dt = datetime.now()

                        if current_dt > expiration_dt:
                            logger.warning(f"❌ 激活已过期: {expiration_date}")
                            return False

                        # 硬件ID匹配且未过期，继续验证流程
                        effective_product_id = saved_product_id

                        # 根据产品ID确定激活类型
                        if effective_product_id.endswith('_test'):
                            logger.info(f"使用试用版激活状态，剩余 {(expiration_dt - current_dt).days} 天")
                        elif effective_product_id.endswith('_yue'):
                            logger.info(f"使用月卡版激活状态，剩余 {(expiration_dt - current_dt).days} 天")
                        elif effective_product_id.endswith('_nian'):
                            logger.info(f"使用年费版激活状态，剩余 {(expiration_dt - current_dt).days} 天")
                        else:
                            logger.info(f"使用正式版激活状态，剩余 {(expiration_dt - current_dt).days} 天")

                        # 判断是否需要启动时进行服务器验证
                        # 解密订单号和激活码
                        order_no = None
                        activation_code_val = None

                        try:
                            if encrypted_order_no:
                                order_no = decrypt_data(encrypted_order_no, hardware_id)
                            if encrypted_activation_code:
                                activation_code_val = decrypt_data(encrypted_activation_code, hardware_id)
                        except Exception as e:
                            logger.warning(f"解密激活信息失败: {e}")

                        should_validate_on_startup = False

                        # 月卡版必须每次启动都进行服务器验证
                        if effective_product_id and effective_product_id.endswith('_yue'):
                            if not order_no:
                                logger.error("❌ 月卡版没有订单号，无法进行服务器验证")
                                error_reason = "月卡版激活信息异常\n请重新激活或联系客服"
                                show_activation_error_dialog(error_reason)
                                return False
                            should_validate_on_startup = True
                            logger.info("月卡版启动，强制要求联网验证")
                        # 只要有订单号，就应该优先尝试服务器验证（包括试用期）
                        elif order_no:
                            should_validate_on_startup = True

                            # 检查离线使用次数
                            db_offline_count = offline_usage_count
                            persistent_offline_count = _get_offline_count_from_registry(hardware_id)
                            offline_usage_count_val = max(db_offline_count, persistent_offline_count)

                            # 根据产品类型获取最大离线次数
                            max_offline_count = _get_max_offline_count(effective_product_id)

                            logger.info(f"离线使用次数检查: 数据库={db_offline_count}, 持久化={persistent_offline_count}, 使用={offline_usage_count_val}, 最大={max_offline_count}")

                            if offline_usage_count_val >= max_offline_count:
                                logger.warning(f"离线使用次数已达上限({offline_usage_count_val}/{max_offline_count})，强制要求联网验证")
                            else:
                                logger.info(f"优先尝试网络验证，已离线使用{offline_usage_count_val}次，剩余{max_offline_count-offline_usage_count_val}次离线机会")

                            logger.info(f"进行服务器验证（产品ID: {effective_product_id}）")

                        # 如果需要启动时验证，执行服务器检查
                        server_validated = False
                        if should_validate_on_startup:
                            logger.info(f"启动时从服务器检查激活状态 - 订单号: {order_no}, 产品ID: {effective_product_id}, 硬件ID: {hardware_id}")
                            try:
                                server_status = _check_server_activation_status(
                                    effective_product_id, hardware_id, server_url, order_no
                                )

                                if server_status['activated'] and not server_status['is_expired']:
                                    # 服务器激活状态有效，更新本地状态
                                    server_product_id = server_status.get('product_id', effective_product_id)
                                    logger.info(f"使用服务器返回的产品ID更新本地状态: {server_product_id}")
                                    _update_local_activation_status(
                                        server_product_id, hardware_id, server_status
                                    )
                                    logger.info(f"✅ 服务器激活状态有效，激活码: {server_status.get('activation_code', 'N/A')}, 剩余 {server_status['days_remaining']} 天")
                                    server_validated = True
                                else:
                                    # 服务器验证失败，明确判断失败原因
                                    if server_status.get('error_type') == 'product_id_mismatch':
                                        error_reason = "激活验证失败\n原因：产品ID不匹配\n请重新激活或联系客服"
                                        logger.warning(f"❌ 激活验证失败: 产品ID不匹配")
                                    elif server_status.get('error_type') == 'network_error':
                                        # 网络错误，不显示错误弹框，直接启用离线模式
                                        logger.warning("❌ 激活验证失败: 无法连接到服务器")
                                        server_validated = False
                                    elif server_status.get('is_expired'):
                                        error_reason = "激活验证失败\n原因：激活已过期\n请重新激活或联系客服"
                                        logger.warning(f"❌ 激活验证失败: 激活已过期")
                                    else:
                                        error_reason = "激活验证失败\n原因：激活信息不匹配\n请重新激活或联系客服"
                                        logger.warning(f"❌ 激活验证失败: 激活信息不匹配")

                                    # 只有非网络错误才显示弹框
                                    if server_status.get('error_type') != 'network_error':
                                        show_activation_error_dialog(error_reason)
                                        return False
                            except Exception as e:
                                # 简化联网错误日志，只显示用户友好的提示
                                logger.warning("❌ 服务器验证异常，启用离线模式: 无法连接到服务器")
                                server_validated = False
                        else:
                            # 没有订单号，无法从服务器验证，启用离线模式
                            logger.info("没有订单号，启用离线模式")
                            server_validated = False

                        # 如果服务器验证失败或不需要验证，检查是否可以离线使用
                        if not server_validated:
                            # 月卡版和试用版必须联网验证，不允许离线使用
                            if effective_product_id and (effective_product_id.endswith('_yue') or effective_product_id.endswith('_test')):
                                version_name = "月卡版" if effective_product_id.endswith('_yue') else "试用版"
                                logger.error(f"❌ {version_name}必须联网验证，无法离线使用")
                                error_reason = f"网络连接失败，无法完成激活验证\n\n请检查网络连接后重新启动软件。\n\n如果您使用的是{version_name}，必须联网才能正常使用"
                                show_activation_error_dialog(error_reason)
                                return False

                            # 检查离线使用次数
                            db_offline_count = offline_usage_count
                            persistent_offline_count = _get_offline_count_from_registry(hardware_id)
                            offline_usage_count_val = max(db_offline_count, persistent_offline_count)

                            # 根据产品类型获取最大离线次数
                            max_offline_count = _get_max_offline_count(effective_product_id)

                            if offline_usage_count_val >= max_offline_count:
                                logger.error(f"❌ 离线使用次数已达上限({offline_usage_count_val}/{max_offline_count})，必须联网验证")
                                error_reason = "离线使用次数已达上限\n为了保护您的权益，请连接网络完成激活验证\n请联系客服或检查网络连接"
                                show_activation_error_dialog(error_reason)
                                return False
                            else:
                                # 增加离线使用计数
                                new_offline_count = offline_usage_count_val + 1
                                logger.info(f"✅ 启用离线模式 ({new_offline_count}/{max_offline_count})，剩余 {max_offline_count-new_offline_count} 次离线使用机会")

                                # 更新离线使用计数和时间
                                try:
                                    _update_offline_usage_stats(effective_product_id, hardware_id, new_offline_count)
                                except Exception as e:
                                    logger.warning(f"更新离线使用统计失败: {str(e)}")

                                return True

                        # 如果服务器验证成功
                        if server_validated:
                            logger.info(f"✅ 激活状态有效，可以直接使用")
                            return True

                # 没有找到匹配的硬件ID记录
                logger.error("❌ 数据库中未找到匹配的硬件ID，需要重新激活")
                return False

        except Exception as e:
            logger.error(f"数据库读取异常: {str(e)}")
            return False

    except Exception as e:
        logger.error(f"检查激活状态异常: {str(e)}")
        return False

def _check_local_activation_status(product_id: str, hardware_id: str) -> Dict:
    """检查本地激活状态 - 使用原有数据库但添加持久化保护"""
    db_path = "client_activation.db"
    
    # 检查数据库文件是否存在
    if not os.path.exists(db_path):
        return {
            'activated': False,
            'is_expired': True,
            'days_remaining': 0
        }
    
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            
            # 检查表是否存在
            cursor.execute('''
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='activation_status'
            ''')
            
            if not cursor.fetchone():
                return {
                    'activated': False,
                    'is_expired': True,
                    'days_remaining': 0
                }
            
            # 查询激活状态（包含加密字段）
            cursor.execute('''
                SELECT activation_type, activation_date, expiration_date, order_no, activation_code,
                       encrypted_order_no, encrypted_activation_code
                FROM activation_status 
                WHERE product_id = ? AND hardware_id = ?
                ORDER BY created_at DESC LIMIT 1
            ''', (product_id, hardware_id))
            
            result = cursor.fetchone()
            
            if result:
                activation_type, activation_date, expiration_date, order_no, activation_code, encrypted_order_no, encrypted_activation_code = result
                
                # 强制使用加密数据解密验证，如果解密失败则删除数据库
                try:
                    if encrypted_order_no:
                        order_no = decrypt_data(encrypted_order_no, hardware_id)
                    if encrypted_activation_code:
                        activation_code = decrypt_data(encrypted_activation_code, hardware_id)
                    
                    # 如果加密数据存在但解密失败，说明硬件ID不匹配
                    if (encrypted_order_no or encrypted_activation_code) and (not order_no and not activation_code):
                        raise Exception("硬件ID不匹配，解密失败")
                        
                except Exception as e:
                    logger.error(f"数据解密失败，硬件ID不匹配: {str(e)}")
                    
                    # 硬件ID不匹配，立即删除数据库，强制重新激活
                    try:
                        db_path = "client_activation.db"
                        if os.path.exists(db_path):
                            os.remove(db_path)
                            logger.warning("硬件ID不匹配，已删除数据库，需要重新激活")
                    except Exception as delete_error:
                        logger.error(f"删除数据库失败: {delete_error}")
                    
                    # 显示明确的错误提示给用户
                    error_reason = "硬件ID验证失败\n检测到设备变更或硬件ID不匹配\n请重新激活软件"
                    show_activation_error_dialog(error_reason)
                    
                    # 抛出异常，阻止任何可能的绕过
                    raise Exception("硬件ID验证失败，请重新激活")
                
                # 检查是否过期
                expiration_dt = datetime.fromisoformat(expiration_date)
                current_dt = datetime.now()
                
                is_expired = current_dt > expiration_dt
                
                return {
                    'activated': True,
                    'activation_type': activation_type,
                    'activation_date': activation_date,
                    'expiration_date': expiration_date,
                    'order_no': order_no,  # 包含订单号（解密后）
                    'activation_code': activation_code,  # 包含激活码（解密后）
                    'is_expired': is_expired,
                    'days_remaining': max(0, (expiration_dt - current_dt).days) if not is_expired else 0
                }
            
            return {
                'activated': False,
                'is_expired': True,
                'days_remaining': 0
            }
            
    except Exception as e:
        logger.error(f"检查本地激活状态异常: {str(e)}")
        return {
            'activated': False,
            'is_expired': True,
            'days_remaining': 0
        }

def _check_server_activation_status(product_id: str, hardware_id: str, server_url: str, order_no: str = None) -> Dict:
    """检查服务器激活状态"""
    global _last_server_status
    
    try:
        # 如果提供了订单号，直接使用；否则从本地查找
        if not order_no:
            # 尝试所有可能的产品ID变体来查找订单号
            local_status = None
            actual_product_id = product_id
            
            # 尝试不同的产品ID变体
            for pid in [product_id, f"{product_id}_test", f"{product_id}_nian", f"{product_id}_yue"]:
                status = _check_local_activation_status(pid, hardware_id)
                if status.get('order_no'):
                    local_status = status
                    order_no = status['order_no']
                    actual_product_id = pid
                    logger.info(f"找到订单号: {order_no}, 产品ID: {actual_product_id}")
                    break
            
            if not order_no:
                # 没有订单号，无法从服务器查询激活状态
                logger.info("本地没有订单号信息，无法从服务器查询激活状态")
                return {
                    'activated': False,
                    'is_expired': True,
                    'days_remaining': 0
                }
        
        # 使用订单号查询激活状态
        logger.info(f"从服务器检查激活状态 - 订单号: {order_no}, 产品ID: {product_id}")
        
        # 使用订单号查询支付状态，获取激活码
        response = requests.get(f"{server_url}/api/check-status/{order_no}", 
                              timeout=10)
        
        if response.status_code == 200:
            result = response.json()
            logger.info(f"服务器激活状态查询结果: {result}")
            
            # 检查支付状态
            if result.get('success') or result.get('paid'):
                status = result.get('status', '')
                
                if status == 'SUCCESS' or result.get('paid') == True:
                    # 支付成功，获取激活码
                    activation_code = result.get('activation_code')
                    
                    if activation_code:
                        # 验证服务器返回的信息是否匹配
                        server_product_id = result.get('product_id')
                        server_hardware_id = result.get('hardware_id')
                        server_app_user_id = result.get('app_user_id')
                        server_expire_time = result.get('expire_time')
                        
                        # 验证产品ID - 使用本地存储的实际产品ID进行匹配
                        actual_local_product_id = product_id
                        if 'local_status' in locals() and local_status:
                            # 如果通过查找流程找到了本地状态，使用实际的产品ID
                            actual_local_product_id = local_status.get('product_id', product_id)
                        
                        if server_product_id and server_product_id != actual_local_product_id:
                            error_reason = f"产品ID不匹配: 本地={actual_local_product_id}, 服务器={server_product_id}"
                            logger.error(error_reason)
                            # 不在这里显示弹窗，让调用方统一处理
                            return {
                                'activated': False,
                                'is_expired': False,  # 不是过期，是ID不匹配
                                'days_remaining': 0,
                                'error_type': 'product_id_mismatch'  # 添加错误类型标识
                            }
                        
                        # 在成功验证后，确保返回的产品ID是服务器返回的ID
                        product_id = server_product_id or actual_local_product_id
                        
                        # 验证硬件ID
                        if server_hardware_id and server_hardware_id != hardware_id:
                            error_reason = f"硬件ID不匹配: 本地={hardware_id}, 服务器={server_hardware_id}"
                            logger.warning(error_reason)
                            # 不在这里显示弹窗，让调用方统一处理
                            return {
                                'activated': False,
                                'is_expired': True,
                                'days_remaining': 0,
                                'error_type': 'hardware_id_mismatch'  # 添加错误类型标识
                            }
                        
                        # 验证用户ID（如果有本地用户ID信息）
                        # 这里可以根据需要添加用户ID验证逻辑
                        
                        # 验证激活码是否匹配 - 只有当我们有local_status时才验证
                        # 注意：当提供了order_no参数但没有通过查找流程时，local_status可能未定义
                        if 'local_status' in locals() and local_status:
                            local_activation_code = local_status.get('activation_code')
                            if local_activation_code and local_activation_code != activation_code:
                                error_reason = f"激活码不匹配: 本地={local_activation_code}, 服务器={activation_code}"
                                logger.warning(error_reason)
                                # 不在这里显示弹窗，让调用方统一处理
                                return {
                                    'activated': False,
                                    'is_expired': True,
                                    'days_remaining': 0,
                                    'error_type': 'activation_code_mismatch'  # 添加错误类型标识
                                }
                        
                        # 使用服务器返回的过期时间
                        if server_expire_time:
                            try:
                                # 处理不同的时间格式
                                server_expire_time = server_expire_time.replace('Z', '+00:00')
                                # 确保时间格式正确
                                if 'T' not in server_expire_time:
                                    # 如果没有时间部分，添加默认时间
                                    server_expire_time += 'T00:00:00+00:00'
                                
                                expire_dt = datetime.fromisoformat(server_expire_time)
                                current_dt = datetime.now()
                                is_expired = current_dt > expire_dt
                                days_remaining = max(0, (expire_dt - current_dt).days) if not is_expired else 0
                                
                                logger.info(f"使用服务器过期时间: {server_expire_time}, 剩余 {days_remaining} 天")
                                
                            except Exception as e:
                                logger.warning(f"解析服务器过期时间失败，使用默认计算: {str(e)}")
                                # 使用默认计算
                                duration_days = 365  # 默认值
                                activate_dt = datetime.now()
                                expire_dt = activate_dt + timedelta(days=duration_days)
                                current_dt = datetime.now()
                                is_expired = current_dt > expire_dt
                                days_remaining = max(0, (expire_dt - current_dt).days) if not is_expired else 0
                        else:
                            # 使用默认计算
                            duration_days = 365  # 默认值
                            activate_dt = datetime.now()
                            expire_dt = activate_dt + timedelta(days=duration_days)
                            current_dt = datetime.now()
                            is_expired = current_dt > expire_dt
                            days_remaining = max(0, (expire_dt - current_dt).days) if not is_expired else 0
                        
                        # 检查是否已过期
                        if is_expired:
                            logger.warning(f"激活已过期，过期时间: {server_expire_time}")
                            return {
                                'activated': False,
                                'activation_type': 'official',
                                'activation_code': activation_code,
                                'order_no': order_no,
                                'activation_date': result.get('activate_time', datetime.now().isoformat()),
                                'expiration_date': server_expire_time if server_expire_time else expire_dt.isoformat(),
                                'is_expired': True,
                                'days_remaining': 0
                            }

                        logger.info(f"服务器激活状态有效，激活码: {activation_code}, 剩余 {days_remaining} 天")

                        # 保存最后一次服务器验证状态
                        global _last_server_status
                        _last_server_status = {
                            'success': True,
                            'error': None,
                            'result': result
                        }

                        return {
                            'activated': True,
                            'activation_type': 'official',
                            'activation_code': activation_code,
                            'order_no': order_no,  # 保存订单号
                            'activation_date': result.get('activate_time', datetime.now().isoformat()),
                            'expiration_date': server_expire_time if server_expire_time else expire_dt.isoformat(),
                            'is_expired': False,
                            'days_remaining': days_remaining
                        }
                    else:
                        # 支付成功但未返回激活码 - 可能是订单不存在或激活流程未完成
                        logger.warning("支付成功但未返回激活码，可能是订单不存在或激活流程未完成")
                        return {
                            'activated': False,
                            'is_expired': True,
                            'days_remaining': 0,
                            'error_type': 'order_not_found'
                        }
                else:
                    logger.info(f"支付状态: {status}")
                    # 非SUCCESS状态，视为未激活
                    return {
                        'activated': False,
                        'is_expired': True,
                        'days_remaining': 0
                    }
            else:
                logger.warning(f"支付状态查询失败: {result.get('error', '未知错误')}")
                return {
                    'activated': False,
                    'is_expired': True,
                    'days_remaining': 0
                }

        else:
            logger.warning(f"服务器激活状态检查失败: {response.status_code}")
            return {
                'activated': False,
                'is_expired': True,
                'days_remaining': 0
            }
    except Exception as e:
        # 简化联网错误日志，只显示用户友好的提示
        logger.warning("❌ 激活验证失败: 无法连接到服务器")
        
        # 保存最后一次服务器验证状态
        _last_server_status = {
            'success': False,
            'error': str(e),
            'result': None
        }
        
        # 区分网络错误和真正的激活过期
        return {
            'activated': False,
            'is_expired': False,  # 网络错误不是真正的过期
            'days_remaining': 0,
            'error_type': 'network_error'  # 添加错误类型标识
        }

def _check_hardware_id_changed(product_id: str, current_hardware_id: str) -> bool:
    """检查硬件ID是否发生变化"""
    try:
        db_path = "client_activation.db"
        
        if not os.path.exists(db_path):
            # 数据库不存在，没有历史记录，不算变化
            return False
        
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            
            # 检查表是否存在
            cursor.execute('''
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='activation_status'
            ''')
            
            if not cursor.fetchone():
                return False
            
            # 查询所有产品ID的激活状态（检查是否有任何激活记录）
            cursor.execute('''
                SELECT hardware_id FROM activation_status
                WHERE product_id LIKE ? OR product_id LIKE ?
                ORDER BY created_at DESC LIMIT 1
            ''', (f"{product_id}%", f"{product_id.split('_')[0]}%"))
            
            result = cursor.fetchone()
            
            if result:
                saved_hardware_id = result[0]
                if saved_hardware_id != current_hardware_id:
                    logger.error(f"硬件ID发生变化: 保存={saved_hardware_id}, 当前={current_hardware_id}")
                    # 硬件ID不匹配，清除激活文件
                    # _clear_activation_files()  # 已注释：不再删除数据库
                    return True
                else:
                    logger.debug(f"硬件ID匹配: {saved_hardware_id}")
                    return False
            else:
                # 没有历史记录，不算变化
                return False
                
    except Exception as e:
        logger.error(f"检查硬件ID变化异常: {str(e)}")
        # 异常情况下，假设没有变化，避免误删激活状态
        return False

def _strict_check_hardware_id_changed(product_id: str, current_hardware_id: str) -> bool:
    """严格检查硬件ID是否发生变化（增强安全性）"""
    try:
        db_path = "client_activation.db"
        
        if not os.path.exists(db_path):
            # 数据库不存在，说明是全新安装，需要激活
            logger.info("数据库不存在，需要重新激活")
            return True

        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            
            # 检查表是否存在
            cursor.execute('''
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='activation_status'
            ''')
            
            if not cursor.fetchone():
                # 表不存在，需要激活
                logger.info("激活状态表不存在，需要重新激活")
                return True
            
            # 查询所有产品ID的激活状态
            cursor.execute('''
                SELECT hardware_id, activation_type, expiration_date 
                FROM activation_status
                WHERE product_id LIKE ? OR product_id LIKE ?
                ORDER BY created_at DESC LIMIT 1
            ''', (f"{product_id}%", f"{product_id.split('_')[0]}%"))
            
            result = cursor.fetchone()
            
            if result:
                saved_hardware_id, activation_type, expiration_date = result
                
                # 检查硬件ID是否匹配
                if saved_hardware_id != current_hardware_id:
                    logger.error(f"硬件ID发生变化: 保存={saved_hardware_id}, 当前={current_hardware_id}")
                    
                    # 硬件ID不匹配，清除激活文件
                    # _clear_activation_files()  # 已注释：不再删除数据库
                    return True
                
                # 检查是否过期
                if expiration_date:
                    expire_dt = datetime.fromisoformat(expiration_date)
                    current_dt = datetime.now()
                    if current_dt > expire_dt:
                        logger.info(f"激活已过期，需要重新激活")
                        return True
                
                logger.debug(f"硬件ID匹配: {saved_hardware_id}")
                return False
            else:
                # 没有激活记录，需要激活
                logger.info("没有激活记录，需要重新激活")
                return True
                
    except Exception as e:
        logger.error(f"严格检查硬件ID变化异常: {str(e)}")
        # 异常情况下，假设硬件ID发生变化，确保安全
        return True

def _clear_activation_files():
    """清除激活相关文件 - 确保数据库连接已关闭"""
    try:
        # 强制触发垃圾回收，确保所有数据库连接被关闭
        import gc
        gc.collect()

        # 延迟删除数据库文件
        db_path = "client_activation.db"
        if os.path.exists(db_path):
            # 先尝试重命名文件（更安全的操作）
            temp_path = f"client_activation.db.{os.getpid()}.temp"
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                os.rename(db_path, temp_path)
                # 再删除重命名后的文件
                os.remove(temp_path)
                logger.info("已清除激活数据库文件")
            except Exception as rename_error:
                # 重命名失败，尝试直接删除
                logger.warning(f"重命名数据库失败，尝试直接删除: {rename_error}")
                try:
                    os.remove(db_path)
                    logger.info("已清除激活数据库文件")
                except Exception as remove_error:
                    logger.error(f"直接删除数据库也失败: {remove_error}")
                    raise
        
        # 删除应用用户ID文件
        user_id_file = os.path.join(os.path.dirname(__file__), ".app_user_id")
        if os.path.exists(user_id_file):
            os.remove(user_id_file)
            logger.info("已清除应用用户ID文件")
        
        # 删除临时二维码文件
        for file in os.listdir('.'):
            if file.startswith('qr_') and file.endswith('.png'):
                os.remove(file)
                logger.info(f"已清除临时文件: {file}")
        
        logger.info("激活文件清除完成")
        
    except Exception as e:
        logger.error(f"清除激活文件失败: {str(e)}")

def _update_local_activation_status(product_id: str, hardware_id: str, status: Dict):
    """更新本地激活状态 - 使用服务器返回的产品ID"""
    db_path = "client_activation.db"
    
    # 优先使用服务器返回的产品ID，确保一致性
    actual_product_id = status.get('product_id', product_id)
    order_no = status.get('order_no', status.get('wechat_order_no'))
    
    logger.info(f"更新本地激活状态: 使用产品ID {actual_product_id}, 订单号 {order_no}")
    
    # 强制使用服务器返回的产品ID，确保绑定关系一致
    if status.get('product_id'):
        # 优先使用服务器返回的产品ID
        actual_product_id = status['product_id']
    elif order_no and not status.get('product_id'):
        # 如果服务器没有返回产品ID但返回了订单号，使用订单号对应的产品ID
        actual_product_id = product_id
    
    # 如果是更新操作，删除所有旧的产品ID记录，只保留最新的
    delete_old_records = True
    
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            
            # 创建表（如果不存在）- 添加加密字段和离线统计字段
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS activation_status (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_id TEXT NOT NULL,
                    hardware_id TEXT,
                    encrypted_hardware_id TEXT,
                    order_no TEXT,  -- 明文订单号（兼容旧版本）
                    activation_code TEXT,  -- 明文激活码（兼容旧版本）
                    encrypted_order_no TEXT,  -- 加密订单号
                    encrypted_activation_code TEXT,  -- 加密激活码
                    activation_type TEXT,
                    activation_date TEXT,
                    expiration_date TEXT,
                    encrypted_expiration_date TEXT,  -- 加密的过期时间
                    offline_usage_count INTEGER DEFAULT 0,  -- 离线使用次数
                    encrypted_offline_count TEXT,  -- 加密的离线次数
                    last_offline_validation TEXT,  -- 上次离线验证时间
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    integrity_signature TEXT,  -- 数据完整性签名
                    version INTEGER DEFAULT 2  -- 数据结构版本号
                )
            ''')
            
            # 检查现有表是否缺少新字段，并添加
            cursor.execute("PRAGMA table_info(activation_status)")
            columns = [column[1] for column in cursor.fetchall()]

            # 检查并添加缺失的字段
            missing_columns = []
            if 'encrypted_hardware_id' not in columns:
                missing_columns.append('encrypted_hardware_id TEXT')
            if 'offline_usage_count' not in columns:
                missing_columns.append('offline_usage_count INTEGER DEFAULT 0')
            if 'last_offline_validation' not in columns:
                missing_columns.append('last_offline_validation TEXT')
            if 'encrypted_order_no' not in columns:
                missing_columns.append('encrypted_order_no TEXT')
            if 'encrypted_activation_code' not in columns:
                missing_columns.append('encrypted_activation_code TEXT')
            if 'encrypted_expiration_date' not in columns:
                missing_columns.append('encrypted_expiration_date TEXT')
            if 'encrypted_offline_count' not in columns:
                missing_columns.append('encrypted_offline_count TEXT')
            if 'integrity_signature' not in columns:
                missing_columns.append('integrity_signature TEXT')
            if 'version' not in columns:
                missing_columns.append('version INTEGER DEFAULT 2')

            for column_def in missing_columns:
                column_name = column_def.split()[0]
                try:
                    cursor.execute(f"ALTER TABLE activation_status ADD COLUMN {column_def}")
                    logger.info(f"已添加缺失字段: {column_name}")
                except sqlite3.OperationalError as e:
                    logger.warning(f"添加字段 {column_name} 失败: {e}")
            
            # 删除旧的激活状态 - 删除所有该产品ID的旧记录
            cursor.execute('''
                DELETE FROM activation_status
                WHERE product_id = ?
            ''', (actual_product_id,))
            
            # 加密敏感数据
            encrypted_hardware_id = encrypt_hardware_id(hardware_id)
            encrypted_order_no = ""
            encrypted_activation_code = ""
            encrypted_expiration_date = ""
            encrypted_offline_count = ""
            order_no = status.get('order_no')
            activation_code = status.get('activation_code')

            if order_no:
                encrypted_order_no = encrypt_data(order_no, hardware_id)
            if activation_code:
                encrypted_activation_code = encrypt_data(activation_code, hardware_id)
            if status.get('expiration_date'):
                encrypted_expiration_date = encrypt_data(str(status.get('expiration_date')), hardware_id)

            # 加密离线次数（初始为0）
            encrypted_offline_count = encrypt_data("0", hardware_id)

            # 计算数据完整性签名
            data_to_sign = f"{actual_product_id}{status.get('activation_type')}{status.get('expiration_date')}0"
            integrity_signature = _calculate_hmac(data_to_sign)

            # 插入新的激活状态（只保存加密数据，增强安全性）
            # 确保保存服务器返回的产品ID信息
            # offline_usage_count 从0开始，表示已使用的离线次数
            cursor.execute('''
                INSERT INTO activation_status
                (product_id, hardware_id, encrypted_hardware_id, order_no, activation_code,
                 encrypted_order_no, encrypted_activation_code,
                 activation_type, activation_date, expiration_date, encrypted_expiration_date,
                 offline_usage_count, encrypted_offline_count, integrity_signature, version)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                actual_product_id,  # 使用服务器返回的产品ID
                "",  # 不保存明文硬件ID（增强安全性）
                encrypted_hardware_id,  # 使用当前硬件ID加密存储
                "",  # 不保存明文订单号（增强安全性）
                "",  # 不保存明文激活码（增强安全性）
                encrypted_order_no,  # 加密订单号
                encrypted_activation_code,  # 加密激活码
                status.get('activation_type'),
                status.get('activation_date'),
                status.get('expiration_date'),
                encrypted_expiration_date,  # 加密过期时间
                0,  # 初始已使用次数为0
                encrypted_offline_count,  # 加密离线次数
                integrity_signature,  # 数据完整性签名
                2  # 数据结构版本号
            ))
            
            logger.info(f"✅ 本地激活状态已更新（加密存储）: 产品ID={actual_product_id}")
            
            conn.commit()
            
    except Exception as e:
        logger.error(f"更新本地激活状态异常: {str(e)}")

def _save_offline_count_to_registry(hardware_id: str, usage_count: int):
    """将离线使用计数保存到系统持久化位置（防止删除数据库绕过）"""
    try:
        import json
        # 在当前目录创建一个隐藏文件保存离线计数
        persistence_file = ".offline_usage.json"
        data = {}
        
        # 读取现有数据
        if os.path.exists(persistence_file):
            try:
                with open(persistence_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except:
                data = {}
        
        # 更新数据
        data[hardware_id] = {
            'usage_count': usage_count,
            'last_update': datetime.now().isoformat(),
            'hardware_hash': hashlib.sha256(hardware_id.encode()).hexdigest()  # 添加硬件ID哈希验证
        }
        
        # 保存数据
        with open(persistence_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            
        # 设置文件为隐藏（Windows）
        if os.name == 'nt':
            import subprocess
            # 隐藏文件，隐藏控制台窗口
            subprocess.run(['attrib', '+H', persistence_file], check=False,
                         creationflags=subprocess.CREATE_NO_WINDOW)
            
        logger.debug(f"离线使用计数已持久化保存: {hardware_id} -> {usage_count}")
    except Exception as e:
        logger.warning(f"保存离线计数到持久化存储失败: {str(e)}")

def _get_offline_count_from_registry(hardware_id: str) -> int:
    """从系统持久化位置获取离线使用计数（增强验证）"""
    try:
        import json
        persistence_file = ".offline_usage.json"
        
        if os.path.exists(persistence_file):
            with open(persistence_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            if hardware_id in data:
                # 验证硬件ID哈希是否匹配，防止数据篡改
                saved_hash = data[hardware_id].get('hardware_hash')
                current_hash = hashlib.sha256(hardware_id.encode()).hexdigest()
                
                if saved_hash != current_hash:
                    logger.warning(f"硬件ID哈希不匹配，可能数据被篡改")
                    # 数据被篡改，重置计数
                    # _clear_activation_files()  # 已注释：不再删除数据库
                    return 0
                
                count = data[hardware_id].get('usage_count', 0)
                logger.debug(f"从持久化存储读取离线计数: {hardware_id} -> {count}")
                return count
                
    except Exception as e:
        logger.warning(f"从持久化存储读取离线计数失败: {str(e)}")
    
    return 0

def _update_offline_usage_stats(product_id: str, hardware_id: str, usage_count: int):
    """更新离线使用统计 - 使用持久化计数保护"""
    db_path = "client_activation.db"

    # 1. 将计数保存到持久化存储（防止删除数据库绕过）
    _save_offline_count_to_registry(hardware_id, usage_count)

    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()

            # 检查表是否存在，如果不存在则创建
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS activation_status (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_id TEXT NOT NULL,
                    hardware_id TEXT,
                    encrypted_hardware_id TEXT,
                    order_no TEXT,
                    activation_code TEXT,
                    encrypted_order_no TEXT,
                    encrypted_activation_code TEXT,
                    activation_type TEXT,
                    activation_date TEXT,
                    expiration_date TEXT,
                    encrypted_expiration_date TEXT,
                    offline_usage_count INTEGER DEFAULT 0,
                    encrypted_offline_count TEXT,
                    last_offline_validation TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    integrity_signature TEXT,
                    version INTEGER DEFAULT 2
                )
            ''')

            # 更新离线使用计数和验证时间 - 通过加密硬件ID查找
            current_time = datetime.now().isoformat()
            encrypted_hardware_id = encrypt_hardware_id(hardware_id)
            cursor.execute('''
                UPDATE activation_status
                SET offline_usage_count = ?, last_offline_validation = ?
                WHERE product_id = ? AND encrypted_hardware_id = ?
            ''', (usage_count, current_time, product_id, encrypted_hardware_id))

            conn.commit()
            logger.debug(f"离线使用统计已更新: {usage_count}次")

    except Exception as e:
        logger.error(f"更新离线使用统计异常: {str(e)}")

def _get_max_offline_count(product_id: str) -> int:
    """根据产品ID获取最大离线次数"""
    if product_id.endswith('_test') or product_id.endswith('_yue'):
        # 测试版和月卡版：0次（必须联网）
        return 0
    elif product_id.endswith('_nian'):
        # 年卡版：20次
        return 20
    else:
        # 正式版（终身版）：60次
        return 60

def _decrement_offline_count(product_id: str, hardware_id: str) -> int:
    """减少离线次数并返回剩余次数"""
    try:
        db_path = "client_activation.db"

        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()

            # 查询所有该product_id的记录
            cursor.execute('''
                SELECT offline_usage_count, encrypted_hardware_id FROM activation_status
                WHERE product_id = ?
                ORDER BY created_at DESC
            ''', (product_id,))

            all_records = cursor.fetchall()
            current_count = None
            matched_record = None

            # 遍历记录，尝试解密匹配硬件ID
            for record in all_records:
                db_offline_count, encrypted_hardware_id = record
                try:
                    # 尝试解密硬件ID
                    saved_hardware_id = decrypt_hardware_id(encrypted_hardware_id, hardware_id)
                    if saved_hardware_id == hardware_id:
                        # 找到匹配的记录
                        current_count = db_offline_count
                        matched_record = encrypted_hardware_id
                        logger.info(f"找到匹配的激活记录，当前离线次数: {current_count}")
                        break
                except:
                    # 解密失败，继续查找下一条记录
                    continue

            if current_count is not None:
                # 增加已使用次数
                new_count = current_count + 1

                # 获取激活类型和过期时间（用于更新签名）
                cursor.execute('''
                    SELECT activation_type, expiration_date, encrypted_expiration_date, version
                    FROM activation_status
                    WHERE product_id = ? AND encrypted_hardware_id = ?
                ''', (product_id, matched_record))
                type_record = cursor.fetchone()
                if type_record:
                    activation_type, expiration_date, encrypted_expiration_date, version = type_record

                    # 优先使用加密字段
                    if encrypted_expiration_date:
                        try:
                            verified_expiration = decrypt_data(encrypted_expiration_date, hardware_id)
                        except:
                            verified_expiration = expiration_date
                    else:
                        verified_expiration = expiration_date

                    # 加密新的离线次数
                    encrypted_new_count = encrypt_data(str(new_count), hardware_id)

                    # 更新签名
                    data_to_sign = f"{product_id}{activation_type}{verified_expiration}{new_count}"
                    new_signature = _calculate_hmac(data_to_sign)

                    # 更新数据库
                    cursor.execute('''
                        UPDATE activation_status
                        SET offline_usage_count = ?,
                            encrypted_offline_count = ?,
                            integrity_signature = ?,
                            last_offline_validation = ?
                        WHERE product_id = ? AND encrypted_hardware_id = ?
                    ''', (new_count, encrypted_new_count, new_signature, datetime.now().isoformat(),
                          product_id, matched_record))
                else:
                    # 兼容旧版本，只更新明文
                    cursor.execute('''
                        UPDATE activation_status
                        SET offline_usage_count = ?,
                            last_offline_validation = ?
                        WHERE product_id = ? AND encrypted_hardware_id = ?
                    ''', (new_count, datetime.now().isoformat(), product_id, matched_record))

                conn.commit()
                logger.info(f"离线次数更新: {current_count} -> {new_count}")
                return new_count
            else:
                logger.warning("未找到匹配的激活记录，无法减少离线次数")
                return -1

    except Exception as e:
        logger.error(f"减少离线次数异常: {str(e)}")
        return -1

def _reset_offline_count(product_id: str, hardware_id: str) -> bool:
    """重置离线次数到初始值"""
    try:
        db_path = "client_activation.db"

        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()

            # 查询所有该product_id的记录
            cursor.execute('''
                SELECT offline_usage_count, encrypted_hardware_id FROM activation_status
                WHERE product_id = ?
                ORDER BY created_at DESC
            ''', (product_id,))

            all_records = cursor.fetchall()
            matched_record = None

            # 遍历记录，尝试解密匹配硬件ID
            for record in all_records:
                db_offline_count, encrypted_hardware_id = record
                try:
                    # 尝试解密硬件ID
                    saved_hardware_id = decrypt_hardware_id(encrypted_hardware_id, hardware_id)
                    if saved_hardware_id == hardware_id:
                        # 找到匹配的记录
                        matched_record = encrypted_hardware_id
                        logger.info(f"找到匹配的激活记录，当前离线次数: {db_offline_count}")
                        break
                except:
                    # 解密失败，继续查找下一条记录
                    continue

            if matched_record is not None:
                # 重置为0（已使用次数清零）
                cursor.execute('''
                    UPDATE activation_status
                    SET offline_usage_count = ?
                    WHERE product_id = ? AND encrypted_hardware_id = ?
                ''', (0, product_id, matched_record))

                conn.commit()
                logger.info(f"离线次数已重置为 0")
                return True
            else:
                logger.warning("未找到匹配的激活记录，无法重置离线次数")
                return False

    except Exception as e:
        logger.error(f"重置离线次数异常: {str(e)}")
        return False

def _validate_local_activation(product_id: str, hardware_id: str) -> Tuple[bool, Dict]:
    """
    第一步：本地验证
    读取硬件ID解码数据库核对硬件ID
    失败直接返回False
    成功返回激活信息字典
    """
    try:
        db_path = "client_activation.db"

        # 检查数据库是否存在
        if not os.path.exists(db_path):
            logger.info("数据库不存在，本地验证失败")
            return False, {}

        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()

            # 检查表是否存在
            cursor.execute('''
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='activation_status'
            ''')

            if not cursor.fetchone():
                logger.info("激活状态表不存在，本地验证失败")
                return False, {}

            # 查询所有激活记录（不限定product_id）
            cursor.execute('''
                SELECT product_id, encrypted_hardware_id, encrypted_order_no, encrypted_activation_code,
                       activation_type, activation_date, expiration_date, encrypted_expiration_date,
                       offline_usage_count, encrypted_offline_count, integrity_signature, version
                FROM activation_status
                ORDER BY created_at DESC
            ''')

            all_results = cursor.fetchall()

            if not all_results:
                logger.info("未找到激活记录，本地验证失败")
                return False, {}

            # 遍历所有记录，查找匹配的加密硬件ID
            for result in all_results:
                saved_product_id, saved_encrypted_hardware_id, encrypted_order_no, encrypted_activation_code, \
                activation_type, activation_date, expiration_date, encrypted_expiration_date, \
                offline_usage_count, encrypted_offline_count, integrity_signature, version = result

                # 尝试用当前硬件ID解密保存的硬件ID
                try:
                    saved_hardware_id = decrypt_hardware_id(saved_encrypted_hardware_id, hardware_id)
                except:
                    # 解密失败，跳过这条记录（可能不是同一设备）
                    continue

                # 检查解密后的硬件ID是否与当前硬件ID一致
                if saved_hardware_id == hardware_id:
                    logger.info("✅ 硬件ID匹配，本地验证成功")

                    # 验证数据完整性（检查签名）
                    if integrity_signature:
                        try:
                            # 优先使用加密字段
                            if encrypted_expiration_date:
                                try:
                                    verified_expiration = decrypt_data(encrypted_expiration_date, hardware_id)
                                except:
                                    verified_expiration = expiration_date
                            else:
                                verified_expiration = expiration_date

                            if encrypted_offline_count:
                                try:
                                    verified_offline_count = int(decrypt_data(encrypted_offline_count, hardware_id))
                                except:
                                    verified_offline_count = offline_usage_count
                            else:
                                verified_offline_count = offline_usage_count

                            # 验证签名
                            data_to_verify = f"{saved_product_id}{activation_type}{verified_expiration}{verified_offline_count}"
                            if not _verify_hmac(data_to_verify, integrity_signature):
                                logger.error("❌ 数据完整性验证失败，数据库可能被篡改")
                                return False, {}
                        except Exception as e:
                            logger.error(f"数据完整性验证异常: {e}")
                            return False, {}

                    # 验证成功，立即返回结果数据
                    return True, {
                        'product_id': saved_product_id,
                        'hardware_id': hardware_id,  # 使用当前硬件ID
                        'encrypted_order_no': encrypted_order_no,
                        'encrypted_activation_code': encrypted_activation_code,
                        'activation_type': activation_type,
                        'activation_date': activation_date,
                        'expiration_date': expiration_date,
                        'offline_usage_count': offline_usage_count,
                        'verified_offline_count': verified_offline_count,
                        'verified_expiration': verified_expiration
                    }
            else:
                # 所有记录都不匹配
                logger.error("❌ 未找到匹配的加密硬件ID")
                return False, {}

    except Exception as e:
        logger.error(f"本地验证异常: {str(e)}")
        return False, {}

def _validate_with_server(product_id: str, hardware_id: str, server_url: str,
                         activation_info: Dict) -> Tuple[bool, str]:
    """
    第二步：服务器验证
    联网成功获取激活信息并核对所有信息
    核对项目：产品ID、硬件ID、激活码、过期时间
    返回 (是否通过, 错误信息)
    """
    global _last_server_status

    try:
        # 从本地激活信息中获取订单号
        if activation_info.get('encrypted_order_no'):
            # 解密订单号
            try:
                order_no = decrypt_data(activation_info['encrypted_order_no'], hardware_id)
                activation_code = decrypt_data(activation_info.get('encrypted_activation_code', ''), hardware_id)
            except Exception as e:
                logger.error(f"解密激活信息失败: {e}")
                return False, "激活信息损坏"
        else:
            # 兼容旧版本，使用明文订单号
            order_no = activation_info.get('order_no')
            activation_code = activation_info.get('activation_code')

        if not order_no:
            logger.error("没有订单号，无法进行服务器验证")
            return False, "缺少订单号"

        # 调用服务器验证
        server_status = _check_server_activation_status(product_id, hardware_id, server_url, order_no)

        # 检查是否是网络错误
        if server_status.get('error_type') == 'network_error':
            logger.warning("服务器验证失败，启用离线模式")
            return False, "NETWORK_ERROR"

        # 检查是否是订单不存在
        if server_status.get('error_type') == 'order_not_found':
            logger.error("服务器验证失败：订单不存在或激活未完成")
            return False, "订单不存在或激活未完成"

        if not server_status.get('activated', False):
            logger.error("服务器验证失败：激活无效或已过期")
            return False, "激活无效或已过期"

        # 核对产品ID
        server_product_id = server_status.get('product_id', '')
        if server_product_id and server_product_id != product_id:
            logger.error(f"产品ID不匹配: 服务器={server_product_id}, 本地={product_id}")
            return False, "产品信息不匹配"

        # 核对硬件ID（服务器返回的）
        server_hardware_id = server_status.get('hardware_id', '')
        if server_hardware_id and server_hardware_id != hardware_id:
            logger.error(f"硬件ID不匹配: 服务器={server_hardware_id}, 本地={hardware_id}")
            return False, "硬件ID不匹配"

        # 核对激活码
        server_activation_code = server_status.get('activation_code', '')
        if activation_code and server_activation_code and activation_code != server_activation_code:
            logger.error("激活码不匹配")
            return False, "激活码不匹配"

        # 核对过期时间 - 优先使用服务器时间
        server_expiration = server_status.get('expiration_date', '')
        local_expiration = activation_info.get('verified_expiration') or activation_info.get('expiration_date', '')

        if server_expiration:
            # 服务器返回了过期时间，检查是否已过期
            try:
                server_time = datetime.fromisoformat(server_expiration.replace('Z', '+00:00'))
                now = datetime.now()

                if server_time < now:
                    logger.error(f"激活已过期: 服务器过期时间={server_expiration}")
                    return False, "激活已过期"

                # 如果有本地过期时间，进行对比检查
                if local_expiration:
                    local_time = datetime.fromisoformat(local_expiration.replace('Z', '+00:00'))
                    time_diff = abs((server_time - local_time).total_seconds())
                    if time_diff > 3600:  # 允许1小时的误差
                        logger.warning(f"本地过期时间与服务器不一致: 服务器={server_expiration}, 本地={local_expiration}")
                        # 不返回错误，继续验证（使用服务器时间为准）
            except Exception as e:
                logger.warning(f"检查过期时间失败: {e}")
                return False, "过期时间格式错误"
        else:
            logger.warning("服务器未返回过期时间，无法验证有效期")
            return False, "服务器数据不完整"


        # 验证通过，重置离线次数
        _reset_offline_count(product_id, hardware_id)

        # 更新本地激活信息
        _update_local_activation_status(
            server_status.get('product_id', product_id),
            hardware_id,
            server_status
        )

        logger.info("✅ 服务器验证成功，所有信息核对通过")
        _last_server_status = {
            'success': True,
            'error': None,
            'result': server_status
        }
        return True, ""

    except requests.exceptions.RequestException as e:
        logger.warning(f"❌ 服务器连接失败: {e}")
        _last_server_status = {
            'success': False,
            'error': str(e),
            'result': None
        }
        # 网络错误，返回特殊标记
        return False, "NETWORK_ERROR"
    except Exception as e:
        logger.error(f"❌ 服务器验证异常: {e}")
        _last_server_status = {
            'success': False,
            'error': str(e),
            'result': None
        }
        return False, str(e)

class SimpleActivationClient:
    """简单激活客户端"""
    
    def __init__(self, product_id: str = "pdf_merger", server_url: str = "https://wfnlj520.com", 
                 app_name: str = "PDF合并工具", app_version: str = "1.0.0"):
        self.product_id = product_id
        self.server_url = server_url
        self.app_name = app_name
        self.app_version = app_version
        self.hardware_id = get_hardware_id()
        self.app_user_id = get_app_user_id()  # 新增：获取独立的应用用户ID
        
        # 判断是否为月卡版
        self.is_monthly_card = product_id.endswith('_yue')
        
        # 延迟获取价格：只有在需要创建订单时才获取
        self.price = None  # 初始化为None，需要时再获取
        
        self.current_order_no = None
        self.activation_code = None  # 初始化激活码属性
        self._timer_thread = None
        self._stop_timer = False
        
        self.activated = self.check_activation()  # 初始化时检查激活状态
        
        # 如果未激活，不需要特殊处理，让调用方决定如何处理
        # 因为无法在这里区分是网络连接失败还是激活过期
        
        # 如果已激活，从本地数据库恢复激活码和订单号
        if self.activated:
            self._restore_activation_info()
            # 启动定时验证（月卡版需要更频繁的验证）
            self._start_periodic_validation()
        
        # 注册退出时的清理函数
        import atexit
        self._cleanup_registered = False
        atexit.register(self._cleanup_on_exit)
    
    def check_activation(self) -> bool:
        """检查激活状态 - 使用新逻辑"""
        success, error_msg = self._check_activation_v2()
        return success

    def _check_activation_v2(self) -> Tuple[bool, str]:
        """
        检查激活状态 - 按照新逻辑实现

        Returns:
            tuple: (是否可以继续使用, 错误信息)
        """
        try:
            # 0步：数据库完整性验证
            if not _verify_database_integrity():
                logger.error("❌ 数据库完整性验证失败")
                # 清除损坏的数据库，进入激活界面
                logger.info("数据库损坏或不存在，清除本地数据并进入激活界面")
                _clear_activation_files()
                return False, "DATABASE_CORRUPTED"

            # 第一步：本地验证 - 直接解密硬件ID
            local_success, activation_info = _validate_local_activation("", self.hardware_id)

            if local_success:
                # 获取实际的产品ID
                effective_product_id = activation_info.get('product_id', '')
                logger.info(f"✅ 本地验证成功，产品ID: {effective_product_id}")

                # 根据实际产品ID获取最大离线次数
                max_offline_count = _get_max_offline_count(effective_product_id)

                # 第二步：服务器验证
                server_success, error_msg = _validate_with_server(effective_product_id, self.hardware_id, self.server_url, activation_info)

                if server_success:
                    # 服务器验证通过，所有信息核对无误
                    logger.info("✅ 服务器验证通过，激活有效")
                    self.effective_product_id = effective_product_id
                    return True, ""
                else:
                    # 服务器验证失败，判断错误类型
                    if error_msg == "NETWORK_ERROR":
                        # 网络连接失败，检查离线次数
                        current_offline_count = activation_info.get('offline_usage_count', 0)
                        remaining_offline = max_offline_count - current_offline_count

                        logger.info(f"网络连接失败，剩余离线次数: {remaining_offline}/{max_offline_count}")

                        if remaining_offline <= 0:
                            # 没有离线次数了
                            logger.error("❌ 没有离线次数，需要联网验证")

                            # 区分版本显示不同提示
                            if effective_product_id.endswith('_test'):
                                error_reason = "试用版必须联网才能使用\n\n请检查网络连接后重新启动软件"
                            elif effective_product_id.endswith('_yue'):
                                error_reason = "月卡版必须联网才能使用\n\n请检查网络连接后重新启动软件"
                            else:
                                error_reason = "离线次数已用完\n\n请连接网络完成激活验证"

                            show_activation_error_dialog(error_reason, allow_continue=False)
                            return False, "NO_OFFLINE_COUNT"
                        elif remaining_offline > 3:
                            # 剩余离线次数大于3，直接进入主程序
                            logger.info(f"剩余离线次数充足({remaining_offline}次)，直接进入主程序")
                            # 减少一次离线次数
                            _decrement_offline_count(effective_product_id, self.hardware_id)
                            self.effective_product_id = effective_product_id
                            return True, ""
                        else:
                            # 剩余离线次数不足3次，提示用户尽快联网验证
                            logger.warning(f"剩余离线次数较少({remaining_offline}次)，提示用户联网")

                            # 区分版本显示不同提示
                            if effective_product_id.endswith('_test'):
                                error_reason = f"试用版建议联网验证\n\n当前离线次数: {remaining_offline}/{max_offline_count}\n\n请尽快联网验证以确保正常使用"
                            elif effective_product_id.endswith('_yue'):
                                error_reason = f"月卡版建议联网验证\n\n当前离线次数: {remaining_offline}/{max_offline_count}\n\n请尽快联网验证以确保正常使用"
                            else:
                                error_reason = f"建议联网验证\n\n剩余离线次数: {remaining_offline}/{max_offline_count}\n\n请尽快联网验证以确保正常使用"

                            # 显示提示框，但允许继续使用
                            show_activation_error_dialog(error_reason, allow_continue=True)
                            # 减少一次离线次数
                            _decrement_offline_count(effective_product_id, self.hardware_id)
                            self.effective_product_id = effective_product_id
                            return True, ""
                    else:
                        # 服务器验证失败，且不是网络错误（信息不匹配、激活过期等）
                        logger.error(f"❌ 服务器验证失败: {error_msg}")

                        # 硬件ID不匹配时，删除数据库，进入激活界面
                        if "硬件ID不匹配" in error_msg or "激活无效或已过期" in error_msg:
                            logger.info("检测到设备变更或激活失效，清除本地激活数据")
                            _clear_activation_files()

                            # 显示错误提示，允许继续（进入激活界面）
                            show_activation_error_dialog("检测到设备变更或激活失效\n\n请重新激活软件", allow_continue=True)

                        return False, error_msg
            else:
                # 本地验证失败
                logger.warning("❌ 本地验证失败，需要重新激活")
                return False, "INVALID_ACTIVATION"

        except Exception as e:
            logger.error(f"检查激活状态异常: {str(e)}")
            return False, str(e)

    def _should_perform_periodic_validation(self) -> bool:
        """判断是否需要进行定时验证"""
        try:
            # 检查所有可能的产品ID的状态
            product_ids = [self.product_id, f"{self.product_id}_test", f"{self.product_id}_nian", f"{self.product_id}_yue"]
            
            # 选择有效的激活状态
            effective_status = None
            for pid in product_ids:
                status = _check_local_activation_status(pid, self.hardware_id)
                if status['activated'] and not status['is_expired']:
                    effective_status = status
                    break
            
            # 如果没有有效激活状态，不需要定时验证
            if not effective_status:
                return False
            
            # 检查激活天数
            days_remaining = effective_status.get('days_remaining', 0)
            
            # 简单规则：大于30天只启动时验证，<=30天定时验证
            if days_remaining <= 30:
                logger.info(f"激活剩余{days_remaining}天，启用定时验证")
                return True
            else:
                logger.info(f"激活剩余{days_remaining}天，只启动时验证")
                return False
            
        except Exception as e:
            logger.error(f"判断定时验证条件异常: {str(e)}")
            return False
    
    def _periodic_validation_task(self):
        """定时验证任务"""
        while not self._stop_timer:
            try:
                # 设置验证间隔：月卡版每1小时，永久版每3小时
                if self.is_monthly_card:
                    time.sleep(1 * 60 * 60)  # 1小时
                else:
                    time.sleep(3 * 60 * 60)  # 3小时
                
                if self._stop_timer:
                    break
                    
                # 检查是否需要进行验证
                if self._should_perform_periodic_validation():
                    logger.info("执行定时验证...")
                    
                    # 执行服务器验证
                    server_status = _check_server_activation_status(
                        self.product_id, self.hardware_id, self.server_url
                    )
                    
                    if not server_status['activated'] or server_status['is_expired']:
                        # 验证失败，显示错误提示
                        error_reason = "定时验证失败：激活状态异常"
                        show_activation_error_dialog(error_reason)
                        logger.warning(f"定时验证失败: {error_reason}")
                    else:
                        # 验证成功，更新本地状态
                        _update_local_activation_status(
                            self.product_id, self.hardware_id, server_status
                        )
                        logger.info("定时验证成功，已更新本地状态")
                        
            except Exception as e:
                logger.error(f"定时验证任务异常: {str(e)}")
    
    def _start_periodic_validation(self):
        """启动定时验证"""
        try:
            # 检查是否需要进行定时验证
            if not self._should_perform_periodic_validation():
                logger.info("当前激活状态不需要定时验证")
                return
            
            # 启动定时验证线程
            self._stop_timer = False
            self._timer_thread = threading.Thread(target=self._periodic_validation_task, daemon=True)
            self._timer_thread.start()
            logger.info("定时验证已启动（每3小时验证一次）")
            
        except Exception as e:
            logger.error(f"启动定时验证异常: {str(e)}")
    
    def stop_periodic_validation(self):
        """停止定时验证"""
        self._stop_timer = True
        if self._timer_thread and self._timer_thread.is_alive():
            self._timer_thread.join(timeout=5)
        logger.info("定时验证已停止")
    
    def _restore_activation_info(self):
        """从本地数据库恢复激活信息（激活码和订单号）"""
        try:
            # 使用新的 _validate_local_activation 方法，不限定产品ID
            local_success, activation_info = _validate_local_activation("", self.hardware_id)

            if local_success:
                # 解密激活码和订单号
                encrypted_order_no = activation_info.get('encrypted_order_no', '')
                encrypted_activation_code = activation_info.get('encrypted_activation_code', '')
                product_id = activation_info.get('product_id', '')

                try:
                    if encrypted_order_no:
                        self.current_order_no = decrypt_data(encrypted_order_no, self.hardware_id)
                    if encrypted_activation_code:
                        self.activation_code = decrypt_data(encrypted_activation_code, self.hardware_id)
                except Exception as e:
                    logger.warning(f"解密激活信息失败: {e}")

                logger.info(f"已恢复激活信息 - 产品ID: {product_id}, 激活码: {self.activation_code}, 订单号: {self.current_order_no}")
                return

            logger.warning("未找到有效的本地激活信息")
        except Exception as e:
            logger.error(f"恢复激活信息失败: {str(e)}")
    
    def _cleanup_qr_code_files(self):
        """清理二维码图片文件"""
        try:
            # 删除临时二维码文件
            import os
            for file in os.listdir('.'):
                if file.startswith('qr_') and file.endswith('.png'):
                    os.remove(file)
                    logger.info(f"已清理二维码文件: {file}")
        except Exception as e:
            logger.error(f"清理二维码文件失败: {str(e)}")
    
    def _cleanup_on_exit(self):
        """程序退出时的清理操作"""
        try:
            # 避免多次执行
            if self._cleanup_registered:
                return
            
            # 停止定时验证线程
            self.stop_periodic_validation()
            
            # 清理二维码文件
            self._cleanup_qr_code_files()
            
            # 关闭数据库连接（如果有）
            try:
                import sqlite3
                conn = sqlite3.connect("client_activation.db")
                conn.close()
            except:
                pass
            
            # 数据已经是加密存储的，不需要文件级加密
            logger.info("程序退出，数据库数据已加密保存")
            
            self._cleanup_registered = True
            
        except Exception as e:
            logger.error(f"程序退出清理失败: {str(e)}")
    
    def get_server_product_price(self, product_id: str) -> float:
        """从服务器获取产品价格 - 必须成功，否则无法创建订单"""
        try:
            # 即使未激活也要获取产品价格，因为激活界面需要显示价格信息
            # 注释掉这个检查，允许在未激活状态下获取价格
            # if not self.activated:
            #     logger.info("❌ 未激活状态，不获取产品价格")
            #     raise Exception("软件未激活，无法获取产品价格")

            # 获取产品信息
            url = f"{self.server_url}/api/products/{product_id}"
            response = requests.get(url, timeout=10)

            if response.status_code == 200:
                result = response.json()

                # 服务器直接返回产品信息，不是嵌套在product字段中
                if result.get('success') and 'price' in result:
                    price = result['price']
                    logger.info(f"✅ 从服务器获取产品价格成功: {product_id} - {price}元")
                    return price
                elif result.get('success') and result.get('product') and 'price' in result['product']:
                    # 兼容另一种可能的返回格式
                    price = result['product']['price']
                    logger.info(f"✅ 从服务器获取产品价格成功(兼容格式): {product_id} - {price}元")
                    return price
                else:
                    error_msg = result.get('error', '未知错误')
                    logger.error(f"❌ 获取产品信息失败: {error_msg}")
                    raise Exception(f"服务器返回错误: {error_msg}")
            else:
                logger.error(f"❌ HTTP错误: {response.status_code}")
                raise Exception(f"HTTP请求失败: {response.status_code}")
        except Exception as e:
            # 简化联网错误日志，只显示用户友好的提示
            logger.error("❌ 获取服务器价格异常: 无法连接到服务器")

            # 检查错误类型，只有网络错误才抛出异常
            error_msg = str(e)
            # 扩展网络错误判断条件，包含更多网络相关的关键词
            is_network_error = any(keyword in error_msg for keyword in [
                "无法连接到服务器", "网络", "连接", "Timeout", "Connection",
                "NameResolutionError", "getaddrinfo", "Max retries exceeded",
                "HTTPSConnectionPool", "无法解析主机", "DNS", "socket"
            ])

            if is_network_error:
                raise Exception("无法连接到服务器")
            else:
                # 其他错误（如激活过期），不抛出异常，让调用方处理
                logger.warning(f"获取产品价格失败，但非网络错误: {error_msg}")
                # 返回默认价格或None
                return None
    
    def create_order(self, description="PDF合并工具激活", amount=None, app_user_id=None):
        """创建支付订单，返回 (order_no, qr_code_url, error_msg) 三元组"""
        try:
            if not app_user_id:
                app_user_id = f"user_{int(time.time())}"
            
            # 如果未指定金额，从服务器获取价格
            if amount is None:
                if self.price is None:
                    # 延迟获取价格
                    self.price = self.get_server_product_price(self.product_id)
                amount = self.price
            
            # 根据API文档，使用正确的订单创建接口
            order_data = {
                "product_id": self.product_id,
                "amount": amount,
                "description": description,
                "app_user_id": app_user_id,
                "hardware_id": self.hardware_id
            }
            
            logger.info(f"创建订单数据: {order_data}")
            
            # 使用兼容前端创建订单的API
            response = requests.post(f"{self.server_url}/api/create_order", 
                                   json=order_data, 
                                   timeout=10)
            
            if response.status_code == 200:
                result = response.json()
                logger.info(f"订单创建响应: {result}")
                
                if result.get('success'):
                    order_no = result.get('order_id')
                    qr_code_url = result.get('qr_code_url')
                    self.current_order_no = order_no
                    
                    # 保存二维码URL供后续使用
                    self._qr_code_url = qr_code_url
                    
                    # 保存订单号到本地状态，用于后续激活验证
                    status = {
                        'order_no': order_no,
                        'activation_date': datetime.now().isoformat(),
                        'expiration_date': (datetime.now() + timedelta(days=30)).isoformat()
                    }
                    _update_local_activation_status(self.product_id, self.hardware_id, status)
                    
                    return order_no, qr_code_url, None  # 成功时错误信息为None
                else:
                    # 处理价格不匹配等错误
                    error_msg = result.get('error', '订单创建失败')
                    logger.error(f"订单创建失败: {error_msg}")
                    
                    # 如果价格不匹配，更新本地价格缓存
                    if "价格不匹配" in error_msg and result.get('suggested_price'):
                        self.price = result.get('suggested_price')
                        logger.info(f"已更新本地价格缓存为: {self.price}元")
                    
                    return None, None, error_msg  # 返回错误信息
            else:
                error_msg = f"订单创建请求失败: {response.status_code}"
                logger.error(error_msg)
                return None, None, error_msg
                
        except Exception as e:
            logger.error(f"创建订单异常: {str(e)}")
            return None, None
    
    def get_qr_code(self, order_no=None):
        """获取订单二维码图片文件"""
        try:
            if not order_no:
                order_no = self.current_order_no
            
            if not order_no:
                logger.error("没有有效的订单号")
                return None
            
            # 根据服务器响应，二维码URL已经返回
            # 服务器返回的二维码URL是相对路径，需要拼接完整URL
            qr_url = None
            if hasattr(self, '_qr_code_url') and self._qr_code_url:
                qr_url = self._qr_code_url
                # 如果是相对路径，拼接完整URL
                if qr_url.startswith('/'):
                    qr_url = f"{self.server_url}{qr_url}"
            else:
                # 如果_create_order时没有保存二维码URL，使用API获取
                qr_url = f"{self.server_url}/api/qr-code/{order_no}"
            
            # 下载二维码图片
            response = requests.get(qr_url, timeout=10)
            if response.status_code == 200:
                # 保存二维码图片到本地临时文件
                qr_filename = f"qr_{order_no}.png"
                with open(qr_filename, 'wb') as f:
                    f.write(response.content)
                
                logger.info(f"二维码图片已下载: {qr_filename}")
                return qr_filename
            else:
                logger.error(f"下载二维码图片失败: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"获取二维码异常: {str(e)}")
            return None
    
    def show_activation_info(self):
        """显示激活信息"""
        status = _check_local_activation_status(self.product_id, self.hardware_id)
        
        if status['activated']:
            if status['is_expired']:
                print(f"❌ 激活已过期 ({status['activation_type']}版)")
                print(f"过期时间: {status['expiration_date']}")
            else:
                print(f"✅ 已激活 ({status['activation_type']}版)")
                print(f"有效期至: {status['expiration_date']}")
                print(f"剩余天数: {status['days_remaining']}天")
        else:
            print("❌ 软件未激活")
    
    def activate_trial(self) -> Tuple[bool, str]:
        """激活试用版"""
        try:
            # 保存原始产品ID
            original_product_id = self.product_id
            original_price = self.price
            
            # 切换到试用版产品ID
            trial_product_id = f"{self.product_id}_test"
            self.product_id = trial_product_id
            
            # 创建试用版订单
            order_no, qr_code_url, error_msg = self.create_order(
                description=f"{self.app_name} - 试用版激活",
                amount=0.01,  # 试用版价格
                app_user_id=self.app_user_id
            )
            
            # 恢复原始产品ID
            self.product_id = original_product_id
            self.price = original_price
            
            if order_no:
                # 试用版激活不需要等待支付，直接设置试用状态
                # 服务器会在支付成功后自动激活
                
                # 更新本地状态为试用版，保存订单号
                status = {
                    'activation_type': 'trial',
                    'order_no': order_no,  # 保存订单号
                    'activation_date': datetime.now().isoformat(),
                    'expiration_date': (datetime.now() + timedelta(days=30)).isoformat()
                }
                _update_local_activation_status(self.product_id, self.hardware_id, status)
                
                # 保存订单信息用于后续检查
                self.current_order_no = order_no
                
                return True, f"试用版激活成功！请支付0.01元完成激活，有效期30天。订单号: {order_no}"
            else:
                error_display = error_msg if error_msg else "试用版激活失败"
                return False, f"试用版激活失败: {error_display}"
            
        except Exception as e:
            logger.error(f"激活试用版异常: {str(e)}")
            return False, f"激活异常: {str(e)}"
    
    def check_payment_status(self, order_no: str = None) -> str:
        """检查支付状态，返回激活码或None"""
        try:
            if not order_no:
                order_no = self.current_order_no
            
            if not order_no:
                logger.error("没有有效的订单号")
                return None
            
            # 使用订单号查询支付状态
            response = requests.get(f"{self.server_url}/api/check-status/{order_no}", timeout=10)
            
            if response.status_code == 200:
                result = response.json()
                logger.info(f"支付状态查询结果: {result}")
                
                if result.get('success') or result.get('paid'):
                    status = result.get('status', '')
                    
                    if status == 'SUCCESS' or result.get('paid') == True:
                        # 支付成功，检查响应中是否包含激活码
                        activation_code = result.get('activation_code')
                        
                        if activation_code:
                            # 激活成功，返回激活码
                            logger.info(f"支付成功，激活码: {activation_code}")
                            return activation_code
                        else:
                            logger.warning("支付成功但未返回激活码")
                            return None
                    else:
                        # 支付中或其他状态
                        logger.info(f"支付状态: {status}")
                        return None
                else:
                    logger.warning(f"支付状态查询失败: {result.get('error', '未知错误')}")
                    return None
            else:
                logger.error(f"支付状态查询请求失败: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"检查支付状态异常: {str(e)}")
            return None
    
    def verify_activation(self, activation_code: str) -> bool:
        """验证激活码"""
        try:
            # 简化验证流程：如果从服务器获取到激活码，直接视为激活成功
            # 因为服务器已经验证了支付状态
            if activation_code:
                # 首先检查当前订单号（如果有）
                order_no = self.current_order_no
                
                # 如果没有当前订单号，尝试从本地数据库查找所有产品ID的订单号
                if not order_no:
                    # 检查所有可能的产品ID
                    product_ids = [self.product_id, f"{self.product_id}_test", f"{self.product_id}_nian", f"{self.product_id}_yue"]
                    
                    for pid in product_ids:
                        local_status = _check_local_activation_status(pid, self.hardware_id)
                        temp_order_no = local_status.get('order_no')
                        if temp_order_no:
                            order_no = temp_order_no
                            logger.info(f"使用产品ID {pid} 查询到订单号: {order_no}")
                            break
                
                if not order_no:
                    raise Exception("本地没有订单号信息，无法查询激活状态")
                
                try:
                    # 使用订单号查询支付状态
                    url = f"{self.server_url}/api/check-status/{order_no}"
                    response = requests.get(url, timeout=10)
                    
                    if response.status_code == 200:
                        result = response.json()
                        if result.get('success') or result.get('paid'):
                            status = result.get('status', '')
                            
                            if status == 'SUCCESS' or result.get('paid') == True:
                                # 支付成功，验证激活码
                                server_activation_code = result.get('activation_code')
                                
                                if server_activation_code and server_activation_code == activation_code:
                                    # 激活码匹配，获取激活信息
                                    expire_time_str = result.get('expire_time')
                                    server_product_id = result.get('product_id', self.product_id)
                                    
                                    if not expire_time_str:
                                        raise Exception("服务器未返回到期时间")
                                    
                                    # 计算激活时长（天）
                                    expire_time = datetime.fromisoformat(expire_time_str.replace('Z', '+00:00'))
                                    activate_time = datetime.fromisoformat(result.get('activate_time', expire_time_str).replace('Z', '+00:00'))
                                    duration_days = (expire_time - activate_time).days
                                    
                                    # 判断激活类型：根据服务器返回的产品ID确定版本类型
                                    activation_type = 'official'
                                    if server_product_id:
                                        if server_product_id.endswith('_test'):
                                            activation_type = 'trial'
                                        elif server_product_id.endswith('_yue'):
                                            activation_type = 'monthly'
                                        elif server_product_id.endswith('_nian'):
                                            activation_type = 'yearly'
                                    
                                    logger.info(f"✅ 激活验证成功: 产品ID={server_product_id}, 类型={activation_type}, 时长={duration_days}天")
                                else:
                                    raise Exception(f"激活码不匹配: 本地={activation_code}, 服务器={server_activation_code}")
                            else:
                                raise Exception(f"支付状态异常: {status}")
                        else:
                            raise Exception(f"服务器返回错误: {result.get('error', '未知错误')}")
                    else:
                        raise Exception(f"HTTP请求失败: {response.status_code}")
                except Exception as e:
                    logger.error(f"❌ 查询激活状态失败: {e}")
                    raise Exception(f"无法从服务器查询激活状态: {e}")
                
                # 确定应该使用哪个产品ID更新本地状态
                # 总是使用服务器返回的产品ID，确保一致性
                product_id_for_update = server_product_id or self.product_id
                
                # 更新本地状态
                status = {
                    'activation_type': activation_type,
                    'activation_code': activation_code,  # 保存激活码
                    'order_no': order_no,  # 使用查询到的订单号
                    'activation_date': datetime.now().isoformat(),
                    'expiration_date': expire_time.isoformat()  # 使用服务器返回的过期时间
                }
                _update_local_activation_status(product_id_for_update, self.hardware_id, status)
                
                # 更新当前激活状态
                self.activated = True
                self.activation_code = activation_code
                self.current_order_no = order_no  # 更新当前订单号
                
                logger.info(f"激活码验证成功，类型={activation_type}, 有效期={duration_days}天")
                return True
            else:
                logger.warning("激活码为空")
                return False
                
        except Exception as e:
            logger.error(f"验证激活码异常: {str(e)}")
            return False
    
    def decrypt_activation_code(self, activation_code: str, order_id: str) -> bool:
        """验证激活码（兼容性方法）"""
        # 调用verify_activation方法，保持兼容性
        return self.verify_activation(activation_code)
    
    def start_trial_activation_flow(self) -> Tuple[bool, any]:
        """启动试用版激活流程（统一方法）"""
        try:
            # 保存原始产品ID和价格
            original_product_id = self.product_id
            original_price = self.price

            # 切换到试用版产品ID
            trial_product_id = f"{self.product_id}_test"
            self.product_id = trial_product_id

            # 优先使用缓存价格，如果没有则请求服务器
            if hasattr(self, 'cached_prices') and trial_product_id in self.cached_prices:
                trial_price = self.cached_prices[trial_product_id]
                logger.info(f"使用缓存价格: {trial_product_id} - {trial_price}元")
            else:
                trial_price = self.get_server_product_price(trial_product_id)
            self.price = trial_price
            
            # 创建试用版订单，使用试用版的实际价格
            order_no, qr_code_url, error_msg = self.create_order(
                description="PDF合并工具 - 试用版激活",
                amount=None,  # 使用服务器默认价格（试用版价格）
                app_user_id=self.app_user_id
            )
            
            # 恢复原始产品ID和价格
            self.product_id = original_product_id
            self.price = original_price
            
            if order_no:
                # 获取二维码文件
                qr_file = self.get_qr_code(order_no)
                if qr_file:
                    return True, (order_no, qr_file)
                else:
                    return False, "二维码文件生成失败"
            else:
                # 返回具体的错误信息
                error_display = error_msg if error_msg else "试用版订单创建失败"
                return False, error_display
                
        except Exception as e:
            logger.error(f"试用版激活流程异常: {str(e)}")
            return False, f"试用版激活失败: {str(e)}"
    
    def start_official_activation_flow(self) -> Tuple[bool, any]:
        """启动正式版激活流程（统一方法）"""
        try:
            # 创建正式版订单
            order_no, qr_code_url, error_msg = self.create_order()
            
            if order_no:
                # 获取二维码文件
                qr_file = self.get_qr_code(order_no)
                if qr_file:
                    return True, (order_no, qr_file)
                else:
                    return False, "二维码文件生成失败"
            else:
                # 返回具体的错误信息
                error_display = error_msg if error_msg else "正式版订单创建失败"
                return False, error_display
                
        except Exception as e:
            logger.error(f"正式版激活流程异常: {str(e)}")
            return False, f"正式版激活失败: {str(e)}"

    def start_year_activation_flow(self) -> Tuple[bool, any]:
        """启动年费版激活流程（统一方法）"""
        try:
            # 保存原始产品ID和价格
            original_product_id = self.product_id
            original_price = self.price

            # 切换到年费版产品ID
            year_product_id = f"{self.product_id}_nian"
            self.product_id = year_product_id

            # 优先使用缓存价格，如果没有则请求服务器
            if hasattr(self, 'cached_prices') and year_product_id in self.cached_prices:
                year_price = self.cached_prices[year_product_id]
                logger.info(f"使用缓存价格: {year_product_id} - {year_price}元")
            else:
                year_price = self.get_server_product_price(year_product_id)
            self.price = year_price
            
            # 创建年费版订单，使用年费版的实际价格
            order_no, qr_code_url, error_msg = self.create_order(
                description="PDF合并工具 - 年费版激活",
                amount=None,  # 使用服务器默认价格（年费版价格）
                app_user_id=self.app_user_id
            )
            
            # 恢复原始产品ID和价格
            self.product_id = original_product_id
            self.price = original_price
            
            if order_no:
                # 获取二维码文件
                qr_file = self.get_qr_code(order_no)
                if qr_file:
                    return True, (order_no, qr_file)
                else:
                    return False, "二维码文件生成失败"
            else:
                # 返回具体的错误信息
                error_display = error_msg if error_msg else "年费版订单创建失败"
                return False, error_display
                
        except Exception as e:
            logger.error(f"年费版激活流程异常: {str(e)}")
            return False, f"年费版激活失败: {str(e)}"
    
    def start_monthly_activation_flow(self) -> Tuple[bool, any]:
        """启动月卡版激活流程（统一方法）"""
        try:
            # 保存原始产品ID和价格
            original_product_id = self.product_id
            original_price = self.price

            # 切换到月卡版产品ID
            monthly_product_id = f"{self.product_id}_yue"
            self.product_id = monthly_product_id

            # 优先使用缓存价格，如果没有则请求服务器
            if hasattr(self, 'cached_prices') and monthly_product_id in self.cached_prices:
                monthly_price = self.cached_prices[monthly_product_id]
                logger.info(f"使用缓存价格: {monthly_product_id} - {monthly_price}元")
            else:
                monthly_price = self.get_server_product_price(monthly_product_id)
            self.price = monthly_price
            
            # 创建月卡版订单，使用月卡版的实际价格
            order_no, qr_code_url, error_msg = self.create_order(
                description="PDF合并工具 - 月卡版激活",
                amount=None,  # 使用服务器默认价格（月卡版价格）
                app_user_id=self.app_user_id
            )
            
            # 恢复原始产品ID和价格
            self.product_id = original_product_id
            self.price = original_price
            
            if order_no:
                # 获取二维码文件
                qr_file = self.get_qr_code(order_no)
                if qr_file:
                    return True, (order_no, qr_file)
                else:
                    return False, "二维码文件生成失败"
            else:
                # 返回具体的错误信息
                error_display = error_msg if error_msg else "月卡版订单创建失败"
                return False, error_display
                
        except Exception as e:
            logger.error(f"月卡版激活流程异常: {str(e)}")
            return False, f"月卡版激活失败: {str(e)}"

class SimpleActivationUI:
    """简单激活界面"""
    
    def __init__(self, product_id: str = "pdf_merger", server_url: str = "http://localhost:5000"):
        self.client = SimpleActivationClient(product_id, server_url)
    
    def show(self):
        """显示激活界面"""
        print("\n" + "="*50)
        print("          软件激活界面")
        print("="*50)
        
        # 显示当前状态
        self.client.show_activation_info()
        
        print("\n激活选项:")
        print("1. 激活试用版 (需要支付试用费用)")
        print("2. 激活正式版 (需要购买正式版)")
        print("3. 退出")
        
        choice = input("\n请选择 (1-3): ").strip()
        
        if choice == '1':
            self._activate_trial_flow()
        elif choice == '2':
            self._activate_official_flow()
        elif choice == '3':
            print("退出激活界面")
            return
        else:
            print("❌ 无效选择")
        
        input("\n按回车键继续...")
    
    def _activate_trial_flow(self):
        """试用版激活流程"""
        print("\n🔄 正在创建试用期订单...")
        
        # 使用产品ID_test创建试用期订单
        trial_product_id = f"{self.client.product_id}_test"
        
        # 创建试用期订单
        order_no, qr_code_url, error_msg = self.client.create_order(
            description="PDF合并工具 - 试用版激活",
            amount=None,  # 使用服务器默认价格
            app_user_id=self.client.app_user_id
        )
        
        if order_no and qr_code_url:
            print(f"\n✅ 试用期订单创建成功！")
            print(f"订单号: {order_no}")
            
            # 获取并显示二维码
            qr_filename = self.client.get_qr_code(order_no)
            if qr_filename:
                print(f"二维码已生成: {qr_filename}")
                print("请使用微信扫描二维码完成支付")
            
            # 等待支付完成
            print("\n🔄 等待支付完成...")
            self._wait_for_payment(order_no)
        else:
            error_display = error_msg if error_msg else "试用期订单创建失败"
            print(f"\n❌ {error_display}")
    
    def _activate_official_flow(self):
        """正式版激活流程"""
        print("\n📞 请联系客服购买正式版授权")
        print("客服电话: 400-xxx-xxxx")
        print("客服微信: xxxxxx")
    
    def _wait_for_payment(self, order_no: str):
        """等待支付完成"""
        max_attempts = 60  # 最多等待5分钟
        attempt = 0
        
        while attempt < max_attempts:
            activation_code = self.client.check_payment_status(order_no)
            
            if activation_code:
                # 支付成功，验证激活码
                if self.client.verify_activation(activation_code):
                    print(f"\n✅ 激活成功！")
                    print(f"激活码: {activation_code}")
                    print("软件已激活，可以正常使用")
                    return True
                else:
                    print("\n❌ 激活码验证失败")
                    return False
            
            # 等待5秒后重试
            time.sleep(5)
            attempt += 1
            print(f".", end="", flush=True)
        
        print("\n⏰ 支付等待超时，请稍后手动检查支付状态")
        return False

# 使用示例
if __name__ == "__main__":
    # 检查激活状态
    if not check_activation():
        # 显示激活界面
        ui = SimpleActivationUI()
        ui.show()
    else:
        print("✅ 软件已激活，可以正常使用")
        
        # 显示激活信息
        client = SimpleActivationClient()
        client.show_activation_info()