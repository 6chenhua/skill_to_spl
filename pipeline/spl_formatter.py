"""
spl_formatter.py
────────────────
SPL缩进格式化器 - 层级缩进版本

缩进规则（层级结构）：
层级0 (0空格): DEFINE_AGENT, END_AGENT
层级1 (4空格): DEFINE_PERSONA, DEFINE_CONSTRAINTS, DEFINE_FILES, DEFINE_APIS, DEFINE_WORKER等
层级2 (8空格): PERSONA内容, CONSTRAINTS内容, FILES内容, WORKER内容, INPUTS, OUTPUTS等
层级3 (12空格): INPUTS/OUTPUTS内容, MAIN_FLOW内容, SEQUENTIAL_BLOCK, IF, WHILE等
层级4 (16空格): 命令内容, SEQUENTIAL_BLOCK内容
层级5 (20空格): 嵌套命令内容

规则：
1. Block标记本身缩进到其父级层级
2. Block内部内容比标记多一级缩进
3. 在APIS block内：每个API作为整体单元处理
"""

import re
from typing import List, Tuple

# Block定义：(开始模式, 结束模式, 层级)
# 层级表示该block标记本身的缩进层级
BLOCK_PATTERNS = [
    # Level 0: 最外层
    (r'^\[DEFINE_AGENT:', r'^\[END_AGENT\]', 0),
    
    # Level 1: AGENT内部的直接子blocks
    (r'^\[DEFINE_PERSONA:\]', r'^\[END_PERSONA\]', 1),
    (r'^\[DEFINE_AUDIENCE:\]', r'^\[END_AUDIENCE\]', 1),
    (r'^\[DEFINE_CONCEPTS:\]', r'^\[END_CONCEPTS\]', 1),
    (r'^\[DEFINE_CONSTRAINTS:\]', r'^\[END_CONSTRAINTS\]', 1),
    (r'^\[DEFINE_VARIABLES:\]', r'^\[END_VARIABLES\]', 1),
    (r'^\[DEFINE_FILES:\]', r'^\[END_FILES\]', 1),
    (r'^\[DEFINE_APIS:\]', r'^\[END_APIS\]', 1),
    (r'^\[DEFINE_WORKER:', r'^\[END_WORKER\]', 1),  # DEFINE_WORKER:可能有描述
    
    # Level 2: WORKER内部的blocks
    (r'^\[INPUTS\]', r'^\[END_INPUTS\]', 2),
    (r'^\[OUTPUTS\]', r'^\[END_OUTPUTS\]', 2),
    (r'^\[MAIN_FLOW\]', r'^\[END_MAIN_FLOW\]', 2),
    (r'^\[ALTERNATIVE_FLOW:', r'^\[END_ALTERNATIVE_FLOW\]', 2),
    (r'^\[EXCEPTION_FLOW:', r'^\[END_EXCEPTION_FLOW\]', 2),
    (r'^\[EXAMPLES\]', r'^\[END_EXAMPLES\]', 2),
    
    # Level 3: FLOW内部的控制结构
    (r'^\[SEQUENTIAL_BLOCK\]', r'^\[END_SEQUENTIAL_BLOCK\]', 3),
    (r'^\[IF\s+', r'^\[END_IF\]', 3),
    (r'^\[WHILE\s+', r'^\[END_WHILE\]', 3),
    (r'^\[FOR\s+', r'^\[END_FOR\]', 3),
]

# 控制流标记（与IF同级）
CONTROL_FLOW_PATTERNS = [
    (r'^\[ELSEIF\s+', 3),
    (r'^\[ELSE\]', 3),
]

# API名称模式
API_NAME_PATTERN = re.compile(r'^[A-Z][a-zA-Z0-9_]*<[^>]+>')


def _classify_line(line: str) -> Tuple[str, int]:
    """
    分类一行文本。
    
    Returns:
        (类型, 层级)
        类型: 'start', 'end', 'control', 'content'
    """
    stripped = line.strip()
    
    # 检查是否是block结束标记（先检查结束，防止[END_IF]被误认为IF开始）
    for start_pat, end_pat, level in BLOCK_PATTERNS:
        if re.match(end_pat, stripped):
            return ('end', level)
    
    # 检查是否是block开始标记
    for start_pat, end_pat, level in BLOCK_PATTERNS:
        if re.match(start_pat, stripped):
            return ('start', level)
    
    # 检查是否是控制流标记
    for pattern, level in CONTROL_FLOW_PATTERNS:
        if re.match(pattern, stripped):
            return ('control', level)
    
    # 普通内容
    return ('content', -1)


