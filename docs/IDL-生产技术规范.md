# IDL生产技术规范

基于 OpenAPI 的前后端接口契约设计与交付手册

文档版本 1.0.0　技术基线 OpenAPI 3.1.0　编制日期 2026年9月14日

本规范采用 OpenAPI 描述 HTTP JSON 接口，以仓库中的契约文件作为请求、响应和代码生成的共同依据。前端、后端、测试和平台团队围绕同一份定义完成评审、开发、验证及发布，减少字段不一致、错误处理分歧和接口升级中断。

本文可作为团队生产开发规范直接纳入仓库。配套工程提供完整 Project 资源契约、正反例、静态校验、TypeScript 调用样例和 CI 工作流。生产接入时，实施团队应完成第 3 节的环境配置及上线验收，将实际业务服务纳入契约测试。文中的“必须”“应当”“可以”分别表示本方案的强制规则、推荐规则和可选规则；引用标准的要求以原标准为准。

## 1 适用范围与技术决策

本规范适用于浏览器或移动端访问业务 HTTP API，以及网关后的同步 JSON 服务。服务端可以使用 Java、Go、Python、Node.js 或其他技术栈。示例使用项目管理业务说明完整接口生命周期，业务资源可以替换，契约规则应保持一致。

| 维度 | 本方案选择 | 工程约束 |
| --- | --- | --- |
| 传输 | HTTPS 上的 HTTP API | 客户端使用 HTTPS 服务地址 |
| 契约 | OpenAPI 3.1.0 | 所有操作与数据结构纳入版本管理 |
| 数据约束 | JSON Schema 2020-12 兼容子集 | 只采用已通过当前工具链验证的关键字 |
| 文档载体 | YAML 源文件 | YAML 只用于描述契约，线上请求体使用 JSON |
| 前端类型 | openapi-typescript | 从契约生成，禁止手改生成文件 |
| 前端请求 | openapi-fetch | 认证获取与 UI 状态由应用管理 |
| 失败响应 | Problem Details | 使用 application/problem+json |
| 浏览器认证 | OAuth2 授权码流程与 PKCE | 由受信任的身份服务签发访问令牌 |
| 版本演进 | 路径主版本与契约语义版本 | 先部署兼容服务端，再启用新客户端能力 |

