# Python 命名规范与常用英文词表

命名的目标不是使用复杂英文，而是让名称能够回答“它是什么”或“它做什么”。
优先选择简单、常见、可以重复使用的英文单词，不需要追求长句或高级词汇。

## 1. 基础格式

| 对象 | 格式 | 示例 |
|---|---|---|
| Python 文件 | 小写蛇形命名 | `user_service.py` |
| 文件夹/包 | 小写蛇形命名 | `dependencies/` |
| 函数和方法 | 小写蛇形命名 | `create_user()` |
| 普通变量 | 小写蛇形命名 | `access_token` |
| 布尔变量 | `is_`、`has_`、`can_` 开头 | `is_active` |
| 类和数据模型 | 大驼峰命名 | `UserService` |
| 常量 | 大写蛇形命名 | `MAX_RETRY_COUNT` |
| 私有实现 | 单下划线开头 | `_build_payload()` |
| 测试函数 | `test_预期行为` | `test_create_user_success()` |

不要使用拼音、无意义缩写或中英文混合标识符：

```python
# 不推荐
def huoqu_yonghu(): ...


def get_usr_info(): ...


# 推荐
def get_user(): ...


def get_user_profile(): ...
```

## 2. 函数命名公式

函数名称通常使用“动词 + 名词”：

```text
create + user       -> create_user
get + order         -> get_order
list + articles     -> list_articles
update + profile    -> update_profile
delete + comment    -> delete_comment
verify + password   -> verify_password
decode + token      -> decode_token
register + routes   -> register_routes
```

常见操作动词：

| 英文 | 含义 | 使用场景 |
|---|---|---|
| `create` | 创建 | 新建数据库记录或资源 |
| `get` | 获取一个 | 按 ID 获取单条数据 |
| `list` | 获取多个 | 列表、分页查询 |
| `update` | 更新 | 修改已有数据 |
| `delete` | 删除 | 删除资源 |
| `load` | 加载 | 从文件、缓存或外部来源读取 |
| `save` | 保存 | 写入文件或持久化 |
| `build` | 构造 | 分步骤组装复杂对象 |
| `parse` | 解析 | 把字符串转换成结构化数据 |
| `encode` | 编码 | 对数据进行编码 |
| `decode` | 解码 | 还原编码数据 |
| `validate` | 校验格式 | 检查字段、结构或规则 |
| `verify` | 验证真伪 | 密码、签名、令牌验证 |
| `hash` | 哈希 | 生成不可逆摘要 |
| `register` | 注册 | 注册路由、异常处理器 |
| `configure` | 配置 | 应用日志或组件配置 |
| `open` / `close` | 打开/关闭 | 文件或连接生命周期 |

## 3. 数据名称公式

变量和类通常使用名词：

| 英文 | 含义 |
|---|---|
| `user` | 用户 |
| `account` | 账号 |
| `profile` | 资料 |
| `article` | 文章 |
| `order` | 订单 |
| `request` | 请求 |
| `response` | 响应 |
| `payload` | 载荷 |
| `token` | 令牌 |
| `session` | 会话 |
| `connection` | 连接 |
| `engine` | 数据库引擎 |
| `factory` | 工厂/创建器 |
| `settings` | 配置集合 |
| `schema` | 数据结构模型 |
| `model` | ORM 或领域模型 |
| `router` | 路由器 |
| `service` | 业务逻辑服务 |
| `repository` | 数据仓储 |
| `dependency` | 依赖项 |
| `handler` | 处理器 |
| `middleware` | 中间件 |
| `exception` | 异常 |
| `cache` | 缓存 |
| `metadata` | 元数据 |

## 4. 查询函数命名

按照返回数量区分：

```python
get_user(user_id)  # 返回一个用户，不存在时通常返回 None 或抛出异常
get_user_by_email(email)  # 根据特定字段返回一个用户
list_users()  # 返回用户列表
search_users(keyword)  # 根据条件搜索多个用户
count_users()  # 返回数量
user_exists(email)  # 返回 bool
```

布尔函数使用能够直接读成问题的名称：

```python
is_active()
has_permission()
can_delete_article()
token_is_expired()
```

## 5. 各层常用命名

### Router

```python
router
create_user
get_user
list_users
update_user
delete_user
```

### Schema

```python
UserCreate
UserUpdate
UserResponse
UserListResponse
LoginRequest
TokenResponse
```

### ORM Model

```python
User
UserToken
Article
OrderItem
```

### CRUD / Repository

```python
create_user
get_user_by_id
get_user_by_email
list_users
update_user
delete_user
```

### Service

```python
register_user
authenticate_user
publish_article
cancel_order
reset_password
```

Service 名称表达业务动作，CRUD 名称表达数据库动作。

## 6. 当前项目标准名称

本模板已经统一使用以下名称：

```python
create_app
register_middlewares
register_exception_handlers
get_settings
async_engine
async_session_factory
get_db_session
get_redis_client
close_redis
hash_password
verify_password
create_access_token
get_current_token_payload
ResponseModel
Base
```

## 7. 英文不熟悉时的实用办法

1. 先用中文写清楚功能，例如“根据邮箱获取用户”。
2. 套用“动词 + 名词”公式：获取=`get`，用户=`user`，根据邮箱=`by_email`。
3. 得到 `get_user_by_email`。
4. 在整个项目中搜索相似名称，保持同一概念只使用一个英文单词。
5. 把新出现且会重复使用的业务词补充到本文词表。

可以让 AI 帮助命名，但应提供返回值和行为：

```text
请给“根据邮箱查询单个用户，不存在返回 None”的 Python 异步函数起名，
要求 snake_case，并说明选择原因。
```

推荐结果应类似：

```python
async def get_user_by_email(...) -> User | None:
    ...
```

避免只问“这个函数叫什么”，因为缺少行为信息时容易得到不准确名称。