def _is_api_declaration(line: str) -> bool:
    """检查是否是API声明的开始"""
    return bool(API_NAME_PATTERN.match(line.strip()))


def _collect_api_block(lines: List[str], start_idx: int) -> Tuple[List[str], int]:
    """
    收集完整的API声明块。
    
    从API名称行开始，收集到下一个API声明或[END_APIS]或文件结束。
    
    Returns:
        (api_lines, next_idx)
    """
    api_lines = [lines[start_idx]]
    i = start_idx + 1
    
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        
        # 空行属于API块的一部分
        if not stripped:
            api_lines.append(line)
            i += 1
            continue
        
        # 如果遇到下一个API声明或结束标记，停止收集
        if _is_api_declaration(stripped):
            break
        
        line_type, _ = _classify_line(stripped)
        if line_type == 'end' and '[END_APIS]' in stripped:
            break
        
        api_lines.append(line)
        i += 1
    
    return api_lines, i


def _indent_api_block(api_lines: List[str], base_indent: int, indent_size: int) -> List[str]:
    """
    给API块添加基础缩进。
    
    保持API内部结构不变，只添加基础偏移。
    """
    if not api_lines:
        return api_lines
    
    result = []
    for line in api_lines:
        if line.strip():
            # 非空行：添加基础偏移
            line_existing = len(line) - len(line.lstrip())
            new_indent = base_indent + line_existing
            result.append(' ' * new_indent + line.lstrip())
        else:
            # 空行保持原样
            result.append(line)
    
    return result


def format_spl_indentation(spl_text: str, indent_size: int = 4) -> str:
    """
    格式化SPL文本，强制应用层级缩进。
    
    Args:
        spl_text: 原始SPL文本
        indent_size: 每个层级的缩进空格数（默认4）
    
    Returns:
        格式化后的SPL文本
    """
    if not spl_text or not spl_text.strip():
        return spl_text
    
    lines = spl_text.split('\n')
    result = []
    stack = []  # 跟踪block层级栈
    i = 0
    
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        
        # 空行处理
        if not stripped:
            result.append(line)
            i += 1
            continue
        
        # 注释行处理
        if stripped.startswith('#'):
            # 注释缩进到当前层级
            current_level = len(stack)
            result.append(' ' * (current_level * indent_size) + stripped)
            i += 1
            continue
        
        # 分类这一行
        line_type, level = _classify_line(stripped)
        
        if line_type == 'start':
            # Block开始标记
            # 缩进到其定义的层级
            result.append(' ' * (level * indent_size) + stripped)
            # 内容层级 = 标记层级 + 1
            stack.append(level + 1)
            i += 1
            
            # 特殊处理：如果是[DEFINE_APIS:]，按API单元处理
            if '[DEFINE_APIS:]' in stripped:
                i += 1
                while i < len(lines):
                    line = lines[i]
                    stripped_inner = line.strip()
                    
                    if not stripped_inner:
                        result.append(line)
                        i += 1
                        continue
                    
                    if '[END_APIS]' in stripped_inner:
                        break
                    
                    if _is_api_declaration(stripped_inner):
                        # 收集完整API块
                        api_lines, next_idx = _collect_api_block(lines, i)
                        # API块缩进到层级2（在APIS内部）
                        indented_api = _indent_api_block(api_lines, 2 * indent_size, indent_size)
                        result.extend(indented_api)
                        i = next_idx
                    else:
                        # 其他内容（不应该在APIS内部出现）
                        result.append(' ' * (2 * indent_size) + stripped_inner)
                        i += 1
                continue
            
        elif line_type == 'end':
            # Block结束标记
            # 缩进到对应的开始标记同级
            if stack:
                content_level = stack.pop()
                marker_level = content_level - 1
                result.append(' ' * (marker_level * indent_size) + stripped)
            else:
                result.append(stripped)
            i += 1
            
        elif line_type == 'control':
            # 控制流标记（ELSEIF/ELSE）
            # 缩进到对应的IF同级（层级3）
            result.append(' ' * (level * indent_size) + stripped)
            i += 1
            
        else:
            # 普通内容行
            # 缩进到当前栈深度
            current_level = len(stack)
            result.append(' ' * (current_level * indent_size) + stripped)
            i += 1
    
    return '\n'.join(result)


