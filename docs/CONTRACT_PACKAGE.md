# 可执行契约包说明

本包把前后端共同约定落实为一个可校验的 OpenAPI 文件。它提供类型与示例门禁，不包含实际 Project 服务、认证服务、数据库、网关配置或发布动作。生产服务必须另外满足主文档与运维章节的行为要求；静态校验通过不能代替部署验收。

## 1. 文件与职责

| 文件 | 用途 |
|---|---|
| `contracts/openapi.yaml` | 五个 Project 接口的唯一机器可读定义 |
| `contracts/fixtures.json` | 34 个正向/负向 Schema 样例 |
| `scripts/verify_contract.py` | OpenAPI、引用、示例和本项目规则的离线校验 |
| `tests/test_contract.py` | 证明校验器会拒绝典型错误的回归测试 |
| `requirements-contract.txt` | 人工维护的直接依赖输入，固定兼容基线 |
| `requirements-contract.lock` | 实际安装解析得到的全部 28 个依赖版本 |
| `.github/workflows/contract.yml` | Python 校验与 TypeScript 检查的 PR/push 门禁 |

OpenAPI 采用 **3.1.0**，`jsonSchemaDialect` 显式指定 **JSON Schema 2020-12**。这是为整套工具选定的兼容基线，不宣称是标准或工具的最新版本。`nullable: true` 是 OpenAPI 3.0 风格，本包使用 `type: [string, 'null']`。定义格式和 OAuth2 Flow 见 [OpenAPI 3.1.0 官方规范](https://spec.openapis.org/oas/v3.1.0)。

## 2. 安装与执行

在仓库根目录执行。交付时已在 Windows、CPython 3.12.14 上实际安装和执行以下 Python 检查；GitHub 托管 Linux 工作流需要首次推送后获得自己的执行记录。

PowerShell：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-contract.lock
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe scripts/verify_contract.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Linux / macOS：

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-contract.lock
.venv/bin/python -m pip check
.venv/bin/python scripts/verify_contract.py
.venv/bin/python -m unittest discover -s tests -v
```

依赖基线为 [PyYAML 6.0.2](https://pypi.org/project/PyYAML/6.0.2/)、[jsonschema 4.23.0](https://pypi.org/project/jsonschema/4.23.0/)（含 format 校验依赖）、[openapi-spec-validator 0.7.2](https://pypi.org/project/openapi-spec-validator/0.7.2/)。本地引用检查先于 OpenAPI 校验执行；脚本不会访问实际 API、认证服务或例子里的域名。首次安装依赖需要连接软件包仓库。

TypeScript 工具使用根目录 `package.json` 与 `pnpm-lock.yaml`，安装后运行：

```bash
pnpm install --frozen-lockfile
pnpm validate
```

修改契约后先运行 `pnpm generate`，审查并提交生成类型，再运行 `pnpm validate`。CI 的 `check:generated` 检测已提交类型是否过期，不能替代跨版本兼容性比较。

## 3. 五个接口的统一约定

| operationId | HTTP | 成功 | 必需 scope | 特殊请求头 |
|---|---|---|---|---|
| `listProjects` | `GET /v1/projects` | 200 ProjectPage | `projects:read` | 无 |
| `createProject` | `POST /v1/projects` | 201 Project | `projects:write` | `Idempotency-Key` |
| `getProject` | `GET /v1/projects/{projectId}` | 200 Project | `projects:read` | 无 |
| `updateProject` | `PATCH /v1/projects/{projectId}` | 200 Project | `projects:write` | `If-Match` |
| `deleteProject` | `DELETE /v1/projects/{projectId}` | 204 空体 | `projects:write` | `If-Match` |

创建的请求 Schema 名为 `CreateProject`，更新为 `UpdateProject`，分页响应为 `ProjectPage`。`projects:write` 不隐含 `projects:read`；界面需要读写时必须申请并获得两项 scope。租户由已验证令牌的授权上下文确定，不提供请求 `tenantId` 字段。scope 通过后仍须做租户和对象级授权。

Project 必含 `id`、`displayName`、`description`、`createdAt`、`updatedAt`、`version`。UUID 用小写规范字符串；时间为 UTC RFC 3339 字符串并以 `Z` 结尾。`version` 是 1 到 9007199254740991 的整数。`displayName` 为 1–100 个 Unicode 码点且至少一个非空白字符，不自动 trim；空白以契约 `DisplayName.pattern` 的显式码点集合为准，不依赖 Python 与 JavaScript 各自的 `\s` 定义。仅由 U+FEFF、U+0085 或 U+001C 构成的名字被拒绝，emoji 按 Unicode 码点计数。`description` 最多 2000 个码点，可为 `null`，空字符串与 `null` 不合并。

创建省略 `description` 时服务端写入空值。PATCH 使用 `application/merge-patch+json`：省略字段不改值，`description:null` 按 Merge Patch 移除成员，业务层将清除结果在完整 Project 响应中输出为必有的 `description:null`。`displayName:null`、整个文档 `null`、空对象和未知字段均被拒绝。每次成功接受 PATCH，包括同值赋值，版本都递增一次。

GET 单项、POST、PATCH 返回强 ETag，例如响应体 `version: 1` 对应头 `ETag: "1"`。PATCH/DELETE 的 `If-Match` 支持且只支持一个强版本号：缺失为 428；弱标签、列表、通配符或错误格式为 400；合法但不匹配为 412。服务端必须把比较与修改放在同一原子事务/条件写中。

该 ETag 方案要求单项 JSON 稳定 UTF-8 序列化、identity 内容编码，以及网关不压缩不转换。所有响应为 `Cache-Control: no-store, no-transform`。修改序列化规则或响应字段时，需要迁移受影响资源版本或新增 API 主版本，避免两个不同表示字节共享强 ETag。该条件是实现约束，YAML 无法自动落实。

分页 `limit` 默认 20，范围 1–100，首次省略 `cursor`。排序固定 `createdAt ASC, id ASC`，`createdAt` 不可变。游标有完整性保护，绑定租户、过滤条件、排序并在 15 分钟后过期；过期、篡改或跨租户使用返回 400 `INVALID_CURSOR`。无下一页时 `nextCursor:null`。本方案是实时 keyset 分页，跨页读取不保证快照集合完整性。

POST 幂等键使用不加引号的 ASCII 值，16–128 字符，仅字母、数字、下划线、连字符；建议随机 UUIDv4。作用域为租户、主体、operationId；同键同指纹重放原结果，不重做写入。同键不同指纹为 409 `IDEMPOTENCY_KEY_REUSED`；仍执行中为 409 `IDEMPOTENCY_IN_PROGRESS` 并发送 `Retry-After`。从终态完成起保留至少 24 小时；不能按 TTL 清理执行中或结果未知的记录。指纹算法、事务与恢复流程见运维章节。

## 4. 错误体与验证边界

错误统一使用 `application/problem+json` 和 `Problem`，必需 `type`、`title`、`status`、`code`、`traceId`。HTTP 状态必须等于 `status`，客户端按稳定 `code` 分支，对未知 code 做通用处理。422 额外必需 `errors` 数组；每项包含 `location`、`pointer`、`code`、`message`。`pointer` 是在指定 body/query/path/header 容器中的 JSON Pointer。`code`、`traceId`、`errors` 是本项目扩展，不能写成 RFC 规定的通用字段。Problem Details 和扩展规则见 [RFC 9457](https://www.rfc-editor.org/rfc/rfc9457.html)。

所有响应必须发送 `X-Request-Id`，格式为 32 位小写十六进制且非全零。新生成错误的响应头与正文 `traceId` 一致；幂等终态错误回放保留原正文 `traceId`，`X-Request-Id` 标识本次请求，服务端日志连接两者。浏览器 CORS 必须暴露该头，实际配置见运维文档。

| 检查 | 当前实现 |
|---|---|
| YAML 重复键 | 拒绝，避免后值覆盖前值 |
| OpenAPI 结构 | `openapi-spec-validator` 校验 3.1.0 |
| `$ref` | 真正的契约/Schema 引用必须为文档内部 JSON Pointer 且可解析；示例实例中的同名数据字段保持普通业务数据 |
| operationId | 五个规定操作必须齐全、标识固定且全局唯一 |
| 认证 | 每个 operation 显式定义正确的 oauth2 scope；拒绝隐式继承或匿名列表 |
| 错误 | 必须引用公共 Problem，内容类型统一，示例状态匹配 HTTP 状态 |
| 必需请求头 | POST Idempotency-Key、PATCH/DELETE If-Match 必须声明且 required=true |
| 必需响应头 | 检查单项读取/创建/更新 ETag、创建 Location、401 challenge、429/503 Retry-After，所有响应 Cache-Control/X-Request-Id 必需 |
| 示例 | 校验媒体/参数/响应头例子以及 JSON Schema examples，开启 format 校验 |
| 请求/响应扩展性 | 指定请求对象关闭未知字段；指定响应对象开放未来字段 |
| 负向样例 | 错误类型、未知字段、null 语义、ETag、UUID、时间、安全整数等 |

本校验器是针对当前项目的规则集：新增其他资源、其他 scope、外部 schema、`$id`、`$dynamicRef` 或其他 JSON Schema 方言时，需要有审查地扩展规则和测试。不要为消除失败随意关掉校验。格式校验验证的是样例值，不会把 TypeScript 的 `string` 变成运行时 UUID 验证器。

以下内容必须通过服务实现与集成测试验证：真实请求/响应格式；缺少 If-Match 是否实际返回 428；是否把错误 HTTP 状态与 Problem.status 对齐；幂等原子性/崩溃恢复/重放；租户隔离与对象授权；PKCE S256；游标签名和过期；ETag 与字节表示一致性；CORS；限流；事务回滚；数据库排序规则；负载、备份恢复和兼容升级。当前脚本没有实现这些行为，也没有把 mock 结果当作实测服务证据。

## 5. CI 与依赖维护

工作流只使用 `contents: read`，不保留 Git checkout 凭据，不配置发布令牌，并有 15 分钟任务上限。三个 Action 固定到官方仓库已核实的完整提交 SHA：

| Action | 基线版本 | 官方对应提交 |
|---|---|---|
| checkout | 4.2.2 | [11bd71901bbe5b1630ceea73d27597364c9af683](https://github.com/actions/checkout/commit/11bd71901bbe5b1630ceea73d27597364c9af683) |
| setup-python | 5.6.0 | [a26af69be951a213d495a4c3e4e4022e16d87065](https://github.com/actions/setup-python/commit/a26af69be951a213d495a4c3e4e4022e16d87065) |
| setup-node | 4.4.0 | [49933ea5288caeca8642d1e84afbd3f7d6820020](https://github.com/actions/setup-node/commit/49933ea5288caeca8642d1e84afbd3f7d6820020) |

SHA 固定保证引用稳定，不是永久免维护承诺。运行时、Action 与依赖升级应走单独 PR，重新安装锁文件、执行全套检查并审查生成代码差异。Python 锁文件固定全部解析版本，尚未包含 wheel 哈希；有制品完整性要求时，应在组织认可的包镜像中归档依赖、记录 SHA-256 并启用 hash 校验。不要把未锁传递依赖的输入文件用于可重复的 CI 安装。

当前 CI 已包含静态结构、样例、校验器回归和 TypeScript 门禁，没有真实的“与上一生产版本比较”步骤。接入发布系统时从制品库按**已发布不可变版本**取基线，缺失基线必须阻断发布，完成语义 diff 审查后才合入；不能把当前分支自己的文件当作基线制造绿灯。集成、安全、负载与发布门禁同样应接入真实环境和结果。