OpenAPI 是 HTTP API 的接口描述规范，可用于文档、代码生成和测试工具。这里固定 3.1.0 作为可复现基线，升级规范版本时，应同时验证解析器、生成器、网关与测试工具。本文件中的 `openapi` 是规范版本，契约的 `info.version` 是 API 文档版本，二者分别维护。[OpenAPI 规范](https://spec.openapis.org/oas/v3.1.0.html)

已有 gRPC 服务可以继续使用 Protobuf，GraphQL 服务可以继续使用 SDL。若向浏览器提供 REST 网关，应单独维护外部 HTTP 契约和明确的内部字段映射。消息队列、WebSocket、文件下载和事件流应建立对应的专门契约及验收规则；不要为了统一格式把所有通信模型转换为本例的 CRUD。

## 2 契约结构与权威来源

`contracts/openapi.yaml` 是接口结构的权威来源；本手册规定其业务语义和实施方式。若二者出现冲突，应修正同一个变更集中的契约、示例、客户端和文档后再合并。生产系统的行为必须与发布的契约版本一致。

契约至少包含 API 标题、版本、服务地址、操作路径、唯一 `operationId`、参数位置与约束、请求媒体类型、成功与失败响应、认证方案及权限范围。每个公开字段应说明单位、缺省行为、空值语义、边界和至少一个示例。所有 `$ref` 必须可解析，外部网络引用不得成为构建依赖。

```text
需求与业务规则
    → OpenAPI 契约及示例
    → 前后端共同评审
    → 规范校验与代码生成
    → 服务实现及客户端接入
    → 行为测试与兼容性评审
    → 契约和服务一起发布
```

评审者应区分四个层次：语法合法、数据结构合法、业务行为正确、生产运行达标。静态校验通过只能证明其检查范围内的定义成立。`security` 声明不会自动完成鉴权，`default` 不会自动写入请求，`format` 也需要运行时校验器配置才能执行。

JSON Schema 的 `required` 决定属性是否必须出现，`type` 决定其允许值；出现且为 `null` 与完全缺省不同。`additionalProperties` 决定未声明属性的处理方式。[对象约束](https://json-schema.org/understanding-json-schema/reference/object) [类型约束](https://json-schema.org/understanding-json-schema/reference/type)

## 3 接入顺序与环境配置

首次接入应按以下顺序完成。负责人员是团队角色，每个项目应在内部发布记录中填入具体人员或值班组。

| 阶段 | 必须完成的工作 | 负责角色 | 完成证据 |
| --- | --- | --- | --- |
| 契约初始化 | 替换资源与字段，确认所有业务错误 | API 负责人及前端负责人 | 契约评审记录 |
| 环境配置 | 设置服务域名与 OAuth 参数 | 平台及身份团队 | 环境配置清单 |
| 服务实现 | 校验、授权、事务、幂等和并发控制 | 后端负责人 | 集成测试结果 |
| 客户端接入 | 生成类型、设置令牌提供函数、处理错误 | 前端负责人 | 浏览器端测试结果 |
| 交付验证 | 执行 CI 及目标环境验收 | 测试负责人 | 发布报告 |
| 上线运行 | 灰度、监控、回滚与值班交接 | 发布负责人 | 发布记录及回滚演练 |

环境配置必须包括 API 的 HTTPS 根地址、OAuth issuer、authorization URL、token URL、audience、public client ID、精确注册的 redirect URI、所需 scopes、CORS 来源名单、超时与重试预算、幂等保存周期、cursor 签名密钥及轮换方式。示例中的 `api.example.com`、`auth.example.com` 和其他 example.com 地址是保留域名，部署前替换为实际受控地址。

客户端不得内置 OAuth client secret；访问令牌、签名密钥与生产连接字符串不得进入契约、示例或前端构建产物。环境之间可以更换地址与配置，但同一个版本的接口结构应保持一致。域名替换也要通过 URL 与重定向配置检查。

本仓库提供的快速开始命令及工具固定版本见 `README.md` 和 `docs/CONTRACT_PACKAGE.md`。在 Windows 中使用仓库虚拟环境的 `Scripts/python.exe`，在 Linux 中使用 `bin/python`。安装依赖后先验证契约，再生成类型并编译客户端，随后启动团队自己的后端服务执行接口验收。

## 4 仓库与日常工作流

```text
contracts/openapi.yaml          接口定义
contracts/fixtures.json         数据正反例
scripts/verify_contract.py      契约与示例检查
tests/                         校验器测试
examples/typescript/            客户端与生成类型
.github/workflows/contract.yml  持续集成
docs/IDL-生产技术规范.md         团队规范正文
docs/CONTRACT_PACKAGE.md        契约工具使用与覆盖范围
```

开发者从需求创建变更分支，先修改契约及正反例。后端评审资源语义、错误、权限和数据库影响；前端评审可用性、类型映射、错误展示和旧客户端兼容性。完成评审后可以并行开发。生成类型应与源契约一起提交，CI 检查重新生成后是否发生差异。

一次变更必须同时包含必要的契约、数据样例、服务实现、客户端更新、行为测试和发布说明。对于分仓库系统，可以分多次部署，但发布记录必须包含对应契约版本与提交号。生成产物禁止手工修补；需要改变行为时应修改契约或客户端包装层。

契约评审权限应通过仓库规则落实。团队可配置 CODEOWNERS 覆盖 `contracts/`、`examples/typescript/schema.d.ts` 与兼容性规则，并要求 API 与消费方至少各一名负责人参与。CI 中已实现的检查与需要由团队接入的检查在验证记录中分别列明。

## 5 URL与请求设计

资源路径使用复数名词和小写短横线形式，例如 `/v1/projects`。路径参数表示资源身份，查询参数表示过滤和分页。JSON 字段使用 lowerCamelCase，Schema 名称使用 PascalCase，`operationId` 使用稳定的动词加资源名，例如 `createProject`。已发布的 `operationId` 会影响生成 API，修改前必须评估调用方。

| 操作 | 方法与路径 | 成功响应 | 额外请求要求 |
| --- | --- | --- | --- |
| 列出项目 | GET /v1/projects | 200 项目列表 | projects:read |
| 创建项目 | POST /v1/projects | 201 项目及 Location 和 ETag | projects:write 与 Idempotency-Key |
| 读取项目 | GET /v1/projects/{projectId} | 200 项目及 ETag | projects:read |
| 局部更新 | PATCH /v1/projects/{projectId} | 200 更新后项目及 ETag | projects:write 与 If-Match |
| 删除项目 | DELETE /v1/projects/{projectId} | 204 无响应体 | projects:write 与 If-Match |

GET 不承载请求体且不得产生业务写入。创建使用 `application/json`；局部更新使用 `application/merge-patch+json`。接口不接受媒体类型不符的请求，返回 415。204 响应没有 JSON 数据，客户端不得强制对其解析 JSON。

路径 UUID 验证失败、查询参数无法解析或 JSON 语法损坏按契约返回 400；JSON 可解析但请求对象不符合业务字段约束时返回 422。未知查询参数应拒绝，避免拼写错误静默改变查询行为；若某个框架默认忽略参数，需要额外实现这一规则。

查询参数只接受文档列出的参数。重复的单值参数应返回 400；数组参数必须在契约中明确序列化规则。查询条件直接映射到预定义过滤项，SQL 排序字段和过滤操作使用服务端白名单。租户上下文从已校验身份及授权关系中确定。

## 6 数据建模规则

| 数据类别 | 表达方式 | 本方案规则 |
| --- | --- | --- |
| 资源标识 | string 与 uuid format | 不使用数据库自增数值作为跨语言 ID |
| 时间点 | string 与 date-time format | 服务端统一输出 UTC 与 Z 后缀 |
| 日历日期 | string 与 date format | 明确是日期，不擅自补时区 |
| 计数与版本 | 有上下界的 integer | 浏览器使用的整数不得超出安全整数范围 |
| 金额 | 十进制字符串或最小币种单位整数 | 必须说明币种、精度及舍入规则 |
| 状态 | string | 有限枚举必须定义未知值处理与升级策略 |
| 集合 | array | 用空数组表示无条目，限制请求数组长度 |
| 可空文本 | type 为 string 和 null | 区分缺省、空字符串与 null |

线上 JSON 使用 UTF-8。整数超出 JavaScript 精确整数范围时，应改为十进制字符串传递；不允许 NaN、Infinity 或未定义值出现在 JSON 中。JSON 重复键应在解析阶段拒绝，避免各语言解析结果不同。[JSON 标准](https://www.rfc-editor.org/rfc/rfc8259.html)

时间输出采用 RFC 3339 格式，例如 `2026-09-14T08:00:00Z`。本方案要求统一 UTC；精度在同一字段上固定，服务端保存精度与分页比较精度必须一致。[时间戳标准](https://www.rfc-editor.org/rfc/rfc3339.html)

请求与响应使用独立 Schema。创建请求只接受可写字段；`id`、`createdAt`、`updatedAt`、`version` 由服务端生成，客户端提交这些字段应失败。请求对象设置 `additionalProperties: false`。响应允许增加字段，客户端读取自己认识的字段，但服务端序列化仍应使用明确的输出 DTO 白名单，避免泄露内部数据。

不要直接把数据库实体当成 API Schema。字段的内部命名、索引和存储空值可以改变，只要公开契约与语义保持稳定。嵌套对象、数组长度及文本长度应有边界。字符串长度按 Unicode 码点计数，不以 JavaScript UTF-16 code unit 数量或用户感知字素数量替代；增加 emoji 与组合字符的边界样例。UI 显示宽度与用户感知字符数应单独考虑。

`format`、正则表达式和业务验证职责必须明确。JSON Schema 检查能验证 UUID 和结构，授权逻辑负责访问资格，领域逻辑负责诸如配额、唯一性与状态转换。默认值由服务端显式执行，测试覆盖应用后的值；日志只记录允许公开的非敏感配置值，不依赖生成器碰巧填充。

`allOf` 表示同时满足所有约束。团队应避免把关闭额外字段的基础 Schema 与新增字段机械组合，否则可能拒绝合法字段。需要多态时为各分支定义明确标识，并验证 `oneOf` 分支互斥；工具链未验证的复杂关键字应先补测试再采用。

## 7 Project字段与空值语义

| 字段 | 响应类型 | 创建规则 | 更新规则 |
| --- | --- | --- | --- |
| id | UUID 字符串 | 服务端生成 | 不可修改 |
| displayName | 非空字符串 | 必填且满足长度约束 | 缺省不变，null 不合法 |
| description | 字符串或 null | 可选，缺省规范化为 null | 缺省不变，null 清除 |
| createdAt | UTC 时间字符串 | 服务端生成 | 不可修改 |
| updatedAt | UTC 时间字符串 | 服务端生成 | 成功变更时更新 |
| version | 正整数 | 服务端初始化 | 与并发版本控制一起递增 |

准确的长度、数值上界和正则以配套 YAML 为准。`displayName` 长度为 1 至 100 个码点且至少含一个非空白字符，不自动 trim；首尾空格可以保留。空白字符采用契约显式列举的码点范围，包含 U+FEFF、U+0085 和 U+001C 等边界字符，不依赖各语言对 `\S` 的不同解释。`description` 最多 2000 个码点。若业务要求禁止首尾空格，应在契约与校验逻辑中同步添加规则。显示名称不承担唯一业务标识职责；若增加唯一约束，应补充作用范围和冲突错误。

下面是局部更新请求的语义：

```json
{"displayName": "新版项目名称"}
```

只更新名称，保留原描述。以下请求清除描述：

```json
{"description": null}
```

Merge Patch 首先以 null 移除表示中的成员，业务层据此清除持久化描述；返回公开 Project 表示时，规范化为必有 `description: null`。空对象 `{}` 被本方案拒绝。数组如未来纳入 Merge Patch，应明确整个数组替换语义；需要按元素更新时另设资源操作。[Merge Patch 标准](https://www.rfc-editor.org/rfc/rfc7396.html)

## 8 响应与错误处理

成功响应直接返回资源对象或列表对象。列表包含 `items` 和 `nextCursor`，最后一页 `nextCursor` 为 null。创建返回 201 并给出新资源 `Location`，读取与更新返回 ETag。业务失败使用对应 HTTP 状态码和 Problem Details，避免用 HTTP 200 包裹错误。

| HTTP状态 | 本方案含义 | 客户端动作 |
| --- | --- | --- |
| 400 | 语法或参数格式错误 | 修正请求后重试 |
| 401 | 缺少或无效身份凭证 | 按认证流程重新获取身份 |
| 403 | 已认证但权限不足 | 提示无权限，停止自动重试 |
| 404 | 资源不存在或按策略隐藏 | 刷新列表或提示不可用 |
| 409 | 业务冲突或幂等处理冲突 | 按稳定错误码处理 |
| 412 | 当前资源版本与 If-Match 不符 | 重新读取并解决编辑冲突 |
| 415 | 请求媒体类型不受支持 | 修正 Content-Type |
| 422 | 字段或领域输入不符合约束 | 展示对应字段错误 |
| 428 | 更新或删除缺少条件头 | 读取资源后提供 If-Match |
| 429 | 达到请求限制 | 遵守 Retry-After 与重试预算 |
| 500 | 未预期的服务内部失败 | 展示可追踪失败并记录关联信息 |
| 503 | 临时服务不可用 | 在安全条件下延后尝试 |

每个操作实际承诺的状态码应与 YAML 中的 `responses` 一致。API 层能够处理的失败按契约输出；CDN、代理或连接层仍可能返回 HTML、纯文本、空响应或直接断连，客户端必须有解析失败和网络失败分支。

Problem Details 使用 `type` 标识问题类别，`title` 表示稳定的类别描述，`status` 与 HTTP 状态一致，`detail` 描述本次安全可公开的原因，`instance` 如提供则用于定位本次问题。本方案增加稳定 `code`、请求关联用 `traceId` 和字段错误集合 `errors`。422 响应必须包含非空 `errors`，其他错误中可选。前端按 `code` 处理逻辑，禁止解析自然语言 `detail` 推断业务分支。[Problem Details 标准](https://www.rfc-editor.org/rfc/rfc9457.html)

API 所有响应声明 `Cache-Control: no-store, no-transform` 与 `X-Request-Id`。本方案将请求关联标识编码为非全零的 32 位小写十六进制串；新生成的错误体 `traceId` 与当前响应头的关联标识保持一致。终态错误的幂等回放保留正文中的原 traceId，响应头使用本次请求的新标识，日志关联二者。

字段错误定位方式与字段名称统一，嵌套路径采用契约规定的指针形式。错误不返回 SQL、堆栈、服务密钥、令牌、内部路径或未经处理的用户输入。UI 展示错误使用文本渲染，服务端返回的内容不得直接作为 HTML 插入。

## 9 服务端实现流程

请求首先经过网关的连接与大小限制、来源策略及基础限流；进入业务服务后验证身份与权限，再完成参数解码与结构校验。POST 的幂等查重在会随时间变化的配额、唯一性等领域规则之前完成，以免已经成功的提交因后续状态变化而无法回放。对于带条件的请求，应按 HTTP 前置条件处理规则，在常规检查通过后、实际变更之前检查版本。应以稳定策略决定错误优先级，避免通过错误信息泄露资源是否存在。

后端需要实现以下流程，并在集成测试中验证每一步的边界：

1. 解析受支持的媒体类型、路径、查询和请求体，拒绝重复 JSON 键与非法编码。
2. 校验令牌签发方、受众、有效期与权限；确定主体及租户授权上下文。
3. 验证 Schema，建立 API 输入与领域对象的明确映射。
4. POST 先做幂等查重，仅新请求执行会变化的领域规则；PATCH 与 DELETE 在常规检查通过后完成 ETag 条件检查。
5. 在数据库事务中执行授权范围内的写入，必要事件使用事务发件箱。
6. 将持久化结果映射为公开 DTO，填写状态、ETag、Location 等响应头。
7. 记录结构化访问日志、指标及审计事件，敏感信息按字段规则脱敏。

Schema 校验建议在测试和预发布环境覆盖全部请求与响应。在生产请求入口持续校验输入；对于内部构造的响应，可根据开销采用抽样或异步检查，但必须确保异常不会导致敏感响应进入日志。响应漂移告警要包含 operationId 与契约版本，便于定位。

数据库与外部系统失败需保留原子性。更新或删除必须将权限条件、资源 ID 和版本条件放在同一个受控事务边界内，不能先检查版本再执行无条件写入。外部通知、付款等不可回滚副作用需要单独设计幂等与补偿，不可仅凭 API 返回 500 就断定操作未发生。

## 10 前端接入与生成代码

前端从契约生成 TypeScript 声明，再由薄包装层管理基础地址、访问令牌、超时、错误和业务返回值。配套 `examples/typescript/client.ts` 展示五种资源操作；其调用方式和测试命令见同目录 README。`getAccessToken` 由应用注入，客户端库不保存登录凭证，也不承担 OAuth 登录 UI。

openapi-typescript 支持从 OpenAPI 生成声明，openapi-fetch 提供基于这些声明的请求类型推导。TypeScript 类型检查发生在编译期，生成类型不会自动校验线上 JSON；需要运行时保证时，应在边界增加经过验证的 Schema 校验器。[类型生成说明](https://openapi-ts.dev/introduction) [请求客户端说明](https://openapi-ts.dev/openapi-fetch/)

创建操作的幂等键属于一次业务提交。应用应在第一次发送前生成并保存它，在同一提交的超时、断线或重复点击恢复中复用；用户确认开始新的业务提交时才生成新键。样例要求调用者显式传入 key，避免请求包装器在每次重试时悄悄换键。

编辑界面读取 Project 时同时保存 ETag。提交 PATCH 时使用该 ETag；遇到 412 应重新读取并让用户解决差异，禁止用最新 ETag 自动覆盖其他人的变更。DELETE 遇到失败也应按具体状态重新读取和确认结果。

UI 应区分取消、网络不可达、超时、认证失败、输入错误、版本冲突和服务器失败。更新请求超时后，界面应表现为“结果待确认”，通过已知资源 ID 重新读取核对。POST 在约定有效窗口内用同 key 与同语义请求取得终态回放；超过窗口或仍然未知时，通过运营工具关联幂等记录并恢复，本契约未提供独立幂等查询端点。用户切换页面时取消旧读取请求，防止迟到响应覆盖当前页面数据。

## 11 扩展接口的约定

批量操作需要给出条数上限、原子性、条目关联标识和部分失败格式，并明确幂等粒度。异步长任务应返回任务资源与查询位置，定义排队、运行、完成、失败、取消状态和结果保留期限；202 表示已接受处理，不能当作业务成功完成。

文件上传宜采用受限的对象存储上传流程，约定大小、类型、校验和、对象归属、扫描状态及下载权限。上传成功和业务对象可用应有明确边界。下载与事件流采用各自媒体类型和客户端处理，不套用本例 JSON 对象解析逻辑。

Webhook 应独立定义事件 ID、Schema 版本、签名原文、时间窗口、密钥轮换、重试周期、去重期限和重放方式，并限制回调地址的访问范围。分页大规模导出宜使用异步导出或快照，不把普通游标列表承诺为数据库一致性快照。

上述扩展属于设计入口，配套工程只实现契约工具与 Project 同步接口样例。团队新增这些能力时，应另行补全其契约、失败模式和验收用例。

## 12 安全与认证

浏览器使用 OAuth 2.0 Authorization Code + PKCE `S256`；禁止在前端放置 client secret。精确登记回调地址，将一次性 verifier/state 绑定登录事务并校验返回；使用 OIDC 时还需验证 ID Token 的 issuer、audience、签名、有效期及 nonce。ID Token 不作为 API access token。公共客户端使用 PKCE 是标准安全要求，BFF 是本方案的架构选择。[RFC 9700](https://www.rfc-editor.org/rfc/rfc9700.html)

基线契约是资源 API 的 Bearer 认证，随附浏览器示例为 SPA 直连：access token 仅放内存，refresh token 按身份平台能力实施轮换或发送方约束；不得写入 URL、日志或持久化前端存储。可选生产架构是同源 BFF：浏览器访问 `https://app.example.com/api`，BFF 保存 access/refresh token 并转发资源 API，浏览器只持有随机会话标识。BFF 的浏览器 Cookie 端点、登录/退出及 CSRF 机制必须另写契约，不能把接收 `getAccessToken` 的资源 API 客户端直接当作 Cookie SDK。

BFF Cookie 设置 `Secure; HttpOnly; SameSite=Lax; Path=/`，采用 `__Host-` 前缀且不设置 Domain。登录后轮换会话，退出时作废服务端会话。Cookie 时长、绝对/空闲超时、token 轮换和撤销策略由身份负责人登记；回调方式需验证与 SameSite 的兼容性。

Cookie 认证的写请求同时校验精确 Origin 和绑定会话的 CSRF token，拒绝缺失/错误 token；SameSite 只是补充措施。OAuth 回调有独立的登录事务防护，不套用业务 CSRF header。CORS 只控制浏览器跨源读取，不能替代认证和对象授权。[OWASP CSRF 防护](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)

同源 BFF 无需开放资源 API CORS。若浏览器直连 `https://api.example.com`，按白名单返回单一 Origin，动态选择时加 `Vary: Origin`；预检允许实际所需方法及 `Authorization, Content-Type, Idempotency-Key, If-Match, traceparent`，Cookie 模式还应允许实际使用的 CSRF header。向脚本暴露 `ETag, Location, Retry-After, X-Request-Id`。携带 Cookie 时还需 `Access-Control-Allow-Credentials: true`，Origin 不得为 `*`；允许合法预检通过不代表业务请求免鉴权。[Fetch CORS 协议](https://fetch.spec.whatwg.org/#http-cors-protocol)

资源服务校验 access token 的 issuer、audience、时效和签名/内省结果；只信任配置的算法与密钥来源。每次读取、修改、删除 Project 都执行 `principal + tenant + action + resource` 授权，不能仅凭 `projects:write` scope 或 UUID 难猜而放行。租户来自已验证身份并核对租户成员关系；数据库查询显式包含 tenant 条件。更新按字段白名单映射 `displayName/description`，禁止请求覆写 owner、tenant、内部状态。[OWASP 对象级授权](https://api-security.owasp.org/editions/2023/en/0xa1-broken-object-level-authorization/)

## 13 幂等与并发与故障恢复

创建 Project 必须携带高熵 `Idempotency-Key`。同一次用户意图生成一次，网络重试复用；主动创建第二个 Project 才生成新 key。数据库唯一键采用 `(tenant_id, principal_id, operation_id, key)`；每次回放仍重新认证授权，不能向失去权限的主体泄露历史结果。

持久化记录至少包含作用域、语义指纹及算法版本、状态、业务资源 ID、结果状态码/正文/必要响应头、开始/完成/过期时间、租约与 fencing token。指纹覆盖方法、规范化路由/业务参数和请求体语义；只做明确约定的规范化，保留数组顺序、缺失与 null 差异，拒绝重复 JSON 成员。不能未经约定就 trim 字符串、转换大小写或丢弃未知字段；包含行为相关头（如适用的 If-Match）。散列原始 JSON 文本会将对象成员排序、空白差异误判为不同请求。

| 当前记录 | 本次条件 | 团队约定的处理 |
|---|---|---|
| 无记录 | 身份、格式及参数有效 | 原子占位为 `IN_PROGRESS`，仅占位成功者执行 |
| 任意有效记录 | 指纹不同 | `409`，问题码 `IDEMPOTENCY_KEY_REUSED` |
| `IN_PROGRESS` | 指纹相同 | `409`，问题码 `IDEMPOTENCY_IN_PROGRESS`，附 `Retry-After` |
| `SUCCEEDED` / `FAILED_FINAL` | 指纹相同且仍有权访问 | 回放已记录业务结果，不再次执行 |
| `UNKNOWN` | 提交结果无法确定 | 冻结执行，查询业务事实并对账后转终态 |

`409 + Retry-After` 是本方案协议约定。结果回放保留原业务正文、状态码、Location/ETag，但重新生成当前请求追踪头，绝不回放 Set-Cookie 等会话头。终态错误的原正文 traceId 定位首次处理，新的 X-Request-Id 定位本次回放，日志保存二者关联。认证、格式校验或限流的前置拒绝不占位；已开始处理后的确定性业务失败记录为 `FAILED_FINAL`。确认事务完全回滚且没有外部副作用的瞬时故障才可安全释放或重新执行；超时、断连及不确定的 5xx 不能据此推断事务回滚。

单数据库事务须原子提交业务写入、幂等终态和结果记录；“先写业务，再写 Redis 成功缓存”存在重复创建窗口。外部调用使用同事务 outbox 和稳定业务去重键，下游也需实现去重/对账，不宣称跨系统 exactly-once。租约到期只触发恢复检查；接管者使用 fencing token 阻止旧执行者继续写入。`IN_PROGRESS/UNKNOWN` 不得被普通 TTL 清理任务删除。

终态保留期建议自完成起至少 24 小时，业务最长重试窗口、离线客户端及故障恢复需要更长时相应延长。到期可能被清理并作为新请求执行，因此客户端超过约定窗口不得盲目重发创建，应查询业务结果或进入人工恢复。金融、订单等不可重复业务还需独立业务唯一约束，不能依赖临时 key。为卡住记录设置年龄告警、资源关联查询、人工修复审计和定期恢复任务。

## 14 ETag 与局部更新

GET 返回强 ETag，示例 `ETag: "7"`；更新提交原样 `If-Match: "7"`。标准采用强比较；前提不成立返回 `412`，本方案缺少条件返回 `428` 并设置 `Cache-Control: no-store, no-transform`。本方案要求单一具体强标签，拒绝 `*`、弱标签或多值作为更新输入，错误按契约返回 `400`；这是对 HTTP 可用语法的应用级收窄。[RFC 9110 条件请求](https://www.rfc-editor.org/rfc/rfc9110.html#section-13.1.1)、[RFC 6585 §3](https://www.rfc-editor.org/rfc/rfc6585.html#section-3)

授权、读取当前版本和条件更新必须在事务中保持一致，例如 `UPDATE ... WHERE tenant_id=? AND id=? AND version=?`，成功后递增版本；受影响行数为零时在权限范围内区分不存在与冲突。ETag 必须随实际表示变化；本基线固定单项资源 JSON 的 UTF-8 序列化与 identity 内容编码，网关不得压缩或变换，响应使用 no-transform。任何影响表示字节的变化都须更新 version；更换序列化规则应迁移受影响版本或发布新 API 版本。扩展投影或压缩编码前，应重新设计能区分表示变体的 ETag 契约。客户端收到 `412` 后重新获取并让用户合并修改，禁止自动套用新标签覆盖别人提交。

PATCH 使用 `application/merge-patch+json`：省略字段不改变；`displayName` 不可为 null；`description: null` 按 Merge Patch 删除表示成员，业务层清除存储值，再将响应规范化为必有的 `description: null`。先在副本上应用补丁，校验完整业务状态，再原子提交；数组整体替换，不能把 Merge Patch 当作数组元素更新语言。[RFC 7396](https://www.rfc-editor.org/rfc/rfc7396.html)

## 15 游标分页与一致性

Project 固定按不可变 `(createdAt, id)` 升序，后页查询使用 `createdAt > lastCreatedAt OR (createdAt = lastCreatedAt AND id > lastId)`；时间精度、ID 排序规则与数据库索引一致。Cursor 是不可解释的服务端令牌，签名并绑定租户、身份/权限上下文、过滤条件、排序、最后位置、协议版本和到期时间；包含敏感内容时加密，单纯 Base64 不提供保护。每页重新授权。篡改、跨租户、过滤条件改变或过期统一按契约返回 `400 INVALID_CURSOR`。

默认列表是逐页当前视图，不承诺快照：并发删除、权限变化、筛选字段更新或晚提交记录都可能让集合与首页时不同；keyset 只能改善偏移分页位移问题。导出若要求首页时集合完整一致，另设异步导出任务并固定数据库快照/版本化结果集，不能把长事务挂在多个浏览器请求之间。本基线 Cursor 有效期为 15 分钟，limit 默认 20 且最大 100；准确约束写入契约，服务端限制扫描量，不接受无限 limit。

## 16 超时与重试与限流

每条调用链设总 deadline，并向下游传递剩余预算；连接、读响应、数据库锁等待和外部调用分别限时。取消客户端请求不能视为服务端业务取消。初始容量配置由接口负责人给出并经压测确定，例如交互总预算 10 秒、单次请求最多 5 秒；其含义是所有重试和等待合计受 10 秒限制，不是每层都可用满额预算。

客户端仅对网络瞬时失败及明确可恢复的 `408/429/502/503/504` 考虑重试，前提仍是操作可安全重复。GET 可有限重试；POST 仅在该端点已实现上述幂等协议、同 key/同语义、处于有效窗口时重试。无 key 的 POST、未知业务结果、`412/422` 不自动重试；`401` 最多触发一次受控刷新，再按原操作的重试资格决定是否重发。[RFC 9110 幂等方法](https://www.rfc-editor.org/rfc/rfc9110.html#section-9.2.2)

随附客户端每次调用只发送一次；业务层需要自动重试时，团队约定最多追加 1 次，采用 full jitter：`random(0, min(2s, 200ms * 2^attempt))`。解析 Retry-After 的秒数与 HTTP 日期，等待不早于该值；超过剩余 deadline 则结束并向调用者返回可再次尝试时间。只在一层拥有重试策略，避免浏览器/BFF/网关/服务多层放大；幂等处理中 409 仅按其问题码和约定延后。[RFC 9110 Retry-After](https://www.rfc-editor.org/rfc/rfc9110.html#section-10.2.3)

网关按 tenant/principal/operation 实施速率与突发限流，服务端另设并发、请求体字节、分页量、执行时间和日配额；IP 只能作为附加信号。限流返回 `429` 与恢复提示，容量故障返回 `503`，不得把二者混同。[RFC 6585 §4](https://www.rfc-editor.org/rfc/rfc6585.html#section-4) 初始阈值记录为配置版本并附压测证据；限制器故障时读请求可限额降级，写入和付费资源按业务风险选择拒绝，必须预先登记，不能默认无限放行。幂等回放也计入请求速率，但不再次扣业务用量。

## 17 可观测性与敏感数据

入口生成受控 `X-Request-Id`，分布式追踪使用 `traceparent`；校验外部值格式与长度，跨信任边界按策略重新建 trace，不能把追踪 ID 作为授权依据。[W3C Trace Context](https://www.w3.org/TR/trace-context/) 结构化日志记录时间、operationId、路由模板、状态、耗时、服务版本、脱敏主体/租户标识、幂等命中和冲突类别。禁止日志记录 Authorization、Cookie、token、完整请求体和用户 description；key 只记录受控摘要。过滤换行，限制长度，配置访问权限、保留期及删除策略。[OWASP 日志规范](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)

按 operationId 统计请求量、成功率、p50/p95/p99、429、5xx、412、幂等未知状态年龄及依赖超时；指标标签不放用户 ID、key 或原始路径，避免基数失控。权限变更及人工恢复写入独立审计。Problem Details 只返回可处理的错误描述与追踪标识，不暴露 SQL、堆栈或 token；`status` 与实际 HTTP 状态一致。[RFC 9457](https://www.rfc-editor.org/rfc/rfc9457.html)

## 18 兼容性与发布回滚

以下按“已发布旧客户端调用新服务端”判断；新客户端先于服务端上线是另一方向，必须另外验证。`default` 不会自动补齐请求，也不能抵消新增必填字段造成的破坏。

| 契约变化 | 对旧客户端 | 发布要求 |
|---|---|---|
| 请求字段变必填、缩短 maxLength、收紧 pattern、删除可接受枚举/null | 破坏 | 新主版本或保留旧行为 |
| 新增可选请求字段、扩大请求枚举 | 通常兼容 | 先服务端后客户端；旧服务端可能拒绝新字段/值 |
| 删除/重命名响应字段，必填改可选，允许原本不允许的 null | 破坏 | 新主版本；保留过渡表示 |
| 增加响应字段 | 有条件兼容 | 旧客户端必须忽略未知字段；严格闭合响应 schema 会破坏 |
| 增加响应枚举值/union 分支 | 破坏 | 预先定义开放值和未知分支处理，不能事后假定兼容 |
| 可选响应字段变必填、缩小响应枚举 | 通常兼容 | 检查客户端生成代码、业务语义与回滚旧实例 |
| 修改排序、分页一致性、错误含义、权限或副作用 | 可能破坏 | 人工语义评审，diff 工具不能证明兼容 |

以已发布生产契约为基线运行 `oasdiff breaking`，同时审查 changelog；固定工具版本，忽略项必须附原因、接口 owner、迁移期限。工具报告与真实 SDK/服务端验证结合使用。[oasdiff 官方变更检测](https://github.com/oasdiff/oasdiff/blob/main/docs/BREAKING-CHANGES.md)

采用先扩展后收缩：增加兼容数据库结构 → 发布兼容新旧契约的服务端 → 小流量灰度 → 发布客户端 → 迁移存量 → 达到弃用条件后删除旧行为。灰度比例、观察窗口和自动停止阈值由 SRE 在发布单填写；例如按租户稳定分组从 1% 到 10% 再扩大，观察错误率、延迟及未知幂等记录。新旧实例必须共享兼容的幂等存储、cursor/ETag 版本处理和签名密钥轮换窗口。

回滚包括应用、配置与数据兼容方案：保留上个可用制品和客户端功能开关；旧服务能读取新数据前才可切回。禁止把“回滚代码”当作自动撤销业务写入。不可逆迁移先备份并验证恢复流程，必要时停止写流量、前向修复。契约、SDK、镜像摘要、数据库迁移版本和发布记录必须关联同一发布 ID。

## 19 测试门禁与责任清单

每次契约变更依次执行：语法/ref 解析与 lint → 正反例 schema 验证 → 与生产基线兼容性比较 → SDK 确定性生成和编译 → 提供方集成验证 → 发布前验收。线上默认校验全部请求；响应校验至少在测试环境全量启用，生产采样时需脱敏。仅生成 TypeScript 类型或 Mock 不构成运行时验证。

必须覆盖：跨租户和越权字段、过期 token、CORS/CSRF；description 缺失/null；同 key 并发只产生一个资源、异体冲突、提交后断连、租约接管、终态过期；旧 ETag 冲突和并发更新；游标篡改及并发增删；429/Retry-After、deadline、代理返回 HTML/空正文；新旧客户端/服务端交叉组合。外部副作用场景增加 outbox 重投和下游去重恢复测试。CI 凭据最小授权，依赖固定版本/锁文件，禁止 PR 不可信代码获取生产密钥。

| 责任角色 | 上线前必须交付的证据 |
|---|---|
| API owner / 前后端负责人 | 已评审契约、兼容报告、生成 SDK、错误与迁移说明 |
| 后端 / 数据负责人 | 原子性与并发测试、幂等恢复演练、索引计划、迁移/恢复步骤 |
| 安全 / 身份负责人 | OAuth 配置、对象授权测试、Cookie/CORS/CSRF、密钥轮换与审计策略 |
| QA | 正反例、真实提供方合同测试、新旧版本交叉验收记录 |
| SRE / 发布负责人 | 容量阈值、SLO/告警、灰度条件、回滚制品与值班联系人 |

任一证据缺失时保持“待验收”状态；文档完整和静态检查通过不等于业务服务已经可直接上线。

## 20 工程执行与示例调用

在仓库根目录执行以下命令。Python 3.12 及 Node.js 24.19.0 是 CI 基线，Node.js 包管理器固定为 pnpm 11.19.0。更换版本须重新跑完整检查。`requirements-contract.lock` 和 `pnpm-lock.yaml` 固定实际依赖解析，安装时不得忽略锁文件。

Windows PowerShell：

```powershell
py -3.12 -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements-contract.lock
.venv/Scripts/python.exe scripts/verify_contract.py
.venv/Scripts/python.exe -m unittest discover -s tests -v
pnpm install --frozen-lockfile
pnpm validate
.venv/Scripts/python.exe scripts/build_docs.py
```

Linux 或 macOS：

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-contract.lock
.venv/bin/python scripts/verify_contract.py
.venv/bin/python -m unittest discover -s tests -v
pnpm install --frozen-lockfile
pnpm validate
.venv/bin/python scripts/build_docs.py
```

修改 YAML 后先执行 `pnpm generate`，评审生成差异，再执行 `pnpm validate`。生成检查失败不能靠手工编辑 schema.d.ts 修复。浏览器阅读版由标准库脚本生成，不依赖网络资源；阅读版末尾含可展开的完整 YAML 快照，维护时以 YAML 源文件为准。

以下 bash 示例要求先在本地安全配置 `API_BASE_URL` 与 `ACCESS_TOKEN`；地址指向团队已部署的服务。示例 UUID 用来表示一次逻辑提交的幂等键，实际应用需生成新的高熵值并在该提交重试中保持不变。

```bash
curl --fail-with-body -i \
  -X POST "${API_BASE_URL:?}/v1/projects" \
  -H "Authorization: Bearer ${ACCESS_TOKEN:?}" \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: 9c4de9a9-c624-4510-8704-76cd3cfa6610' \
  --data '{"displayName":"生产接入示例","description":null}'
```

成功时应收到 201、Location、ETag 和完整 Project。以服务端实际返回的 ID 与 ETag 更新：

```bash
curl --fail-with-body -i \
  -X PATCH "${API_BASE_URL:?}/v1/projects/${PROJECT_ID:?}" \
  -H "Authorization: Bearer ${ACCESS_TOKEN:?}" \
  -H 'Content-Type: application/merge-patch+json' \
  -H "If-Match: ${PROJECT_ETAG:?}" \
  --data '{"description":"已完成首次接入"}'
```

`PROJECT_ETAG` 包含服务端返回的双引号，例如字符串值 `"1"`。不要只传整数 1。对同一个已变化资源重用旧标签，应得到 412。命令可能显示业务数据与响应头，执行时遵循终端记录与凭据使用规则。

## 21 生产验收用例矩阵

下表用于目标环境的提供方验收，配套静态工具与 Mock Fetch 测试只覆盖其中一部分。测试记录必须标明服务地址所属环境、镜像摘要、契约版本、执行时间和结果，不以本手册替代真实服务测试。

| 编号 | 输入或故障 | 必须验证的结果 |
| --- | --- | --- |
| P01 | 合法创建后读取 | 201 与 200 一致，Location 正确，ETag 可用于更新 |
| P02 | 缺少 displayName 或仅空白 | 422，errors 指向对应字段 |
| P03 | 提交未知字段 tenantId 或 version | 请求被拒绝，不改变归属或版本 |
| P04 | description 缺省与 null | 创建缺省规范化，PATCH 缺省不变，null 清除 |
| P05 | 非法 UUID 或重复查询参数 | 400，不触发业务写入 |
| P06 | 损坏 JSON 或错误媒体类型 | 分别返回 400 或 415 |
| P07 | 缺少或过期令牌 | 401，返回正确的认证挑战 |
| P08 | 跨租户访问已知资源 ID | 被拒绝，不泄露对象或历史幂等结果 |
| P09 | 同 key 同请求并发提交 | 业务资源仅创建一次，终态可回放 |
| P10 | 同 key 换请求体 | 409 幂等键复用冲突 |
| P11 | 提交事务后丢失响应 | 同 key 可取回结果，不重复执行 |
| P12 | 处理中节点崩溃或租约到期 | 先查询事实和对账，旧执行者不能继续写入 |
| P13 | 两个客户端使用同一 ETag 更新 | 最多一个条件写入成功，其余 412 |
| P14 | 缺少条件头或使用弱标签 | 分别返回 428 或 400 |
| P15 | 删除成功 | 204 且无响应体，后续读取按策略返回 404 |
| P16 | 游标篡改或跨上下文使用 | 400 INVALID_CURSOR，不扩大数据范围 |
| P17 | 达到限流与依赖不可用 | 429 或 503，Retry-After 与实际恢复策略一致 |
| P18 | 代理返回 HTML 或连接取消 | 客户端保留错误状态，界面无 JSON 解析崩溃 |
| P19 | 内容编码及网关变换 | 强 ETag 与实际表示一致，禁止错误共用标签 |
| P20 | 新旧客户端与服务端组合 | 滚动升级与回滚均符合已声明兼容范围 |

响应验收同时检查状态码、Content-Type、必要响应头、Schema 和业务结果。接口支持超大整数、emoji 或组合字符时增加相应跨语言测试。并发测试需实际触发竞争与故障窗口，仅循环顺序调用不足以验证原子性。

## 22 版本治理与变更记录

本方案将 `/v1` 作为不兼容接口的主版本边界。`info.version` 使用语义版本：兼容的新能力递增次版本，文档修正或不改变契约接受集合的修复递增修订版本。发现线上实现与契约不符时，先评估消费者依赖，再决定修复行为或发布迁移方案，不能简单以“修 bug”为由忽略兼容性。

生产契约基线取自最近成功发布的不可变制品，保存提交号和 SHA256。比较基线不得使用待评审分支中的同名文件，否则开发者可以同时修改基线使检查失效。首次发布没有历史生产基线，应明确登记首次验收，并在发布成功后建立基线。

可采用固定版本的 oasdiff 执行以下检查。`--fail-on WARN` 使警告和错误都会阻止流水线；仅执行打印差异的命令不能自动构成门禁。工具安装与摘要校验由 CI 的受控工具镜像负责，禁止在每次运行时获取未固定的 latest。[oasdiff 变更检测](https://github.com/oasdiff/oasdiff/blob/main/docs/BREAKING-CHANGES.md)

```bash
oasdiff breaking --fail-on WARN \
  artifacts/production-openapi.yaml contracts/openapi.yaml
oasdiff changelog \
  artifacts/production-openapi.yaml contracts/openapi.yaml
```

本仓库提供静态与客户端 CI；生产基线获取、提供方集成测试、压测及发布流程需要连接团队实际系统。兼容性门禁无法仅从当前仓库推导历史生产状态，配置时应要求缺失基线失败，并仅允许经过登记的首次发布流程建立初始基线。

一次变更的发布记录至少填写以下项目：

```text
变更标题
业务触发场景与预期结果
契约版本与提交号
受影响的 operationId 和字段
旧客户端访问新服务端的兼容结论
新客户端访问旧服务端的兼容结论
数据库及配置变更
幂等 ETag Cursor 的迁移影响
自动检查结果与目标环境验收记录
灰度比例 观察窗口 停止条件
回滚制品 数据处理步骤及负责人
弃用起始日期 迁移目标和停止服务条件
```

弃用应有可发现的说明、迁移指引和调用量证据。团队应先设定支持周期，再与消费方确认实际迁移窗口；删除旧版本前确认剩余调用来源与处理方案。规范中的 `deprecated: true` 是描述信息，需要配合监控和发布治理才会产生实际效果。

## 23 常见故障处理手册

| 现象 | 首先检查 | 处理方式 |
| --- | --- | --- |
| 生成类型与后端不一致 | 契约版本和生成差异 | 修正契约或实现，重新生成和验证 |
| 文档能调用但浏览器失败 | Origin、预检与响应头暴露 | 对照 CORS 来源名单和实际方法检查 |
| 浏览器读不到 ETag | Access-Control-Expose-Headers | 明确暴露 ETag，避免 UI 保存空标签 |
| POST 超时后重复资源 | key 是否复用和幂等事务边界 | 关联日志与业务记录，修复原子性及恢复流程 |
| 并发更新覆盖他人修改 | If-Match 和数据库条件写 | 使用原子条件更新，412 不自动覆盖 |
| 分页出现变动 | 是否误认为快照与排序键是否稳定 | 核查 keyset 条件，导出改用快照任务 |
| 客户端遇到新错误码崩溃 | 是否穷尽匹配而无兜底 | 未知 code 回退通用错误并保存 traceId |
| 发布后旧客户端报错 | 请求收紧、响应空值或枚举变化 | 停止灰度，恢复兼容行为或执行迁移 |

排障时首先保留 operationId、traceId、契约版本、HTTP 状态和发生时间，再按授权范围读取服务端日志。幂等结果未知、数据库迁移异常或跨租户风险应由对应负责人接手。任何手工数据修复必须保留修改原因、前后状态摘要和执行记录。

## 24 参考资料

本规范的阈值、命名、分页协议、幂等状态机和发布流程属于团队设计。以下资料用于核对相关技术标准和工具行为，查阅日期为2026年9月14日。

- [OpenAPI 3.1.0 规范](https://spec.openapis.org/oas/v3.1.0.html)
- [JSON Schema 对象约束](https://json-schema.org/understanding-json-schema/reference/object)
- [JSON Schema 类型](https://json-schema.org/understanding-json-schema/reference/type)
- [RFC 8259 JSON](https://www.rfc-editor.org/rfc/rfc8259.html)
- [RFC 3339 时间戳](https://www.rfc-editor.org/rfc/rfc3339.html)
- [RFC 9110 HTTP 语义](https://www.rfc-editor.org/rfc/rfc9110.html)
- [RFC 6585 条件请求与限流状态](https://www.rfc-editor.org/rfc/rfc6585.html)
- [RFC 7396 JSON Merge Patch](https://www.rfc-editor.org/rfc/rfc7396.html)
- [RFC 9457 Problem Details](https://www.rfc-editor.org/rfc/rfc9457.html)
- [RFC 9700 OAuth 安全实践](https://www.rfc-editor.org/rfc/rfc9700.html)
- [WHATWG Fetch 与 CORS](https://fetch.spec.whatwg.org/)
- [OWASP 对象级授权](https://api-security.owasp.org/editions/2023/en/0xa1-broken-object-level-authorization/)
- [OWASP CSRF 防护](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)
- [OWASP 日志规范](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [W3C Trace Context](https://www.w3.org/TR/trace-context/)
- [openapi-typescript](https://openapi-ts.dev/introduction)
- [openapi-fetch](https://openapi-ts.dev/openapi-fetch/)
- [oasdiff](https://github.com/oasdiff/oasdiff/blob/main/docs/BREAKING-CHANGES.md)