def validate_spl_indentation(spl_text: str, indent_size: int = 4) -> List[dict]:
    """
    验证SPL缩进是否正确。
    
    Args:
        spl_text: 要验证的SPL文本
        indent_size: 期望的缩进大小
    
    Returns:
        错误列表
    """
    if not spl_text or not spl_text.strip():
        return []
    
    lines = spl_text.split('\n')
    errors = []
    stack = []
    i = 0
    
    while i < len(lines):
        line_num = i + 1
        line = lines[i]
        stripped = line.strip()
        
        if not stripped or stripped.startswith('#'):
            i += 1
            continue
        
        actual_indent = len(line) - len(line.lstrip())
        line_type, level = _classify_line(stripped)
        
        if line_type == 'start':
            expected_indent = level * indent_size
            if actual_indent != expected_indent:
                errors.append({
                    'line': line_num,
                    'content': stripped[:50],
                    'expected': expected_indent,
                    'actual': actual_indent,
                    'type': 'start_block'
                })
            stack.append(level + 1)
            
            # 跳过APIS block内的内容
            if '[DEFINE_APIS:]' in stripped:
                i += 1
                while i < len(lines):
                    inner_stripped = lines[i].strip()
                    if '[END_APIS]' in inner_stripped:
                        break
                    i += 1
                continue
            
        elif line_type == 'end':
            if stack:
                content_level = stack.pop()
                marker_level = content_level - 1
                expected_indent = marker_level * indent_size
                if actual_indent != expected_indent:
                    errors.append({
                        'line': line_num,
                        'content': stripped[:50],
                        'expected': expected_indent,
                        'actual': actual_indent,
                        'type': 'end_block'
                    })
                    
        elif line_type == 'control':
            expected_indent = level * indent_size
            if actual_indent != expected_indent:
                errors.append({
                    'line': line_num,
                    'content': stripped[:50],
                    'expected': expected_indent,
                    'actual': actual_indent,
                    'type': 'control_flow'
                })
                
        else:
            current_level = len(stack)
            expected_indent = current_level * indent_size
            if actual_indent != expected_indent:
                errors.append({
                    'line': line_num,
                    'content': stripped[:50],
                    'expected': expected_indent,
                    'actual': actual_indent,
                    'type': 'content'
                })
        
        i += 1
    
    return errors


# 便捷函数
def fix_spl_indentation(spl_text: str) -> str:
    """修复SPL缩进（format_spl_indentation的别名）"""
    return format_spl_indentation(spl_text, indent_size=4)


def is_spl_indentation_valid(spl_text: str) -> bool:
    """检查SPL缩进是否有效"""
    errors = validate_spl_indentation(spl_text)
    return len(errors) == 0


def format_worker_block_indentation(worker_spl: str, indent_size: int = 4) -> str:
    """格式化单个WORKER block的缩进。
    
    这个函数假设输入是完整的WORKER block（包含[DEFINE_WORKER:...]和[END_WORKER]），
    并相对于WORKER的层级（level 1）来格式化内部内容。
    
    Args:
        worker_spl: WORKER SPL文本
        indent_size: 每个层级的缩进空格数（默认4）
        
    Returns:
        格式化后的WORKER SPL文本
    """
    if not worker_spl or not worker_spl.strip():
        return worker_spl
    
    lines = worker_spl.split('\n')
    result = []
    stack = []  # 相对于WORKER内部的层级栈
    i = 0
    
    # WORKER基础偏移 = 1 (DEFINE_WORKER在层级1)
    base_level = 1
    
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        
        # 空行处理
        if not stripped:
            result.append(line)
            i += 1
            continue
        
        # 注释行处理
        if stripped.startswith('#'):
            current_level = len(stack)
            result.append(' ' * ((base_level + current_level) * indent_size) + stripped)
            i += 1
            continue
        
        # 分类这一行
        line_type, level = _classify_line(stripped)
        
        # 调整层级为相对于WORKER内部的层级
        # level是全局层级，我们需要相对于base_level
        relative_level = level - base_level
        
        if line_type == 'start':
            # Block开始标记 - 缩进到其定义的全局层级
            result.append(' ' * (level * indent_size) + stripped)
            # 内容层级 = 标记层级 + 1
            stack.append(level + 1)
            i += 1
            
        elif line_type == 'end':
            # Block结束标记 - 缩进到对应的开始标记同级
            if stack:
                content_level = stack.pop()
                marker_level = content_level - 1
                result.append(' ' * (marker_level * indent_size) + stripped)
            else:
                result.append(stripped)
            i += 1
            
        elif line_type == 'control':
            # 控制流标记 - 使用其全局层级
            result.append(' ' * (level * indent_size) + stripped)
            i += 1
            
        else:
            # 普通内容行 - 缩进到当前栈深度
            current_level = len(stack)
            result.append(' ' * (current_level * indent_size) + stripped)
            i += 1
    
    return '\n'.join(result)
